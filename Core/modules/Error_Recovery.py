#!/usr/bin/env python3
"""
Error_Recovery.py — pipeline error log, report, retry + quarantine (READY)
==========================================================================
What it does now (20 Oct 2026, Shells):

* Every pipeline failure that goes through ``notifier.notify_error`` (the clip
  pipeline in ``bot.process_recording`` — used by ``bolt watch``,
  ``bolt recordings`` and live mode — plus other modules) is written to
  ``Data/pipeline_errors.jsonl`` with the stage, the recording it happened on
  and the error. A crash of the whole pipeline is logged too.
* ``bolt error-recovery run`` reads that log and shows what failed recently
  (default last 7 days): per stage (how often, latest error, what to try) and
  per recording (whether the file still opens; unreadable ones are suggested
  for quarantine).
* ``bolt error-recovery quarantine FILE`` moves a broken recording into
  ``Data/quarantine/`` (never overwrites; every move logged in
  ``Data/quarantine/_moves.jsonl``) and ``restore`` puts it back.
* ``with_retry`` keeps working for in-process callers.

Discord: ``notifier`` already posts each error to the webhooks, so this module
does NOT post again unless ``ERROR_RECOVERY_DISCORD=1``.

Soft-fail prefix: ``Error recovery unavailable:``.

CLI (via ``bolt error-recovery``):
  status [--json] [--probe]
  list [--json]
  run [--days N] [--json] [--no-probe]     (alias: summary, report)
  quarantine FILE [--reason TEXT] [--dry-run] [--json]
  restore [NAME ...|--all] [--dry-run] [--json]
  clear [--json]                           (archives the log, starts fresh)

Public API (in-process):
  with_retry, ErrorTracker, get_tracker, record_error, session_summary,
  set_context, current_context, load_errors, build_report,
  quarantine_file, restore_files
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

_SOFT = "Error recovery unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_QUARANTINE = _REPO / "Data" / "quarantine"
_ERROR_LOG = _REPO / "Data" / "pipeline_errors.jsonl"
_ARCHIVE = _REPO / "Data" / "pipeline_errors.archive.jsonl"
# Legacy CWD-relative path (pre-promotion callers)
_LEGACY_QUARANTINE = Path("quarantine")

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "") or ""
MAX_ERRORS_BEFORE_ALERT = int(os.getenv("MAX_ERRORS_BEFORE_ALERT", "3") or "3")
DEFAULT_DAYS = 7
_LOG_MAX_BYTES = 5 * 1024 * 1024
_VIDEO_EXT = {".mp4", ".mov", ".mkv", ".flv", ".ts", ".m4v", ".webm", ".avi"}

# What to try, by stage keyword (first match wins — keep 'subtitle' above
# 'title'). Plain words for William.
_STAGE_HINTS = [
    ("unreadable", "The recording file won't open (corrupt, cut short, or still "
     "copying). Quarantine it (command below) or re-export it; nothing else to fix."),
    ("highlight", "Highlights couldn't be read from the recording. If the file "
     "won't open (see below) quarantine it; otherwise check ffmpeg with `bolt doctor`, "
     "then `bolt recordings latest --force`."),
    ("clip_generator", "Cutting clips failed. Check free disk space and ffmpeg "
     "(`bolt doctor`), then `bolt recordings latest --force`."),
    ("clip generator", "Cutting clips failed. Check free disk space and ffmpeg "
     "(`bolt doctor`), then `bolt recordings latest --force`."),
    ("subtitle", "Captions failed. Clips still work; check `bolt wrap status` "
     "for the Whisper backend."),
    ("title", "Title writing failed (AI down?). Clips still get a plain title; "
     "check `bolt doctor`."),
    ("video_intelligence", "On-screen stats (OCR) failed. Optional — titles "
     "continue without stats."),
    ("ranker", "Ranking failed, so clips were kept in cut order. Usually harmless."),
    ("tiktok", "Making the vertical copy or queueing failed. Rebuild with "
     "`bolt reprocess run`."),
    ("queue", "Queueing failed. Rebuild with `bolt reprocess run`."),
    ("process_recording", "The whole pipeline crashed on this recording. "
     "Retry with `bolt recordings latest --force`; if it keeps crashing, quarantine it."),
]

_context: Dict[str, str] = {"recording": ""}


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _local_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _redact_webhook(url: str) -> str:
    """Show presence without leaking the full webhook URL."""
    raw = (url or "").strip()
    if not raw:
        return ""
    if len(raw) <= 16:
        return "***"
    return f"{raw[:12]}…{raw[-4:]}"


def _truthy(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def quarantine_dir() -> Path:
    """Repo-rooted quarantine directory (Data/quarantine/)."""
    return _QUARANTINE


def error_log_path() -> Path:
    return _ERROR_LOG


def _moves_log() -> Path:
    return _QUARANTINE / "_moves.jsonl"


def _quarantine_files(root: Optional[Path] = None) -> List[Path]:
    root = root or _QUARANTINE
    if not root.is_dir():
        return []
    try:
        return [
            p for p in root.iterdir()
            if p.is_file() and not p.name.startswith(("_", "."))
        ]
    except Exception:
        return []


def _quarantine_count(path: Optional[Path] = None) -> int:
    return len(_quarantine_files(path))


def _list_quarantine_files(limit: int = 50) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        files = sorted(_quarantine_files(), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return []
    for p in files[:limit]:
        try:
            st = p.stat()
            rows.append({
                "name": p.name,
                "path": str(p),
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="seconds"),
            })
        except Exception:
            rows.append({"name": p.name, "path": str(p), "size": None, "mtime": None})
    return rows


# ── context (which recording the pipeline is on) ─────────────────────────────

def set_context(recording: Optional[str]) -> None:
    """Tell the tracker which recording is being processed ('' / None clears)."""
    _context["recording"] = str(recording or "")


def current_context() -> str:
    return _context.get("recording", "")


# ── retry ────────────────────────────────────────────────────────────────────

def with_retry(
    fn: Callable[..., Any],
    *args: Any,
    retries: int = 3,
    label: str = "",
    reraise: bool = False,
    delay: float = 5.0,
    **kwargs: Any,
) -> Any:
    last_exc: Optional[BaseException] = None
    wait = float(delay)
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            print(
                f"[ErrorRecovery] {label or getattr(fn, '__name__', 'fn')} "
                f"attempt {attempt}/{retries} failed: {exc}"
            )
            if attempt < retries and wait > 0:
                time.sleep(wait)
                wait *= 3
    if reraise and last_exc:
        raise last_exc
    return None


# ── persistent error log ─────────────────────────────────────────────────────

def _trim_log(path: Path) -> None:
    """Keep the log bounded: past 5 MB keep the newest 2000 lines."""
    try:
        if path.stat().st_size <= _LOG_MAX_BYTES:
            return
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-2000:]
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        pass


def _append_log(entry: Dict[str, Any], path: Optional[Path] = None) -> bool:
    path = path or _ERROR_LOG
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _trim_log(path)
        return True
    except Exception as exc:
        print(f"[ErrorTracker] could not write {path}: {exc}")
        return False


def _parse_time(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()  # naive = local
    return dt


def load_errors(days: Optional[float] = DEFAULT_DAYS, path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Entries from the error log, newest last. days=None → everything."""
    path = path or _ERROR_LOG
    if not path.is_file():
        return []
    cutoff = None
    if days is not None:
        cutoff = datetime.now().astimezone() - timedelta(days=float(days))
    out: List[Dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if not isinstance(row, dict):
                    continue
                dt = _parse_time(row.get("time"))
                if cutoff is not None and (dt is None or dt < cutoff):
                    continue
                out.append(row)
    except Exception:
        return out
    return out


class ErrorTracker:
    def __init__(self, log_path: Optional[Path] = None, persist: bool = True) -> None:
        self._errors: List[Dict[str, Any]] = []
        self._counts: Dict[str, int] = {}
        self._alerted: set = set()
        self._log_path = log_path
        self._persist = persist

    def record(self, stage: str, context: str, error: Any, *, quiet: bool = False) -> Dict[str, Any]:
        recording = str(context or "")
        entry = {
            "time": _local_iso(),
            "stage": str(stage or "unknown"),
            "recording": recording,
            "recording_name": Path(recording).name if recording else "",
            "error": str(error)[:2000],
            "error_type": type(error).__name__ if isinstance(error, BaseException) else "",
        }
        self._errors.append(entry)
        self._counts[entry["stage"]] = self._counts.get(entry["stage"], 0) + 1
        if self._persist:
            _append_log(entry, self._log_path)
        if not quiet:
            print(f"[ErrorTracker] {entry['stage']}: {error}")
        if (
            self._counts[entry["stage"]] >= MAX_ERRORS_BEFORE_ALERT
            and entry["stage"] not in self._alerted
        ):
            self._alerted.add(entry["stage"])
            print(
                f"[ErrorTracker] {entry['stage']} failed {self._counts[entry['stage']]}x "
                "this session — see `bolt error-recovery run`."
            )
            self._alert_discord(entry["stage"], error)
        return entry

    def quarantine(self, file_path: str, reason: str = "") -> None:
        res = quarantine_file(file_path, reason=reason)
        if res.get("ok"):
            print(f"[ErrorTracker] Quarantined: {file_path} → {res.get('dest')} ({reason})")
        else:
            print(f"[ErrorTracker] Could not quarantine {file_path}: {res.get('error')}")

    def send_summary(self) -> None:
        if not self._errors:
            print("[ErrorTracker] No errors this session.")
            return
        print(f"[ErrorTracker] Session errors: {len(self._errors)}")
        for stage, count in sorted(self._counts.items(), key=lambda x: -x[1]):
            print(f"  {stage}: {count}x")

    def snapshot(self) -> Dict[str, Any]:
        return {
            "error_count": len(self._errors),
            "counts": dict(self._counts),
            "alerted_stages": sorted(self._alerted),
            "errors": list(self._errors),
        }

    def _alert_discord(self, stage: str, error: Any) -> None:
        # notifier.notify_error already posts every error to the webhooks.
        if not (DISCORD_WEBHOOK and _truthy(os.getenv("ERROR_RECOVERY_DISCORD"))):
            return
        body = {
            "content": (
                f"⚠️ **Bolt error alert** | {stage} failed "
                f"{self._counts.get(stage, 0)}x\nLatest: {error}"
            )
        }
        try:
            req = urllib.request.Request(
                DISCORD_WEBHOOK,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass


_tracker: Optional[ErrorTracker] = None


def get_tracker() -> ErrorTracker:
    global _tracker
    if _tracker is None:
        _tracker = ErrorTracker()
    return _tracker


def record_error(stage: str, context: str, error: Any, *, quiet: bool = False) -> Optional[Dict[str, Any]]:
    """Never raises."""
    try:
        return get_tracker().record(stage, context or current_context(), error, quiet=quiet)
    except Exception:
        return None


def session_summary() -> None:
    get_tracker().send_summary()


# ── readability probe ────────────────────────────────────────────────────────

def _ffprobe() -> Optional[str]:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from FFmpeg_Bin import ffprobe_bin  # type: ignore

        return ffprobe_bin()
    except Exception:
        return shutil.which("ffprobe")


def probe_readable(path: str) -> Dict[str, Any]:
    """{'exists', 'readable', 'duration', 'detail'} — readable = has a video
    stream and a duration > 0 according to ffprobe. Never raises."""
    p = Path(path)
    out: Dict[str, Any] = {"exists": p.is_file(), "readable": None, "duration": None, "detail": ""}
    if not out["exists"]:
        out["detail"] = "file is gone (moved, deleted or quarantined)"
        return out
    probe = _ffprobe()
    if not probe:
        out["detail"] = "no ffprobe to check with"
        return out
    try:
        res = subprocess.run(
            [probe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_type:format=duration",
             "-of", "json", str(p)],
            capture_output=True, text=True, timeout=20,
        )
    except Exception as exc:
        out["detail"] = f"ffprobe failed: {exc}"
        return out
    try:
        data = json.loads(res.stdout or "{}")
    except Exception:
        data = {}
    has_video = any(s.get("codec_type") == "video" for s in data.get("streams") or [])
    try:
        duration = float((data.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    out["duration"] = round(duration, 2) if duration else None
    if res.returncode == 0 and has_video and duration > 0:
        out["readable"] = True
        out["detail"] = f"opens fine ({duration:.0f} s)"
    else:
        out["readable"] = False
        err = (res.stderr or "").strip().splitlines()
        last = err[-1].replace(f"{p}: ", "").strip() if err else ""
        out["detail"] = "won't open: " + (last[:160] or "no video stream / no duration")
    return out


# ── report ───────────────────────────────────────────────────────────────────

def stage_hint(stage: str) -> str:
    low = (stage or "").lower()
    for key, hint in _STAGE_HINTS:
        if key in low:
            return hint
    return "Check `bolt doctor`; retry with `bolt recordings latest --force`."


def _stage_key(stage: str) -> str:
    # "Subtitle_Generator (clip01.mp4)" → "Subtitle_Generator"
    return (stage or "unknown").split(" (")[0].strip() or "unknown"


def build_report(days: Optional[float] = DEFAULT_DAYS, *, probe: bool = True,
                 path: Optional[Path] = None) -> Dict[str, Any]:
    rows = load_errors(days, path)
    stages: Dict[str, Dict[str, Any]] = {}
    recs: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        key = _stage_key(r.get("stage", ""))
        s = stages.setdefault(key, {"stage": key, "count": 0, "last_time": "", "last_error": "",
                                    "recordings": set(), "hint": stage_hint(key)})
        s["count"] += 1
        s["last_time"] = r.get("time", "")
        s["last_error"] = r.get("error", "")
        rec = r.get("recording") or ""
        if rec:
            s["recordings"].add(rec)
            g = recs.setdefault(rec, {"recording": rec, "name": Path(rec).name, "count": 0,
                                      "stages": [], "last_time": "", "last_error": ""})
            g["count"] += 1
            if key not in g["stages"]:
                g["stages"].append(key)
            g["last_time"] = r.get("time", "")
            g["last_error"] = r.get("error", "")
    stage_list = sorted(stages.values(), key=lambda s: (-s["count"], s["stage"]))
    for s in stage_list:
        s["recordings"] = len(s["recordings"])
    rec_list = sorted(recs.values(), key=lambda g: g["last_time"], reverse=True)
    for g in rec_list:
        is_video = Path(g["recording"]).suffix.lower() in _VIDEO_EXT
        if probe and is_video:
            pr = probe_readable(g["recording"])
            g.update({"exists": pr["exists"], "readable": pr["readable"], "file_check": pr["detail"]})
        else:
            g.update({"exists": Path(g["recording"]).exists(), "readable": None, "file_check": ""})
        if g.get("readable") is False:
            g["suggest"] = f"bolt error-recovery quarantine \"{g['recording']}\""
    return {
        "days": days,
        "log": str(path or _ERROR_LOG),
        "total": len(rows),
        "stages": stage_list,
        "recordings": rec_list,
        "unreadable": [g["recording"] for g in rec_list if g.get("readable") is False],
        "quarantine_count": _quarantine_count(),
    }


# ── quarantine / restore ─────────────────────────────────────────────────────

def _read_moves() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    path = _moves_log()
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                out.append(row)
        except Exception:
            continue
    return out


def quarantine_file(file_path: str, *, reason: str = "", dry_run: bool = False) -> Dict[str, Any]:
    """Move one file into Data/quarantine/. Never overwrites. Never raises."""
    out: Dict[str, Any] = {"ok": False, "dry_run": dry_run, "source": "", "dest": "", "error": ""}
    try:
        src = Path(file_path).expanduser()
        if not src.is_absolute():
            src = (Path.cwd() / src)
        src = src.resolve()
        out["source"] = str(src)
        if not src.is_file():
            out["error"] = _soft(f"no such file: {src}")
            return out
        qdir = quarantine_dir().resolve()
        if qdir in src.parents:
            out["error"] = _soft(f"already in quarantine: {src.name}")
            return out
        dest = qdir / src.name
        out["dest"] = str(dest)
        if dest.exists():
            out["error"] = _soft(f"{dest.name} is already in quarantine — not overwriting (rename one first)")
            return out
        if dry_run:
            out["ok"] = True
            return out
        qdir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        _append_log({"time": _local_iso(), "action": "quarantine", "name": dest.name,
                     "original": str(src), "dest": str(dest), "reason": reason}, _moves_log())
        out["ok"] = True
        return out
    except Exception as exc:
        out["error"] = _soft(str(exc) or type(exc).__name__)
        return out


def restore_files(names: Iterable[str] = (), *, all_files: bool = False,
                  dry_run: bool = False) -> Dict[str, Any]:
    """Put quarantined files back where they came from. Never overwrites."""
    out: Dict[str, Any] = {"ok": True, "dry_run": dry_run, "restored": [], "skipped": [], "available": []}
    try:
        moves = _read_moves()
        last: Dict[str, Dict[str, Any]] = {}
        for m in moves:
            if m.get("action") == "quarantine":
                last[m.get("name", "")] = m
        present = {p.name: p for p in _quarantine_files()}
        out["available"] = sorted(present)
        wanted = sorted(present) if all_files else [Path(n).name for n in names]
        for name in wanted:
            q = present.get(name)
            if q is None:
                out["skipped"].append({"name": name, "why": "not in quarantine"})
                continue
            original = (last.get(name) or {}).get("original")
            if not original:
                out["skipped"].append({"name": name, "why": "no record of where it came from — move it by hand"})
                continue
            dest = Path(original)
            if dest.exists():
                out["skipped"].append({"name": name, "why": f"{dest} already exists — not overwriting"})
                continue
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(q), str(dest))
                _append_log({"time": _local_iso(), "action": "restore", "name": name,
                             "original": str(dest)}, _moves_log())
            out["restored"].append({"name": name, "to": str(dest)})
        out["ok"] = not out["skipped"] or bool(out["restored"])
        return out
    except Exception as exc:
        out["ok"] = False
        out["error"] = _soft(str(exc) or type(exc).__name__)
        return out


def clear_log() -> Dict[str, Any]:
    """Archive the current error log (append to pipeline_errors.archive.jsonl)."""
    out: Dict[str, Any] = {"ok": False, "archived": 0, "archive": str(_ARCHIVE), "error": ""}
    try:
        if not _ERROR_LOG.is_file():
            out["ok"] = True
            return out
        text = _ERROR_LOG.read_text(encoding="utf-8", errors="replace")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        with open(_ARCHIVE, "a", encoding="utf-8") as fh:
            for ln in lines:
                fh.write(ln + "\n")
        _ERROR_LOG.unlink()
        out["archived"] = len(lines)
        out["ok"] = True
        return out
    except Exception as exc:
        out["error"] = _soft(str(exc) or type(exc).__name__)
        return out


# ── status / list / run ──────────────────────────────────────────────────────

def status(*, probe: bool = False) -> Dict[str, Any]:
    """Never raises."""
    try:
        qdir = quarantine_dir()
        recent = load_errors(DEFAULT_DAYS)
        last = recent[-1] if recent else None
        api_ok = all(callable(f) for f in (with_retry, get_tracker, record_error,
                                           session_summary, build_report, quarantine_file))
        wired = False
        try:
            notifier_src = (Path(__file__).resolve().parent / "notifier.py").read_text(encoding="utf-8")
            wired = "record_error" in notifier_src
        except Exception:
            wired = False
        log_dir_ok = os.access(str(_ERROR_LOG.parent), os.W_OK)
        ready = api_ok and wired and log_dir_ok
        missing: List[str] = []
        if not wired:
            missing.append("notifier.notify_error does not log to Error_Recovery")
        if not log_dir_ok:
            missing.append(f"cannot write {_ERROR_LOG.parent}")
        info: Dict[str, Any] = {
            "checked_at": _iso(),
            "ready": ready,
            "partial": False,
            "readiness": "READY" if ready else "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "cli": "bolt error-recovery",
            "module": str(Path(__file__).resolve()),
            "module_present": Path(__file__).is_file(),
            "wired_into_pipeline": wired,
            "error_log": str(_ERROR_LOG),
            "error_log_present": _ERROR_LOG.is_file(),
            "errors_last_7_days": len(recent),
            "last_error": (
                f"{last.get('time', '')} · {_stage_key(last.get('stage', ''))} · "
                f"{last.get('recording_name') or '-'} · {str(last.get('error', ''))[:120]}"
                if last else ""
            ),
            "max_errors_before_alert": MAX_ERRORS_BEFORE_ALERT,
            "discord_webhook_present": bool(DISCORD_WEBHOOK.strip()),
            "discord_webhook_redacted": _redact_webhook(DISCORD_WEBHOOK),
            "discord_from_error_recovery": _truthy(os.getenv("ERROR_RECOVERY_DISCORD")),
            "quarantine_dir": str(qdir),
            "quarantine_exists": qdir.is_dir(),
            "quarantine_count": _quarantine_count(qdir),
            "legacy_cwd_quarantine_exists": _LEGACY_QUARANTINE.is_dir(),
            "api_ok": api_ok,
            "api_note": "with_retry + ErrorTracker + report + quarantine importable" if api_ok else "API check failed",
            "probe": bool(probe),
            "probe_ok": None,
            "error": "" if ready else _soft("; ".join(missing) or "not ready"),
            "hint": (
                "clip pipeline errors → Data/pipeline_errors.jsonl · `bolt error-recovery run` "
                "shows what failed + what to try · quarantine/restore broken recordings"
            ),
            "is_stranger_ready": True,
            "missing": missing,
        }
        if probe:
            try:
                info["probe_ok"] = with_retry(lambda: True, retries=1, label="status-probe", delay=0) is True
                info["probe_label"] = "with_retry(lambda: True)"
            except Exception as exc:
                info["probe_ok"] = False
                info["error"] = _soft(str(exc) or type(exc).__name__)
        return info
    except Exception as exc:
        return {
            "checked_at": _iso(), "ready": False, "partial": True, "readiness": "PARTIAL",
            "soft_fail_prefix": _SOFT, "cli": "bolt error-recovery",
            "error": _soft(str(exc) or type(exc).__name__), "hint": "import/status failed",
            "is_stranger_ready": False, "probe": bool(probe), "probe_ok": False,
            "quarantine_count": 0,
        }


def list_items() -> List[Dict[str, Any]]:
    st = status(probe=False)
    rows: List[Dict[str, Any]] = [
        {"id": "module", "ok": bool(st.get("module_present")), "detail": st.get("module", "")},
        {"id": "wired_into_pipeline", "ok": bool(st.get("wired_into_pipeline")),
         "detail": "notifier.notify_error → Data/pipeline_errors.jsonl"},
        {"id": "error_log", "ok": True,
         "detail": f"{st.get('error_log')} present={st.get('error_log_present')} "
                   f"last7d={st.get('errors_last_7_days')}"},
        {"id": "quarantine_dir", "ok": True,
         "detail": f"{st.get('quarantine_dir')} files={st.get('quarantine_count')}"},
        {"id": "discord", "ok": True,
         "detail": "notifier posts errors when webhooks are set; Error_Recovery adds none "
                   "unless ERROR_RECOVERY_DISCORD=1"},
    ]
    if st.get("last_error"):
        rows.append({"id": "last_error", "ok": False, "detail": st["last_error"]})
    for qf in _list_quarantine_files(limit=20):
        rows.append({"id": f"quarantine:{qf.get('name')}", "ok": True,
                     "detail": f"size={qf.get('size')} since={qf.get('mtime')}"})
    if st.get("legacy_cwd_quarantine_exists"):
        rows.append({"id": "legacy_cwd_quarantine", "ok": False,
                     "detail": "CWD quarantine/ still present — prefer Data/quarantine/"})
    return rows


def try_run(*, days: Optional[float] = DEFAULT_DAYS, probe: bool = True,
            dry_run: bool = False) -> Dict[str, Any]:
    """Build the recent-errors report. Read-only. Never raises."""
    try:
        rep = build_report(days, probe=probe)
        rep["ok"] = True
        rep["dry_run"] = dry_run
        rep["error"] = ""
        return rep
    except Exception as exc:
        return {"ok": False, "error": _soft(str(exc) or type(exc).__name__)}


# ── printing ─────────────────────────────────────────────────────────────────

def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, indent=2))
        return 0
    print(f"Error recovery: {info.get('readiness')}  ready={'yes' if info.get('ready') else 'no'}")
    print(f"  wired into clip pipeline: {info.get('wired_into_pipeline')}")
    print(f"  error log: {info.get('error_log')}  ({info.get('errors_last_7_days', 0)} in the last 7 days)")
    if info.get("last_error"):
        print(f"  last error: {info['last_error']}")
    print(f"  quarantine: {info.get('quarantine_dir')}  files={info.get('quarantine_count')}")
    if info.get("probe"):
        print(f"  probe_ok: {info.get('probe_ok')}")
    if info.get("error"):
        print(f"  {info['error']}")
    else:
        print(f"  hint: {info.get('hint')}")
    return 0


def _print_report(rep: Dict[str, Any]) -> None:
    days = rep.get("days")
    window = f"last {days:g} days" if isinstance(days, (int, float)) else "all time"
    print(f"Pipeline errors ({window}): {rep.get('total', 0)}   log: {rep.get('log')}")
    if not rep.get("total"):
        print("  Nothing failed. 🎉")
    for s in rep.get("stages") or []:
        print(f"\n  {s['stage']} — {s['count']}x on {s['recordings']} recording(s), last {s['last_time']}")
        print(f"    latest: {str(s['last_error'])[:200]}")
        print(f"    try: {s['hint']}")
    recs = rep.get("recordings") or []
    if recs:
        print("\n  Recordings with errors:")
        for g in recs[:15]:
            check = f" · {g['file_check']}" if g.get("file_check") else ""
            print(f"    {g['name']} — {g['count']}x ({', '.join(g['stages'])}){check}")
            if g.get("suggest"):
                print(f"      quarantine: {g['suggest']}")
    print(f"\n  Quarantined files: {rep.get('quarantine_count', 0)} "
          f"(bolt error-recovery restore to list / put back)")


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="bolt error-recovery",
        description="Clip pipeline error log + report, quarantine/restore broken recordings.",
    )
    parser.add_argument("action", nargs="?", default="status",
                        choices=["status", "list", "run", "summary", "report",
                                 "quarantine", "restore", "clear"])
    parser.add_argument("targets", nargs="*", help="quarantine: FILE · restore: NAME …")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--probe", action="store_true", help="status: with_retry self-test")
    parser.add_argument("--days", type=float, default=DEFAULT_DAYS, help="run: window (default 7)")
    parser.add_argument("--all-time", action="store_true", help="run: whole log")
    parser.add_argument("--no-probe", action="store_true", help="run: don't open recordings to check them")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reason", default="", help="quarantine: note kept in _moves.jsonl")
    parser.add_argument("--all", dest="all_files", action="store_true", help="restore: every quarantined file")
    args = parser.parse_args(argv)
    action = "run" if args.action in ("summary", "report") else args.action

    if action == "status":
        return _print_status(status(probe=args.probe), args.json)

    if action == "list":
        rows = list_items()
        if args.json:
            print(json.dumps({"items": rows}, indent=2))
        else:
            for r in rows:
                print(f"[{'OK' if r['ok'] else 'NO'}] {r['id']}: {r['detail']}")
        return 0

    if action == "run":
        rep = try_run(days=None if args.all_time else args.days, probe=not args.no_probe,
                      dry_run=args.dry_run)
        if args.json:
            print(json.dumps(rep, indent=2, default=str))
        elif not rep.get("ok"):
            print(rep.get("error"))
        else:
            _print_report(rep)
        return 0

    if action == "quarantine":
        if len(args.targets) != 1:
            print(_soft("usage: bolt error-recovery quarantine FILE [--reason TEXT] [--dry-run]"))
            return 0
        res = quarantine_file(args.targets[0], reason=args.reason, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(res, indent=2))
        elif res.get("ok"):
            verb = "Would move" if args.dry_run else "Moved"
            print(f"{verb} {res['source']} → {res['dest']}")
            if not args.dry_run:
                print(f"  Undo: bolt error-recovery restore \"{Path(res['dest']).name}\"")
        else:
            print(res.get("error"))
        return 0

    if action == "restore":
        if not args.targets and not args.all_files:
            files = _list_quarantine_files()
            if args.json:
                print(json.dumps({"quarantined": files}, indent=2))
            elif not files:
                print("Quarantine is empty.")
            else:
                print("In quarantine (restore with NAME or --all):")
                for f in files:
                    print(f"  {f['name']}  ({f['size']} bytes, since {f['mtime']})")
            return 0
        res = restore_files(args.targets, all_files=args.all_files, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            verb = "Would restore" if args.dry_run else "Restored"
            for r in res.get("restored") or []:
                print(f"{verb} {r['name']} → {r['to']}")
            for s in res.get("skipped") or []:
                print(f"Skipped {s['name']}: {s['why']}")
            if res.get("error"):
                print(res["error"])
        return 0

    if action == "clear":
        res = clear_log()
        if args.json:
            print(json.dumps(res, indent=2))
        elif res.get("ok"):
            print(f"Archived {res['archived']} error line(s) to {res['archive']}; log starts fresh.")
        else:
            print(res.get("error"))
        return 0

    print(_soft(f"unknown action {action!r}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
