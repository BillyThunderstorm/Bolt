import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


CONFIG_PATH = Path(__file__).parent.parent / "config.json"
STATE_PATH  = Path(__file__).parent.parent / "data" / "brain_state.json"


class BrainController:
    def __init__(self):
        self.config = self._load_config()
        self.state = self._load_state()

    # ── State persistence ────────────────────────────────────────────
    def _load_config(self) -> dict:
        try:
            with open(CONFIG_PATH) as f:
                return json.load(f)
        except Exception:
            return {}

    def _load_state(self) -> dict:
        try:
            with open(STATE_PATH) as f:
                return json.load(f)
        except Exception:
            return {
                "last_session_end": None,
                "clips_posted_today": 0,
                "last_post_date": None,
                "session_count": 0,
            }

    def _save_state(self):
        STATE_PATH.parent.mkdir(exist_ok=True)
        with open(STATE_PATH, "w") as f:
            json.dump(self.state, f, indent=2)

    # ── The Decision Engine ──────────────────────────────────────────
    def decide(self, event: str, data: Dict[str, Any]) -> List[Dict]:
        """
        Main entry point. Given an event + data, return a list of actions.
        Each action is a dict: {"action": str, "data": dict}
        """
        handler = {
            "stream_started":   self._handle_stream_start,
            "stream_ended":     self._handle_stream_end,
            "highlight_found":  self._handle_highlight_found,
            "clip_ready":       self._handle_clip_ready,
            "peak_hour":        self._handle_peak_hour,
            "raid_received":    self._handle_raid,
            "donation_received":self._handle_donation,
        }.get(event)

        if not handler:
            return [{"action": "log", "data": {"msg": f"Unknown event: {event}"}}]

        return handler(data)

    # ── Event Handlers ───────────────────────────────────────────────
    def _handle_stream_start(self, data):
        self.state["session_count"] += 1
        self._save_state()
        return [
            {"action": "speak",       "data": {"line": "Bolt online. Let's go."}},
            {"action": "start_chat_bot", "data": {}},
            {"action": "begin_monitoring", "data": data},
        ]

    def _handle_stream_end(self, data):
        self.state["last_session_end"] = datetime.now().isoformat()
        self._save_state()
        return [
            {"action": "detect_highlights", "data": data},
            {"action": "stop_chat_bot",    "data": {}},
        ]

    def _handle_highlight_found(self, data):
        # Only generate clips if confidence is real, not noise
        if data.get("confidence", 0) < 0.4:
            return [{"action": "skip_highlight", "data": data}]
        return [{"action": "generate_clip", "data": data}]

    def _handle_clip_ready(self, data):
        score = data.get("score", 0)
        min_score = self.config.get("min_clip_score", 65)

        # Tier 1: Excellent clip — full pipeline
        if score >= 80:
            return [
                {"action": "generate_title",     "data": data},
                {"action": "generate_subtitles", "data": data},
                {"action": "format_vertical",    "data": data},
                {"action": "queue_for_posting",  "data": data},
                {"action": "speak", "data": {"line": "Got a banger."}},
            ]

        # Tier 2: Good enough — include but don't celebrate
        if score >= min_score:
            return [
                {"action": "generate_title",     "data": data},
                {"action": "generate_subtitles", "data": data},
                {"action": "format_vertical",    "data": data},
                {"action": "queue_for_posting",  "data": data},
            ]

        # Tier 3: Below threshold — archive instead of discard
        return [{"action": "archive_clip", "data": data}]

    def _handle_peak_hour(self, data):
        ready_clips = data.get("ready_clips", [])
        if not ready_clips:
            return [{"action": "log", "data": {"msg": "Peak hour but no clips ready"}}]
        return [
            {"action": "discord_notify", "data": {
                "msg": f"🚀 {len(ready_clips)} clips ready at peak hour.",
                "clips": ready_clips
            }}
        ]

    def _handle_raid(self, data):
        return [
            {"action": "speak", "data": {"line": f"Raid incoming from {data.get('from')}!"}},
            {"action": "chat_message", "data": {"msg": f"Welcome raiders! 💜"}},
            {"action": "mark_highlight", "data": {"reason": "raid"}},
        ]

    def _handle_donation(self, data):
        amount = data.get("amount", 0)
        return [
            {"action": "speak", "data": {"line": f"Thanks for the ${amount}!"}},
            {"action": "mark_highlight", "data": {"reason": "donation"}},
        ]


# ── Singleton + executor ─────────────────────────────────────────────
brain = BrainController()


def execute(action: Dict):
    """
    The bridge between Brain decisions and your existing modules.
    Add new mappings here as Bolt grows.
    """
    name = action["action"]
    data = action.get("data", {})

    # Lazy imports so Brain_Controller doesn't crash if a module is missing
    if name == "speak":
        from modules.Bolt_Voice import speak
        speak(data["line"])

    elif name == "detect_highlights":
        from modules.Highlight_Detector import detect_highlights
        detect_highlights(data["video_path"])

    elif name == "generate_clip":
        from modules.Clip_Generator import generate_clip
        generate_clip(data)

    elif name == "generate_title":
        from modules.Title_Generator import generate_title
        generate_title(data["clip_path"])

    elif name == "generate_subtitles":
        from modules.Subtitle_Generator import generate_subtitles
        generate_subtitles(data["clip_path"])

    elif name == "format_vertical":
        from modules.Clip_Factory import format_vertical
        format_vertical(data["clip_path"])

    elif name == "queue_for_posting":
        from modules.Post_Queue import add_to_queue
        add_to_queue(data)

    elif name == "discord_notify":
        from modules.Peak_Hour_Notifier import send_discord
        send_discord(data["msg"])

    elif name == "archive_clip":
        # Move to clips/_archive/ instead of deleting
        from pathlib import Path
        import shutil
        src = Path(data["clip_path"])
        dst = src.parent / "_archive" / src.name
        dst.parent.mkdir(exist_ok=True)
        if src.exists():
            shutil.move(str(src), str(dst))

    elif name == "log":
        print(f"[Brain] {data.get('msg')}")

    else:
        print(f"[Brain] No executor for action: {name}")


def main_loop(event: str, data: dict):
    """Call this from anywhere to send events to the Brain."""
    actions = brain.decide(event, data)
    for action in actions:
        execute(action)
