# modules/AI_Title_Generator.py
# Viral title templates + local A/B trainer from performance_outcomes.jsonl.
#
# Intended purpose (READINESS IDEA → READY):
#   Learn which title categories/templates historically earn more views,
#   then bias generate_title() / propose_ab() toward winners.
# Soft-fail prefix: "Title trainer unavailable:"
#
# CLI:
#   bolt titles                 # status (safe)
#   bolt titles status [--json]
#   bolt titles train [--dry-run] [--days N]
#   bolt titles ab "base title" [--game NAME] [--json]
#
# Model file: Data/viral_titles_model.json
# Outcomes:   Data/performance_outcomes.jsonl (same as bolt analytics / stats)

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = PROJECT_ROOT / "Data" / "viral_titles_model.json"
_OUTCOME_CANDIDATES = (
    PROJECT_ROOT / "Data" / "performance_outcomes.jsonl",
    PROJECT_ROOT / "Data" / "data" / "performance_outcomes.jsonl",
    PROJECT_ROOT / "data" / "performance_outcomes.jsonl",
)

# Back-compat name used by older callers / docs.
VIRAL_MODEL_FILE = str(MODEL_PATH)

TITLE_TEMPLATES: Dict[str, List[str]] = {
    "reaction": [
        "I can't believe this happened in {game}",
        "This {game} moment broke my brain",
        "Nobody saw this coming in {game}",
        "My reaction to this {game} clip says everything",
    ],
    "achievement": [
        "Finally hit {achievement} in {game}",
        "The {game} play I've been grinding for",
        "How I pulled off the impossible in {game}",
        "{achievement} after 100 hours of {game}",
    ],
    "funny": [
        "The funniest thing that happened in {game} today",
        "This {game} bug is actually hilarious",
        "I don't even know what happened here ({game})",
        "This {game} moment lives rent free in my head",
    ],
    "hype": [
        "The most insane {game} clip you'll see today",
        "This {game} play is UNREAL",
        "POV: you just went off in {game}",
        "No way this actually worked in {game}",
    ],
    "challenge": [
        "Can this {game} strategy actually work?",
        "What happens when you try this in {game}",
        "Testing the most broken thing in {game}",
        "This should not be possible in {game}",
    ],
    "informative": [
        "How to pull this off in {game}",
        "The {game} technique nobody talks about",
        "This is why {game} pros do it this way",
        "Learn this {game} trick in 30 seconds",
    ],
}

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "reaction": ["insane", "crazy", "no way", "what", "omg", "bro", "wait"],
    "achievement": ["finally", "clutch", "first time", "win", "victory", "ranked"],
    "funny": ["lol", "lmao", "bug", "glitch", "wtf", "accident", "oops"],
    "hype": ["go off", "cracked", "nasty", "goated", "diff", "aim"],
    "challenge": ["try", "test", "see if", "attempt", "challenge", "strategy"],
    "informative": ["how", "tip", "trick", "tutorial", "learn", "guide"],
}


def _notify(msg: str, *, level: str = "info", reason: str = "") -> None:
    try:
        from modules.notifier import notify

        notify(msg, level=level, reason=reason or None)
    except Exception:
        # Trainer must never depend on the notifier being importable.
        pass


def _notify_title(clip: str, title: str, category: str, runner_up: Optional[str]) -> None:
    try:
        from modules.notifier import notify_title

        notify_title(clip, title, category, runner_up)
    except Exception:
        pass


def _notify_error(where: str, exc: BaseException, *, recoverable: bool = True) -> None:
    try:
        from modules.notifier import notify_error

        notify_error(where, exc, recoverable=recoverable)
    except Exception:
        print(f"Title trainer unavailable: {where}: {exc}", file=sys.stderr)


def _resolve_outcomes_path(path: Optional[Path] = None) -> Path:
    if path is not None:
        return path
    for candidate in _OUTCOME_CANDIDATES:
        if candidate.exists():
            return candidate
    return _OUTCOME_CANDIDATES[0]


def _load_outcomes(
    path: Optional[Path] = None, *, days: Optional[int] = None
) -> List[Dict[str, Any]]:
    path = _resolve_outcomes_path(path)
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    cutoff: Optional[float] = None
    if days is not None:
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if cutoff is not None:
                    ts_str = row.get("timestamp")
                    if not ts_str:
                        continue
                    try:
                        ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        if ts.timestamp() < cutoff:
                            continue
                    except (ValueError, TypeError):
                        continue
                rows.append(row)
    except OSError as exc:
        _notify_error("load_outcomes", exc, recoverable=True)
        return []
    return rows


