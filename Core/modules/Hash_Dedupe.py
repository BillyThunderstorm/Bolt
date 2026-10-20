#!/usr/bin/env python3
"""
Hash_Dedupe.py — SHA256 duplicate finder for Bolt's media (READY)
================================================================
``bolt clip-dedupe`` status / list / run. Engine: ``scripts/clip_deduplicator.py``.

Scans media/clips, the recordings folder (config ``recordings_folder``,
default media/Recordings), media/vertical_clips, media/output and media/covers
(or ``--scan DIR``), hashes every video/image/audio file (case-insensitive
extensions incl. ``.MOV``; AppleDouble ``._`` files, hidden files and
symlinks skipped) and reports byte-identical groups with sizes and
reclaimable space. Incremental: unchanged files (same size + mtime) reuse the
cached hash in ``Data/media_hash_db.json`` (atomic write, Finder tags kept).

Read-only on media — never deletes or moves anything.

Soft-fail prefix: ``Hash dedupe unavailable:``.
Distinct from READY pipeline ``Core/modules/Clip_Deduplicator.py`` (pHash
during process_recording → ``Data/seen_clips.json``).

Public API:
  status() / list_items() / try_run() / print_status() / main()
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Hash dedupe unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_ENGINE = _REPO / "scripts" / "clip_deduplicator.py"
_CORE = _REPO / "Core"
_PIPELINE = _CORE / "modules" / "Clip_Deduplicator.py"
_DATA = _REPO / "Data"
_HASH_DB = _DATA / "media_hash_db.json"
_SEEN = _DATA / "seen_clips.json"
_PATHS = _REPO / "scripts" / "_paths.py"

_engine_mod = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    return msg if msg.startswith(_SOFT) else f"{_SOFT} {msg}"


def _engine():
    """Import scripts/clip_deduplicator.py once (raises on failure)."""
    global _engine_mod
    if _engine_mod is not None:
        return _engine_mod
    if not _ENGINE.is_file():
        raise FileNotFoundError(f"engine missing ({_ENGINE})")
    scripts = str(_ENGINE.parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    cwd = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location("clip_deduplicator", _ENGINE)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    finally:
        try:
            os.chdir(cwd)  # _paths chdirs to the repo; don't leak that
        except OSError:
            pass
    _engine_mod = mod
    return mod


def _local_time(iso: str) -> str:
    try:
        dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%d %b %Y %I:%M %p %Z").lstrip("0")
    except Exception:
        return iso or "never"


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness for the SHA256 duplicate finder."""
    out: Dict[str, Any] = {
        "checked_at": _utc_now(),
        "ready": False,
        "partial": False,
        "readiness": "READY",
        "soft_fail_prefix": _SOFT,
        "engine_path": str(_ENGINE),
        "engine_present": _ENGINE.is_file(),
        "paths_helper_present": _PATHS.is_file(),
        "data_present": _DATA.is_dir(),
        "hash_db_path": str(_HASH_DB),
        "hash_db_present": _HASH_DB.is_file(),
        "pipeline_module": str(_PIPELINE),
        "pipeline_present": _PIPELINE.is_file(),
        "pipeline_seen_file": str(_SEEN),
        "cli": "bolt clip-dedupe",
        "prefer_pipeline": "Clip_Deduplicator (process_recording / Data/seen_clips.json)",
        "note": (
            "SHA256 scan of media/clips, recordings, vertical_clips, output, covers → "
            "duplicate groups + reclaimable space; incremental cache "
            "Data/media_hash_db.json. Read-only on media. Distinct from READY "
            "pipeline Clip_Deduplicator pHash (Data/seen_clips.json)."
        ),
        "is_stranger_ready": True,
        "probe": bool(probe),
        "scan_dirs": [],
        "media_files": 0,
        "media_bytes": 0,
        "cached_files": 0,
        "last_run": {},
        "error": "",
        "hint": "",
    }
    try:
        if not out["engine_present"]:
            out["error"] = _soft(f"engine missing ({_ENGINE})")
        elif not out["paths_helper_present"]:
            out["error"] = _soft("scripts/_paths.py missing")
        elif not out["data_present"]:
            out["error"] = _soft("Data/ missing — run from the Bolt repo (bolt setup)")
        elif not os.access(_DATA, os.W_OK):
            out["error"] = _soft("Data/ is not writable (hash cache can't be saved)")
        if out["error"]:
            out["hint"] = out["error"]
            return out

        eng = _engine()
        dirs = eng.default_scan_dirs()
        rows = []
        total = 0
        total_bytes = 0
        for d in dirs:
            present = d.is_dir()
            n = b = 0
            if present:
                for p in eng.iter_media(d):
                    n += 1
                    try:
                        b += p.stat().st_size
                    except OSError:
                        pass
            rows.append({"dir": eng._rel(d, _REPO), "present": present, "files": n, "bytes": b})
            total += n
            total_bytes += b
        out["scan_dirs"] = rows
        out["media_files"] = total
        out["media_bytes"] = total_bytes
        db = eng.load_hash_db(_HASH_DB)
        out["cached_files"] = len(db.get("files", {}))
        lr = db.get("last_run") or {}
        out["last_run"] = {
            k: lr.get(k)
            for k in (
                "ran_at", "files_scanned", "hashed", "reused", "duplicate_groups",
                "duplicate_files", "reclaimable_bytes", "elapsed_s",
            )
            if k in lr
        }
        if not any(r["present"] for r in rows):
            out["error"] = _soft(
                "no media folders found (media/clips, media/Recordings, media/vertical_clips, "
                "media/output, media/covers) — run bolt recordings or bolt wrap first, "
                "or bolt clip-dedupe run --scan DIR"
            )
            out["hint"] = out["error"]
            return out
        out["ready"] = True
        out["hint"] = "ok — run: bolt clip-dedupe run [--dry-run] [--scan DIR]"
        if probe:
            out["probe_engine_import"] = True
        return out
    except Exception as exc:
        out["ready"] = False
        out["error"] = _soft(f"status failed ({type(exc).__name__}: {exc})")
        out["hint"] = out["error"]
        return out


