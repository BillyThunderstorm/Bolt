#!/usr/bin/env python3
"""
Performance_Baseline.py — Bolt speed check (READY)
==================================================
CLI wrapper for ``scripts/performance_baseline.py`` (``bolt performance``).

The engine times Bolt's startup the honest way — each item in a fresh Python
process (cold import), median of 3 runs — prints a plain report, compares it
with the previous baseline, and saves JSON to ``logs/performance/``.

Soft-fail prefix: ``Baseline unavailable:``. Local only (no network/keys,
nothing spoken, nothing deleted). Distinct from READY ``bolt analytics``
(outcomes summary) and ``bolt stats`` / ``performance-sync`` (social pull).

Public API:
  status() / list_items() / last_report() / try_run() / print_status() / main()
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
_METHOD = "fresh-process-v2"
_RUN_TIMEOUT = 600


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    return msg if msg.startswith(_SOFT) else f"{_SOFT} {msg}"


def _psutil_ok() -> bool:
    try:
        import psutil  # noqa: F401

        return True
    except Exception:
        return False


def _ms(sec: Any) -> str:
    try:
        sec = float(sec)
    except Exception:
        return "—"
    return f"{sec * 1000:.0f} ms" if sec < 1 else f"{sec:.2f} s"


def _load(p: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _recent_baselines(limit: int = 8) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not _RESULTS.is_dir():
        return rows
    try:
        files = sorted((p for p in _RESULTS.glob("baseline_*.json") if p.is_file()),
                       key=lambda p: p.name, reverse=True)
    except Exception:
        return rows
    for p in files[:limit]:
        try:
            st = p.stat()
            data = _load(p) or {}
            summ = data.get("summary") or {}
            rows.append({
                "path": str(p),
                "name": p.name,
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "size_bytes": st.st_size,
                "timestamp": data.get("timestamp"),
                "method": data.get("method") or "old in-process",
                "bolt_startup_sec": summ.get("bolt_startup_sec"),
                "verdict": summ.get("verdict"),
            })
        except Exception:
            continue
    return rows


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness for the Bolt speed check (READY when engine + results dir work)."""
    try:
        script_ok = _SCRIPT.is_file()
        core_ok = _CORE.is_dir()
        launch_ok = _LAUNCH.is_file()
        bot_ok = _BOT.is_file()
        psutil = _psutil_ok()
        recent = _recent_baselines(5)

        writable = False
        try:
            _RESULTS.mkdir(parents=True, exist_ok=True)
            probe_file = _RESULTS / ".bolt_baseline_write_probe"
            probe_file.write_text("ok", encoding="utf-8")
            probe_file.unlink(missing_ok=True)
            writable = True
        except Exception:
            writable = False

        last = recent[0] if recent else None
        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": False,
            "readiness": "READY",
            "soft_fail_prefix": _SOFT,
            "script_path": str(_SCRIPT),
            "script_present": script_ok,
            "core_present": core_ok,
            "launch_path": str(_LAUNCH),
            "launch_present": launch_ok,
            "bot_path": str(_BOT),
            "bot_present": bot_ok,
            "results_dir": str(_RESULTS),
            "results_present": _RESULTS.is_dir(),
            "results_writable": writable,
            "psutil_present": bool(psutil),
            "recent_baselines": recent,
            "recent_count": len(recent),
            "last_baseline": last,
            "cli": "bolt performance",
            "note": ("Bolt speed check (cold startup + module import times) → logs/performance/; "
                     "not bolt analytics (outcomes) or bolt stats (social pull)"),
            "is_stranger_ready": True,
            "probe": bool(probe),
            "error": "",
            "hint": "",
        }
        if not script_ok:
            out["error"] = _soft(f"engine missing ({_SCRIPT})")
        elif not core_ok:
            out["error"] = _soft(f"Core/ missing ({_CORE})")
        elif not writable:
            out["error"] = _soft(f"cannot write results dir ({_RESULTS}) — check folder permissions")
        if out["error"]:
            out["hint"] = out["error"]
            return out

        out["ready"] = True
        bits = ["engine ok", f"results {_RESULTS.name}/ writable", f"{len(recent)} saved"]
        if not (launch_ok and bot_ok):
            bits.append("Core/launch.py or bot.py missing (syntax check skips it)")
        bits.append("psutil ok" if psutil else "psutil missing (optional: memory numbers — uv pip install psutil)")
        if last and last.get("method") == _METHOD:
            bits.append(f"last: Bolt startup {_ms(last.get('bolt_startup_sec'))} ({(last.get('timestamp') or '')[:16].replace('T', ' ')})")
        else:
            bits.append("no new-style baseline yet — run: bolt performance run")
        out["hint"] = " · ".join(bits)
        return out
    except Exception as exc:
        return {
            "checked_at": _utc_now(), "ready": False, "partial": False, "readiness": "READY",
            "soft_fail_prefix": _SOFT, "is_stranger_ready": True,
            "error": _soft(f"status failed ({exc})"), "hint": _soft(f"status failed ({exc})"),
        }


