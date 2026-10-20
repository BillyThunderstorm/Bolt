#!/usr/bin/env python3
"""
Log_Perf.py — `bolt log-perf`: log how a posted clip did (READY)
================================================================
Manual performance logger for the learning loop. Use it after you post a clip
by hand (TikTok API is paused; X / Instagram / Kick have no pull either):

  bolt log-perf run --clip 929da53e --views 2.5k --likes 140
  bolt log-perf run --clip Hands --views 2400 --platform tiktok --dry-run
  bolt log-perf run --list [--manual]      # recent rows
  bolt log-perf run --history              # trigger table Clip_Ranker uses
  bolt log-perf run                        # interactive (terminal)

`--clip` takes a queue id, filename, stem or path and fills in the trigger,
game and title from the queue / clip sidecar. Re-logging the same clip on the
same platform updates its row (no double counting in the weekly report or in
Clip_Ranker's averages). Rows land in Data/performance_outcomes.jsonl and feed
Data/clip_history.json, the decision engine and the memory index.

Soft-fail prefix: ``Log perf unavailable:``. Distinct from READY ``bolt stats``
(YouTube API pull via Social_Stats / Performance_Sync).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
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
_CONFIG = _REPO / "Core" / "config.json"
_CORE = _REPO / "Core"


def _soft(msg: str) -> str:
    return msg if msg.startswith(_SOFT) else f"{_SOFT} {msg}"


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rows() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not _OUTCOMES.is_file():
        return out
    try:
        with _OUTCOMES.open(encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except Exception:
        return []
    return out


def _outcomes_count() -> int:
    return len(_rows())


def _config_game() -> str:
    try:
        return str(json.loads(_CONFIG.read_text(encoding="utf-8")).get("game") or "")
    except Exception:
        return ""


def status(*, probe: bool = False) -> Dict[str, Any]:
    rows = _rows()
    manual = [r for r in rows if r.get("source") != "youtube_api"]
    last = max(manual, key=lambda r: str(r.get("timestamp") or ""), default={})
    info: Dict[str, Any] = {
        "checked_at": _iso(),
        "ready": False,
        "partial": False,
        "readiness": "READY",
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
        "outcomes_count": len(rows),
        "manual_count": len(manual),
        "last_manual": (
            {k: last.get(k) for k in ("timestamp", "platform", "game", "trigger", "views", "title")}
            if last else None
        ),
        "history_path": str(_HISTORY),
        "history_present": _HISTORY.is_file(),
        "game": _config_game(),
        "probe": bool(probe),
        "probe_ok": None,
        "error": "",
        "hint": (
            "after posting: bolt log-perf run --clip <queue id|name> --views N "
            "[--likes N --platform tiktok|x|instagram|kick] · re-log updates the row · "
            "distinct from READY bolt stats (YouTube API)"
        ),
        "is_stranger_ready": True,
    }
    missing = []
    if not info["engine_present"]:
        missing.append("scripts/log_clip_performance.py")
    if not info["paths_present"]:
        missing.append("scripts/_paths.py")
    if missing:
        info["error"] = _soft("missing " + ", ".join(missing))
        return info
    if not info["clip_ranker_present"]:
        info["hint"] = _soft("Clip_Ranker missing — rows still save; ranker boost skipped")

    info["ready"] = True
    if probe:
        try:
            for p in (str(_REPO / "scripts"), str(_CORE)):
                if p not in sys.path:
                    sys.path.insert(0, p)
            spec = importlib.util.spec_from_file_location("bolt_log_perf_engine", _ENGINE)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load {_ENGINE}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            info["engine_has_list"] = callable(getattr(mod, "list_recent", None))
            info["engine_has_log"] = callable(getattr(mod, "log_clip", None))
            info["clip_ranker_importable"] = getattr(mod, "update_historical_performance", None) is not None
            info["probe_ok"] = bool(info["engine_has_log"])
            if not info["probe_ok"]:
                raise ImportError("engine has no log_clip()")
        except Exception as exc:
            info["probe_ok"] = False
            info["ready"] = False
            info["error"] = _soft(str(exc) or type(exc).__name__)
    return info


def list_items() -> List[Dict[str, Any]]:
    st = status(probe=False)
    last = st.get("last_manual") or {}
    return [
        {"id": "engine", "ok": st["engine_present"], "detail": st["engine"]},
        {"id": "paths", "ok": st["paths_present"], "detail": st["paths_helper"]},
        {"id": "clip_ranker", "ok": st["clip_ranker_present"],
         "detail": st["clip_ranker"] + (" (trigger boost)" if st["clip_ranker_present"] else " (missing — soft)")},
        {"id": "outcomes", "ok": True,
         "detail": f"{st['outcomes_path']} rows={st['outcomes_count']} manual={st['manual_count']}"},
        {"id": "last_manual", "ok": True,
         "detail": (f"{str(last.get('timestamp'))[:10]} {last.get('platform')} {last.get('views')} views "
                    f"({last.get('title') or last.get('trigger')})") if last else "none yet"},
        {"id": "history", "ok": True, "detail": f"{st['history_path']} present={st['history_present']}"},
        {"id": "game", "ok": bool(st.get("game")), "detail": f"default game {st.get('game')!r} (Core/config.json)"},
        {"id": "tiktok_note", "ok": True, "detail": "TikTok API paused — log TikTok/X/IG/Kick views here after posting"},
    ]


def _engine_env() -> Dict[str, str]:
    env = dict(os.environ)
    pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(_CORE) if not pp else f"{_CORE}:{pp}"
    return env


def try_run(argv: Optional[List[str]] = None, *, capture: bool = True) -> Dict[str, Any]:
    """Run the engine. capture=False hands it the terminal (interactive mode)."""
    out: Dict[str, Any] = {"ok": False, "error": "", "exit_code": 0, "report": ""}
    st = status(probe=False)
    if not st.get("engine_present"):
        out["error"] = st.get("error") or _soft("engine missing")
        return out
    cmd = [sys.executable, str(_ENGINE)] + list(argv or [])
    try:
        if capture:
            proc = subprocess.run(cmd, cwd=str(_REPO), env=_engine_env(),
                                  capture_output=True, text=True, stdin=subprocess.DEVNULL)
            out["report"] = (proc.stdout or "") + (proc.stderr or "")
        else:
            proc = subprocess.run(cmd, cwd=str(_REPO), env=_engine_env())
        out["exit_code"] = int(proc.returncode or 0)
        if proc.returncode == 0:
            out["ok"] = True
        else:
            txt = out["report"].strip().splitlines()
            soft = [ln for ln in txt if ln.startswith(_SOFT)]
            out["error"] = soft[-1] if soft else (_soft(txt[-1][:200]) if txt else _soft(f"exit {proc.returncode}"))
    except Exception as exc:
        out["error"] = _soft(str(exc) or type(exc).__name__)
        out["exit_code"] = 1
    return out


def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, indent=2))
        return 0
    ready = "yes" if info.get("ready") else "no"
    print(f"log-perf readiness: {info.get('readiness')}  ready={ready}")
    print(f"  engine:   {_ENGINE}  present={info.get('engine_present')}")
    print(f"  ranker:   {_RANK}  present={info.get('clip_ranker_present')}")
    print(f"  outcomes: {_OUTCOMES}  rows={info.get('outcomes_count')} manual={info.get('manual_count')}")
    last = info.get("last_manual")
    if last:
        print(f"  last manual: {str(last.get('timestamp'))[:16]} {last.get('platform')} · "
              f"{last.get('views')} views · {last.get('title') or last.get('trigger')}")
    print(f"  default game: {info.get('game') or '?'} (clip's own game wins when known)")
    if info.get("probe"):
        print(f"  probe_ok: {info.get('probe_ok')}")
    print(f"  {info['error']}" if info.get("error") else f"  hint: {info.get('hint')}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ("status", "list", "run", "-h", "--help") and argv[0].startswith("-"):
        argv = ["run"] + argv

    parser = argparse.ArgumentParser(prog="bolt log-perf",
                                     description="Log how a posted clip did (READY; soft-fail).")
    parser.add_argument("action", nargs="?", default="status", choices=["status", "list", "run"])
    parser.add_argument("--probe", action="store_true", help="status only: load the engine")
    args, rest = parser.parse_known_args(argv)
    as_json = "--json" in rest

    if args.action == "status":
        return _print_status(status(probe=args.probe), as_json)

    if args.action == "list":
        rows = list_items()
        if as_json:
            print(json.dumps({"items": rows}, indent=2))
        else:
            for r in rows:
                print(f"[{'OK' if r['ok'] else 'NO'}] {r['id']}: {r['detail']}")
        return 0

    # run → engine. Interactive / plain output goes straight to the terminal.
    result = try_run(rest, capture=as_json)
    if as_json:
        if result.get("ok"):
            sys.stdout.write(result.get("report") or "")
        else:
            print(json.dumps({"ok": False, "error": result.get("error")}, indent=2))
        return 0
    if not result.get("ok") and result.get("exit_code") not in (1, 2):
        print(result.get("error") or _soft("engine failed"))
    # Engine already printed its own soft-fail line for exit 2; keep bolt's exit 0.
    return 0


if __name__ == "__main__":
    sys.exit(main())