def list_items(*, as_json: bool = False) -> int:
    """Checklist of hash-dedupe gates + per-folder counts."""
    try:
        info = status()
        rows = [
            ("engine scripts/clip_deduplicator.py", bool(info.get("engine_present"))),
            ("scripts/_paths.py", bool(info.get("paths_helper_present"))),
            ("Data/ writable", bool(info.get("data_present")) and not info.get("error", "").endswith("writable (hash cache can't be saved)")),
        ]
        for r in info.get("scan_dirs") or []:
            rows.append((f"{r['dir']} ({r['files']} media files)" if r["present"] else f"{r['dir']} (missing — skipped)", r["present"]))
        rows.append((f"Data/media_hash_db.json cache ({info.get('cached_files', 0)} files)", True))
        rows.append(("read-only on media (never deletes/moves)", True))
        rows.append(("distinct from pipeline Clip_Deduplicator pHash (Data/seen_clips.json)", bool(info.get("pipeline_present"))))
        if as_json:
            print(json.dumps({
                "ok": True,
                "readiness": "READY" if info.get("ready") else "UNAVAILABLE",
                "items": [{"name": n, "ok": ok} for n, ok in rows],
                "media_files": info.get("media_files"),
                "hint": info.get("hint"),
                "error": info.get("error"),
            }, indent=2))
            return 0
        print("Hash dedupe (SHA256 duplicate finder)", flush=True)
        for name, ok in rows:
            print(f"  [{'OK' if ok else '--'}] {name}", flush=True)
        if info.get("hint"):
            print(f"  → {info['hint']}", flush=True)
        return 0
    except Exception as exc:
        msg = _soft(f"list failed ({exc})")
        print(json.dumps({"ok": False, "error": msg}, indent=2) if as_json else msg)
        return 0


def try_run(
    *,
    dry_run: bool = False,
    as_json: bool = False,
    extra: Optional[List[str]] = None,
) -> int:
    """Run the engine in-process (never raises, never hard-fails the CLI)."""
    try:
        info = status()
        has_scan = bool(extra and ("--scan" in extra or "--check" in extra or "--clear-db" in extra or "--clear" in extra))
        if not info.get("ready") and not (has_scan and info.get("engine_present") and info.get("data_present")):
            msg = info.get("error") or _soft("not ready")
            print(json.dumps({"ok": False, "error": msg}, indent=2) if as_json else msg)
            return 0
        argv: List[str] = []
        if dry_run:
            argv.append("--dry-run")
        if as_json:
            argv.append("--json")
        argv.extend(extra or [])
        eng = _engine()
        eng.DRY_RUN = False
        cwd = os.getcwd()
        try:
            rc = eng.main(argv)
        finally:
            try:
                os.chdir(cwd)
            except OSError:
                pass
        if rc not in (0, 1) and not as_json:
            print(_soft(f"engine exit {rc}"))
        return 0
    except Exception as exc:
        msg = _soft(f"run failed ({type(exc).__name__}: {exc})")
        print(json.dumps({"ok": False, "error": msg}, indent=2) if as_json else msg)
        return 0


