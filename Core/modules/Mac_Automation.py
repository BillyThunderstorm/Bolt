#!/usr/bin/env python3
"""
Mac_Automation.py — launchd / cron / Shortcuts readiness (PARTIAL)
=================================================================
William-specific macOS glue status surface. Soft-fail prefix:
``Mac automation unavailable:``.

Existing pieces (already real):
  scripts/install_mac_automation.py
  scripts/autostart.py  (com.streamer.ai-assistant)
  scripts/macos_shortcuts/{signed,unsigned}/

This module does **not** claim stranger-ready or READY — stay PARTIAL.

  bolt mac-auto                         # status (default)
  bolt mac-auto status [--json] [--probe]
  bolt mac-auto list [--json]
  bolt mac-auto install [launchd|cron|shortcuts|all] [--dry-run] [--json]

Aliases: mac_auto, mac-automation, automation, shortcuts-status, launchd-status.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO = Path(__file__).resolve().parents[2]
_INSTALL = _REPO / "scripts" / "install_mac_automation.py"
_AUTOSTART = _REPO / "scripts" / "autostart.py"
_SIGNED_DIR = _REPO / "scripts" / "macos_shortcuts" / "signed"
_UNSIGNED_DIR = _REPO / "scripts" / "macos_shortcuts" / "unsigned"
_VENV_BOLT = _REPO / ".venv" / "bin" / "bolt"
_VENV_PY = _REPO / ".venv" / "bin" / "python3"
_PLIST_LABEL = "com.streamer.ai-assistant"
_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{_PLIST_LABEL}.plist"
_BRIEFING_CRON_MARK = "Daily at 5pm: evening briefing"
_PROCESS_CRON_MARK = "Every 2 hours: auto-process any new recordings"
_INSTALL_STEPS = ("launchd", "cron", "shortcuts", "all")
_SOFT = "Mac automation unavailable:"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _run(
    cmd: List[str],
    *,
    timeout: float = 8.0,
    text: bool = True,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=text,
        timeout=timeout,
        check=False,
    )


def _crontab_text() -> tuple[Optional[str], Optional[str]]:
    """Return (text, error). Missing crontab is not fatal."""
    if platform.system() != "Darwin" and shutil.which("crontab") is None:
        return None, "crontab not available"
    try:
        r = _run(["crontab", "-l"], timeout=5.0)
    except Exception as exc:
        return None, str(exc)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip() or f"exit {r.returncode}"
        # Empty crontab often exits 1 with "no crontab for …"
        if "no crontab" in err.lower():
            return "", None
        return None, err
    return r.stdout or "", None


def _signed_shortcut_count() -> int:
    if not _SIGNED_DIR.is_dir():
        return 0
    return sum(
        1
        for p in _SIGNED_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in (".shortcut", ".wflow")
    )


def _launchctl_loaded(*, probe: bool) -> Optional[bool]:
    if not probe or platform.system() != "Darwin":
        return None
    try:
        domain = f"gui/{os.getuid()}"
        r = _run(["launchctl", "print", f"{domain}/{_PLIST_LABEL}"], timeout=5.0)
        if r.returncode == 0:
            return True
        # Fallback: list and grep label
        r2 = _run(["launchctl", "list"], timeout=5.0)
        if r2.returncode == 0 and _PLIST_LABEL in (r2.stdout or ""):
            return True
        return False
    except Exception:
        return False


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Mac automation readiness. Never raises. PARTIAL / not stranger-ready."""
    try:
        is_darwin = platform.system() == "Darwin"
        install_present = _INSTALL.is_file()
        autostart_present = _AUTOSTART.is_file()
        plist_exists = _PLIST_PATH.is_file()
        shortcuts_cli = shutil.which("shortcuts")
        signed_count = _signed_shortcut_count()
        venv_bolt = str(_VENV_BOLT) if _VENV_BOLT.is_file() else None
        venv_py = str(_VENV_PY) if _VENV_PY.is_file() else None

        cron_text, cron_err = _crontab_text()
        briefing_mark = bool(cron_text and _BRIEFING_CRON_MARK in cron_text)
        process_mark = bool(cron_text and _PROCESS_CRON_MARK in cron_text)
        cron_marks = briefing_mark or process_mark

        launchd_loaded = _launchctl_loaded(probe=probe)

        missing: List[str] = []
        if not is_darwin:
            missing.append("not macOS (Darwin)")
        if not install_present:
            missing.append("missing scripts/install_mac_automation.py")
        if not autostart_present:
            missing.append("missing scripts/autostart.py")

        # ready bar: darwin + install script + at least one automation piece
        piece_ok = bool(plist_exists or signed_count > 0 or cron_marks)
        ready = bool(is_darwin and install_present and piece_ok)

        if ready:
            hint = (
                "darwin + install script + automation pieces present. "
                "Try: bolt mac-auto list / bolt mac-auto install all --dry-run"
            )
            error = None
        else:
            parts = list(missing)
            if is_darwin and install_present and not piece_ok:
                parts.append(
                    "no launchd plist, signed shortcuts, or cron marks — "
                    "try: bolt mac-auto install all --dry-run"
                )
            error = _soft("; ".join(parts[:3]) if parts else "not ready")
            hint = error

        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": ready,
            "partial": True,
            "readiness": "PARTIAL",
            "is_stranger_ready": False,
            "is_william_specific": True,
            "soft_fail_prefix": _SOFT,
            "darwin": is_darwin,
            "platform": platform.system(),
            "install_script": str(_INSTALL) if install_present else None,
            "install_script_present": install_present,
            "autostart_script": str(_AUTOSTART) if autostart_present else None,
            "autostart_present": autostart_present,
            "plist_label": _PLIST_LABEL,
            "plist_path": str(_PLIST_PATH),
            "plist_exists": plist_exists,
            "launchd_loaded": launchd_loaded,
            "crontab_readable": cron_text is not None,
            "crontab_error": cron_err,
            "cron_briefing_mark": briefing_mark,
            "cron_process_mark": process_mark,
            "cron_marks": cron_marks,
            "shortcuts_cli": shortcuts_cli,
            "shortcuts_cli_present": bool(shortcuts_cli),
            "signed_dir": str(_SIGNED_DIR),
            "signed_shortcut_count": signed_count,
            "unsigned_dir_exists": _UNSIGNED_DIR.is_dir(),
            "venv_bolt": venv_bolt,
            "venv_python": venv_py,
            "missing": missing,
            "error": error,
            "hint": hint,
        }

        if probe:
            out["probe"] = True
            if not is_darwin:
                out["probe_ok"] = False
                out["probe_detail"] = _soft("not macOS")
            else:
                details = []
                if launchd_loaded is True:
                    details.append("launchd loaded")
                elif launchd_loaded is False:
                    details.append("launchd not loaded")
                else:
                    details.append("launchd load unchecked")
                if cron_marks:
                    details.append("cron marks ok")
                elif cron_err:
                    details.append(f"crontab ({cron_err})")
                else:
                    details.append("no cron marks")
                if signed_count:
                    details.append(f"{signed_count} signed shortcut(s)")
                else:
                    details.append("no signed shortcuts")
                out["probe_ok"] = bool(ready)
                out["probe_detail"] = "; ".join(details)
                if not out["probe_ok"] and not out.get("error"):
                    out["error"] = _soft(out["probe_detail"])
                    out["hint"] = out["error"]
        return out
    except Exception as exc:
        return {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": True,
            "readiness": "PARTIAL",
            "is_stranger_ready": False,
            "is_william_specific": True,
            "soft_fail_prefix": _SOFT,
            "darwin": platform.system() == "Darwin",
            "platform": platform.system(),
            "install_script_present": _INSTALL.is_file(),
            "autostart_present": _AUTOSTART.is_file(),
            "plist_exists": False,
            "launchd_loaded": None,
            "cron_marks": False,
            "shortcuts_cli_present": False,
            "signed_shortcut_count": 0,
            "error": _soft(f"status failed ({exc})"),
            "hint": _soft(f"status failed ({exc})"),
        }


