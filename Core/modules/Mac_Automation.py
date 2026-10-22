#!/usr/bin/env python3
"""
Mac_Automation.py — what runs on its own on this Mac, and is it working? (READY)
===============================================================================
``bolt mac-auto`` looks at every Bolt automation that is actually installed on
Goddess and says, in plain words, whether it is working:

  * cron jobs (``crontab -l``) — storage monitor, media rotation, nightly
    cleanup, clip compress, site data push, 5 PM briefing, Sunday weekly, … and
    any other lines in your crontab;
  * the launchd agent ``com.streamer.ai-assistant`` (Bolt live watcher);
  * the Bolt Shortcuts in the Shortcuts app.

For each one: what it does, when it runs, whether the script / python it
points at exists and can run, when its log was last written and whether that
matches the schedule (STALE), whether the last run ended in an error (FAILING,
with the error line), and the exact fix.

  bolt mac-auto                         # status (default; read-only)
  bolt mac-auto status [--json] [--probe]
  bolt mac-auto list [--json]
  bolt mac-auto install [launchd|cron|shortcuts|all] [--apply] [--json]

``install`` is a dry run unless ``--apply`` is given. It only adds what is
missing (never duplicates a cron line, never removes one) and backs up the
crontab to ``Data/backups/mac-auto/`` before any change.

Every subprocess has a short timeout; nothing here runs osascript.
Soft-fail prefix: ``Mac automation unavailable:``.
Aliases: mac_auto, mac-automation, automation, shortcuts-status, launchd-status.
"""

from __future__ import annotations

import json
import os
import platform
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_REPO = Path(__file__).resolve().parents[2]
_INSTALL = _REPO / "scripts" / "install_mac_automation.py"
_AUTOSTART = _REPO / "scripts" / "autostart.py"
_SIGNED_DIR = _REPO / "scripts" / "macos_shortcuts" / "signed"
_UNSIGNED_DIR = _REPO / "scripts" / "macos_shortcuts" / "unsigned"
_VENV_BOLT = _REPO / ".venv" / "bin" / "bolt"
_VENV_PY = _REPO / ".venv" / "bin" / "python3"
_PLIST_LABEL = "com.streamer.ai-assistant"
_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{_PLIST_LABEL}.plist"
_BACKUP_DIR = _REPO / "Data" / "backups" / "mac-auto"
_HEARTBEAT_DIR = _REPO / "logs" / "heartbeats"
_BRIEFING_CRON_MARK = "Daily at 5pm: evening briefing"
_PROCESS_CRON_MARK = "Every 2 hours: auto-process any new recordings"
_INSTALL_STEPS = ("launchd", "cron", "shortcuts", "all")
_SOFT = "Mac automation unavailable:"
_BIG_LOG = 20 * 1024 * 1024

# Shortcut names the installer builds (library may show them with underscores).
_BOLT_SHORTCUTS = (
    "Bolt Morning",
    "Bolt Review Queue",
    "Bolt Stats",
    "Bolt Wrap-Up",
    "Extract Text from Photos",
    "Extract Text from JPGs to PDF",
)

# What each known job does, in plain words. Matched by substring of the command.
_KNOWN: Tuple[Dict[str, Any], ...] = (
    {"key": "compress_videos.sh", "name": "Clip compress",
     "does": "Shrinks new clips in media/clips (original kept in originals_backup until you clean it).",
     "quiet": True, "heartbeat": "compress_videos.last"},
    {"key": "storage_monitor.sh", "name": "Storage monitor",
     "does": "Checks free disk space and media folder sizes; alerts you if something is too big."},
    {"key": "media_rotation.sh", "name": "Media rotation",
     "does": "Keeps the media folders under their size limits."},
    {"key": "storage_optimization.sh", "name": "Nightly cleanup",
     "does": "Sends old clips to the Trash (skips queued clips) and tidies storage."},
    {"key": "weekly_analysis.py", "name": "Weekly report",
     "does": "Builds your weekly performance report and texts + emails it to you."},
    {"key": "generate_thumbnails.py", "name": "Thumbnails",
     "does": "Makes thumbnails for new clips."},
    {"key": "daily_briefing.py", "name": "5 PM briefing",
     "does": "Evening briefing → Apple Reminders, Mac banner and email."},
    {"key": "launch.py process", "name": "Auto-process recordings",
     "does": "Turns any new recordings in media/Recordings into clips."},
    {"key": "site_data_writer.py", "name": "Website numbers",
     "does": "Writes site-data.json and publishes it to GitHub so your website shows current progress.",
     "extra_logs": ("logs/site_data_push.log",),
     "fix_failing": ("Run it once by hand to see the full error: cd ~/developer/Bolt && "
                     ".venv/bin/python3 scripts/site_data_writer.py --push ; then read logs/site_data_push.log")},
    {"key": "creative-hour.sh", "name": "Creative Hour (yours, not Bolt)",
     "does": "Plays your Creative Hour song and shows a 'Time to Create!' banner.", "bolt": False},
)

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_ERR = re.compile(
    r"Traceback \(most recent call last\)|\bError\b|error:|ERROR|\bfailed\b|FAILED|"
    r"unavailable:|command not found|No such file|Permission denied|not permitted|timed out|"
    r"cannot |can't open"
)
_ZERO_COUNT = re.compile(r"\b(failed|errors?|failures?)\s*[:=]\s*0\b", re.I)
_OK = re.compile(
    r"complet|finished|\bsent\b|\bsaved\b|\bwrote\b|\bpushed\b|\bdone\b|no new|success|"
    r"nothing to|unchanged|Total videos|within size limit|Weekly report generated",
    re.I,
)


# ── small helpers ────────────────────────────────────────────────────────────

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    return msg if msg.startswith(_SOFT) else f"{_SOFT} {msg}"


def _run(cmd: List[str], *, timeout: float = 8.0, text: bool = True,
         input: Optional[str] = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=text, timeout=timeout,
                          check=False, input=input)


def _fmt_time(dt: Optional[datetime], now: Optional[datetime] = None) -> str:
    if dt is None:
        return "never"
    now = now or datetime.now()
    clock = dt.strftime("%-I:%M %p")
    if dt.date() == now.date():
        day = "today"
    elif dt.date() == (now - timedelta(days=1)).date():
        day = "yesterday"
    else:
        day = dt.strftime("%a %b %-d")
    return f"{day} {clock} CT"


