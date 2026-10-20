#!/usr/bin/env python3
"""
scripts/log_clip_performance.py — Log clip performance for Bolt's learning loop
=================================================================================
After you post a clip by hand (TikTok API is paused) and it has been live for
24h+, log how it did. Bolt uses this to boost the ranking of trigger types
that perform well.

Writes:
  - Data/performance_outcomes.jsonl (one row per clip + platform; re-logging
    the same clip on the same platform UPDATES its row instead of adding a
    duplicate, so the weekly report doesn't double-count)
  - Data/clip_history.json (per-game trigger averages used by Clip_Ranker;
    an update adjusts the totals instead of counting the clip twice)
  - the decision engine (first log only) and the memory index

Usage:
  python3 scripts/log_clip_performance.py --clip 929da53e --views 2011
      # queue id / filename / stem / path → trigger, game, title filled in
  python3 scripts/log_clip_performance.py --trigger ace --views 15000 --likes 1200 --game "Marvel Rivals"
  python3 scripts/log_clip_performance.py --clip Hands --views 2500 --dry-run
  python3 scripts/log_clip_performance.py --list            # recent rows
  python3 scripts/log_clip_performance.py --history         # trigger table for the current game
  python3 scripts/log_clip_performance.py                   # interactive (needs a terminal)
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import REPO_ROOT, DATA_DIR, CLIPS_DIR, LOGS_DIR, CONFIG_FILE  # noqa: E402,F401

PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT
_CORE = REPO_ROOT / "Core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

try:  # optional — append still works without the ranker
    from modules.Clip_Ranker import update_historical_performance  # noqa: E402
except Exception:  # pragma: no cover
    update_historical_performance = None

SOFT = "Log perf unavailable:"

# Canonical post-reorg path (also read by Checkup_Writer + Performance_Sync + weekly).
PERFORMANCE_OUTCOMES_FILE = REPO_ROOT / "Data" / "performance_outcomes.jsonl"
HISTORY_FILE = REPO_ROOT / "Data" / "clip_history.json"
QUEUE_FILE = REPO_ROOT / "Data" / "ready_to_post.json"
MULTI_QUEUE_FILE = REPO_ROOT / "Data" / "multi_platform_queue.json"
MEDIA_DIR = REPO_ROOT / "media"
_LEGACY_OUTCOMES = (
    REPO_ROOT / "Data" / "data" / "performance_outcomes.jsonl",
    REPO_ROOT / "data" / "performance_outcomes.jsonl",
)
OUTCOMES_FILE = PERFORMANCE_OUTCOMES_FILE  # back-compat alias

_VIDEO_EXT = (".mp4", ".mov", ".m4v", ".mkv", ".webm")
_CLIP_NAME_RE = re.compile(
    r"^(?P<stem>.+)_clip(?P<index>\d+)_(?P<trigger>[a-z0-9_]+?)_(?P<timestamp>\d+)"
    r"(?:_(?:tiktok|vertical|shorts|reels|captioned|final))*$"
)
_PLATFORMS = {
    "tiktok": "TikTok", "tt": "TikTok",
    "youtube": "YouTube", "yt": "YouTube", "shorts": "YouTube",
    "youtube_shorts": "YouTube", "youtube-shorts": "YouTube",
    "instagram": "Instagram", "ig": "Instagram", "reels": "Instagram",
    "instagram_reels": "Instagram", "insta": "Instagram",
    "x": "X", "twitter": "X",
    "kick": "Kick", "twitch": "Twitch", "facebook": "Facebook", "fb": "Facebook",
    "threads": "Threads", "bluesky": "Bluesky",
}


class LogPerfError(Exception):
    """Clean, user-facing failure (printed with the soft-fail prefix)."""


# ── small helpers ────────────────────────────────────────────────────────────

def normalize_platform(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "TikTok"
    return _PLATFORMS.get(raw.lower().replace(" ", "_"), raw)


def _parse_count(value, label: str) -> int:
    if value is None or value == "":
        return 0
    s = str(value).strip().lower().replace(",", "").replace("_", "")
    mult = 1
    if s.endswith("k"):
        mult, s = 1_000, s[:-1]
    elif s.endswith("m"):
        mult, s = 1_000_000, s[:-1]
    try:
        n = int(round(float(s) * mult))
    except ValueError:
        raise LogPerfError(f"{label} must be a number (got {value!r})")
    if n < 0:
        raise LogPerfError(f"{label} can't be negative (got {value!r})")
    return n


def _load_config_game() -> str:
    """Current game from Core/config.json (follows Twitch via `bolt game`)."""
    for path in (CONFIG_FILE, REPO_ROOT / "config.json"):
        try:
            if Path(path).is_file():
                game = str(json.loads(Path(path).read_text(encoding="utf-8")).get("game") or "").strip()
                if game and game != "__twitch__":
                    return game
        except Exception:
            continue
    return "Gaming"


def _load_json(path: Path, default):
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _load_history() -> dict:
    data = _load_json(HISTORY_FILE, {})
    return data if isinstance(data, dict) else {}


def _read_rows() -> list:
    rows = []
    if not PERFORMANCE_OUTCOMES_FILE.is_file():
        return rows
    with PERFORMANCE_OUTCOMES_FILE.open(encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                rec = {"_raw": line}  # keep unreadable lines untouched
            rows.append(rec)
    return rows


def _write_in_place(path: Path, text: str) -> None:
    """Write via a verified temp file, then copy bytes into the original so
    the file keeps its inode, Finder tags and other xattrs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        if Path(tmp).read_text(encoding="utf-8") != text:
            raise LogPerfError(f"verify failed writing {path.name}")
        if path.exists():
            shutil.copyfile(tmp, path)
        else:
            os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _rows_to_text(rows: list) -> str:
    out = []
    for r in rows:
        if isinstance(r, dict) and set(r) == {"_raw"}:
            out.append(r["_raw"])
        else:
            out.append(json.dumps(r, ensure_ascii=False))
    return ("\n".join(out) + "\n") if out else ""


