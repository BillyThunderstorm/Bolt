# config_loader.py
import json
from pathlib import Path

def load_config(config_path: str = "config.json"):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Config error: {e}")
        return {"game": "Gaming", "highlight_sensitivity": 0.7}  # defaults
