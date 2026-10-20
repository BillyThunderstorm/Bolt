#!/usr/bin/env python3
"""
Video_Compress.py — shrink clips in media/clips (READY)
=======================================================
``bolt compress`` re-encodes finished clips in ``media/clips`` to a smaller
H.264 file and keeps it only when it is at least 10 % smaller and passes a
check (same length, still has video, still has audio if it had audio).

How it works:
  * Encoder: the working ffmpeg from FFmpeg_Bin (ffmpeg-full) with libx264
    CRF 22 "fast" — same look as HandBrake's "Fast 1080p30" but it keeps the
    clip's own frame rate (60 fps stays 60 fps) and never upscales. HandBrakeCLI
    is only used when no ffmpeg works and HandBrake itself actually starts
    (``BOLT_COMPRESS_ENGINE=handbrake`` forces it).
  * The encode is written to a hidden ``media/clips/.compress_tmp/`` folder so
    nothing else (watch, dedupe, ranking) sees a half-written mp4.
  * On success the original moves to ``media/clips/originals_backup/`` and the
    smaller file takes its exact name, modification time and Finder tags, so
    the queue, sidecars and age-based cleanups keep working.
  * Every clip is recorded once in ``Data/compress_ledger.json`` — clips that
    didn't shrink enough or failed (3 tries) are not re-encoded every 30 min.
  * ``bolt compress clean-backups`` deletes backups older than N days
    (default 7) — that's when the space is actually freed. Never automatic.
  * Cron (``scripts/compress_videos.sh`` every 30 min) calls ``run --cron``:
    quiet when there's nothing new, one lock so runs never overlap, and the
    log is trimmed when it passes 5 MB.

Soft-fail prefix: ``Compress unavailable:``.

Public API:
  status() / list_items() / try_run() / compress_clips() / clean_backups()
  print_status() / main()
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Compress unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "compress_videos.sh"
_CLIPS = _REPO / "media" / "clips"
_LEGACY_CLIPS = _REPO / "clips"
_LOG = _REPO / "logs" / "video_compression.log"
_LEDGER = _REPO / "Data" / "compress_ledger.json"
_OPTIMIZE = _REPO / "scripts" / "storage_optimization.sh"
_TAGS_XATTR = "com.apple.metadata:_kMDItemUserTags"

MIN_AGE_MIN = 5.0          # skip files still being written
MIN_SAVINGS_PCT = 10.0     # keep the encode only when it saves this much
MAX_FAILS = 3              # stop retrying a clip that keeps failing
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_KEEP_LINES = 2000
DURATION_TOLERANCE = 0.75  # seconds
CRF = 22


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _mb(n: float) -> str:
    return f"{n / (1024 * 1024):.1f} MB"


# ── paths / tools ──────────────────────────────────────────────────────────

def _clips_dir() -> Path:
    env = (os.environ.get("BOLT_COMPRESS_CLIPS_DIR") or os.environ.get("CLIPS_DIR") or "").strip()
    if env:
        return Path(env).expanduser()
    if _CLIPS.is_dir():
        return _CLIPS
    if _LEGACY_CLIPS.is_dir():
        return _LEGACY_CLIPS
    return _CLIPS


def _ledger_path() -> Path:
    env = (os.environ.get("BOLT_COMPRESS_LEDGER") or "").strip()
    return Path(env).expanduser() if env else _LEDGER


def _log_path() -> Path:
    env = (os.environ.get("BOLT_COMPRESS_LOG") or os.environ.get("LOG_FILE") or "").strip()
    return Path(env).expanduser() if env else _LOG


def _which(name: str) -> Optional[str]:
    path = shutil.which(name)
    if path:
        return path
    brew = Path("/opt/homebrew/bin") / name
    if brew.is_file() and os.access(brew, os.X_OK):
        return str(brew)
    return None


def _ffmpeg() -> Optional[str]:
    try:
        from modules.FFmpeg_Bin import working_ffmpeg  # type: ignore
    except Exception:
        try:
            sys.path.insert(0, str(_REPO / "Core"))
            from modules.FFmpeg_Bin import working_ffmpeg  # type: ignore
        except Exception:
            return None
    try:
        return working_ffmpeg()
    except Exception:
        return None


def _ffprobe() -> Optional[str]:
    try:
        from modules.FFmpeg_Bin import ffprobe_bin  # type: ignore
        path = ffprobe_bin()
    except Exception:
        path = _which("ffprobe")
    if not path:
        return None
    try:
        ok = subprocess.run([path, "-version"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        ok = False
    return path if ok else None


def _handbrake_state() -> Dict[str, Any]:
    """Is HandBrakeCLI installed, and does it actually start?"""
    path = (os.environ.get("HANDBRAKE_CLI") or "").strip() or _which("HandBrakeCLI")
    if not path:
        return {"path": None, "works": False, "problem": "not installed"}
    try:
        proc = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            return {"path": path, "works": True, "problem": ""}
        err = ((proc.stderr or "") + (proc.stdout or "")).strip()
        problem = "won't start"
        if "Library not loaded" in err:
            lib = err.split("Library not loaded:", 1)[1].split("\n", 1)[0].strip()
            problem = f"won't start — missing {Path(lib).name} (brew install libbluray, or ignore — ffmpeg is used)"
        return {"path": path, "works": False, "problem": problem}
    except Exception as exc:
        return {"path": path, "works": False, "problem": f"won't start ({exc})"}


def _engine() -> Dict[str, Any]:
    """Pick the encoder: ffmpeg first unless HandBrake is forced."""
    forced = (os.environ.get("BOLT_COMPRESS_ENGINE") or "").strip().lower()
    ff = _ffmpeg()
    hb = _handbrake_state()
    if forced == "handbrake" and hb["works"]:
        return {"name": "handbrake", "path": hb["path"], "ffmpeg": ff, "handbrake": hb}
    if ff:
        return {"name": "ffmpeg", "path": ff, "ffmpeg": ff, "handbrake": hb}
    if hb["works"]:
        return {"name": "handbrake", "path": hb["path"], "ffmpeg": None, "handbrake": hb}
    return {"name": None, "path": None, "ffmpeg": None, "handbrake": hb}


# ── ledger / log ───────────────────────────────────────────────────────────

def _load_ledger() -> Dict[str, Any]:
    path = _ledger_path()
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict) and isinstance(data.get("clips"), dict):
            return data
    except Exception:
        pass
    return {"version": 1, "clips": {}}


def _save_ledger(data: Dict[str, Any]) -> None:
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _utc_now()
    fd, tmp = tempfile.mkstemp(prefix=".compress_ledger.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _trim_log(path: Path) -> None:
    try:
        if path.is_file() and path.stat().st_size > LOG_MAX_BYTES:
            lines = path.read_text(errors="replace").splitlines()[-LOG_KEEP_LINES:]
            path.write_text(
                f"[{datetime.now():%Y-%m-%d %H:%M:%S}] (log trimmed to last {LOG_KEEP_LINES} lines)\n"
                + "\n".join(lines) + "\n"
            )
    except Exception:
        pass


class _Logger:
    def __init__(self, echo: bool) -> None:
        self.echo = echo
        self.path = _log_path()
        self.lines: List[str] = []

    def __call__(self, msg: str) -> None:
        line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
        self.lines.append(line)
        if self.echo:
            print(msg)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as fh:
                fh.write(line + "\n")
        except Exception:
            pass


# ── probing / encoding ─────────────────────────────────────────────────────

def _probe(path: Path) -> Optional[Dict[str, Any]]:
    probe = _ffprobe()
    if not probe:
        return None
    try:
        proc = subprocess.run(
            [probe, "-v", "error", "-show_entries",
             "format=duration,bit_rate:stream=codec_type,codec_name,width,height,avg_frame_rate",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout or "{}")
    except Exception:
        return None
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    try:
        duration = float((data.get("format") or {}).get("duration") or 0)
    except Exception:
        duration = 0.0
    return {
        "duration": duration,
        "has_video": video is not None,
        "has_audio": audio is not None,
        "width": int((video or {}).get("width") or 0),
        "height": int((video or {}).get("height") or 0),
        "video_codec": (video or {}).get("codec_name"),
        "audio_codec": (audio or {}).get("codec_name"),
    }


def _encode_cmd(engine: Dict[str, Any], src: Path, dst: Path, info: Dict[str, Any]) -> List[str]:
    if engine["name"] == "handbrake":
        return [engine["path"], "-i", str(src), "-o", str(dst),
                "--preset=Fast 1080p30", "--quality", str(CRF), "--vfr", "--optimize"]
    w, h = info.get("width") or 0, info.get("height") or 0
    cmd = [engine["path"], "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
           "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?",
           "-c:v", "libx264", "-preset", "fast", "-crf", str(CRF), "-pix_fmt", "yuv420p"]
    # Cap at 1080 on the short side (portrait-safe); never upscale.
    if w and h and min(w, h) > 1080:
        cmd += ["-vf", "scale=-2:1080" if w >= h else "scale=1080:-2"]
    if info.get("audio_codec") == "aac":
        cmd += ["-c:a", "copy"]
    else:
        cmd += ["-c:a", "aac", "-b:a", "160k"]
    cmd += ["-movflags", "+faststart", str(dst)]
    return cmd


def _copy_tags(src: Path, dst: Path) -> None:
    """Carry Finder colour tags across (macOS only; best effort)."""
    if platform.system() != "Darwin" or not Path("/usr/bin/xattr").exists():
        return
    try:
        proc = subprocess.run(["/usr/bin/xattr", "-px", _TAGS_XATTR, str(src)],
                              capture_output=True, text=True, timeout=10)
        if proc.returncode == 0 and proc.stdout.strip():
            subprocess.run(["/usr/bin/xattr", "-wx", _TAGS_XATTR, proc.stdout.strip(), str(dst)],
                           capture_output=True, timeout=10)
    except Exception:
        pass


def _candidates(clips: Path, ledger: Dict[str, Any], *, include_fresh: bool = False,
                only: Optional[str] = None) -> Dict[str, List[Any]]:
    now = time.time()
    backup = clips / "originals_backup"
    todo: List[Path] = []
    skipped: List[Dict[str, str]] = []
    entries = ledger.get("clips", {})
    for p in sorted(clips.glob("*.mp4")):
        if not p.is_file() or p.name.startswith("."):
            continue
        if only and p.name != only and p.stem != only:
            continue
        entry = entries.get(p.name) or {}
        st = p.stat()
        if (backup / p.name).is_file():
            skipped.append({"file": p.name, "reason": "already compressed (backup exists)"})
            continue
        result = entry.get("result")
        same_file = entry.get("size") == st.st_size
        if result == "compressed" and same_file:
            skipped.append({"file": p.name, "reason": "already compressed"})
            continue
        if result == "kept_original" and same_file:
            skipped.append({"file": p.name, "reason": f"already small ({entry.get('savings_pct', 0)}% possible)"})
            continue
        if result == "failed" and same_file and int(entry.get("fails", 0)) >= MAX_FAILS:
            skipped.append({"file": p.name, "reason": f"failed {entry.get('fails')} times — skipped"})
            continue
        if not include_fresh and (now - st.st_mtime) / 60.0 < MIN_AGE_MIN:
            skipped.append({"file": p.name, "reason": "less than 5 min old (may still be writing)"})
            continue
        todo.append(p)
    return {"todo": todo, "skipped": skipped}


def compress_clips(*, dry_run: bool = False, limit: Optional[int] = None,
                   min_savings: float = MIN_SAVINGS_PCT, only: Optional[str] = None,
                   include_fresh: bool = False, echo: bool = True) -> Dict[str, Any]:
    """Compress new clips. Returns a summary dict (never raises)."""
    log = _Logger(echo=echo)
    clips = _clips_dir()
    out: Dict[str, Any] = {"ok": True, "clips_dir": str(clips), "dry_run": dry_run,
                           "compressed": [], "kept": [], "failed": [], "skipped": [],
                           "saved_bytes": 0, "error": ""}
    if not clips.is_dir():
        out.update(ok=False, error=_soft(f"clips folder missing ({clips})"))
        return out
    engine = _engine()
    out["engine"] = engine["name"]
    if not engine["name"]:
        hb = engine["handbrake"]
        out.update(ok=False, error=_soft(
            "no working ffmpeg (brew install ffmpeg-full) and HandBrakeCLI "
            f"{hb.get('problem') or 'not installed'}"))
        return out
    if not _ffprobe():
        out.update(ok=False, error=_soft("no working ffprobe to check the result (brew install ffmpeg-full)"))
        return out

    ledger = _load_ledger()
    found = _candidates(clips, ledger, include_fresh=include_fresh, only=only)
    todo, out["skipped"] = found["todo"], found["skipped"]
    if limit is not None and limit >= 0:
        todo = todo[:limit]
    out["candidates"] = [p.name for p in todo]
    if dry_run or not todo:
        return out

    lock_path = clips / ".compress.lock"
    try:
        import fcntl
        lock_fh = open(lock_path, "w")
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock_fh.close()
            out.update(ok=True, error="", busy=True)
            if echo:
                print("Another compress run is still going — skipping this one.")
            return out
    except Exception:
        lock_fh = None

    tmp_dir = clips / ".compress_tmp"
    backup = clips / "originals_backup"
    try:
        tmp_dir.mkdir(exist_ok=True)
        backup.mkdir(exist_ok=True)
        log(f"Compress run: {len(todo)} clip(s) with {engine['name']} (clips={clips})")
        for src in todo:
            name = src.name
            st = src.stat()
            entry = ledger["clips"].get(name) or {}
            info = _probe(src)
            if not info or not info["has_video"] or info["duration"] <= 0:
                fails = int(entry.get("fails", 0)) + 1 if entry.get("size") == st.st_size else 1
                ledger["clips"][name] = {"result": "failed", "fails": fails, "size": st.st_size,
                                         "reason": "unreadable clip", "at": _utc_now()}
                out["failed"].append({"file": name, "reason": "unreadable clip"})
                log(f"  ✗ {name}: can't read this clip (try {fails}/{MAX_FAILS})")
                _save_ledger(ledger)
                continue
            tmp = tmp_dir / name
            if tmp.exists():
                tmp.unlink()
            cmd = _encode_cmd(engine, src, tmp, info)
            started = time.time()
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=max(600, int(info["duration"] * 20)))
                err = ((proc.stderr or "").strip().splitlines() or [""])[-1][:200]
                rc = proc.returncode
            except subprocess.TimeoutExpired:
                rc, err = -1, "timed out"
            new = _probe(tmp) if tmp.is_file() else None
            problem = ""
            if rc != 0 or not new:
                problem = f"encode failed ({err or rc})"
            elif not new["has_video"]:
                problem = "result has no video"
            elif info["has_audio"] and not new["has_audio"]:
                problem = "result lost its audio"
            elif abs(new["duration"] - info["duration"]) > DURATION_TOLERANCE:
                problem = f"length changed ({info['duration']:.1f}s → {new['duration']:.1f}s)"
            if problem:
                if tmp.exists():
                    tmp.unlink()
                fails = int(entry.get("fails", 0)) + 1 if entry.get("size") == st.st_size else 1
                ledger["clips"][name] = {"result": "failed", "fails": fails, "size": st.st_size,
                                         "reason": problem, "engine": engine["name"], "at": _utc_now()}
                out["failed"].append({"file": name, "reason": problem})
                log(f"  ✗ {name}: {problem} (try {fails}/{MAX_FAILS}) — original untouched")
                _save_ledger(ledger)
                continue
            new_size = tmp.stat().st_size
            savings = round((1 - new_size / st.st_size) * 100, 1) if st.st_size else 0.0
            secs = round(time.time() - started, 1)
            if savings < min_savings:
                tmp.unlink()
                ledger["clips"][name] = {"result": "kept_original", "size": st.st_size,
                                         "savings_pct": savings, "engine": engine["name"],
                                         "at": _utc_now()}
                out["kept"].append({"file": name, "savings_pct": savings})
                log(f"  = {name}: only {savings}% smaller — kept the original ({_mb(st.st_size)})")
                _save_ledger(ledger)
                continue
            # Swap: original → backup, encode → original name (same mtime + tags).
            _copy_tags(src, tmp)
            os.utime(tmp, (st.st_atime, st.st_mtime))
            dest_backup = backup / name
            shutil.move(str(src), str(dest_backup))
            try:
                os.replace(tmp, src)
            except Exception:
                shutil.move(str(dest_backup), str(src))  # put the original back
                raise
            ledger["clips"][name] = {"result": "compressed", "size": new_size,
                                     "original_size": st.st_size, "savings_pct": savings,
                                     "engine": engine["name"], "seconds": secs,
                                     "backup": str(dest_backup), "at": _utc_now()}
            out["compressed"].append({"file": name, "before": st.st_size, "after": new_size,
                                      "savings_pct": savings, "seconds": secs})
            out["saved_bytes"] += st.st_size - new_size
            log(f"  ✓ {name}: {_mb(st.st_size)} → {_mb(new_size)} ({savings}% smaller, {secs}s); "
                f"original in originals_backup/")
            _save_ledger(ledger)
        log(f"Done: {len(out['compressed'])} compressed, {len(out['kept'])} already small, "
            f"{len(out['failed'])} failed — {_mb(out['saved_bytes'])} saved once backups are cleaned")
    except Exception as exc:
        out.update(ok=False, error=_soft(f"run failed ({exc})"))
        log(out["error"])
    finally:
        try:
            if tmp_dir.is_dir() and not any(tmp_dir.iterdir()):
                tmp_dir.rmdir()
        except Exception:
            pass
        if lock_fh:
            try:
                lock_fh.close()
                lock_path.unlink()
            except Exception:
                pass
        _trim_log(log.path)
    return out


def clean_backups(*, older_than_days: float = 7.0, dry_run: bool = False) -> Dict[str, Any]:
    """Delete originals in originals_backup/ older than N days (frees the space)."""
    backup = _clips_dir() / "originals_backup"
    out: Dict[str, Any] = {"ok": True, "backup_dir": str(backup), "removed": [], "kept": 0,
                           "freed_bytes": 0, "dry_run": dry_run}
    if not backup.is_dir():
        return out
    cutoff = time.time() - older_than_days * 86400
    for p in sorted(backup.iterdir()):
        if not p.is_file() or p.name.startswith("."):
            continue
        # Age = when it was backed up (ctime moves with the rename), not the clip's own date.
        st = p.stat()
        backed_up = max(st.st_ctime, st.st_mtime)
        if backed_up > cutoff:
            out["kept"] += 1
            continue
        out["removed"].append(p.name)
        out["freed_bytes"] += st.st_size
        if not dry_run:
            try:
                p.unlink()
            except Exception:
                out["removed"].pop()
                out["freed_bytes"] -= st.st_size
    return out


# ── readiness / CLI ────────────────────────────────────────────────────────

def _dir_bytes(d: Path) -> int:
    try:
        return sum(p.stat().st_size for p in d.iterdir() if p.is_file())
    except Exception:
        return 0


def _crontab_mentions_compress() -> Optional[bool]:
    try:
        proc = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        if proc.returncode != 0:
            return None
        body = (proc.stdout or "").lower()
        return "compress" in body or "handbrake" in body
    except Exception:
        return None


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness for clip compression."""
    try:
        clips = _clips_dir()
        clips_ok = clips.is_dir()
        engine = _engine()
        hb = engine["handbrake"]
        ledger = _load_ledger()
        found = _candidates(clips, ledger) if clips_ok else {"todo": [], "skipped": []}
        backup = clips / "originals_backup"
        entries = ledger.get("clips", {}).values()
        done = [e for e in entries if e.get("result") == "compressed"]
        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": False,
            "readiness": "READY",
            "soft_fail_prefix": _SOFT,
            "engine": engine["name"],
            "ffmpeg_path": engine["ffmpeg"],
            "ffmpeg_present": bool(engine["ffmpeg"]),
            "handbrake_path": hb.get("path"),
            "handbrake_present": bool(hb.get("path")),
            "handbrake_works": bool(hb.get("works")),
            "handbrake_problem": hb.get("problem") or "",
            "script_path": str(_SCRIPT),
            "script_present": _SCRIPT.is_file(),
            "clips_dir": str(clips),
            "clips_present": clips_ok,
            "mp4_count": len(list(clips.glob("*.mp4"))) if clips_ok else 0,
            "waiting": len(found["todo"]),
            "compressed_total": len(done),
            "saved_total_bytes": sum(int(e.get("original_size", 0)) - int(e.get("size", 0)) for e in done),
            "backup_dir": str(backup),
            "backup_count": len([p for p in backup.iterdir() if p.is_file()]) if backup.is_dir() else 0,
            "backup_bytes": _dir_bytes(backup) if backup.is_dir() else 0,
            "ledger_path": str(_ledger_path()),
            "log_path": str(_log_path()),
            "crontab_mentions_compress": _crontab_mentions_compress(),
            "cli": "bolt compress",
            "probe": bool(probe),
            "error": "",
            "hint": "",
        }
        if not clips_ok:
            out["error"] = _soft(f"clips folder missing ({clips})")
        elif not engine["name"]:
            out["error"] = _soft("no working ffmpeg (brew install ffmpeg-full); "
                                 f"HandBrakeCLI {hb.get('problem') or 'not installed'}")
        elif not _ffprobe():
            out["error"] = _soft("no working ffprobe (brew install ffmpeg-full)")
        if out["error"]:
            out["hint"] = out["error"]
            return out
        out["ready"] = True
        hint = f"ok — {out['waiting']} clip(s) waiting; run: bolt compress run [--dry-run]"
        if out["backup_count"]:
            hint += (f"; {out['backup_count']} original(s) in backup ({_mb(out['backup_bytes'])}) — "
                     "bolt compress clean-backups frees it")
        out["hint"] = hint
        return out
    except Exception as exc:
        return {"checked_at": _utc_now(), "ready": False, "readiness": "READY",
                "soft_fail_prefix": _SOFT, "error": _soft(f"status failed ({exc})"),
                "hint": _soft(f"status failed ({exc})"), "cli": "bolt compress", "probe": bool(probe)}


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    info = status(probe=probe)
    if as_json:
        print(json.dumps(info, indent=2, default=str))
        return 0
    print("Clip compress (READY)")
    print(f"  ready: {info.get('ready')}")
    print(f"  encoder: {info.get('engine') or 'none'}"
          + (f" ({info.get('ffmpeg_path')})" if info.get('engine') == 'ffmpeg' else ""))
    hb = "works" if info.get("handbrake_works") else (info.get("handbrake_problem") or "not installed")
    print(f"  HandBrakeCLI: {hb} (optional — ffmpeg is used first)")
    print(f"  clips: {info.get('clips_dir')} ({info.get('mp4_count')} mp4, {info.get('waiting')} waiting)")
    print(f"  compressed so far: {info.get('compressed_total')} "
          f"(saved {_mb(info.get('saved_total_bytes') or 0)})")
    print(f"  backups: {info.get('backup_count')} ({_mb(info.get('backup_bytes') or 0)})")
    print(f"  cron every 30 min: {info.get('crontab_mentions_compress')}")
    if info.get("error"):
        print(f"  → {info['error']}")
    elif info.get("hint"):
        print(f"  → {info['hint']}")
    return 0


