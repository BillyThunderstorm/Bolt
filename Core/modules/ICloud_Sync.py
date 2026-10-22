#!/usr/bin/env python3
"""
ICloud_Sync.py — Bolt iCloud Drive multi-Mac sync (READY 22 Oct 2026)
=====================================================================
What it does: copies the Bolt project (code, docs, small data) from this Mac's
checkout into ``iCloud Drive/Bolt`` so the second Mac (Magneto) gets it through
iCloud. This is what ``scripts/move_to_icloud.sh`` was meant to do
(Docs/AI_Guide.md), rebuilt so it is safe to run unattended:

* Non-interactive. No ``read -p``, no osascript, short timeouts.
* Copy only. Never deletes anything, never moves the live repo.
* Never overwrites a file in iCloud that somebody changed. A file is only
  refreshed when the iCloud copy is still exactly what Bolt copied last time
  (tracked in ``logs/icloud_sync_state.json``); the old copy goes to the
  Trash first. Anything else that differs is skipped and reported as a conflict.
* Skips secrets (.env / .env.local, token / credential files), recordings and
  big media (media/, vod_samples/, clips/, video/audio files, any file over
  25 MB), .git, .venv, node_modules, caches, logs and Data/backups.
* Every copied file is logged to ``logs/icloud_sync.jsonl`` (+ one summary line).
* Refuses with a clear fix when iCloud Drive is missing / not signed in / low
  on space, or when a run would copy more than ``--max-mb`` (default 500 MB).

Soft-fail prefix: ``iCloud unavailable:``.

CLI (via ``bolt icloud``):
  status [--json] [--probe]
  list [--json]
  run [--dry-run|--apply] [--only PATH ...] [--max-mb N] [--json]
  run --script shared|setup   (legacy two-account helpers: shown only, never run)
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SOFT = "iCloud unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_MOVE = _REPO / "scripts" / "move_to_icloud.sh"
_SHARED = _REPO / "scripts" / "migrate_to_shared.sh"
_SETUP = _REPO / "scripts" / "setup_icloud.sh"
_GUIDE = _REPO / "Docs" / "AI_Guide.md"
_SCRIPTS = {
    "move": _MOVE,
    "shared": _SHARED,
    "setup": _SETUP,
}
_DEFAULT_SCRIPT = "move"
_LOG = _REPO / "logs" / "icloud_sync.jsonl"
_STATE = _REPO / "logs" / "icloud_sync_state.json"

DEFAULT_MAX_MB = 500
MAX_FILE_MB = 25
MIN_LOCAL_FREE_GB = 5
QUOTA_TIMEOUT_S = 8

# Folder names skipped wherever they appear.
SKIP_DIR_NAMES = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", ".cache", ".tox",
    ".tmp.driveupload", ".idea", "Bolt 2", ".Trash",
}
SKIP_DIR_GLOBS = [".venv-*", "*.egg-info"]
# Top-level (repo-relative) folders skipped: big media, local-only runtime stuff.
SKIP_TOP_PATHS = {
    "recordings", "media", "vod_samples", "clips", "vertical_clips",
    "logs", "Data/backups", "dist", "build",
}
SECRET_GLOBS = [
    ".env", ".env.*", "*.env", "*token*.json", "*token_cache*", "*credentials*.json",
    "client_secret*", "*.pem", "*.key", "*.p12", "*.keychain", "*cookies*",
    "id_rsa*", "id_ed25519*",
]
SECRET_ALLOW = {".env.example"}
MEDIA_EXT = {
    ".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm", ".flv", ".ts", ".mts",
    ".wav", ".aif", ".aiff", ".flac", ".mp3", ".m4a", ".aac", ".ogg",
    ".logicx", ".band",
}
JUNK_GLOBS = [".DS_Store", "*.pyc", "*.pyo", "*.log", "*.bak", "*.bak-*", "*.tmp",
              "*.swp", ".icloudsync-tmp-*", "*.icloud"]


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _local(iso: Any) -> str:
    """UTC ISO stamp → local time label (box/Mac clock zone)."""
    try:
        dt = datetime.strptime(str(iso), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        lt = dt.astimezone()
        return lt.strftime("%d %b %Y %I:%M %p ").lstrip("0") + (lt.tzname() or "")
    except Exception:
        return str(iso)


def _mb(n: int) -> str:
    return f"{n / 1048576:.1f} MB"


def _icloud_root() -> Path:
    return Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"


def _icloud_bolt(root: Optional[Path] = None) -> Path:
    return (root or _icloud_root()) / "Bolt"


def _path_under_icloud(path: Path, icloud: Path) -> bool:
    try:
        path.resolve().relative_to(icloud.resolve())
        return True
    except Exception:
        return False


def _dir_nonempty(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        next(path.iterdir())
        return True
    except Exception:
        return False


def _load_state() -> Dict[str, Any]:
    try:
        data = json.loads(_STATE.read_text())
        if isinstance(data, dict):
            data.setdefault("files", {})
            return data
    except Exception:
        pass
    return {"files": {}}


def _save_state(state: Dict[str, Any]) -> None:
    _STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
    os.replace(tmp, _STATE)


def _last_run() -> Optional[Dict[str, Any]]:
    """Last summary line of logs/icloud_sync.jsonl (cheap tail read)."""
    try:
        with open(_LOG, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 65536))
            lines = fh.read().decode("utf-8", "ignore").splitlines()
        for line in reversed(lines):
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("event") == "summary":
                return row
    except Exception:
        pass
    return None


# ── space / sign-in checks ──────────────────────────────────────────────────
def icloud_quota(timeout: int = QUOTA_TIMEOUT_S) -> Dict[str, Any]:
    """Ask macOS (brctl quota) how much iCloud space is left. Never prompts."""
    out: Dict[str, Any] = {"ok": False, "bytes_free": None, "detail": ""}
    if not shutil.which("brctl"):
        out["detail"] = "brctl not found (cannot check iCloud space)"
        return out
    try:
        proc = subprocess.run(["brctl", "quota"], capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL)
        text = (proc.stdout or "") + (proc.stderr or "")
        out["detail"] = text.strip()[:200]
        for tok in text.split():
            if tok.isdigit():
                out["bytes_free"] = int(tok)
                out["ok"] = True
                break
        if not out["ok"]:
            low = text.lower()
            if "not logged" in low or "no account" in low or "sign" in low:
                out["signed_out"] = True
    except subprocess.TimeoutExpired:
        out["detail"] = f"brctl quota timed out after {timeout}s"
    except Exception as exc:
        out["detail"] = f"brctl quota failed ({exc})"
    return out


def status(*, probe: bool = False) -> Dict[str, Any]:
    """iCloud sync readiness. Never raises. Fast unless probe=True."""
    try:
        is_darwin = platform.system() == "Darwin"
        icloud = _icloud_root()
        dest = _icloud_bolt(icloud)
        shared = Path("/Users/Shared/Bolt")
        repo_in_icloud = _path_under_icloud(_REPO, icloud) if icloud.is_dir() else False

        engines = {name: path.is_file() for name, path in _SCRIPTS.items()}
        icloud_present = icloud.is_dir()
        dest_present = dest.is_dir()
        dest_nonempty = _dir_nonempty(dest)
        last = _last_run()

        missing: List[str] = []
        if not is_darwin:
            missing.append("not macOS (Darwin)")
        if is_darwin and not icloud_present:
            missing.append(
                "iCloud Drive folder missing — fix: System Settings → [your name] → "
                "iCloud → iCloud Drive ON (sign in to iCloud first)"
            )
        if repo_in_icloud:
            missing.append("this checkout already lives inside iCloud Drive — nothing to copy")

        ready = bool(is_darwin and icloud_present and not repo_in_icloud)
        if ready:
            if last:
                hint = (f"last sync {_local(last.get('at'))}: copied {last.get('copied', 0)} files "
                        f"({_mb(int(last.get('copied_bytes') or 0))}) · bolt icloud run "
                        "(dry-run) then --apply")
            else:
                hint = ("no sync yet · bolt icloud run (dry-run report) then "
                        "bolt icloud run --apply")
            error = ""
        else:
            error = _soft("; ".join(missing[:3]) if missing else "not ready")
            hint = error

        out: Dict[str, Any] = {
            "checked_at": _iso(),
            "ready": ready,
            "partial": False,
            "readiness": "READY",
            "soft_fail_prefix": _SOFT,
            "cli": "bolt icloud",
            "is_stranger_ready": False,
            "is_william_specific": True,
            "darwin": is_darwin,
            "platform": platform.system(),
            "repo": str(_REPO),
            "repo_under_icloud": repo_in_icloud,
            "icloud_root": str(icloud),
            "icloud_present": icloud_present,
            "icloud_bolt": str(dest),
            "icloud_bolt_present": dest_present,
            "icloud_bolt_nonempty": dest_nonempty,
            "shared_bolt": str(shared),
            "shared_bolt_present": shared.is_dir(),
            "engine": "built-in safe copy (ICloud_Sync.sync)",
            "engines": {k: str(v) for k, v in _SCRIPTS.items()},
            "engines_present": engines,
            "log": str(_LOG),
            "last_run": last,
            "docs_guide": str(_GUIDE),
            "docs_guide_present": _GUIDE.is_file(),
            "missing": missing,
            "error": error,
            "hint": hint,
            "probe": bool(probe),
            "probe_ok": None,
            "probe_detail": "",
        }

        if probe:
            details: List[str] = []
            ok = ready
            if not is_darwin:
                details.append("not Darwin")
            elif not icloud_present:
                details.append("iCloud Drive missing")
            else:
                q = icloud_quota()
                out["icloud_quota"] = q
                if q.get("ok"):
                    details.append(f"iCloud signed in, {q['bytes_free'] / 1e9:.1f} GB free")
                else:
                    details.append(f"iCloud space unknown ({q.get('detail')})")
                    if q.get("signed_out"):
                        ok = False
                details.append("Bolt copy present" if dest_nonempty else "no Bolt copy yet")
                try:
                    free = shutil.disk_usage(str(Path.home())).free
                    details.append(f"Mac disk {free / 1e9:.0f} GB free")
                except Exception:
                    pass
            out["probe_ok"] = bool(ok)
            out["probe_detail"] = "; ".join(details)
            if not ok and not out.get("error"):
                out["error"] = _soft(out["probe_detail"])
                out["hint"] = out["error"]
        return out
    except Exception as exc:
        return {
            "checked_at": _iso(),
            "ready": False,
            "partial": False,
            "readiness": "READY",
            "soft_fail_prefix": _SOFT,
            "cli": "bolt icloud",
            "is_stranger_ready": False,
            "is_william_specific": True,
            "darwin": platform.system() == "Darwin",
            "platform": platform.system(),
            "error": _soft(f"status failed ({exc})"),
            "hint": _soft(f"status failed ({exc})"),
            "probe": bool(probe),
            "probe_ok": False,
        }


def list_items() -> List[Dict[str, Any]]:
    st = status(probe=False)
    last = st.get("last_run") or {}
    rows: List[Dict[str, Any]] = [
        {"id": "platform_darwin", "ok": bool(st.get("darwin")), "detail": st.get("platform") or ""},
        {"id": "icloud_drive", "ok": bool(st.get("icloud_present")), "detail": st.get("icloud_root") or ""},
        {"id": "icloud_bolt_copy", "ok": bool(st.get("icloud_bolt_nonempty")),
         "detail": f"{st.get('icloud_bolt')} nonempty={st.get('icloud_bolt_nonempty')}"},
        {"id": "repo_outside_icloud", "ok": not st.get("repo_under_icloud"),
         "detail": f"{st.get('repo')} (live repo stays put; only a copy goes to iCloud)"},
        {"id": "last_sync", "ok": bool(last),
         "detail": (f"{_local(last.get('at'))} copied {last.get('copied')} "
                    f"({_mb(int(last.get('copied_bytes') or 0))})") if last else "never"},
        {"id": "log", "ok": True, "detail": str(_LOG)},
        {"id": "skips", "ok": True,
         "detail": "secrets (.env*, tokens, credentials), recordings/media/clips, video+audio, "
                   f">{MAX_FILE_MB} MB files, .git, .venv, node_modules, caches, logs, Data/backups"},
        {"id": "move_to_icloud.sh", "ok": bool((st.get("engines_present") or {}).get("move")),
         "detail": "thin wrapper → bolt icloud run"},
        {"id": "migrate_to_shared.sh / setup_icloud.sh (legacy)", "ok": True,
         "detail": "two-account helpers; shown only, never run by Bolt (they rm -rf)"},
    ]
    if st.get("error"):
        rows.append({"id": "error", "ok": False, "detail": st["error"]})
    return rows


# ── planning ────────────────────────────────────────────────────────────────
def _skip_reason(rel: str, name: str, is_dir: bool) -> Optional[str]:
    if is_dir:
        if name in SKIP_DIR_NAMES or any(fnmatch.fnmatch(name, g) for g in SKIP_DIR_GLOBS):
            return "excluded folder"
        if rel in SKIP_TOP_PATHS:
            if rel in ("recordings", "media", "vod_samples", "clips", "vertical_clips"):
                return "media"
            return "excluded folder"
        return None
    if name not in SECRET_ALLOW and any(fnmatch.fnmatch(name.lower(), g) for g in SECRET_GLOBS):
        return "secret"
    if any(fnmatch.fnmatch(name, g) for g in JUNK_GLOBS):
        return "junk"
    if Path(name).suffix.lower() in MEDIA_EXT:
        return "media"
    return None


def _sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def plan(*, source: Optional[Path] = None, dest: Optional[Path] = None,
         only: Optional[List[str]] = None, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Work out what a sync would do. Read-only."""
    src = Path(source or _REPO)
    dst = Path(dest or _icloud_bolt())
    state = state if state is not None else _load_state()
    known = state.get("files", {})
    only_n = [o.strip("/").rstrip("/") for o in (only or []) if o.strip("/")]

    copy: List[Dict[str, Any]] = []
    update: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []
    same = 0
    skipped: Dict[str, Dict[str, int]] = {}
    skipped_examples: Dict[str, List[str]] = {}

    def _skip(reason: str, rel: str, size: int) -> None:
        s = skipped.setdefault(reason, {"files": 0, "bytes": 0})
        s["files"] += 1
        s["bytes"] += size
        ex = skipped_examples.setdefault(reason, [])
        if len(ex) < 5:
            ex.append(rel)

    for root, dirs, files in os.walk(src, followlinks=False):
        rp = Path(root)
        rel_root = rp.relative_to(src).as_posix()
        rel_root = "" if rel_root == "." else rel_root
        keep = []
        for d in sorted(dirs):
            rel = f"{rel_root}/{d}" if rel_root else d
            if (rp / d).is_symlink():
                _skip("symlink", rel + "/", 0)
                continue
            if only_n and not any(rel == o or rel.startswith(o + "/") or o.startswith(rel + "/")
                                  for o in only_n):
                continue
            why = _skip_reason(rel, d, True)
            if why:
                _skip(why, rel + "/", 0)
                continue
            keep.append(d)
        dirs[:] = keep
        for f in sorted(files):
            rel = f"{rel_root}/{f}" if rel_root else f
            p = rp / f
            if only_n and not any(rel == o or rel.startswith(o + "/") for o in only_n):
                continue
            if p.is_symlink():
                _skip("symlink", rel, 0)
                continue
            try:
                size = p.stat().st_size
            except OSError:
                continue
            why = _skip_reason(rel, f, False)
            if not why and size > MAX_FILE_MB * 1048576:
                why = f"over {MAX_FILE_MB} MB"
            if why:
                _skip(why, rel, size)
                continue
            d = dst / rel
            row = {"path": rel, "bytes": size}
            if not d.exists():
                copy.append(row)
                continue
            try:
                dsize = d.stat().st_size
            except OSError:
                conflicts.append({**row, "why": "iCloud copy unreadable (maybe not downloaded)"})
                continue
            if dsize == size and _sha1(d) == _sha1(p):
                same += 1
                continue
            rec = known.get(rel)
            if rec and dsize == rec.get("bytes") and _sha1(d) == rec.get("sha1"):
                update.append(row)  # iCloud copy is untouched since Bolt put it there
            else:
                conflicts.append({**row, "why": "iCloud copy was changed (maybe on Magneto) — left alone"})

    by_top: Dict[str, Dict[str, int]] = {}
    for r in copy + update:
        top = r["path"].split("/", 1)[0] if "/" in r["path"] else "(top files)"
        t = by_top.setdefault(top, {"files": 0, "bytes": 0})
        t["files"] += 1
        t["bytes"] += r["bytes"]
    total = sum(r["bytes"] for r in copy + update)
    return {
        "source": str(src),
        "dest": str(dst),
        "only": only_n,
        "copy": copy,
        "update": update,
        "conflicts": conflicts,
        "unchanged": same,
        "skipped": skipped,
        "skipped_examples": skipped_examples,
        "by_folder": dict(sorted(by_top.items(), key=lambda kv: -kv[1]["bytes"])),
        "total_files": len(copy) + len(update),
        "total_bytes": total,
    }


