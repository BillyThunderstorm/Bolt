#!/usr/bin/env python3
"""
Game_Config.py — per-game sensitivity profiles + soft-fail CLI (PARTIAL)
========================================================================
Merged priority:
  Data/configs/game_configs.json (user overrides)
  > built-in _PROFILES
  > _DEFAULTS

Soft-fail prefix: ``Game config unavailable:``.

CLI (via ``bolt game-config``):
  status [--json] [--probe]
  list [--json]
  show [game] [--json]
  set <game> [--json] KEY=VALUE …

Stay PARTIAL — overrides optional; profiles William-tuned; not stranger-ready.
Distinct from PARTIAL ``bolt obs-game`` (OBS scene→config game tracker) and
READY ``bolt obs`` (WebSocket monitor).

Public API (in-process):
  get_game_config(game_name) → dict
  detect_game() → str
  save_custom_config(game_name, overrides)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Game config unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_CORE_CONFIG = _REPO / "Core" / "config.json"
_CUSTOM = _REPO / "Data" / "configs" / "game_configs.json"
# Legacy CWD-relative path (pre-reorg / wrong-cwd callers)
_LEGACY_CUSTOM = _REPO / "game_configs.json"

_DEFAULTS = {
    "highlight_sensitivity": 0.7,
    "spike_multiplier": 2.8,
    "pad_before": 12.0,
    "pad_after": 20.0,
    "min_clip_score": 40.0,
    "tiktok_style": "letterbox",
    "title_vibe": "highlight",
    "game_events_enabled": False,
}

_PROFILES = {
    "marvel rivals": {
        "spike_multiplier": 2.4,
        "pad_before": 10,
        "pad_after": 18,
        "title_vibe": "kill",
        "game_events_enabled": True,
    },
    "overwatch": {
        "spike_multiplier": 2.5,
        "pad_before": 10,
        "pad_after": 18,
        "title_vibe": "skill",
    },
    "overwatch 2": {
        "spike_multiplier": 2.5,
        "pad_before": 10,
        "pad_after": 18,
        "title_vibe": "skill",
    },
    "valorant": {
        "spike_multiplier": 2.6,
        "pad_before": 12,
        "pad_after": 20,
        "title_vibe": "clutch",
    },
    "cs2": {
        "spike_multiplier": 2.7,
        "pad_before": 12,
        "pad_after": 18,
        "title_vibe": "clutch",
    },
    "apex legends": {
        "spike_multiplier": 2.4,
        "pad_before": 14,
        "pad_after": 22,
        "title_vibe": "win",
    },
    "fortnite": {
        "spike_multiplier": 2.3,
        "pad_before": 12,
        "pad_after": 20,
        "title_vibe": "win",
    },
    "warzone": {
        "spike_multiplier": 2.5,
        "pad_before": 14,
        "pad_after": 20,
        "title_vibe": "win",
    },
    "league of legends": {
        "spike_multiplier": 2.6,
        "pad_before": 15,
        "pad_after": 25,
        "title_vibe": "skill",
        "min_clip_score": 45,
    },
    "dota 2": {
        "spike_multiplier": 2.6,
        "pad_before": 15,
        "pad_after": 25,
        "title_vibe": "skill",
    },
    "minecraft": {
        "spike_multiplier": 2.2,
        "pad_before": 10,
        "pad_after": 15,
        "title_vibe": "funny",
    },
    "phasmophobia": {
        "spike_multiplier": 2.0,
        "pad_before": 8,
        "pad_after": 15,
        "title_vibe": "funny",
    },
    "just chatting": {
        "spike_multiplier": 3.5,
        "pad_before": 20,
        "pad_after": 30,
        "title_vibe": "reaction",
        "tiktok_style": "crop",
    },
}


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _custom_path() -> Path:
    """Prefer Data/configs/; fall back to legacy repo-root file if present."""
    if _CUSTOM.is_file():
        return _CUSTOM
    if _LEGACY_CUSTOM.is_file():
        return _LEGACY_CUSTOM
    return _CUSTOM


def _load_custom() -> dict:
    path = _custom_path()
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_game_config(game_name: str = "") -> dict:
    cfg = dict(_DEFAULTS)
    key = (game_name or "").lower().strip()
    if key in _PROFILES:
        cfg.update(_PROFILES[key])
    custom = _load_custom()
    if key in custom and isinstance(custom[key], dict):
        cfg.update(custom[key])
    return cfg


def detect_game() -> str:
    name = os.getenv("GAME_NAME", "") or ""
    if name.strip():
        return name.strip()
    for path in (_CORE_CONFIG, _REPO / "config.json"):
        try:
            if path.is_file():
                with open(path, encoding="utf-8") as f:
                    game = json.load(f).get("game", "Gaming")
                return str(game or "Gaming")
        except Exception:
            continue
    return "Gaming"


def save_custom_config(game_name: str, overrides: dict) -> Path:
    """Write overrides under Data/configs/game_configs.json. Returns path written."""
    key = (game_name or "").lower().strip()
    if not key:
        raise ValueError("empty game name")
    if not isinstance(overrides, dict):
        raise TypeError("overrides must be a dict")
    custom = _load_custom()
    custom[key] = overrides
    dest = _CUSTOM
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(custom, f, indent=2)
        f.write("\n")
    return dest


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Never raises. ready=True when built-in profiles load (always, unless broken)."""
    try:
        custom_path = _custom_path()
        custom = _load_custom()
        current = detect_game()
        current_cfg = get_game_config(current)
        builtin_count = len(_PROFILES)
        custom_count = sum(1 for v in custom.values() if isinstance(v, dict))

        missing: List[str] = []
        if not _CORE_CONFIG.is_file():
            missing.append("missing Core/config.json (detect_game falls back to Gaming)")

        # ready = module + built-ins usable (overrides optional)
        ready = builtin_count > 0

        info: Dict[str, Any] = {
            "checked_at": _iso(),
            "ready": ready,
            "partial": True,
            "readiness": "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "cli": "bolt game-config",
            "module": str(Path(__file__).resolve()),
            "core_config": str(_CORE_CONFIG),
            "core_config_present": _CORE_CONFIG.is_file(),
            "custom_path": str(custom_path),
            "custom_present": custom_path.is_file(),
            "custom_canonical": str(_CUSTOM),
            "legacy_custom_present": _LEGACY_CUSTOM.is_file(),
            "builtin_profile_count": builtin_count,
            "custom_override_count": custom_count,
            "current_game": current,
            "current_has_builtin": current.lower().strip() in _PROFILES,
            "current_has_override": current.lower().strip() in custom,
            "current_keys": sorted(current_cfg.keys()),
            "probe": bool(probe),
            "probe_ok": None,
            "error": "",
            "hint": (
                "built-in profiles always work · overrides in "
                "Data/configs/game_configs.json · distinct from PARTIAL "
                "bolt obs-game (scene→game) · stay PARTIAL"
            ),
            "is_stranger_ready": False,
            "missing": missing,
        }

        if not ready:
            info["error"] = _soft("built-in profiles empty")

        if probe:
            try:
                # Resolve one known profile + detect_game round-trip
                sample = get_game_config("valorant")
                info["probe_ok"] = bool(sample.get("spike_multiplier"))
                info["probe_sample_game"] = "valorant"
                info["probe_spike_multiplier"] = sample.get("spike_multiplier")
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
            "cli": "bolt game-config",
            "error": _soft(str(exc) or type(exc).__name__),
            "hint": "import/status failed",
            "is_stranger_ready": False,
            "probe": bool(probe),
            "probe_ok": False,
        }


