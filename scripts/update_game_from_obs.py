#!/usr/bin/env python3
"""
scripts/update_game_from_obs.py — keep Core/config.json "game" in step with OBS
==============================================================================
Engine for ``bolt obs-game`` (Core/modules/OBS_Game_Tracker.py).

* ``sync_once(dry_run=...)`` — ask OBS for the current scene (read-only
  request, 3 s timeout), look it up in Data/configs/scene_game_mapping.json
  and, if the game differs, write Core/config.json ``game`` (atomic; every
  other key kept). One line per sync goes to logs/obs_game_tracker.jsonl.
* ``main()`` — watch mode: sync once now, then follow OBS scene changes
  until Ctrl+C / SIGTERM (``bolt obs-game stop``). Logs to
  logs/obs_game_tracker.log.

Mapping value ``__twitch__`` means "use the game set on my Twitch channel"
(Helix, 8 s timeout). If Twitch can't answer, the current game is kept.

Scene names match loosely: case, extra spaces and OBS's "(1)" copy suffix
are ignored, so "Be Right Back(1)" finds a "Be Right Back" mapping.

Never changes OBS scenes, settings, streaming or recording.

Settings: OBS_HOST / OBS_PORT / OBS_PASSWORD from .env.local, then .env
(first value wins); Core/config.json obs_host / obs_port win over env.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Post-reorg path bootstrap (adds Core/ to sys.path, chdirs to repo root).
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import (  # noqa: E402
    REPO_ROOT,
    DATA_DIR,
    CLIPS_DIR,
    LOGS_DIR,
    CONFIG_FILE,
    CONFIG_DIR,
)

PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT

MAPPING_FILE = CONFIG_DIR / "scene_game_mapping.json"
CHANGE_LOG = LOGS_DIR / "obs_game_tracker.jsonl"
WATCH_LOG = LOGS_DIR / "obs_game_tracker.log"
PID_FILE = LOGS_DIR / "obs_game_tracker.pid"

logger = logging.getLogger("bolt.obs_game_tracker")

TWITCH_LIVE_SENTINEL = "__twitch__"
SOFT = "Game tracker unavailable:"
OBS_TIMEOUT = 3.0
TWITCH_TIMEOUT = 8.0

FIX_OBS_OFF = (
    "Open OBS, then OBS → Tools → WebSocket Server Settings → tick "
    "'Enable WebSocket server' (port {port}) → OK."
)
FIX_NO_PASSWORD = (
    "OBS asks for a WebSocket password but Bolt has none. In OBS → Tools → "
    "WebSocket Server Settings → Show Connect Info, copy the password and put it "
    "in ~/developer/Bolt/.env.local as OBS_PASSWORD=<password>."
)
FIX_BAD_PASSWORD = (
    "OBS rejected the password. In OBS → Tools → WebSocket Server Settings → "
    "Show Connect Info, copy the password and set OBS_PASSWORD=<password> in "
    "~/developer/Bolt/.env.local (it overrides .env)."
)
FIX_NO_CLIENT = "Install the WebSocket client: cd ~/developer/Bolt && uv sync"


# ── settings ────────────────────────────────────────────────────────────────


def load_env() -> None:
    """Load .env.local then .env (first value wins; never overrides real env)."""
    for name in (".env.local", ".env"):
        path = REPO_ROOT / name
        if not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                if k.startswith("export "):
                    k = k[len("export "):].strip()
                v = v.strip().strip('"').strip("'")
                if k and v and not os.environ.get(k):
                    os.environ[k] = v
        except Exception as exc:  # pragma: no cover - soft
            logger.warning("could not read %s: %s", name, exc)


def obs_settings() -> Dict[str, Any]:
    """host / port / password. config.json obs_host/obs_port, else env, else defaults."""
    load_env()
    cfg = _read_json(CONFIG_FILE, {})
    cfg = cfg if isinstance(cfg, dict) else {}
    host = str(cfg.get("obs_host") or os.getenv("OBS_HOST") or "localhost").strip() or "localhost"
    try:
        port = int(cfg.get("obs_port") or os.getenv("OBS_PORT") or 4455)
    except (TypeError, ValueError):
        port = 4455
    password = (os.getenv("OBS_PASSWORD") or "").strip()
    return {
        "host": host,
        "port": port,
        "password": password,
        "password_set": bool(password),
        "use_obs_integration": bool(cfg.get("use_obs_integration", True)),
    }


# ── small helpers ───────────────────────────────────────────────────────────


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def current_config_game() -> str:
    cfg = _read_json(CONFIG_FILE, {})
    return str(cfg.get("game") or "") if isinstance(cfg, dict) else ""


def _norm(name: str) -> str:
    """Loose scene key: casefold, single spaces, drop OBS's trailing '(1)' copy suffix."""
    s = " ".join(str(name or "").split()).casefold()
    s = re.sub(r"\s*\(\d+\)$", "", s)
    return s.strip()