def _report(p: Dict[str, Any], *, header: str) -> str:
    lines = [
        header,
        f"  from: {p['source']}",
        f"  to:   {p['dest']}",
    ]
    if p.get("only"):
        lines.append(f"  only: {', '.join(p['only'])}")
    lines.append(
        f"  new files: {len(p['copy'])} · refresh (unchanged Bolt copies): {len(p['update'])} · "
        f"already up to date: {p['unchanged']} · conflicts left alone: {len(p['conflicts'])}"
    )
    lines.append(f"  total to copy: {p['total_files']} files, {_mb(p['total_bytes'])}")
    if p["by_folder"]:
        lines.append("  by folder:")
        for k, v in list(p["by_folder"].items())[:15]:
            lines.append(f"    {k:<24} {v['files']:>6} files  {_mb(v['bytes']):>10}")
    if p["skipped"]:
        lines.append("  skipped (never copied):")
        for k, v in sorted(p["skipped"].items()):
            ex = ", ".join(p["skipped_examples"].get(k, [])[:3])
            lines.append(f"    {k:<16} {v['files']:>6} items  {_mb(v['bytes']):>10}  e.g. {ex}")
    for c in p["conflicts"][:10]:
        lines.append(f"  conflict: {c['path']} — {c['why']}")
    return "\n".join(lines) + "\n"


