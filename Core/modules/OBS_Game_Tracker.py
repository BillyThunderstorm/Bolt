#!/usr/bin/env python3
"""
OBS_Game_Tracker.py — `bolt obs-game`: keep Core/config.json "game" in step with OBS (READY)
===========================================================================================
Engine: ``scripts/update_game_from_obs.py`` (background helper
``scripts/start_obs_game_tracker.py``). Mapping:
``Data/configs/scene_game_mapping.json`` (``__twitch__`` = use the Twitch
channel's game). Soft-fail prefix: ``Game tracker unavailable:``.

CLI (via ``bolt obs-game``):
  status [--json] [--no-obs]   OBS scene, mapped game, config game, match?
  list   [--json]              mapping + which OBS scenes are mapped
  run    [--dry-run] [--json]  one real sync now (dry-run = show only)
  run --watch                  follow scene changes until Ctrl+C
  run --background             same, as a background process (logs/)
  stop                         stop the background tracker

Logs: logs/obs_game_tracker.jsonl (every sync), logs/obs_game_tracker.log
(watch / background). Never changes OBS scenes, settings, stream or recording.
Distinct from READY ``bolt obs`` (WebSocket status) and ``bolt game``
(Twitch-based refresh / pin).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
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
_JSONL = _REPO / "logs" / "obs_game_tracker.jsonl"
_PID = _REPO / "logs" / "obs_game_tracker.pid"

_ENGINE_MOD = None


def _soft(msg: str) -> str:
    return msg if msg.startswith(_SOFT) else f"{_SOFT} {msg}"


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_engine():
    global _ENGINE_MOD
    if _ENGINE_MOD is not None:
        return _ENGINE_MOD
    for p in (str(_CORE), str(_REPO / "scripts")):
        if p not in sys.path:
            sys.path.insert(0, p)
    if not _ENGINE.is_file():
        raise FileNotFoundError(f"missing {_ENGINE.relative_to(_REPO)}")
    spec = importlib.util.spec_from_file_location("update_game_from_obs", _ENGINE)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {_ENGINE}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _ENGINE_MOD = mod
    return mod


def _bg_pid() -> Optional[int]:
    try:
        pid = int(_PID.read_text().strip())
        os.kill(pid, 0)
        return pid
    except Exception:
        return None


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness + (probe=True) live OBS scene / mapped game / match. Never raises."""
    info: Dict[str, Any] = {
        "checked_at": _iso(), "readiness": "READY", "ready": False, "partial": False,
        "soft_fail_prefix": _SOFT, "cli": "bolt obs-game",
        "engine_present": _ENGINE.is_file(), "paths_present": _PATHS.is_file(),
        "mapping": str(_MAPPING), "mapping_present": _MAPPING.is_file(), "mapping_scene_count": 0,
        "config": str(_CONFIG), "config_present": _CONFIG.is_file(), "config_game": "",
        "obs_checked": bool(probe), "obs_ok": None, "probe_ok": None,
        "obs_scene": "", "mapped_value": "", "mapped_game": "", "matched_by": "",
        "match": None, "background_pid": _bg_pid(),
        "error": "", "fix": "", "hint": "",
        "log": str(_JSONL),
    }
    missing = [n for n, ok in (("scripts/update_game_from_obs.py", info["engine_present"]),
                               ("scripts/_paths.py", info["paths_present"]),
                               ("Data/configs/scene_game_mapping.json", info["mapping_present"]),
                               ("Core/config.json", info["config_present"])) if not ok]
    if missing:
        info["error"] = _soft("missing " + ", ".join(missing))
        info["fix"] = "Restore the missing file(s) from git or Data/backups/."
        return info
    try:
        eng = _load_engine()
        info["config_game"] = eng.current_config_game()
        mapping = eng.load_mapping()
        info["mapping_scene_count"] = len(mapping.get("scenes") or {})
        s = eng.obs_settings()
        info["obs_summary"] = {"host": s["host"], "port": s["port"], "password_set": s["password_set"],
                               "use_obs_integration": s["use_obs_integration"]}
        info["ready"] = True
    except Exception as exc:
        info["error"] = _soft(str(exc) or type(exc).__name__)
        info["fix"] = "Check Data/configs/scene_game_mapping.json and Core/config.json are valid JSON."
        return info
    try:
        from modules.Game_Refresh import freshness as _fr  # noqa: WPS433
        info["game_freshness"] = _fr()
    except Exception as exc:
        info["game_freshness"] = {"error": f"freshness unavailable ({exc})"}

    if not probe:
        info["hint"] = "bolt obs-game status shows the live OBS scene; bolt obs-game run syncs once"
        return info

    snap = eng.obs_snapshot()
    info["obs_ok"] = info["probe_ok"] = bool(snap["ok"])
    if not snap["ok"]:
        info["error"] = _soft(snap["error"])
        info["fix"] = snap["fix"]
        return info
    info["obs_scene"] = snap["scene"]
    value, key, how = eng.lookup_scene(snap["scene"], mapping)
    info["matched_by"] = how
    if value is None:
        info["hint"] = (f"scene {snap['scene']!r} isn't mapped, so the game stays as is. "
                        f"Add it to Data/configs/scene_game_mapping.json to track it.")
        return info
    info["mapped_value"] = value
    if value == eng.TWITCH_LIVE_SENTINEL:
        tw = eng._twitch_game()
        info["mapped_game"] = tw.get("game") or ""
        if not tw.get("game"):
            info["hint"] = f"scene maps to Twitch, but Twitch gave no game ({tw.get('error')}); run would keep the game."
    else:
        info["mapped_game"] = value
    if info["mapped_game"]:
        info["match"] = info["mapped_game"] == info["config_game"]
        info["hint"] = ("config game matches OBS" if info["match"]
                        else "differs — bolt obs-game run will update config.json")
    return info


