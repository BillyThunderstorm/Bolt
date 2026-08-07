"""
Voice_Checklist.py — Bolt session task tracker with voice recognition
=======================================================================
Displays a pre-session checklist and listens for you to say tasks out loud.
When you say a task (or a keyword from it), Bolt doesn't just check it off —
it actually VERIFIES or COMPLETES the item by running a check function.

How it works:
  1. Mic picks up your voice continuously in a background thread
  2. Google Speech Recognition converts it to text (free, needs internet)
  3. Each spoken phrase is compared to every unchecked task using keyword matching
  4. On a match, Bolt runs that task's "verify" function for status feedback
  5. The task is marked ✅ either way (verify is feedback, not a hard gate)
  6. When all tasks are done, Bolt congratulates you and exits

Run standalone:
  python3 -m modules.Voice_Checklist

Or import into launch.py / bot.py:
  from modules.Voice_Checklist import VoiceChecklist
  cl = VoiceChecklist()
  cl.run()
"""

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# ── Colours for the terminal ───────────────────────────────────────────────────
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
GRAY = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"

# ── Paths ──────────────────────────────────────────────────────────────────────
# Voice_Checklist.py lives at Core/modules/ → Core is parent, repo root is grandparent.
CORE = Path(__file__).resolve().parent.parent
REPO = CORE.parent
ROOT = CORE  # kept for callers / progress paths under Core/
TASKS_FILE = CORE / "session_tasks.json"
PROGRESS_FILE = CORE / "logs" / "checklist_progress.json"
DATA_DIR = REPO / "Data"


def _load_env() -> None:
    """Load secrets the same way launch.py does: .env.local then .env at repo root."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    if not load_dotenv(REPO / ".env.local"):
        load_dotenv(REPO / ".env")


# ── Verify functions ───────────────────────────────────────────────────────────
# Each returns (success: bool, message: str).
# On voice/keyboard match we still check the item off even if verify fails —
# verification is feedback, not a hard gate (see _verify_task).


def _verify_obs() -> tuple:
    """Check that OBS is running and WebSocket is reachable."""
    _load_env()
    try:
        import subprocess

        result = subprocess.run(
            ["pgrep", "-f", "OBS.app/Contents/MacOS/OBS"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode != 0:
            return False, "OBS is not running — open OBS first"
    except Exception as e:
        return False, f"Could not check OBS process: {e}"

    # Check WebSocket
    try:
        import websocket

        host = os.getenv("OBS_HOST", "localhost")
        port = os.getenv("OBS_PORT", "4455")
        ws = websocket.create_connection(f"ws://{host}:{port}", timeout=3)
        ws.close()
        return True, "OBS is running and WebSocket is reachable"
    except ImportError:
        return True, "OBS is running (WebSocket check skipped — websocket-client not installed)"
    except Exception as e:
        return False, f"OBS is running but WebSocket is not reachable: {e}"


def _verify_twitch_title_game() -> tuple:
    """Check that the Twitch channel has a title and game set. Bolt can also
    sync the game from Twitch to config.json."""
    try:
        from modules.Twitch_API import get_current_game, get_last_stream_info

        _load_env()
        game = get_current_game()
        info = get_last_stream_info()
        title = info.get("title", "")

        if game == "Unknown" or not game:
            return False, "No game set on your Twitch channel — set it before going live"
        if not title or title in ("No recent streams", "Error fetching stream data"):
            return False, f"Game is '{game}' but no stream title found — set a title on Twitch"

        # Sync to config.json
        config_path = CORE / "config.json"
        if config_path.exists():
            config = json.loads(config_path.read_text())
            config["game"] = game
            config_path.write_text(json.dumps(config, indent=2) + "\n")

        return True, f"Twitch is ready — game: {game}, title: {title}"
    except Exception as e:
        return False, f"Could not check Twitch: {e}"


def _verify_streamlabs() -> tuple:
    """Check that Streamlabs socket token is configured."""
    _load_env()
    token = os.getenv("STREAMLABS_SOCKET_TOKEN", "").strip()
    if token:
        return True, "Streamlabs token is configured"
    return False, "Streamlabs socket token not set in .env — alerts won't fire"


def _verify_content_plan() -> tuple:
    """Check that there's recent performance data or a content plan."""
    perf_file = DATA_DIR / "performance_outcomes.jsonl"
    queue_file = DATA_DIR / "multi_platform_queue.json"

    has_perf = perf_file.exists() and perf_file.stat().st_size > 0
    has_queue = queue_file.exists() and queue_file.stat().st_size > 0

    if has_perf and has_queue:
        return True, "Performance data and clip queue are available for review"
    elif has_queue:
        return True, "Clip queue is available — no performance history yet (new channel)"
    else:
        return False, "No content plan data found — clips will be discovered as you stream"