def load_mapping() -> Dict[str, Any]:
    raw = _read_json(MAPPING_FILE, None)
    if not isinstance(raw, dict):
        raise ValueError(f"cannot read {MAPPING_FILE} (missing or not valid JSON)")
    scenes = raw.get("scenes")
    if not isinstance(scenes, dict):
        raise ValueError(f'{MAPPING_FILE} has no "scenes" object')
    return raw


def lookup_scene(scene: str, mapping: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], str, str]:
    """Return (mapped_value, matched_key, how) — how is exact / loose / none."""
    mapping = mapping if mapping is not None else load_mapping()
    scenes = mapping.get("scenes") or {}
    if scene in scenes:
        return str(scenes[scene]), scene, "exact"
    want = _norm(scene)
    if want:
        for key, val in scenes.items():
            if _norm(key) == want:
                return str(val), key, "loose"
    return None, "", "none"


def _log_jsonl(row: Dict[str, Any]) -> None:
    try:
        CHANGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CHANGE_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:  # pragma: no cover - soft
        logger.warning("could not write %s: %s", CHANGE_LOG, exc)


# ── OBS (read-only) ─────────────────────────────────────────────────────────


def _auth_string(password: str, auth: Dict[str, Any]) -> str:
    secret = base64.b64encode(
        hashlib.sha256((password + auth["salt"]).encode()).digest()
    ).decode()
    return base64.b64encode(
        hashlib.sha256((secret + auth["challenge"]).encode()).digest()
    ).decode()


def _obs_connect(settings: Dict[str, Any], timeout: float):
    """Open + identify a WebSocket. Returns (ws, None) or (None, (error, fix))."""
    host, port, password = settings["host"], settings["port"], settings["password"]
    try:
        import websocket  # websocket-client
    except ImportError:
        return None, ("websocket-client is not installed", FIX_NO_CLIENT)
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError:
        return None, (
            f"OBS isn't answering on {host}:{port} (OBS closed, or its WebSocket server is off)",
            FIX_OBS_OFF.format(port=port),
        )
    try:
        ws = websocket.create_connection(f"ws://{host}:{port}", timeout=timeout)
    except Exception as exc:
        return None, (f"port {port} is open but it isn't OBS's WebSocket ({type(exc).__name__})",
                      FIX_OBS_OFF.format(port=port))
    try:
        ws.settimeout(timeout)
        hello = json.loads(ws.recv())
        if hello.get("op") != 0:
            raise ValueError("no Hello from OBS")
        auth = (hello.get("d") or {}).get("authentication")
        ident: Dict[str, Any] = {"rpcVersion": 1, "eventSubscriptions": 0}
        if auth:
            if not password:
                ws.close()
                return None, ("OBS needs a WebSocket password and OBS_PASSWORD is empty", FIX_NO_PASSWORD)
            ident["authentication"] = _auth_string(password, auth)
        ws.send(json.dumps({"op": 1, "d": ident}))
        try:
            reply = json.loads(ws.recv())
        except Exception:
            reply = {}
        if reply.get("op") != 2:
            try:
                ws.close()
            except Exception:
                pass
            if auth:
                return None, ("OBS rejected the WebSocket password", FIX_BAD_PASSWORD)
            return None, ("OBS refused the connection", FIX_OBS_OFF.format(port=port))
        return ws, None
    except Exception as exc:
        try:
            ws.close()
        except Exception:
            pass
        return None, (f"OBS didn't finish the handshake within {timeout:.0f}s ({type(exc).__name__})",
                      "OBS may be busy or frozen — wait a moment or restart OBS, then try again.")


def _obs_request(ws, request_type: str, rid: str) -> Dict[str, Any]:
    ws.send(json.dumps({"op": 6, "d": {"requestType": request_type, "requestId": rid}}))
    for _ in range(50):
        msg = json.loads(ws.recv())
        d = msg.get("d") or {}
        if msg.get("op") == 7 and d.get("requestId") == rid:
            if not (d.get("requestStatus") or {}).get("result"):
                raise RuntimeError(f"{request_type} failed: {(d.get('requestStatus') or {}).get('comment')}")
            return d.get("responseData") or {}
    raise RuntimeError(f"no answer to {request_type}")