def list_items(*, check_obs: bool = True) -> Dict[str, Any]:
    out: Dict[str, Any] = {"mapping": {}, "obs_scenes": [], "obs_error": "", "obs_fix": "", "error": ""}
    try:
        eng = _load_engine()
        mapping = eng.load_mapping()
    except Exception as exc:
        out["error"] = _soft(str(exc))
        return out
    out["mapping"] = dict(mapping.get("scenes") or {})
    out["live_scene"] = mapping.get("live_scene") or "Live Scene"
    if check_obs:
        snap = eng.obs_snapshot(scene_list=True)
        if snap["ok"]:
            for name in snap["scenes"]:
                value, key, how = eng.lookup_scene(name, mapping)
                out["obs_scenes"].append({"scene": name, "current": name == snap["scene"],
                                          "maps_to": value, "via_key": key, "matched_by": how})
        else:
            out["obs_error"], out["obs_fix"] = _soft(snap["error"]), snap["fix"]
    return out


def try_run(*, dry_run: bool = False, watch: bool = False, background: bool = False) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": False, "error": "", "fix": "", "report": ""}
    try:
        eng = _load_engine()
    except Exception as exc:
        out["error"] = _soft(str(exc))
        return out
    if background:
        try:
            p = subprocess.run([sys.executable, str(_BG_HELPER)], cwd=str(_REPO),
                               capture_output=True, text=True, timeout=10)
            out["ok"] = True
            out["report"] = (p.stdout or "") + (p.stderr or "")
        except Exception as exc:
            out["error"] = _soft(f"could not start background tracker ({exc})")
        return out
    if watch:
        out["ok"] = True
        eng.main()
        return out
    r = eng.sync_once(dry_run=dry_run, trigger="run_dry" if dry_run else "run")
    out["result"] = r
    if not r.get("ok"):
        out["error"] = _soft(r.get("error") or "sync failed")
        out["fix"] = r.get("fix") or ""
        return out
    out["ok"] = True
    tag = "dry run — nothing written" if dry_run else ("updated" if r.get("changed") else "no change")
    lines = [f"[OBS game tracker] {tag}",
             f"  OBS scene:   {r.get('scene')!r}"
             + (f"  (matched mapping key {r.get('matched_key')!r})" if r.get("matched_by") == "loose" else ""),
             f"  maps to:     {r.get('mapped_value') or '(not mapped)'}"
             + (f" → {r.get('game')!r}" if r.get("mapped_value") == eng.TWITCH_LIVE_SENTINEL and r.get("game") else ""),
             f"  config game: {r.get('before')!r} → {r.get('after')!r}" if r.get("changed")
             else f"  config game: {r.get('before')!r}",
             f"  {r.get('message')}",
             f"  log: {_JSONL}"]
    out["report"] = "\n".join(lines) + "\n"
    return out