# ── trash / copy / log ──────────────────────────────────────────────────────
def _trash(path: Path) -> Tuple[bool, str]:
    """Send a file to the Trash. Never unlinks, never uses osascript."""
    test_dir = os.environ.get("BOLT_ICLOUD_TRASH_DIR")
    if test_dir:
        td = Path(test_dir)
        td.mkdir(parents=True, exist_ok=True)
        target = td / f"{path.name}.{int(time.time() * 1000)}"
        shutil.move(str(path), str(target))
        return True, "test-trash"
    if Path("/usr/bin/trash").exists():
        try:
            subprocess.run(["/usr/bin/trash", str(path)], capture_output=True, timeout=30,
                           stdin=subprocess.DEVNULL)
        except Exception:
            pass
        if not path.exists():
            return True, "trash"
    try:
        home_trash = Path.home() / ".Trash"
        home_trash.mkdir(exist_ok=True)
        target = home_trash / f"{path.name} {datetime.now().strftime('%H%M%S%f')}"
        shutil.move(str(path), str(target))
        return True, "~/.Trash"
    except Exception as exc:
        return False, f"error: {exc}"


def _log(rows: List[Dict[str, Any]]) -> None:
    try:
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG, "a") as fh:
            for r in rows:
                fh.write(json.dumps(r, default=str) + "\n")
    except Exception:
        pass


