#!/usr/bin/env python3
"""
Game_Refresh.py — keep Core/config.json ``game`` fresh (READY; soft-fail)
========================================================================
Why: ``game`` sat on "007 First Light" for a month because it only changed on
an OBS scene switch or a Twitch fetch, and the Live Scene mapping can be pinned.
Nothing recorded *when* the value was last confirmed, so nothing warned.

This module adds:
  * ``Data/configs/game_state.json`` — who set the game, when it was last
    *confirmed* (authoritative source) and last *checked* (any refresh).
  * ``refresh()`` — resolve the live game at stream start / on demand:
      * Live Scene pinned to a real name → keep the pin, but also ask Twitch
        and warn loudly when the channel category disagrees
      * Live Scene = __twitch__ → Twitch Helix channel game (8s timeout)
      * else keep current value (warn)
    Only Twitch / manual ``set`` / OBS non-live scene change count as *confirmed*.
    A pinned mapping refresh stamps ``checked_at`` but not ``confirmed_at`` —
    so a pin that William forgot still goes stale and gets flagged.
  * ``set_game()`` — manual confirm (optionally re-pin the Live Scene mapping).
  * ``record_change()`` — hook for scripts/update_game_from_obs.py.
  * ``freshness()`` — age + stale flag for status / doctor.

CLI (via ``bolt game``):
  status [--json] [--no-twitch]   (default; never writes; when the Live Scene
                                  follows Twitch it also asks Twitch and flags drift)
  refresh [--source S] [--dry-run] [--json]
  set <name> [--pin] [--json]
  unpin [--json]                  (Live Scene → __twitch__)
  history [--json]

Soft-fail prefix: ``Game refresh unavailable:``. Stale threshold:
``Core/config.json`` ``game_stale_days`` or env ``BOLT_GAME_STALE_DAYS`` (default 7).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Game refresh unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_CORE = _REPO / "Core"
_CONFIG = _CORE / "config.json"
_MAPPING = _REPO / "Data" / "configs" / "scene_game_mapping.json"
_STATE = _REPO / "Data" / "configs" / "game_state.json"
_TWITCH_SENTINEL = "__twitch__"
_DEFAULT_STALE_DAYS = 7
_CONFIRMING_SOURCES = {"twitch", "manual", "obs_scene", "stream_start_twitch"}
_HISTORY_MAX = 50


def _soft(msg: str) -> str:
    return msg if msg.startswith(_SOFT) else f"{_SOFT} {msg}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def config_game() -> str:
    cfg = _load_json(_CONFIG, {})
    return str(cfg.get("game") or "") if isinstance(cfg, dict) else ""


def stale_days() -> int:
    env = (os.environ.get("BOLT_GAME_STALE_DAYS") or "").strip()
    if env.isdigit():
        return max(1, int(env))
    cfg = _load_json(_CONFIG, {})
    try:
        return max(1, int(cfg.get("game_stale_days", _DEFAULT_STALE_DAYS)))
    except Exception:
        return _DEFAULT_STALE_DAYS


def load_state() -> Dict[str, Any]:
    st = _load_json(_STATE, {})
    return st if isinstance(st, dict) else {}


def _save_state(state: Dict[str, Any]) -> None:
    hist = state.get("history") or []
    state["history"] = hist[-_HISTORY_MAX:]
    _write_json(_STATE, state)


def _write_config_game(new_game: str) -> bool:
    """Set Core/config.json game; returns True when the value changed."""
    cfg = _load_json(_CONFIG, None)
    if not isinstance(cfg, dict):
        raise RuntimeError(f"cannot read {_CONFIG}")
    if cfg.get("game") == new_game:
        return False
    cfg["game"] = new_game
    _write_json(_CONFIG, cfg)
    return True


def record_change(game: str, source: str, *, previous: str = "") -> Dict[str, Any]:
    """Stamp state for a game value (called by every writer). Never raises."""
    try:
        state = load_state()
        now = _iso()
        state["game"] = game
        state["source"] = source
        state["checked_at"] = now
        if source in _CONFIRMING_SOURCES:
            state["confirmed_at"] = now
            state["confirmed_source"] = source
        if previous != game or not state.get("changed_at"):
            if previous != game:
                state["changed_at"] = now
        state.setdefault("history", []).append(
            {"at": now, "game": game, "previous": previous, "source": source}
        )
        _save_state(state)
        return state
    except Exception as exc:  # pragma: no cover - soft
        return {"error": _soft(str(exc))}


def freshness(state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = load_state() if state is None else state
    limit = stale_days()
    cur = config_game()
    confirmed = _parse(str(state.get("confirmed_at") or ""))
    age_days: Optional[float] = None
    if confirmed:
        age_days = round((_now() - confirmed).total_seconds() / 86400.0, 2)
    mismatch = bool(state.get("game")) and state.get("game") != cur
    stale = confirmed is None or (age_days is not None and age_days > limit) or mismatch
    if confirmed is None:
        why = "never confirmed (no Twitch fetch / manual set recorded)"
    elif mismatch:
        why = f"config game {cur!r} differs from last recorded {state.get('game')!r} (edited by hand?)"
    elif stale:
        why = f"last confirmed {age_days:.1f} days ago (> {limit})"
    else:
        why = f"confirmed {age_days:.1f} days ago via {state.get('confirmed_source')}"
    return {
        "game": cur,
        "confirmed_at": state.get("confirmed_at") or "",
        "checked_at": state.get("checked_at") or "",
        "source": state.get("source") or "",
        "age_days": age_days,
        "stale_days": limit,
        "stale": bool(stale),
        "reason": why,
        "fix": (
            "bolt game refresh (Twitch) or bolt game set \"<Game>\""
            if stale
            else ""
        ),
    }


def _mapping() -> Dict[str, Any]:
    raw = _load_json(_MAPPING, {})
    return raw if isinstance(raw, dict) else {}


def live_scene_value() -> str:
    m = _mapping()
    scene = m.get("live_scene") or "Live Scene"
    return str((m.get("scenes") or {}).get(scene) or "")


def _twitch_game(timeout: float = 8.0) -> Dict[str, Any]:
    """Fetch channel game from Twitch Helix in a thread with a hard timeout."""
    box: Dict[str, Any] = {"game": "", "error": ""}

    def _work() -> None:
        try:
            if str(_CORE) not in sys.path:
                sys.path.insert(0, str(_CORE))
            from modules import Twitch_API  # noqa: WPS433

            g = Twitch_API.get_current_game()
            if g and g != "Unknown":
                box["game"] = g
            else:
                box["error"] = "Twitch returned no game (token/creds? channel unset?)"
        except Exception as exc:
            box["error"] = f"Twitch fetch failed ({type(exc).__name__}: {exc})"

    t = threading.Thread(target=_work, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        box["error"] = f"Twitch fetch timed out after {timeout:.0f}s"
    return box


def refresh(*, source: str = "manual_refresh", dry_run: bool = False,
            use_twitch: bool = True) -> Dict[str, Any]:
    """Resolve the live game and update config + state. Never raises.

    Order:
      * Live Scene pinned to a real name (William's explicit choice) → use the
        pin, but still ask Twitch and warn when the channel category differs.
      * Live Scene = ``__twitch__`` → Twitch Helix channel game.
      * Otherwise keep the current value (warn).
    """
    out: Dict[str, Any] = {"ok": False, "dry_run": dry_run, "trigger": source,
                           "previous": config_game(), "attempts": []}
    try:
        pin = live_scene_value()
        pinned = bool(pin) and pin != _TWITCH_SENTINEL
        tw: Dict[str, Any] = {"game": "", "error": "skipped (--no-twitch)"}
        if use_twitch:
            tw = _twitch_game()
        out["attempts"].append({"source": "twitch", "game": tw["game"], "error": tw["error"]})
        out["attempts"].append({"source": "obs_mapping_pin", "game": pin if pinned else "",
                                "error": "" if pinned else "Live Scene maps to __twitch__ (no pin)"})
        warnings: List[str] = []
        if pinned:
            resolved, how = pin, "obs_mapping_pin"
            if tw["game"] and tw["game"].casefold() != pin.casefold():
                warnings.append(
                    f"Twitch category is {tw['game']!r} but OBS Live Scene is pinned to {pin!r}. "
                    f"If you switched games: bolt game set \"{tw['game']}\" --pin "
                    "(or bolt game unpin to follow Twitch)."
                )
        elif tw["game"]:
            resolved, how = tw["game"], "twitch"
        else:
            resolved, how = out["previous"], "kept"
            warnings.append(f"Twitch unavailable ({tw['error']}); kept {resolved!r}.")
        out["game"], out["resolved_via"] = resolved, how
        out["twitch_game"] = tw["game"]
        if dry_run:
            out["ok"] = True
            out["would_change"] = resolved != out["previous"]
            if warnings:
                out["warning"] = " ".join(warnings)
            return out
        changed = _write_config_game(resolved) if resolved else False
        out["changed"] = changed
        if how == "twitch":
            stamp_source = "stream_start_twitch" if source == "stream_start" else "twitch"
        else:
            stamp_source = how
        state = record_change(resolved, stamp_source, previous=out["previous"])
        fr = freshness(state if isinstance(state, dict) and "error" not in state else None)
        out["freshness"] = fr
        if how != "twitch" and fr.get("stale"):
            warnings.append(
                f"{resolved!r} not confirmed recently ({fr.get('reason')}). "
                f"Confirm with: bolt game set \"{resolved}\"."
            )
        if warnings:
            out["warning"] = " ".join(warnings)
        out["ok"] = True
        return out
    except Exception as exc:
        out["error"] = _soft(str(exc) or type(exc).__name__)
        return out


def unpin() -> Dict[str, Any]:
    """Point OBS Live Scene back at the __twitch__ sentinel."""
    try:
        m = _mapping()
        scene = m.get("live_scene") or "Live Scene"
        prev = (m.get("scenes") or {}).get(scene)
        m.setdefault("scenes", {})[scene] = _TWITCH_SENTINEL
        _write_json(_MAPPING, m)
        return {"ok": True, "scene": scene, "previous": prev, "now": _TWITCH_SENTINEL}
    except Exception as exc:
        return {"ok": False, "error": _soft(str(exc) or type(exc).__name__)}


def set_game(name: str, *, pin: bool = False) -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": _soft("empty game name")}
    try:
        prev = config_game()
        changed = _write_config_game(name)
        pinned = False
        if pin:
            m = _mapping()
            scene = m.get("live_scene") or "Live Scene"
            m.setdefault("scenes", {})[scene] = name
            _write_json(_MAPPING, m)
            pinned = True
        record_change(name, "manual", previous=prev)
        return {"ok": True, "game": name, "previous": prev, "changed": changed,
                "pinned_live_scene": pinned, "freshness": freshness()}
    except Exception as exc:
        return {"ok": False, "error": _soft(str(exc) or type(exc).__name__)}


def status(*, check_twitch: bool = False) -> Dict[str, Any]:
    """Never writes. With ``check_twitch`` (CLI default when the Live Scene
    follows Twitch), also asks Twitch and flags drift: a "fresh" config game
    that no longer matches the channel category is still the wrong game."""
    fr = freshness()
    pin = live_scene_value()
    pinned = pin not in ("", _TWITCH_SENTINEL)
    drift: Dict[str, Any] = {"twitch_checked": False, "twitch_game": "",
                             "twitch_error": "", "twitch_drift": False}
    if check_twitch and not pinned:
        tw = _twitch_game(timeout=6.0)
        drift.update(twitch_checked=True, twitch_game=tw["game"], twitch_error=tw["error"])
        if tw["game"] and tw["game"].casefold() != str(fr.get("game") or "").casefold():
            drift["twitch_drift"] = True
            drift["drift_fix"] = (
                f"Twitch category is {tw['game']!r} but config game is {fr.get('game')!r} — "
                "run bolt game refresh (bolt launch does this automatically at stream start)."
            )
    return {
        "checked_at": _iso(),
        "readiness": "READY",
        "ready": _CONFIG.is_file(),
        "soft_fail_prefix": _SOFT,
        "cli": "bolt game",
        "config": str(_CONFIG),
        "state_file": str(_STATE),
        "state_present": _STATE.is_file(),
        "mapping": str(_MAPPING),
        "live_scene_value": live_scene_value(),
        "live_scene_pinned": pinned,
        **fr,
        **drift,
        "hooks": [
            "scripts/update_game_from_obs.py (tracker start + StreamStateChanged start + scene change)",
            "Core/launch.py (bolt launch: refresh before tracker)",
        ],
    }


def _print(obj: Dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, indent=2))


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(prog="bolt game", description="Game freshness (READY; soft-fail)")
    p.add_argument("action", nargs="?", default="status",
                   choices=["status", "refresh", "set", "unpin", "history"])
    p.add_argument("name", nargs="*", help="set: game name")
    p.add_argument("--json", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--pin", action="store_true", help="set: also pin OBS Live Scene mapping")
    p.add_argument("--no-twitch", action="store_true", help="refresh/status: skip Twitch fetch")
    p.add_argument("--source", default="manual_refresh", help="refresh: trigger label (e.g. stream_start)")
    a = p.parse_args(argv)
    try:
        if a.action == "status":
            st = status(check_twitch=not a.no_twitch)
            if a.json:
                _print(st, True)
            else:
                flag = "STALE" if st["stale"] else "fresh"
                print(f"game readiness: READY  game={st['game']!r}  [{flag}]")
                print(f"  {st['reason']}")
                print(f"  confirmed_at: {st['confirmed_at'] or '-'}  checked_at: {st['checked_at'] or '-'}  (UTC)")
                print(f"  live scene mapping: {st['live_scene_value']!r} pinned={st['live_scene_pinned']}")
                print(f"  stale threshold: {st['stale_days']} days  state: {_STATE}")
                if st.get("twitch_checked"):
                    if st.get("twitch_game"):
                        match = "DRIFT" if st.get("twitch_drift") else "matches"
                        print(f"  twitch category: {st['twitch_game']!r} ({match})")
                    else:
                        print(f"  twitch category: - ({st.get('twitch_error') or 'unavailable'}; Twitch creds in .env)")
                if st.get("twitch_drift"):
                    print(f"  WARNING: {st['drift_fix']}")
                if st["stale"]:
                    print(f"  WARNING: game may be stale — {st['fix']}")
            return 0
        if a.action == "refresh":
            r = refresh(source=a.source, dry_run=a.dry_run, use_twitch=not a.no_twitch)
            if a.json:
                _print(r, True)
            elif r.get("error"):
                print(r["error"])
            else:
                for at in r["attempts"]:
                    print(f"  try {at['source']}: {at['game'] or '-'} {('— ' + at['error']) if at['error'] else ''}")
                verb = "would set" if a.dry_run else "game"
                print(f"{verb} = {r['game']!r} via {r['resolved_via']} (was {r['previous']!r})")
                if r.get("warning"):
                    print(f"  WARNING: {r['warning']}")
            return 0
        if a.action == "set":
            r = set_game(" ".join(a.name), pin=a.pin)
            if a.json:
                _print(r, True)
            elif r.get("error"):
                print(r["error"])
            else:
                print(f"game = {r['game']!r} (was {r['previous']!r}); confirmed now"
                      + ("; Live Scene pinned" if r["pinned_live_scene"] else ""))
            return 0
        if a.action == "unpin":
            r = unpin()
            if a.json:
                _print(r, True)
            else:
                print(r.get("error") or f"{r['scene']}: {r['previous']!r} -> __twitch__ (refresh now follows Twitch)")
            return 0
        if a.action == "history":
            hist = load_state().get("history") or []
            if a.json:
                _print({"history": hist}, True)
            else:
                for h in hist[-20:]:
                    print(f"{h['at']}  {h['previous']!r} -> {h['game']!r}  ({h['source']})")
                if not hist:
                    print("(no history yet — run bolt game refresh)")
            return 0
    except Exception as exc:
        print(_soft(str(exc) or type(exc).__name__))
    return 0


if __name__ == "__main__":
    sys.exit(main())