def obs_snapshot(timeout: float = OBS_TIMEOUT, *, scene_list: bool = False) -> Dict[str, Any]:
    """Current program scene (and optionally all scene names). Never raises."""
    settings = obs_settings()
    out: Dict[str, Any] = {"ok": False, "scene": "", "scenes": [], "error": "", "fix": "",
                           "host": settings["host"], "port": settings["port"],
                           "password_set": settings["password_set"]}
    ws, err = _obs_connect(settings, timeout)
    if err:
        out["error"], out["fix"] = err
        return out
    try:
        cur = _obs_request(ws, "GetCurrentProgramScene", "bolt-scene")
        out["scene"] = str(cur.get("currentProgramSceneName") or cur.get("sceneName") or "")
        if scene_list:
            lst = _obs_request(ws, "GetSceneList", "bolt-scenes")
            out["scenes"] = [str(s.get("sceneName") or "") for s in (lst.get("scenes") or [])]
        out["ok"] = True
    except Exception as exc:
        out["error"] = f"OBS didn't answer the scene request ({type(exc).__name__}: {exc})"
        out["fix"] = "OBS may be busy or frozen — wait a moment or restart OBS, then try again."
    finally:
        try:
            ws.close()
        except Exception:
            pass
    return out


# ── resolve + write ─────────────────────────────────────────────────────────


def _twitch_game() -> Dict[str, str]:
    try:
        from modules.Game_Refresh import _twitch_game as gr_twitch  # hard timeout, thread

        return gr_twitch(timeout=TWITCH_TIMEOUT)
    except Exception as exc:
        return {"game": "", "error": f"Twitch lookup unavailable ({exc})"}


def _resolve_game(mapped_value: str) -> str:
    """Mapped value → game name ('' when __twitch__ and Twitch can't answer)."""
    if mapped_value == TWITCH_LIVE_SENTINEL:
        tw = _twitch_game()
        if tw.get("game"):
            logger.info("Fetched live game from Twitch: %s", tw["game"])
            return tw["game"]
        logger.warning("Twitch gave no game (%s) — keeping previous value", tw.get("error"))
        return ""
    return mapped_value


def _source_for(mapped_value: str, mapping: Dict[str, Any]) -> str:
    if mapped_value == TWITCH_LIVE_SENTINEL:
        return "twitch"
    live = mapping.get("live_scene") or "Live Scene"
    pinned = (mapping.get("scenes") or {}).get(live)
    return "obs_mapping_pin" if mapped_value == pinned else "obs_scene"


def update_config_game(new_game: str, source: str = "obs_scene") -> Dict[str, Any]:
    """Atomically set Core/config.json game (other keys untouched). Never raises."""
    res = {"changed": False, "before": current_config_game(), "after": "", "error": ""}
    if not new_game:
        res["after"] = res["before"]
        return res
    try:
        from modules.Game_Refresh import _write_config_game, record_change

        res["changed"] = bool(_write_config_game(new_game))
        res["after"] = current_config_game()
        record_change(new_game, source, previous=res["before"])
    except Exception as exc:
        res["error"] = f"could not update {CONFIG_FILE.name} ({exc})"
        res["after"] = current_config_game()
    return res


def sync_scene(scene: str, *, dry_run: bool = False, trigger: str = "run") -> Dict[str, Any]:
    """Map a known scene name to a game and (unless dry_run) apply it."""
    out: Dict[str, Any] = {"at": _iso(), "trigger": trigger, "dry_run": dry_run, "ok": False,
                           "scene": scene, "mapped_value": "", "matched_key": "", "matched_by": "none",
                           "game": "", "before": current_config_game(), "after": "",
                           "changed": False, "would_change": False, "message": "", "error": "", "fix": ""}
    out["after"] = out["before"]
    try:
        mapping = load_mapping()
    except Exception as exc:
        out["error"], out["fix"] = str(exc), "Restore Data/configs/scene_game_mapping.json (see Data/backups/)."
        _log_jsonl(out)
        return out
    value, key, how = lookup_scene(scene, mapping)
    out["matched_key"], out["matched_by"] = key, how
    if value is None:
        out["ok"] = True
        out["message"] = (f"scene {scene!r} isn't in the mapping — game left as {out['before']!r}. "
                          f"To track it, add \"{scene}\": \"<Game>\" to Data/configs/scene_game_mapping.json.")
        _log_jsonl(out)
        return out
    out["mapped_value"] = value
    game = _resolve_game(value)
    out["game"] = game
    if not game:
        out["ok"] = True
        tw = "Twitch didn't return a game" if value == TWITCH_LIVE_SENTINEL else "empty mapping value"
        out["message"] = f"{tw} — game left as {out['before']!r}. Check: bolt game status --twitch"
        _log_jsonl(out)
        return out
    out["would_change"] = game != out["before"]
    if dry_run:
        out["ok"] = True
        out["message"] = (f"would set game {out['before']!r} → {game!r}" if out["would_change"]
                          else f"game already {game!r} — nothing to do")
        _log_jsonl(out)
        return out
    res = update_config_game(game, source=_source_for(value, mapping))
    out.update({"changed": res["changed"], "after": res["after"]})
    if res["error"]:
        out["error"] = res["error"]
        out["fix"] = "Check Core/config.json is valid JSON (bolt doctor)."
    else:
        out["ok"] = True
        out["message"] = (f"game {out['before']!r} → {res['after']!r}" if res["changed"]
                          else f"game already {game!r} — nothing to do")
    _log_jsonl(out)
    return out


