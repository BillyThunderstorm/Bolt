# modules/Config_Loader.py

import json
from pathlib import Path

DEFAULT_CONFIG = {
    "game": "Gaming",
    "highlight_sensitivity": 0.7,
    "recordings_folder": "media/Recordings",
    "clips_folder": "media/clips",
    "vertical_clips_folder": "media/vertical_clips",
    "use_brain": True,
    "use_voice": True,
    "use_twitch": False,
}


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_config(config_path: str | None = None) -> dict:
    root = get_project_root()
    path = Path(config_path) if config_path else root / "config.json"

    if not path.exists():
        print(f"⚠️ config.json not found. Creating default config at: {path}")
        save_config(DEFAULT_CONFIG, path)
        return DEFAULT_CONFIG.copy()

    try:
        with path.open("r", encoding="utf-8") as f:
            user_config = json.load(f)

        config = DEFAULT_CONFIG.copy()
        config.update(user_config)
        return config

    except json.JSONDecodeError as e:
        print(f"❌ config.json is broken JSON: {e}")
        print("Using default config so Bolt does not collapse like a folding chair.")
        return DEFAULT_CONFIG.copy()

    except Exception as e:
        print(f"❌ Config error: {e}")
        return DEFAULT_CONFIG.copy()


def save_config(config: dict, config_path: str | Path | None = None) -> None:
    root = get_project_root()
    path = Path(config_path) if config_path else root / "config.json"

    with path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


def get_config_value(key: str, default=None):
    config = load_config()
    return config.get(key, default)