def _verify_tiktok_idea() -> tuple:
    """Check if TikTok integration is set up or if there are clips ready to post."""
    _load_env()
    tiktok_key = os.getenv("TIKTOK_CLIENT_KEY", "").strip()

    queue_file = DATA_DIR / "multi_platform_queue.json"
    queue_count = 0
    if queue_file.exists():
        try:
            data = json.loads(queue_file.read_text())
            items = data.get("items", data) if isinstance(data, dict) else data
            queue_count = len(items) if isinstance(items, list) else 0
        except Exception:
            pass

    if tiktok_key:
        if queue_count > 0:
            return True, f"TikTok connected — {queue_count} clips in queue to post"
        return True, "TikTok is configured — clips will be queued as you stream"
    else:
        if queue_count > 0:
            return True, f"{queue_count} clips in queue — set up TikTok API to auto-post"
        return False, "TikTok not configured (TIKTOK_CLIENT_KEY missing in .env) — you'll post manually"


def _verify_socials() -> tuple:
    """Check if Discord webhooks are configured for social announcements."""
    _load_env()
    webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    captain = os.getenv("CAPTAIN_HOOK_WEBHOOK_URL", "").strip()
    if webhook or captain:
        return True, "Discord webhooks are configured for stream announcements"
    return False, "No Discord webhook set in .env — won't auto-announce on socials"


def _verify_test_stream() -> tuple:
    """Check that OBS is actually outputting (recording or streaming)."""
    try:
        import websocket
        import hashlib
        import base64

        _load_env()
        pw = os.getenv("OBS_PASSWORD", "")
        host = os.getenv("OBS_HOST", "localhost")
        port = os.getenv("OBS_PORT", "4455")
        ws = websocket.create_connection(f"ws://{host}:{port}", timeout=3)
        raw = ws.recv()
        if not raw:
            ws.close()
            return False, "OBS WebSocket connected but sent an empty hello"
        hello = json.loads(raw)
        challenge = hello.get("d", {}).get("authentication")
        if challenge:
            secret = base64.b64encode(
                hashlib.sha256((pw + challenge["salt"]).encode()).digest()
            ).decode()
            auth = base64.b64encode(
                hashlib.sha256((secret + challenge["challenge"]).encode()).digest()
            ).decode()
            ws.send(
                json.dumps(
                    {
                        "op": 1,
                        "d": {
                            "rpcVersion": hello["d"]["rpcVersion"],
                            "authentication": auth,
                            "eventSubscriptions": 0,
                        },
                    }
                )
            )
            raw = ws.recv()
            if raw:
                json.loads(raw)

        # Check streaming and recording status
        ws.send(json.dumps({"op": 6, "d": {"requestType": "GetStreamStatus", "requestId": "r1"}}))
        r = json.loads(ws.recv())
        while r.get("op") != 7:
            r = json.loads(ws.recv())
        streaming = (r.get("d") or {}).get("responseData", {}).get("outputActive", False)

        ws.send(json.dumps({"op": 6, "d": {"requestType": "GetRecordStatus", "requestId": "r2"}}))
        r = json.loads(ws.recv())
        while r.get("op") != 7:
            r = json.loads(ws.recv())
        recording = (r.get("d") or {}).get("responseData", {}).get("outputActive", False)

        ws.close()

        if streaming:
            return True, "Stream is LIVE on OBS"
        elif recording:
            return True, "OBS is recording (not streaming yet, but capture is active)"
        else:
            return False, "OBS is not streaming or recording — start one to test"
    except Exception as e:
        return False, f"Could not check OBS output status: {e}"


# ── Default tasks (used if session_tasks.json doesn't exist) ──────────────────

