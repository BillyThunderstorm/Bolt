#!/usr/bin/env python3
"""
Evening_Checkin -- short evening conversation about what's missing (2026-10-19)
================================================================================
Bolt looks at local data only, finds what William hasn't logged yet, asks at
most 3 short questions, saves the answers where they belong, and updates
tomorrow's step.

Sources (all local; Drive is optional and off by default):
  - Core/config.json briefing_focus.lane (fallback: Data/memory/week_card.json)
  - Data/content/catalog.json items in that lane (status testing / drafting)
  - Data/business/assessments/*.md fields that are blank or "_(not filled yet)_"
  - Today's Drive "Daily Log YYYY-MM-DD" Result/Lesson (only with --drive or
    config evening_checkin.read_drive_log=true; silently skipped offline)

Answers go to:
  - catalog notes_log  {day, date, text, at}   (or verdict / score fields)
  - the assessment field line (placeholder replaced)
  - Data/memory/checkins/YYYY-MM-DD.md          (evening log, Blue tag)
  - week_card this_week.done when a short gets posted

CLI:
  bolt checkin                       interactive (asks up to 3, Enter = skip)
  bolt checkin --questions [--json]  print today's questions only (read-only)
  bolt checkin --answer KEY=TEXT     save without prompting (repeatable).
                                     KEY is a gap key from --json, or 1/2/3
  bolt checkin --max N --date YYYY-MM-DD --drive

Voice later: voice_hook(questions, speak=..., listen=...) -- no TTS here.
"""

from __future__ import annotations

import argparse
import builtins
import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "Core" / "config.json"
CATALOG = REPO_ROOT / "Data" / "content" / "catalog.json"
ASSESSMENTS_DIR = REPO_ROOT / "Data" / "business" / "assessments"
CHECKINS_DIR = REPO_ROOT / "Data" / "memory" / "checkins"
WEEK_CARD = REPO_ROOT / "Data" / "memory" / "week_card.json"
BLUE_TAG_SOURCE = Path("/Users/carter/Desktop/WRITE HERE.webloc")
TAG_XATTR = "com.apple.metadata:_kMDItemUserTags"

ACTIVE_STATUSES = ("testing", "drafting")
JOURNAL_DAYS = 7
PLACEHOLDER_RE = re.compile(r"^\s*(_\(not [^)]*\)_|_+|tbd|todo|-|n/?a)?\s*$", re.I)
FIELD_RE = re.compile(r"^(\s*-\s*\*\*)(?P<label>[^*]+?)(:?)\*\*:?(?P<value>.*)$")
POSTED_RE = re.compile(r"^\s*(posted|published|it'?s up|uploaded)\b", re.I)

# Gap priority: lower = asked first.
PRIORITY = {
    "notes": 10,
    "verdict": 20,
    "score": 25,
    "assessment_field": 30,
    "daily_log_result": 40,
    "daily_log_lesson": 45,
    "short_progress": 50,
}

# Friendly question per assessment field label (lowercased, score stripped).
FIELD_QUESTIONS = {
    "who it's not for": "Who is the {product} NOT for?",
    "who it's for": "Who is the {product} for?",
    "pros": "What's the best thing about the {product}?",
    "cons": "What's one con of the {product}?",
    "measurable results": "What were the results with the {product}, in one line?",
    "day-by-day notes": "Any day-by-day moments you remember with the {product}? One line is fine.",
    "test method": "How did you test the {product}?",
    "duration": "How long did you test the {product}, and how many uses?",
    "disclosure": "Did you buy the {product} with your own money, or was it gifted?",
    "if it's a dud, what works instead": "If the {product} is a dud, what works instead?",
}


# ---------------------------------------------------------------- io helpers
def _today(day: Optional[str] = None) -> date:
    if isinstance(day, date):
        return day
    if day:
        return date.fromisoformat(str(day))
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/Chicago")).date()
    except Exception:
        return date.today()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _settings() -> Dict[str, Any]:
    cfg = _load_json(CONFIG, {})
    return cfg if isinstance(cfg, dict) else {}