# ── clip lookup ──────────────────────────────────────────────────────────────

def _queue_entries() -> list:
    entries = []
    q = _load_json(QUEUE_FILE, {})
    clips = q.get("clips") if isinstance(q, dict) else q
    for c in clips or []:
        if isinstance(c, dict):
            entries.append({
                "queue_id": str(c.get("id") or ""),
                "clip_path": str(c.get("clip_path") or ""),
                "title": str(c.get("title") or ""),
                "game": str(c.get("game") or ""),
                "trigger": str(c.get("trigger") or ""),
                "status": str(c.get("status") or ""),
            })
    mq = _load_json(MULTI_QUEUE_FILE, {})
    for it in (mq.get("items") if isinstance(mq, dict) else []) or []:
        if isinstance(it, dict):
            entries.append({
                "queue_id": str(it.get("queue_id") or ""),
                "clip_path": str(it.get("original_clip_path") or ""),
                "title": str(it.get("clip_name") or ""),
                "game": str(it.get("game") or ""),
                "trigger": "",
                "status": "",
            })
    return entries


def _media_files():
    for sub in ("clips", "vertical_clips", "output"):
        base = MEDIA_DIR / sub
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.suffix.lower() in _VIDEO_EXT and not p.name.startswith("._"):
                yield p


def _name_keys(value: str) -> set:
    p = Path(str(value or "").strip())
    keys = {p.name.lower(), p.stem.lower()}
    return {k for k in keys if k}


def _sidecar_for(clip_path: str) -> dict:
    """Clip_Generator writes <stem>.json next to each clip (trigger, game, score).
    Vertical copies (`…_tiktok.mp4`) point back at the original clip's sidecar."""
    if not clip_path:
        return {}
    p = Path(clip_path)
    stems = [p.stem]
    base = re.sub(r"(_(tiktok|vertical|shorts|reels|captioned|final))+$", "", p.stem)
    if base != p.stem:
        stems.append(base)
    dirs = [p.parent, CLIPS_DIR]
    for d in dirs:
        for s in stems:
            sc = Path(d) / f"{s}.json"
            data = _load_json(sc, None)
            if isinstance(data, dict):
                return data
    return {}


def _trigger_from_name(clip_path: str) -> str:
    m = _CLIP_NAME_RE.match(Path(str(clip_path or "")).stem)
    return m.group("trigger") if m else ""