def _copy_one(src: Path, dst: Path) -> None:
    """Copy via a temp file in the same folder, then rename. Never overwrites."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.parent / f".icloudsync-tmp-{dst.name}"
    shutil.copy2(src, tmp)
    if dst.exists():
        _trash(tmp)
        raise FileExistsError(f"{dst} appeared during copy — left alone")
    os.replace(tmp, dst)


def sync(*, source: Optional[Path] = None, dest: Optional[Path] = None,
         only: Optional[List[str]] = None, max_mb: int = DEFAULT_MAX_MB,
         check_space: bool = True) -> Dict[str, Any]:
    """Real copy. Non-interactive; copy-only; logs every file."""
    src = Path(source or _REPO)
    dst = Path(dest or _icloud_bolt())
    out: Dict[str, Any] = {"ok": False, "error": "", "copied": [], "refreshed": [],
                           "failed": [], "dest": str(dst)}
    state = _load_state()
    p = plan(source=src, dest=dst, only=only, state=state)
    out["plan"] = p
    need = p["total_bytes"]

    if need > max_mb * 1048576:
        out["error"] = _soft(
            f"this run would copy {_mb(need)}, over the {max_mb} MB safety limit — "
            f"check `bolt icloud run` (dry-run), then narrow with --only or raise --max-mb"
        )
        return out
    if check_space and need:
        try:
            free = shutil.disk_usage(str(dst.parent if dst.parent.exists() else Path.home())).free
            if free < need + MIN_LOCAL_FREE_GB * 1e9:
                out["error"] = _soft(
                    f"Mac disk low ({free / 1e9:.1f} GB free; iCloud keeps a local copy) — "
                    f"free up space (bolt storage) and retry")
                return out
        except Exception:
            pass
        q = icloud_quota()
        out["icloud_quota"] = q
        if q.get("signed_out"):
            out["error"] = _soft("not signed in to iCloud — System Settings → sign in → "
                                 "iCloud → iCloud Drive ON, then retry")
            return out
        if q.get("ok") and q["bytes_free"] < need * 2 + 1e9:
            out["error"] = _soft(
                f"iCloud storage low ({q['bytes_free'] / 1e9:.1f} GB left, need ~{_mb(need)}) — "
                "free iCloud space or upgrade, then retry")
            return out

    started = _iso()
    log_rows: List[Dict[str, Any]] = []
    files_state = state.setdefault("files", {})
    for kind, rows in (("copy", p["copy"]), ("refresh", p["update"])):
        for r in rows:
            rel = r["path"]
            s, d = src / rel, dst / rel
            try:
                if kind == "refresh":
                    ok, how = _trash(d)
                    if not ok:
                        raise RuntimeError(f"could not move old iCloud copy to Trash ({how})")
                _copy_one(s, d)
                files_state[rel] = {"bytes": r["bytes"], "sha1": _sha1(d), "at": started}
                (out["copied"] if kind == "copy" else out["refreshed"]).append(rel)
                log_rows.append({"at": _iso(), "event": kind, "path": rel, "bytes": r["bytes"],
                                 "to": str(d)})
            except Exception as exc:
                out["failed"].append({"path": rel, "error": str(exc)})
                log_rows.append({"at": _iso(), "event": "failed", "path": rel, "error": str(exc)})
    copied_bytes = sum(r["bytes"] for r in p["copy"] + p["update"]
                       if r["path"] in set(out["copied"]) | set(out["refreshed"]))
    summary = {
        "at": _iso(), "event": "summary", "started": started, "source": str(src),
        "dest": str(dst), "only": p["only"], "copied": len(out["copied"]),
        "refreshed": len(out["refreshed"]), "copied_bytes": copied_bytes,
        "unchanged": p["unchanged"], "conflicts": [c["path"] for c in p["conflicts"]],
        "failed": len(out["failed"]),
        "skipped": {k: v["files"] for k, v in p["skipped"].items()},
    }
    log_rows.append(summary)
    _log(log_rows)
    try:
        _save_state(state)
    except Exception as exc:
        out["state_error"] = str(exc)
    out["summary"] = summary
    out["ok"] = not out["failed"]
    if out["failed"]:
        out["error"] = _soft(f"{len(out['failed'])} files failed — see {_LOG}")
    return out


def try_run(*, script: str = _DEFAULT_SCRIPT, dry_run: bool = True, apply: bool = False,
            only: Optional[List[str]] = None, max_mb: int = DEFAULT_MAX_MB) -> Dict[str, Any]:
    """Dry-run report by default; ``apply=True`` does the real safe copy."""
    out: Dict[str, Any] = {"ok": False, "error": "", "exit_code": 0, "report": "",
                           "dry_run": bool(dry_run or not apply), "apply": bool(apply and not dry_run),
                           "script": script}
    key = (script or _DEFAULT_SCRIPT).strip().lower()
    if key in ("move_to_icloud", "move-to-icloud", "icloud"):
        key = "move"
    elif key in ("migrate_to_shared", "migrate-to-shared", "shared-hop"):
        key = "shared"
    elif key in ("setup_icloud", "setup-icloud", "second-account"):
        key = "setup"
    if key not in _SCRIPTS:
        out["error"] = _soft(f"unknown script {script!r} — use move|shared|setup")
        return out
    out["script"] = key
    if key != "move":
        out["ok"] = True
        out["report"] = (
            f"[iCloud] {_SCRIPTS[key].name} is a legacy two-account helper (needs a second macOS "
            "user and deletes folders with rm -rf). Bolt never runs it. Use the default:\n"
            "  bolt icloud run            # dry-run report\n"
            "  bolt icloud run --apply    # safe copy into iCloud Drive/Bolt\n")
        return out

    st = status(probe=False)
    if not st.get("ready"):
        out["error"] = st.get("error") or _soft("not ready")
        return out

    if out["dry_run"]:
        p = plan(only=only)
        out["plan"] = {k: v for k, v in p.items() if k not in ("copy", "update")}
        out["ok"] = True
        rep = _report(p, header="[iCloud] dry-run — nothing copied. Plan:")
        if p["total_bytes"] > max_mb * 1048576:
            rep += (f"  NOTE: over the {max_mb} MB safety limit — --apply would refuse; "
                    "narrow with --only or raise --max-mb\n")
        rep += "  run `bolt icloud run --apply` to copy (copy-only; never deletes or overwrites)\n"
        out["report"] = rep
        return out

    res = sync(only=only, max_mb=max_mb)
    out["ok"] = bool(res.get("ok"))
    out["error"] = res.get("error", "")
    out["summary"] = res.get("summary")
    out["failed"] = res.get("failed")
    if res.get("summary"):
        s = res["summary"]
        out["report"] = (
            _report(res["plan"], header="[iCloud] synced:") +
            f"  copied {s['copied']} new + {s['refreshed']} refreshed files "
            f"({_mb(s['copied_bytes'])}); failed {s['failed']}\n"
            f"  log: {_LOG}\n"
            "  iCloud uploads in the background; Magneto gets it in Finder → iCloud Drive → Bolt\n")
    return out


def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, indent=2, default=str))
        return 0
    ready = "yes" if info.get("ready") else "no"
    print(f"icloud readiness: {info.get('readiness')}  ready={ready}")
    print(f"  darwin:   {info.get('darwin')} ({info.get('platform')})")
    print(f"  iCloud:   {info.get('icloud_root')}  present={info.get('icloud_present')}")
    print(f"  dest:     {info.get('icloud_bolt')}  nonempty={info.get('icloud_bolt_nonempty')}")
    print(f"  repo:     under_icloud={info.get('repo_under_icloud')}  path={info.get('repo')}")
    last = info.get("last_run")
    if last:
        print(f"  last run: {_local(last.get('at'))}  copied={last.get('copied')} "
              f"refreshed={last.get('refreshed')} ({_mb(int(last.get('copied_bytes') or 0))}) "
              f"conflicts={len(last.get('conflicts') or [])} failed={last.get('failed')}")
    else:
        print("  last run: never")
    if info.get("probe"):
        print(f"  probe_ok: {info.get('probe_ok')}  ({info.get('probe_detail')})")
    if info.get("error"):
        print(f"  {info['error']}")
    else:
        print(f"  hint: {info.get('hint')}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="bolt icloud",
        description="Copy Bolt into iCloud Drive/Bolt for the second Mac (READY; soft-fail).",
    )
    parser.add_argument("action", nargs="?", default="status", choices=["status", "list", "run"])
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--probe", action="store_true",
                        help="status: also check iCloud sign-in/space (brctl, 8s timeout)")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="run: report only (default when --apply is omitted)")
    parser.add_argument("--apply", action="store_true", help="run: really copy (copy-only)")
    parser.add_argument("--only", action="append", default=[], metavar="PATH",
                        help="run: limit to a repo-relative folder/file (repeatable)")
    parser.add_argument("--max-mb", type=int, default=DEFAULT_MAX_MB,
                        help=f"run: refuse to copy more than this (default {DEFAULT_MAX_MB})")
    parser.add_argument("--script", default=_DEFAULT_SCRIPT,
                        help="run: move (default) | shared | setup (legacy, shown only)")
    args = parser.parse_args(argv)

    if args.action == "status":
        return _print_status(status(probe=args.probe), args.json)

    if args.action == "list":
        rows = list_items()
        if args.json:
            print(json.dumps({"items": rows}, indent=2, default=str))
        else:
            print("iCloud sync pieces (READY — William multi-Mac; not stranger-ready)")
            for r in rows:
                print(f"  [{'OK' if r['ok'] else '--'}] {r['id']}: {r['detail']}")
        return 0

    result = try_run(script=args.script, dry_run=bool(args.dry_run or not args.apply),
                     apply=args.apply, only=args.only, max_mb=args.max_mb)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if result.get("report"):
            sys.stdout.write(result["report"])
        if result.get("error"):
            print(result["error"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