def list_items(*, as_json: bool = False) -> int:
    """Checklist + recent baseline files (no run)."""
    try:
        info = status(probe=False)
        rows = [
            ("engine scripts/performance_baseline.py", bool(info.get("script_present"))),
            ("Core/ present", bool(info.get("core_present"))),
            ("Core/launch.py", bool(info.get("launch_present"))),
            ("Core/bot.py", bool(info.get("bot_present"))),
            (f"results dir writable ({info.get('results_dir')})", bool(info.get("results_writable"))),
            ("psutil (optional — memory numbers)", bool(info.get("psutil_present"))),
        ]
        recent = info.get("recent_baselines") or []
        if as_json:
            print(json.dumps({"ok": True, "readiness": "READY",
                              "items": [{"name": n, "ok": ok} for n, ok in rows],
                              "recent": recent, "hint": info.get("hint"),
                              "error": info.get("error")}, indent=2))
            return 0
        print("Bolt speed check (READY)")
        for name, ok in rows:
            print(f"  [{'OK' if ok else '--'}] {name}")
        if recent:
            print("  saved baselines (newest first):")
            for r in recent[:5]:
                when = (r.get("timestamp") or r.get("mtime") or "")[:16].replace("T", " ")
                if r.get("method") == _METHOD:
                    print(f"    - {r['name']}  {when}  Bolt startup {_ms(r.get('bolt_startup_sec'))}  · {r.get('verdict') or ''}")
                else:
                    print(f"    - {r['name']}  {when}  (old method — not comparable)")
        if info.get("error"):
            print(f"  → {info['error']}")
        print("  (run: bolt performance run [--quick] · last report: bolt performance last)")
        return 0
    except Exception as exc:
        msg = _soft(f"list failed ({exc})")
        print(json.dumps({"ok": False, "error": msg}, indent=2) if as_json else msg,
              file=sys.stdout if as_json else sys.stderr)
        return 0


def last_report(*, as_json: bool = False) -> int:
    """Print the newest saved report (no new run)."""
    recent = [r for r in _recent_baselines(20) if r.get("method") == _METHOD]
    if not recent:
        msg = _soft("no saved speed check yet — run: bolt performance run")
        print(json.dumps({"ok": False, "error": msg}, indent=2) if as_json else msg,
              file=sys.stdout if as_json else sys.stderr)
        return 0
    data = _load(Path(recent[0]["path"])) or {}
    if as_json:
        print(json.dumps(data, indent=2, default=str))
        return 0
    print(data.get("report") or "(report text missing)")
    print(f"\n  File: {recent[0]['path']}")
    return 0


def _engine_args(args: List[str]) -> List[str]:
    out: List[str] = []
    if "--quick" in args:
        out.append("--quick")
    if "--repeats" in args:
        i = args.index("--repeats")
        if i + 1 < len(args):
            out += ["--repeats", args[i + 1]]
    if "--no-save" in args:
        out.append("--no-save")
    return out