def list_items() -> List[Dict[str, Any]]:
    st = status(probe=False)
    custom = _load_custom()
    rows: List[Dict[str, Any]] = []
    rows.append(
        {
            "id": "core_config",
            "ok": bool(st.get("core_config_present")),
            "detail": st.get("core_config") or str(_CORE_CONFIG),
        }
    )
    rows.append(
        {
            "id": "custom_overrides",
            "ok": bool(st.get("custom_present")),
            "detail": (
                f"{st.get('custom_path')} overrides={st.get('custom_override_count', 0)}"
            ),
        }
    )
    rows.append(
        {
            "id": "builtin_profiles",
            "ok": int(st.get("builtin_profile_count") or 0) > 0,
            "detail": f"{st.get('builtin_profile_count')} games",
        }
    )
    rows.append(
        {
            "id": "current_game",
            "ok": True,
            "detail": (
                f"{st.get('current_game')} "
                f"builtin={st.get('current_has_builtin')} "
                f"override={st.get('current_has_override')}"
            ),
        }
    )
    for name in sorted(_PROFILES.keys()):
        has_override = name in custom and isinstance(custom.get(name), dict)
        rows.append(
            {
                "id": f"profile:{name}",
                "ok": True,
                "detail": "builtin" + (" + override" if has_override else ""),
            }
        )
    for name, ov in sorted(custom.items()):
        if name in _PROFILES:
            continue
        if not isinstance(ov, dict):
            continue
        rows.append(
            {
                "id": f"override-only:{name}",
                "ok": True,
                "detail": f"custom keys={sorted(ov.keys())}",
            }
        )
    rows.append(
        {
            "id": "soft_fail",
            "ok": True,
            "detail": (
                f"prefix {_SOFT!r}; stay PARTIAL; distinct from PARTIAL bolt obs-game"
            ),
        }
    )
    return rows