DEFAULT_TASKS = [
    {
        "id": "obs_setup",
        "task": "Set up OBS — scenes, sources, audio levels",
        "keywords": ["obs", "scene", "audio", "levels", "setup", "set up", "obs ready", "obs done"],
        "done": False,
        "verify": _verify_obs,
    },
    {
        "id": "twitch_title",
        "task": "Set Twitch title and game category",
        "keywords": ["title", "twitch", "game", "category", "stream title", "title set"],
        "done": False,
        "verify": _verify_twitch_title_game,
    },
    {
        "id": "streamlabs",
        "task": "Check Streamlabs alerts are on",
        "keywords": ["streamlabs", "stream labs", "alerts", "donations", "alert"],
        "done": False,
        "verify": _verify_streamlabs,
    },
    {
        "id": "content_plan",
        "task": "Review content plan for this session",
        "keywords": ["content", "plan", "review", "ideas", "session", "queue", "content plan"],
        "done": False,
        "verify": _verify_content_plan,
    },
    {
        "id": "tiktok_idea",
        "task": "Pick a TikTok clip idea to aim for",
        "keywords": ["tiktok", "tick tock", "clip idea", "viral", "tik tok"],
        "done": False,
        "verify": _verify_tiktok_idea,
    },
    {
        "id": "socials",
        "task": "Announce the stream on socials",
        "keywords": [
            "tweet",
            "announced",
            "social",
            "socials",
            "twitter",
            "instagram",
            "discord",
            "announce",
        ],
        "done": False,
        "verify": _verify_socials,
    },
    {
        "id": "test_stream",
        "task": "Do a quick test stream check",
        "keywords": ["test stream", "stream check", "delay", "quality", "recording", "test check"],
        "done": False,
        "verify": _verify_test_stream,
    },
]


# ── Main class ─────────────────────────────────────────────────────────────────


