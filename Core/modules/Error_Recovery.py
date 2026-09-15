#!/usr/bin/env python3
"""
Error_Recovery.py — retry + error tracking soft-fail CLI (PARTIAL)
==================================================================
Pipeline failure helpers: ``with_retry``, ``ErrorTracker`` (record / quarantine /
send_summary / Discord alert threshold), ``get_tracker`` / ``record_error`` /
``session_summary``.

Soft-fail prefix: ``Error recovery unavailable:``.

CLI (via ``bolt error-recovery``):
  status [--json] [--probe]
  list [--json]
  run [--json] [--dry-run] [--probe]
  summary  (alias of run)

Stay PARTIAL — not wired into bot.py; Discord alert path overlaps PARTIAL
``bolt discord`` but this surface is pipeline retry/quarantine — keep distinct.
Not stranger-ready.

Public API (in-process):
  with_retry, ErrorTracker, get_tracker, record_error, session_summary
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

_SOFT = "Error recovery unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_QUARANTINE = _REPO / "Data" / "quarantine"
# Legacy CWD-relative path (pre-promotion callers)
_LEGACY_QUARANTINE = Path("quarantine")

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "") or ""
MAX_ERRORS_BEFORE_ALERT = int(os.getenv("MAX_ERRORS_BEFORE_ALERT", "3") or "3")


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def quarantine_dir() -> Path:
    """Repo-rooted quarantine directory (Data/quarantine/)."""
    return _QUARANTINE


def _quarantine_count(path: Optional[Path] = None) -> int:
    root = path or _QUARANTINE
    if not root.is_dir():
        return 0
    try:
        return sum(1 for p in root.iterdir() if p.is_file())
    except Exception:
        return 0


def _list_quarantine_files(limit: int = 50) -> List[Dict[str, Any]]:
    root = _QUARANTINE
    if not root.is_dir():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        files = sorted(
            (p for p in root.iterdir() if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        return []
    for p in files[:limit]:
        try:
            st = p.stat()
            rows.append(
                {
                    "name": p.name,
                    "path": str(p),
                    "size": st.st_size,
                    "mtime": datetime.fromtimestamp(
                        st.st_mtime, tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
            )
        except Exception:
            rows.append({"name": p.name, "path": str(p), "size": None, "mtime": None})
    return rows


def with_retry(
    fn: Callable[..., Any],
    *args: Any,
    retries: int = 3,
    label: str = "",
    reraise: bool = False,
    **kwargs: Any,
) -> Any:
    delay = 5
    last_exc: Optional[BaseException] = None
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            print(
                f"[ErrorRecovery] {label or getattr(fn, '__name__', 'fn')} "
                f"attempt {attempt}/{retries} failed: {exc}"
            )
            if attempt < retries:
                time.sleep(delay)
                delay *= 3
    if reraise and last_exc:
        raise last_exc
    return None


class ErrorTracker:
    def __init__(self) -> None:
        self._errors: List[Dict[str, Any]] = []
        self._counts: Dict[str, int] = {}
        self._alerted: set = set()

    def record(self, stage: str, context: str, error: Exception) -> None:
        entry = {
            "stage": stage,
            "context": context,
            "error": str(error),
            "time": datetime.now().isoformat(),
        }
        self._errors.append(entry)
        self._counts[stage] = self._counts.get(stage, 0) + 1
        print(f"[ErrorTracker] {stage}: {error}")
        if (
            self._counts[stage] >= MAX_ERRORS_BEFORE_ALERT
            and stage not in self._alerted
        ):
            self._alerted.add(stage)
            self._alert_discord(stage, error)

    def quarantine(self, file_path: str, reason: str = "") -> None:
        dest_dir = quarantine_dir()
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            print(f"[ErrorTracker] Could not create quarantine dir {dest_dir}: {exc}")
            return
        dest = dest_dir / os.path.basename(file_path)
        try:
            shutil.move(file_path, str(dest))
            print(f"[ErrorTracker] Quarantined: {file_path} → {dest} ({reason})")
        except Exception as exc:
            print(f"[ErrorTracker] Could not quarantine {file_path}: {exc}")

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

    def _alert_discord(self, stage: str, error: Exception) -> None:
        if not DISCORD_WEBHOOK:
            return
        body = {
            "content": (
                f"⚠️ **Bolt error alert** | {stage} failed "
                f"{self._counts[stage]}x\nLatest: {error}"
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


def record_error(stage: str, context: str, error: Exception) -> None:
    get_tracker().record(stage, context, error)


def session_summary() -> None:
    get_tracker().send_summary()


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Never raises. ready=True when public API importable + quarantine path resolvable."""
    try:
        qdir = quarantine_dir()
        q_exists = qdir.is_dir()
        q_count = _quarantine_count(qdir)
        webhook = DISCORD_WEBHOOK
        webhook_present = bool(webhook.strip())

        api_ok = True
        api_note = "with_retry + ErrorTracker + get_tracker importable"
        try:
            assert callable(with_retry)
            assert ErrorTracker is not None
            assert callable(get_tracker)
            assert callable(record_error)
            assert callable(session_summary)
        except Exception as exc:
            api_ok = False
            api_note = f"API check failed: {exc}"

        missing: List[str] = []
        if not api_ok:
            missing.append("public API not importable")
        # Webhook optional — pipeline retry/quarantine works without Discord
        if not webhook_present:
            missing.append(
                "DISCORD_WEBHOOK_URL unset (optional; threshold alerts skip Discord)"
            )

        ready = api_ok and bool(qdir)

        info: Dict[str, Any] = {
            "checked_at": _iso(),
            "ready": ready,
            "partial": True,
            "readiness": "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "cli": "bolt error-recovery",
            "module": str(Path(__file__).resolve()),
            "module_present": Path(__file__).is_file(),
            "max_errors_before_alert": MAX_ERRORS_BEFORE_ALERT,
            "discord_webhook_present": webhook_present,
            "discord_webhook_redacted": _redact_webhook(webhook) if webhook_present else "",
            "quarantine_dir": str(qdir),
            "quarantine_exists": q_exists,
            "quarantine_count": q_count,
            "legacy_cwd_quarantine_exists": _LEGACY_QUARANTINE.is_dir(),
            "api_ok": api_ok,
            "api_note": api_note,
            "with_retry_importable": api_ok,
            "error_tracker_importable": api_ok,
            "probe": bool(probe),
            "probe_ok": None,
            "error": "",
            "hint": (
                "pipeline retry/quarantine · Data/quarantine/ · distinct from "
                "PARTIAL bolt discord / bolt alerts · stay PARTIAL (not wired into bot.py)"
            ),
            "is_stranger_ready": False,
            "missing": missing,
        }

        if not ready:
            info["error"] = _soft(api_note if not api_ok else "quarantine path unresolved")

        if probe:
            try:
                result = with_retry(lambda: True, retries=1, label="status-probe")
                info["probe_ok"] = result is True
                info["probe_label"] = "with_retry(lambda: True)"
            except Exception as exc:
                info["probe_ok"] = False
                info["error"] = _soft(str(exc) or type(exc).__name__)
        return info
    except Exception as exc:
        return {
            "checked_at": _iso(),
            "ready": False,
            "partial": True,
            "readiness": "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "cli": "bolt error-recovery",
            "error": _soft(str(exc) or type(exc).__name__),
            "hint": "import/status failed",
            "is_stranger_ready": False,
            "probe": bool(probe),
            "probe_ok": False,
        }