def try_show(game: str = "") -> Dict[str, Any]:
    """Resolve merged config for a game. Never raises."""
    out: Dict[str, Any] = {
        "ok": False,
        "error": "",
        "game": "",
        "config": {},
        "has_builtin": False,
        "has_override": False,
        "source": "defaults",
    }
    try:
        name = (game or "").strip() or detect_game()
        key = name.lower().strip()
        custom = _load_custom()
        cfg = get_game_config(name)
        has_builtin = key in _PROFILES
        has_override = key in custom and isinstance(custom.get(key), dict)
        source = "defaults"
        if has_builtin and has_override:
            source = "builtin+override"
        elif has_builtin:
            source = "builtin"
        elif has_override:
            source = "override"
        out.update(
            {
                "ok": True,
                "game": name,
                "config": cfg,
                "has_builtin": has_builtin,
                "has_override": has_override,
                "source": source,
            }
        )
        return out
    except Exception as exc:
        out["error"] = _soft(str(exc) or type(exc).__name__)
        return out


def _parse_kv(pairs: List[str]) -> Dict[str, Any]:
    """Parse KEY=VALUE tokens; coerce bool/int/float when obvious."""
    out: Dict[str, Any] = {}
    for raw in pairs:
        if "=" not in raw:
            raise ValueError(f"expected KEY=VALUE, got {raw!r}")
        key, val = raw.split("=", 1)
        key = key.strip()
        val = val.strip()
        if not key:
            raise ValueError(f"empty key in {raw!r}")
        low = val.lower()
        if low in ("true", "yes", "on"):
            out[key] = True
        elif low in ("false", "no", "off"):
            out[key] = False
        else:
            try:
                if "." in val:
                    out[key] = float(val)
                else:
                    out[key] = int(val)
            except ValueError:
                out[key] = val
    return out


def try_set(game: str, pairs: List[str], *, merge: bool = True) -> Dict[str, Any]:
    """Write/merge custom overrides. Never raises."""
    out: Dict[str, Any] = {
        "ok": False,
        "error": "",
        "game": game,
        "path": str(_CUSTOM),
        "overrides": {},
    }
    try:
        key = (game or "").strip()
        if not key:
            out["error"] = _soft("empty game name")
            return out
        if not pairs:
            out["error"] = _soft("no KEY=VALUE pairs")
            return out
        new_ov = _parse_kv(pairs)
        if merge:
            existing = _load_custom().get(key.lower().strip())
            if isinstance(existing, dict):
                merged = dict(existing)
                merged.update(new_ov)
                new_ov = merged
        path = save_custom_config(key, new_ov)
        out["ok"] = True
        out["path"] = str(path)
        out["overrides"] = new_ov
        return out
    except Exception as exc:
        out["error"] = _soft(str(exc) or type(exc).__name__)
        return out