def sync_once(*, dry_run: bool = False, trigger: str = "run") -> Dict[str, Any]:
    """Ask OBS for the current scene, then sync_scene(). Never raises."""
    snap = obs_snapshot()
    if not snap["ok"]:
        out = {"at": _iso(), "trigger": trigger, "dry_run": dry_run, "ok": False, "scene": "",
               "before": current_config_game(), "after": current_config_game(), "changed": False,
               "error": snap["error"], "fix": snap["fix"]}
        _log_jsonl(out)
        return out
    return sync_scene(snap["scene"], dry_run=dry_run, trigger=trigger)


# Kept for callers that pass a mapped value (older Stream_Monitor wiring).
def _on_scene_changed(mapped_value: str):
    game = _resolve_game(mapped_value)
    if game:
        try:
            mapping = load_mapping()
        except Exception:
            mapping = {}
        update_config_game(game, source=_source_for(mapped_value, mapping))


# ── watch mode ──────────────────────────────────────────────────────────────


def _print(msg: str) -> None:
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)


def _make_monitor(settings: Dict[str, Any], on_scene, on_stream_start):
    from modules.Stream_Monitor import StreamMonitor

    class _TrackerMonitor(StreamMonitor):
        """Scene + stream events only (no audio meter flood); passes raw scene names."""

        def _handle_hello(self, data: dict):
            auth = data.get("authentication")
            ident: Dict[str, Any] = {"rpcVersion": 1,
                                     "eventSubscriptions": (1 << 0) | (1 << 2) | (1 << 6)}
            if auth and self.password:
                ident["authentication"] = _auth_string(self.password, auth)
            self._ws.send(json.dumps({"op": 1, "d": ident}))

        def _handle_scene_change(self, scene_name: str):
            if scene_name and scene_name != self._last_scene:
                self._last_scene = scene_name
                on_scene(scene_name)

    return _TrackerMonitor(host=settings["host"], port=settings["port"],
                           password=settings["password"], on_stream_start=on_stream_start)


def main(stop_event: Optional[threading.Event] = None) -> int:
    """Watch OBS and keep config.json game in step. Ctrl+C / SIGTERM stops it."""
    stop_event = stop_event or threading.Event()
    settings = obs_settings()
    _print("[OBS game tracker] watching OBS scenes (Ctrl+C or `bolt obs-game stop` to stop)")
    _print(f"  mapping: {MAPPING_FILE}")
    _print(f"  config:  {CONFIG_FILE}   changes log: {CHANGE_LOG}")

    first = sync_once(trigger="watch_start")
    if not first.get("ok"):
        _print(f"{SOFT} {first.get('error')}. Fix: {first.get('fix')}")
        return 0
    _print(f"  now: scene {first.get('scene')!r} → {first.get('message')}")

    def on_scene(scene: str):
        r = sync_scene(scene, trigger="scene_change")
        _print(f"scene {scene!r} → {r.get('message') or r.get('error')}")

    def on_stream_start():
        r = sync_once(trigger="stream_start")
        _print(f"stream started → {r.get('message') or r.get('error')}")

    if threading.current_thread() is threading.main_thread():
        def _stop(signum, frame):  # noqa: ARG001
            stop_event.set()
        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

    monitor = _make_monitor(settings, on_scene, on_stream_start)
    monitor._last_scene = first.get("scene") or None
    monitor.start()
    try:
        while not stop_event.is_set():
            stop_event.wait(1.0)
    except KeyboardInterrupt:
        pass
    _print("[OBS game tracker] stopping")
    monitor.stop()
    return 0


start_game_tracker = main


def _cli_watch_with_pid() -> int:
    """Entry for the background helper: record PID, watch, clean up."""
    try:
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass
    try:
        return main()
    finally:
        try:
            if PID_FILE.is_file() and PID_FILE.read_text().strip() == str(os.getpid()):
                PID_FILE.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sys.exit(_cli_watch_with_pid())
