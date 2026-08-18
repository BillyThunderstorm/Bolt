#!/usr/bin/env python3
"""
bolt_day.py — Default morning / production kickoff
==================================================
Briefing, then optional hand-off into the real daily drivers:

  bolt day                 # brief + offer decide (TTY)
  bolt day --decide        # brief → queue decide immediately
  bolt day --voice         # brief → bolt voice
  bolt day --decide --voice  # decide first, then voice
  bolt day --quiet         # no TTS
  bolt day --open          # open next postable video during brief
  bolt day --process       # also process latest recording

Default morning flow we want:
  bolt day --decide
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
        _speech_queue.join()
    except Exception:
        pass


def _tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _prompt_yes(msg: str, *, default_yes: bool) -> bool:
    if not _tty():
        return False
    hint = "Y/n" if default_yes else "y/N"
    try:
        ans = input(f"  {msg} [{hint}]> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not ans:
        return default_yes
    return ans in {"y", "yes"}


def run_day(
    *,
    quiet: bool = False,
    open_next: bool = False,
    process: bool = False,
    decide: bool = False,
    voice: bool = False,
    offer: bool = True,
) -> int:
    tz_name = os.getenv("POSTING_TIMEZONE", "America/New_York")
    try:
        now = datetime.now(ZoneInfo(tz_name))
    except Exception:
        now = datetime.now()
        tz_name = "local"

    print()
    print("═" * 56)
    print("  BOLT DAY — morning / content kickoff")
    print(f"  {now.strftime('%A, %b %d · %I:%M %p')}  ({tz_name})")
    print("═" * 56)

    try:
        from modules.Week_Card import format_card

        print()
        print(format_card())
    except Exception as exc:
        print(f"\n  (week card unavailable: {exc})")

    is_peak = False
    peak_info = ""
    try:
        from modules.Peak_Hour_Notifier import (
            _is_peak_now,
            _print_actionable_table,
            show_next_clip,
        )

        is_peak, peak_info = _is_peak_now()
        print(f"\n  {'🔥 PEAK TIME' if is_peak else '💤 Off-peak'}  —  {peak_info}")
    except Exception as exc:
        print(f"\n  (peak window unavailable: {exc})")

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
            print(f"  ⚠  {s['missing']} ghost rows — run: bolt queue clean")
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
                print("  Default drivers:")
                print("    bolt queue decide     # review / retitle / approve / hold")
                print("    bolt voice            # hands-free ops")
                print("    bolt postnow          # publish #1")
                print("    bolt stats            # social pull status (TikTok/YouTube)")
        else:
            print("\n  No postable clips yet.")
            print("  → bolt recordings          # process latest recording")
            print("  → bolt queue add Clip.mp4  # register a hand-edited vertical")
    except Exception as exc:
        print(f"\n  Queue unavailable: {exc}")

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
        print(
            f"\n  Storage: {used_pct:.0f}% used, {free_gb:.0f} GB free  ·  "
            f"Recordings {rec_gb:.0f} GB"
        )
    except Exception:
        pass

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

    # Social stats readiness (one-liner — full: bolt stats)
    try:
        from modules.Social_Stats import readiness_summary

        print(f"  Social: {readiness_summary()}")
    except Exception:
        print("  Social: run bolt stats  (TikTok/YouTube performance pull)")

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
    print("  Morning flow:")
    print("    1. bolt day --decide            # this brief + queue review")
    print("    2. bolt voice                   # optional hands-free after")
    print("    3. bolt stats youtube --dry-run # YouTube metrics")
    print("       bolt log_perf                # TikTok / X views after you post")
    print()
    print("═" * 56)
    print()

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
        spoken += " Say queue decide, or run bolt day --decide."
    print(f"  🗣  {spoken}\n")
    _speak(spoken, quiet=quiet)

    # Offer interactive hand-offs (TTY only unless flags set)
    if offer and _tty() and not decide and not voice and postable > 0:
        decide = _prompt_yes("Start queue decide now?", default_yes=True)
        if not decide:
            voice = _prompt_yes("Start bolt voice instead?", default_yes=False)

    exit_code = 0

    if decide:
        print("\n  → Starting bolt queue decide…\n")
        _speak("Opening queue decide. Review each clip.", quiet=quiet)
        try:
            from modules.Peak_Hour_Notifier import interactive_decide

            n = interactive_decide(open_first=True)
            print(f"\n  decisions made: {n}")
        except Exception as exc:
            print(f"  queue decide failed: {exc}", file=sys.stderr)
            exit_code = 1

    if voice:
        print("\n  → Starting bolt voice…\n")
        _speak("Voice mode online. Say queue status or approve next.", quiet=quiet)
        try:
            import Bolt_Conversation as conv

            conv.conversation_loop(text_mode=False)
        except Exception as exc:
            print(f"  voice failed: {exc}", file=sys.stderr)
            print("  Tip: bolt voice --text", file=sys.stderr)
            exit_code = exit_code or 1

    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--help" in args or "-h" in args:
        print(__doc__)
        return 0
    quiet = "--quiet" in args or "-q" in args
    open_next = "--open" in args or "-o" in args
    process = "--process" in args
    decide = "--decide" in args or "--review" in args
    voice = "--voice" in args or "--listen" in args
    no_offer = "--no-offer" in args or not sys.stdin.isatty()
    return run_day(
        quiet=quiet,
        open_next=open_next,
        process=process,
        decide=decide,
        voice=voice,
        offer=not no_offer and not decide and not voice,
    )


if __name__ == "__main__":
    raise SystemExit(main())