def _ago(dt: Optional[datetime], now: datetime) -> str:
    if dt is None:
        return ""
    secs = max(0, int((now - dt).total_seconds()))
    if secs < 90:
        return "just now"
    if secs < 5400:
        return f"{secs // 60} min ago"
    if secs < 172800:
        return f"{secs // 3600} h ago"
    return f"{secs // 86400} days ago"


def _mtime(p: Path) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(p.stat().st_mtime)
    except OSError:
        return None


def _tail_lines(p: Path, n: int = 40, max_bytes: int = 65536) -> List[str]:
    try:
        with open(p, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            data = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = [_ANSI.sub("", ln).rstrip() for ln in data.splitlines()]
    return [ln for ln in lines if ln.strip()][-n:]


def _last_error(lines: List[str]) -> Optional[str]:
    """Error line if the log's most recent signal is an error (after the last OK)."""
    last_err = last_ok = -1
    err_line = None
    for i, ln in enumerate(lines):
        ln = _ANSI.sub("", ln)
        if _ERR.search(ln) and not _ZERO_COUNT.search(ln):
            last_err, err_line = i, ln.strip()
        elif _OK.search(ln):
            last_ok = i
    if last_err > last_ok and err_line:
        return err_line[:300]
    return None


# ── cron schedule ───────────────────────────────────────────────────────────

def _expand(field: str, lo: int, hi: int) -> Optional[set]:
    out: set = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, s = part.split("/", 1)
            if not s.isdigit() or int(s) == 0:
                return None
            step = int(s)
        if part in ("*", ""):
            a, b = lo, hi
        elif "-" in part:
            x, y = part.split("-", 1)
            if not (x.isdigit() and y.isdigit()):
                return None
            a, b = int(x), int(y)
        elif part.isdigit():
            a = int(part)
            b = hi if step > 1 else a
        else:
            return None
        if a < lo or b > hi or a > b:
            return None
        out.update(range(a, b + 1, step))
    if hi == 7:  # day-of-week: 7 == Sunday
        out = {0 if v == 7 else v for v in out}
    return out


def parse_schedule(fields: List[str]) -> Optional[Dict[str, Any]]:
    if len(fields) != 5:
        return None
    rng = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
    sets = []
    for f, (lo, hi) in zip(fields, rng):
        s = _expand(f, lo, hi)
        if s is None:
            return None
        sets.append(s)
    return {"fields": fields, "minute": sets[0], "hour": sets[1], "dom": sets[2],
            "month": sets[3], "dow": sets[4],
            "dom_any": fields[2] == "*", "dow_any": fields[4] == "*"}


def _matches(sched: Dict[str, Any], t: datetime) -> bool:
    if t.minute not in sched["minute"] or t.hour not in sched["hour"] or t.month not in sched["month"]:
        return False
    dow = (t.weekday() + 1) % 7  # cron: 0 = Sunday
    dom_ok = t.day in sched["dom"]
    dow_ok = dow in sched["dow"]
    if sched["dom_any"] and sched["dow_any"]:
        return True
    if sched["dom_any"]:
        return dow_ok
    if sched["dow_any"]:
        return dom_ok
    return dom_ok or dow_ok


def previous_runs(sched: Dict[str, Any], now: datetime, count: int = 2,
                  max_days: int = 8) -> List[datetime]:
    t = now.replace(second=0, microsecond=0)
    out: List[datetime] = []
    for _ in range(max_days * 24 * 60):
        if _matches(sched, t):
            out.append(t)
            if len(out) >= count:
                break
        t -= timedelta(minutes=1)
    return out


def _clock(h: int, m: int) -> str:
    return datetime(2000, 1, 1, h, m).strftime("%-I:%M %p").replace(":00 ", " ")


def describe_schedule(fields: List[str]) -> str:
    m, h, dom, mon, dow = fields
    days = {"0": "Sundays", "7": "Sundays", "1": "Mondays", "2": "Tuesdays", "3": "Wednesdays",
            "4": "Thursdays", "5": "Fridays", "6": "Saturdays"}
    if dom == "*" and mon == "*":
        if h == "*" and m.startswith("*/"):
            return f"every {m[2:]} minutes"
        if h == "*" and m.isdigit():
            return f"every hour at :{int(m):02d}"
        if h.startswith("*/") and m.isdigit():
            at = "on the hour" if int(m) == 0 else f"at :{int(m):02d}"
            return f"every {h[2:]} hours {at}"
        if h.isdigit() and m.isdigit():
            when = _clock(int(h), int(m))
            if dow == "*":
                return f"daily at {when}"
            if dow in days:
                return f"{days[dow]} at {when}"
            if dow == "1-5":
                return f"weekdays at {when}"
    return "cron " + " ".join(fields)


# ── crontab parsing ─────────────────────────────────────────────────────────

def _crontab_text() -> Tuple[Optional[str], Optional[str]]:
    """Return (text, error). Missing crontab is not fatal."""
    if shutil.which("crontab") is None:
        return None, "crontab not available"
    try:
        r = _run(["crontab", "-l"], timeout=5.0)
    except subprocess.TimeoutExpired:
        return None, "crontab -l timed out"
    except Exception as exc:
        return None, str(exc)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip() or f"exit {r.returncode}"
        if "no crontab" in err.lower():
            return "", None
        return None, err
    return r.stdout or "", None


def parse_crontab(text: str) -> List[Dict[str, Any]]:
    """Active (non-comment) cron lines with the comment right above each."""
    out: List[Dict[str, Any]] = []
    last_comment = ""
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            last_comment = ""
            continue
        if line.startswith("#"):
            last_comment = line.lstrip("#").strip()
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=", line):  # VAR=value
            continue
        if line.startswith("@"):
            parts = line.split(None, 1)
            out.append({"line": line, "fields": None, "special": parts[0],
                        "command": parts[1] if len(parts) > 1 else "", "comment": last_comment})
        else:
            parts = line.split(None, 5)
            if len(parts) < 6:
                out.append({"line": line, "fields": None, "special": "invalid",
                            "command": line, "comment": last_comment})
            else:
                out.append({"line": line, "fields": parts[:5], "special": None,
                            "command": parts[5], "comment": last_comment})
        last_comment = ""
    return out


def _split_command(command: str) -> Tuple[List[List[str]], List[str]]:
    """Split a cron command into && / ; segments (tokens) and the log files it appends to."""
    logs: List[str] = []
    for m in re.finditer(r">>?\s*([^\s;&|]+)", command):
        target = m.group(1)
        if target not in ("&1", "/dev/null") and not target.startswith("&"):
            logs.append(target)
    clean = re.sub(r"\d?>>?\s*(&\d|[^\s;&|]+)", " ", command)
    segments: List[List[str]] = []
    for seg in re.split(r"&&|;|\|\|", clean):
        try:
            toks = shlex.split(seg)
        except ValueError:
            toks = seg.split()
        if toks:
            segments.append(toks)
    return segments, logs


def _is_exec(p: Path) -> bool:
    return p.is_file() and os.access(p, os.X_OK)


def _syntax_problem(p: Path) -> Optional[str]:
    """Cheap, side-effect-free syntax check for .sh / .py targets."""
    try:
        if p.suffix == ".py":
            compile(p.read_text(errors="replace"), str(p), "exec")
        elif p.suffix == ".sh" or p.suffix == "":
            head = p.read_bytes()[:64]
            if p.suffix == ".sh" or head.startswith(b"#!/bin/bash") or head.startswith(b"#!/bin/sh"):
                r = _run(["bash", "-n", str(p)], timeout=5.0)
                if r.returncode != 0:
                    return (r.stderr or "").strip().splitlines()[-1][:200] if r.stderr else "bash -n failed"
                return _osascript_problem(p)
    except SyntaxError as exc:
        return f"Python syntax error line {exc.lineno}: {exc.msg}"
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None
    return None


def _osascript_problem(p: Path) -> Optional[str]:
    """Compile (never run) any `osascript -e '…'` in a shell script."""
    if platform.system() != "Darwin" or shutil.which("osacompile") is None:
        return None
    try:
        text = p.read_text(errors="replace")
    except OSError:
        return None
    for ln in text.splitlines():
        if "osascript" not in ln or " -e " not in ln or ln.lstrip().startswith("#"):
            continue
        try:
            toks = shlex.split(ln, comments=False)
        except ValueError:
            continue
        scripts = [toks[i + 1] for i, t in enumerate(toks[:-1]) if t == "-e" and "osascript" in " ".join(toks[:i])]
        if not scripts:
            continue
        fd, out = tempfile.mkstemp(suffix=".scpt")
        os.close(fd)
        try:
            cmd = ["osacompile", "-o", out]
            for s in scripts:
                cmd += ["-e", s]
            r = _run(cmd, timeout=5.0)
            if r.returncode != 0:
                msg = (r.stderr or "").strip().splitlines()
                hint = ""
                if any("display notification" in s and " body " in s for s in scripts):
                    hint = " — `display notification` has no `body`; use `subtitle` instead"
                return f"AppleScript won't compile ({msg[-1] if msg else 'error'}){hint}"
        except subprocess.TimeoutExpired:
            return None
        finally:
            try:
                os.unlink(out)
            except OSError:
                pass
    return None


def check_targets(command: str) -> Dict[str, Any]:
    """What the command runs, and whether each piece exists and can run."""
    segments, logs = _split_command(command)
    cwd: Optional[Path] = None
    checks: List[Dict[str, Any]] = []
    problems: List[Dict[str, str]] = []

    def resolve(tok: str) -> Path:
        p = Path(os.path.expanduser(tok))
        return p if p.is_absolute() else (cwd or Path.home()) / p

    for toks in segments:
        prog = toks[0]
        if prog == "cd" and len(toks) > 1:
            cwd = resolve(toks[1])
            ok = cwd.is_dir()
            checks.append({"what": "folder", "path": str(cwd), "ok": ok})
            if not ok:
                problems.append({"kind": "BROKEN", "detail": f"folder {cwd} is missing",
                                 "fix": f"Fix the path in this cron line (crontab -e) or restore {cwd}."})
            continue
        if prog in ("source", "."):
            if len(toks) > 1:
                p = resolve(toks[1])
                ok = p.is_file()
                checks.append({"what": "venv activate", "path": str(p), "ok": ok})
                if not ok:
                    problems.append({"kind": "BROKEN", "detail": f"{p} is missing",
                                     "fix": "Rebuild Bolt's Python: cd ~/developer/Bolt && uv sync"})
            continue
        env_skip = 0
        while env_skip < len(toks) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[env_skip]):
            env_skip += 1
        toks = toks[env_skip:]
        if not toks:
            continue
        prog = toks[0]
        is_py = os.path.basename(prog).startswith("python")
        if "/" in prog:
            p = resolve(prog)
            ok = _is_exec(p) or (p.exists() and os.access(p, os.X_OK))
            what = "python" if is_py else "script"
            checks.append({"what": what, "path": str(p), "ok": ok, "exists": p.exists()})
            if not p.exists():
                fix = ("Rebuild Bolt's Python: cd ~/developer/Bolt && uv sync" if is_py else
                       f"{p} is missing — restore it (git checkout -- {p}) or remove the line with crontab -e.")
                problems.append({"kind": "BROKEN", "detail": f"{p} is missing", "fix": fix})
            elif not ok:
                problems.append({"kind": "BROKEN", "detail": f"{p} is not executable",
                                 "fix": f"chmod +x {shlex.quote(str(p))}"})
            elif not is_py:
                syn = _syntax_problem(p.resolve())
                if syn:
                    problems.append({"kind": "BROKEN", "detail": f"{p.name}: {syn}",
                                     "fix": f"Fix the script {p} (it runs, but this part fails)."})
        elif is_py or prog in ("bash", "sh", "zsh"):
            found = shutil.which(prog, path="/usr/bin:/bin:/usr/sbin:/sbin")
            checks.append({"what": "program (cron PATH)", "path": found or prog, "ok": bool(found)})
            if not found:
                problems.append({"kind": "BROKEN",
                                 "detail": f"`{prog}` isn't on cron's PATH (/usr/bin:/bin)",
                                 "fix": "Use the full path, e.g. /Users/carter/developer/Bolt/.venv/bin/python3"})
        if is_py or prog in ("bash", "sh", "zsh"):
            script = next((t for t in toks[1:] if not t.startswith("-")), None)
            if script and script not in ("-m", "-c"):
                p = resolve(script)
                ok = p.is_file()
                checks.append({"what": "script", "path": str(p), "ok": ok})
                if not ok:
                    problems.append({"kind": "BROKEN", "detail": f"{p} is missing",
                                     "fix": f"Restore {p} (git checkout) or remove the line with crontab -e."})
                else:
                    syn = _syntax_problem(p)
                    if syn:
                        problems.append({"kind": "BROKEN", "detail": f"{p.name}: {syn}",
                                         "fix": f"Fix the syntax error in {p}."})
    log_paths = [str(resolve(l)) for l in logs]
    return {"checks": checks, "problems": problems, "logs": log_paths, "cwd": str(cwd) if cwd else None}