def _empty_model() -> Dict[str, Any]:
    return {
        "category_performance": {},
        "template_performance": {},
        "history": [],
        "trained_at": None,
        "trained_from": None,
        "trained_rows": 0,
        "version": 1,
    }


def _load_model() -> Dict[str, Any]:
    if MODEL_PATH.exists():
        try:
            with open(MODEL_PATH, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("category_performance", {})
                data.setdefault("template_performance", {})
                data.setdefault("history", [])
                return data
        except (OSError, json.JSONDecodeError):
            pass
    # Legacy CWD path (pre-READY bug)
    legacy = Path("viral_titles_model.json")
    if legacy.exists() and legacy.resolve() != MODEL_PATH.resolve():
        try:
            with open(legacy, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("category_performance", {})
                data.setdefault("template_performance", {})
                data.setdefault("history", [])
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return _empty_model()


def _save_model(model: Dict[str, Any]) -> None:
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2)


def _avg(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _classify_title(title: str) -> str:
    title_lower = (title or "").lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return category
    return "hype"


def _detect_achievement(transcription: str) -> Optional[str]:
    achievement_phrases = [
        "kill streak",
        "ace",
        "clutch",
        "MVP",
        "win",
        "ranked up",
        "headshot",
    ]
    tl = (transcription or "").lower()
    for phrase in achievement_phrases:
        if phrase.lower() in tl:
            return phrase
    return None


def _get_category_performance(category: str) -> float:
    model = _load_model()
    views = model.get("category_performance", {}).get(category, [])
    if isinstance(views, list):
        return _avg([float(v) for v in views if isinstance(v, (int, float))])
    if isinstance(views, (int, float)):
        return float(views)
    return 0.0


def _pick_best_template(templates: List[str], category: str) -> str:
    model = _load_model()
    performance = model.get("template_performance", {}) or {}
    scored = [(t, float(performance.get(t, 0) or 0)) for t in templates]
    scored.sort(key=lambda x: x[1], reverse=True)
    if scored and scored[0][1] > 0:
        return scored[0][0]
    return random.choice(templates) if templates else ""


def _record_title(title: str, category: str, clip_path: str) -> None:
    try:
        model = _load_model()
        model.setdefault("history", []).append(
            {
                "title": title,
                "category": category,
                "clip": str(clip_path),
                "views": None,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        # Cap history so the model file stays small.
        if len(model["history"]) > 500:
            model["history"] = model["history"][-500:]
        _save_model(model)
    except OSError as exc:
        _notify_error("record_title", exc, recoverable=True)


def generate_title(
    clip_path: str,
    game: str,
    transcription: str = "",
    visual_intensity: float = 0.5,
) -> str:
    """
    Generate the best title for a clip using templates + learned category bias.
    """
    _notify(
        f"Generating title for: {Path(clip_path).name}",
        level="info",
        reason="Title generation analyzes transcript + video energy + learned category averages.",
    )

    category_scores = {cat: 0 for cat in TITLE_TEMPLATES}
    transcript_lower = (transcription or "").lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in transcript_lower:
                category_scores[category] += 1

    if visual_intensity >= 0.7:
        category_scores["hype"] += 2
        category_scores["reaction"] += 1
    elif visual_intensity <= 0.3:
        category_scores["informative"] += 2
        category_scores["achievement"] += 1

    best_category = max(
        category_scores,
        key=lambda c: (category_scores[c], _get_category_performance(c)),
    )
    templates = TITLE_TEMPLATES[best_category]
    best_template = _pick_best_template(templates, best_category)
    runner_up_template = None
    for t in templates:
        if t != best_template:
            runner_up_template = t
            break

    achievement = _detect_achievement(transcription)
    fill = {"game": game or "this game", "achievement": achievement or "this moment"}
    title = best_template.format(**fill)
    runner_up = (
        runner_up_template.format(**fill) if runner_up_template else None
    )

    _notify_title(Path(clip_path).name, title, best_category, runner_up)
    _record_title(title, best_category, clip_path)
    return title


def propose_ab(
    *,
    game: str = "this game",
    transcription: str = "",
    visual_intensity: float = 0.5,
    base_title: Optional[str] = None,
    clip_path: str = "clip.mp4",
) -> Dict[str, Any]:
    """
    Return an A/B pair: primary (A) + runner-up (B) with categories and scores.
    Soft local loop — no network.
    """
    try:
        category_scores = {cat: 0.0 for cat in TITLE_TEMPLATES}
        text = f"{base_title or ''} {transcription or ''}".lower()
        for category, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    category_scores[category] += 1.0

        if visual_intensity >= 0.7:
            category_scores["hype"] += 2
            category_scores["reaction"] += 1
        elif visual_intensity <= 0.3:
            category_scores["informative"] += 2
            category_scores["achievement"] += 1

        # Fold in learned averages so A/B prefers historically stronger categories.
        ranked: List[Tuple[str, float]] = []
        for cat, score in category_scores.items():
            ranked.append((cat, score + (_get_category_performance(cat) / 1000.0)))
        ranked.sort(key=lambda x: x[1], reverse=True)

        achievement = _detect_achievement(transcription) or "this moment"
        fill = {"game": game or "this game", "achievement": achievement}

        variants: List[Dict[str, Any]] = []
        used_titles: set[str] = set()
        for cat, score in ranked:
            templates = TITLE_TEMPLATES.get(cat) or []
            if not templates:
                continue
            tmpl = _pick_best_template(templates, cat)
            title = tmpl.format(**fill)
            if title in used_titles:
                continue
            used_titles.add(title)
            variants.append(
                {
                    "label": "A" if not variants else "B",
                    "title": title,
                    "category": cat,
                    "score": round(score, 3),
                    "template": tmpl,
                }
            )
            if len(variants) >= 2:
                break

        if base_title and base_title.strip():
            # Keep user/base title as variant A when provided.
            variants = [
                {
                    "label": "A",
                    "title": base_title.strip(),
                    "category": _classify_title(base_title),
                    "score": None,
                    "template": None,
                    "source": "base",
                }
            ] + [
                {**v, "label": "B"}
                for v in variants[:1]
            ]

        model = _load_model()
        return {
            "ok": True,
            "variants": variants,
            "game": game,
            "model_trained_rows": int(model.get("trained_rows") or 0),
            "hint": (
                "Pick A or B; after posting, bolt log_perf / bolt stats "
                "then bolt titles train to feed the loop."
            ),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Title trainer unavailable: {exc}",
            "variants": [],
        }


def train_from_outcomes(
    *,
    days: Optional[int] = None,
    dry_run: bool = False,
    outcomes_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Supervised update from performance_outcomes.jsonl (title + views).
    Soft-fails when the log is missing or has no titled rows.
    """
    try:
        path = _resolve_outcomes_path(outcomes_path)
        rows = _load_outcomes(path, days=days)
        titled = [
            r
            for r in rows
            if (r.get("title") or "").strip()
            and isinstance(r.get("views"), (int, float))
        ]
        if not path.exists():
            return {
                "ok": False,
                "error": (
                    f"Title trainer unavailable: missing outcomes log at {path}. "
                    "Log views with bolt log_perf or bolt stats sync."
                ),
                "trained_rows": 0,
                "dry_run": dry_run,
            }
        if not titled:
            return {
                "ok": False,
                "error": (
                    "Title trainer unavailable: no titled rows with views in "
                    f"{path}. Add titles via bolt stats / bolt log_perf."
                ),
                "trained_rows": 0,
                "outcomes_rows": len(rows),
                "dry_run": dry_run,
                "outcomes_file": str(path),
            }

        cat_views: Dict[str, List[float]] = defaultdict(list)
        tmpl_scores: Dict[str, List[float]] = defaultdict(list)
        for r in titled:
            title = str(r.get("title") or "").strip()
            views = float(r.get("views") or 0)
            cat = _classify_title(title)
            cat_views[cat].append(views)
            # Fuzzy template credit: if a stored template's stem appears in the title.
            title_l = title.lower()
            for c, templates in TITLE_TEMPLATES.items():
                for tmpl in templates:
                    stem = (
                        tmpl.replace("{game}", "")
                        .replace("{achievement}", "")
                        .strip()
                        .lower()
                    )
                    # Use a short distinctive chunk from the template.
                    chunk = " ".join(stem.split()[:4])
                    if chunk and chunk in title_l:
                        tmpl_scores[tmpl].append(views)

        summary = {
            cat: {
                "n": len(vals),
                "avg_views": round(_avg(vals), 2),
            }
            for cat, vals in sorted(cat_views.items(), key=lambda kv: -_avg(kv[1]))
        }

        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "trained_rows": len(titled),
                "outcomes_rows": len(rows),
                "outcomes_file": str(path),
                "categories": summary,
                "model_path": str(MODEL_PATH),
                "hint": "Re-run without --dry-run to write Data/viral_titles_model.json",
            }

        model = _load_model()
        # Replace category samples with this training pass (bounded list).
        model["category_performance"] = {
            cat: vals[-50:] for cat, vals in cat_views.items()
        }
        # Template performance = running average views when fuzzy-matched.
        tmpl_perf = model.get("template_performance") or {}
        for tmpl, vals in tmpl_scores.items():
            tmpl_perf[tmpl] = round(_avg(vals), 2)
        model["template_performance"] = tmpl_perf
        model["trained_at"] = datetime.now(timezone.utc).isoformat()
        model["trained_from"] = str(path)
        model["trained_rows"] = len(titled)
        _save_model(model)

        _notify(
            f"Title trainer: learned from {len(titled)} titled outcomes",
            level="success",
            reason="Category averages now bias generate_title / propose_ab.",
        )
        return {
            "ok": True,
            "dry_run": False,
            "trained_rows": len(titled),
            "outcomes_rows": len(rows),
            "outcomes_file": str(path),
            "model_path": str(MODEL_PATH),
            "categories": summary,
            "hint": "Next: bolt titles ab \"your title\" — or re-run after more bolt stats pulls.",
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Title trainer unavailable: {exc}",
            "trained_rows": 0,
            "dry_run": dry_run,
        }


def train_on_titles(titles_file: str) -> Dict[str, Any]:
    """
    Feed labeled examples: [{"title": "...", "views": 1000}, ...].
    Kept for back-compat with the original supervised API.
    """
    _notify(
        f"Training on titles from: {titles_file}",
        level="info",
        reason="Supervised examples update category_performance for future clips.",
    )
    try:
        with open(titles_file, encoding="utf-8") as f:
            examples = json.load(f)
        if not isinstance(examples, list):
            raise ValueError("expected a JSON list of {title, views}")
    except Exception as e:
        _notify_error("train_on_titles", e, recoverable=False)
        return {
            "ok": False,
            "error": f"Title trainer unavailable: {e}",
            "trained_rows": 0,
        }

    model = _load_model()
    n = 0
    for example in examples:
        if not isinstance(example, dict):
            continue
        title = example.get("title", "") or ""
        views = example.get("views", 0) or 0
        try:
            views_f = float(views)
        except (TypeError, ValueError):
            continue
        category = _classify_title(str(title))
        model.setdefault("category_performance", {}).setdefault(category, [])
        model["category_performance"][category].append(views_f)
        n += 1
    model["trained_at"] = datetime.now(timezone.utc).isoformat()
    model["trained_from"] = str(titles_file)
    model["trained_rows"] = n
    try:
        _save_model(model)
    except OSError as e:
        return {
            "ok": False,
            "error": f"Title trainer unavailable: {e}",
            "trained_rows": n,
        }
    _notify(
        f"Trained on {n} title examples",
        level="success",
        reason="The model prefers categories that historically got more views.",
    )
    return {"ok": True, "trained_rows": n, "model_path": str(MODEL_PATH)}


def status() -> Dict[str, Any]:
    """
    Title trainer readiness. Never raises.
    ready = outcomes log exists with at least one titled row OR a trained model exists.
    """
    try:
        outcomes = _resolve_outcomes_path()
        rows = _load_outcomes(outcomes) if outcomes.exists() else []
        titled = [
            r
            for r in rows
            if (r.get("title") or "").strip()
            and isinstance(r.get("views"), (int, float))
        ]
        model = _load_model()
        cat_perf = model.get("category_performance") or {}
        cats_with_data = [
            c
            for c, v in cat_perf.items()
            if (isinstance(v, list) and v) or isinstance(v, (int, float))
        ]
        model_exists = MODEL_PATH.exists()
        trained_rows = int(model.get("trained_rows") or 0)
        ready = bool(titled) or (model_exists and trained_rows > 0) or bool(cats_with_data)

        if ready and cats_with_data:
            hint = (
                f"Trainer ready — {len(cats_with_data)} categor"
                f"{'y' if len(cats_with_data) == 1 else 'ies'} learned. "
                "Try: bolt titles ab \"your title\" / bolt titles train"
            )
        elif ready and titled:
            hint = (
                f"{len(titled)} titled outcome(s) ready to learn. "
                "Try: bolt titles train  (or --dry-run first)"
            )
        else:
            hint = (
                "Title trainer unavailable: no titled outcomes yet. "
                "After posting, bolt log_perf or bolt stats sync, then bolt titles train."
            )

        top_categories = []
        for cat in cats_with_data:
            vals = cat_perf.get(cat) or []
            if isinstance(vals, list):
                avg = _avg([float(x) for x in vals if isinstance(x, (int, float))])
                n = len(vals)
            else:
                avg = float(vals)
                n = 1
            top_categories.append({"category": cat, "n": n, "avg_views": round(avg, 2)})
        top_categories.sort(key=lambda x: -x["avg_views"])

        return {
            "ready": ready,
            "model_path": str(MODEL_PATH),
            "model_exists": model_exists,
            "trained_at": model.get("trained_at"),
            "trained_rows": trained_rows,
            "categories_learned": len(cats_with_data),
            "top_categories": top_categories[:6],
            "outcomes_file": str(outcomes),
            "outcomes_rows": len(rows),
            "titled_rows": len(titled),
            "templates": {k: len(v) for k, v in TITLE_TEMPLATES.items()},
            "hint": hint,
        }
    except Exception as exc:
        return {
            "ready": False,
            "error": f"Title trainer unavailable: {exc}",
            "hint": f"Title trainer unavailable: {exc}",
        }


def print_status(*, as_json: bool = False) -> int:
    info = status()
    if as_json:
        print(json.dumps(info, indent=2))
        return 0
    ready = "yes" if info.get("ready") else "no"
    print(f"Title trainer ready: {ready}")
    if info.get("error"):
        print(info["error"])
    print(f"  model:     {info.get('model_path')}")
    print(f"  trained:   rows={info.get('trained_rows')}  at={info.get('trained_at')}")
    print(
        f"  outcomes:  {info.get('titled_rows')}/{info.get('outcomes_rows')} "
        f"titled  ({info.get('outcomes_file')})"
    )
    tops = info.get("top_categories") or []
    if tops:
        print("  categories:")
        for row in tops:
            print(
                f"    - {row['category']}: avg_views={row['avg_views']} (n={row['n']})"
            )
    print(f"  hint: {info.get('hint')}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bolt titles",
        description=(
            "Local title A/B trainer — learns from Data/performance_outcomes.jsonl "
            "into Data/viral_titles_model.json. Soft-fail: Title trainer unavailable:"
        ),
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        help="status | train | ab  (default: status)",
    )
    parser.add_argument("text", nargs="?", default=None, help="Base title for `ab`")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument("--dry-run", action="store_true", help="train: don't write model")
    parser.add_argument("--days", type=int, default=None, help="train: only last N days")
    parser.add_argument("--game", default="this game", help="ab: game name fill-in")
    parser.add_argument(
        "--file",
        default=None,
        help="train: optional JSON list file instead of outcomes log",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    action = (args.action or "status").lower().replace("_", "-")
    if action in ("status", "check", "ready"):
        return print_status(as_json=args.json)

    if action in ("train", "learn", "fit"):
        if args.file:
            result = train_on_titles(args.file)
        else:
            result = train_from_outcomes(days=args.days, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result.get("ok"):
                print(
                    f"Title trainer: {'dry-run ' if result.get('dry_run') else ''}"
                    f"trained_rows={result.get('trained_rows')}"
                )
                cats = result.get("categories") or {}
                for cat, stats in list(cats.items())[:8]:
                    print(
                        f"  {cat}: avg_views={stats.get('avg_views')} (n={stats.get('n')})"
                    )
                if result.get("model_path") and not result.get("dry_run"):
                    print(f"  wrote {result['model_path']}")
                print(f"  hint: {result.get('hint')}")
            else:
                print(result.get("error") or "Title trainer unavailable:", file=sys.stderr)
        return 0 if result.get("ok") else 0  # soft-fail exit 0

    if action in ("ab", "a/b", "propose", "variants"):
        base = args.text
        result = propose_ab(game=args.game, base_title=base)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if not result.get("ok"):
                print(result.get("error") or "Title trainer unavailable:", file=sys.stderr)
                return 0
            for v in result.get("variants") or []:
                score = v.get("score")
                score_s = "" if score is None else f", score={score}"
                print(
                    f"  {v.get('label')}: {v.get('title')}  "
                    f"[{v.get('category')}{score_s}]"
                )
            print(f"  hint: {result.get('hint')}")
        return 0

    print(f"unknown titles action: {action}", file=sys.stderr)
    print("  try: bolt titles | bolt titles train | bolt titles ab \"…\"", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
