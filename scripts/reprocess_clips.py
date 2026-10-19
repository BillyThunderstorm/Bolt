#!/usr/bin/env python3
"""
reprocess_clips.py — Rebuild 9:16 vertical versions of existing clips and
add them to the manual multi-platform post queue.

Usage (prefer the CLI: ``bolt reprocess run``):
  python3 scripts/reprocess_clips.py                 → every clip missing a vertical
  python3 scripts/reprocess_clips.py --dry-run       → show the plan, write nothing
  python3 scripts/reprocess_clips.py --force         → rebuild verticals that exist
  python3 scripts/reprocess_clips.py NAME [NAME...]  → only clips whose name contains NAME
  python3 scripts/reprocess_clips.py --limit N       → at most N clips this run

What it does:
  media/clips/*.mp4 → Clip_Factory.format_for_tiktok (config ``tiktok_style``)
  → media/vertical_clips/<stem>_tiktok.mp4, verified as a real portrait video
  → Data/multi_platform_queue.json, MERGED (other queue items are kept; a clip
  that is already queued is not added twice). Plans come from Multi_Publisher
  (same TikTok / Shorts / Reels / Kick format and times as ``bolt multi``).

Never moves or deletes source clips. Never uploads anywhere (TikTok API is
paused; every platform entry is ``manual_upload_ready``).
Exit code: 0 ok (or nothing to do), 1 setup error, 2 some clips failed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
_CORE = REPO_ROOT / "Core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))


def _resolve_dir(modern: Path, legacy: Path) -> Path:
    if modern.is_dir():
        return modern
    if legacy.is_dir():
        return legacy
    return modern


CLIPS_DIR = _resolve_dir(REPO_ROOT / "media" / "clips", REPO_ROOT / "clips")
VERTICAL_DIR = _resolve_dir(
    REPO_ROOT / "media" / "vertical_clips", REPO_ROOT / "vertical_clips"
)
QUEUE_FILE = REPO_ROOT / "Data" / "multi_platform_queue.json"
BACKUP_SUFFIX = ".bak"
QUEUE_ID_PREFIX = "reprocess-"
MIN_VERTICAL_BYTES = 10 * 1024

format_for_tiktok = None  # type: ignore
load_config = None  # type: ignore
_IMPORT_ERROR = ""
try:
    from modules.Clip_Factory import format_for_tiktok as _fft
    from modules.Config_Loader import load_config as _lc

    format_for_tiktok = _fft
    load_config = _lc
except Exception as exc:  # soft import — clear message, no traceback dump
    _IMPORT_ERROR = str(exc)

try:
    from modules.FFmpeg_Bin import probe_video as _probe_video
except Exception:  # pragma: no cover - FFmpeg_Bin is stdlib-only
    _probe_video = None  # type: ignore

try:
    from modules.Multi_Publisher import build_platform_plan as _build_plan
except Exception:
    _build_plan = None  # type: ignore

try:  # Finder purple = media (William's colour key); soft, macOS only
    from modules.Bolt_Wrap import apply_finder_tag as _tag
except Exception:
    _tag = None  # type: ignore

DEFAULT_STYLE = "letterbox"
DEFAULT_HASHTAGS = ["gaming", "clips", "viral", "fyp"]

# Fallback only (Multi_Publisher import failed).
_FALLBACK_PLATFORMS = [
    ("tiktok", "TikTok", 60),
    ("youtube_shorts", "YouTube Shorts", 60),
    ("instagram_reels", "Instagram Reels", 90),
    ("kick", "Kick", None),
]


# ---------------------------------------------------------------- helpers


def load_settings() -> Dict[str, Any]:
    style, hashtags = DEFAULT_STYLE, list(DEFAULT_HASHTAGS)
    if load_config is not None:
        try:
            cfg = load_config() or {}
            style = cfg.get("tiktok_style") or style
            hashtags = cfg.get("hashtags") or hashtags
        except Exception as exc:
            print(f"Warning: config load failed ({exc}); using defaults", file=sys.stderr)
    return {"style": style, "hashtags": list(hashtags)}


def get_clips(clips_dir: Path) -> List[Path]:
    if not clips_dir.is_dir():
        return []
    return sorted(p for p in clips_dir.glob("*.mp4") if p.is_file() and not p.name.startswith("."))


def vertical_path_for(clip: Path, vertical_dir: Path) -> Path:
    return vertical_dir / f"{clip.stem}_tiktok.mp4"


def is_good_vertical(path: Path, source: Optional[Path] = None) -> tuple[bool, str]:
    """A usable vertical: exists, not the source, non-trivial size, portrait."""
    try:
        if not path.is_file():
            return False, "missing"
        if source is not None and path.resolve() == source.resolve():
            return False, "formatter returned the original horizontal clip"
        size = path.stat().st_size
        if size < MIN_VERTICAL_BYTES:
            return False, f"output too small ({size} bytes)"
    except OSError as exc:
        return False, f"cannot read output ({exc})"
    if _probe_video is not None:
        info = _probe_video(str(path))
        if not info:
            return False, "output is not a readable video"
        w, h = info.get("width") or 0, info.get("height") or 0
        if not (h > w > 0):
            return False, f"output is {w}x{h}, not vertical"
    return True, ""


def clip_title(clip: Path) -> str:
    """Readable title: '<Game> highlight (clip 01)' from the ranker sidecar."""
    game = ""
    sidecar = clip.with_suffix(".json")
    if sidecar.is_file():
        try:
            game = str(json.loads(sidecar.read_text(encoding="utf-8")).get("game") or "").strip()
        except Exception:
            game = ""
    m = re.search(r"clip(\d+)", clip.stem)
    num = f" (clip {m.group(1)})" if m else ""
    if game:
        return f"{game} highlight{num}"
    base = re.sub(r"_audio_spike_\d+$", "", clip.stem).replace("_", " ").strip()
    return f"Stream highlight{num}" if not base else f"{base} highlight"


def build_platforms(vertical: Path, title: str, hashtags: List[str]) -> List[dict]:
    if _build_plan is not None:
        try:
            return _build_plan(str(vertical), title, hashtags=hashtags)
        except Exception as exc:
            print(f"  (Multi_Publisher plan failed: {exc}; using basic plan)", file=sys.stderr)
    tags = " ".join(f"#{h.lstrip('#')}" for h in hashtags)
    out = []
    for key, label, max_s in _FALLBACK_PLATFORMS:
        entry = {
            "platform": key,
            "label": label,
            "status": "manual_upload_ready",
            "clip_path": str(vertical),
            "title": title,
            "caption": f"{title}\n\n{tags}".strip(),
            "instructions": f"Upload manually to {label}.",
            "aspect_ratio": "9:16",
        }
        if max_s:
            entry["max_duration_seconds"] = max_s
        out.append(entry)
    return out


def queue_id_for(clip: Path) -> str:
    return f"{QUEUE_ID_PREFIX}{clip.stem}"


def load_queue(queue_file: Path) -> Dict[str, Any]:
    if not queue_file.is_file():
        return {"items": []}
    try:
        data = json.loads(queue_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"queue file is not valid JSON ({exc}); left untouched") from exc
    if isinstance(data, list):
        data = {"items": data}
    if not isinstance(data, dict):
        raise RuntimeError("queue file has an unexpected shape; left untouched")
    data.setdefault("items", [])
    return data


def _item_paths(item: dict) -> set:
    paths = set()
    for p in item.get("platforms") or []:
        cp = p.get("clip_path")
        if cp:
            paths.add(str(cp))
    return paths


def already_queued_elsewhere(items: Iterable[dict], vertical: Path, qid: str) -> bool:
    target = str(vertical)
    for item in items:
        if item.get("queue_id") == qid:
            continue
        if target in _item_paths(item):
            return True
    return False


def save_queue_atomic(queue_file: Path, data: Dict[str, Any]) -> None:
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".mpq_", suffix=".json", dir=str(queue_file.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, queue_file)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# ---------------------------------------------------------------- run


def run(
    *,
    clips_dir: Path = CLIPS_DIR,
    vertical_dir: Path = VERTICAL_DIR,
    queue_file: Path = QUEUE_FILE,
    dry_run: bool = False,
    force: bool = False,
    only: Optional[List[str]] = None,
    limit: Optional[int] = None,
    formatter=None,
    settings: Optional[Dict[str, Any]] = None,
    tag: bool = True,
) -> Dict[str, Any]:
    """Rebuild verticals + merge queue entries. Returns a summary dict."""
    fmt = formatter or format_for_tiktok
    settings = settings or load_settings()
    summary: Dict[str, Any] = {
        "dry_run": dry_run,
        "clips_dir": str(clips_dir),
        "vertical_dir": str(vertical_dir),
        "queue_file": str(queue_file),
        "style": settings["style"],
        "processed": [],
        "reused": [],
        "failed": [],
        "queued": [],
        "already_queued": [],
        "error": "",
    }

    clips = get_clips(clips_dir)
    if only:
        needles = [n.lower() for n in only]
        clips = [c for c in clips if any(n in c.name.lower() for n in needles)]
    summary["clips_found"] = len(clips)
    if not clips:
        summary["error"] = (
            f"no matching mp4 clips in {clips_dir}" if only else f"no mp4 clips in {clips_dir}"
        )
        return summary

    plan = []
    for clip in clips:
        vpath = vertical_path_for(clip, vertical_dir)
        good, _why = is_good_vertical(vpath, clip)
        plan.append((clip, vpath, "reuse" if good and not force else "build"))
    builds = [p for p in plan if p[2] == "build"]
    if limit is not None and limit >= 0 and len(builds) > limit:
        keep = {id(p) for p in builds[:limit]}
        plan = [p for p in plan if p[2] == "reuse" or id(p) in keep]
    summary["plan"] = [{"clip": c.name, "action": a} for c, _v, a in plan]

    if dry_run:
        return summary
    if fmt is None:
        summary["error"] = f"Clip_Factory.format_for_tiktok unavailable ({_IMPORT_ERROR})"
        return summary

    try:
        queue = load_queue(queue_file)
    except RuntimeError as exc:
        summary["error"] = str(exc)
        return summary

    vertical_dir.mkdir(parents=True, exist_ok=True)
    ready: List[tuple] = []
    for i, (clip, vpath, action) in enumerate(plan, 1):
        if action == "reuse":
            print(f"[{i}/{len(plan)}] reuse  {vpath.name}", flush=True)
            summary["reused"].append(vpath.name)
            ready.append((clip, vpath))
            continue
        print(f"[{i}/{len(plan)}] build  {clip.name} → {vpath.name}", flush=True)
        try:
            result = fmt(str(clip), output_dir=str(vertical_dir), style=settings["style"])
        except Exception as exc:
            result = None
            why = f"formatter error: {exc}"
        else:
            out = Path(result) if result else vpath
            good, why = is_good_vertical(out, clip)
            if good:
                vpath = out
        if result and good:
            if _tag is not None and tag:
                try:
                    _tag(vpath, "Purple")
                except Exception:
                    pass
            mb = vpath.stat().st_size / (1024 * 1024)
            print(f"  → ok ({mb:.1f} MB)", flush=True)
            summary["processed"].append(vpath.name)
            ready.append((clip, vpath))
        else:
            print(f"  → FAILED: {why}", flush=True)
            summary["failed"].append({"clip": clip.name, "reason": why})

    items = list(queue.get("items") or [])
    rebuilt = set(summary["processed"])
    changed = False
    for clip, vpath in ready:
        qid = queue_id_for(clip)
        if already_queued_elsewhere(items, vpath, qid):
            summary["already_queued"].append(clip.name)
            continue
        own = any(it.get("queue_id") == qid for it in items)
        if own and vpath.name not in rebuilt:
            # Same vertical, already planned — keep its schedule as is.
            summary["already_queued"].append(clip.name)
            continue
        entry = {
            "queue_id": qid,
            "created_at": datetime.now().isoformat(),
            "source": "bolt reprocess",
            "clip_name": clip.stem,
            "original_clip_path": str(clip),
            "platforms": build_platforms(vpath, clip_title(clip), settings["hashtags"]),
        }
        items = [it for it in items if it.get("queue_id") != qid]
        items.append(entry)
        summary["queued"].append(qid)
        changed = True

    if changed:
        if queue_file.is_file():
            shutil.copy2(queue_file, queue_file.with_name(queue_file.name + BACKUP_SUFFIX))
        queue["items"] = items
        save_queue_atomic(queue_file, queue)
    summary["queue_total"] = len(items)
    return summary


def _print_summary(s: Dict[str, Any]) -> None:
    print()
    if s.get("dry_run"):
        print(f"Dry run — {s.get('clips_found', 0)} clip(s), style={s['style']}; nothing written")
        for row in s.get("plan") or []:
            print(f"  {row['action']:<6} {row['clip']}")
        return
    print("=" * 60)
    print(f"Vertical rebuild (style={s['style']})")
    print(f"  built:          {len(s['processed'])}")
    print(f"  reused:         {len(s['reused'])}")
    print(f"  failed:         {len(s['failed'])}")
    for f in s["failed"]:
        print(f"    - {f['clip']}: {f['reason']}")
    print(f"  queued/updated: {len(s['queued'])}")
    if s["already_queued"]:
        print(f"  already queued: {len(s['already_queued'])} (left as is)")
    print(f"  verticals:      {s['vertical_dir']}")
    print(f"  queue:          {s['queue_file']} ({s.get('queue_total', '?')} items, merged)")
    print("  Manual upload only — nothing was posted (TikTok API paused).")
    print("=" * 60)


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in args or "-n" in args
    force = "--force" in args
    as_json = "--json" in args
    limit: Optional[int] = None
    only: List[str] = []
    skip_next = False
    for i, a in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if a == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                print(f"Error: --limit needs a number, got {args[i + 1]!r}", file=sys.stderr)
                return 1
            skip_next = True
        elif a.startswith("--limit="):
            try:
                limit = int(a.split("=", 1)[1])
            except ValueError:
                print(f"Error: bad {a}", file=sys.stderr)
                return 1
        elif not a.startswith("-"):
            only.append(a)

    if _IMPORT_ERROR and not dry_run:
        print(
            f"Error: Core imports failed ({_IMPORT_ERROR}). Run via: bolt reprocess run",
            file=sys.stderr,
        )
        return 1

    summary = run(dry_run=dry_run, force=force, only=only or None, limit=limit)
    if as_json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        if summary.get("error"):
            print(f"Error: {summary['error']}", file=sys.stderr)
        else:
            _print_summary(summary)
    if summary.get("error"):
        return 0 if summary["error"].startswith("no ") else 1
    return 2 if summary.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