def _manual_command(command: str) -> str:
    return re.sub(r"\s*\d?>>?\s*(&\d|[^\s;&|]+)", "", command).strip()


def _known_for(command: str) -> Dict[str, Any]:
    for k in _KNOWN:
        if k["key"] in command:
            return k
    return {}


def check_cron_job(entry: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now()
    command = entry.get("command", "")
    known = _known_for(command)
    is_bolt = known.get("bolt", "developer/Bolt" in command or "Bolt" in command)
    tgt = check_targets(command)
    problems = list(tgt["problems"])
    job: Dict[str, Any] = {
        "kind": "cron",
        "name": known.get("name") or (entry.get("comment") or command)[:60],
        "does": known.get("does") or (entry.get("comment") or "(no description — custom cron line)"),
        "bolt": bool(is_bolt),
        "line": entry.get("line"),
        "targets": tgt["checks"],
        "logs": [],
    }
    fields = entry.get("fields")
    sched = parse_schedule(fields) if fields else None
    if entry.get("special") == "invalid" or (fields and sched is None):
        job["schedule"] = entry.get("line", "")
        problems.append({"kind": "BROKEN", "detail": "cron can't read this schedule",
                         "fix": "Fix the 5 time fields of this line with crontab -e."})
    elif sched:
        job["schedule"] = describe_schedule(fields)
    else:
        job["schedule"] = entry.get("special") or "?"

    log_paths = list(tgt["logs"])
    for extra in known.get("extra_logs", ()):
        log_paths.append(str(_REPO / extra))
    last_write: Optional[datetime] = None
    for lp in log_paths:
        p = Path(lp)
        mt = _mtime(p)
        info: Dict[str, Any] = {"path": lp, "exists": p.is_file(),
                                "last_written": mt.isoformat(timespec="seconds") if mt else None}
        if p.is_file():
            info["size_mb"] = round(p.stat().st_size / 1048576, 1)
            err = _last_error(_tail_lines(p))
            if err:
                info["last_error"] = err
            core = re.sub(r"^\[[^\]]*\]\s*", "", err or "")
            if err and not any(core and core in q["detail"] for q in problems if q["kind"] == "FAILING"):
                problems.append({"kind": "FAILING", "detail": err,
                                 "fix": known.get("fix_failing") or
                                 f"Run it once by hand to see the full error: {_manual_command(command)}"})
            if p.stat().st_size > _BIG_LOG:
                info["note"] = f"log is {info['size_mb']} MB (fine, but could be trimmed)"
        if mt and (last_write is None or mt > last_write):
            last_write = mt
        job["logs"].append(info)

    hb = known.get("heartbeat")
    hb_time = _mtime(_HEARTBEAT_DIR / hb) if hb else None
    if hb_time:
        job["heartbeat"] = hb_time.isoformat(timespec="seconds")
    seen = max([t for t in (last_write, hb_time) if t], default=None)
    job["last_activity"] = seen.isoformat(timespec="seconds") if seen else None
    job["last_activity_words"] = (f"{_fmt_time(seen, now)} ({_ago(seen, now)})" if seen else "never")

    fresh = "unknown"
    if sched:
        runs = previous_runs(sched, now - timedelta(minutes=5), count=2)
        if runs:
            job["last_expected_run"] = runs[0].isoformat(timespec="minutes")
            job["last_expected_words"] = _fmt_time(runs[0], now)
        if not log_paths and not hb:
            fresh = "no log"
        elif known.get("quiet") and not hb_time:
            fresh = "quiet"  # writes only when it has work
        elif runs and seen is None:
            fresh = "stale"
        elif runs:
            slack = timedelta(minutes=2)
            if seen >= runs[0] - slack:
                fresh = "on time"
            elif len(runs) > 1 and seen >= runs[1] - slack:
                fresh = "missed last run"
            elif known.get("quiet") and hb_time is None:
                fresh = "quiet"
            else:
                fresh = "stale"
    job["freshness"] = fresh
    if fresh == "stale":
        problems.append({
            "kind": "STALE",
            "detail": (f"should have run {job.get('last_expected_words', '?')}, "
                       f"but its log was last written {job['last_activity_words']}"),
            "fix": ("If the Mac was asleep/off then, that's expected. Otherwise run it by hand "
                    f"to check: {_manual_command(command)}"),
        })
    job["problems"] = problems
    job["state"] = _state(problems, fresh)
    return job


def _state(problems: List[Dict[str, str]], fresh: str = "") -> str:
    kinds = {p["kind"] for p in problems}
    for k in ("BROKEN", "FAILING", "STALE"):
        if k in kinds:
            return k
    if fresh == "missed last run":
        return "LATE"
    return "OK"


# ── launchd ─────────────────────────────────────────────────────────────────

def _launchctl_entry(label: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if platform.system() != "Darwin" or shutil.which("launchctl") is None:
        return None, "launchctl not available"
    try:
        r = _run(["launchctl", "list"], timeout=5.0)
    except subprocess.TimeoutExpired:
        return None, "launchctl list timed out"
    except Exception as exc:
        return None, str(exc)
    for ln in (r.stdout or "").splitlines():
        parts = ln.split("\t") if "\t" in ln else ln.split()
        if len(parts) >= 3 and parts[2].strip() == label:
            pid = parts[0].strip()
            st = parts[1].strip()
            return {"pid": int(pid) if pid.isdigit() else None,
                    "last_exit": int(st) if st.lstrip("-").isdigit() else None}, None
    return {}, None


def _proc_uptime(pid: int) -> Optional[str]:
    try:
        r = _run(["ps", "-o", "etime=", "-p", str(pid)], timeout=3.0)
        return (r.stdout or "").strip() or None
    except Exception:
        return None


def check_launchd(plist_path: Path = _PLIST_PATH, label: str = _PLIST_LABEL,
                  now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    now = now or datetime.now()
    if not plist_path.is_file():
        return None
    job: Dict[str, Any] = {
        "kind": "launchd", "name": "Bolt live watcher (launchd)", "bolt": True,
        "label": label, "plist": str(plist_path),
        "does": "Starts Bolt at login and keeps it watching media/Recordings for new recordings "
                "(restarts it if it crashes).",
        "schedule": "at login, kept running", "targets": [], "logs": [],
    }
    problems: List[Dict[str, str]] = []
    try:
        with open(plist_path, "rb") as fh:
            pl = plistlib.load(fh)
    except Exception as exc:
        problems.append({"kind": "BROKEN", "detail": f"plist can't be read ({exc})",
                         "fix": "Re-create it: bolt mac-auto install launchd --apply"})
        job["problems"] = problems
        job["state"] = _state(problems)
        return job
    args = list(pl.get("ProgramArguments") or ([pl["Program"]] if pl.get("Program") else []))
    wd = pl.get("WorkingDirectory")
    if args:
        prog = Path(args[0])
        ok = _is_exec(prog) or (prog.exists() and os.access(prog, os.X_OK))
        job["targets"].append({"what": "python" if "python" in prog.name else "program",
                               "path": str(prog), "ok": ok})
        if not ok:
            problems.append({"kind": "BROKEN", "detail": f"{prog} is missing or not executable",
                             "fix": "Rebuild Bolt's Python: cd ~/developer/Bolt && uv sync"})
        if len(args) > 1 and args[1].endswith(".py"):
            sp = Path(args[1]) if os.path.isabs(args[1]) else Path(wd or "/") / args[1]
            job["targets"].append({"what": "script", "path": str(sp), "ok": sp.is_file()})
            if not sp.is_file():
                problems.append({"kind": "BROKEN", "detail": f"{sp} is missing",
                                 "fix": "Re-create the agent: bolt mac-auto install launchd --apply"})
        job["command"] = " ".join(args)
    if wd and not Path(wd).is_dir():
        problems.append({"kind": "BROKEN", "detail": f"WorkingDirectory {wd} is missing",
                         "fix": "Re-create the agent: bolt mac-auto install launchd --apply"})

    entry, err = _launchctl_entry(label)
    if err:
        job["loaded"] = None
        job["running_words"] = f"unknown ({err})"
    elif not entry:
        job["loaded"] = False
        job["running"] = False
        job["running_words"] = "not loaded"
        problems.append({"kind": "FAILING", "detail": "the agent is installed but not loaded",
                         "fix": f"launchctl load -w {plist_path}  (or log out and back in)"})
    else:
        job["loaded"] = True
        job["pid"] = entry.get("pid")
        job["last_exit"] = entry.get("last_exit")
        job["running"] = bool(entry.get("pid"))
        if job["running"]:
            up = _proc_uptime(entry["pid"])
            job["running_words"] = f"running (PID {entry['pid']}" + (f", up {up})" if up else ")")
        else:
            job["running_words"] = f"loaded but not running (last exit {entry.get('last_exit')})"
    for key in ("StandardOutPath", "StandardErrorPath"):
        lp = pl.get(key)
        if not lp:
            continue
        p = Path(lp)
        mt = _mtime(p)
        info: Dict[str, Any] = {"path": lp, "exists": p.is_file(),
                                "last_written": mt.isoformat(timespec="seconds") if mt else None}
        if p.is_file():
            info["size_mb"] = round(p.stat().st_size / 1048576, 1)
        job["logs"].append(info)
        if key == "StandardErrorPath" and p.is_file() and job.get("loaded") and not job.get("running"):
            tail = _tail_lines(p, 5)
            if tail and (job.get("last_exit") or 0) != 0:
                problems.append({"kind": "FAILING", "detail": tail[-1][:300],
                                 "fix": f"It keeps exiting. Run it by hand to see why: cd {wd or _REPO} && "
                                        + " ".join(args)})
    out_log = next((l for l in job["logs"] if l["path"] == pl.get("StandardOutPath")), None)
    seen = _mtime(Path(out_log["path"])) if out_log else None
    job["last_activity"] = seen.isoformat(timespec="seconds") if seen else None
    job["last_activity_words"] = f"{_fmt_time(seen, now)} ({_ago(seen, now)})" if seen else "never"
    job["freshness"] = "running" if job.get("running") else "n/a"
    job["problems"] = problems
    job["state"] = _state(problems)
    return job


# ── Shortcuts ───────────────────────────────────────────────────────────────

def _norm(name: str) -> str:
    return re.sub(r"[\s_\-]+", "", name).lower()


def _shortcuts_library() -> Tuple[Optional[List[str]], Optional[str]]:
    if shutil.which("shortcuts") is None:
        return None, "Shortcuts CLI not found"
    try:
        r = _run(["shortcuts", "list"], timeout=6.0)
    except subprocess.TimeoutExpired:
        return None, "shortcuts list timed out"
    except Exception as exc:
        return None, str(exc)
    if r.returncode != 0:
        return None, (r.stderr or "").strip()[:200] or f"exit {r.returncode}"
    return [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()], None


def _signed_shortcut_count() -> int:
    if not _SIGNED_DIR.is_dir():
        return 0
    return sum(1 for p in _SIGNED_DIR.iterdir()
               if p.is_file() and p.suffix.lower() in (".shortcut", ".wflow"))


def check_shortcuts(library: Optional[List[str]] = None, lib_err: Optional[str] = None) -> Dict[str, Any]:
    if library is None and lib_err is None:
        library, lib_err = _shortcuts_library()
    have = {_norm(n): n for n in (library or [])}
    found = [n for n in _BOLT_SHORTCUTS if _norm(n) in have]
    missing = [n for n in _BOLT_SHORTCUTS if _norm(n) not in have]
    term = _REPO / "scripts" / "mac_run_in_terminal.sh"
    ocr = _REPO / "scripts" / "ocr_to_editable.py"
    targets = [
        {"what": "Terminal helper (Morning / Review Queue)", "path": str(term), "ok": _is_exec(term)},
        {"what": "Photo OCR script (Extract Text shortcuts)", "path": str(ocr), "ok": ocr.is_file()},
        {"what": "bolt command (Stats / Wrap-Up)", "path": str(_VENV_BOLT), "ok": _is_exec(_VENV_BOLT)},
    ]
    problems: List[Dict[str, str]] = []
    for t in targets:
        if not t["ok"]:
            fix = (f"chmod +x {t['path']}" if Path(t["path"]).exists()
                   else "Rebuild: cd ~/developer/Bolt && uv sync")
            problems.append({"kind": "BROKEN", "detail": f"{t['path']} missing or not executable", "fix": fix})
    if lib_err:
        words = f"couldn't read the Shortcuts library ({lib_err})"
    elif missing:
        words = f"{len(found)} of {len(_BOLT_SHORTCUTS)} in the Shortcuts app; missing: {', '.join(missing)}"
        problems.append({"kind": "MISSING", "detail": f"not in the Shortcuts app: {', '.join(missing)}",
                         "fix": "bolt mac-auto install shortcuts --apply, then click Add on each dialog"})
    else:
        words = f"all {len(_BOLT_SHORTCUTS)} Bolt shortcuts are in the Shortcuts app"
    state = _state(problems)
    if state == "OK" and any(p["kind"] == "MISSING" for p in problems):
        state = "MISSING"
    return {
        "kind": "shortcuts", "name": "Bolt Shortcuts", "bolt": True,
        "does": "Buttons in the Shortcuts app / Siri: Bolt Morning, Review Queue, Stats, Wrap-Up, "
                "and Extract Text from Photos.",
        "schedule": "when you tap them (not scheduled)",
        "found": found, "missing": missing, "library_error": lib_err,
        "signed_files": _signed_shortcut_count(), "targets": targets,
        "summary": words, "problems": problems, "state": state, "freshness": "n/a",
    }


# ── status ──────────────────────────────────────────────────────────────────

def collect(now: Optional[datetime] = None, *, crontab_text: Optional[str] = None,
            shortcuts: bool = True) -> Dict[str, Any]:
    now = now or datetime.now()
    cron_err = None
    if crontab_text is None:
        crontab_text, cron_err = _crontab_text()
    jobs: List[Dict[str, Any]] = []
    for entry in parse_crontab(crontab_text or ""):
        try:
            jobs.append(check_cron_job(entry, now))
        except Exception as exc:  # never let one line break the report
            jobs.append({"kind": "cron", "name": entry.get("line", "")[:60], "bolt": True,
                         "state": "UNKNOWN", "problems": [{"kind": "UNKNOWN", "detail": str(exc), "fix": ""}],
                         "schedule": "?", "does": ""})
    ld = check_launchd(now=now)
    if ld:
        jobs.append(ld)
    if shortcuts and platform.system() == "Darwin":
        jobs.append(check_shortcuts())
    return {"jobs": jobs, "crontab_error": cron_err, "crontab_readable": crontab_text is not None}


def status(*, probe: bool = False, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Mac automation status. Never raises."""
    try:
        is_darwin = platform.system() == "Darwin"
        data = collect(now, shortcuts=True)
        jobs = data["jobs"]
        bolt_jobs = [j for j in jobs if j.get("bolt")]
        attention = [j for j in jobs if j.get("state") not in ("OK", "LATE")]
        bolt_attention = [j for j in bolt_jobs if j.get("state") not in ("OK", "LATE")]
        cron_jobs = [j for j in jobs if j["kind"] == "cron"]
        ld = next((j for j in jobs if j["kind"] == "launchd"), None)
        sc = next((j for j in jobs if j["kind"] == "shortcuts"), None)
        ready = bool(is_darwin and data["crontab_readable"] and bolt_jobs)
        if not is_darwin:
            error = _soft("not macOS (Darwin)")
        elif not data["crontab_readable"]:
            error = _soft(f"can't read crontab ({data['crontab_error']})")
        elif not bolt_jobs:
            error = _soft("no Bolt automations installed — try: bolt mac-auto install all")
        else:
            error = None
        counts = {s: sum(1 for j in jobs if j.get("state") == s)
                  for s in ("OK", "LATE", "STALE", "FAILING", "BROKEN", "MISSING", "UNKNOWN")}
        if error:
            hint = error
        elif attention:
            hint = (f"{len(jobs)} automations: {counts['OK'] + counts['LATE']} OK, "
                    f"{len(attention)} need attention ("
                    + ", ".join(f"{j['name']}: {j['state']}" for j in attention[:3])
                    + ") — bolt mac-auto status")
        else:
            hint = f"all {len(jobs)} automations OK — bolt mac-auto status"
        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": ready,
            "healthy": ready and not bolt_attention,
            "readiness": "READY",
            "partial": False,
            "soft_fail_prefix": _SOFT,
            "darwin": is_darwin,
            "platform": platform.system(),
            "counts": counts,
            "jobs": jobs,
            "needs_attention": [{"name": j["name"], "state": j["state"],
                                 "problems": j.get("problems", [])} for j in attention],
            "crontab_readable": data["crontab_readable"],
            "crontab_error": data["crontab_error"],
            "cron_job_count": len(cron_jobs),
            "cron_briefing_mark": any("daily_briefing.py" in (j.get("line") or "") for j in cron_jobs),
            "cron_process_mark": any("launch.py process" in (j.get("line") or "") for j in cron_jobs),
            "plist_label": _PLIST_LABEL,
            "plist_path": str(_PLIST_PATH),
            "plist_exists": _PLIST_PATH.is_file(),
            "launchd_loaded": ld.get("loaded") if ld else None,
            "launchd_running": ld.get("running") if ld else None,
            "shortcuts_found": sc.get("found") if sc else [],
            "shortcuts_missing": sc.get("missing") if sc else list(_BOLT_SHORTCUTS),
            "signed_shortcut_count": _signed_shortcut_count(),
            "install_script_present": _INSTALL.is_file(),
            "autostart_present": _AUTOSTART.is_file(),
            "venv_python": str(_VENV_PY) if _VENV_PY.exists() else None,
            "venv_bolt": str(_VENV_BOLT) if _VENV_BOLT.is_file() else None,
            "error": error,
            "hint": hint,
        }
        if probe:
            out["probe"] = True
            out["probe_ok"] = bool(out["healthy"])
            out["probe_detail"] = hint
        return out
    except Exception as exc:
        return {"checked_at": _utc_now(), "ready": False, "healthy": False, "readiness": "READY",
                "partial": False, "soft_fail_prefix": _SOFT, "darwin": platform.system() == "Darwin",
                "jobs": [], "error": _soft(f"status failed ({exc})"),
                "hint": _soft(f"status failed ({exc})")}


_ICON = {"OK": "✅", "LATE": "🟡", "STALE": "🟠", "FAILING": "❌", "BROKEN": "❌",
         "MISSING": "🟠", "UNKNOWN": "❔"}


def _job_lines(j: Dict[str, Any]) -> List[str]:
    lines = [f"{_ICON.get(j.get('state'), '•')} {j['name']} — {j.get('state')}"]
    lines.append(f"     What: {j.get('does', '')}")
    lines.append(f"     When: {j.get('schedule', '?')}")
    tg = j.get("targets") or []
    if tg:
        bad = [t for t in tg if not t.get("ok")]
        if bad:
            lines.append("     Runs: " + "; ".join(f"{t['what']} {t['path']} ✗" for t in bad))
        else:
            names = [Path(t["path"]).name for t in tg if t["what"] in ("script", "python", "program")]
            lines.append("     Runs: " + (", ".join(names) if names else "helper scripts") + " — found and runnable ✓")
    if j["kind"] == "launchd":
        lines.append(f"     Now:  {j.get('running_words', '?')}; output log last written "
                     f"{j.get('last_activity_words', 'never')}")
    elif j["kind"] == "shortcuts":
        lines.append(f"     Now:  {j.get('summary', '')}")
    else:
        fr = j.get("freshness")
        last = j.get("last_activity_words", "never")
        if fr == "on time":
            lines.append(f"     Log:  last written {last} — matches the schedule ✓")
        elif fr == "missed last run":
            lines.append(f"     Log:  last written {last} — missed the {j.get('last_expected_words')} run "
                         "(Mac asleep?) but ran the time before")
        elif fr == "quiet":
            lines.append(f"     Log:  last written {last} — this job only writes when it has work")
        elif fr == "no log":
            lines.append("     Log:  this line doesn't save a log")
        elif fr == "stale":
            lines.append(f"     Log:  last written {last} — should have run {j.get('last_expected_words')}")
        else:
            lines.append(f"     Log:  last written {last}")
        for l in j.get("logs") or []:
            if l.get("note"):
                lines.append(f"     Note: {Path(l['path']).name}: {l['note']}")
    for p in j.get("problems") or []:
        lines.append(f"     ⚠ {p['kind']}: {p['detail']}")
        if p.get("fix"):
            lines.append(f"       Fix: {p['fix']}")
    return lines


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    try:
        info = status(probe=probe)
        if as_json:
            print(json.dumps(info, indent=2, default=str))
            return 0
        now = datetime.now()
        print(f"Bolt Mac automation — {now.strftime('%a %b %-d, %-I:%M %p')} CT")
        if info.get("error"):
            print(f"  {info['error']}")
        jobs = info.get("jobs") or []
        for group, title in ((True, "Bolt automations"), (False, "Other things in your crontab")):
            sel = [j for j in jobs if bool(j.get("bolt")) == group]
            if not sel:
                continue
            print(f"\n{title}:")
            for j in sel:
                for ln in _job_lines(j):
                    print("  " + ln)
        print()
        c = info.get("counts") or {}
        att = info.get("needs_attention") or []
        if att:
            print(f"Summary: {len(jobs)} automations — {c.get('OK', 0) + c.get('LATE', 0)} OK, "
                  f"{len(att)} need attention: " + ", ".join(f"{a['name']} ({a['state']})" for a in att))
        elif jobs:
            print(f"Summary: all {len(jobs)} automations OK.")
        return 0
    except Exception as exc:
        msg = _soft(f"status print failed ({exc})")
        if as_json:
            print(json.dumps({"ready": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def list_items(*, as_json: bool = False) -> int:
    """One line per automation."""
    try:
        info = status()
        jobs = info.get("jobs") or []
        rows = [{"name": j["name"], "kind": j["kind"], "when": j.get("schedule"),
                 "state": j.get("state"), "bolt": j.get("bolt")} for j in jobs]
        if as_json:
            print(json.dumps({"ok": True, "readiness": "READY", "items": rows,
                              "hint": info.get("hint"), "error": info.get("error")}, indent=2))
            return 0
        print("Mac automations on this Mac")
        for r in rows:
            tag = "" if r["bolt"] else "  (not Bolt)"
            print(f"  {_ICON.get(r['state'], '•')} {r['state']:<8} {r['name']:<34} {r['when']}{tag}")
        if info.get("hint"):
            print(f"  → {info['hint']}")
        return 0
    except Exception as exc:
        msg = _soft(f"list failed ({exc})")
        print(json.dumps({"ok": False, "error": msg}) if as_json else msg,
              file=sys.stdout if as_json else sys.stderr)
        return 0


# ── install (dry-run by default) ────────────────────────────────────────────

def desired_cron_entries() -> List[Dict[str, str]]:
    py = _VENV_PY
    logs = _REPO / "logs"
    return [
        {"key": "daily_briefing.py", "comment": f"# {_BRIEFING_CRON_MARK} → Apple Reminders + Mac banner + email",
         "line": (f"0 17 * * * cd {_REPO} && {py} {_REPO / 'scripts' / 'daily_briefing.py'} --send "
                  f">> {logs / 'daily_briefing.log'} 2>&1")},
        {"key": "launch.py process", "comment": f"# {_PROCESS_CRON_MARK}",
         "line": (f"0 */2 * * * cd {_REPO} && {py} {_REPO / 'Core' / 'launch.py'} process --no-checklist "
                  f">> {logs / 'auto_process.log'} 2>&1")},
    ]


def plan_cron(text: str) -> List[Dict[str, str]]:
    """Desired entries that are NOT already active in the crontab (no duplicates)."""
    active = [e["command"] for e in parse_crontab(text or "")]
    return [d for d in desired_cron_entries() if not any(d["key"] in c for c in active)]


def apply_cron(text: str, missing: List[Dict[str, str]], *, backup_dir: Path = _BACKUP_DIR,
               writer=None) -> Dict[str, Any]:
    if not missing:
        return {"changed": False, "backup": None}
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"crontab-{datetime.now():%Y%m%d-%H%M%S}.txt"
    backup.write_text(text or "")
    body = (text or "").rstrip("\n")
    for d in missing:
        body += f"\n\n{d['comment']}\n{d['line']}"
    body += "\n"
    if writer is None:
        r = _run(["crontab", "-"], input=body, timeout=10.0)
        if r.returncode != 0:
            return {"changed": False, "backup": str(backup),
                    "error": _soft(f"crontab write failed: {(r.stderr or '').strip()}")}
    else:
        writer(body)
    return {"changed": True, "backup": str(backup), "added": [d["line"] for d in missing]}


def try_install(step: str = "all", *, apply: bool = False, as_json: bool = False) -> int:
    try:
        step_l = (step or "all").strip().lower()
        if step_l not in _INSTALL_STEPS:
            msg = _soft(f"unknown step {step!r} — use launchd|cron|shortcuts|all")
            print(json.dumps({"ok": False, "error": msg}) if as_json else msg)
            return 0
        if platform.system() != "Darwin":
            msg = _soft("not macOS — install skipped")
            print(json.dumps({"ok": False, "error": msg}) if as_json else msg)
            return 0
        steps = ["launchd", "cron", "shortcuts"] if step_l == "all" else [step_l]
        py = str(_VENV_PY) if _VENV_PY.exists() else sys.executable
        report: List[Dict[str, Any]] = []
        for s in steps:
            item: Dict[str, Any] = {"step": s}
            if s == "cron":
                text, err = _crontab_text()
                if text is None:
                    item.update(ok=False, error=_soft(f"can't read crontab ({err})"))
                else:
                    missing = plan_cron(text)
                    item["already_there"] = [d["key"] for d in desired_cron_entries() if d not in missing]
                    item["would_add"] = [d["line"] for d in missing]
                    if apply and missing:
                        item.update(apply_cron(text, missing))
                    item["ok"] = not item.get("error")
            elif s == "launchd":
                ld = check_launchd()
                if ld and ld.get("running"):
                    item.update(ok=True, nothing_to_do=f"already installed and {ld['running_words']}")
                else:
                    cmd = [py, str(_AUTOSTART), "install"]
                    item["would_run"] = " ".join(cmd)
                    if apply:
                        if _PLIST_PATH.is_file():
                            _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(_PLIST_PATH, _BACKUP_DIR / f"{_PLIST_LABEL}-{datetime.now():%Y%m%d-%H%M%S}.plist")
                        try:
                            r = _run(cmd, timeout=60.0)
                            item.update(ok=r.returncode == 0, returncode=r.returncode,
                                        output=((r.stdout or "") + (r.stderr or "")).strip()[-800:])
                        except subprocess.TimeoutExpired:
                            item.update(ok=False, error=_soft("launchd install timed out"))
                    else:
                        item["ok"] = True
            elif s == "shortcuts":
                sc = check_shortcuts()
                if sc.get("library_error"):
                    item["note"] = f"couldn't read the Shortcuts library ({sc['library_error']})"
                if not sc.get("missing") and not sc.get("library_error"):
                    item.update(ok=True, nothing_to_do=sc["summary"])
                else:
                    cmd = [py, str(_INSTALL), "shortcuts"]
                    item["would_run"] = " ".join(cmd)
                    item["missing"] = sc.get("missing")
                    item["needs_you"] = "Shortcuts opens an import dialog per shortcut — click Add on each."
                    if apply:
                        try:
                            r = _run(cmd, timeout=120.0)
                            item.update(ok=r.returncode == 0, returncode=r.returncode,
                                        output=((r.stdout or "") + (r.stderr or "")).strip()[-800:])
                        except subprocess.TimeoutExpired:
                            item.update(ok=False, error=_soft("shortcuts install timed out"))
                    else:
                        item["ok"] = True
            report.append(item)
        payload = {"ok": all(i.get("ok") for i in report), "dry_run": not apply, "steps": report}
        if as_json:
            print(json.dumps(payload, indent=2, default=str))
            return 0
        print("Mac automation install — " + ("APPLYING" if apply else "dry run (nothing changed; add --apply)"))
        for i in report:
            print(f"  {i['step']}:")
            if i.get("error"):
                print(f"    {i['error']}")
            if i.get("nothing_to_do"):
                print(f"    nothing to do — {i['nothing_to_do']}")
            for k in i.get("already_there") or []:
                print(f"    already in crontab: {k}")
            for ln in i.get("would_add") or []:
                print(f"    {'added' if i.get('changed') else 'would add'}: {ln}")
            if i.get("step") == "cron" and not i.get("would_add") and not i.get("error"):
                print("    nothing to add (no duplicates written)")
            if i.get("backup"):
                print(f"    crontab backed up to {i['backup']}")
            if i.get("would_run"):
                print(f"    {'ran' if apply else 'would run'}: {i['would_run']}")
            if i.get("needs_you"):
                print(f"    you: {i['needs_you']}")
            if i.get("output"):
                print("    " + i["output"].replace("\n", "\n    "))
        return 0
    except Exception as exc:
        msg = _soft(f"install wrapper failed ({exc})")
        print(json.dumps({"ok": False, "error": msg}) if as_json else msg)
        return 0


HELP = """bolt mac-auto — what runs on its own on this Mac, and is it working

  bolt mac-auto                                   # status (default; read-only)
  bolt mac-auto status [--json] [--probe]         # every cron job, launchd agent, Shortcuts
  bolt mac-auto list [--json]                     # one line each
  bolt mac-auto install [launchd|cron|shortcuts|all] [--apply]
                                                  # dry run unless --apply; adds only what's
                                                  # missing; backs up crontab first

States: OK · LATE (missed one run, e.g. Mac asleep) · STALE (missed 2+ runs)
        FAILING (last run ended in an error) · BROKEN (script/python missing)
        MISSING (shortcut not in the Shortcuts app)
Backups: Data/backups/mac-auto/
"""


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(HELP)
        return 0
    json_out = "--json" in args
    probe = "--probe" in args
    apply = "--apply" in args and "--dry-run" not in args
    positionals = [a for a in args if not a.startswith("-")]
    if not positionals:
        return print_status(as_json=json_out, probe=probe)
    cmd = positionals[0].lower()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "pieces", "checklist"):
        return list_items(as_json=json_out)
    if cmd in ("install", "setup", "apply"):
        step = positionals[1].lower() if len(positionals) > 1 else "all"
        return try_install(step, apply=apply, as_json=json_out)
    print(f"unknown mac-auto action: {cmd}", file=sys.stderr)
    print("  try: bolt mac-auto status|list|install [--json] [--apply] [--probe]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
