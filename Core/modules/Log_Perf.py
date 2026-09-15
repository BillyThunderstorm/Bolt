#!/usr/bin/env python3
"""
Log_Perf.py — soft-fail CLI for scripts/log_clip_performance.py (PARTIAL)
=======================================================================
Manual clip performance logger for the learning loop (views/likes →
Data/performance_outcomes.jsonl + Clip_Ranker history). Soft-fail prefix:
``Log perf unavailable:``.

CLI (via ``bolt log-perf`` / ``bolt log_perf``):
  status [--json] [--probe]
  list   [--json]
  run    [--trigger T --views N ...]   # or --list; bare run = interactive

Stay PARTIAL — manual / interactive learning input; distinct from READY
``bolt stats`` (YouTube/TikTok API pull via Social_Stats / Performance_Sync).
While TikTok API is paused, this is the TT/X manual path.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Log perf unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_ENGINE = _REPO / "scripts" / "log_clip_performance.py"
_PATHS = _REPO / "scripts" / "_paths.py"
_RANK = _REPO / "Core" / "modules" / "Clip_Ranker.py"
_OUTCOMES = _REPO / "Data" / "performance_outcomes.jsonl"
_HISTORY = _REPO / "Data" / "clip_history.json"
_CORE = _REPO / "Core"


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _outcomes_count() -> int:
    if not _OUTCOMES.is_file():
        return 0
    try:
        n = 0
        with _OUTCOMES.open(encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.strip():
                    n += 1
        return n
    except Exception:
        return 0


def status(*, probe: bool = False) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "checked_at": _iso(),
        "ready": False,
        "partial": True,
        "readiness": "PARTIAL",
        "soft_fail_prefix": _SOFT,
        "cli": "bolt log-perf",
        "engine": str(_ENGINE),
        "engine_present": _ENGINE.is_file(),
        "paths_helper": str(_PATHS),
        "paths_present": _PATHS.is_file(),
        "clip_ranker": str(_RANK),
        "clip_ranker_present": _RANK.is_file(),
        "outcomes_path": str(_OUTCOMES),
        "outcomes_present": _OUTCOMES.is_file(),
        "outcomes_count": _outcomes_count(),
        "history_path": str(_HISTORY),
        "history_present": _HISTORY.is_file(),
        "probe": bool(probe),
        "probe_ok": None,
        "error": "",
        "hint": (
            "manual TT/X learning logger · distinct from READY bolt stats "
            "(API sync) · TikTok API paused → use this after posting"
        ),
        "is_stranger_ready": False,
    }
    missing = []
    if not info["engine_present"]:
        missing.append("scripts/log_clip_performance.py")
    if not info["paths_present"]:
        missing.append("scripts/_paths.py")
    if missing:
        info["error"] = _soft("missing " + ", ".join(missing))
        return info

    # Clip_Ranker is preferred but not hard-required for append-only log.
    if not info["clip_ranker_present"]:
        info["hint"] = _soft(
            "Clip_Ranker missing — outcomes may still append; ranker boost skipped"
        )

    info["ready"] = True
    if probe:
        try:
            # Import engine lightly: ensure _paths + module load without running main.
            scripts = str(_REPO / "scripts")
            if scripts not in sys.path:
                sys.path.insert(0, scripts)
            if str(_CORE) not in sys.path:
                sys.path.insert(0, str(_CORE))
            spec = importlib.util.spec_from_file_location("bolt_log_perf_engine", _ENGINE)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load {_ENGINE}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            info["probe_ok"] = True
            info["engine_has_list"] = callable(getattr(mod, "list_recent", None))
            info["engine_has_log"] = callable(
                getattr(mod, "log_performance", None)
            ) or callable(getattr(mod, "_record_learning_outcome", None))
        except Exception as exc:
            info["probe_ok"] = False
            info["ready"] = False
            info["error"] = _soft(str(exc) or type(exc).__name__)
    return info


def list_items() -> List[Dict[str, Any]]:
    st = status(probe=False)
    return [
        {"id": "engine", "ok": st["engine_present"], "detail": st["engine"]},
        {"id": "paths", "ok": st["paths_present"], "detail": st["paths_helper"]},
        {
            "id": "clip_ranker",
            "ok": st["clip_ranker_present"],
            "detail": st["clip_ranker"] + (" (optional boost)" if st["clip_ranker_present"] else " (missing — soft)"),
        },
        {
            "id": "outcomes",
            "ok": True,
            "detail": f"{st['outcomes_path']} count={st['outcomes_count']} present={st['outcomes_present']}",
        },
        {
            "id": "history",
            "ok": True,
            "detail": f"{st['history_path']} present={st['history_present']}",
        },
        {
            "id": "soft_fail",
            "ok": True,
            "detail": f"prefix {_SOFT!r}; stay PARTIAL; distinct from bolt stats",
        },
        {
            "id": "tiktok_note",
            "ok": True,
            "detail": "TikTok API paused — manual log-perf is the TT/X path",
        },
    ]


def try_run(argv: Optional[List[str]] = None) -> Dict[str, Any]:
    """Run the engine with argv (engine flags). Soft-fails instead of raising."""
    out: Dict[str, Any] = {
        "ok": False,
        "error": "",
        "exit_code": 0,
        "report": "",
    }
    st = status(probe=False)
    if not st.get("engine_present"):
        out["error"] = st.get("error") or _soft("engine missing")
        return out
    argv = list(argv or [])
    py = sys.executable
    cmd = [py, str(_ENGINE)] + argv
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    # Ensure Core on PYTHONPATH for modules.Clip_Ranker
    pp = env.get("PYTHONPATH", "")
    core = str(_CORE)
    env["PYTHONPATH"] = core if not pp else f"{core}:{pp}"
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(_REPO),
            env=env,
            capture_output=True,
            text=True,
        )
        out["exit_code"] = int(proc.returncode or 0)
        out["report"] = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            # Soft-fail: surface message, exit 0 to caller of status-like flows;
            # for run we still return engine code but wrap errors.
            err_txt = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
            if "Error" in err_txt or "Traceback" in err_txt or proc.returncode != 0:
                out["error"] = _soft(err_txt.splitlines()[-1][:200])
                out["ok"] = False
                out["exit_code"] = 0  # soft-fail
            else:
                out["ok"] = True
        else:
            out["ok"] = True
    except Exception as exc:
        out["ok"] = False
        out["error"] = _soft(str(exc) or type(exc).__name__)
        out["exit_code"] = 0
    return out


def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, indent=2))
    else:
        ready = "yes" if info.get("ready") else "no"
        print(f"log-perf readiness: {info.get('readiness')}  ready={ready}")
        print(f"  engine:  {_ENGINE}  present={info.get('engine_present')}")
        print(f"  ranker:  {_RANK}  present={info.get('clip_ranker_present')}")
        print(
            f"  outcomes: {_OUTCOMES}  present={info.get('outcomes_present')} "
            f"count={info.get('outcomes_count')}"
        )
        if info.get("probe"):
            print(f"  probe_ok: {info.get('probe_ok')}")
        if info.get("error"):
            print(f"  {info['error']}")
        else:
            print(f"  hint: {info.get('hint')}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Back-compat: bolt log_perf --trigger … / --list / --views … (no action word)
    if argv and argv[0] not in ("status", "list", "run", "-h", "--help"):
        if argv[0].startswith("-"):
            argv = ["run"] + argv

    parser = argparse.ArgumentParser(
        prog="bolt log-perf",
        description="Manual clip performance logger (PARTIAL; soft-fail).",
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "list", "run"],
        help="status (default) | list | run",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="status only: import engine and verify load",
    )
    # Everything after 'run' goes to the engine (parse_known / remainder).
    args, rest = parser.parse_known_args(argv)

    if args.action == "status":
        return _print_status(status(probe=args.probe), args.json)

    if args.action == "list":
        rows = list_items()
        if args.json:
            print(json.dumps({"items": rows}, indent=2))
        else:
            for r in rows:
                mark = "OK" if r["ok"] else "NO"
                print(f"[{mark}] {r['id']}: {r['detail']}")
        return 0

    if args.action == "run":
        # Drop a lone --json meant for wrapper if present without engine meaning
        engine_argv = list(rest)
        result = try_run(engine_argv)
        if result.get("error") and not result.get("ok"):
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(result["error"])
                if result.get("report") and "Traceback" not in (result.get("report") or ""):
                    # still show engine stdout when useful
                    txt = (result.get("report") or "").strip()
                    if txt and txt not in result["error"]:
                        print(txt)
            return 0
        if args.json:
            print(
                json.dumps(
                    {
                        "ok": result.get("ok"),
                        "exit_code": result.get("exit_code"),
                        "report": result.get("report"),
                    },
                    indent=2,
                )
            )
        else:
            sys.stdout.write(result.get("report") or "")
        return int(result.get("exit_code") or 0)

    print(_soft(f"unknown action {args.action!r}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