def resolve_clip(query: str) -> dict:
    """Turn a queue id / filename / stem / path into what we know about the clip.

    Returns {clip_path, queue_id, title, game, trigger, matched_by}. Raises
    LogPerfError when the query matches more than one different clip.
    """
    q = str(query or "").strip()
    info = {"clip_path": "", "queue_id": "", "title": "", "game": "",
            "trigger": "", "matched_by": "", "query": q}
    if not q:
        return info

    entries = _queue_entries()
    ql = q.lower()
    hits = []
    if len(q) >= 4 and re.fullmatch(r"[0-9a-fA-F]+", q):
        hits = [e for e in entries if e["queue_id"].lower().startswith(ql)]
        if hits:
            info["matched_by"] = "queue id"
    if not hits:
        keys = _name_keys(q)
        hits = [e for e in entries if keys & _name_keys(e["clip_path"])
                or (e["title"] and e["title"].strip().lower() == ql)]
        if hits:
            info["matched_by"] = "queue"
    # Collapse entries for the same clip (ready_to_post + multi-platform queue
    # share a queue id; the richer entry wins, blanks are filled from the other).
    uniq = {}
    for e in hits:
        key = e["queue_id"] or e["clip_path"]
        if key in uniq:
            for k, v in e.items():
                if v and not uniq[key].get(k):
                    uniq[key][k] = v
        else:
            uniq[key] = dict(e)
    hits = list(uniq.values())
    if len(hits) > 1:
        ids = ", ".join(f"{e['queue_id']} ({Path(e['clip_path']).name})" for e in hits[:6])
        raise LogPerfError(f"'{q}' matches more than one queued clip: {ids}. Use the queue id.")

    if hits:
        e = hits[0]
        info.update({k: e[k] for k in ("clip_path", "queue_id", "title", "game", "trigger")})
    else:
        p = Path(q).expanduser()
        if p.is_file():
            info["clip_path"], info["matched_by"] = str(p.resolve()), "path"
        else:
            keys = _name_keys(q)
            files = [f for f in _media_files() if keys & _name_keys(str(f))]
            if len({str(f) for f in files}) > 1:
                names = ", ".join(str(f.relative_to(REPO_ROOT)) for f in files[:6])
                raise LogPerfError(f"'{q}' matches more than one file: {names}. Use the full path.")
            if files:
                info["clip_path"], info["matched_by"] = str(files[0]), "media"
            else:
                info["clip_path"], info["matched_by"] = q, ""  # unknown — keep as typed

    side = _sidecar_for(info["clip_path"])
    if not info["trigger"]:
        info["trigger"] = str(side.get("trigger") or "") or _trigger_from_name(info["clip_path"])
    if not info["game"] and side.get("game"):
        info["game"] = str(side["game"])
    if not info["title"] and info["clip_path"]:
        info["title"] = Path(info["clip_path"]).stem
    return info


# ── history (Clip_Ranker) ────────────────────────────────────────────────────

