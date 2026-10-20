#!/usr/bin/env python3
"""
Bolt Site Data Writer
=====================
Generates site-data.json from Bolt's live data and optionally
commits it to GitHub so the Cloudflare Worker can serve it.

Usage:
  python3 scripts/site_data_writer.py          # Generate only
  python3 scripts/site_data_writer.py --push   # Generate + push ONLY the site-data file(s)
                                               # (soft-fails, logs to logs/site_data_push.log)
  python3 scripts/site_data_writer.py --path /custom/path/site-data.json
  python3 scripts/site_data_writer.py status [--json] [--probe]

Add to bot.py pipeline:
  from site_data_writer import write_site_data
  write_site_data(push=True)

Post-reorg (July 2026): the script was moved to
scripts/ but its internal REPO_ROOT math wasn't
updated. Now uses _paths.py so REPO_ROOT, DATA_DIR, CLIPS_DIR etc.
resolve against the new layout.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Post-reorg: REPO_ROOT and standard subpaths.
# Make _paths importable in BOTH direct invocation and `from scripts import X`.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _paths import (  # noqa: E402
    REPO_ROOT, DATA_DIR, CLIPS_DIR, DAILY_BRIEFINGS_DIR, CONFIG_FILE,
)


def _tiktok_key_ok() -> bool:
    try:
        from modules.TikTok_Auth import tiktok_api_enabled

        if not tiktok_api_enabled():
            return True
    except Exception:
        pass
    return bool(os.getenv("TIKTOK_ACCESS_TOKEN"))

# Backward-compatible aliases for code that uses `ROOT` / `PROJECT_ROOT`.
PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT


DATA_DIR = DATA_DIR  # alias kept for backwards compat with downstream code
CLIPS_DIR = CLIPS_DIR
VERTICAL_DIR = REPO_ROOT / "media" / "vertical_clips"
BRIEFINGS_DIR = DAILY_BRIEFINGS_DIR
QUEUE_FILE = DATA_DIR / "multi_platform_queue.json"
CONFIG_FILE = CONFIG_FILE  # Core/config.json
SITE_DATA_FILE = DATA_DIR / "site-data.json"

CT = timezone(timedelta(hours=-5))


def _load_json(path, default=None):
    if default is None:
        default = {}
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


_BRIEFING_NAME_PATTERNS = (
    # (regex on file stem, strptime format)
    (re.compile(r"^briefing_(\d{8})$"), "%Y%m%d"),
    (re.compile(r"^morning_(\d{4}-\d{2}-\d{2})$"), "%Y-%m-%d"),
    (re.compile(r"^(\d{4}-\d{2}-\d{2})$"), "%Y-%m-%d"),
)


def _briefing_date(path):
    """Date encoded in a briefing filename, or None for undated files."""
    for rx, fmt in _BRIEFING_NAME_PATTERNS:
        m = rx.match(path.stem)
        if m:
            try:
                return datetime.strptime(m.group(1), fmt)
            except ValueError:
                return None
    return None


def _newest_briefing_file(briefings_dir):
    """Pick the newest daily briefing.

    Files are named briefing_YYYYMMDD.md (to July 2026),
    morning_YYYY-MM-DD.md (current) or YYYY-MM-DD.md. Sorting names
    alphabetically picked "briefing_20260704" forever, so pick by the
    date in the name; fall back to latest_morning.md / newest mtime.
    """
    if not briefings_dir.exists():
        return None, None
    files = [p for p in briefings_dir.glob("*.md") if p.is_file()]
    dated = [(d, p) for p in files for d in [_briefing_date(p)] if d is not None]
    if dated:
        d, p = max(dated, key=lambda dp: (dp[0], dp[1].stat().st_mtime))
        latest = briefings_dir / "latest_morning.md"
        # latest_morning.md is rewritten every run; prefer it when it is newer
        # than the dated copy of the same day (same content, fresher).
        if latest.exists() and latest.stat().st_mtime > p.stat().st_mtime + 60:
            ld = datetime.fromtimestamp(latest.stat().st_mtime)
            if ld.date() > d.date():
                return latest, ld
        return p, d
    if files:
        p = max(files, key=lambda f: f.stat().st_mtime)
        return p, datetime.fromtimestamp(p.stat().st_mtime)
    return None, None


def _latest_briefing(briefings_dir=None):
    briefings_dir = Path(briefings_dir) if briefings_dir else BRIEFINGS_DIR
    latest, dt = _newest_briefing_file(briefings_dir)
    if latest is None:
        return {"date": datetime.now(CT).strftime("%A, %B %d, %Y"), "action_items": []}

    content = latest.read_text(errors="replace")
    date_display = dt.strftime("%A, %B %d, %Y")

    action_items = []
    in_actions = False
    for line in content.splitlines():
        if "Action Items" in line:
            in_actions = True
            continue
        if in_actions:
            stripped = line.strip()
            if (
                stripped.startswith("#")
                or stripped.startswith("```")
                or stripped.startswith("---")
            ):
                in_actions = False
                continue
            if stripped and stripped[0].isdigit():
                item = stripped.lstrip("0123456789. ").strip()
                if item:
                    action_items.append(item)

    return {"date": date_display, "action_items": action_items[:8], "source": latest.name}


def _clip_queue():
    data = _load_json(QUEUE_FILE, {"items": []})
    items = data.get("items", [])

    clips = []
    for item in items[:12]:
        platforms = item.get("platforms", [])
        tiktok = next((p for p in platforms if p.get("platform") == "tiktok"), None)
        title = "Untitled clip"
        if tiktok:
            caption = tiktok.get("caption", "")
            title = caption.split("\n")[0] if caption else "Untitled clip"
        clips.append(
            {
                "id": item.get("queue_id", ""),
                "created": item.get("created_at", ""),
                "title": title,
                "platforms": len(platforms),
                "status": tiktok.get("status", "queued") if tiktok else "queued",
            }
        )
    return clips


def _system_status():
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        pass

    clips_count = 0
    if CLIPS_DIR.exists():
        clips_count = len(list(CLIPS_DIR.glob("*.mp4"))) + len(
            list(CLIPS_DIR.glob("*.mkv"))
        )

    vertical_count = 0
    if VERTICAL_DIR.exists():
        vertical_count = len(list(VERTICAL_DIR.glob("*.mp4")))

    queue_data = _load_json(QUEUE_FILE, {"items": []})
    queue_count = len(queue_data.get("items", []))

    config = _load_json(CONFIG_FILE, {})

    return {
        "clips_made": clips_count,
        "vertical_clips": vertical_count,
        "ready_to_post": queue_count,
        "recordings_processed": len(
            _load_json(DATA_DIR / "processed_recordings.json", [])
        ),
        "api_keys": {
            "twitch": bool(os.getenv("TWITCH_CLIENT_ID")),
            "obs": bool(os.getenv("OBS_PASSWORD")),
            "discord": bool(os.getenv("DISCORD_WEBHOOK_URL")),
            "tiktok": _tiktok_key_ok(),
        },
    }


def _peak_hours():
    config = _load_json(CONFIG_FILE, {})
    windows = config.get("peak_notifications", {}).get("windows", [])
    now = datetime.now(CT)
    current_hour = now.hour

    result = []
    for w in windows:
        start = w.get("start_hour", 0)
        end = w.get("end_hour", 0)
        label = w.get("label", "")
        in_window = start <= current_hour < end
        result.append(
            {
                "label": label,
                "start_hour": start,
                "end_hour": end,
                "start_display": f"{start % 12 or 12} {'AM' if start < 12 else 'PM'}",
                "end_display": f"{end % 12 or 12} {'AM' if end < 12 else 'PM'}",
                "in_window": in_window,
                # "active" is read by the deployed billythunderstorm.live page as
                # "Billy is streaming right now". A peak window is not a stream,
                # and this file is only refreshed every ~2h, so never claim live.
                "active": False,
            }
        )
    return result


READINESS_FILE = REPO_ROOT / "Docs" / "READINESS.md"
_LEVELS = ("READY", "PARTIAL", "SHELL", "IDEA")
_PROMO_RX = re.compile(
    r"\*\*READY \((?P<day>\d{1,2})\s+(?P<mon>[A-Za-z]{3})[a-z]*\s+(?P<year>\d{4})"
    r"(?:[,\s]*~?(?P<time>\d{1,2}:\d{2}\s*[AP]M))?"
)


def _progress(readiness_path=None, recent_limit=5):
    """Bolt build progress from Docs/READINESS.md.

    Counts = table rows under each "## READY / PARTIAL / SHELL / IDEA"
    section (subsections like "### Services" are not counted).
    Recent = rows whose status cell says "**READY (20 Oct 2026 ~5:40 AM CT…"
    (the date Shells promoted them), newest first.
    """
    path = Path(readiness_path) if readiness_path else READINESS_FILE
    counts = {k: 0 for k in _LEVELS}
    recent = []
    updated = None
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return {"counts": counts, "total": 0, "percent_ready": 0, "recent": [], "updated": None, "available": False}

    m = re.search(r"last updated ([^)*]+?)\)", text[:600])
    if m:
        updated = m.group(1).strip()

    section = None
    header_seen = False
    promo_rows = []
    for line in text.splitlines():
        if line.startswith("## "):
            word = line[3:].strip().split()[0].upper() if line[3:].strip() else ""
            section = word if word in _LEVELS else None
            header_seen = False
            continue
        if line.startswith("### "):
            section = None
            continue
        if section is None:
            continue
        st = line.strip()
        if not st.startswith("|"):
            continue
        if re.match(r"^\|\s*:?-{2,}", st):
            continue
        if not header_seen:
            header_seen = True  # first row of each table is its header
            continue
        counts[section] += 1
        promo_rows.append(st)

    for row in promo_rows:
        pm = _PROMO_RX.search(row)
        if not pm:
            continue
        try:
            dt = datetime.strptime(f"{pm['day']} {pm['mon'][:3]} {pm['year']}", "%d %b %Y")
        except ValueError:
            continue
        if pm["time"]:
            try:
                t = datetime.strptime(pm["time"].replace(" ", ""), "%I:%M%p")
                dt = dt.replace(hour=t.hour, minute=t.minute)
            except ValueError:
                pass
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        name = re.sub(r"[*`~]", "", cells[0]).strip() if cells else ""
        if name:
            recent.append((dt, name))
    recent.sort(key=lambda r: r[0], reverse=True)

    total = sum(counts.values())
    pct = round(100 * counts["READY"] / total) if total else 0
    return {
        "counts": counts,
        "total": total,
        "percent_ready": pct,
        "recent": [
            {"name": n, "date": d.strftime("%Y-%m-%d"), "display": d.strftime("%b %-d") + (d.strftime(", %-I:%M %p CT") if d.hour or d.minute else "")}
            for d, n in recent[:recent_limit]
        ],
        "updated": updated,
        "available": True,
    }


def write_site_data(push=False, output_path=None):
    """Generate site-data.json from Bolt's live data.

    Args:
        push: If True, git add + commit + push after writing.
        output_path: Override output path (default: Data/site-data.json)

    Returns:
        Path to the written file.
    """
    site_data = {
        "generated_at": datetime.now(CT).strftime("%Y-%m-%d %H:%M:%S"),
        "status": _system_status(),
        "queue": _clip_queue(),
        "briefing": _latest_briefing(),
        "peaks": _peak_hours(),
        "progress": _progress(),
    }

    path = Path(output_path) if output_path else SITE_DATA_FILE
    path.write_text(json.dumps(site_data, indent=2) + "\n")
    print(f"  ⚡  Wrote site data to {path}")

    if output_path is None and MIRROR_ROOT:
        # The deployed bolt-api Worker (Jun 2026) still reads /site-data.json
        # at the repo root. Keep a mirror until the Worker is redeployed.
        try:
            ROOT_MIRROR_FILE.write_text(path.read_text())
        except OSError as exc:
            print(f"  ⚠  root mirror not written: {exc}")

    if push:
        if output_path is not None:
            print("  ⚠  --push only publishes the default Data/site-data.json; skipped")
        else:
            push_site_data()

    return path


MIRROR_ROOT = os.getenv("BOLT_SITE_MIRROR_ROOT", "1") != "0"
ROOT_MIRROR_FILE = REPO_ROOT / "site-data.json"
PUSH_LOG = REPO_ROOT / "logs" / "site_data_push.log"
PUSH_REMOTE = os.getenv("BOLT_SITE_REMOTE", "origin")
PUSH_BRANCH = os.getenv("BOLT_SITE_BRANCH", "main")


def _log_push(msg):
    line = f"[{datetime.now(CT).strftime('%Y-%m-%d %H:%M:%S')} CT] {msg}"
    print(f"  {msg}")
    try:
        PUSH_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(PUSH_LOG, "a") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _git(args, *, repo, env=None, timeout=60, check=True):
    r = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True,
        timeout=timeout, env=env,
    )
    if check and r.returncode != 0:
        raise subprocess.CalledProcessError(r.returncode, ["git", *args], r.stdout, r.stderr)
    return r.stdout.strip()


def push_site_data(repo=None, files=None, remote=None, branch=None, attempts=2):
    """Publish ONLY the site-data file(s) to GitHub. Never raises.

    Builds a one-file commit on top of the fetched remote branch with a
    private index (plumbing), so it never stages, sweeps in, stashes or
    rebases anything else in the working tree. If the push races another
    push it re-fetches and retries; any other failure is logged to
    logs/site_data_push.log and skipped (soft-fail).

    When the local branch has no commits of its own beyond the remote,
    it is fast-forwarded to the new commit (only the published paths'
    index entries change; their working-tree content already matches).
    """
    repo = Path(repo) if repo else REPO_ROOT
    remote = remote or PUSH_REMOTE
    branch = branch or PUSH_BRANCH
    if files is None:
        files = [SITE_DATA_FILE]
        if MIRROR_ROOT and ROOT_MIRROR_FILE.exists():
            files.append(ROOT_MIRROR_FILE)
    rels = [str(Path(f).resolve().relative_to(repo.resolve())) for f in files]
    tmp_index = repo / ".git" / "site-data-push.index"
    try:
        for attempt in range(1, attempts + 1):
            _git(["fetch", "--quiet", remote, branch], repo=repo, timeout=60)
            base = _git(["rev-parse", f"refs/remotes/{remote}/{branch}"], repo=repo)
            env = dict(os.environ, GIT_INDEX_FILE=str(tmp_index))
            _git(["read-tree", base], repo=repo, env=env)
            blobs = {}
            for rel in rels:
                blob = _git(["hash-object", "-w", "--", rel], repo=repo)
                blobs[rel] = blob
                _git(["update-index", "--add", "--cacheinfo", f"100644,{blob},{rel}"], repo=repo, env=env)
            tree = _git(["write-tree"], repo=repo, env=env)
            if tree == _git(["rev-parse", f"{base}^{{tree}}"], repo=repo):
                _log_push("site data unchanged on GitHub; nothing to push")
                return "unchanged"
            msg = f"site data update — {datetime.now(CT).strftime('%b %d, %H:%M')} CT"
            commit = _git(["commit-tree", tree, "-p", base, "-m", msg], repo=repo)
            r = subprocess.run(
                ["git", "push", "--quiet", remote, f"{commit}:refs/heads/{branch}"],
                cwd=str(repo), capture_output=True, text=True, timeout=90,
            )
            if r.returncode == 0:
                _git(["update-ref", f"refs/remotes/{remote}/{branch}", commit], repo=repo, check=False)
                _fast_forward_local(repo, branch, base, commit, blobs)
                _log_push(f"pushed site data {commit[:8]} ({', '.join(rels)})")
                return "pushed"
            err = (r.stderr or "").strip().splitlines()
            reason = err[-1] if err else f"exit {r.returncode}"
            if attempt < attempts and ("rejected" in r.stderr or "fetch first" in r.stderr or "non-fast-forward" in r.stderr):
                _log_push(f"push raced another update ({reason}); retrying on fresh {remote}/{branch}")
                continue
            _log_push(f"Sites unavailable: git push failed: {reason} (local site-data.json still written)")
            return "failed"
        return "failed"
    except subprocess.TimeoutExpired as exc:
        _log_push(f"Sites unavailable: git timed out ({' '.join(exc.cmd[:3])}); local file still written")
    except subprocess.CalledProcessError as exc:
        err = ((exc.stderr or "") if isinstance(exc.stderr, str) else "").strip().splitlines()
        _log_push(f"Sites unavailable: {' '.join(exc.cmd[:3])} failed: {err[-1] if err else exc.returncode}")
    except (OSError, ValueError) as exc:
        _log_push(f"Sites unavailable: {exc}")
    finally:
        try:
            tmp_index.unlink()
        except OSError:
            pass
    return "failed"


def _fast_forward_local(repo, branch, base, commit, blobs):
    """Move the local branch to the data commit only when that is a pure
    fast-forward of an otherwise-identical branch. Best-effort."""
    try:
        head_ref = _git(["symbolic-ref", "-q", "HEAD"], repo=repo, check=False)
        local = _git(["rev-parse", "-q", "--verify", f"refs/heads/{branch}"], repo=repo, check=False)
        if local != base:
            _log_push(
                f"local {branch} is not at {base[:8]}; left it alone "
                f"(pull/rebase later picks up the data commit)"
            )
            return
        _git(["update-ref", f"refs/heads/{branch}", commit, base], repo=repo)
        if head_ref == f"refs/heads/{branch}":
            for rel, blob in blobs.items():
                _git(["update-index", "--add", "--cacheinfo", f"100644,{blob},{rel}"], repo=repo)
    except Exception as exc:  # noqa: BLE001 - never break the writer
        _log_push(f"local fast-forward skipped: {exc}")


def status(*, probe: bool = False):
    """Write-path / git-remote readiness. Never raises."""
    info = {
        "ready": True,
        "site_data_path": str(SITE_DATA_FILE),
        "site_data_exists": SITE_DATA_FILE.exists(),
        "site_data_mtime": None,
        "git_remote": False,
        "hint": "",
    }
    try:
        if SITE_DATA_FILE.exists():
            ts = SITE_DATA_FILE.stat().st_mtime
            info["site_data_mtime"] = datetime.fromtimestamp(ts).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
    except OSError as exc:
        info["ready"] = False
        info["hint"] = f"Sites unavailable: cannot stat site-data ({exc})"
    try:
        r = subprocess.run(
            ["git", "remote"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        info["git_remote"] = bool((r.stdout or "").strip()) and r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        info["git_remote"] = False

    if not info["hint"]:
        if info["git_remote"]:
            info["hint"] = (
                "Local write path OK; git remote present. "
                "Try: bolt site / bolt site --push"
            )
        else:
            info["hint"] = (
                "Sites unavailable: git remote not configured "
                "(local write still works; --push soft-fails)"
            )

    try:
        lines = PUSH_LOG.read_text().strip().splitlines() if PUSH_LOG.exists() else []
        info["last_push_log"] = lines[-1] if lines else None
    except OSError:
        info["last_push_log"] = None

    if probe:
        info["probe_ok"] = False
        info["probe_detail"] = ""
        try:
            probe_path = DATA_DIR / ".site-data-probe.json"
            write_site_data(push=False, output_path=str(probe_path))
            ok = probe_path.exists() and probe_path.stat().st_size > 0
            try:
                probe_path.unlink(missing_ok=True)
            except OSError:
                pass
            if ok:
                info["probe_ok"] = True
                info["probe_detail"] = f"ok — wrote probe under {DATA_DIR.name}/"
            else:
                info["probe_detail"] = "Sites unavailable: probe write empty"
                info["hint"] = info["probe_detail"]
                info["ready"] = False
        except Exception as exc:
            info["probe_detail"] = f"Sites unavailable: probe failed ({exc})"
            info["hint"] = info["probe_detail"]
            info["ready"] = False
    return info


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    """Print write-specific status. Always exit 0."""
    info = status(probe=probe)
    if as_json:
        print(json.dumps(info, indent=2, default=str))
        return 0
    print("\n  Site data writer")
    print("  " + "─" * 40)
    flag = "✓" if info.get("ready") else "○"
    print(f"  {flag}  ready: {bool(info.get('ready'))}")
    print(f"      path: {info.get('site_data_path')}")
    print(f"      exists: {info.get('site_data_exists')}")
    if info.get("site_data_mtime"):
        print(f"      mtime: {info.get('site_data_mtime')}")
    print(f"      git_remote: {info.get('git_remote')}")
    if info.get("hint"):
        print(f"      → {info['hint']}")
    if probe:
        pflag = "✓" if info.get("probe_ok") else "○"
        print(f"  {pflag}  probe: {info.get('probe_detail') or '(none)'}")
    print()
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help", "help"):
        print(
            "site_data_writer — write Data/site-data.json\n"
            "  python scripts/site_data_writer.py\n"
            "  python scripts/site_data_writer.py --push\n"
            "  python scripts/site_data_writer.py status [--json] [--probe]\n"
            "  python scripts/site_data_writer.py --path /custom/site-data.json\n"
        )
        raise SystemExit(0)

    json_out = "--json" in args
    probe = "--probe" in args
    push = "--push" in args
    path_arg = None
    for i, arg in enumerate(args):
        if arg == "--path" and i + 1 < len(args):
            path_arg = args[i + 1]

    positionals = [a for a in args if not a.startswith("-")]
    if positionals and positionals[0].lower() in ("status", "check", "ready"):
        raise SystemExit(print_status(as_json=json_out, probe=probe))
    if not positionals and (json_out or probe) and not push and path_arg is None:
        raise SystemExit(print_status(as_json=json_out, probe=probe))

    write_site_data(push=push, output_path=path_arg)