def list_items() -> List[Dict[str, Any]]:
    st = status(probe=False)
    rows: List[Dict[str, Any]] = []
    rows.append(
        {
            "id": "module",
            "ok": bool(st.get("module_present")),
            "detail": st.get("module") or str(Path(__file__).resolve()),
        }
    )
    rows.append(
        {
            "id": "public_api",
            "ok": bool(st.get("api_ok")),
            "detail": st.get("api_note") or "",
        }
    )
    rows.append(
        {
            "id": "max_errors_before_alert",
            "ok": True,
            "detail": str(st.get("max_errors_before_alert")),
        }
    )
    rows.append(
        {
            "id": "discord_webhook",
            "ok": bool(st.get("discord_webhook_present")),
            "detail": (
                f"present redacted={st.get('discord_webhook_redacted')!r}"
                if st.get("discord_webhook_present")
                else "unset (optional; threshold alerts skip Discord)"
            ),
        }
    )
    rows.append(
        {
            "id": "quarantine_dir",
            "ok": True,
            "detail": (
                f"{st.get('quarantine_dir')} exists={st.get('quarantine_exists')} "
                f"files={st.get('quarantine_count')}"
            ),
        }
    )
    if st.get("legacy_cwd_quarantine_exists"):
        rows.append(
            {
                "id": "legacy_cwd_quarantine",
                "ok": False,
                "detail": "CWD quarantine/ still present — prefer Data/quarantine/",
            }
        )
    for qf in _list_quarantine_files(limit=20):
        rows.append(
            {
                "id": f"quarantine:{qf.get('name')}",
                "ok": True,
                "detail": f"size={qf.get('size')} mtime={qf.get('mtime')}",
            }
        )
    if int(st.get("quarantine_count") or 0) == 0:
        rows.append(
            {
                "id": "quarantine_empty",
                "ok": True,
                "detail": "no quarantined files",
            }
        )
    rows.append(
        {
            "id": "soft_fail",
            "ok": True,
            "detail": (
                f"prefix {_SOFT!r}; stay PARTIAL; distinct from PARTIAL "
                "bolt discord / bolt alerts"
            ),
        }
    )
    return rows


