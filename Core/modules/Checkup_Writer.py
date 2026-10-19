#!/usr/bin/env python3
"""
modules/Checkup_Writer.py — Live data bridge for App/Bolt_Checkup.html
=======================================================================
The checkup dashboard is a static HTML file — it can't pull data by itself.
This module bridges that gap: it reads Bolt's real runtime data and writes
a small JavaScript file that the HTML page loads on refresh.

Why a .js file instead of JSON?
  Browsers block fetch() requests to local files (file:// protocol) due to
  security restrictions. But <script src="..."> for local files works fine.
  So we write the data as a JS variable: window.Bolt_DATA = {...}
  App/Bolt_Checkup.html reads window.Bolt_DATA and populates itself.

When does this run?
  - Called by launch.py at startup (so the page is fresh when you open it)
  - Called by bot.py after each pipeline run (so stats update as clips process)
  - CLI: bolt checkup [--open] [--json]
  - Standalone: python -m modules.Checkup_Writer
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path, PurePosixPath

from modules.Clip_Ranker import parse_clip_filename

# Post-reorg layout: this file lives at Core/modules/ → repo root is parents[2]
_REPO = Path(__file__).resolve().parents[2]

# Prefer post-reorg paths; fall back to legacy names if someone still uses them.
DATA_DIR = _REPO / "Data"
if not DATA_DIR.exists():
    DATA_DIR = _REPO / "data"

CLIPS_DIR = _REPO / "media" / "clips"
if not CLIPS_DIR.exists():
    CLIPS_DIR = _REPO / "clips"

VERTICAL_DIR = _REPO / "media" / "vertical_clips"
if not VERTICAL_DIR.exists():
    VERTICAL_DIR = _REPO / "vertical_clips"

RANKINGS_FILE = DATA_DIR / "rankings.json"
QUEUE_FILE = DATA_DIR / "ready_to_post.json"
OUTPUT_FILE = DATA_DIR / "Bolt_data.js"
HTML_FILE = _REPO / "App" / "Bolt_Checkup.html"
# Thumbnails and "does this file exist?" checks stay inside this root.
# `bolt review --fixtures` points it at a sample directory. The live board uses the repo.
REVIEW_MEDIA_ROOT = _REPO

_VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".webm", ".m4v"}
# The review board plays these in a browser. mkv stays a real file for
# `file_exists` but is not offered as inline video.
_PLAYABLE_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
_THUMB_SUFFIXES = {".jpg", ".jpeg"}
_CLOSED_REVIEW_STATUSES = {"posted", "scrapped"}


def _count_clips() -> int:
    """Count how many clips exist in the clips folder."""
    if not CLIPS_DIR.exists():
        return 0
    return len(list(CLIPS_DIR.glob("*.mp4"))) + len(list(CLIPS_DIR.glob("*.mkv")))


def _count_vertical_clips() -> int:
    """Count TikTok-formatted vertical clips."""
    if not VERTICAL_DIR.exists():
        return 0
    return len(list(VERTICAL_DIR.glob("*.mp4")))


def _load_rankings() -> list:
    """Load clip rankings from rankings.json."""
    if not RANKINGS_FILE.exists():
        return []
    try:
        with open(RANKINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return data.get("rankings", [])
    except Exception:
        return []


def _load_queue() -> list:
    """Load the post queue from ready_to_post.json."""
    if not QUEUE_FILE.exists():
        return []
    try:
        with open(QUEUE_FILE, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return data.get("items", data.get("clips", data.get("queue", [])))
    except Exception:
        return []


def _tiktok_key_ok() -> bool:
    """Token is only required while the TikTok Open API is enabled."""
    try:
        from modules.TikTok_Auth import tiktok_api_enabled

        if not tiktok_api_enabled():
            return True
    except Exception:
        pass
    return bool(os.getenv("TIKTOK_ACCESS_TOKEN"))


def _check_env_keys() -> dict:
    """
    Check which API keys are present in .env.
    Returns a dict of key_name -> True/False.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(_REPO / ".env.local")
        load_dotenv(_REPO / ".env")
    except Exception:
        pass
    return {
        "twitch": bool(os.getenv("TWITCH_CLIENT_ID")),
        "obs": bool(os.getenv("OBS_PASSWORD")),
        "streamlabs": bool(os.getenv("STREAMLABS_SOCKET_TOKEN")),
        "discord": bool(os.getenv("DISCORD_WEBHOOK_URL")),
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "xai": bool(os.getenv("XAI_API_KEY")),
        "tiktok": _tiktok_key_ok(),
        "bot_token": bool(os.getenv("TWITCH_BOT_TOKEN")),
    }