def stop() -> Dict[str, Any]:
    pid = _bg_pid()
    if not pid:
        try:
            _PID.unlink()
        except Exception:
            pass
        return {"ok": True, "stopped": False, "message": "no background OBS game tracker is running"}
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            time.sleep(0.2)
            try:
                os.kill(pid, 0)
            except OSError:
                break
        else:
            return {"ok": False, "stopped": False,
                    "message": _soft(f"tracker PID {pid} didn't stop; run: kill {pid}")}
        try:
            _PID.unlink()
        except Exception:
            pass
        return {"ok": True, "stopped": True, "message": f"stopped background OBS game tracker (PID {pid})"}
    except Exception as exc:
        return {"ok": False, "stopped": False, "message": _soft(str(exc))}


def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, indent=2))
        return 0
    print(f"OBS game tracker: {info.get('readiness')}")
    print(f"  config game:  {info.get('config_game')!r}")
    if info.get("obs_checked"):
        if info.get("obs_ok"):
            scene = info.get("obs_scene")
            loose = "  (loose name match)" if info.get("matched_by") == "loose" else ""
            print(f"  OBS scene:    {scene!r}{loose}")
            mv = info.get("mapped_value")
            if mv:
                via = " (from Twitch)" if mv == "__twitch__" else ""
                print(f"  mapped game:  {info.get('mapped_game')!r}{via}")
            else:
                print("  mapped game:  (scene not mapped)")
            m = info.get("match")
            print(f"  match:        {'yes' if m else ('no' if m is False else 'n/a')}")
    obs = info.get("obs_summary") or {}
    if obs:
        print(f"  OBS:          {obs.get('host')}:{obs.get('port')}  password set: "
              f"{'yes' if obs.get('password_set') else 'no'}")
    print(f"  mapping:      {info.get('mapping_scene_count')} scenes in Data/configs/scene_game_mapping.json")
    pid = info.get("background_pid")
    print(f"  background:   {'running (PID %s)' % pid if pid else 'not running'}")
    fr = info.get("game_freshness") or {}
    if fr.get("stale"):
        print(f"  note: game may be stale — {fr.get('reason')}")
    if info.get("error"):
        print(f"  {info['error']}")
        if info.get("fix"):
            print(f"  Fix: {info['fix']}")
    elif info.get("hint"):
        print(f"  {info['hint']}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="bolt obs-game",
                                     description="Keep Core/config.json game in step with the OBS scene.")
    parser.add_argument("action", nargs="?", default="status", choices=["status", "list", "run", "stop"])
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--probe", action="store_true", help="status: check OBS live (default; kept for scripts)")
    parser.add_argument("--no-obs", action="store_true", help="status/list: don't contact OBS")
    parser.add_argument("--dry-run", action="store_true", help="run: show what would change, write nothing")
    parser.add_argument("--once", action="store_true", help="run: one sync (the default)")
    parser.add_argument("--watch", action="store_true", help="run: follow scene changes until Ctrl+C")
    parser.add_argument("--background", action="store_true", help="run: watch in the background (bolt obs-game stop)")
    args = parser.parse_args(argv)

    if args.action == "status":
        return _print_status(status(probe=not args.no_obs), args.json)

    if args.action == "list":
        res = list_items(check_obs=not args.no_obs)
        if args.json:
            print(json.dumps(res, indent=2))
            return 0
        if res.get("error"):
            print(res["error"])
            return 0
        print("Mapping (Data/configs/scene_game_mapping.json):")
        for k, v in res["mapping"].items():
            print(f"  {k!r:24} → {v}" + ("   (Twitch channel game)" if v == "__twitch__" else ""))
        if res.get("obs_error"):
            print(res["obs_error"])
            print(f"Fix: {res['obs_fix']}")
        elif not args.no_obs:
            print("OBS scenes:")
            for s in res["obs_scenes"]:
                cur = " *current*" if s["current"] else ""
                if s["maps_to"] is None:
                    print(f"  {s['scene']!r:24} not mapped (game left alone){cur}")
                else:
                    via = f" via {s['via_key']!r}" if s["matched_by"] == "loose" else ""
                    print(f"  {s['scene']!r:24} → {s['maps_to']}{via}{cur}")
        return 0

    if args.action == "stop":
        r = stop()
        print(json.dumps(r, indent=2) if args.json else r["message"])
        return 0

    result = try_run(dry_run=args.dry_run, watch=args.watch, background=args.background)
    if args.json:
        print(json.dumps({k: v for k, v in result.items() if k != "report"} | {"report": result.get("report", "")},
                         indent=2))
    elif not result.get("ok"):
        print(result.get("error"))
        if result.get("fix"):
            print(f"Fix: {result['fix']}")
    else:
        sys.stdout.write(result.get("report") or "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