def _history_adjust(game: str, trigger: str, prev_views: int, prev_likes: int,
                    views: int, likes: int) -> None:
    """Re-log of the same clip: move totals by the difference and replace the
    matching observation instead of counting the clip twice."""
    history = _load_history()
    entry = history.get(game, {}).get(trigger)
    if not isinstance(entry, dict):
        if update_historical_performance:
            update_historical_performance(game, trigger, views, likes)
        return
    entry["total_views"] = max(0, int(entry.get("total_views", 0)) + views - prev_views)
    entry["total_likes"] = max(0, int(entry.get("total_likes", 0)) + likes - prev_likes)
    entry["avg_views"] = entry["total_views"] // max(1, int(entry.get("total_clips", 1) or 1))
    obs = entry.setdefault("observations", [])
    for o in reversed(obs):
        if int(o.get("views", -1)) == prev_views and int(o.get("likes", -1)) == prev_likes:
            o["views"], o["likes"] = views, likes
            o["at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
            break
    else:
        obs.append({"at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
                    "views": views, "likes": likes})
    _write_in_place(HISTORY_FILE, json.dumps(history, indent=2))


# ── core ─────────────────────────────────────────────────────────────────────

def _like_rate(views: int, likes: int) -> float:
    if views <= 0:
        return 0.0
    return round(likes / views, 4)


def _is_success(views: int, likes: int) -> bool:
    """Successful = 1000+ views OR a >=5% like rate (skipped at zero views)."""
    if views >= 1000:
        return True
    if views > 0 and likes > 0:
        return (likes / views) >= 0.05
    return False


def _find_existing(rows: list, platform: str, clip_path: str, queue_id: str):
    """Index of an earlier manual row for the same clip + platform (API rows
    from `bolt stats` are left alone — that sync owns them)."""
    if not (clip_path or queue_id):
        return None
    for i in range(len(rows) - 1, -1, -1):
        r = rows[i]
        if not isinstance(r, dict) or r.get("source") == "youtube_api":
            continue
        if normalize_platform(r.get("platform")) != platform:
            continue
        if queue_id and str(r.get("queue_id") or "") == queue_id:
            return i
        if clip_path and str(r.get("clip_path") or "") == clip_path:
            return i
    return None


def _record_learning_outcome(
    game: str,
    trigger: str,
    views: int,
    likes: int,
    clip_path: str = "",
    platform: str = "",
    note: str = "",
    queue_id: str = "",
    title: str = "",
    game_source: str = "",
    dry_run: bool = False,
) -> dict:
    """Log (or update) one clip's performance and feed the learning loop."""
    views, likes = int(views), int(likes)
    platform = normalize_platform(platform)
    like_rate = round((likes / views) * 100, 2) if views > 0 else 0.0
    success = _is_success(views, likes)
    now = datetime.now().isoformat()

    entry = {
        "timestamp": now,
        "game": game,
        "trigger": trigger,
        "views": views,
        "likes": likes,
        "like_rate": like_rate,
        "success": success,
        "clip_path": clip_path,
        "platform": platform,
        "note": note,
        "source": "manual",
    }
    if queue_id:
        entry["queue_id"] = queue_id
    if title:
        entry["title"] = title
    if game_source:
        entry["game_source"] = game_source

    rows = _read_rows()
    idx = _find_existing(rows, platform, clip_path, queue_id)
    prev = rows[idx] if idx is not None else None
    if prev is not None:
        # Re-log: keep what the first log knew unless told otherwise.
        if game_source in ("", "config") and prev.get("game") not in (None, "", "Unknown"):
            game = entry["game"] = str(prev["game"])
            entry["game_source"] = "previous log"
        if trigger == "unknown" and prev.get("trigger") not in (None, "", "unknown"):
            trigger = entry["trigger"] = str(prev["trigger"])
        entry["first_logged_at"] = prev.get("first_logged_at") or prev.get("timestamp") or now
        if not note and prev.get("note"):
            entry["note"] = prev["note"]
        entry["previous_views"] = int(prev.get("views") or 0)
    else:
        entry["first_logged_at"] = now
    entry["action"] = "updated" if prev is not None else "logged"
    if dry_run:
        entry["dry_run"] = True
        return entry

    saved = {k: v for k, v in entry.items() if k not in ("action", "dry_run", "previous_views")}
    if prev is not None:
        rows[idx] = saved
        _write_in_place(PERFORMANCE_OUTCOMES_FILE, _rows_to_text(rows))
    else:
        PERFORMANCE_OUTCOMES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PERFORMANCE_OUTCOMES_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(saved, ensure_ascii=False) + "\n")

    # Clip_Ranker averages.
    try:
        same_bucket = prev is not None and prev.get("game") == game and prev.get("trigger") == trigger
        if same_bucket:
            _history_adjust(game, trigger, int(prev.get("views") or 0),
                            int(prev.get("likes") or 0), views, likes)
        elif update_historical_performance:
            update_historical_performance(game, trigger, views, likes)
    except Exception as exc:  # pragma: no cover - history is best-effort
        print(f"[log_clip_performance] clip history update skipped: {exc}")

    # Decision engine: count each clip once.
    if prev is None:
        try:
            from modules.Think_Learn_Decide import ThinkLearnDecideEngine

            engine = ThinkLearnDecideEngine({})
            engine.learn_from_outcome(
                "clip_performance",
                success,
                {"game": game, "trigger": trigger, "views": views, "likes": likes,
                 "like_rate": like_rate, "platform": platform, "note": note},
            )
        except Exception as exc:  # pragma: no cover - learning is best-effort
            print(f"[log_clip_performance] learning loop skipped: {exc}")

    try:
        from modules.Memory_Index import refresh_memory_index

        refresh_memory_index()
    except Exception as exc:  # pragma: no cover - index refresh is best-effort
        print(f"[log_clip_performance] memory refresh skipped: {exc}")

    # Sanity: the row must be on disk now.
    if not any(isinstance(r, dict) and r.get("timestamp") == now for r in _read_rows()):
        raise LogPerfError("row was not saved to Data/performance_outcomes.jsonl")
    return entry


