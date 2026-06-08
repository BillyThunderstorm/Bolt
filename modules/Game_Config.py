"""
Game Config
===========
Per-game sensitivity profiles. Merged priority:
  game_configs.json (user overrides) > built-in profiles > defaults
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()

_DEFAULTS = {
    "highlight_sensitivity": 0.7,
    "spike_multiplier":      2.8,
    "pad_before":            12.0,
    "pad_after":             20.0,
    "min_clip_score":        40.0,
    "tiktok_style":          "letterbox",
    "title_vibe":            "highlight",
    "game_events_enabled":   False,
}

_PROFILES = {
    "marvel rivals":     {"spike_multiplier": 2.4, "pad_before": 10, "pad_after": 18, "title_vibe": "kill", "game_events_enabled": True},
    "overwatch":         {"spike_multiplier": 2.5, "pad_before": 10, "pad_after": 18, "title_vibe": "skill"},
    "overwatch 2":       {"spike_multiplier": 2.5, "pad_before": 10, "pad_after": 18, "title_vibe": "skill"},
    "valorant":          {"spike_multiplier": 2.6, "pad_before": 12, "pad_after": 20, "title_vibe": "clutch"},
    "cs2":               {"spike_multiplier": 2.7, "pad_before": 12, "pad_after": 18, "title_vibe": "clutch"},
    "apex legends":      {"spike_multiplier": 2.4, "pad_before": 14, "pad_after": 22, "title_vibe": "win"},
    "fortnite":          {"spike_multiplier": 2.3, "pad_before": 12, "pad_after": 20, "title_vibe": "win"},
    "warzone":           {"spike_multiplier": 2.5, "pad_before": 14, "pad_after": 20, "title_vibe": "win"},
    "league of legends": {"spike_multiplier": 2.6, "pad_before": 15, "pad_after": 25, "title_vibe": "skill", "min_clip_score": 45},
    "dota 2":            {"spike_multiplier": 2.6, "pad_before": 15, "pad_after": 25, "title_vibe": "skill"},
    "minecraft":         {"spike_multiplier": 2.2, "pad_before": 10, "pad_after": 15, "title_vibe": "funny"},
    "phasmophobia":      {"spike_multiplier": 2.0, "pad_before": 8,  "pad_after": 15, "title_vibe": "funny"},
    "just chatting":     {"spike_multiplier": 3.5, "pad_before": 20, "pad_after": 30, "title_vibe": "reaction", "tiktok_style": "crop"},
}


def get_game_config(game_name: str = "") -> dict:
    cfg    = dict(_DEFAULTS)
    key    = game_name.lower().strip()
    if key in _PROFILES:
        cfg.update(_PROFILES[key])
    custom = _load_custom()
    if key in custom:
        cfg.update(custom[key])
    return cfg


def detect_game() -> str:
    name = os.getenv("GAME_NAME", "")
    if name:
        return name
    try:
        with open("config.json") as f:
            return json.load(f).get("game", "Gaming")
    except Exception:
        return "Gaming"


def save_custom_config(game_name: str, overrides: dict):
    custom = _load_custom()
    custom[game_name.lower()] = overrides
    with open("game_configs.json", "w") as f:
        json.dump(custom, f, indent=2)


def _load_custom() -> dict:
    if os.path.exists("game_configs.json"):
        try:
            with open("game_configs.json") as f:
                return json.load(f)
        except Exception:
            pass
    return {}