def list_items(*, as_json: bool = False) -> int:
    info = status()
    clips = Path(info.get("clips_dir") or _clips_dir())
    found = _candidates(clips, _load_ledger()) if clips.is_dir() else {"todo": [], "skipped": []}
    if as_json:
        print(json.dumps({"ok": True, "waiting": [p.name for p in found["todo"]],
                          "skipped": found["skipped"], "hint": info.get("hint"),
                          "error": info.get("error")}, indent=2))
        return 0
    print(f"Clips waiting to compress: {len(found['todo'])}")
    for p in found["todo"][:30]:
        print(f"  {p.name} ({_mb(p.stat().st_size)})")
    if found["skipped"]:
        print(f"Skipped: {len(found['skipped'])}")
        for s in found["skipped"][:30]:
            print(f"  {s['file']} — {s['reason']}")
    if info.get("error"):
        print(f"  → {info['error']}")
    return 0


def try_run(*, dry_run: bool = False, as_json: bool = False, limit: Optional[int] = None,
            min_savings: float = MIN_SAVINGS_PCT, only: Optional[str] = None,
            cron: bool = False) -> int:
    """CLI wrapper around compress_clips (never raises)."""
    if cron:
        _trim_log(_log_path())
    try:
        res = compress_clips(dry_run=dry_run, limit=limit, min_savings=min_savings,
                             only=only, echo=not (as_json or cron))
    except Exception as exc:
        res = {"ok": False, "error": _soft(f"run failed ({exc})")}
    if as_json:
        print(json.dumps(res, indent=2, default=str))
        return 0
    if cron:
        if res.get("error"):
            _Logger(echo=False)(res["error"])
        return 0
    if res.get("error"):
        print(res["error"], file=sys.stderr)
        return 0
    if dry_run:
        cands = res.get("candidates") or []
        print(f"Would compress {len(cands)} clip(s) in {res.get('clips_dir')} with {res.get('engine')}:")
        for c in cands[:30]:
            print(f"  {c}")
        for s in (res.get("skipped") or [])[:30]:
            print(f"  skip {s['file']} — {s['reason']}")
        return 0
    if not res.get("candidates"):
        print("Nothing new to compress.")
        if res.get("skipped"):
            print(f"  ({len(res['skipped'])} clip(s) skipped — bolt compress list shows why)")
        return 0
    print(f"  log: {_log_path()}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt compress — shrink clips in media/clips (READY)

  bolt compress                          # status (default)
  bolt compress status [--json]
  bolt compress list [--json]            # what's waiting / skipped and why
  bolt compress run [--dry-run] [--limit N] [--min-savings PCT] [--clip NAME] [--json]
  bolt compress clean-backups [--days N] [--dry-run]   # delete backed-up originals (default 7 days)

Keeps a smaller copy only when it's ≥10% smaller and the same length.
Originals go to media/clips/originals_backup/ until you clean them.
Encoder: ffmpeg-full (libx264 CRF 22, keeps frame rate); HandBrakeCLI only
if no ffmpeg works. Cron: scripts/compress_videos.sh every 30 min.
Soft-fail: "Compress unavailable:".
"""
        )
        return 0

    def _opt(flag: str) -> Optional[str]:
        if flag in args:
            i = args.index(flag)
            if i + 1 < len(args):
                val = args[i + 1]
                del args[i:i + 2]
                return val
            del args[i]
        return None

    limit_s, min_s, clip, days_s = _opt("--limit"), _opt("--min-savings"), _opt("--clip"), _opt("--days")
    json_out = "--json" in args
    probe = "--probe" in args
    dry_run = "--dry-run" in args or "-n" in args
    cron = "--cron" in args
    cleaned = [a for a in args if not a.startswith("-")]
    try:
        limit = int(limit_s) if limit_s is not None else None
        min_savings = float(min_s) if min_s is not None else MIN_SAVINGS_PCT
        days = float(days_s) if days_s is not None else 7.0
    except ValueError:
        print(_soft("--limit/--days/--min-savings need a number"), file=sys.stderr)
        return 0

    cmd = cleaned[0].lower() if cleaned else "status"
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "checklist"):
        return list_items(as_json=json_out)
    if cmd in ("run", "compress", "scan", "go"):
        return try_run(dry_run=dry_run, as_json=json_out, limit=limit,
                       min_savings=min_savings, only=clip, cron=cron)
    if cmd in ("clean-backups", "clean_backups", "clean", "purge"):
        res = clean_backups(older_than_days=days, dry_run=dry_run)
        if json_out:
            print(json.dumps(res, indent=2))
            return 0
        verb = "Would delete" if dry_run else "Deleted"
        print(f"{verb} {len(res['removed'])} backed-up original(s), {_mb(res['freed_bytes'])} "
              f"(older than {days:g} days); kept {res['kept']} newer.")
        return 0

    print(_soft(f"unknown command '{cmd}' — try status|list|run|clean-backups"), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
