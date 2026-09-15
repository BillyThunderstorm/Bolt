#!/usr/bin/env python3
"""
Performance_Baseline.py — local import/startup baseline (PARTIAL)
=================================================================
Wraps ``scripts/performance_baseline.py`` (PROJECT_STATUS / OPTIMIZATION
claim + thin ``bolt performance`` passthrough) with a soft-fail CLI.

Soft-fail prefix: ``Baseline unavailable:``. Local diagnostic only —
distinct from READY ``bolt analytics`` (outcomes summary) and
``bolt stats`` / ``performance-sync`` (social pull). Stay PARTIAL.

Public API:
  status() / list_items() / try_run() / print_status() / main()
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Baseline unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "performance_baseline.py"
_RESULTS = _REPO / "logs" / "performance"
_CORE = _REPO / "Core"
_LAUNCH = _CORE / "launch.py"
_BOT = _CORE / "bot.py"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _psutil_ok() -> bool:
    try:
        import psutil  # noqa: F401

        return True
    except Exception:
        return False


def _recent_baselines(limit: int = 8) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not _RESULTS.is_dir():
        return rows
    try:
        files = sorted(
            (p for p in _RESULTS.glob("baseline_*.json") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        return rows
    for p in files[:limit]:
        try:
            st = p.stat()
            rows.append(
                {
                    "path": str(p),
                    "name": p.name,
                    "mtime": datetime.fromtimestamp(
                        st.st_mtime, tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "size_bytes": st.st_size,
                }
            )
        except Exception:
            continue
    return rows


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness for local performance baseline (PARTIAL)."""
    try:
        script_ok = _SCRIPT.is_file()
        core_ok = _CORE.is_dir()
        launch_ok = _LAUNCH.is_file()
        bot_ok = _BOT.is_file()
        results_ok = _RESULTS.is_dir()
        psutil = _psutil_ok() if (probe or True) else None
        recent = _recent_baselines(5)

        writable = False
        try:
            _RESULTS.mkdir(parents=True, exist_ok=True)
            probe_file = _RESULTS / ".bolt_baseline_write_probe"
            probe_file.write_text("ok", encoding="utf-8")
            probe_file.unlink(missing_ok=True)
            writable = True
            results_ok = True
        except Exception:
            writable = False

        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": True,
            "readiness": "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "script_path": str(_SCRIPT),
            "script_present": script_ok,
            "core_present": core_ok,
            "launch_path": str(_LAUNCH),
            "launch_present": launch_ok,
            "bot_path": str(_BOT),
            "bot_present": bot_ok,
            "results_dir": str(_RESULTS),
            "results_present": results_ok,
            "results_writable": writable,
            "psutil_present": bool(psutil),
            "recent_baselines": recent,
            "recent_count": len(recent),
            "cli": "bolt performance",
            "note": (
                "local import/startup baseline → logs/performance/; "
                "not bolt analytics (outcomes) or bolt stats (social pull)"
            ),
            "is_stranger_ready": False,
            "probe": bool(probe),
            "error": "",
            "hint": "",
        }

        if not script_ok:
            out["error"] = _soft(f"engine missing ({_SCRIPT})")
            out["hint"] = out["error"]
            return out
        if not core_ok:
            out["error"] = _soft(f"Core/ missing ({_CORE})")
            out["hint"] = out["error"]
            return out
        if not writable:
            out["error"] = _soft(f"cannot write results dir ({_RESULTS})")
            out["hint"] = out["error"]
            return out

        # Soft ready: script + Core + writable results. Missing launch/bot
        # is informational (script skips them). psutil optional (falls back).
        out["ready"] = True
        bits = [
            "script ok",
            "Core ok",
            f"results {_RESULTS.name}/",
            f"{len(recent)} prior",
        ]
        if launch_ok and bot_ok:
            bits.append("Core/launch+bot")
        elif not launch_ok or not bot_ok:
            bits.append("script startup paths may skip")
        if psutil:
            bits.append("psutil")
        else:
            bits.append("psutil optional")
        out["hint"] = " · ".join(bits) + " · local diagnostic (stay PARTIAL)"
        return out
    except Exception as exc:
        return {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": True,
            "readiness": "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "is_stranger_ready": False,
            "error": _soft(f"status failed ({exc})"),
            "hint": _soft(f"status failed ({exc})"),
        }


