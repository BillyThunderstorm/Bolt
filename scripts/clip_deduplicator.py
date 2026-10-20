#!/usr/bin/env python3
"""
Hash-based Duplicate Detection for Bolt (READY)
===============================================
Finds byte-identical media files (SHA256) across Bolt's media folders and
reports each duplicate group with sizes and reclaimable space. Read-only on
media: it never deletes, moves or rewrites a media file. The only file it
writes is the hash cache ``Data/media_hash_db.json`` (atomic, Finder tags kept).

Default scan (any that exist):
  media/clips, recordings folder (Core/config.json ``recordings_folder``,
  default media/Recordings), media/vertical_clips, media/output, media/covers

Incremental: a file whose size + mtime are unchanged since the last run reuses
its cached hash, so re-runs only read new/changed files. Entries for files
that disappeared from a scanned folder are pruned.

Matches video/image/audio extensions case-insensitively (``.MOV`` etc.), skips
macOS AppleDouble ``._name`` sidecars, hidden files/folders and symlinks.
Hard links of one file are not counted as reclaimable.

Usage (prefer ``bolt clip-dedupe run``):
  python3 scripts/clip_deduplicator.py                 # scan + report + save cache
  python3 scripts/clip_deduplicator.py --dry-run       # scan + report, cache not saved
  python3 scripts/clip_deduplicator.py --scan media/clips [--scan DIR ...]
  python3 scripts/clip_deduplicator.py --check path/to/file.mp4   # exit 1 if duplicate
  python3 scripts/clip_deduplicator.py --rehash        # ignore cache, hash everything
  python3 scripts/clip_deduplicator.py --json [--limit N]
  python3 scripts/clip_deduplicator.py --clear-db      # delete the hash cache only

Distinct from READY pipeline ``Core/modules/Clip_Deduplicator.py`` (pHash
during ``process_recording`` → ``Data/seen_clips.json``).
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import (  # noqa: E402
    REPO_ROOT,
    DATA_DIR,
    CLIPS_DIR,
    RECORDINGS_DIR,
    VERTICAL_CLIPS_DIR,
    OUTPUT_DIR,
    MEDIA_DIR,
    CONFIG_FILE,
)

SOFT = "Hash dedupe unavailable:"
DB_VERSION = 2

# Backward-compatible aliases
PROJECT_ROOT = REPO_ROOT
HASH_DB_PATH = DATA_DIR / "media_hash_db.json"
DRY_RUN = False

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".flv", ".ts", ".hybrid_mov"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aif", ".aiff", ".flac"}
MEDIA_EXTS = VIDEO_EXTS | IMAGE_EXTS | AUDIO_EXTS

TAG_XATTR = "com.apple.metadata:_kMDItemUserTags"
FINDER_INFO_XATTR = "com.apple.FinderInfo"
DATA_TAG = "Orange\n7"  # Bolt colour scheme: orange = data

_CHUNK = 1 << 20  # 1 MiB
_BIG_FILE = 100 * 1024 * 1024  # print a progress line for files over 100 MB


# ── paths ───────────────────────────────────────────────────────────────────

def _resolve_clips_dir() -> Path:
    legacy = REPO_ROOT / "clips"
    if not CLIPS_DIR.is_dir() and legacy.is_dir():
        return legacy
    return CLIPS_DIR


def _resolve_recordings_dir() -> Path:
    """Recordings folder: env RECORDINGS_FOLDER > config recordings_folder > media/Recordings."""
    candidates: List[Path] = []
    env = os.environ.get("RECORDINGS_FOLDER", "").strip()
    if env:
        candidates.append(Path(env).expanduser())
    try:
        cfg = json.loads(Path(CONFIG_FILE).read_text(encoding="utf-8"))
        rf = str(cfg.get("recordings_folder") or "").strip()
        if rf:
            p = Path(rf).expanduser()
            candidates.append(p if p.is_absolute() else REPO_ROOT / p)
    except Exception:
        pass
    candidates += [RECORDINGS_DIR, MEDIA_DIR / "recordings", REPO_ROOT / "recordings"]
    for c in candidates:
        if c.is_dir():
            return c
    return RECORDINGS_DIR


def default_scan_dirs() -> List[Path]:
    """Default folders, in keep-priority order (earlier folder wins a tie)."""
    out: List[Path] = []
    for d in (
        _resolve_clips_dir(),
        _resolve_recordings_dir(),
        VERTICAL_CLIPS_DIR,
        OUTPUT_DIR,
        MEDIA_DIR / "covers",
    ):
        if d not in out:
            out.append(d)
    return out


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _abs(rel: str, repo_root: Path) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else repo_root / p


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def human_size(n: float) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ── file walking / hashing ─────────────────────────────────────────────────

def is_media_file(path: Path) -> bool:
    name = path.name
    if name.startswith("."):  # AppleDouble ._x, .DS_Store, hidden temp files
        return False
    return path.suffix.lower() in MEDIA_EXTS


def iter_media(root: Path, counters: Optional[Dict[str, int]] = None) -> Iterator[Path]:
    """Yield media files under root (sorted, no symlinks, no hidden dirs)."""
    counters = counters if counters is not None else {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            if fn.startswith("._"):
                counters["appledouble"] = counters.get("appledouble", 0) + 1
                continue
            if not is_media_file(p):
                continue
            if p.is_symlink():
                counters["symlinks"] = counters.get("symlinks", 0) + 1
                continue
            yield p


def calculate_hash(file_path: Path, chunk_size: int = _CHUNK) -> Optional[str]:
    """SHA256 of a file (None on read error)."""
    h = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                h.update(chunk)
        return h.hexdigest()
    except (IOError, OSError) as e:
        print(f"  ! could not read {file_path}: {e}", file=sys.stderr)
        return None


# ── hash DB (atomic, keeps Finder tags) ─────────────────────────────────────

def _empty_db() -> Dict[str, Any]:
    return {"version": DB_VERSION, "updated_at": "", "files": {}, "last_run": {}}


def load_hash_db(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load the cache; migrates v1 ({hash: path}) and survives a corrupt file."""
    db_path = Path(db_path or HASH_DB_PATH)
    if not db_path.exists():
        return _empty_db()
    try:
        raw = json.loads(db_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        print(f"  ! hash cache unreadable ({e}); starting fresh", file=sys.stderr)
        try:
            shutil.copyfile(db_path, db_path.with_name(db_path.name + ".corrupt"))
        except OSError:
            pass
        return _empty_db()
    if not isinstance(raw, dict):
        return _empty_db()
    db = _empty_db()
    db["updated_at"] = str(raw.get("updated_at") or "")
    db["last_run"] = raw.get("last_run") if isinstance(raw.get("last_run"), dict) else {}
    files = raw.get("files") if isinstance(raw.get("files"), dict) else {}
    for key, val in files.items():
        # v2: {rel_path: {sha256, size, mtime_ns}}; v1 {sha: rel_path} has no
        # size/mtime so it can't be reused — dropped (rehashed on next run).
        if isinstance(val, dict) and val.get("sha256"):
            db["files"][str(key)] = val
    return db


def _darwin() -> bool:
    return platform.system() == "Darwin" and bool(shutil.which("xattr"))


def _read_xattr(path: Path, name: str) -> Optional[str]:
    try:
        r = subprocess.run(["xattr", "-px", name, str(path)], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return " ".join(r.stdout.split())
    except Exception:
        pass
    return None


def _write_xattr(path: Path, name: str, hexval: str) -> bool:
    try:
        r = subprocess.run(["xattr", "-wx", name, hexval, str(path)], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def save_hash_db(db: Dict[str, Any], db_path: Optional[Path] = None) -> Path:
    """Atomic save: temp file → verify → copy Finder tags → os.replace.

    os.replace alone would drop the Finder tag xattrs on macOS, so the old
    file's tags (and FinderInfo colour) are copied onto the temp file first.
    A brand-new cache gets the Bolt data tag (Orange).
    """
    db_path = Path(db_path or HASH_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(db, indent=2, sort_keys=False) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".media_hash_db.", suffix=".tmp", dir=str(db_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        check = json.loads(Path(tmp).read_text(encoding="utf-8"))
        if len(check.get("files", {})) != len(db.get("files", {})):
            raise IOError("temp write verify failed")
        if _darwin():
            tags = None
            if db_path.exists():
                tags = _read_xattr(db_path, TAG_XATTR)
                finfo = _read_xattr(db_path, FINDER_INFO_XATTR)
                if finfo:
                    _write_xattr(Path(tmp), FINDER_INFO_XATTR, finfo)
            if not tags:
                tags = plistlib.dumps([DATA_TAG], fmt=plistlib.FMT_BINARY).hex()
            _write_xattr(Path(tmp), TAG_XATTR, tags)
        os.chmod(tmp, 0o644)
        os.replace(tmp, db_path)
        tmp = ""
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
    return db_path


# ── scan ───────────────────────────────────────────────────────────────────

def scan(
    dirs: Iterable[Path],
    *,
    db_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    dry_run: bool = False,
    rehash: bool = False,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Scan dirs, hash (incrementally), group duplicates, save cache."""
    t0 = time.monotonic()
    repo_root = Path(repo_root or REPO_ROOT)
    db_path = Path(db_path or HASH_DB_PATH)
    db = load_hash_db(db_path)
    cache: Dict[str, Dict[str, Any]] = db["files"]
    dirs = [Path(d).expanduser() for d in dirs]
    dirs = [d if d.is_absolute() else (repo_root / d) for d in dirs]

    counters: Dict[str, int] = {}
    scanned_roots: List[Path] = []
    missing_roots: List[str] = []
    seen: Dict[str, Dict[str, Any]] = {}  # rel -> info
    seen_real: set = set()
    errors: List[str] = []
    hashed = reused = 0
    bytes_hashed = 0
    per_dir: Dict[str, Dict[str, int]] = {}

    for prio, root in enumerate(dirs):
        if not root.is_dir():
            missing_roots.append(_rel(root, repo_root))
            continue
        scanned_roots.append(root.resolve())
        stats = {"files": 0, "bytes": 0}
        per_dir[_rel(root, repo_root)] = stats
        for p in iter_media(root, counters):
            try:
                real = str(p.resolve())
                if real in seen_real:  # overlapping --scan roots
                    continue
                st = p.stat()
            except OSError as e:
                errors.append(f"{p}: {e}")
                continue
            seen_real.add(real)
            rel = _rel(p, repo_root)
            prev = cache.get(rel)
            sha = None
            if (
                not rehash
                and prev
                and prev.get("size") == st.st_size
                and prev.get("mtime_ns") == st.st_mtime_ns
                and prev.get("sha256")
            ):
                sha = prev["sha256"]
                reused += 1
            else:
                if verbose and st.st_size >= _BIG_FILE:
                    print(f"  hashing {rel} ({human_size(st.st_size)})", flush=True)
                sha = calculate_hash(p)
                if sha is None:
                    errors.append(f"{rel}: unreadable")
                    continue
                hashed += 1
                bytes_hashed += st.st_size
            cache[rel] = {
                "sha256": sha,
                "size": st.st_size,
                "mtime_ns": st.st_mtime_ns,
                "hashed_at": (
                    prev.get("hashed_at") or _utc_now()
                    if prev and prev.get("sha256") == sha
                    else _utc_now()
                ),
            }
            seen[rel] = {
                "path": rel,
                "sha256": sha,
                "size": st.st_size,
                "mtime": st.st_mtime,
                "inode": (st.st_dev, st.st_ino),
                "prio": prio,
            }
            stats["files"] += 1
            stats["bytes"] += st.st_size

    # Prune cache entries for files gone from the folders we scanned (and
    # entries elsewhere whose file no longer exists).
    pruned = 0
    for rel in list(cache.keys()):
        if rel in seen:
            continue
        ap = _abs(rel, repo_root)
        try:
            ap_res = ap.resolve()
        except OSError:
            ap_res = ap
        inside = any(_under(ap_res, r) for r in scanned_roots)
        if inside or not ap.exists():
            del cache[rel]
            pruned += 1

    groups = build_groups(seen.values())
    elapsed = time.monotonic() - t0
    summary = {
        "ran_at": _utc_now(),
        "dry_run": bool(dry_run),
        "rehash": bool(rehash),
        "scan_dirs": [_rel(r, repo_root) for r in dirs if r.is_dir()],
        "missing_dirs": missing_roots,
        "per_dir": per_dir,
        "files_scanned": len(seen),
        "bytes_scanned": sum(i["size"] for i in seen.values()),
        "hashed": hashed,
        "reused": reused,
        "bytes_hashed": bytes_hashed,
        "pruned": pruned,
        "skipped_appledouble": counters.get("appledouble", 0),
        "skipped_symlinks": counters.get("symlinks", 0),
        "errors": errors,
        "duplicate_groups": len(groups),
        "duplicate_files": sum(len(g["duplicates"]) for g in groups),
        "reclaimable_bytes": sum(g["reclaimable_bytes"] for g in groups),
        "elapsed_s": round(elapsed, 2),
        "db_path": str(db_path),
        "db_saved": False,
    }
    if not dry_run:
        db["version"] = DB_VERSION
        db["updated_at"] = summary["ran_at"]
        db["files"] = dict(sorted(cache.items()))
        db["last_run"] = dict(summary, groups=groups, db_saved=True)
        save_hash_db(db, db_path)
        summary["db_saved"] = True
    summary["groups"] = groups
    return summary


def build_groups(infos: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group identical files; keep = earliest scan folder, then oldest, then shortest path."""
    by_sha: Dict[str, List[Dict[str, Any]]] = {}
    for i in infos:
        by_sha.setdefault(i["sha256"], []).append(i)
    groups: List[Dict[str, Any]] = []
    for sha, items in by_sha.items():
        if len(items) < 2:
            continue
        items.sort(key=lambda i: (i["prio"], i["mtime"], len(i["path"]), i["path"]))
        keep = items[0]
        inodes = {tuple(i["inode"]) for i in items}
        size = keep["size"]
        dups = items[1:]
        hardlinked = [i["path"] for i in dups if tuple(i["inode"]) == tuple(keep["inode"])]
        groups.append(
            {
                "sha256": sha,
                "size": size,
                "count": len(items),
                "keep": keep["path"],
                "duplicates": [i["path"] for i in dups],
                "hardlinks": hardlinked,
                "reclaimable_bytes": size * (len(inodes) - 1),
            }
        )
    groups.sort(key=lambda g: (-g["reclaimable_bytes"], g["keep"]))
    return groups


def check_file_for_duplicates(
    file_path: Path, hash_db: Optional[Dict[str, Any]] = None, *, repo_root: Optional[Path] = None
) -> List[str]:
    """Return existing cached paths byte-identical to file_path (empty = unique)."""
    repo_root = Path(repo_root or REPO_ROOT)
    file_path = Path(file_path).expanduser()
    if hash_db is None:
        hash_db = load_hash_db()
    if not file_path.is_absolute():
        file_path = Path.cwd() / file_path
    try:
        st = file_path.stat()
        real = file_path.resolve()
    except OSError as e:
        raise FileNotFoundError(f"{file_path}: {e}")
    # Cache keys are relative to the (unresolved) repo root; match either form
    # so /var vs /private/var style symlinks don't report a file as its own copy.
    rel = _rel(file_path, repo_root)
    if rel not in hash_db.get("files", {}):
        rel = _rel(real, repo_root.resolve())
    prev = hash_db.get("files", {}).get(rel)
    if prev and prev.get("size") == st.st_size and prev.get("mtime_ns") == st.st_mtime_ns:
        sha = prev.get("sha256")
    else:
        sha = calculate_hash(file_path)
    if not sha:
        return []
    out = []
    for other, info in hash_db.get("files", {}).items():
        if other == rel or info.get("sha256") != sha:
            continue
        op = _abs(other, repo_root)
        try:
            if not op.exists() or op.resolve() == real:
                continue  # gone, or the same file under another spelling
        except OSError:
            continue
        out.append(other)
    return sorted(out)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── report ─────────────────────────────────────────────────────────────────

def print_report(s: Dict[str, Any], *, limit: int = 20) -> None:
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for d, st in (s.get("per_dir") or {}).items():
        print(f"  {d}: {st['files']} files, {human_size(st['bytes'])}")
    if s.get("missing_dirs"):
        print(f"  (not found, skipped: {', '.join(s['missing_dirs'])})")
    print(
        f"Files scanned: {s['files_scanned']} ({human_size(s['bytes_scanned'])}) — "
        f"hashed {s['hashed']} ({human_size(s['bytes_hashed'])}), reused {s['reused']} from cache"
    )
    extra = []
    if s.get("skipped_appledouble"):
        extra.append(f"{s['skipped_appledouble']} AppleDouble ._ files")
    if s.get("skipped_symlinks"):
        extra.append(f"{s['skipped_symlinks']} symlinks")
    if s.get("pruned"):
        extra.append(f"pruned {s['pruned']} gone file(s) from cache")
    if extra:
        print("Skipped: " + "; ".join(extra))
    if s.get("errors"):
        print(f"Errors ({len(s['errors'])}):")
        for e in s["errors"][:10]:
            print(f"  ! {e}")
    groups = s.get("groups") or []
    print(
        f"Duplicate groups: {s['duplicate_groups']} ({s['duplicate_files']} extra copies) — "
        f"reclaimable {human_size(s['reclaimable_bytes'])}"
    )
    for n, g in enumerate(groups[:limit], 1):
        print(
            f"\n  [{n}] {g['count']} × {human_size(g['size'])} "
            f"(reclaim {human_size(g['reclaimable_bytes'])}) sha256 {g['sha256'][:12]}…"
        )
        print(f"      keep: {g['keep']}")
        for d in g["duplicates"]:
            tag = "  (hard link — same file, no space)" if d in g.get("hardlinks", []) else ""
            print(f"      dup:  {d}{tag}")
    if len(groups) > limit:
        print(f"\n  … and {len(groups) - limit} more group(s) (use --limit N or --json)")
    if groups:
        print(
            "\nNothing was deleted or moved. Review the dup lines and remove copies "
            "yourself in Finder if you want the space back."
        )
    saved = "saved" if s.get("db_saved") else "not saved (dry run)"
    print(f"Hash cache: {s['db_path']} ({saved}) · {s['elapsed_s']:.2f} s")


# ── CLI ────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    global DRY_RUN
    args = list(sys.argv[1:] if argv is None else argv)
    dirs: List[Path] = []
    check: Optional[str] = None
    as_json = False
    rehash = False
    limit = 20
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--dry-run", "-n"):
            DRY_RUN = True
        elif a == "--scan" and i + 1 < len(args):
            dirs.append(Path(args[i + 1]))
            i += 1
        elif a == "--check" and i + 1 < len(args):
            check = args[i + 1]
            i += 1
        elif a == "--limit" and i + 1 < len(args):
            try:
                limit = max(0, int(args[i + 1]))
            except ValueError:
                pass
            i += 1
        elif a == "--json":
            as_json = True
        elif a == "--rehash":
            rehash = True
        elif a in ("--clear-db", "--clear"):
            if HASH_DB_PATH.exists():
                if DRY_RUN or "--dry-run" in args:
                    print(f"[dry-run] would delete hash cache: {HASH_DB_PATH}")
                else:
                    os.remove(HASH_DB_PATH)
                    print(f"Hash cache cleared (media untouched): {HASH_DB_PATH}")
            else:
                print(f"No hash cache at: {HASH_DB_PATH}")
            return 0
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        i += 1

    try:
        if check:
            p = Path(check).expanduser()
            if not p.is_absolute():
                p = Path.cwd() / p
            if not p.is_file():
                msg = f"{SOFT} --check file not found ({check})"
                print(json.dumps({"ok": False, "error": msg}) if as_json else msg)
                return 0
            dups = check_file_for_duplicates(p)
            if as_json:
                print(json.dumps({"ok": True, "file": str(p), "duplicate": bool(dups), "duplicate_of": dups}, indent=2))
            elif dups:
                print(f"Duplicate: {p.name} is byte-identical to:")
                for d in dups:
                    print(f"  {d}")
            else:
                print(f"Unique: {p.name} matches nothing in the hash cache "
                      f"({len(load_hash_db().get('files', {}))} files; run bolt clip-dedupe run to refresh)")
            return 1 if dups else 0

        if not dirs:
            dirs = default_scan_dirs()
        existing = [d for d in dirs if (d if d.is_absolute() else REPO_ROOT / d).is_dir()]
        if not existing:
            msg = (
                f"{SOFT} no media folders found ({', '.join(_rel(d, REPO_ROOT) for d in dirs)}) — "
                "run bolt recordings or bolt wrap first, or pass --scan DIR"
            )
            print(json.dumps({"ok": False, "error": msg}) if as_json else msg)
            return 0

        if not as_json:
            print("=" * 60)
            print("Bolt duplicate finder (SHA256, read-only on media)")
            print("=" * 60)
            print(f"Scan: {', '.join(_rel(d if d.is_absolute() else REPO_ROOT / d, REPO_ROOT) for d in dirs)}")
            if DRY_RUN:
                print("DRY RUN — hash cache will not be saved")
            if rehash:
                print("REHASH — ignoring cached hashes")
        s = scan(dirs, dry_run=DRY_RUN, rehash=rehash, verbose=not as_json)
        if as_json:
            out = dict(s)
            out["ok"] = True
            out["groups"] = s["groups"][:limit] if limit else s["groups"]
            print(json.dumps(out, indent=2))
        else:
            print_report(s, limit=limit)
        return 0
    except KeyboardInterrupt:
        print(f"\n{SOFT} interrupted — hash cache not saved")
        return 130
    except Exception as exc:  # never traceback at the user
        msg = f"{SOFT} {type(exc).__name__}: {exc}"
        print(json.dumps({"ok": False, "error": msg}) if as_json else msg)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