def _print_status(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, indent=2))
    else:
        ready = "yes" if info.get("ready") else "no"
        print(f"game-config readiness: {info.get('readiness')}  ready={ready}")
        print(f"  builtin profiles: {info.get('builtin_profile_count')}")
        print(
            f"  custom overrides: present={info.get('custom_present')}  "
            f"count={info.get('custom_override_count')}  path={info.get('custom_path')}"
        )
        print(f"  Core/config.json: present={info.get('core_config_present')}")
        print(
            f"  current game: {info.get('current_game')}  "
            f"builtin={info.get('current_has_builtin')}  "
            f"override={info.get('current_has_override')}"
        )
        if info.get("probe"):
            print(
                f"  probe_ok: {info.get('probe_ok')}  "
                f"sample={info.get('probe_sample_game')}  "
                f"spike={info.get('probe_spike_multiplier')}"
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
        prog="bolt game-config",
        description="Per-game sensitivity profiles (PARTIAL; soft-fail).",
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "list", "show", "set", "get"],
        help="status (default) | list | show | set (get = show alias)",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="status only: resolve a sample profile",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="set: replace overrides for the game instead of merging",
    )
    parser.add_argument(
        "rest",
        nargs="*",
        help="show: optional game name; set: game KEY=VALUE …",
    )
    args = parser.parse_args(argv)

    action = "show" if args.action == "get" else args.action

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

    if action == "show":
        game = " ".join(args.rest).strip()
        result = try_show(game)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if not result.get("ok"):
                print(result.get("error") or _soft("show failed"))
                return 0
            print(f"game: {result.get('game')}  source={result.get('source')}")
            cfg = result.get("config") or {}
            for k in sorted(cfg.keys()):
                print(f"  {k}: {cfg[k]}")
        return 0

    if action == "set":
        if not args.rest:
            msg = _soft("usage: bolt game-config set <game> KEY=VALUE …")
            if args.json:
                print(json.dumps({"ok": False, "error": msg}, indent=2))
            else:
                print(msg)
            return 0
        # First token(s) before KEY=VALUE are the game name
        game_parts: List[str] = []
        kv_parts: List[str] = []
        for tok in args.rest:
            if "=" in tok and not game_parts:
                # Unusual: first token is already KV — need a game
                kv_parts.append(tok)
            elif "=" in tok:
                kv_parts.append(tok)
            elif kv_parts:
                # Non-KV after KVs — treat as more game name? Unlikely; soft-fail
                kv_parts.append(tok)
            else:
                game_parts.append(tok)
        # If we collected KVs before any game token, error
        if kv_parts and not game_parts:
            # Re-parse: last chance — single-word game might be missing
            msg = _soft("set needs a game name before KEY=VALUE pairs")
            if args.json:
                print(json.dumps({"ok": False, "error": msg}, indent=2))
            else:
                print(msg)
            return 0
        # If no "=" yet, treat last as incomplete
        if not kv_parts:
            # Maybe: set "marvel rivals" spike_multiplier=2.4 — already split
            msg = _soft("set needs KEY=VALUE pairs")
            if args.json:
                print(json.dumps({"ok": False, "error": msg}, indent=2))
            else:
                print(msg)
            return 0
        game = " ".join(game_parts).strip()
        result = try_set(game, kv_parts, merge=not args.no_merge)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result.get("ok"):
                print(f"✓ Saved {game} overrides → {result.get('path')}")
                for k, v in sorted((result.get("overrides") or {}).items()):
                    print(f"  {k}: {v}")
            else:
                print(result.get("error") or _soft("set failed"))
        return 0

    print(_soft(f"unknown action {action!r}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