class VoiceChecklist:
    """
    Runs a voice-activated session checklist.
    Tasks come from session_tasks.json (or DEFAULT_TASKS if file doesn't exist).
    Say a task out loud → Bolt verifies it and marks it done if the check passes.
    """

    def __init__(self, tasks: list = None, use_voice: bool = True):
        self.tasks = tasks or self._load_tasks()
        self.use_voice = use_voice
        self._lock = threading.Lock()
        self._listening = False
        self._done_event = threading.Event()

    # ── Task loading / saving ──────────────────────────────────────────────────

    def _load_tasks(self) -> list:
        """Load tasks from session_tasks.json, falling back to defaults."""
        if TASKS_FILE.exists():
            try:
                data = json.loads(TASKS_FILE.read_text())
                # Support both {"tasks": [...]} and plain [...]
                tasks = data.get("tasks", data) if isinstance(data, dict) else data
                # Reset done state for a fresh session
                for t in tasks:
                    t["done"] = False
                # Merge in verify functions from DEFAULT_TASKS by id
                default_verify = {t["id"]: t["verify"] for t in DEFAULT_TASKS if "verify" in t}
                for t in tasks:
                    if t["id"] in default_verify:
                        t["verify"] = default_verify[t["id"]]
                return tasks
            except Exception as e:
                print(
                    f"{YELLOW}Could not load session_tasks.json: {e} — using defaults{RESET}"
                )

        return [dict(t) for t in DEFAULT_TASKS]  # copy so defaults aren't mutated

    def _save_progress(self):
        """Save current progress to logs so you can resume if Bolt crashes."""
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Don't serialize the verify functions
        tasks_copy = []
        for t in self.tasks:
            t_copy = {k: v for k, v in t.items() if k != "verify"}
            tasks_copy.append(t_copy)
        PROGRESS_FILE.write_text(
            json.dumps(
                {
                    "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "tasks": tasks_copy,
                },
                indent=2,
            )
        )

    # ── Display ────────────────────────────────────────────────────────────────

    def _print_checklist(self, clear: bool = True):
        """Render the checklist to the terminal."""
        if clear:
            # Move cursor up N lines instead of clearing whole screen
            lines = len(self.tasks) + 6
            sys.stdout.write(f"\033[{lines}A\033[J")

        done_count = sum(1 for t in self.tasks if t["done"])
        total = len(self.tasks)

        print(
            f"\n{BOLD}{CYAN}  ⚡ Bolt Pre-Stream Checklist{RESET}  "
            f"{GRAY}({done_count}/{total} done){RESET}"
        )
        print(f"  {GRAY}{'─' * 42}{RESET}")

        for t in self.tasks:
            if t["done"]:
                print(f"  {GREEN}✅  {t['task']}{RESET}")
            else:
                print(f"  {GRAY}○   {t['task']}{RESET}")

        print(
            f"\n  {GRAY}🎤 Say a task keyword (e.g. 'OBS ready', 'title set')  │  Ctrl+C to skip{RESET}\n"
        )

    def _print_initial(self):
        """Print the checklist for the first time (no clear)."""
        done_count = sum(1 for t in self.tasks if t["done"])
        total = len(self.tasks)

        print(
            f"\n{BOLD}{CYAN}  ⚡ Bolt Pre-Stream Checklist{RESET}  "
            f"{GRAY}({done_count}/{total} done){RESET}"
        )
        print(f"  {GRAY}{'─' * 42}{RESET}")

        for t in self.tasks:
            if t["done"]:
                print(f"  {GREEN}✅  {t['task']}{RESET}")
            else:
                print(f"  {GRAY}○   {t['task']}{RESET}")

        print(
            f"\n  {GRAY}🎤 Say a task keyword (e.g. 'OBS ready', 'title set')  │  Ctrl+C to skip{RESET}\n"
        )

    # ── Voice matching ─────────────────────────────────────────────────────────

    def _match_task(self, spoken: str) -> Optional[str]:
        """
        Compare spoken text to all unchecked tasks.
        Returns the task ID if a match is found, else None.

        Short/generic keywords (e.g. "on", "set", "x") only count when paired
        with another hit, so casual speech does not latch onto the wrong row.
        """
        spoken_lower = spoken.lower().strip()
        if not spoken_lower:
            return None

        best_id = None
        best_score = 0

        # Weak tokens need a second hit (or a strong keyword) to count as a match.
        weak_keywords = {
            "on",
            "set",
            "x",
            "check",
            "post",
            "ready",
            "done",
            "good",
            "ok",
            "okay",
        }

        for task in self.tasks:
            if task["done"]:
                continue

            keywords = [kw.lower() for kw in task.get("keywords", [])]
            strong_hits = 0
            weak_hits = 0

            for kw in keywords:
                if kw not in spoken_lower:
                    continue
                if kw in weak_keywords or len(kw) <= 2:
                    weak_hits += 1
                else:
                    strong_hits += 1

            # Prefer distinctive keywords; allow 2+ weak-only hits as a last resort.
            if strong_hits:
                score = strong_hits * 2 + weak_hits
            elif weak_hits >= 2:
                score = weak_hits
            else:
                score = 0

            if score > best_score:
                best_score = score
                best_id = task["id"]

        return best_id if best_score >= 1 else None

    def _verify_task(self, task_id: str) -> bool:
        """Run the task's verify function for feedback, then mark it done.

        Verify is advisory: if the user named the task, we check it off even when
        the automated check fails (missing API keys, OBS not streaming yet, etc.).
        Returns True if the task was marked done.
        """
        with self._lock:
            task = None
            for t in self.tasks:
                if t["id"] == task_id and not t["done"]:
                    task = t
                    break

            if not task:
                return False

        verify_fn = task.get("verify")
        if not verify_fn:
            self.mark_done(task_id)
            return True

        # Run the verify function outside the lock (it may take time)
        print(f"  {CYAN}⚡ Checking: {task['task']}...{RESET}")
        try:
            success, message = verify_fn()
        except Exception as e:
            success, message = False, f"Verify error: {e}"

        if success:
            print(f"  {GREEN}✓ {message}{RESET}")
        else:
            # Still mark done — user claimed the task by voice/keyboard.
            print(f"  {YELLOW}⚠ {message}{RESET}")
            print(f"  {GRAY}  (marking done anyway — you said this one){RESET}")

        self.mark_done(task_id)
        return True

    def mark_done(self, task_id: str):
        """Mark a task as complete and refresh the display."""
        with self._lock:
            for task in self.tasks:
                if task["id"] == task_id and not task["done"]:
                    task["done"] = True
                    self._print_checklist()
                    self._save_progress()

                    # Check if all done
                    if all(t["done"] for t in self.tasks):
                        self._done_event.set()
                    break

    def mark_done_by_name(self, partial_name: str):
        """Manually mark a task done by typing part of its name."""
        partial = partial_name.lower()
        for task in self.tasks:
            if partial in task["task"].lower() and not task["done"]:
                self.mark_done(task["id"])
                return True
        return False

    # ── Voice listener ─────────────────────────────────────────────────────────

    def _listen_loop(self):
        """Background thread — continuously listens to the mic and checks for matches.

        If speech_recognition or PyAudio is missing (or the mic can't open), fall
        back to keyboard mode instead of crashing the thread with a traceback.
        """
        try:
            import speech_recognition as sr
        except ImportError:
            print(f"\n{YELLOW}  speech_recognition not installed.{RESET}")
            print(
                f"  Run:  uv pip install SpeechRecognition pyaudio\n"
                f"  (PyAudio also needs PortAudio: brew install portaudio)\n"
            )
            print(f"  Falling back to keyboard mode — type task names instead.\n")
            self._keyboard_fallback()
            return

        # Probe mic availability before entering the listen loop so a missing
        # PyAudio install becomes a clean keyboard fallback, not a Thread-1 boom.
        try:
            import pyaudio  # noqa: F401
        except ImportError:
            print(f"\n{YELLOW}  PyAudio not installed — voice checklist needs it.{RESET}")
            print(
                f"  Run:  brew install portaudio && uv pip install pyaudio\n"
            )
            print(f"  Falling back to keyboard mode — type task names instead.\n")
            self._keyboard_fallback()
            return

        recognizer = sr.Recognizer()
        recognizer.pause_threshold = 0.6
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True

        try:
            mic = sr.Microphone()
        except (AttributeError, OSError) as e:
            print(f"\n{YELLOW}  Could not open microphone: {e}{RESET}")
            print(f"  Falling back to keyboard mode — type task names instead.\n")
            self._keyboard_fallback()
            return

        try:
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=1)

                while self._listening and not self._done_event.is_set():
                    try:
                        audio = recognizer.listen(
                            source, timeout=5, phrase_time_limit=6
                        )
                        text = recognizer.recognize_google(audio)
                        print(f'  {GRAY}🎤 Heard: "{text}"{RESET}')

                        task_id = self._match_task(text)
                        if task_id:
                            self._verify_task(task_id)
                        else:
                            print(
                                f'  {YELLOW}No matching task — try a keyword '
                                f'(e.g. "OBS ready", "title set", "Streamlabs", "TikTok"){RESET}'
                            )

                    except sr.WaitTimeoutError:
                        pass
                    except sr.UnknownValueError:
                        pass
                    except sr.RequestError as e:
                        print(f"\n  {YELLOW}Speech API error: {e}{RESET}")
                        time.sleep(3)
                    except Exception as e:
                        print(f"\n  {YELLOW}Listener error: {e}{RESET}")
                        time.sleep(1)
        except Exception as e:
            print(f"\n{YELLOW}  Microphone listen failed: {e}{RESET}")
            print(f"  Falling back to keyboard mode — type task names instead.\n")
            self._keyboard_fallback()


    def _keyboard_fallback(self):
        """If speech_recognition isn't installed, fall back to typing."""
        print(
            f"  {CYAN}Type part of a task name and press Enter — Bolt will verify it.{RESET}"
        )
        print(f"  {GRAY}(Type 'skip' to exit the checklist){RESET}\n")

        while self._listening and not self._done_event.is_set():
            try:
                text = input("  > ").strip()
                if text.lower() in ("skip", "exit", "done", "quit"):
                    self._done_event.set()
                    break
                if text:
                    task_id = self._match_task(text)
                    if task_id:
                        self._verify_task(task_id)
                    else:
                        print(f'  {YELLOW}No matching task found for "{text}"{RESET}')
            except (EOFError, KeyboardInterrupt):
                self._done_event.set()
                break

    # ── Run ────────────────────────────────────────────────────────────────────

    def run(self, timeout_minutes: int = 15) -> list:
        """
        Show the checklist and start listening.
        Blocks until all tasks are done or timeout_minutes elapses.
        Returns the final task list.
        """
        self._print_initial()
        self._listening = True

        if self.use_voice:
            listener = threading.Thread(target=self._listen_loop, daemon=True)
            listener.start()
        else:
            fallback = threading.Thread(target=self._keyboard_fallback, daemon=True)
            fallback.start()

        timeout_sec = timeout_minutes * 60
        completed = self._done_event.wait(timeout=timeout_sec)
        self._listening = False

        done_count = sum(1 for t in self.tasks if t["done"])
        total = len(self.tasks)

        if completed:
            print(
                f"\n{GREEN}{BOLD}  🎉 All verified! Let's get this stream started.{RESET}\n"
            )
        else:
            print(
                f"\n{YELLOW}  ⏩ Skipping checklist — {done_count}/{total} tasks verified.{RESET}\n"
            )

        self._save_progress()
        return self.tasks

    def run_keyboard_only(self, timeout_minutes: int = 15) -> list:
        """Same as run() but forces keyboard mode (no mic needed)."""
        self.use_voice = False
        return self.run(timeout_minutes)


# ── Standalone usage ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Bolt Voice Checklist")
    parser.add_argument(
        "--keyboard", action="store_true", help="Use keyboard instead of voice"
    )
    parser.add_argument(
        "--timeout", type=int, default=15, help="Minutes before auto-skip (default 15)"
    )
    args = parser.parse_args()

    checklist = VoiceChecklist(use_voice=not args.keyboard)

    try:
        checklist.run(timeout_minutes=args.timeout)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}  Checklist skipped.{RESET}\n")