def log_performance(game: str, trigger: str, views: int, likes: int) -> dict:
    """Backwards-compatible thin wrapper."""
    return _record_learning_outcome(game=game, trigger=trigger, views=views, likes=likes)


def log_clip(clip: str = "", views=None, likes=0, trigger: str = "", game: str = "",
             platform: str = "TikTok", note: str = "", dry_run: bool = False) -> dict:
    """High-level entry: resolve the clip, fill trigger/game, validate, log."""
    views_n = _parse_count(views, "views")
    likes_n = _parse_count(likes, "likes")
    info = resolve_clip(clip) if clip else {}
    trig = (trigger or info.get("trigger") or "").strip().lower()
    if not trig and clip and info.get("matched_by"):
        trig = "unknown"
    if not trig:
        if clip:
            raise LogPerfError(
                f"couldn't find '{clip}' in the queue or media folders. Check the name "
                "(bolt queue shows ids), or add --trigger (kill, ace, audio_spike, manual…) to log it anyway."
            )
        raise LogPerfError("need --clip or --trigger (e.g. --clip 929da53e or --trigger ace)")
    if game:
        g, src = game, "user"
    elif info.get("game"):
        g, src = info["game"], "clip"
    else:
        g, src = _load_config_game(), "config"
    if likes_n > views_n and views_n > 0:
        print(f"  note: likes ({likes_n:,}) are higher than views ({views_n:,}) — double-check.")
    entry = _record_learning_outcome(
        game=g, trigger=trig, views=views_n, likes=likes_n,
        clip_path=info.get("clip_path", "") if clip else "",
        platform=platform, note=note,
        queue_id=info.get("queue_id", ""), title=info.get("title", ""),
        game_source=src, dry_run=dry_run,
    )
    entry["matched_by"] = info.get("matched_by", "")
    return entry


# ── views ────────────────────────────────────────────────────────────────────

def show_current(game: str):
    history = _load_history()
    game_data = history.get(game, {})
    if not game_data:
        print(f"\n  No history yet for '{game}'. Log your first clip!\n")
        return
    print(f"\n  Performance history for: {game}")
    print(f"  {'-' * 60}")
    print(f"  {'Trigger':<14} {'Clips':>6} {'Total Views':>12} {'Avg Views':>10} {'Boost':>7}")
    print(f"  {'-' * 60}")
    for trig, data in sorted(game_data.items(), key=lambda kv: kv[1].get("avg_views", 0), reverse=True):
        clips = data.get("total_clips", 0)
        views = data.get("total_views", 0)
        avg = data.get("avg_views", 0)
        boost = min(15.0, (avg / 10_000) * 15.0)
        print(f"  {trig:<14} {clips:>6} {views:>12,} {avg:>10,} {boost:>6.1f}p")
    print()


def list_recent(limit: int = 20, manual_only: bool = False):
    rows = [r for r in _read_rows() if isinstance(r, dict) and "_raw" not in r]
    if manual_only:
        rows = [r for r in rows if r.get("source") != "youtube_api"]
    if not rows:
        print("No performance data logged yet.")
        return
    rows.sort(key=lambda r: str(r.get("timestamp") or ""))
    print(f"\nLast {min(limit, len(rows))} logged performances (newest first):\n")
    print(f"{'Date':11} {'Platform':9} {'Game':20} {'Trigger':12} {'Views':>9} {'Likes':>7}  Clip")
    print("-" * 96)
    for e in reversed(rows[-limit:]):
        title = str(e.get("title") or Path(str(e.get("clip_path") or "")).stem or "")
        title = " ".join(title.split())[:30]
        mark = "✓" if e.get("success") else " "
        print(
            f"{str(e.get('timestamp') or '')[:10]:11} {str(e.get('platform') or '?')[:9]:9} "
            f"{str(e.get('game') or 'Unknown')[:20]:20} {str(e.get('trigger') or '?')[:12]:12} "
            f"{int(e.get('views') or 0):>9,} {int(e.get('likes') or 0):>7,} {mark} {title}"
        )
    print()


