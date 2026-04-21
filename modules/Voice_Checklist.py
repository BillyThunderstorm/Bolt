"""
Voice_Checklist.py — Bolt session task tracker with voice recognition
=======================================================================
Displays a pre-session checklist and listens for you to say tasks out loud.
When you say a task (or a keyword from it), Bolt marks it complete.

How the voice matching works:
  1. Mic picks up your voice continuously in a background thread
  2. Google Speech Recognition converts it to text (free, needs internet)
  3. Each spoken phrase is compared to every unchecked task using keyword matching
  4. If enough keywords match, the task gets marked ✅ and a sound plays
  5. When all tasks are done, Bolt congratulates you and exits

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

# ── Colours for the terminal ───────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
GRAY   = "\033[90m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT           = Path(__file__).parent.parent
TASKS_FILE     = ROOT / "session_tasks.json"
PROGRESS_FILE  = ROOT / "logs" / "checklist_progress.json"


# ── Default tasks (used if session_tasks.json doesn't exist) ──────────────────

DEFAULT_TASKS = [
    {
        "id":       "obs_setup",
        "task":     "Set up OBS — scenes, sources, audio levels",
        "keywords": ["obs", "scene", "audio", "levels", "setup", "set up"],
        "done":     False,
    },
    {
        "id":       "twitch_title",
        "task":     "Set Twitch title and game category",
        "keywords": ["title", "twitch", "game", "category", "set"],
        "done":     False,
    },
    {
        "id":       "streamlabs",
        "task":     "Check Streamlabs alerts are on",
        "keywords": ["streamlabs", "alerts", "donations", "alert"],
        "done":     False,
    },
    {
        "id":       "content_plan",
        "task":     "Review content plan for this session",
        "keywords": ["content", "plan", "review", "ideas", "session"],
        "done":     False,
    },
    {
        "id":       "tiktok_idea",
        "task":     "Pick a TikTok clip idea to aim for",
        "keywords": ["tiktok", "clip", "idea", "moment", "viral"],
        "done":     False,
    },
    {
        "id":       "socials",
        "task":     "Announce the stream on socials",
        "keywords": ["tweet", "post", "announced", "social", "twitter", "x", "instagram"],
        "done":     False,
    },
    {
        "id":       "test_stream",
        "task":     "Do a quick test stream check",
        "keywords": ["test", "check", "delay", "stream check", "quality"],
        "done":     False,
    },
]


# ── Main class ─────────────────────────────────────────────────────────────────

class VoiceChecklist:
    """
    Runs a voice-activated session checklist.

    Tasks come from session_tasks.json (or DEFAULT_TASKS if file doesn't exist).
    Say a task out loud → Bolt marks it done.
    """

    def __init__(self, tasks: list = None, use_voice: bool = True):
        self.tasks      = tasks or self._load_tasks()
        self.use_voice  = use_voice
        self._lock      = threading.Lock()
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
                return tasks
            except Exception as e:
                print(f"{YELLOW}Could not load session_tasks.json: {e} — using defaults{RESET}")

        return [dict(t) for t in DEFAULT_TASKS]   # copy so defaults aren't mutated

    def _save_progress(self):
        """Save current progress to logs so you can resume if Bolt crashes."""
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PROGRESS_FILE.write_text(json.dumps({
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tasks":    self.tasks,
        }, indent=2))

    # ── Display ────────────────────────────────────────────────────────────────

    def _print_checklist(self, clear: bool = True):
        """Render the checklist to the terminal."""
        if clear:
            # Move cursor up N lines instead of clearing whole screen
            lines = len(self.tasks) + 6
            sys.stdout.write(f"\033[{lines}A\033[J")

        done_count = sum(1 for t in self.tasks if t["done"])
        total      = len(self.tasks)

        print(f"\n{BOLD}{CYAN}  🦊 Bolt Pre-Session Checklist{RESET}  "
              f"{GRAY}({done_count}/{total} done){RESET}")
        print(f"  {GRAY}{'─' * 42}{RESET}")

        for t in self.tasks:
            if t["done"]:
                print(f"  {GREEN}✅  {t['task']}{RESET}")
            else:
                print(f"  {GRAY}○   {t['task']}{RESET}")

        print(f"\n  {GRAY}🎤 Say a task out loud to check it off  │  Ctrl+C to skip{RESET}\n")

    def _print_initial(self):
        """Print the checklist for the first time (no clear)."""
        done_count = sum(1 for t in self.tasks if t["done"])
        total      = len(self.tasks)

        print(f"\n{BOLD}{CYAN}  🦊 Bolt Pre-Session Checklist{RESET}  "
              f"{GRAY}({done_count}/{total} done){RESET}")
        print(f"  {GRAY}{'─' * 42}{RESET}")

        for t in self.tasks:
            if t["done"]:
                print(f"  {GREEN}✅  {t['task']}{RESET}")
            else:
                print(f"  {GRAY}○   {t['task']}{RESET}")

        print(f"\n  {GRAY}🎤 Say a task out loud to check it off  │  Ctrl+C to skip{RESET}\n")

    # ── Voice matching ─────────────────────────────────────────────────────────

    def _match_task(self, spoken: str) -> str | None:
        """
        Compare spoken text to all unchecked tasks.
        Returns the task ID if a match is found, else None.

        How matching works:
          - We split both the spoken phrase and the task's keywords into words
          - If 2+ keywords match, it's a hit (so you don't need to say it perfectly)
          - "OBS good" → matches "obs_setup" because "obs" is a keyword
        """
        spoken_lower = spoken.lower()
        spoken_words = set(spoken_lower.split())

        best_id    = None
        best_score = 0

        for task in self.tasks:
            if task["done"]:
                continue

            keywords = [kw.lower() for kw in task.get("keywords", [])]
            score    = 0

            for kw in keywords:
                if kw in spoken_lower:   # substring match (catches "streamlabs" inside longer phrase)
                    score += 1

            # Require at least 1 keyword match
            if score > best_score:
                best_score = score
                best_id    = task["id"]

        return best_id if best_score >= 1 else None

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
        """
        Manually mark a task done by typing part of its name.
        Useful when voice isn't available.
        """
        partial = partial_name.lower()
        for task in self.tasks:
            if partial in task["task"].lower() and not task["done"]:
                self.mark_done(task["id"])
                return True
        return False

    # ── Voice listener ─────────────────────────────────────────────────────────

    def _listen_loop(self):
        """
        Background thread — continuously listens to the mic and checks for matches.
        Uses Google Speech Recognition (free, needs internet).

        Why a background thread?
          So the main thread can do other things (or just show the checklist)
          while this runs silently in the background.
        """
        try:
            import speech_recognition as sr
        except ImportError:
            print(f"\n{YELLOW}  speech_recognition not installed.{RESET}")
            print(f"  Run:  pip3 install SpeechRecognition pyaudio --break-system-packages\n")
            print(f"  Falling back to keyboard mode — type task names instead.\n")
            self._keyboard_fallback()
            return

        recognizer = sr.Recognizer()
        recognizer.pause_threshold   = 0.6    # how long a pause ends a phrase
        recognizer.energy_threshold  = 300    # mic sensitivity (auto-adjusts)
        recognizer.dynamic_energy_threshold = True

        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)

            while self._listening and not self._done_event.is_set():
                try:
                    audio = recognizer.listen(source, timeout=5, phrase_time_limit=6)
                    text  = recognizer.recognize_google(audio)
                    print(f"  {GRAY}🎤 Heard: \"{text}\"{RESET}")

                    task_id = self._match_task(text)
                    if task_id:
                        self.mark_done(task_id)

                except sr.WaitTimeoutError:
                    pass    # no speech — just loop again
                except sr.UnknownValueError:
                    pass    # couldn't understand — loop again
                except sr.RequestError as e:
                    print(f"\n  {YELLOW}Speech API error: {e}{RESET}")
                    time.sleep(3)
                except Exception as e:
                    print(f"\n  {YELLOW}Listener error: {e}{RESET}")
                    time.sleep(1)

    def _keyboard_fallback(self):
        """
        If speech_recognition isn't installed, fall back to typing.
        Type part of a task name and press Enter to mark it done.
        """
        print(f"  {CYAN}Type part of a task name and press Enter to check it off.{RESET}")
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
                        self.mark_done(task_id)
                    else:
                        print(f"  {YELLOW}No matching task found for \"{text}\"{RESET}")
            except (EOFError, KeyboardInterrupt):
                self._done_event.set()
                break

    # ── Run ────────────────────────────────────────────────────────────────────

    def run(self, timeout_minutes: int = 15) -> list:
        """
        Show the checklist and start listening.
        Blocks until all tasks are done or timeout_minutes elapses.
        Returns the final task list.

        timeout_minutes: how long to wait before auto-continuing (default 15 min)
        """
        self._print_initial()
        self._listening  = True

        # Start voice listener in background
        if self.use_voice:
            listener = threading.Thread(target=self._listen_loop, daemon=True)
            listener.start()
        else:
            fallback = threading.Thread(target=self._keyboard_fallback, daemon=True)
            fallback.start()

        # Wait for completion or timeout
        timeout_sec = timeout_minutes * 60
        completed   = self._done_event.wait(timeout=timeout_sec)
        self._listening = False

        # Final message
        done_count = sum(1 for t in self.tasks if t["done"])
        total      = len(self.tasks)

        if completed:
            print(f"\n{GREEN}{BOLD}  🎉 All done! Let's get this stream started.{RESET}\n")
        else:
            print(f"\n{YELLOW}  ⏩ Skipping checklist — {done_count}/{total} tasks complete.{RESET}\n")

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
    parser.add_argument("--keyboard", action="store_true", help="Use keyboard instead of voice")
    parser.add_argument("--timeout",  type=int, default=15, help="Minutes before auto-skip (default 15)")
    args = parser.parse_args()

    checklist = VoiceChecklist(use_voice=not args.keyboard)

    try:
        checklist.run(timeout_minutes=args.timeout)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}  Checklist skipped.{RESET}\n")
