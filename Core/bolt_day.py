#!/usr/bin/env python3
"""
bolt_day.py — One-command daily kickoff for content production
==============================================================
Prints (and optionally speaks) a short ops briefing:
  greeting → peak window → queue table → next clip → storage → budget

Usage:
  bolt day
  bolt day --quiet          # no TTS
  bolt day --open           # open next postable video
  bolt day --process        # also run recordings latest (can take a while)

Tonight path after this:
  bolt queue decide
  bolt postnow              # when ready to publish
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_CORE = Path(__file__).resolve().parent
_REPO = _CORE.parent
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))
os.chdir(_REPO)


def _speak(text: str, quiet: bool) -> None:
    if quiet:
        return
    try:
        from modules.Bolt_Voice import speak, _speech_queue

        speak(text)
        # Don't block forever on long days — join with care
        _speech_queue.join()
    except Exception:
        pass


def run_day(*, quiet: bool = False, open_next: bool = False, process: bool = False) -> int:
    tz_name = os.getenv("POSTING_TIMEZONE", "America/New_York")
    try:
        now = datetime.now(ZoneInfo(tz_name))
    except Exception:
        now = datetime.now()
        tz_name = "local"

    print()
    print("═" * 56)
    print("  BOLT DAY — content kickoff")
    print(f"  {now.strftime('%A, %b %d · %I:%M %p')}  ({tz_name})")
    print("═" * 56)

    # Peak window
    is_peak = False
    peak_info = ""
    try:
        from modules.Peak_Hour_Notifier import _is_peak_now, _print_actionable_table, show_next_clip

        is_peak, peak_info = _is_peak_now()
        print(f"\n  {'🔥 PEAK TIME' if is_peak else '💤 Off-peak'}  —  {peak_info}")
    except Exception as exc:
        print(f"\n  (peak window unavailable: {exc})")

    # Queue
    postable = 0
    next_title = ""
    try:
        from modules.Peak_Hour_Notifier import queue_summary, _actionable_clips

        s = queue_summary()
        clips = _actionable_clips()
        postable = len(clips)
        print(
            f"\n  Queue: {postable} postable  ·  "
            f"{s.get('approved', 0)} approved  ·  "
            f"{s.get('awaiting_approval', 0)} awaiting  ·  "
            f"{s.get('posted', 0)} posted"
        )
        if s.get("missing"):
            print(
                f"  ⚠  {s['missing']} ghost rows — run: bolt queue clean"
            )
        if clips:
            print()
            _print_actionable_table(limit=8)
            next_title = clips[0].get("title") or Path(
                clips[0].get("clip_path") or ""
            ).name
            print()
            if open_next:
                show_next_clip(open_video=True)
            else:
                print("  Next step:  bolt queue decide")
                print("             bolt queue next --open")
                print("             bolt postnow          # publish #1 now")
        else:
            print("\n  No postable clips yet.")
            print("  → bolt recordings          # process latest recording")
            print("  → bolt queue add Clip.mp4  # register a hand-edited vertical")
    except Exception as exc:
        print(f"\n  Queue unavailable: {exc}")

    # Storage one-liner
    try:
        import shutil

        u = shutil.disk_usage(_REPO)
        free_gb = u.free / (1024**3)
        used_pct = 100 * u.used / u.total if u.total else 0
        rec = _REPO / "media" / "Recordings"
        rec_gb = 0.0
        if rec.exists():
            import subprocess

            out = subprocess.check_output(["du", "-sk", str(rec)], text=True)
            rec_gb = float(out.split()[0]) / (1024 * 1024)
        print(f"\n  Storage: {used_pct:.0f}% used, {free_gb:.0f} GB free  ·  Recordings {rec_gb:.0f} GB")
    except Exception:
        pass

    # Budget one-liner
    try:
        from modules.XAI_Usage import status_dict
        from modules.LLM_Budget import llm_mode

        st = status_dict()
        cap = st.get("cap_usd")
        spent = st.get("spend_usd") or 0
        if cap:
            print(f"  API: mode={llm_mode()}  ·  ${spent:.2f} of ${cap:.0f} soft cap")
        else:
            print(f"  API: mode={llm_mode()}  ·  ${spent:.2f} spent (no cap)")
    except Exception:
        pass

    # Optional process
    if process:
        print("\n  Processing latest recording…")
        import subprocess

        py = sys.executable
        rc = subprocess.call(
            [py, str(_REPO / "scripts" / "process_recordings.py"), "latest"],
            cwd=str(_REPO),
        )
        if rc != 0:
            print(f"  recordings exit {rc}")

    print()
    print("  Tonight produce path:")
    print("    1. bolt recordings          # if you have a new session file")
    print("    2. bolt queue decide        # review / retitle / approve / hold")
    print("    3. bolt postnow             # when a clip is ready to go live")
    print("    4. bolt voice               # hands-free ops (optional)")
    print()
    print("═" * 56)
    print()

    # Spoken summary + short real plan (not LLM fiction)
    try:
        from modules.Intent_Router import _action_day

        spoken = _action_day()
    except Exception:
        spoken = (
            f"Hey William! Bolt day kickoff. "
            f"{'Peak posting window is open. ' if is_peak else 'Off peak right now. '}"
            f"You have {postable} postable clips."
        )
        if next_title:
            spoken += f" Next up: {next_title}."
        spoken += " Run bolt queue decide to review, or bolt postnow when you're ready."
    print(f"  🗣  {spoken}\n")
    _speak(spoken, quiet=quiet)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    quiet = "--quiet" in args or "-q" in args
    open_next = "--open" in args or "-o" in args
    process = "--process" in args
    if "--help" in args or "-h" in args:
        print(__doc__)
        return 0
    return run_day(quiet=quiet, open_next=open_next, process=process)


if __name__ == "__main__":
    raise SystemExit(main())