def current_lane() -> str:
    bf = _settings().get("briefing_focus") or {}
    if bf.get("lane"):
        return str(bf["lane"])
    card = _load_json(WEEK_CARD, {}) or {}
    for slot in ("this_week", "last_week"):
        topic = str((card.get(slot) or {}).get("topic") or "").lower()
        if "tech" in topic or "gaming" in topic:
            return "tech"
        if "beauty" in topic or "skincare" in topic:
            return "beauty"
    return "product"


def _focus_item_id() -> str:
    bf = _settings().get("briefing_focus") or {}
    return str(bf.get("focus_item") or "")


def _short_name(item: Dict[str, Any]) -> str:
    """'K&F Concept Neck Phone Holder' -> 'neck phone holder' for friendly questions."""
    name = str(item.get("name") or "item")
    for brand in ("K&F Concept ", "Facmogu "):
        if name.startswith(brand):
            name = name[len(brand):]
    return name.lower()


def _lane_items(lane: str) -> List[Dict[str, Any]]:
    data = _load_json(CATALOG, {"items": []}) or {}
    items = [
        i for i in data.get("items", [])
        if isinstance(i, dict) and i.get("lane") == lane and i.get("status") in ACTIVE_STATUSES
    ]
    focus = _focus_item_id()
    items.sort(key=lambda i: (0 if focus and i.get("id") == focus else 1))
    return items