def try_run(*, as_json: bool = False, dry_run: bool = False,
            extra: Optional[List[str]] = None) -> int:
    """Soft-fail run of the engine (never raises)."""
    def fail(msg: str) -> int:
        msg = _soft(msg)
        if as_json:
            print(json.dumps({"ok": False, "error": msg, "readiness": "READY"}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0

    try:
        info = status(probe=False)
        if not info.get("ready"):
            return fail(info.get("error") or "speed check not ready")
        eargs = list(extra or [])
        if dry_run:
            payload = {"ok": True, "readiness": "READY", "dry_run": True,
                       "would_run": [str(_SCRIPT)] + eargs,
                       "results_dir": str(_RESULTS), "cwd": str(_REPO)}
            if as_json:
                print(json.dumps(payload, indent=2))
            else:
                print(f"[dry-run] would run: {_SCRIPT} {' '.join(eargs)}".rstrip())
                print(f"  results: {_RESULTS}  (takes ~5 s; --quick ~2 s)")
            return 0

        env = os.environ.copy()
        env["PYTHONPATH"] = str(_CORE) + (f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else "")
        cmd = [sys.executable, str(_SCRIPT)] + eargs + (["--json"] if as_json else [])
        try:
            proc = subprocess.run(cmd, cwd=str(_REPO), env=env, capture_output=as_json,
                                  text=True, timeout=_RUN_TIMEOUT)
        except subprocess.TimeoutExpired:
            return fail(f"speed check timed out after {_RUN_TIMEOUT}s")
        except Exception as exc:
            return fail(f"run failed ({exc})")
        if proc.returncode != 0:
            tail = (proc.stderr or "").strip()[-400:] if as_json else ""
            return fail(f"engine exited {proc.returncode}" + (f": {tail}" if tail else ""))
        if as_json:
            try:
                data = json.loads(proc.stdout)
            except Exception:
                return fail("engine output was not JSON")
            print(json.dumps({"ok": True, "readiness": "READY",
                              "output": data.get("saved_to"),
                              "summary": data.get("summary"),
                              "comparison": data.get("comparison"),
                              "report": data.get("report")}, indent=2, default=str))
        return 0
    except Exception as exc:
        return fail(f"run failed ({exc})")


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    try:
        info = status(probe=probe)
        if as_json:
            print(json.dumps(info, indent=2, default=str))
            return 0
        print("Bolt speed check (READY)")
        print(f"  ready: {info.get('ready')}")
        print(f"  engine: {info.get('script_present')} · Core: {info.get('core_present')} · "
              f"launch: {info.get('launch_present')} · bot: {info.get('bot_present')}")
        print(f"  results: {info.get('results_dir')} (writable={info.get('results_writable')}, "
              f"saved={info.get('recent_count')})")
        print(f"  psutil: {info.get('psutil_present')}"
              + ("" if info.get("psutil_present") else " (optional — memory numbers: uv pip install psutil)"))
        last = info.get("last_baseline") or {}
        if last.get("method") == _METHOD:
            print(f"  last check: {(last.get('timestamp') or '')[:16].replace('T', ' ')} — "
                  f"Bolt startup {_ms(last.get('bolt_startup_sec'))} — {last.get('verdict') or ''}")
        else:
            print("  last check: none in the new format yet — run: bolt performance run")
        print(f"  → {info.get('error') or info.get('hint')}")
        return 0
    except Exception as exc:
        print(_soft(f"status print failed ({exc})"), file=sys.stderr)
        return 0


_HELP = """bolt performance — Bolt speed check (READY)

  bolt performance                          # status (default)
  bolt performance status [--json]
  bolt performance run [--quick] [--repeats N] [--no-save] [--json] [--dry-run]
  bolt performance last [--json]            # show the newest saved report
  bolt performance list [--json]            # checklist + saved baselines

run: times Bolt startup, the `bolt` command, each Bolt module and big libraries
(torch, cv2, openai…) in fresh processes (median of 3; --quick = 1), compares
with the previous baseline (flags anything ≥50 ms AND ≥25% slower), and saves
logs/performance/baseline_YYYYMMDD_HHMMSS.json. ~5 s. Local only.
Soft-fail: "Baseline unavailable:". Distinct from bolt analytics / bolt stats.
Aliases: baseline, perf-baseline, performance-baseline
"""


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(_HELP)
        return 0
    json_out = "--json" in args
    probe = "--probe" in args
    dry_run = "--dry-run" in args or "--dryrun" in args
    cleaned: List[str] = []
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a == "--repeats":
            skip = True
            continue
        if not a.startswith("-"):
            cleaned.append(a)

    if not cleaned:
        return print_status(as_json=json_out, probe=probe)
    cmd = cleaned[0].lower()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "recent", "checklist"):
        return list_items(as_json=json_out)
    if cmd in ("last", "report", "show", "compare"):
        return last_report(as_json=json_out)
    if cmd in ("run", "baseline", "measure", "bench", "snapshot"):
        return try_run(as_json=json_out, dry_run=dry_run, extra=_engine_args(args))
    print(_soft(f"unknown command '{cmd}' — try status|run|last|list"), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