def _load_performance_totals() -> tuple[int, int, int]:
    """Return (clips_posted, total_views, total_likes) from performance log."""
    candidates = [
        DATA_DIR / "performance_outcomes.jsonl",
    ]
    total_views = 0
    total_likes = 0
    clips_posted = 0
    for perf_file in candidates:
        if not perf_file.exists():
            continue
        try:
            with open(perf_file, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue
                    total_views += int(data.get("views", 0) or 0)
                    total_likes += int(data.get("likes", 0) or 0)
                    clips_posted += 1
        except Exception:
            continue
        break  # use first file that exists
    return clips_posted, total_views, total_likes


def _count_processed_recordings() -> int:
    candidates = [
        DATA_DIR / "processed_recordings.json",
    ]
    for processed_file in candidates:
        if not processed_file.exists():
            continue
        try:
            with open(processed_file, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return len(data)
            if isinstance(data, dict):
                return len(data.get("processed", data.get("files", [])))
        except Exception:
            continue
    return 0


def _section(fn):
    """Run one morning section. A failure becomes {"error": "..."} and stops there."""
    try:
        value = fn()
    except Exception as exc:
        return {"error": f"{exc.__class__.__name__}: {exc}"[:240]}
    if not isinstance(value, dict):
        return {"error": "section did not return a dict"}
    return value


def _bash_commands(text: str) -> str:
    """Pull the command lines out of a ```bash fence, if one is present."""
    match = re.search(r"```bash\s*(.*?)```", text or "", re.DOTALL)
    if not match:
        return ""
    lines = [line.strip() for line in match.group(1).splitlines() if line.strip()]
    return "\n".join(lines)


def _as_score(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _morning_header() -> dict:
    creator = "William"
    lanes = ["game", "tech"]
    # Lazy import: Content_Manager pulls in the catalog helpers. If that import
    # fails, the greeting still renders and the actions section reports its own error.
    try:
        from modules.Content_Manager import CREATOR_NAME, PREFERRED_LANES

        if CREATOR_NAME:
            creator = str(CREATOR_NAME)
        if PREFERRED_LANES:
            lanes = [str(lane) for lane in PREFERRED_LANES]
    except Exception:
        pass
    return {
        "greeting": f"Good morning, {creator}",
        "creator": creator,
        "lanes": lanes,
        "date": date.today().isoformat(),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _mission_checkin(text: str) -> dict:
    labels = {
        "time available": "hours",
        "max budget": "budget",
        "already owned / usable": "assets",
        "already owned": "assets",
    }
    found: dict = {}
    for line in text.splitlines():
        match = re.match(r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", line)
        if not match:
            continue
        label = match.group(1).strip().lower()
        key = labels.get(label)
        if key:
            found[key] = match.group(2).strip()
    return found


def _mission_title(text: str, path: Path) -> str:
    goal = re.search(r"\*\*Goal:\*\*\s*(.+)", text)
    if goal and goal.group(1).strip():
        return goal.group(1).strip()
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            if title and "mission briefing" not in title.lower():
                return title
            break
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", path.stem)
    pretty = stem.replace("-", " ").strip()
    return pretty or "Mission"


def _mission_date(text: str, path: Path) -> str:
    stamped = re.search(r"\*\*Date:\*\*\s*(\d{4}-\d{2}-\d{2})", text)
    if stamped:
        return stamped.group(1)
    prefix = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
    return prefix.group(1) if prefix else ""


def _mission_actions(text: str) -> list:
    checks = re.findall(r"^- \[[ xX]\] (.+)$", text, re.MULTILINE)
    lines = [item.strip() for item in checks if item.strip()]
    if lines:
        return lines[:3]
    steps = re.findall(r"^\d+\.\s+(.+)$", text, re.MULTILINE)
    return [item.strip() for item in steps if item.strip()][:3]


def _mission_command(text: str, goal: str) -> str:
    """Next command from _default_next_command. Skip it if that call is not cheap."""
    try:
        from modules.Command_Center import _default_next_command

        week = re.search(r"\*\*This week:\*\*\s*(.+)", text)
        topic = week.group(1).strip() if week else ""
        evidence = {
            "week": {"this_week": topic},
            "research": {"candidates_pending_c5": 0},
        }
        raw = _default_next_command(goal, _mission_checkin(text), evidence)
        return _bash_commands(raw)
    except Exception:
        return ""


def _morning_mission() -> dict:
    from modules.Command_Center import latest_mission

    path = latest_mission()
    if path is None:
        return {"empty": True, "hint": "No mission yet. Run `bolt mission`."}
    text = path.read_text(encoding="utf-8")
    title = _mission_title(text, path)
    mission_date = _mission_date(text, path)
    stale = False
    if mission_date:
        try:
            age = (date.today() - date.fromisoformat(mission_date)).days
            stale = age > 7
        except ValueError:
            stale = False
    return {
        "empty": False,
        "title": title,
        "date": mission_date,
        "stale": stale,
        "actions": _mission_actions(text),
        "command": _mission_command(text, title),
        "file": path.name,
    }


def _queue_status_counts(queue: list) -> dict:
    """Same buckets as scripts/daily_briefing.py _queue_counts()."""
    counts = {"total": 0, "ready": 0, "posted": 0, "scrapped": 0, "other": 0}
    counts["total"] = len(queue)
    for item in queue:
        if not isinstance(item, dict):
            counts["other"] += 1
            continue
        status = (item.get("status") or "unknown").lower()
        if status == "ready":
            counts["ready"] += 1
        elif status == "posted":
            counts["posted"] += 1
        elif status == "scrapped":
            counts["scrapped"] += 1
        else:
            counts["other"] += 1
    return counts


def _read_json_document(path: Path):
    """Read a JSON file. Missing file is None. Bad JSON raises."""
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _json_rows(data) -> list:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "clips", "queue", "rankings"):
            rows = data.get(key)
            if isinstance(rows, list):
                return rows
    return []


def _ranking_scores(rankings: list) -> dict:
    lookup = {}
    for row in rankings:
        if not isinstance(row, dict):
            continue
        score = _as_score(row.get("score"))
        if score is None:
            continue
        for key in ("clip_path", "path", "file", "filename", "title", "name"):
            raw = str(row.get(key) or "").strip()
            if not raw:
                continue
            lookup[raw.lower()] = score
            lookup[Path(raw).name.lower()] = score
    return lookup


# Filename suffixes Bolt already uses, plus a vertical-folder fallback.
# Vertical clips are the TikTok export (media/vertical_clips/).
_PLATFORM_SUFFIXES = (
    ("_tiktok", "TikTok"),
    ("_youtube", "YouTube"),
    ("_shorts", "Shorts"),
    ("_reels", "Reels"),
)


def _infer_platform(clip_path: str, explicit) -> str:
    """Use an explicit platform, else guess from the filename or folder."""
    if isinstance(explicit, list):
        explicit = ", ".join(str(part) for part in explicit if str(part).strip())
    text = str(explicit or "").strip()
    if text:
        return text
    if not clip_path:
        return ""
    path = Path(clip_path)
    stem = path.stem.lower()
    for suffix, label in _PLATFORM_SUFFIXES:
        if stem.endswith(suffix):
            return label
    for part in path.parts[:-1]:
        token = part.lower()
        if token == "vertical" or token.startswith("vertical"):
            return "TikTok"
    return ""


def _listed_status(raw: str) -> str:
    """Card pill: ready stays ready. Every other still-open row is queued."""
    return "ready" if raw == "ready" else "queued"


def _clip_score(item: dict, lookup: dict):
    score = _as_score(item.get("score"))
    if score is not None:
        return score
    for key in ("clip_path", "path", "file", "filename", "title"):
        raw = str(item.get(key) or "").strip()
        if not raw:
            continue
        if raw.lower() in lookup:
            return lookup[raw.lower()]
        name = Path(raw).name.lower()
        if name in lookup:
            return lookup[name]
    return None


def _path_inside(path: Path, root: Path) -> Path | None:
    """Resolved path if it stays inside `root` after symlink resolution."""
    try:
        resolved = path.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    return resolved


def _child_inside(parent: Path, name: str, root: Path) -> Path | None:
    """One path segment under `parent`, case-insensitive, still inside `root`."""
    if name in ("", ".", "..") or "/" in name or "\\" in name or "\x00" in name:
        return None
    chosen: Path | None = None
    direct = parent / name
    try:
        if direct.exists():
            chosen = direct
    except OSError:
        chosen = None
    if chosen is None:
        if not parent.is_dir():
            return None
        folded = name.casefold()
        try:
            for child in parent.iterdir():
                if child.name.casefold() == folded:
                    chosen = child
                    break
        except OSError:
            return None
    if chosen is None or _path_inside(chosen, root) is None:
        return None
    return chosen


def _walk_inside(root: Path, parts: list[str]) -> Path | None:
    current = root
    for part in parts:
        nxt = _child_inside(current, part, root)
        if nxt is None:
            return None
        current = nxt
    inside = _path_inside(current, root)
    if inside is None or not inside.is_file():
        return None
    return inside


def resolve_clip_in_root(clip_path: str, root: Path | None = None) -> Path | None:
    """Map a queue path onto a file inside `root`.

    Queue rows often store absolute Mac paths (`/Users/carter/developer/Bolt/media/...`)
    whose casing may not match this checkout. The lookup uses the `media/`,
    `clips/`, or `vertical_clips/` suffix and walks case-insensitively.
    A file that resolves outside `root` is ignored.
    """
    base = (root or REVIEW_MEDIA_ROOT).resolve()
    raw = str(clip_path or "").strip()
    if not raw or "\x00" in raw:
        return None
    direct = Path(raw)
    if direct.is_absolute():
        inside = _path_inside(direct, base)
        if inside is not None and inside.is_file():
            return inside

    posix = raw.replace("\\", "/")
    parts = [part for part in PurePosixPath(posix).parts if part not in ("/", "")]
    lowers = [part.casefold() for part in parts]
    candidates: list[list[str]] = []
    for index in range(len(lowers) - 1, -1, -1):
        if lowers[index] == "media":
            candidates.append(parts[index:])
    for index in range(len(lowers) - 1, -1, -1):
        part = lowers[index]
        if part in ("clips", "vertical_clips") and (
            index == 0 or lowers[index - 1] != "media"
        ):
            candidates.append(parts[index:])
    if not posix.startswith("/"):
        candidates.append(parts)

    seen: set[tuple[str, ...]] = set()
    for rel in candidates:
        if not rel or any(part in ("", ".", "..") for part in rel):
            continue
        key = tuple(part.casefold() for part in rel)
        if key in seen:
            continue
        seen.add(key)
        found = _walk_inside(base, rel)
        if found is not None:
            return found
    return None


def review_file_exists(clip_path: str, root: Path | None = None) -> bool:
    """True when the queued video is on disk, including a repo-relative match."""
    raw = str(clip_path or "").strip()
    if raw:
        try:
            if Path(raw).is_file():
                return True
        except OSError:
            pass
    found = resolve_clip_in_root(raw, root)
    return bool(found and found.suffix.lower() in _VIDEO_SUFFIXES)


def playable_video_for_clip(clip_path: str, root: Path | None = None) -> Path | None:
    """Browser-playable video inside `root`, or None.

    Same root rule as thumbnails: the resolved file must stay inside `root`.
    """
    base = (root or REVIEW_MEDIA_ROOT).resolve()
    video = resolve_clip_in_root(clip_path, base)
    if video is None or not video.is_file():
        return None
    try:
        video.relative_to(base)
    except ValueError:
        return None
    if video.suffix.lower() not in _PLAYABLE_VIDEO_SUFFIXES:
        return None
    return video


def thumbnail_for_clip(clip_path: str, root: Path | None = None) -> Path | None:
    """JPG next to the clip, same stem, and only if it stays inside `root`."""
    base = (root or REVIEW_MEDIA_ROOT).resolve()
    video = resolve_clip_in_root(clip_path, base)
    if video is not None:
        for suffix in (".jpg", ".jpeg"):
            inside = _path_inside(video.with_suffix(suffix), base)
            if inside is not None and inside.is_file() and inside.suffix.lower() in _THUMB_SUFFIXES:
                return inside
    raw = str(clip_path or "").strip()
    if not raw:
        return None
    for suffix in (".jpg", ".jpeg"):
        found = resolve_clip_in_root(str(Path(raw).with_suffix(suffix)), base)
        if found is not None and found.suffix.lower() in _THUMB_SUFFIXES:
            return found
    return None


def _review_sort_key(clip: dict):
    score = clip.get("score")
    numeric = score if isinstance(score, (int, float)) else -1
    return (0 if clip.get("actionable") else 1, -numeric, str(clip.get("filename") or ""))


def _review_counts(clips: list) -> dict:
    counts = {
        "total": len(clips),
        "ready": 0,
        "held": 0,
        "posted": 0,
        "scrapped": 0,
        "other": 0,
        "actionable": 0,
    }
    for clip in clips:
        status = str(clip.get("status") or "")
        if status == "ready":
            counts["ready"] += 1
        elif status == "held":
            counts["held"] += 1
        elif status == "posted":
            counts["posted"] += 1
        elif status == "scrapped":
            counts["scrapped"] += 1
        else:
            counts["other"] += 1
        if clip.get("actionable"):
            counts["actionable"] += 1
    return counts


def _review_row(item: dict, lookup: dict) -> dict:
    clip_path = str(item.get("clip_path") or item.get("path") or item.get("file") or "")
    filename = Path(clip_path).name if clip_path else ""
    parsed = parse_clip_filename(clip_path) if clip_path else {}
    trigger = str(item.get("trigger") or parsed.get("trigger") or "")
    status = str(item.get("status") or "").lower()
    tier = str(item.get("tier") or "")
    score = _clip_score(item, lookup)
    exists = review_file_exists(clip_path)
    listed = _listed_status(status)
    if status == "held":
        pill = "held"
    elif status == "ready" and tier == "mid":
        pill = "queued"
    elif status in _CLOSED_REVIEW_STATUSES:
        pill = status
    else:
        pill = listed
    title = str(item.get("title") or "").strip()
    if not title:
        title = Path(filename).stem if filename else "Untitled clip"
    return {
        "id": str(item.get("id") or ""),
        "title": title,
        "score": score,
        "status": status,
        "pill": pill,
        "tier": tier,
        "trigger": trigger,
        "clip_index": parsed.get("index"),
        "platform": _infer_platform(clip_path, item.get("platform")),
        "filename": filename,
        "file_exists": exists,
        "ghost": status not in _CLOSED_REVIEW_STATUSES and not exists,
        "hold_reason": str(item.get("hold_reason") or ""),
        "has_thumbnail": thumbnail_for_clip(clip_path) is not None,
        "has_video": playable_video_for_clip(clip_path) is not None,
        "hidden_default": status in _CLOSED_REVIEW_STATUSES,
        "actionable": status == "ready" and exists,
    }


def gather_review() -> dict:
    """Read-only snapshot of the clip queue for the review board and checkup card.

    Does not call `_ensure_auto_post_plan` or write the queue. Posted and scrapped
    rows stay in `clips` so the board can reveal them; `top` is the first three
    still-open rows after the actionable-then-score sort.
    """
    footer = "Keep never posts. Posting still needs `bolt approve` / your OK."
    command = "bolt review"
    empty_hint = "No clips in the queue yet. Process a recording, then run `bolt queue list`."
    if not QUEUE_FILE.exists():
        counts = _review_counts([])
        return {
            "empty": True,
            "hint": empty_hint,
            "counts": counts,
            "clips": [],
            "top": [],
            "command": command,
            "footer": footer,
            "thumbnail_tip": False,
        }
    rows = [row for row in _load_queue() if isinstance(row, dict)]
    lookup = _ranking_scores(_json_rows(_read_json_document(RANKINGS_FILE)))
    clips = [_review_row(row, lookup) for row in rows]
    clips.sort(key=_review_sort_key)
    counts = _review_counts(clips)
    if not clips:
        return {
            "empty": True,
            "hint": empty_hint,
            "counts": counts,
            "clips": [],
            "top": [],
            "command": command,
            "footer": footer,
            "thumbnail_tip": False,
        }
    hint = ""
    if counts["actionable"] == 0:
        hint = (
            f"Nothing to review: {counts['posted']} posted, "
            f"{counts['scrapped']} scrapped, {counts['held']} held."
        )
    top = [
        {
            "id": clip["id"],
            "title": clip["title"],
            "score": clip["score"],
            "status": clip["pill"],
        }
        for clip in clips
        if not clip["hidden_default"]
    ][:3]
    open_rows = [clip for clip in clips if not clip["hidden_default"]]
    return {
        "empty": False,
        "hint": hint,
        "counts": counts,
        "clips": clips,
        "top": top,
        "command": command,
        "footer": footer,
        "thumbnail_tip": any(not clip["has_thumbnail"] for clip in open_rows),
    }


def _morning_clips() -> dict:
    queue_data = _read_json_document(QUEUE_FILE)
    rank_data = _read_json_document(RANKINGS_FILE)
    queue = _json_rows(queue_data)
    lookup = _ranking_scores(_json_rows(rank_data))
    counts = _queue_status_counts(queue)
    postable = []
    for item in queue:
        if not isinstance(item, dict):
            continue
        status = (item.get("status") or "").lower()
        if status in ("posted", "scrapped"):
            continue
        clip_path = str(item.get("clip_path") or item.get("path") or item.get("file") or "")
        postable.append(
            {
                "title": str(item.get("title") or "Untitled clip"),
                "score": _clip_score(item, lookup),
                "file": Path(clip_path).name if clip_path else "",
                "platform": _infer_platform(clip_path, item.get("platform")),
                "status": _listed_status(status),
            }
        )

    def _by_score(row: dict):
        return row["score"] if row["score"] is not None else -1

    ready = [row for row in postable if row["status"] == "ready"]
    queued = [row for row in postable if row["status"] != "ready"]
    ready.sort(key=_by_score, reverse=True)
    queued.sort(key=_by_score, reverse=True)
    top = (ready + queued)[:3]
    summary = (
        f"Ready {counts['ready']} · In queue {counts['other']} · Posted {counts['posted']}"
    )
    if not top:
        return {
            "empty": True,
            "hint": "Queue is empty. Run the clip pipeline / `bolt checkup` after processing.",
            "counts": counts,
            "summary": summary,
            "clips": [],
        }
    return {"empty": False, "hint": "", "counts": counts, "summary": summary, "clips": top}


def _candidate_pick(entry: dict) -> dict:
    return {
        "name": str(entry.get("name") or entry.get("creator") or "").strip(),
        "platform": str(entry.get("platform") or "").strip(),
        "verdict": str(entry.get("c5_verdict") or "").strip(),
    }


def _morning_research() -> dict:
    from modules import Researcher as researcher

    empty = {
        "empty": True,
        "hint": "No research picks yet. `bolt research find`",
        "counts": {"kept": 0, "dropped": 0, "pending_c5": 0, "blocked_c7": 0},
        "kept": [],
        "pending": [],
    }
    # list_candidates() creates a missing log. Stay read-only when there is nothing to read.
    if not researcher.RESEARCH_LOG.exists():
        return empty
    report = researcher.summary()
    kept = []
    pending = []
    for entry in researcher.list_candidates(limit=200):
        if not isinstance(entry, dict):
            continue
        pick = _candidate_pick(entry)
        if not pick["name"]:
            continue
        gate = (entry.get("gate") or {}).get("verdict")
        verdict = pick["verdict"]
        if verdict == "fits" and len(kept) < 3:
            kept.append(pick)
        elif verdict == "maybe" or (gate == "cleared" and not verdict):
            if len(pending) < 3:
                if not verdict:
                    pick["verdict"] = "pending"
                pending.append(pick)
    counts = {
        "kept": int(report.get("candidates_kept") or 0),
        "dropped": int(report.get("candidates_dropped") or 0),
        "pending_c5": int(report.get("candidates_pending_c5") or 0),
        "blocked_c7": int(report.get("candidates_blocked_c7") or 0),
    }
    if not kept and not pending and not any(counts.values()):
        return empty
    return {
        "empty": False,
        "hint": "",
        "counts": counts,
        "kept": kept,
        "pending": pending,
    }


def _catalog_items() -> list:
    """Read the catalog without calling _ensure_seed_files()."""
    from modules import Content_Manager as content

    path = content.CATALOG_FILE
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("items") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _morning_actions() -> dict:
    items = _catalog_items()
    if not items:
        return {
            "empty": True,
            "hint": "Nothing queued. `bolt manage add …`",
            "testing": 0,
            "items": [],
            "advance": None,
            "lesson": "",
        }
    # Catalog exists, so the manager helpers are worth calling. They may seed
    # missing sibling files (sponsors, playbook). That is the manager's own
    # behavior; this card does not call sponsors_find() or store_feature_next().
    from modules.Content_Manager import advance_next, business_lesson, list_items, next_actions

    actions = next_actions(limit=3)
    testing = list_items(status="testing")
    advance = advance_next()
    lesson = business_lesson()
    return {
        "empty": False,
        "hint": "",
        "testing": len(testing),
        "items": [
            {
                "type": str(action.get("type") or ""),
                "title": str(action.get("title") or ""),
                "why": str(action.get("why") or ""),
                "command": str(action.get("command") or ""),
            }
            for action in actions
            if isinstance(action, dict)
        ],
        "advance": {
            "title": str(advance.get("title") or ""),
            "why": str(advance.get("why") or ""),
            "command": str(advance.get("command") or ""),
        },
        "lesson": str(lesson or ""),
    }


def gather_morning() -> dict:
    """
    Local snapshot for the Good Morning Bolt card.

    Each section is isolated: one bad file cannot blank the rest of the checkup.
    No LLM calls, no network, no TTS.
    """
    try:
        header = _morning_header()
    except Exception as exc:
        header = {
            "greeting": "Good morning",
            "creator": "",
            "lanes": [],
            "date": "",
            "generated_at": "",
            "error": f"{exc.__class__.__name__}: {exc}"[:240],
        }
    morning = dict(header)
    morning["mission"] = _section(_morning_mission)
    morning["clips"] = _section(_morning_clips)
    morning["research"] = _section(_morning_research)
    morning["actions"] = _section(_morning_actions)
    morning["footer"] = "All posts still need your approval."
    try:
        briefing = _REPO / "Docs" / "briefings" / "daily" / "latest_morning.md"
        morning["briefing_href"] = (
            "../Docs/briefings/daily/latest_morning.md" if briefing.is_file() else ""
        )
    except Exception:
        morning["briefing_href"] = ""
    return morning


def gather_stats() -> dict:
    """
    Read all real Bolt data and return a stats dict.
    This is what gets written into Bolt_data.js for the dashboard.
    """
    rankings = _load_rankings()
    queue = _load_queue()
    clips = _count_clips()
    vertical = _count_vertical_clips()
    keys = _check_env_keys()
    clips_posted, total_views, total_likes = _load_performance_totals()

    # Count highlights from rankings (each ranking entry = one detected highlight)
    highlight_count = len(rankings)

    # Count titles generated (clips that have a title in the queue)
    titles_generated = sum(
        1 for item in queue if str(item.get("title", "")).strip()
    )

    # Average clip score
    scores = [
        item.get("score", 0) for item in queue if item.get("score") is not None
    ]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    # Top clip
    top_clip = None
    if queue:
        sorted_q = sorted(queue, key=lambda x: x.get("score", 0) or 0, reverse=True)
        top = sorted_q[0]
        top_clip = {
            "title": top.get("title", "Untitled clip"),
            "score": top.get("score", 0),
            "path": Path(str(top.get("clip_path", "") or "")).name,
        }

    stats = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "clips_made": clips,
        "vertical_clips": vertical,
        "highlights": highlight_count,
        "titles_generated": titles_generated,
        "ready_to_post": len(queue),
        "avg_score": avg_score,
        "top_clip": top_clip,
        "api_keys": keys,
        "clips_posted": clips_posted,
        "total_views": total_views,
        "total_likes": total_likes,
        "recordings_processed": _count_processed_recordings(),
        "phase": {
            "current": 3,
            "p1_done": True,
            "p2_done": True,
            "p3_active": True,
            "p4_done": False,
        },
    }
    try:
        stats["morning"] = gather_morning()
    except Exception as exc:
        stats["morning"] = {"error": f"{exc.__class__.__name__}: {exc}"[:240]}
    try:
        review = gather_review()
        stats["review"] = {
            "empty": review["empty"],
            "hint": review["hint"],
            "counts": review["counts"],
            "top": review["top"],
            "command": review["command"],
            "footer": review["footer"],
        }
    except Exception as exc:
        stats["review"] = {"error": f"{exc.__class__.__name__}: {exc}"[:240]}
    return stats


def write_data_file(stats: dict | None = None) -> Path:
    """
    Write Bolt_data.js with current Bolt stats.
    The HTML dashboard loads this file to show live data.

    Returns the path to the written file.
    """
    if stats is None:
        stats = gather_stats()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    js_content = f"""// Auto-generated by Bolt — do not edit manually.
// Updated: {stats["generated_at"]}
// Re-generated on every launch.py startup and after each pipeline run.
window.Bolt_DATA = {json.dumps(stats, indent=2)};
"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(js_content)

    return OUTPUT_FILE


def update_checkup():
    """
    Public entry point — gather stats and write the data file.
    Call this from launch.py and after each pipeline run.
    """
    stats = gather_stats()
    path = write_data_file(stats)

    clips = stats["clips_made"]
    queue = stats["ready_to_post"]
    avg = stats["avg_score"]

    print(f"  ✓  Checkup data updated → {path}")
    print(f"     Clips: {clips}  |  Ready to post: {queue}  |  Avg score: {avg}")
    if HTML_FILE.exists():
        print(f"     Dashboard: {HTML_FILE}")
    return stats


# ── CLI ────────────────────────────────────────────────────────────────────────

def open_dashboard() -> bool:
    """Open App/Bolt_Checkup.html in the default browser. Returns True if opened."""
    if not HTML_FILE.exists():
        print(f"  ✗  Dashboard HTML missing: {HTML_FILE}")
        return False
    try:
        import webbrowser
        # file:// URL so a local double-click / browser open works without a server
        webbrowser.open(HTML_FILE.resolve().as_uri())
        print(f"  ✓  Opened {HTML_FILE}")
        return True
    except Exception as exc:
        print(f"  ✗  Could not open dashboard: {exc}")
        return False


def _main(argv=None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Refresh Bolt checkup data and optionally open the dashboard."
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open App/Bolt_Checkup.html after writing Data/Bolt_data.js",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the stats dict as JSON instead of the human summary",
    )
    parser.add_argument(
        "--path",
        action="store_true",
        help="Print the HTML and data file paths, then exit (no write)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.path:
        print(f"html={HTML_FILE}")
        print(f"data={OUTPUT_FILE}")
        return 0

    print("\n  ⚡️  Bolt Checkup Writer")
    stats = update_checkup()

    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        print("\n  Full stats:")
        for k, v in stats.items():
            if k not in ("api_keys", "top_clip", "phase", "morning", "review"):
                print(f"    {k:20} {v}")
        review = stats.get("review") or {}
        if isinstance(review, dict) and review.get("counts"):
            counts = review["counts"]
            print(
                "\n  Clip review: "
                f"ready {counts.get('ready', 0)} · held {counts.get('held', 0)} · "
                f"posted {counts.get('posted', 0)}"
            )
            print("  Open the board: bolt review")
        morning = stats.get("morning") or {}
        if isinstance(morning, dict) and morning.get("greeting"):
            print(f"\n  {morning['greeting']}")
        print("\n  API keys present:")
        for k, v in stats["api_keys"].items():
            mark = "✓" if v else "✗"
            print(f"    {mark}  {k}")
        if stats["top_clip"]:
            tc = stats["top_clip"]
            print(f"\n  Top clip: {tc['title']} (score: {tc['score']})")
        print(f"\n  Dashboard data: {OUTPUT_FILE}")
        if HTML_FILE.exists():
            print(f"  Dashboard HTML:  {HTML_FILE}")
            print("  Open with: bolt checkup --open")
        else:
            print(f"  ✗  Expected HTML missing: {HTML_FILE}")
        print()

    if args.open:
        ok = open_dashboard()
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