def list_items(*, as_json: bool = False) -> int:
    """Checklist + recent baseline files (no run)."""
    try:
        info = status(probe=False)
        rows = [
            ("script performance_baseline.py", bool(info.get("script_present"))),
            ("Core/ present", bool(info.get("core_present"))),
            ("Core/launch.py", bool(info.get("launch_present"))),
            ("Core/bot.py", bool(info.get("bot_present"))),
            (f"results dir ({info.get('results_dir')})", bool(info.get("results_present"))),
            ("results writable", bool(info.get("results_writable"))),
            ("psutil (optional richer memory)", bool(info.get("psutil_present"))),
            ("soft-fail CLI (bolt performance)", True),
            ("distinct from bolt analytics / bolt stats", True),
            ("local diagnostic (stay PARTIAL)", True),
        ]
        recent = info.get("recent_baselines") or []
        if as_json:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "readiness": "PARTIAL",
                        "items": [{"name": n, "ok": ok} for n, ok in rows],
                        "recent": recent,
                        "hint": info.get("hint"),
                        "error": info.get("error"),
                    },
                    indent=2,
                )
            )
            return 0
        print("Performance baseline (PARTIAL — local diagnostic)")
        for name, ok in rows:
            mark = "OK" if ok else "--"
            print(f"  [{mark}] {name}")
        if recent:
            print("  recent:")
            for r in recent[:5]:
                print(f"    - {r.get('name')} ({r.get('mtime')})")
        if info.get("hint"):
            print(f"  → {info['hint']}")
        print("  (run: bolt performance run [--json])")
        return 0
    except Exception as exc:
        msg = _soft(f"list failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def try_run(*, as_json: bool = False, dry_run: bool = False) -> int:
    """Soft-fail run of performance_baseline.py (never raises)."""
    try:
        info = status(probe=False)
        if not info.get("script_present"):
            msg = info.get("error") or _soft("engine script missing")
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": "PARTIAL"},
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0
        if not info.get("ready"):
            msg = info.get("error") or _soft("baseline tooling not ready")
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": "PARTIAL"},
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0

        if dry_run:
            payload = {
                "ok": True,
                "readiness": "PARTIAL",
                "dry_run": True,
                "would_run": str(_SCRIPT),
                "results_dir": str(_RESULTS),
                "cwd": str(_REPO),
            }
            if as_json:
                print(json.dumps(payload, indent=2))
            else:
                print(f"[dry-run] would run: {_SCRIPT}")
                print(f"  cwd: {_REPO}")
                print(f"  results: {_RESULTS}")
            return 0

        before = {p.name for p in _RESULTS.glob("baseline_*.json")} if _RESULTS.is_dir() else set()
        env = os.environ.copy()
        env["PYTHONPATH"] = str(_CORE) + (
            f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else ""
        )
        py = sys.executable
        try:
            proc = subprocess.run(
                [py, str(_SCRIPT)],
                cwd=str(_REPO),
                env=env,
                capture_output=as_json,
                text=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            msg = _soft("baseline timed out after 180s")
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": "PARTIAL"},
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0
        except Exception as exc:
            msg = _soft(f"run failed ({exc})")
            if as_json:
                print(
                    json.dumps(
                        {"ok": False, "error": msg, "readiness": "PARTIAL"},
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0

        after = {p.name for p in _RESULTS.glob("baseline_*.json")} if _RESULTS.is_dir() else set()
        new_names = sorted(after - before)
        newest = None
        if new_names:
            newest = str(_RESULTS / new_names[-1])
        else:
            recent = _recent_baselines(1)
            if recent:
                newest = recent[0].get("path")

        if proc.returncode != 0:
            err_tail = ""
            if as_json and proc.stderr:
                err_tail = proc.stderr.strip()[-400:]
            msg = _soft(
                f"engine exited {proc.returncode}"
                + (f": {err_tail}" if err_tail else "")
            )
            if as_json:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "error": msg,
                            "readiness": "PARTIAL",
                            "output": newest,
                            "stdout": (proc.stdout or "")[-800:] if proc.stdout else "",
                        },
                        indent=2,
                    )
                )
            else:
                print(msg, file=sys.stderr)
            return 0

        if as_json:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "readiness": "PARTIAL",
                        "output": newest,
                        "results_dir": str(_RESULTS),
                        "stdout": (proc.stdout or "")[-1200:] if proc.stdout else "",
                    },
                    indent=2,
                )
            )
        else:
            # Non-json: engine already printed; just confirm path
            if newest:
                print(f"\nBaseline saved: {newest}")
        return 0
    except Exception as exc:
        msg = _soft(f"run failed ({exc})")
        if as_json:
            print(
                json.dumps(
                    {"ok": False, "error": msg, "readiness": "PARTIAL"},
                    indent=2,
                )
            )
        else:
            print(msg, file=sys.stderr)
        return 0


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    try:
        info = status(probe=probe)
        if as_json:
            print(json.dumps(info, indent=2, default=str))
            return 0
        print("Performance baseline readiness (PARTIAL)")
        print(f"  ready: {info.get('ready')}")
        print(f"  readiness: {info.get('readiness')}")
        print(
            f"  script: {info.get('script_present')} · Core: {info.get('core_present')} · "
            f"launch: {info.get('launch_present')} · bot: {info.get('bot_present')}"
        )
        print(
            f"  results: {info.get('results_dir')} "
            f"(writable={info.get('results_writable')}, prior={info.get('recent_count')})"
        )
        print(f"  psutil: {info.get('psutil_present')}")
        print(f"  note: {info.get('note')}")
        print(f"  soft_fail_prefix: {info.get('soft_fail_prefix')}")
        if info.get("error"):
            print(f"  → {info['error']}")
        elif info.get("hint"):
            print(f"  → {info['hint']}")
        return 0
    except Exception as exc:
        msg = _soft(f"status print failed ({exc})")
        if as_json:
            print(
                json.dumps(
                    {"ready": False, "error": msg, "readiness": "PARTIAL"},
                    indent=2,
                )
            )
        else:
            print(msg, file=sys.stderr)
        return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt performance — local import/startup baseline (PARTIAL)

  bolt performance                              # status (default)
  bolt performance status [--json] [--probe]
  bolt performance list [--json]
  bolt performance run [--json] [--dry-run]

Soft-fail: "Baseline unavailable:".
Local diagnostic — stay PARTIAL.
Distinct from bolt analytics (outcomes) and bolt stats (social pull).
Engine: scripts/performance_baseline.py → logs/performance/
Aliases: baseline, perf-baseline, performance-baseline
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    dry_run = "--dry-run" in args or "--dryrun" in args
    cleaned = [a for a in args if not a.startswith("-")]

    if not cleaned:
        return print_status(as_json=json_out, probe=probe)

    cmd = cleaned[0].lower()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "recent", "checklist"):
        return list_items(as_json=json_out)
    if cmd in ("run", "baseline", "measure", "bench", "snapshot"):
        return try_run(as_json=json_out, dry_run=dry_run)

    print(
        _soft(f"unknown command '{cmd}' — try status|list|run"),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