# ------------------------------------------------------------ assessments
def parse_assessment(path: Path) -> Dict[str, Any]:
    """Return {title, product, fields: [{label, key, value, line_no}]}."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    title = ""
    fields = []
    for n, line in enumerate(lines):
        if not title and line.startswith("# "):
            title = line[2:].strip()
        m = FIELD_RE.match(line)
        if not m:
            continue
        label = m.group("label").strip().rstrip(":")
        value = m.group("value").strip()
        # A field with indented sub-lines (claims, day notes) is filled if it has children.
        has_children = False
        for nxt in lines[n + 1:]:
            if FIELD_RE.match(nxt) or nxt.startswith("#"):
                break
            if nxt.strip().startswith("-") or re.match(r"^\s+\d+\.", nxt):
                if not PLACEHOLDER_RE.match(re.sub(r"^\s*(-|\d+\.)\s*(Day \d+:)?", "", nxt)):
                    has_children = True
                    break
        fields.append({
            "label": label,
            "key": _slug(re.sub(r"\(.*?\)", "", label)),
            "value": value,
            "line_no": n,
            "blank": (not has_children) and bool(PLACEHOLDER_RE.match(value)),
        })
    product = re.sub(r"^Assessment:\s*", "", title)
    product = re.sub(r"\s*\(.*\)\s*$", "", product).strip() or Path(path).stem
    return {"title": title, "product": product, "fields": fields, "path": str(path)}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _field_question(label: str, product: str) -> str:
    base = re.sub(r"\(.*?\)", "", label).strip().lower().replace("\u2019", "'")
    base = base.split("+")[0].strip() if base.startswith("verdict") else base
    if base.startswith("verdict"):
        return f"What's your verdict and score out of 10 for the {product}?"
    tmpl = FIELD_QUESTIONS.get(base)
    if tmpl:
        return tmpl.format(product=product)
    return f"Quick one for the {product}: what goes under \"{label}\"?"


# ----------------------------------------------------------- daily log (drive)
def _drive_log_fields(day: date) -> Optional[Dict[str, str]]:
    """Read Result/Lesson from Drive 'Daily Log YYYY-MM-DD'. None when unavailable."""
    try:
        from modules import Google_Drive_Handbook as G

        drive, docs = G._get_service(interactive=False)
        if not drive or not docs:
            return None
        found = G.find_daily_log(drive, G._daily_ops_id(), f"Daily Log {day.isoformat()}")
        if not found:
            return None
        text = G._doc_plain_text(docs, found["id"])
    except Exception:
        return None
    out = {}
    for key in ("Result", "Lesson"):
        m = re.search(rf"^{key}:\s*(.*)$", text or "", re.M)
        out[key.lower()] = (m.group(1).strip() if m else "")
    return out


def _drive_enabled(flag: Optional[bool]) -> bool:
    if flag is not None:
        return flag
    return bool((_settings().get("evening_checkin") or {}).get("read_drive_log", False))


def _local_log_answers(day: date) -> Dict[str, str]:
    """Answers already saved tonight (so we don't ask twice)."""
    path = CHECKINS_DIR / f"{day.isoformat()}.md"
    done: Dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^- `([^`]+)`.*?: (.*)$", line)
            if m:
                done[m.group(1)] = m.group(2)
    return done


# ------------------------------------------------------------------- gaps
def find_gaps(day: Optional[str] = None, *, drive: Optional[bool] = None) -> List[Dict[str, Any]]:
    """Ordered list of gaps (most important first). Read-only."""
    d = _today(day)
    lane = current_lane()
    gaps: List[Dict[str, Any]] = []
    answered = _local_log_answers(d)
    items = _lane_items(lane)
    assessed_paths = set()

    for item in items:
        iid = item.get("id") or _slug(item.get("name") or "")
        name = _short_name(item)
        notes = item.get("notes_log") or []
        if item.get("assessment"):
            assessed_paths.add(str((REPO_ROOT / item["assessment"]).resolve()))
        if item.get("status") == "testing":
            if not notes:
                gaps.append(_gap("notes", f"catalog:{iid}:notes", item=iid, name=name,
                                 detail="no journal notes yet"))
            elif len(notes) >= JOURNAL_DAYS and not item.get("verdict"):
                gaps.append(_gap("verdict", f"catalog:{iid}:verdict", item=iid, name=name,
                                 detail=f"{len(notes)} notes, no verdict"))
            elif not item.get("verdict"):
                gaps.append(_gap("notes", f"catalog:{iid}:notes", item=iid, name=name,
                                 detail=f"day {len(notes) + 1} note due", day_n=len(notes) + 1))
        if item.get("verdict") and item.get("score") in (None, ""):
            gaps.append(_gap("score", f"catalog:{iid}:score", item=iid, name=name,
                             detail="verdict but no score"))

    # Assessment files: blank / placeholder fields.
    product_by_path: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if item.get("assessment"):
            product_by_path[str((REPO_ROOT / item["assessment"]).resolve())] = item
    if ASSESSMENTS_DIR.is_dir():
        for path in sorted(ASSESSMENTS_DIR.glob("*.md")):
            try:
                parsed = parse_assessment(path)
            except Exception:
                continue
            item = product_by_path.get(str(path.resolve()))
            if item is not None and item.get("status") not in ACTIVE_STATUSES:
                continue
            product = _short_name(item) if item else parsed["product"]
            for f in parsed["fields"]:
                if not f["blank"]:
                    continue
                gaps.append(_gap("assessment_field", f"assessment:{path.stem}:{f['key']}",
                                 file=str(path), label=f["label"], name=product,
                                 item=(item or {}).get("id"),
                                 detail=f"{path.name}: {f['label']} blank"))

    # Today's Daily Log (Drive, optional).
    if _drive_enabled(drive):
        log = _drive_log_fields(d)
        if log is not None:
            if not log.get("result"):
                gaps.append(_gap("daily_log_result", "daily_log:result", detail="Result blank"))
            if not log.get("lesson"):
                gaps.append(_gap("daily_log_lesson", "daily_log:lesson", detail="Lesson blank"))

    # Short progress for the focus drafting item (one question max).
    drafting = [i for i in items if i.get("status") == "drafting" and i.get("verdict")]
    if drafting:
        it = drafting[0]
        gaps.append(_gap("short_progress", f"short:{it['id']}", item=it["id"], name=_short_name(it),
                         detail="short not posted yet"))

    gaps = [g for g in gaps if g["key"] not in answered]
    gaps.sort(key=lambda g: g["priority"])  # stable: catalog order within a kind
    return gaps


def _gap(kind: str, key: str, **extra: Any) -> Dict[str, Any]:
    g = {"kind": kind, "key": key, "priority": PRIORITY[kind]}
    g.update({k: v for k, v in extra.items() if v is not None})
    return g


def _question_for(gap: Dict[str, Any]) -> str:
    kind = gap["kind"]
    name = gap.get("name") or "your test item"
    if kind == "notes":
        n = gap.get("day_n")
        return (f"Day {n} on the {name}: what stood out today?" if n
                else f"First note on the {name}: what's your first impression?")
    if kind == "verdict":
        return f"You've got enough notes on the {name}. What's your verdict, in one line?"
    if kind == "score":
        return f"What score out of 10 would you give the {name}?"
    if kind == "assessment_field":
        return _field_question(gap.get("label", ""), name)
    if kind == "daily_log_result":
        return "Today's Daily Log has no Result yet. What actually got done today?"
    if kind == "daily_log_lesson":
        return "One lesson from today, in a sentence?"
    if kind == "short_progress":
        return f"How's the {name} short going? (say \"posted\" if it's up)"
    return gap.get("detail", "Anything to log?")


def questions(max: int = 3, day: Optional[str] = None, *, drive: Optional[bool] = None,
              gaps: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Top gaps as short friendly one-line questions: [{n, key, question, kind}]."""
    gaps = find_gaps(day, drive=drive) if gaps is None else gaps
    out = []
    for n, g in enumerate(gaps[: builtins.max(0, int(max))], start=1):
        out.append({"n": n, "key": g["key"], "kind": g["kind"], "question": _question_for(g)})
    return out


# ------------------------------------------------------------------ saving
def _is_skip(text: str) -> bool:
    return not text.strip() or text.strip().lower() in ("skip", "s", "pass", "-", "later", "n/a")


def save_answer(gap: Dict[str, Any], text: str, day: Optional[str] = None) -> Dict[str, Any]:
    """Save one answer. Returns {key, saved_to: [...], next_step?}."""
    d = _today(day)
    text = text.strip()
    kind = gap["kind"]
    saved: List[str] = []
    result: Dict[str, Any] = {"key": gap["key"], "text": text, "saved_to": saved}

    if kind in ("notes", "verdict", "score", "short_progress"):
        catalog = _load_json(CATALOG, {"items": []})
        item = next((i for i in catalog.get("items", []) if i.get("id") == gap.get("item")), None)
        if item is None:
            raise ValueError(f"catalog item not found: {gap.get('item')}")
        if kind == "notes":
            item.setdefault("notes_log", []).append(
                {"day": gap.get("day_n") or len(item.get("notes_log") or []) + 1,
                 "date": d.isoformat(), "text": text, "at": _now_iso()})
            saved.append("catalog notes_log")
        elif kind == "verdict":
            item["verdict"] = text
            m = re.search(r"(\d{1,2})\s*/\s*10", text)
            if m and item.get("score") in (None, ""):
                item["score"] = int(m.group(1))
            saved.append("catalog verdict")
        elif kind == "score":
            m = re.search(r"\d{1,2}", text)
            if not m:
                raise ValueError("score answer needs a number, e.g. 8")
            item["score"] = int(m.group(0))
            saved.append("catalog score")
        elif kind == "short_progress":
            item.setdefault("notes_log", []).append(
                {"day": None, "date": d.isoformat(), "text": f"Short: {text}", "at": _now_iso()})
            saved.append("catalog notes_log")
            if POSTED_RE.match(text):
                item["status"] = "posted"
                item["posted_at"] = d.isoformat()
                saved.append("catalog status=posted")
                _week_card_done(f"posted the {item.get('name')} short")
                saved.append("week_card done")
        catalog["updated_at"] = _now_iso()
        _write_json(CATALOG, catalog)
        try:
            from modules import Briefing_Focus as BF

            result["next_step"] = (BF.next_step(item) if item.get("status") in ACTIVE_STATUSES
                                   else "; ".join(BF.todays_steps()))
        except Exception:
            pass
    elif kind == "assessment_field":
        _fill_assessment_field(Path(gap["file"]), gap["label"], text)
        saved.append(Path(gap["file"]).name)
    elif kind in ("daily_log_result", "daily_log_lesson"):
        saved.append("evening log (paste into today's Daily Log)")

    _append_checkin_log(d, gap, text, saved)
    saved.append(f"checkins/{d.isoformat()}.md")
    return result


def _fill_assessment_field(path: Path, label: str, text: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for n, line in enumerate(lines):
        m = FIELD_RE.match(line)
        if m and m.group("label").strip().rstrip(":") == label:
            head = re.match(r"^(\s*-\s*\*\*[^*]+\*\*:?)", line).group(1)
            if not head.rstrip("*").endswith(":") and not head.endswith(":"):
                head += ":"
            lines[n] = f"{head} {text}"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
    raise ValueError(f"field '{label}' not found in {path.name}")


def _week_card_done(text: str) -> None:
    try:
        from modules import Week_Card as WC

        data = WC.load()
        data["this_week"].setdefault("done", []).append(text)
        WC.save(data)
    except Exception:
        card = _load_json(WEEK_CARD, {}) or {}
        card.setdefault("this_week", {}).setdefault("done", []).append(text)
        card["updated_at"] = _now_iso()
        _write_json(WEEK_CARD, card)


def _append_checkin_log(d: date, gap: Dict[str, Any], text: str, saved: List[str]) -> Path:
    CHECKINS_DIR.mkdir(parents=True, exist_ok=True)
    path = CHECKINS_DIR / f"{d.isoformat()}.md"
    new = not path.exists()
    with open(path, "a", encoding="utf-8") as fh:
        if new:
            fh.write(f"# Evening check-in {d.isoformat()}\n\n")
        when = datetime.now().strftime("%-I:%M %p")
        fh.write(f"- `{gap['key']}` ({when} CT, {_question_for(gap)}): {text}\n")
    if new:
        tag_blue(path)
    return path


def write_next_step(d: date, step: str) -> None:
    path = CHECKINS_DIR / f"{d.isoformat()}.md"
    if path.exists() and step:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"\nTomorrow's step: {step}\n")


def tag_blue(path: Path) -> bool:
    """Copy the Blue Finder tag from WRITE HERE.webloc (macOS only; soft-fail)."""
    if sys.platform != "darwin" or not BLUE_TAG_SOURCE.exists():
        return False
    try:
        hexval = subprocess.run(["xattr", "-px", TAG_XATTR, str(BLUE_TAG_SOURCE)],
                                capture_output=True, text=True, check=True).stdout
        subprocess.run(["xattr", "-wx", TAG_XATTR, hexval.replace("\n", " ").strip(), str(path)],
                       check=True, capture_output=True)
        return True
    except Exception:
        return False


def resolve_key(token: str, gaps: List[Dict[str, Any]], max_q: int) -> Optional[Dict[str, Any]]:
    token = token.strip()
    if token.isdigit():
        idx = int(token) - 1
        return gaps[idx] if 0 <= idx < min(len(gaps), max_q) else None
    return next((g for g in gaps if g["key"] == token), None)


def save_answers(pairs: List[str], day: Optional[str] = None, *, max_q: int = 3,
                 drive: Optional[bool] = None) -> List[Dict[str, Any]]:
    """Non-interactive saves: ['catalog:x:notes=text', '1=text', ...]."""
    gaps = find_gaps(day, drive=drive)
    results = []
    for pair in pairs:
        if "=" not in pair:
            results.append({"key": pair, "error": "expected KEY=TEXT"})
            continue
        key, text = pair.split("=", 1)
        gap = resolve_key(key, gaps, max_q)
        if gap is None:
            results.append({"key": key, "error": "no open gap with that key"})
            continue
        if _is_skip(text):
            results.append({"key": gap["key"], "skipped": True})
            continue
        try:
            results.append(save_answer(gap, text, day))
        except Exception as exc:
            results.append({"key": gap["key"], "error": str(exc)})
    _finish(_today(day), results)
    return results


def _finish(d: date, results: List[Dict[str, Any]]) -> str:
    steps = [r["next_step"] for r in results if r.get("next_step")]
    step = steps[-1] if steps else ""
    if not step and any(r.get("saved_to") for r in results):
        try:
            from modules import Briefing_Focus as BF

            step = (BF.todays_steps() or [""])[0]
        except Exception:
            step = ""
    if step:
        write_next_step(d, step)
    return step


# ------------------------------------------------------------- interactive
def run_interactive(max_q: int = 3, day: Optional[str] = None, *, drive: Optional[bool] = None,
                    ask: Callable[[str], str] = input, say: Callable[[str], None] = print) -> List[Dict[str, Any]]:
    gaps = find_gaps(day, drive=drive)
    qs = questions(max_q, day, gaps=gaps)
    if not qs:
        say("Nothing missing tonight. Nice work.")
        return []
    say(f"Evening check-in: {len(qs)} quick question{'s' if len(qs) != 1 else ''}. Enter skips.")
    results = []
    for q in qs:
        try:
            text = ask(f"{q['n']}. {q['question']}\n> ")
        except (EOFError, KeyboardInterrupt):
            say("")
            break
        if _is_skip(text):
            results.append({"key": q["key"], "skipped": True})
            continue
        gap = next(g for g in gaps if g["key"] == q["key"])
        try:
            results.append(save_answer(gap, text, day))
        except Exception as exc:
            say(f"  Couldn't save that ({exc}).")
    step = _finish(_today(day), results)
    saved = [r for r in results if r.get("saved_to")]
    say(f"Saved {len(saved)} answer{'s' if len(saved) != 1 else ''}." + (f" Tomorrow: {step}" if step else ""))
    return results


def voice_hook(qs: Optional[List[Dict[str, Any]]] = None, *,
               speak: Optional[Callable[[str], None]] = None,
               listen: Optional[Callable[[], str]] = None,
               day: Optional[str] = None) -> Dict[str, Any]:
    """Voice entry point for later. No TTS here.

    Without speak/listen: returns {"lines": [...]} -- the exact lines a voice
    layer should say. With both callables: runs the check-in by voice.
    """
    qs = qs if qs is not None else questions(3, day)
    lines = [q["question"] for q in qs] or ["Nothing missing tonight. Nice work."]
    if speak is None or listen is None:
        return {"lines": lines, "questions": qs}

    def _ask(prompt: str) -> str:
        speak(prompt.split("\n")[0].split(". ", 1)[-1])
        return listen() or ""

    return {"lines": lines, "results": run_interactive(len(qs), day, ask=_ask, say=speak)}


# --------------------------------------------------------------------- CLI
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="bolt checkin", description="Evening check-in (max 3 questions).")
    ap.add_argument("--questions", "-q", action="store_true", help="print questions only (read-only)")
    ap.add_argument("--gaps", action="store_true", help="print every gap found (read-only)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--answer", "-a", action="append", default=[], metavar="KEY=TEXT",
                    help="save an answer without prompting (KEY from --json, or 1/2/3)")
    ap.add_argument("--max", type=int,
                    default=int((_settings().get("evening_checkin") or {}).get("max_questions", 3)))
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today, CT)")
    ap.add_argument("--drive", action="store_true", default=None,
                    help="also read today's Drive Daily Log Result/Lesson (read-only)")
    args = ap.parse_args(argv)

    if args.answer:
        res = save_answers(args.answer, args.date, max_q=args.max, drive=args.drive)
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            for r in res:
                if r.get("error"):
                    print(f"- {r['key']}: not saved ({r['error']})")
                elif r.get("skipped"):
                    print(f"- {r['key']}: skipped")
                else:
                    print(f"- {r['key']}: saved to {', '.join(r['saved_to'])}")
            steps = [r["next_step"] for r in res if r.get("next_step")]
            if steps:
                print(f"Tomorrow: {steps[-1]}")
        return 1 if any(r.get("error") for r in res) else 0

    if args.questions or args.gaps:
        gaps = find_gaps(args.date, drive=args.drive)
        if args.gaps:
            payload: Any = gaps
        else:
            payload = questions(args.max, args.date, gaps=gaps)
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        elif args.gaps:
            for g in gaps:
                print(f"- [{g['kind']}] {g['key']}: {g.get('detail', '')}")
        else:
            if not payload:
                print("Nothing missing tonight. Nice work.")
            for q in payload:
                print(f"{q['n']}. {q['question']}")
        return 0

    run_interactive(args.max, args.date, drive=args.drive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
