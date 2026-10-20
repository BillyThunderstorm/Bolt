#!/usr/bin/env python3
"""
Filter the existing clip backlog by score.

Scores come from real clip data — sidecar written at cut time, original
detector scores recovered from daily logs, or a fresh audio analysis.
Never uses a hardcoded highlight/50 stand-in.

Moves low-scoring clips (mp4 + every same-name companion: sidecar .json,
thumbnail .jpg, .srt …) into media/clips/_low_score/ and logs every move to
media/clips/_low_score/_moves.jsonl so ``--restore`` can put them back.

Safety rails:
  * threshold comes from the game profile (Game_Config: per-game override >
    Core/config.json > built-in > default) unless --threshold is given
  * clips still waiting in the post queue (Data/ready_to_post.json /
    Data/multi_platform_queue.json) are kept unless --include-queued
  * clips that could not be scored at all (score source "none") are kept
  * a name that already exists in the destination is never overwritten
  * --dry-run moves nothing
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Post-reorg path bootstrap. Adds the script's own dir to sys.path so
# `from _paths import …` works in both direct invocation and `from
# scripts import X` (test) contexts. The helper itself adds Core/ and
# 3rd_Party/llm/ to sys.path so `from modules import Y` resolves, and
# chdirs to the repo root for any CWD-relative paths the script uses.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from _paths import REPO_ROOT, CLIPS_DIR  # noqa: E402

# Backward-compatible aliases for code that uses `ROOT` / `PROJECT_ROOT`.
PROJECT_ROOT = REPO_ROOT
ROOT = REPO_ROOT

from modules import Clip_Ranker as _ranker  # noqa: E402
from modules.Clip_Ranker import (  # noqa: E402
    DISCARD_BELOW,
    clip_from_path,
    load_logged_highlight_scores,
)
from modules.Config_Loader import load_config  # noqa: E402

LOW_NAME = "_low_score"
MOVES_LOG = "_moves.jsonl"
QUEUE_FILES = (
    REPO_ROOT / "Data" / "ready_to_post.json",
    REPO_ROOT / "Data" / "multi_platform_queue.json",
)
DONE_STATUSES = {
    "posted", "published", "uploaded", "rejected", "skipped", "removed",
    "deleted", "expired", "done", "cancelled", "canceled",
    "missing_file",
}


# ── helpers ──────────────────────────────────────────────────────────────────

def resolve_threshold(game, override=None, config=None):
    """Return (threshold, source). Never raises."""
    if override is not None:
        return float(override), "--threshold"
    config = config if isinstance(config, dict) else {}
    try:
        from modules.Game_Config import effective_config

        eff = effective_config(game, config)
        value = (eff.get("values") or {}).get("min_clip_score")
        if value is not None:
            src = (eff.get("sources") or {}).get("min_clip_score", "default")
            return float(value), f"game profile ({src})"
    except Exception:
        pass
    if config.get("min_clip_score") is not None:
        try:
            return float(config["min_clip_score"]), "config"
        except (TypeError, ValueError):
            pass
    return float(DISCARD_BELOW), "default"


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _status_done(value) -> bool:
    return str(value or "").strip().lower() in DONE_STATUSES


def active_queue_strings(queue_files=QUEUE_FILES):
    """All strings from post-queue entries that are not posted/rejected yet."""
    out = []
    for qf in queue_files:
        try:
            data = json.loads(Path(qf).read_text(encoding="utf-8"))
        except Exception:
            continue
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            for key in ("clips", "items", "queue"):
                if isinstance(data.get(key), list):
                    items.extend(data[key])
        for item in items:
            if not isinstance(item, dict):
                continue
            if _status_done(item.get("status")):
                continue
            plats = item.get("platforms")
            if isinstance(plats, list) and plats and all(
                isinstance(p, dict) and _status_done(p.get("status")) for p in plats
            ):
                continue
            out.extend(_strings(item))
    return out


def is_queued(stem: str, queue_strings) -> bool:
    pat = re.compile(re.escape(stem) + r"(?![0-9A-Za-z])")
    return any(pat.search(s) for s in queue_strings)


def companions(folder: Path, stem: str):
    """The clip plus every file in ``folder`` sharing its exact stem."""
    try:
        return sorted(
            p for p in folder.iterdir()
            if p.is_file() and (p.stem == stem or p.name.startswith(stem + "."))
        )
    except FileNotFoundError:
        return []


def _log_move(low_dir: Path, record: dict) -> None:
    try:
        low_dir.mkdir(parents=True, exist_ok=True)
        with open(low_dir / MOVES_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def move_group(files, dest_dir: Path):
    """Move files into dest_dir. All-or-nothing; refuses to overwrite."""
    clashes = [f.name for f in files if (dest_dir / f.name).exists()]
    if clashes:
        return False, f"already in {dest_dir.name}: {', '.join(clashes)}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    done = []
    try:
        for f in files:
            target = dest_dir / f.name
            shutil.move(str(f), str(target))
            done.append((target, f))
    except Exception as exc:
        for target, original in reversed(done):
            try:
                shutil.move(str(target), str(original))
            except Exception:
                pass
        return False, f"move failed ({exc}); rolled back"
    return True, ""


def score_clip_path(path: Path, game: str, history: dict, logged: dict):
    clip = clip_from_path(path, game=game, logged_scores=logged)
    try:
        score, breakdown = _ranker._score_clip(clip, history)
    except Exception:
        ranked = _ranker.rank_clips([clip], min_score=0, game=game)
        score = float(getattr(ranked[0], "score", 0.0) or 0.0) if ranked else 0.0
        breakdown = getattr(clip, "breakdown", "")
    try:
        tier = _ranker._classify_tier(score)
    except Exception:
        tier = ""
    return {
        "name": path.name,
        "stem": path.stem,
        "score": float(score),
        "breakdown": breakdown,
        "source": getattr(clip, "score_source", "?"),
        "tier": tier,
    }


# ── filter ───────────────────────────────────────────────────────────────────

def run_filter(*, clips_dir=CLIPS_DIR, threshold=None, game=None, dry_run=False,
               include_queued=False, queue_files=QUEUE_FILES, config=None):
    config = config if isinstance(config, dict) else (load_config() or {})
    game = game or config.get("game") or "Gaming"
    thr, thr_src = resolve_threshold(game, threshold, config)
    clips_dir = Path(clips_dir)
    low_dir = clips_dir / LOW_NAME
    result = {
        "ok": True, "dry_run": bool(dry_run), "game": game,
        "threshold": thr, "threshold_source": thr_src,
        "clips_dir": str(clips_dir), "low_dir": str(low_dir),
        "kept": [], "moved": [], "skipped": [],
    }
    clips = sorted(p for p in clips_dir.glob("*.mp4") if p.is_file()) if clips_dir.is_dir() else []
    if not clips:
        result["note"] = f"No clips in {clips_dir}"
        return result

    logged = load_logged_highlight_scores()
    history = _ranker._load_history(game)
    queue_strings = [] if include_queued else active_queue_strings(queue_files)

    for path in clips:
        row = score_clip_path(path, game, history, logged)
        if not dry_run:
            _ranker.write_clip_sidecar(
                path, ranked_score=row["score"], tier=row["tier"],
                game=game, breakdown=row["breakdown"],
            )
        if row["score"] >= thr:
            result["kept"].append(row)
            continue
        if row["source"] == "none":
            row["reason"] = "could not be scored (no sidecar, log or audio score) — kept"
            result["skipped"].append(row)
            continue
        if not include_queued and is_queued(row["stem"], queue_strings):
            row["reason"] = "still in the post queue — kept (use --include-queued to move anyway)"
            result["skipped"].append(row)
            continue
        files = companions(clips_dir, row["stem"])
        row["files"] = [f.name for f in files]
        if dry_run:
            result["moved"].append(row)
            continue
        ok, err = move_group(files, low_dir)
        if not ok:
            row["reason"] = err
            result["skipped"].append(row)
            continue
        _log_move(low_dir, {
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "action": "move", "stem": row["stem"], "score": row["score"],
            "threshold": thr, "game": game, "files": row["files"],
        })
        result["moved"].append(row)
    return result


# ── restore ──────────────────────────────────────────────────────────────────

def low_score_stems(clips_dir=CLIPS_DIR):
    low = Path(clips_dir) / LOW_NAME
    if not low.is_dir():
        return []
    return sorted(p.stem for p in low.glob("*.mp4") if p.is_file())


def run_restore(names=None, *, restore_all=False, clips_dir=CLIPS_DIR, dry_run=False):
    clips_dir = Path(clips_dir)
    low_dir = clips_dir / LOW_NAME
    available = low_score_stems(clips_dir)
    result = {
        "ok": True, "dry_run": bool(dry_run), "clips_dir": str(clips_dir),
        "low_dir": str(low_dir), "available": available,
        "restored": [], "skipped": [],
    }
    if restore_all:
        wanted = list(available)
    else:
        wanted = []
        for raw in names or []:
            stem = Path(raw).name
            for ext in (".mp4", ".json", ".jpg"):
                if stem.endswith(ext):
                    stem = stem[: -len(ext)]
            if stem in available:
                wanted.append(stem)
            else:
                result["skipped"].append({"stem": stem, "reason": f"not in {LOW_NAME}"})
    for stem in wanted:
        files = companions(low_dir, stem)
        files = [f for f in files if f.name != MOVES_LOG]
        row = {"stem": stem, "files": [f.name for f in files]}
        if dry_run:
            result["restored"].append(row)
            continue
        ok, err = move_group(files, clips_dir)
        if not ok:
            row["reason"] = err
            result["skipped"].append(row)
            continue
        _log_move(low_dir, {
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "action": "restore", "stem": stem, "files": row["files"],
        })
        result["restored"].append(row)
    if result["skipped"] and not result["restored"]:
        result["ok"] = False
    return result


# ── CLI ──────────────────────────────────────────────────────────────────────

def _print_filter(res: dict) -> None:
    if res.get("note"):
        print(res["note"])
        return
    n = len(res["kept"]) + len(res["moved"]) + len(res["skipped"])
    print(
        f"Scoring {n} clip(s) for {res['game']}  "
        f"(keep ≥ {res['threshold']:g} · {res['threshold_source']})"
    )
    for row in res["kept"]:
        print(f"  KEEP  {row['name']}  (score {row['score']:.0f})  {row['breakdown']}  src={row['source']}")
    verb_line = "WOULD MOVE" if res["dry_run"] else "MOVE"
    for row in res["moved"]:
        extra = f" + {len(row.get('files', [])) - 1} companion file(s)" if len(row.get("files", [])) > 1 else ""
        print(f"  {verb_line}  {row['name']}  (score {row['score']:.0f}){extra}  {row['breakdown']}  src={row['source']}")
    for row in res["skipped"]:
        print(f"  SKIP  {row['name']}  (score {row['score']:.0f})  {row.get('reason', '')}")
    verb = "Would move" if res["dry_run"] else "Moved"
    print(f"\n✓ Kept {len(res['kept'])} clip(s) at or above {res['threshold']:g}")
    print(f"✗ {verb} {len(res['moved'])} clip(s) to {res['low_dir']}")
    if res["skipped"]:
        print(f"• Left {len(res['skipped'])} low clip(s) in place (see SKIP reasons)")
    if res["moved"] and not res["dry_run"]:
        print("  Undo: bolt filter-backlog restore <name> | restore --all")


def _print_restore(res: dict) -> None:
    if not res["restored"] and not res["skipped"]:
        avail = res["available"]
        if not avail:
            print(f"Nothing in {res['low_dir']} to restore.")
        else:
            print(f"{len(avail)} clip(s) in {LOW_NAME}:")
            for stem in avail:
                print(f"  {stem}")
            print("Restore: bolt filter-backlog restore <name> [<name> …] | restore --all")
        return
    verb = "WOULD RESTORE" if res["dry_run"] else "RESTORED"
    for row in res["restored"]:
        print(f"  {verb}  {row['stem']}  ({len(row['files'])} file(s)) → {res['clips_dir']}")
    for row in res["skipped"]:
        print(f"  SKIP  {row['stem']}  {row.get('reason', '')}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Move low-scoring clips into media/clips/_low_score/ (and back)"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Score and print decisions without moving files")
    parser.add_argument("--threshold", type=float, default=None,
                        help="Keep clips at or above this score (default: game profile min_clip_score)")
    parser.add_argument("--game", default=None,
                        help="Game key for history/profile (default: config.json game)")
    parser.add_argument("--include-queued", action="store_true",
                        help="Also move low clips that are still in the post queue")
    parser.add_argument("--restore", nargs="*", default=None, metavar="NAME",
                        help="Move clips back from _low_score (no names = list them)")
    parser.add_argument("--all", action="store_true", help="With --restore: restore everything")
    parser.add_argument("--clips-dir", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true", help="Print a JSON result")
    args = parser.parse_args(argv)
    clips_dir = Path(args.clips_dir).expanduser().resolve() if args.clips_dir else CLIPS_DIR

    if args.restore is not None or args.all:
        res = run_restore(args.restore or [], restore_all=args.all,
                          clips_dir=clips_dir, dry_run=args.dry_run)
        print(json.dumps(res, indent=2, default=str)) if args.json else _print_restore(res)
        return 0 if res["ok"] else 1

    res = run_filter(clips_dir=clips_dir, threshold=args.threshold, game=args.game,
                     dry_run=args.dry_run, include_queued=args.include_queued)
    print(json.dumps(res, indent=2, default=str)) if args.json else _print_filter(res)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