def _hs(n: Any) -> str:
    try:
        return _engine().human_size(n or 0)
    except Exception:
        return f"{n} B"


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    try:
        info = status(probe=probe)
        if as_json:
            print(json.dumps(info, indent=2))
            return 0
        state = "READY" if info.get("ready") else "UNAVAILABLE"
        print(f"Hash dedupe (SHA256 duplicate finder) — {state}")
        for r in info.get("scan_dirs") or []:
            if r["present"]:
                print(f"  {r['dir']}: {r['files']} media files, {_hs(r['bytes'])}")
            else:
                print(f"  {r['dir']}: missing (skipped)")
        if info.get("scan_dirs"):
            print(f"  total: {info.get('media_files', 0)} media files, {_hs(info.get('media_bytes'))}")
        print(f"  hash cache: {info.get('hash_db_path')} ({info.get('cached_files', 0)} files cached)")
        lr = info.get("last_run") or {}
        if lr.get("ran_at"):
            print(
                f"  last run: {_local_time(lr['ran_at'])} — {lr.get('files_scanned', 0)} files, "
                f"{lr.get('duplicate_groups', 0)} duplicate group(s), reclaimable "
                f"{_hs(lr.get('reclaimable_bytes'))}, {lr.get('elapsed_s', 0)} s "
                f"(hashed {lr.get('hashed', 0)}, reused {lr.get('reused', 0)})"
            )
        else:
            print("  last run: never")
        print(f"  pipeline (distinct): {info.get('prefer_pipeline')}")
        if info.get("error"):
            print(f"  error: {info['error']}")
        if info.get("hint") and info.get("hint") != info.get("error"):
            print(f"  → {info['hint']}")
        return 0
    except Exception as exc:
        msg = _soft(f"status print failed ({exc})")
        print(json.dumps({"ready": False, "error": msg}, indent=2) if as_json else msg)
        return 0


_HELP = """bolt clip-dedupe — find byte-identical media (SHA256), read-only

  bolt clip-dedupe                         # status (default)
  bolt clip-dedupe status [--json]
  bolt clip-dedupe list [--json]
  bolt clip-dedupe run [--dry-run] [--json] [--scan DIR ...] [--rehash] [--limit N]
  bolt clip-dedupe run --check FILE        # is FILE a copy of something already scanned?
  bolt clip-dedupe run --clear-db          # delete the hash cache only (media untouched)

Default scan: media/clips, recordings folder, media/vertical_clips, media/output,
media/covers. Reports duplicate groups (keep + dup paths, sizes, reclaimable).
Never deletes or moves media. Incremental cache: Data/media_hash_db.json.
Soft-fail: "Hash dedupe unavailable:".
Distinct from READY pipeline Clip_Deduplicator (pHash, Data/seen_clips.json).
Aliases: clip_dedupe, hash-dedupe, dedupe-status, sha-dedupe.
"""


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(_HELP)
        return 0
    json_out = "--json" in args
    probe = "--probe" in args
    dry_run = "--dry-run" in args or "-n" in args

    extra: List[str] = []
    cleaned: List[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--scan", "--check", "--limit") and i + 1 < len(args):
            extra.extend([a, args[i + 1]])
            i += 2
            continue
        if a in ("--clear-db", "--clear", "--rehash"):
            extra.append(a)
        elif not a.startswith("-"):
            cleaned.append(a)
        i += 1

    if not cleaned:
        if extra:
            return try_run(dry_run=dry_run, as_json=json_out, extra=extra)
        return print_status(as_json=json_out, probe=probe)

    cmd = cleaned[0].lower()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "checklist"):
        return list_items(as_json=json_out)
    if cmd in ("run", "go", "exec", "scan", "dedupe", "dedup"):
        return try_run(dry_run=dry_run, as_json=json_out, extra=extra)
    print(_soft(f"unknown command {cleaned[0]!r} — try status|list|run"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