def try_run(
    *, dry_run: bool = False, probe: bool = False
) -> Dict[str, Any]:
    """Print tracker session summary / optional retry self-test. Never raises."""
    out: Dict[str, Any] = {
        "ok": False,
        "error": "",
        "dry_run": bool(dry_run),
        "probe": bool(probe),
        "probe_ok": None,
        "snapshot": {},
        "summary_printed": False,
    }
    try:
        tracker = get_tracker()
        snap = tracker.snapshot()
        out["snapshot"] = {
            "error_count": snap.get("error_count", 0),
            "counts": snap.get("counts") or {},
            "alerted_stages": snap.get("alerted_stages") or [],
        }
        if dry_run:
            out["ok"] = True
            out["summary_printed"] = False
            out["hint"] = "dry-run: skipped session_summary(); tracker state above"
            if probe:
                try:
                    result = with_retry(lambda: True, retries=1, label="run-probe")
                    out["probe_ok"] = result is True
                except Exception as exc:
                    out["probe_ok"] = False
                    out["error"] = _soft(str(exc) or type(exc).__name__)
            return out

        session_summary()
        out["summary_printed"] = True
        out["ok"] = True

        if probe:
            try:
                result = with_retry(lambda: True, retries=1, label="run-probe")
                out["probe_ok"] = result is True
            except Exception as exc:
                out["probe_ok"] = False
                out["error"] = _soft(str(exc) or type(exc).__name__)
        return out
    except Exception as exc:
        out["error"] = _soft(str(exc) or type(exc).__name__)
        return out


def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, indent=2))
    else:
        ready = "yes" if info.get("ready") else "no"
        print(f"error-recovery readiness: {info.get('readiness')}  ready={ready}")
        print(f"  module: present={info.get('module_present')}")
        print(f"  MAX_ERRORS_BEFORE_ALERT: {info.get('max_errors_before_alert')}")
        print(
            f"  DISCORD_WEBHOOK_URL: present={info.get('discord_webhook_present')}  "
            f"redacted={info.get('discord_webhook_redacted')!r}"
        )
        print(
            f"  quarantine: path={info.get('quarantine_dir')}  "
            f"exists={info.get('quarantine_exists')}  "
            f"files={info.get('quarantine_count')}"
        )
        print(
            f"  API: with_retry/ErrorTracker importable={info.get('api_ok')}  "
            f"({info.get('api_note')})"
        )
        if info.get("probe"):
            print(
                f"  probe_ok: {info.get('probe_ok')}  "
                f"label={info.get('probe_label')}"
            )
        if info.get("error"):
            print(f"  {info['error']}")
        else:
            print(f"  hint: {info.get('hint')}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    argv = list(sys.argv[1:] if argv is None else argv)

    parser = argparse.ArgumentParser(
        prog="bolt error-recovery",
        description="Pipeline retry/quarantine helpers (PARTIAL; soft-fail).",
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "list", "run", "summary"],
        help="status (default) | list | run | summary (run alias)",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="status/run: with_retry(lambda: True) self-test",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run: skip session_summary(); print tracker state only",
    )
    args = parser.parse_args(argv)

    action = "run" if args.action == "summary" else args.action

    if action == "status":
        return _print_status(status(probe=args.probe), args.json)

    if action == "list":
        rows = list_items()
        if args.json:
            print(json.dumps({"items": rows, "soft_fail_note": _SOFT}, indent=2))
        else:
            for r in rows:
                mark = "OK" if r["ok"] else "NO"
                print(f"[{mark}] {r['id']}: {r['detail']}")
            print(f"(soft-fail prefix: {_SOFT!r})")
        return 0

    if action == "run":
        result = try_run(dry_run=args.dry_run, probe=args.probe)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result.get("error") and not result.get("ok"):
                print(result["error"])
                return 0
            snap = result.get("snapshot") or {}
            mode = "dry-run" if result.get("dry_run") else "live"
            print(
                f"error-recovery run ({mode}): ok={result.get('ok')}  "
                f"session_errors={snap.get('error_count', 0)}"
            )
            counts = snap.get("counts") or {}
            if counts:
                for stage, count in sorted(counts.items(), key=lambda x: -x[1]):
                    print(f"  {stage}: {count}x")
            else:
                print("  (no tracked errors this process)")
            if result.get("probe"):
                print(f"  probe_ok: {result.get('probe_ok')}")
            if result.get("hint"):
                print(f"  hint: {result['hint']}")
            if result.get("error"):
                print(f"  {result['error']}")
        return 0

    print(_soft(f"unknown action {action!r}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
