#!/usr/bin/env python3
"""
Media_Retention — the single place Bolt decides which media may be thrown away.

Used by scripts/storage_optimization.sh (nightly 3 AM, the one real cleaner)
and scripts/media_rotation.sh (size limits; storage_monitor.sh calls it).

Rules (approved by William, 2026-10-20):
  1. Never touch a clip that an unposted / unrejected post-queue entry still
     needs (Data/ready_to_post.json + Data/multi_platform_queue.json). Matching
     is by file name stem, so the horizontal clip, its vertical ``_tiktok``
     version, thumbnails, and the source recording (``<source>_clipNN_…``) are
     all protected together.
  2. Age = when Bolt made the file: a time field in the clip's .json sidecar or
     ``first_seen`` in Data/media_hash_db.json; otherwise the LATER of mtime and
     birthtime (yt-dlp downloads and new ffmpeg cuts now get a fresh mtime too).
  3. Nothing is deleted outright: files go to the macOS Trash (``/usr/bin/trash``,
     then Finder, then ~/.Trash). Every decision is logged to
     logs/media_retention.log with a Central-time timestamp and the reason.

CLI (run with the repo .venv python):
  Media_Retention.py age  --dir D [--dir D2] --days N [--label L] [--dry-run]
  Media_Retention.py size --dir D --max-gb G [--label L] [--dry-run]
  Media_Retention.py trash-file PATH --reason R [--dry-run]
  Media_Retention.py protected [--json]
  Media_Retention.py prune-queue [--dry-run]

Env overrides (tests): BOLT_RETENTION_QUEUES (os.pathsep list),
BOLT_RETENTION_HASH_DB, BOLT_RETENTION_LOG, BOLT_RETENTION_TRASH_DIR,
BOLT_RETENTION_BACKUP_DIR.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
CT = ZoneInfo("America/Chicago")

MEDIA_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".jpg", ".jpeg", ".png"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}
DONE_STATUSES = {
    "posted", "published", "uploaded", "rejected", "skipped", "removed",
    "deleted", "expired", "done", "complete", "completed", "cancelled",
    "canceled", "scrapped", "scrapped_missing_file", "missing_file", "archived",
}
SIDECAR_TIME_KEYS = (
    "created_at", "processed_at", "generated_at", "cut_at", "saved_at",
    "clipped_at", "first_seen",
)
VERTICAL_SUFFIXES = ("_tiktok",)
_CLIP_SOURCE_RE = re.compile(r"^(.*?)[_ ]clip\d+(?:_|$)")


# ── paths / env ───────────────────────────────────────────────────────────────

def _queue_files() -> list[Path]:
    env = os.environ.get("BOLT_RETENTION_QUEUES")
    if env:
        return [Path(p) for p in env.split(os.pathsep) if p]
    return [REPO / "Data" / "ready_to_post.json", REPO / "Data" / "multi_platform_queue.json"]


def _hash_db() -> Path:
    return Path(os.environ.get("BOLT_RETENTION_HASH_DB") or REPO / "Data" / "media_hash_db.json")


def _log_path() -> Path:
    return Path(os.environ.get("BOLT_RETENTION_LOG") or REPO / "logs" / "media_retention.log")


def _backup_dir() -> Path:
    return Path(os.environ.get("BOLT_RETENTION_BACKUP_DIR") or REPO / "Data" / "backups")


def now_ct() -> datetime:
    return datetime.now(CT)


def log_event(action: str, path, reason: str) -> None:
    line = f"{now_ct().strftime('%Y-%m-%d %H:%M:%S %Z')}\t{action}\t{path}\t{reason}\n"
    try:
        lp = _log_path()
        lp.parent.mkdir(parents=True, exist_ok=True)
        with open(lp, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


# ── names / protection ────────────────────────────────────────────────────────

def _stem(name: str) -> str:
    base = Path(str(name)).name
    p = Path(base)
    return p.stem if p.suffix else base


def clip_key(name: str) -> str:
    """Stem with any vertical/platform suffix removed (clip ↔ _tiktok match)."""
    s = _stem(name)
    for suf in VERTICAL_SUFFIXES:
        if s.endswith(suf):
            s = s[: -len(suf)]
    return s


def source_key(name: str) -> str | None:
    m = _CLIP_SOURCE_RE.match(clip_key(name))
    return m.group(1) if m else None


def _items(data) -> list:
    if isinstance(data, list):
        return data
    out = []
    if isinstance(data, dict):
        for key in ("clips", "items", "queue"):
            if isinstance(data.get(key), list):
                out.extend(data[key])
    return out


def _done(value) -> bool:
    return str(value or "").strip().lower() in DONE_STATUSES


def _platforms(item: dict) -> list:
    out = []
    for key in ("platforms", "platform_plan"):
        if isinstance(item.get(key), list):
            out.extend(p for p in item[key] if isinstance(p, dict))
    return out


def item_active(item: dict) -> bool:
    if not isinstance(item, dict) or _done(item.get("status")):
        return False
    plats = _platforms(item)
    if plats and all(_done(p.get("status")) for p in plats) and not item.get("status"):
        return False
    return True


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def item_media_refs(item: dict) -> list[str]:
    """Every string in the entry that names a media file, plus clip_name."""
    refs = []
    for s in _strings(item):
        if "\n" in s or ": " in s or len(s) > 1024:
            continue  # captions / descriptions, not file names
        if Path(s).suffix.lower() in MEDIA_EXTS:
            refs.append(s)
    name = item.get("clip_name")
    if isinstance(name, str) and _CLIP_SOURCE_RE.match(name):
        refs.append(name)
    return refs


def _load(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def protected_index(queue_files=None) -> dict:
    clips: set[str] = set()
    sources: set[str] = set()
    entries = 0
    for qf in queue_files or _queue_files():
        for item in _items(_load(qf)):
            if not item_active(item):
                continue
            entries += 1
            for ref in item_media_refs(item):
                k = clip_key(ref)
                if k:
                    clips.add(k)
                src = source_key(ref)
                if src:
                    sources.add(src)
    return {"clips": clips, "sources": sources, "entries": entries}


def is_protected(path, index: dict) -> bool:
    k = clip_key(Path(path).name)
    return k in index["clips"] or k in index["sources"]


# ── age ───────────────────────────────────────────────────────────────────────

def _parse_ts(value) -> float | None:
    if isinstance(value, (int, float)) and value > 1e9:
        return float(value) / (1e9 if value > 1e12 else 1)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CT)
    return dt.timestamp()


_HASH_CACHE: dict = {}


def _hash_first_seen(path: Path) -> float | None:
    db = _hash_db()
    key = str(db)
    if key not in _HASH_CACHE:
        data = _load(db) or {}
        _HASH_CACHE[key] = data.get("files", {}) if isinstance(data, dict) else {}
    files = _HASH_CACHE[key]
    try:
        rel = str(Path(path).resolve().relative_to(REPO))
    except ValueError:
        rel = str(path)
    entry = files.get(rel) or files.get(str(path))
    if isinstance(entry, dict):
        return _parse_ts(entry.get("first_seen"))
    return None


def _sidecar_time(path: Path) -> float | None:
    p = Path(path)
    for cand in (p.with_suffix(".json"), p.with_name(clip_key(p.name) + ".json")):
        if cand == p or not cand.is_file():
            continue
        data = _load(cand)
        if isinstance(data, dict):
            for k in SIDECAR_TIME_KEYS:
                ts = _parse_ts(data.get(k))
                if ts:
                    return ts
    return None


def created_time(path) -> tuple[float, str]:
    """(epoch, source) for when Bolt made this file."""
    p = Path(path)
    ts = _sidecar_time(p)
    if ts:
        return ts, "sidecar"
    ts = _hash_first_seen(p)
    if ts:
        return ts, "hash_db.first_seen"
    st = p.stat()
    birth = getattr(st, "st_birthtime", 0) or 0
    if birth > st.st_mtime:
        return float(birth), "birthtime"
    return float(st.st_mtime), "mtime"


def _fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts, CT).strftime("%Y-%m-%d %H:%M %Z")


def _media_files(dirs) -> list[Path]:
    out = []
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for root, dnames, fnames in os.walk(d):
            dnames[:] = [n for n in dnames if not n.startswith(".")]
            for n in fnames:
                f = Path(root) / n
                # Case-sensitive on purpose: same scope as the old `find -name "*.mov"`
                # rules, so e.g. iPhone IMG_*.MOV files are not newly swept up.
                if f.suffix in MEDIA_EXTS and f.is_file() and not f.is_symlink():
                    out.append(f)
    return out


# ── trash ─────────────────────────────────────────────────────────────────────

def _unique(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stamp = now_ct().strftime("%Y%m%d-%H%M%S")
    i = 0
    while True:
        cand = dest.with_name(f"{dest.stem} {stamp}{'-' + str(i) if i else ''}{dest.suffix}")
        if not cand.exists():
            return cand
        i += 1


def trash(path) -> tuple[bool, str]:
    """Move one file to the Trash. Never unlinks. Returns (ok, method)."""
    p = Path(path)
    if not p.exists():
        return False, "missing"
    test_dir = os.environ.get("BOLT_RETENTION_TRASH_DIR")
    if test_dir:
        td = Path(test_dir)
        td.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(_unique(td / p.name)))
        return True, "test-trash"
    if sys.platform == "darwin":
        if Path("/usr/bin/trash").exists():
            try:
                subprocess.run(["/usr/bin/trash", str(p)], capture_output=True, timeout=60)
            except Exception:
                pass
            if not p.exists():
                return True, "trash"
        try:
            script = f'tell application "Finder" to delete (POSIX file "{p.resolve()}" as alias)'
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=60)
        except Exception:
            pass
        if not p.exists():
            return True, "finder"
    home_trash = Path.home() / ".Trash"
    try:
        home_trash.mkdir(exist_ok=True)
        shutil.move(str(p), str(_unique(home_trash / p.name)))
        return True, "~/.Trash"
    except Exception as exc:
        return False, f"error: {exc}"


def _size(f: Path) -> int:
    try:
        return f.stat().st_size
    except OSError:
        return 0


def _apply(cands: list[dict], dry_run: bool, echo=print) -> dict:
    moved, failed, freed = 0, 0, 0
    for c in cands:
        f, reason = c["path"], c["reason"]
        if dry_run:
            echo(f"[DRY RUN] Would trash: {f} ({c['size']/1048576:.1f}MB) — {reason}")
            log_event("WOULD_TRASH", f, reason)
            moved += 1
            freed += c["size"]
            continue
        ok, method = trash(f)
        if ok:
            echo(f"Trashed: {f} ({c['size']/1048576:.1f}MB, via {method}) — {reason}")
            log_event("TRASHED", f, f"{reason} [via {method}]")
            moved += 1
            freed += c["size"]
        else:
            echo(f"Could not trash {f}: {method}")
            log_event("FAILED", f, f"{reason} [{method}]")
            failed += 1
    return {"trashed": moved, "failed": failed, "bytes": freed}


# ── plans ─────────────────────────────────────────────────────────────────────

def plan_age(dirs, days: float, now: float | None = None, index=None) -> dict:
    now = now or time.time()
    cutoff = now - days * 86400
    index = index or protected_index()
    cands, protected = [], []
    for f in _media_files(dirs):
        ts, src = created_time(f)
        if ts >= cutoff:
            continue
        info = {"path": f, "size": _size(f), "created": ts, "source": src,
                "reason": f"older than {days:g}d (made {_fmt(ts)} via {src})"}
        if is_protected(f, index):
            info["reason"] = "protected: still in post queue"
            protected.append(info)
        else:
            cands.append(info)
    return {"candidates": cands, "protected": protected}


def _dir_bytes(d: Path) -> int:
    total = 0
    for root, _, fnames in os.walk(d):
        for n in fnames:
            try:
                total += (Path(root) / n).lstat().st_size
            except OSError:
                pass
    return total


def plan_size(dir_, max_gb: float, index=None) -> dict:
    d = Path(dir_)
    index = index or protected_index()
    if not d.is_dir():
        return {"candidates": [], "protected": [], "size": 0, "limit": max_gb * 1024**3}
    size = _dir_bytes(d)
    limit = max_gb * 1024**3
    files = []
    for f in _media_files([d]):
        ts, src = created_time(f)
        files.append((ts, src, f))
    files.sort(key=lambda t: t[0])
    cands, protected = [], []
    projected = size
    for ts, src, f in files:
        if projected <= limit:
            break
        info = {"path": f, "size": _size(f), "created": ts, "source": src,
                "reason": f"size limit {max_gb:g}GB (oldest first; made {_fmt(ts)} via {src})"}
        if is_protected(f, index):
            info["reason"] = "protected: still in post queue"
            protected.append(info)
            continue
        cands.append(info)
        projected -= info["size"]
    return {"candidates": cands, "protected": protected, "size": size, "limit": limit,
            "projected": projected}


def _report_protected(protected: list[dict], label: str, dry_run: bool, echo=print):
    for p in protected:
        echo(f"Kept (in post queue): {p['path']}")
        log_event("KEPT_PROTECTED", p["path"], f"{label}: {p['reason']}" + (" [dry-run]" if dry_run else ""))


def run_age(dirs, days, label, dry_run=False, echo=print) -> dict:
    plan = plan_age(dirs, days)
    _report_protected(plan["protected"], label, dry_run, echo)
    if not plan["candidates"]:
        echo(f"No files older than {days:g} days found in {label} (by Bolt creation time)")
        return {"trashed": 0, "failed": 0, "bytes": 0, "protected": len(plan["protected"])}
    res = _apply(plan["candidates"], dry_run, echo)
    verb = "Would trash" if dry_run else "Trashed"
    echo(f"{verb} {res['trashed']} files older than {days:g} days in {label}, "
         f"{res['bytes']/1048576:.1f}MB; kept {len(plan['protected'])} queued")
    res["protected"] = len(plan["protected"])
    return res


def run_size(dir_, max_gb, label, dry_run=False, echo=print) -> dict:
    plan = plan_size(dir_, max_gb)
    gb = plan["size"] / 1024**3
    if plan["size"] <= plan["limit"]:
        echo(f"{label} directory is within size limit: {gb:.1f}GB <= {max_gb:g}GB")
        return {"trashed": 0, "failed": 0, "bytes": 0, "protected": 0}
    echo(f"{label} exceeds size limit: {gb:.1f}GB > {max_gb:g}GB — trashing oldest unqueued files")
    _report_protected(plan["protected"], label, dry_run, echo)
    res = _apply(plan["candidates"], dry_run, echo)
    verb = "Would trash" if dry_run else "Trashed"
    echo(f"{verb} {res['trashed']} files (~{res['bytes']/1024**3:.2f}GB) from {label}; "
         f"kept {len(plan['protected'])} queued. Note: Trash must be emptied to free disk space.")
    res["protected"] = len(plan["protected"])
    return res


def trash_file(path, reason, dry_run=False, echo=print) -> int:
    p = Path(path)
    if is_protected(p, protected_index()):
        echo(f"Kept (in post queue): {p}")
        log_event("KEPT_PROTECTED", p, reason)
        return 2
    res = _apply([{"path": p, "size": _size(p), "reason": reason}], dry_run, echo)
    return 0 if res["failed"] == 0 else 1


# ── queue prune ───────────────────────────────────────────────────────────────

def _resolve(ref: str) -> Path:
    p = Path(ref).expanduser()
    return p if p.is_absolute() else REPO / p


def _write_json_in_place(path: Path, data) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    json.loads(text)  # validate
    with open(path, "w", encoding="utf-8") as fh:  # in place keeps Finder tags
        fh.write(text)


def prune_queues(dry_run=False, queue_files=None, echo=print) -> dict:
    stamp = now_ct().strftime("%Y%m%d-%H%M%S")
    when = now_ct().isoformat(timespec="seconds")
    report = {"files": {}, "backups": []}
    for qf in queue_files or _queue_files():
        qf = Path(qf)
        data = _load(qf)
        if data is None:
            continue
        counts = {"entries": 0, "active": 0, "marked_missing_file": 0, "ok": 0, "no_video_ref": 0}
        changed = False
        for item in _items(data):
            if not isinstance(item, dict):
                continue
            counts["entries"] += 1
            if not item_active(item):
                continue
            counts["active"] += 1
            vids = [r for r in item_media_refs(item) if Path(r).suffix.lower() in VIDEO_EXTS]
            if not vids:
                counts["no_video_ref"] += 1
                continue
            if any(_resolve(v).is_file() for v in vids):
                counts["ok"] += 1
                continue
            counts["marked_missing_file"] += 1
            name = item.get("id") or item.get("queue_id") or item.get("clip_name") or "?"
            missing = sorted(set(vids))
            echo(f"{'[DRY RUN] ' if dry_run else ''}missing_file: {qf.name} {name} → {', '.join(Path(m).name for m in missing)}")
            log_event("QUEUE_MISSING_FILE" + ("_DRY" if dry_run else ""), qf.name + ":" + str(name),
                      "video gone: " + ", ".join(missing))
            item["missing_file_prev_status"] = item.get("status")
            item["status"] = "missing_file"
            item["missing_file_at"] = when
            item["missing_file_paths"] = missing
            for p in _platforms(item):
                if not _done(p.get("status")):
                    p["missing_file_prev_status"] = p.get("status")
                    p["status"] = "missing_file"
            changed = True
        if changed and not dry_run:
            bdir = _backup_dir()
            bdir.mkdir(parents=True, exist_ok=True)
            backup = bdir / f"{qf.stem}_{stamp}_pre-missing-file.json"
            shutil.copy2(qf, backup)
            report["backups"].append(str(backup))
            _write_json_in_place(qf, data)
        report["files"][qf.name] = counts
    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Bolt media retention (protects queued clips; trashes, never deletes)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("age")
    a.add_argument("--dir", action="append", required=True)
    a.add_argument("--days", type=float, required=True)
    a.add_argument("--label", default="media")
    a.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("size")
    s.add_argument("--dir", required=True)
    s.add_argument("--max-gb", type=float, required=True)
    s.add_argument("--label", default="media")
    s.add_argument("--dry-run", action="store_true")
    t = sub.add_parser("trash-file")
    t.add_argument("path")
    t.add_argument("--reason", default="manual")
    t.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("protected")
    p.add_argument("--json", action="store_true")
    q = sub.add_parser("prune-queue")
    q.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "age":
        res = run_age(args.dir, args.days, args.label, args.dry_run)
        return 1 if res["failed"] else 0
    if args.cmd == "size":
        res = run_size(args.dir, args.max_gb, args.label, args.dry_run)
        return 1 if res["failed"] else 0
    if args.cmd == "trash-file":
        return trash_file(args.path, args.reason, args.dry_run)
    if args.cmd == "protected":
        idx = protected_index()
        if args.json:
            print(json.dumps({k: sorted(v) if isinstance(v, set) else v for k, v in idx.items()}, indent=2))
        else:
            print(f"{idx['entries']} active queue entries protect {len(idx['clips'])} clip names "
                  f"and {len(idx['sources'])} source recordings")
            for k in sorted(idx["clips"]):
                print("  clip:  ", k)
            for k in sorted(idx["sources"]):
                print("  source:", k)
        return 0
    if args.cmd == "prune-queue":
        rep = prune_queues(dry_run=args.dry_run)
        print(json.dumps(rep, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
