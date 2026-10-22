#!/usr/bin/env python3
"""
BOLT QUICK HEALTH CHECK
=======================
A few-second "is Bolt ready to make clips right now?" check. Every line is
OK / WARN / FAIL and every WARN or FAIL says exactly how to fix it.

Checks (all local; the only network call is a 2 s ping to Ollama on this Mac):
  1. Files Bolt needs (config, bot, launcher, creator profile, settings)
  2. Folders (recordings, clips, verticals, Data, memory, logs)
  3. Tools: a working ffmpeg + ffprobe (clips can't be cut without them),
     Whisper for captions (Python package or the Mac's whisper CLI)
  4. Python packages the clip pipeline imports
  5. Bolt pipeline modules import cleanly
  6. Core/config.json loads (shows the current game)
  7. AI for titles/chat: Grok key, Ollama running, OpenAI key (fallback)
  8. Disk space free

Settings are read like the rest of Bolt: .env.local first, then .env
(first value wins; works without python-dotenv).

For the full live/mocked/stale audit of every feature use ``bolt doctor``.

Usage:
  bolt health run [--json]
  python3 scripts/health_check.py [--json]
Exit code 0 = no FAIL lines (warnings allowed), 1 = something must be fixed.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import (  # noqa: E402
    REPO_ROOT,
    CORE_DIR,
    MODULES_DIR,
    DATA_DIR,
    MEDIA_DIR,
    CLIPS_DIR,
    VERTICAL_CLIPS_DIR,
    RECORDINGS_DIR,
    MEMORY_DIR,
    MEMORY_HOT_FILE,
    CONFIG_FILE,
    BOT_FILE,
    BOLT_BRAIN_FILE,
    LOGS_DIR,
)

LAUNCH_FILE = CORE_DIR / "launch.py"
ENV_LOCAL_FILE = REPO_ROOT / ".env.local"
ENV_FILE = REPO_ROOT / ".env"

DISK_WARN_GB = 20.0
DISK_FAIL_GB = 5.0

_PLACEHOLDER_MARKERS = ("sk_your", "your_", "changeme", "xxx")


# ── settings ────────────────────────────────────────────────────────────────

def _parse_env_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if " #" in val and not val.startswith(("'", '"')):
            val = val.split(" #", 1)[0].strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if key:
            out[key] = val
    return out


def load_settings(files: Optional[List[Path]] = None) -> List[str]:
    """Load .env.local then .env into os.environ (existing values win).

    Returns the list of files that were read.
    """
    files = files if files is not None else [ENV_LOCAL_FILE, ENV_FILE]
    read: List[str] = []
    for path in files:
        if not path.is_file():
            continue
        read.append(path.name)
        for key, val in _parse_env_file(path).items():
            if key not in os.environ or not os.environ.get(key, "").strip():
                os.environ[key] = val
    return read


def _is_set(key: str) -> bool:
    val = os.environ.get(key, "").strip()
    if not val:
        return False
    low = val.lower()
    return not any(m in low for m in _PLACEHOLDER_MARKERS)


# ── result collection ───────────────────────────────────────────────────────

class Report:
    def __init__(self) -> None:
        self.sections: List[Dict[str, Any]] = []

    def section(self, title: str) -> None:
        self.sections.append({"title": title, "checks": []})

    def add(self, state: str, name: str, detail: str = "", fix: str = "") -> None:
        if not self.sections:
            self.section("Checks")
        self.sections[-1]["checks"].append(
            {"state": state, "name": name, "detail": detail, "fix": fix}
        )

    def all_checks(self) -> List[Dict[str, Any]]:
        return [c for s in self.sections for c in s["checks"]]

    def counts(self) -> Dict[str, int]:
        c = {"OK": 0, "WARN": 0, "FAIL": 0}
        for chk in self.all_checks():
            c[chk["state"]] = c.get(chk["state"], 0) + 1
        return c


def _quiet(fn: Callable[[], Any]) -> Any:
    """Run fn with its prints swallowed (module imports can be chatty)."""
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return fn()


# ── individual checks ───────────────────────────────────────────────────────

def check_files(r: Report) -> None:
    r.section("Files Bolt needs")
    required = [
        (CONFIG_FILE, "Settings (Core/config.json)", True,
         "Restore Core/config.json from git: git checkout Core/config.json"),
        (BOT_FILE, "Clip pipeline (Core/bot.py)", True,
         "Restore it from git: git checkout Core/bot.py"),
        (LAUNCH_FILE, "Launcher (Core/launch.py)", True,
         "Restore it from git: git checkout Core/launch.py"),
        (BOLT_BRAIN_FILE, "Creator profile (Core/bolt_brain.md)", False,
         "Optional — titles/chat get less personal without it."),
        (MEMORY_HOT_FILE, "Hot memory (Data/MEMORY.md)", False,
         "Optional — run: bolt refresh-memory run"),
    ]
    for path, label, needed, fix in required:
        if path.is_file():
            r.add("OK", label, f"{path.stat().st_size:,} bytes")
        else:
            r.add("FAIL" if needed else "WARN", label, "missing", fix)
    if ENV_LOCAL_FILE.is_file() or ENV_FILE.is_file():
        names = [p.name for p in (ENV_LOCAL_FILE, ENV_FILE) if p.is_file()]
        r.add("OK", "Keys file", " + ".join(names) + " (.env.local wins)")
    else:
        r.add("WARN", "Keys file", "no .env.local or .env",
              "Copy .env.example to .env.local and add your keys.")


def check_dirs(r: Report) -> None:
    r.section("Folders")
    dirs = [
        (MODULES_DIR, "Core/modules", True),
        (RECORDINGS_DIR, "media/Recordings (OBS recordings in)", False),
        (CLIPS_DIR, "media/clips (finished clips)", False),
        (VERTICAL_CLIPS_DIR, "media/vertical_clips (9:16)", False),
        (DATA_DIR, "Data", True),
        (MEMORY_DIR, "Data/memory", False),
        (LOGS_DIR, "logs", False),
    ]
    for path, label, needed in dirs:
        if path.is_dir():
            try:
                n = sum(1 for p in path.iterdir() if not p.name.startswith("."))
            except OSError:
                n = 0
            r.add("OK", label, f"{n} items")
        elif needed:
            r.add("FAIL", label, "missing", f"Restore from git: git checkout {path.relative_to(REPO_ROOT)}")
        else:
            r.add("WARN", label, "missing",
                  f"Create it: mkdir -p \"{path}\" (Bolt also makes it on first use)")


def check_tools(r: Report) -> None:
    r.section("Tools")
    try:
        from modules import FFmpeg_Bin  # type: ignore

        ff = FFmpeg_Bin.working_ffmpeg()
        if ff:
            r.add("OK", "ffmpeg (cuts clips)", ff)
            probe = FFmpeg_Bin.ffprobe_bin()
            if probe and FFmpeg_Bin._works(probe):  # noqa: SLF001
                r.add("OK", "ffprobe (reads recordings)", probe)
            else:
                r.add("FAIL", "ffprobe (reads recordings)", "no working ffprobe",
                      "brew reinstall ffmpeg-full (ffprobe ships with it)")
        else:
            r.add("FAIL", "ffmpeg (cuts clips)", "no ffmpeg that starts",
                  "brew install ffmpeg-full (or set BOLT_FFMPEG=/path/to/ffmpeg in .env.local)")
    except Exception as exc:  # pragma: no cover - defensive
        r.add("FAIL", "ffmpeg (cuts clips)", f"check failed: {exc}", "Run: bolt doctor")

    try:
        from modules import Subtitle_Generator  # type: ignore

        backend = _quiet(Subtitle_Generator.whisper_backend)
        if backend == "module":
            r.add("OK", "Whisper (captions)", "Python package in Bolt's venv")
        elif backend and backend.startswith("cli:"):
            r.add("OK", "Whisper (captions)", f"Mac whisper CLI {backend[4:]}")
        else:
            r.add("WARN", "Whisper (captions)", "not found — clips are made without captions",
                  "uv sync --extra subtitles  (or pip3 install openai-whisper for a Mac-wide CLI)")
    except Exception as exc:
        r.add("WARN", "Whisper (captions)", f"check failed: {exc}",
              "uv sync --extra subtitles")


def check_packages(r: Report) -> None:
    r.section("Python packages")
    deps = [
        ("requests", "web requests", True),
        ("numpy", "audio/video math", True),
        ("librosa", "audio highlight detection", True),
        ("cv2", "video frames (OpenCV)", False),
        ("moviepy", "video editing helpers", False),
        ("openai", "Grok/OpenAI client", False),
        ("twitchio", "Twitch chat bot", False),
    ]
    for module, desc, needed in deps:
        try:
            _quiet(lambda m=module: __import__(m))
            r.add("OK", module, desc)
        except Exception as exc:
            msg = "not installed" if isinstance(exc, ImportError) else f"import error: {str(exc)[:60]}"
            r.add("FAIL" if needed else "WARN", module, f"{desc} — {msg}",
                  "From the Bolt folder run: uv sync")


def check_modules(r: Report) -> None:
    r.section("Bolt pipeline modules")
    mods = [
        "Config_Loader", "Highlight_Detector", "Clip_Generator", "Clip_Factory",
        "Title_Generator", "Subtitle_Generator", "Clip_Ranker", "Game_Config",
        "Think_Learn_Decide", "LLM_Handler", "Bolt_Memory", "Bolt_Chat",
    ]
    for name in mods:
        try:
            _quiet(lambda n=name: __import__(f"modules.{n}"))
            r.add("OK", name)
        except Exception as exc:
            r.add("FAIL", name, f"won't import: {type(exc).__name__}: {str(exc)[:80]}",
                  f"Run: bolt doctor  (or python3 -c 'import modules.{name}' from Core/ to see the full error)")


def check_config(r: Report) -> None:
    r.section("Settings")
    try:
        from modules.Config_Loader import load_config  # type: ignore

        cfg = _quiet(load_config) or {}
        game = cfg.get("game") or "(not set)"
        r.add("OK", "Core/config.json loads",
              f"game: {game} · min score {cfg.get('min_post_score')} · max {cfg.get('max_clips_per_session')} clips/session")
        if game == "(not set)":
            r.add("WARN", "Current game", "not set — clips use default sensitivity",
                  "Run: bolt game refresh  (follows your Twitch category)")
    except Exception as exc:
        r.add("FAIL", "Core/config.json loads", str(exc)[:120],
              "Fix the JSON (python3 -m json.tool Core/config.json shows the line) or git checkout Core/config.json")


def _ollama_up(timeout: float = 2.0) -> Optional[int]:
    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore") or "{}")
        return len(data.get("models") or [])
    except Exception:
        return None


def check_ai(r: Report, *, ping_ollama: bool = True) -> None:
    r.section("AI for titles / chat / memory")
    grok = _is_set("XAI_API_KEY")
    r.add("OK" if grok else "WARN", "Grok (XAI_API_KEY)",
          "set — first choice" if grok else "not set",
          "" if grok else "Add XAI_API_KEY=... to .env.local (console.x.ai)")
    models = _ollama_up() if ping_ollama else None
    if models is not None:
        r.add("OK", "Ollama (free, on this Mac)", f"running · {models} model(s)")
    elif ping_ollama:
        r.add("WARN", "Ollama (free, on this Mac)", "not running",
              "Open the Ollama app (or run: ollama serve) for free local titles")
    oai = _is_set("OPENAI_API_KEY")
    r.add("OK" if oai else "WARN", "OpenAI (OPENAI_API_KEY)",
          "set — last fallback (needs credits)" if oai else "not set (optional)",
          "" if oai else "Optional — only used if Grok and Ollama are both down")
    if not grok and models is None and not oai and ping_ollama:
        r.add("FAIL", "Any AI available", "none — titles fall back to templates, chat/memory recall won't answer",
              "Start Ollama or add XAI_API_KEY to .env.local")


def check_disk(r: Report) -> None:
    r.section("Disk")
    try:
        usage = shutil.disk_usage(str(MEDIA_DIR if MEDIA_DIR.exists() else REPO_ROOT))
        free_gb = usage.free / (1024 ** 3)
        detail = f"{free_gb:.1f} GB free of {usage.total / (1024 ** 3):.0f} GB"
        if free_gb < DISK_FAIL_GB:
            r.add("FAIL", "Free space", detail,
                  "Recordings will fail. Run: bolt storage optimize, then bolt compress clean-backups")
        elif free_gb < DISK_WARN_GB:
            r.add("WARN", "Free space", detail,
                  "Getting low. Run: bolt compress clean-backups or bolt storage optimize")
        else:
            r.add("OK", "Free space", detail)
    except Exception as exc:
        r.add("WARN", "Free space", f"couldn't read: {exc}", "")


def build_report(*, ping_ollama: bool = True) -> Report:
    if str(CORE_DIR) not in sys.path:
        sys.path.insert(0, str(CORE_DIR))
    r = Report()
    check_files(r)
    check_dirs(r)
    check_tools(r)
    check_packages(r)
    check_modules(r)
    check_config(r)
    check_ai(r, ping_ollama=ping_ollama)
    check_disk(r)
    return r


def verdict(counts: Dict[str, int]) -> str:
    if counts.get("FAIL"):
        return "NOT READY — fix the FAIL lines below"
    if counts.get("WARN"):
        return "READY (with warnings)"
    return "READY — all good"


# ── output ──────────────────────────────────────────────────────────────────

_MARK = {"OK": "✓", "WARN": "⚠", "FAIL": "✗"}


def print_report(r: Report, settings_read: List[str]) -> None:
    counts = r.counts()
    print("\n" + "=" * 72)
    print(f" BOLT QUICK HEALTH CHECK — {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")
    print("=" * 72)
    print(f"  {verdict(counts)}  ({counts['OK']} ok · {counts['WARN']} warnings · {counts['FAIL']} failed)")
    print(f"  settings read: {', '.join(settings_read) or 'none'}")
    for i, sec in enumerate(r.sections, 1):
        print(f"\n[{i}] {sec['title'].upper()}")
        for c in sec["checks"]:
            line = f"  {_MARK.get(c['state'], '?')} {c['name']}"
            if c["detail"]:
                line += f" — {c['detail']}"
            print(line)
            if c["state"] != "OK" and c["fix"]:
                print(f"      fix: {c['fix']}")
    problems = [c for c in r.all_checks() if c["state"] != "OK"]
    print("\n" + "-" * 72)
    if problems:
        print("To fix:")
        for c in problems:
            print(f"  {_MARK[c['state']]} {c['name']}: {c['fix'] or c['detail']}")
    else:
        print("Nothing to fix.")
    print("Full audit of every feature: bolt doctor")
    print("=" * 72 + "\n")


def report_dict(r: Report, settings_read: List[str]) -> Dict[str, Any]:
    counts = r.counts()
    return {
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ok": counts["FAIL"] == 0,
        "verdict": verdict(counts),
        "counts": counts,
        "settings_read": settings_read,
        "sections": r.sections,
        "problems": [c for c in r.all_checks() if c["state"] != "OK"],
    }


def run_health_check(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in args
    settings_read = load_settings()
    r = build_report(ping_ollama="--no-network" not in args)
    if as_json:
        print(json.dumps(report_dict(r, settings_read), indent=2))
    else:
        print_report(r, settings_read)
    return 0 if r.counts()["FAIL"] == 0 else 1


if __name__ == "__main__":
    sys.exit(run_health_check())
