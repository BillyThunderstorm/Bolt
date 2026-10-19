#!/usr/bin/env python3
"""
OBS_Game_Tracker.py — soft-fail CLI for OBS scene→config.json game auto-update (PARTIAL)
========================================================================================
Wraps ``scripts/update_game_from_obs.py`` (+ optional background helper
``scripts/start_obs_game_tracker.py``). Soft-fail prefix: ``Game tracker unavailable:``.

CLI (via ``bolt obs-game``):
  status [--json] [--probe]
  list
  run [--once] [--background]

Stay PARTIAL — OBS WebSocket / keys gate live use; not stranger-ready.
Distinct from READY ``bolt obs`` (WebSocket status/monitor) — this surface
auto-updates ``Core/config.json`` ``game`` from OBS scene mapping.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Game tracker unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_CORE = _REPO / "Core"
_ENGINE = _REPO / "scripts" / "update_game_from_obs.py"
_BG_HELPER = _REPO / "scripts" / "start_obs_game_tracker.py"
_PATHS = _REPO / "scripts" / "_paths.py"
_MAPPING = _REPO / "Data" / "configs" / "scene_game_mapping.json"
_CONFIG = _REPO / "Core" / "config.json"
_LOG = _REPO / "logs" / "obs_game_tracker.log"
_STREAM_MONITOR = _REPO / "Core" / "modules" / "Stream_Monitor.py"


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_paths() -> None:
    if str(_CORE) not in sys.path:
        sys.path.insert(0, str(_CORE))
    scripts = str(_REPO / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)


def _mapping_scene_count(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        scenes = raw.get("scenes", {}) if isinstance(raw, dict) else {}
        return len(scenes) if isinstance(scenes, dict) else 0
    except Exception:
        return 0


def _current_config_game(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return str(raw.get("game") or "")
    except Exception:
        return ""
    return ""


def _load_engine():
    _ensure_paths()
    if not _ENGINE.is_file():
        raise FileNotFoundError(f"missing engine {_ENGINE}")
    # Import as a file module via path bootstrap used by the script itself.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "update_game_from_obs", _ENGINE
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {_ENGINE}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def status(*, probe: bool = False) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "checked_at": _iso(),
        "ready": False,
        "partial": True,
        "readiness": "PARTIAL",
        "soft_fail_prefix": _SOFT,
        "cli": "bolt obs-game",
        "engine": str(_ENGINE),
        "engine_present": _ENGINE.is_file(),
        "bg_helper": str(_BG_HELPER),
        "bg_helper_present": _BG_HELPER.is_file(),
        "paths_helper": str(_PATHS),
        "paths_present": _PATHS.is_file(),
        "mapping": str(_MAPPING),
        "mapping_present": _MAPPING.is_file(),
        "mapping_scene_count": _mapping_scene_count(_MAPPING),
        "config": str(_CONFIG),
        "config_present": _CONFIG.is_file(),
        "config_game": _current_config_game(_CONFIG),
        "stream_monitor": str(_STREAM_MONITOR),
        "stream_monitor_present": _STREAM_MONITOR.is_file(),
        "stream_monitor_importable": False,
        "obs_summary": {},
        "probe": bool(probe),
        "probe_ok": None,
        "error": "",
        "hint": (
            "OBS scene→config.json game auto-update · "
            "distinct from READY bolt obs · "
            "bare bolt obs-game = status; bolt obs-game run starts the loop"
        ),
        "is_stranger_ready": False,
    }

    missing = []
    if not info["engine_present"]:
        missing.append("scripts/update_game_from_obs.py")
    if not info["paths_present"]:
        missing.append("scripts/_paths.py")
    if not info["mapping_present"]:
        missing.append("Data/configs/scene_game_mapping.json")
    if not info["config_present"]:
        missing.append("Core/config.json")
    if missing:
        info["error"] = _soft("missing " + ", ".join(missing))
        # still report what we can; ready only when engine+mapping+config present
        info["ready"] = False
        # Continue to fill optional OBS summary below when possible
    else:
        info["ready"] = True

    # Stream_Monitor importability (soft)
    try:
        _ensure_paths()
        from modules import Stream_Monitor as sm  # noqa: WPS433

        info["stream_monitor_importable"] = True
        # Cheap OBS settings summary (no hang)
        try:
            obs_st = sm.status(probe=False)
            info["obs_summary"] = {
                "has_websocket_client": obs_st.get("has_websocket_client"),
                "use_obs_integration": obs_st.get("use_obs_integration"),
                "password_set": obs_st.get("password_set"),
                "host": obs_st.get("host"),
                "port": obs_st.get("port"),
                "hint": (obs_st.get("hint") or "")[:120],
            }
        except Exception as exc:
            info["obs_summary"] = {"error": _soft(str(exc) or type(exc).__name__)}
    except Exception as exc:
        info["stream_monitor_importable"] = False
        if not info["error"]:
            info["hint"] = _soft(
                f"Stream_Monitor import failed ({exc}); engine paths still ok"
            )

    if probe:
        try:
            _ensure_paths()
            from modules.Stream_Monitor import probe_obs  # noqa: WPS433

            p = probe_obs(timeout=2.0)
            info["probe_ok"] = bool(p.get("ok"))
            info["obs_summary"] = {
                **(info.get("obs_summary") or {}),
                "probe_ok": p.get("ok"),
                "probe_reachable": p.get("reachable"),
                "probe_detail": (p.get("detail") or "")[:160],
            }
            if not p.get("ok"):
                # Soft advisory — do not clear ready (files present)
                info["hint"] = p.get("detail") or _soft(
                    "OBS probe failed (open OBS + WebSocket + OBS_PASSWORD)"
                )
        except Exception as exc:
            info["probe_ok"] = False
            info["hint"] = _soft(str(exc) or type(exc).__name__)

    # Game freshness (Game_Refresh; soft) — warns when config game is stale
    try:
        _ensure_paths()
        from modules.Game_Refresh import freshness as _gr_fresh  # noqa: WPS433

        info["game_freshness"] = _gr_fresh()
    except Exception as exc:
        info["game_freshness"] = {"error": _soft(f"freshness unavailable ({exc})")}

    # Engine import smoke (does not start the loop)
    if info["engine_present"] and info["paths_present"]:
        try:
            mod = _load_engine()
            cfg = getattr(mod, "CONFIG_FILE", None)
            mp = getattr(mod, "MAPPING_FILE", None)
            info["engine_config"] = str(cfg) if cfg else ""
            info["engine_mapping"] = str(mp) if mp else ""
            # Sanity: engine should point at post-reorg paths
            if cfg and Path(cfg) != _CONFIG:
                info["hint"] = _soft(
                    f"engine CONFIG_FILE points at {cfg} (expected {_CONFIG})"
                )
            if mp and Path(mp) != _MAPPING:
                info["hint"] = _soft(
                    f"engine MAPPING_FILE points at {mp} (expected {_MAPPING})"
                )
            if not hasattr(mod, "start_game_tracker") and not hasattr(mod, "main"):
                info["ready"] = False
                info["error"] = _soft("engine missing main/start_game_tracker")
        except Exception as exc:
            info["ready"] = False
            info["error"] = _soft(str(exc) or type(exc).__name__)

    return info


def list_items() -> List[Dict[str, Any]]:
    st = status(probe=False)
    rows: List[Dict[str, Any]] = [
        {"id": "engine", "ok": st["engine_present"], "detail": st["engine"]},
        {
            "id": "mapping",
            "ok": st["mapping_present"],
            "detail": (
                f"{st['mapping']} present={st['mapping_present']} "
                f"scenes={st['mapping_scene_count']}"
            ),
        },
        {
            "id": "config",
            "ok": st["config_present"],
            "detail": (
                f"{st['config']} present={st['config_present']} "
                f"game={st.get('config_game')!r}"
            ),
        },
        {
            "id": "stream_monitor",
            "ok": bool(st.get("stream_monitor_importable")),
            "detail": (
                f"{st['stream_monitor']} "
                f"importable={st.get('stream_monitor_importable')}"
            ),
        },
        {
            "id": "bg_helper",
            "ok": st["bg_helper_present"],
            "detail": st["bg_helper"],
        },
        {
            "id": "paths",
            "ok": st["paths_present"],
            "detail": st["paths_helper"],
        },
        {
            "id": "soft_fail",
            "ok": True,
            "detail": f"prefix {_SOFT!r}; stay PARTIAL; is_stranger_ready=False",
        },
        {
            "id": "distinct",
            "ok": True,
            "detail": (
                "distinct from READY bolt obs (WebSocket status/monitor) — "
                "this auto-updates Core/config.json game from OBS scenes"
            ),
        },
        {
            "id": "twitch_sentinel",
            "ok": True,
            "detail": (
                "mapping may use __twitch__ → Helix live game "
                "(soft-fail if Twitch unreachable)"
            ),
        },
    ]
    obs = st.get("obs_summary") or {}
    if obs:
        rows.append(
            {
                "id": "obs_settings",
                "ok": True,
                "detail": (
                    f"host={obs.get('host')}:{obs.get('port')} "
                    f"ws_client={obs.get('has_websocket_client')} "
                    f"password_set={obs.get('password_set')} "
                    f"use_obs={obs.get('use_obs_integration')}"
                ),
            }
        )
    if st.get("error"):
        rows.append({"id": "error", "ok": False, "detail": st["error"]})
    return rows


def try_run(
    *,
    once: bool = False,
    background: bool = False,
) -> Dict[str, Any]:
    """Start tracker loop, dry readiness (--once), or background spawn."""
    out: Dict[str, Any] = {
        "ok": False,
        "error": "",
        "exit_code": 0,
        "report": "",
    }
    st = status(probe=False)
    if once:
        # Dry readiness — never connect forever
        lines = [
            f"[OBS game tracker] dry readiness (--once)",
            f"  mapping: {st.get('mapping')} present={st.get('mapping_present')} "
            f"scenes={st.get('mapping_scene_count')}",
            f"  config:  {st.get('config')} game={st.get('config_game')!r}",
            f"  engine:  present={st.get('engine_present')} ready={st.get('ready')}",
        ]
        obs = st.get("obs_summary") or {}
        if obs:
            hint = obs.get("hint") or ""
            lines.append(
                f"  obs:     host={obs.get('host')}:{obs.get('port')} "
                f"password_set={obs.get('password_set')} "
                f"ws_client={obs.get('has_websocket_client')}"
            )
            if hint:
                lines.append(f"  obs_hint:{hint}")
        else:
            lines.append("  obs:     (no Stream_Monitor summary)")
        if st.get("error"):
            lines.append(f"  {st['error']}")
            out["error"] = st["error"]
            out["ok"] = False
        else:
            out["ok"] = True
        out["report"] = "\n".join(lines) + "\n"
        return out

    if not st.get("ready"):
        out["error"] = st.get("error") or _soft("not ready")
        return out

    if background:
        try:
            if not _BG_HELPER.is_file():
                out["error"] = _soft(f"missing background helper {_BG_HELPER}")
                return out
            _LOG.parent.mkdir(parents=True, exist_ok=True)
            # Prefer helper script (writes logs/obs_game_tracker.log)
            proc = subprocess.Popen(
                [sys.executable, str(_BG_HELPER)],
                cwd=str(_REPO),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                stdout, _ = proc.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                # Helper should exit quickly after spawning; if not, soft-ok
                stdout = "(helper still running — check logs/obs_game_tracker.log)"
            out["ok"] = True
            out["report"] = (
                f"[OBS game tracker] background start via {_BG_HELPER.name}\n"
                f"  log: {_LOG}\n"
                f"{stdout or ''}"
            )
            return out
        except Exception as exc:
            out["ok"] = False
            out["error"] = _soft(str(exc) or type(exc).__name__)
            out["traceback"] = traceback.format_exc(limit=3)
            return out

    # Foreground long-running loop via engine main/start_game_tracker
    try:
        mod = _load_engine()
        runner = getattr(mod, "start_game_tracker", None) or getattr(mod, "main", None)
        if runner is None:
            out["error"] = _soft("engine missing main/start_game_tracker")
            return out
        out["ok"] = True
        out["report"] = (
            "[OBS game tracker] starting foreground loop (Ctrl+C to stop)\n"
        )
        sys.stdout.write(out["report"])
        sys.stdout.flush()
        try:
            runner()
        except KeyboardInterrupt:
            msg = "\n[OBS game tracker] stopped (KeyboardInterrupt)\n"
            sys.stdout.write(msg)
            out["report"] += msg
            out["ok"] = True
        return out
    except Exception as exc:
        out["ok"] = False
        out["error"] = _soft(str(exc) or type(exc).__name__)
        out["traceback"] = traceback.format_exc(limit=3)
        out["exit_code"] = 0
        return out


def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, indent=2))
    else:
        ready = "yes" if info.get("ready") else "no"
        print(f"obs-game readiness: {info.get('readiness')}  ready={ready}")
        print(f"  engine:   {_ENGINE}  present={info.get('engine_present')}")
        print(
            f"  mapping:  {_MAPPING}  present={info.get('mapping_present')} "
            f"scenes={info.get('mapping_scene_count')}"
        )
        print(
            f"  config:   {_CONFIG}  present={info.get('config_present')} "
            f"game={info.get('config_game')!r}"
        )
        print(
            f"  monitor:  importable={info.get('stream_monitor_importable')} "
            f"present={info.get('stream_monitor_present')}"
        )
        obs = info.get("obs_summary") or {}
        if obs:
            print(
                f"  obs:      {obs.get('host')}:{obs.get('port')} "
                f"password_set={obs.get('password_set')} "
                f"ws_client={obs.get('has_websocket_client')}"
            )
        fr = info.get("game_freshness") or {}
        if fr.get("stale"):
            print(f"  WARNING game stale: {fr.get('reason')} — {fr.get('fix')}")
        elif fr.get("reason"):
            print(f"  freshness: {fr.get('reason')}")
        if info.get("probe"):
            print(f"  probe_ok: {info.get('probe_ok')}")
        if info.get("error"):
            print(f"  {info['error']}")
        else:
            print(f"  hint: {info.get('hint')}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="bolt obs-game",
        description=(
            "OBS scene→config.json game tracker readiness / list / run "
            "(PARTIAL; soft-fail)."
        ),
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
        help="status only: short OBS WebSocket probe (soft-fail, no hang)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="run: dry readiness print (no long connect)",
    )
    parser.add_argument(
        "--background",
        action="store_true",
        help="run: spawn via start_obs_game_tracker.py → logs/obs_game_tracker.log",
    )
    args = parser.parse_args(argv)

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
        result = try_run(once=args.once, background=args.background)
        if result.get("error") and not result.get("ok"):
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(result["error"])
            return 0
        if args.json:
            print(
                json.dumps(
                    {
                        "ok": result.get("ok"),
                        "error": result.get("error"),
                        "once": bool(args.once),
                        "background": bool(args.background),
                        "report": (result.get("report") or "")[:2000],
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