def list_items(*, as_json: bool = False) -> int:
    """Checklist: launchd / cron / shortcuts / reminders."""
    try:
        info = status()
        rows = [
            ("platform_darwin", bool(info.get("darwin"))),
            ("scripts/install_mac_automation.py", bool(info.get("install_script_present"))),
            ("scripts/autostart.py", bool(info.get("autostart_present"))),
            (f"launchd plist ({_PLIST_LABEL})", bool(info.get("plist_exists"))),
            ("cron briefing mark (5pm)", bool(info.get("cron_briefing_mark"))),
            ("cron process mark (2h)", bool(info.get("cron_process_mark"))),
            ("shortcuts CLI", bool(info.get("shortcuts_cli_present"))),
            (
                f"signed shortcuts ({info.get('signed_shortcut_count', 0)})",
                int(info.get("signed_shortcut_count") or 0) > 0,
            ),
            ("venv .venv/bin/bolt", bool(info.get("venv_bolt"))),
            ("reminders (Apple_Reminders module)", (_REPO / "Core" / "modules" / "Apple_Reminders.py").is_file()),
            ("stranger-ready (never claimed)", False),
        ]
        if as_json:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "readiness": "PARTIAL",
                        "is_stranger_ready": False,
                        "items": [{"name": n, "ok": ok} for n, ok in rows],
                        "hint": info.get("hint"),
                        "error": info.get("error"),
                    },
                    indent=2,
                )
            )
            return 0
        print("Mac automation pieces (PARTIAL — William-specific; not stranger-ready)")
        for name, ok in rows:
            mark = "OK" if ok else "--"
            print(f"  [{mark}] {name}")
        if info.get("hint"):
            print(f"  → {info['hint']}")
        return 0
    except Exception as exc:
        msg = _soft(f"list failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def try_install(
    step: str = "all",
    *,
    dry_run: bool = True,
    as_json: bool = False,
) -> int:
    """Soft-fail wrapper around install_mac_automation.py. Prefer dry-run."""
    try:
        step_l = (step or "all").strip().lower()
        if step_l not in _INSTALL_STEPS:
            msg = _soft(f"unknown step {step!r} — use launchd|cron|shortcuts|all")
            if as_json:
                print(json.dumps({"ok": False, "error": msg, "dry_run": dry_run}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0

        if not _INSTALL.is_file():
            msg = _soft(f"missing {_INSTALL}")
            if as_json:
                print(json.dumps({"ok": False, "error": msg, "dry_run": dry_run}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0

        py = str(_VENV_PY) if _VENV_PY.is_file() else sys.executable
        if step_l == "all":
            cmd = [py, str(_INSTALL)]
            intended = " ".join(cmd)
        else:
            cmd = [py, str(_INSTALL), step_l]
            intended = " ".join(cmd)

        if dry_run:
            payload = {
                "ok": True,
                "dry_run": True,
                "step": step_l,
                "would_run": intended,
                "note": "no mutation; drop --dry-run to install",
                "readiness": "PARTIAL",
                "is_stranger_ready": False,
            }
            if as_json:
                print(json.dumps(payload, indent=2))
            else:
                print("Mac automation dry-run: would run")
                print(f"  {intended}")
                print("  note: no mutation; drop --dry-run to install (PARTIAL / William-specific)")
            return 0

        if platform.system() != "Darwin":
            msg = _soft("not macOS — install skipped")
            if as_json:
                print(json.dumps({"ok": False, "error": msg, "dry_run": False}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0

        try:
            r = _run(cmd, timeout=120.0)
        except subprocess.TimeoutExpired:
            msg = _soft(f"install timed out ({step_l})")
            if as_json:
                print(json.dumps({"ok": False, "error": msg, "step": step_l}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0
        except Exception as exc:
            msg = _soft(f"install failed ({exc})")
            if as_json:
                print(json.dumps({"ok": False, "error": msg, "step": step_l}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0

        ok = r.returncode == 0
        stdout = (r.stdout or "").strip()
        stderr = (r.stderr or "").strip()
        payload: Dict[str, Any] = {
            "ok": ok,
            "dry_run": False,
            "step": step_l,
            "command": intended,
            "returncode": r.returncode,
            "stdout_tail": stdout[-2000:] if stdout else "",
            "stderr_tail": stderr[-1000:] if stderr else "",
            "readiness": "PARTIAL",
            "is_stranger_ready": False,
        }
        if not ok:
            payload["error"] = _soft(
                f"install exit {r.returncode}"
                + (f": {stderr.splitlines()[-1]}" if stderr else "")
            )
        info = status()
        payload["status_ready"] = bool(info.get("ready"))
        payload["hint"] = info.get("hint")
        if as_json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            if ok:
                print(f"Mac automation install ({step_l}) finished (rc=0)")
                if stdout:
                    print(stdout[-1500:])
            else:
                print(payload["error"], file=sys.stderr)
                if stderr:
                    print(stderr[-800:], file=sys.stderr)
            print(
                f"  status ready={info.get('ready')} · readiness=PARTIAL · stranger-ready=false"
            )
        return 0
    except Exception as exc:
        msg = _soft(f"install wrapper failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    try:
        info = status(probe=probe)
        if as_json:
            print(json.dumps(info, indent=2, default=str))
            return 0
        print("Bolt Mac automation readiness (PARTIAL)")
        print(f"  ready: {info.get('ready')}")
        print(f"  readiness: {info.get('readiness')} · stranger-ready: {info.get('is_stranger_ready')}")
        print(f"  darwin: {info.get('darwin')} · install script: {info.get('install_script_present')}")
        print(f"  autostart.py: {info.get('autostart_present')}")
        print(
            f"  launchd plist: {info.get('plist_exists')}"
            + (
                f" · loaded: {info.get('launchd_loaded')}"
                if info.get("launchd_loaded") is not None
                else ""
            )
        )
        print(
            f"  cron marks: briefing={info.get('cron_briefing_mark')} "
            f"process={info.get('cron_process_mark')}"
        )
        print(
            f"  shortcuts CLI: {info.get('shortcuts_cli_present')} · "
            f"signed: {info.get('signed_shortcut_count')}"
        )
        if info.get("venv_bolt"):
            print(f"  venv bolt: {info['venv_bolt']}")
        if info.get("error"):
            print(f"  → {info['error']}")
        elif info.get("hint"):
            print(f"  → {info['hint']}")
        return 0
    except Exception as exc:
        msg = _soft(f"status print failed ({exc})")
        if as_json:
            print(json.dumps({"ready": False, "error": msg, "readiness": "PARTIAL"}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt mac-auto — Mac automation readiness (PARTIAL / William-specific)

  bolt mac-auto                                      # status (default)
  bolt mac-auto status [--json] [--probe]
  bolt mac-auto list [--json]
  bolt mac-auto install [launchd|cron|shortcuts|all] [--dry-run] [--json]

Soft-fail: "Mac automation unavailable:".
Not stranger-ready. Prefer --dry-run before real install.
Advanced: python3 scripts/install_mac_automation.py
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    dry_run = "--dry-run" in args
    positionals = [a for a in args if not a.startswith("-")]
    if not positionals:
        return print_status(as_json=json_out, probe=probe)

    cmd = positionals[0].lower()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "pieces", "checklist"):
        return list_items(as_json=json_out)
    if cmd in ("install", "setup", "apply"):
        step = positionals[1].lower() if len(positionals) > 1 else "all"
        # Default dry_run=False only when user omitted --dry-run and asked install;
        # still safe: caller should pass --dry-run for smoke. Real install when not dry-run.
        return try_install(step, dry_run=dry_run, as_json=json_out)

    print(f"unknown mac-auto action: {cmd}", file=sys.stderr)
    print(
        "  try: bolt mac-auto status|list|install [--json] [--dry-run] [--probe]",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