def _print_entry(entry: dict) -> None:
    verb = {"logged": "Logged", "updated": "Updated"}.get(entry.get("action"), "Logged")
    if entry.get("dry_run"):
        verb = f"Dry run (nothing saved) — would be {entry.get('action', 'logged')}"
    clip = entry.get("title") or Path(entry.get("clip_path") or "").name
    print(
        f"\n✓ {verb}: {entry['trigger']} in {entry['game']} on {entry['platform']} — "
        f"{entry['views']:,} views, {entry['likes']:,} likes "
        f"({'success' if entry['success'] else 'not a hit yet'})"
    )
    if clip:
        extra = f" · queue {entry['queue_id']}" if entry.get("queue_id") else ""
        print(f"  clip: {clip}{extra}")
    if entry.get("action") == "updated":
        print(f"  was {entry.get('previous_views', 0):,} views — row updated, not duplicated")
    if entry.get("trigger") == "unknown":
        print("  trigger unknown — add --trigger kill/ace/audio_spike/… next time so the ranker can learn from it")
    print(f"  game from: {entry.get('game_source') or 'config'}\n")


def interactive(game: str, platform: str = "TikTok") -> int:
    if not sys.stdin.isatty():
        raise LogPerfError(
            "interactive mode needs a terminal. Use: bolt log-perf run --clip <queue id|name> --views N"
        )
    print("\n=== Bolt Clip Performance Logger ===  (Ctrl+C to cancel)\n")
    clip = input("  Clip (queue id, filename or path; enter to skip): ").strip()
    info = resolve_clip(clip) if clip else {}
    if info.get("clip_path"):
        print(f"  → {info.get('title') or info['clip_path']}  "
              f"trigger={info.get('trigger') or '?'} game={info.get('game') or game}")
    trigger = info.get("trigger") or ""
    if not trigger:
        print("  Trigger types: kill, multi_kill, ace, audio_spike, chat_hype, raid, sub, highlight, manual")
        trigger = input("  Trigger type: ").strip().lower()
    views = input("  Views (after 24h+): ").strip()
    likes = input("  Likes (enter to skip): ").strip()
    plat = input(f"  Platform [{platform}]: ").strip() or platform
    note = input("  Note — why it worked/flopped (optional): ").strip()
    entry = log_clip(clip=clip, views=views, likes=likes or 0, trigger=trigger,
                     game="" if info.get("game") else game, platform=plat, note=note)
    _print_entry(entry)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="bolt log-perf run",
        description="Log a posted clip's performance so Bolt learns what works.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--clip", default="", help="Queue id, filename, stem or path (fills trigger/game/title)")
    p.add_argument("--trigger", default="", help="Trigger type (kill, ace, audio_spike, …); inferred from --clip")
    p.add_argument("--views", default=None, help="Views after 24h+ (2500, 2,500 or 2.5k)")
    p.add_argument("--likes", default="0", help="Likes (optional)")
    p.add_argument("--game", default=None, help="Override game (default: clip's game, else Core/config.json)")
    p.add_argument("--platform", default="TikTok", help="TikTok (default), YouTube, Instagram, X, Kick, …")
    p.add_argument("--note", default="", help="Why it worked/flopped")
    p.add_argument("--dry-run", action="store_true", help="Show what would be logged; save nothing")
    p.add_argument("--list", action="store_true", help="Show recent logged rows and exit")
    p.add_argument("--manual", action="store_true", help="With --list: only manual rows (not YouTube sync)")
    p.add_argument("--limit", type=int, default=20, help="With --list: how many rows")
    p.add_argument("--history", action="store_true", help="Show the trigger table Clip_Ranker uses for the game")
    p.add_argument("--json", action="store_true", help="JSON output for a log")
    args = p.parse_args(argv)

    try:
        if args.list:
            list_recent(limit=max(1, args.limit), manual_only=args.manual)
            return 0
        if args.history:
            show_current(args.game or _load_config_game())
            return 0
        if args.views is None:
            if args.clip or args.trigger:
                raise LogPerfError("missing --views (e.g. --views 2500)")
            return interactive(args.game or _load_config_game(), normalize_platform(args.platform))
        entry = log_clip(clip=args.clip, views=args.views, likes=args.likes,
                         trigger=args.trigger, game=args.game or "",
                         platform=args.platform, note=args.note, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(entry, indent=2, ensure_ascii=False))
        else:
            _print_entry(entry)
        return 0
    except LogPerfError as exc:
        print(f"{SOFT} {exc}")
        return 2
    except (KeyboardInterrupt, EOFError):
        print("\n  Cancelled — nothing logged.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
