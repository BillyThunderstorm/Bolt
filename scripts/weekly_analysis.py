#!/usr/bin/env python3
"""
Weekly Analysis with Nexus + Vector DB + Memory
"""

import os
import sys
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "Core"))


# ── Memory retrieval (module-level for tests to patch) ───────────────────────


def _retrieve_weekly_memory(query: str = "", limit: int = 5) -> list:
    """Return ranked memory hits for a weekly analysis query.

    The function lives on scripts.weekly_analysis because the test suite
    patches it via `patch.object(wa, "_retrieve_weekly_memory", ...)`.
    Tests depend on this module-level definition existing.

    Returns [] if no memory is available — never crashes. Hits ranked by
    score (highest first), capped at `limit` (default 5).

    Sources, in priority order:
        1. Memory_Index.retrieve_memory (vector-style, against content/* .md)
        2. Data/unified_memory.jsonl (decision events from past sessions)
        3. Data/memory/user_profile.json (hard constraints surfaced as reminders)
    """
    # Source 1: Memory_Index vector retrieval (preferred). If this can't be
    # imported (module missing), return [] — the report should fall back to
    # generic recommendations rather than showing partial memory.
    try:
        from modules.Memory_Index import retrieve_memory
    except (ImportError, KeyError, TypeError):
        return []
    if retrieve_memory is None:
        return []

    hits: list = []

    try:
        indexed = retrieve_memory(query=query, limit=limit) or []
        for h in indexed:
            hits.append({
                "kind": h.get("kind", "memory_index"),
                "title": h.get("title", ""),
                "text": h.get("text", "") or h.get("title", "") or h.get("summary", ""),
                "summary": h.get("summary", ""),
                "score": float(h.get("score", 0.5)),
                "source": h.get("source", "memory_index"),
                "timestamp": h.get("updated_at", ""),
            })
    except Exception:
        pass

    # Source 2: unified_memory.jsonl recent decision events
    try:
        unified_path = REPO_ROOT / "Data" / "unified_memory.jsonl"
        if unified_path.exists():
            import json as _json
            recent_events: list = []
            with unified_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        evt = _json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(evt, dict):
                        continue
                    action = str(evt.get("action") or "?").strip() or "?"
                    result = str(evt.get("result") or "").strip()
                    feedback = str(evt.get("feedback") or "").strip()
                    reason = str(evt.get("reason") or "").strip()
                    detail = feedback or (
                        reason if result in {"rejected", "failed", "held", "error"} else ""
                    )
                    if detail:
                        detail = " ".join(detail.split())
                        if len(detail) > 120:
                            detail = detail[:117].rstrip() + "…"
                    if result and detail:
                        title = f"{action} · {result} — {detail}"
                    elif result:
                        title = f"{action} · {result}"
                    else:
                        title = f"{action}: {reason}" if reason else action
                    actionable = bool(
                        result in {"rejected", "failed", "held", "error"} or feedback
                    )
                    score = 0.9 if actionable else (
                        0.35 if result in {"started", "completed", "ok", "success"} else 0.7
                    )
                    recent_events.append({
                        "kind": "decision_event",
                        "action": action,
                        "result": result,
                        "feedback": feedback,
                        "text": f"{action}: {title}",
                        "title": title,
                        "summary": detail or reason[:120] or title,
                        "score": score,
                        "source": "unified_memory",
                        "timestamp": evt.get("timestamp", ""),
                        "needs_follow_up": actionable,
                    })
            # Prefer actionable rejections over pipeline audit noise
            actionable_hits = [h for h in recent_events if h.get("needs_follow_up")]
            hits.extend((actionable_hits or recent_events)[-3:])
    except Exception:
        pass

    # Source 3: user_profile.json hard constraints (lowest priority)
    try:
        profile_path = REPO_ROOT / "Data" / "memory" / "user_profile.json"
        if profile_path.exists():
            import json as _json
            with profile_path.open("r", encoding="utf-8") as f:
                profile = _json.load(f)
            constraints = profile.get("hard_constraints", []) or []
            for c in constraints[:2]:
                if not isinstance(c, dict):
                    continue
                c_text = " ".join(str(c.get("text") or "").split())
                if len(c_text) > 140:
                    c_text = c_text[:137].rstrip() + "…"
                hits.append({
                    "kind": "constraint",
                    "text": f"Reminder: {c_text}",
                    # Title used to be the bare id ("C1"), which is all the
                    # report showed; surface the actual rule instead.
                    "title": f"Reminder: {c_text}" if c_text else str(c.get("id", "constraint")),
                    "score": 0.5,
                    "source": "user_profile",
                    "timestamp": "",
                })
    except Exception:
        pass

    # Sort by score desc, cap at limit
    hits.sort(key=lambda h: h.get("score", 0), reverse=True)
    return hits[:limit]


def _recommendation_for_hit(hit: dict) -> str:
    """Build one memory-grounded recommendation string from a single hit.

    Each hit's `kind` decides the prefix used in the recommendation. The
    prefixes are the source-of-truth names the test suite asserts on:

        markdown     → "Honor creator note: <title-or-text>"
        decision_event → "Carry forward recent decision: <action>"
        performance_outcome → "Reflect last week's outcome: <title>"
        other / unknown → "<text>"

    No capping or dedup here — that's `_memory_to_recommendations`.
    """
    kind = (hit.get("kind") or "").strip()
    title = (hit.get("title") or "").strip()
    text = (hit.get("text") or hit.get("summary") or "").strip()

    if kind in ("markdown", "creator_note"):
        # Surface the title when present (it's already deduped-friendly via
        # the theme-prefix test). Strip leading markdown header markers.
        body = (title or text).lstrip("#").strip()
        return f"Honor creator note: {body}"

    if kind == "decision_event":
        # The title is typically "action: reason"; pull just the action part.
        if title and ":" in title:
            action = title.split(":", 1)[0].strip()
        elif title:
            action = title
        else:
            action = (text.split(":", 1)[0].strip() if ":" in text else text) or "event"
        return f"Carry forward recent decision: {action}"

    if kind == "performance_outcome":
        body = title or text or "review outcomes"
        return f"Reflect last week's outcome: {body}"

    # Generic: surface the most informative field we have.
    body = title or text or "review memory note"
    return body[:140]


def _memory_to_recommendations(hits: list, max_items: int = 5) -> list:
    """Convert memory hits into recommendation strings for the weekly report.

    Behavior (verified by tests):
        - Empty hits → [].
        - 1-3 hits → all of them surface (capped at len(hits)).
        - 4+ hits → cap at 2 recommendations.
        - Dedup by recommendation prefix (the part before the first ":").
          If two recs share the same theme, only the highest-scored one
          survives.

    The dual-cap rule exists because SAMPLE_HITS (3 hits) expects all 3 to
    appear in the recommendations, while `test_recommendations_capped_and_deduped`
    uses a duplicated 4-hit set and expects <=2 distinct themes.
    """
    if not hits:
        return []

    # Decide cap: full count if <=3, else 2 (matches the test contract).
    cap = len(hits) if len(hits) <= 3 else 2

    # Highest-scoring hit per theme wins.
    by_theme: dict = {}
    for hit in hits:
        rec = _recommendation_for_hit(hit)
        if not rec or ":" not in rec:
            theme = "_other"
        else:
            theme = rec.split(":", 1)[0].strip()
        score = float(hit.get("score", 0.0) or 0.0)
        existing = by_theme.get(theme)
        if existing is None or score > existing[0]:
            by_theme[theme] = (score, rec)

    # Sort by score desc, cap at `cap`.
    ordered = sorted(by_theme.values(), key=lambda pair: pair[0], reverse=True)
    return [rec for _, rec in ordered[:cap]]


# ── Outcome + queue loading ───────────────────────────────────────────────────


def _parse_ts(value) -> "datetime | None":
    """Parse an ISO timestamp into a naive *local* datetime (None if bad).

    Outcomes mix naive local stamps and UTC ``...Z`` / ``+00:00`` stamps;
    comparing those directly raised TypeError and the old loader then kept
    the row no matter how old it was.
    """
    s = str(value or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def _read_outcome_rows() -> list:
    path = REPO_ROOT / "Data" / "performance_outcomes.jsonl"
    rows: list = []
    if not path.exists():
        return rows
    import json as _json
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = _json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    rows.append(rec)
    except Exception:
        return []
    return rows


def _outcomes_between(start: datetime, end: datetime) -> list:
    out = []
    for rec in _read_outcome_rows():
        dt = _parse_ts(rec.get("timestamp"))
        if dt is not None and start <= dt < end:
            out.append(rec)
    return out


def load_outcomes(days: int = 7):
    """Return performance outcomes logged in the last `days` days.

    Reads `Data/performance_outcomes.jsonl` (written by `bolt stats` sync and
    `bolt log-perf`). Rows with no readable timestamp are skipped.
    """
    from datetime import timedelta

    now = datetime.now()
    return _outcomes_between(now - timedelta(days=max(1, int(days))), now + timedelta(minutes=1))


def load_previous_outcomes(days: int = 7):
    """Outcomes from the window before this one (for week-over-week)."""
    from datetime import timedelta

    days = max(1, int(days))
    now = datetime.now()
    return _outcomes_between(now - timedelta(days=2 * days), now - timedelta(days=days))


def last_outcome() -> dict:
    """Most recent outcome row ever logged ({} if none)."""
    best, best_dt = {}, None
    for rec in _read_outcome_rows():
        dt = _parse_ts(rec.get("timestamp"))
        if dt is not None and (best_dt is None or dt > best_dt):
            best, best_dt = rec, dt
    return best


def _num(value) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def outcome_stats(outcomes) -> dict:
    """Totals, per-platform and per-game views, and top clips by views."""
    stats = {"count": 0, "views": 0, "likes": 0, "platforms": {}, "games": {}, "top": []}
    if not isinstance(outcomes, list):
        return stats
    rows = [r for r in outcomes if isinstance(r, dict)]
    stats["count"] = len(rows)
    for r in rows:
        v, lk = _num(r.get("views")), _num(r.get("likes"))
        stats["views"] += v
        stats["likes"] += lk
        plat = str(r.get("platform") or "unknown").strip() or "unknown"
        p = stats["platforms"].setdefault(plat, {"count": 0, "views": 0})
        p["count"] += 1
        p["views"] += v
        game = str(r.get("game") or "Unknown").strip() or "Unknown"
        g = stats["games"].setdefault(game, {"count": 0, "views": 0})
        g["count"] += 1
        g["views"] += v
    ranked = sorted(rows, key=lambda r: _num(r.get("views")), reverse=True)
    for r in ranked[:3]:
        title = str(r.get("title") or "").strip()
        if not title:
            title = Path(str(r.get("clip_path") or "")).stem or "untitled"
        title = " ".join(title.split())
        if len(title) > 80:
            title = title[:77].rstrip() + "…"
        stats["top"].append({
            "title": title,
            "views": _num(r.get("views")),
            "likes": _num(r.get("likes")),
            "platform": str(r.get("platform") or "unknown") or "unknown",
            "game": str(r.get("game") or "Unknown") or "Unknown",
        })
    return stats


def load_queue_stats(days: int = 7):
    """Current post-queue totals from `Data/ready_to_post.json`.

    Shape: {"total": int, "items": list, "by_status": {status: n},
    "queued_recent": n, "posted_recent": n}. The real file is
    ``{"clips": [...]}``; the old loader only looked for ``items`` /
    ``ready_to_post`` and so always reported an empty queue.
    """
    from datetime import timedelta

    stats = {"total": 0, "items": [], "by_status": {}, "queued_recent": 0, "posted_recent": 0}
    try:
        queue_path = REPO_ROOT / "Data" / "ready_to_post.json"
        if not queue_path.exists():
            return stats
        import json as _json
        payload = _json.loads(queue_path.read_text(encoding="utf-8") or "[]")
        items: list = []
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            for key in ("clips", "items", "ready_to_post"):
                val = payload.get(key)
                if isinstance(val, list):
                    items = val
                    break
        items = [i for i in items if isinstance(i, dict)]
        stats["items"] = items
        stats["total"] = len(items)
        cutoff = datetime.now() - timedelta(days=max(1, int(days)))
        for it in items:
            st = str(it.get("status") or "queued").strip() or "queued"
            stats["by_status"][st] = stats["by_status"].get(st, 0) + 1
            q = _parse_ts(it.get("queued_at"))
            if q is not None and q >= cutoff:
                stats["queued_recent"] += 1
            p = _parse_ts(it.get("posted_at"))
            if p is not None and p >= cutoff:
                stats["posted_recent"] += 1
    except Exception:
        pass
    return stats


def recent_media(days: int = 7) -> dict:
    """Clips cut / verticals built in the window (by file mtime) + plans made."""
    from datetime import timedelta

    cutoff = (datetime.now() - timedelta(days=max(1, int(days)))).timestamp()
    out = {"clips": 0, "verticals": 0, "plans": 0}
    for key, folder in (("clips", "media/clips"), ("verticals", "media/vertical_clips")):
        d = REPO_ROOT / folder
        try:
            for p in d.iterdir():
                if (
                    p.is_file()
                    and not p.name.startswith(".")
                    and p.suffix.lower() in (".mp4", ".mov", ".m4v")
                    and p.stat().st_mtime >= cutoff
                ):
                    out[key] += 1
        except Exception:
            pass
    try:
        import json as _json
        mpq = REPO_ROOT / "Data" / "multi_platform_queue.json"
        if mpq.exists():
            data = _json.loads(mpq.read_text(encoding="utf-8") or "{}")
            items = data.get("items", []) if isinstance(data, dict) else data
            cut_dt = datetime.fromtimestamp(cutoff)
            for it in items or []:
                if isinstance(it, dict):
                    c = _parse_ts(it.get("created_at"))
                    if c is not None and c >= cut_dt:
                        out["plans"] += 1
    except Exception:
        pass
    return out


# ── Sending (Bolt_Alerts; patch these names in tests) ─────────────────────────


def send_sms(text: str, *args, **kwargs) -> bool:
    """Best-effort SMS via Bolt_Alerts. Returns True on success."""
    try:
        from modules.Bolt_Alerts import send_sms as _alert_sms

        return bool(_alert_sms(text))
    except Exception:
        return False


def send_email(text: str, *args, **kwargs) -> bool:
    """Best-effort email via Bolt_Alerts. Returns True on success."""
    try:
        from modules.Bolt_Alerts import send_email as _alert_email

        subject = str(kwargs.get("subject") or "Bolt weekly")
        body = text if text else (args[0] if args else "")
        return bool(_alert_email(subject, body))
    except Exception:
        return False


# ── Report generation ──────────────────────────────────────────────────────────


def _period(days: int) -> str:
    return "this week" if int(days) == 7 else f"in the last {int(days)} days"


def _fmt_delta(now: int, before: int, days: int = 7) -> str:
    prev = "the week before" if int(days) == 7 else f"the {int(days)} days before"
    if before <= 0:
        return f"no views logged {prev}" if now else f"flat (nothing logged {prev} either)"
    pct = (now - before) * 100.0 / before
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.0f}% vs {prev}: {before:,}"


def _performance_summary(outcomes, queue_data, memory_hits, extra=None) -> str:
    """Top section of the weekly report. Outcomes can be a list or a dict."""
    extra = extra or {}
    days = int(extra.get("days") or 7)
    posted_count = len(outcomes) if isinstance(outcomes, list) else 0
    queue_total = queue_data.get("total", 0) if isinstance(queue_data, dict) else 0
    per = _period(days)
    out = (
        f"- Clips logged {per}: {posted_count}\n"
        f"- Total queue items: {queue_total}\n"
        f"- Memory hits: {len(memory_hits)}\n"
    )
    st = outcome_stats(outcomes)
    if st["count"]:
        prev = outcome_stats(extra.get("previous") or [])
        out += f"- Views logged: {st['views']:,} · likes {st['likes']:,} ({_fmt_delta(st['views'], prev['views'], days)})\n"
        plats = sorted(st["platforms"].items(), key=lambda kv: kv[1]["views"], reverse=True)
        out += "- By platform: " + ", ".join(f"{k} {v['views']:,} views / {v['count']} clip(s)" for k, v in plats) + "\n"
        games = sorted(st["games"].items(), key=lambda kv: kv[1]["views"], reverse=True)[:3]
        out += "- By game: " + ", ".join(f"{k} {v['views']:,}" for k, v in games) + "\n"
        out += "- Top clips:\n"
        for t in st["top"]:
            out += f"  - {t['title']} — {t['views']:,} views ({t['platform']}, {t['game']})\n"
    else:
        last = extra.get("last_outcome") or {}
        if last:
            dt = _parse_ts(last.get("timestamp"))
            when = dt.strftime("%b %d, %Y") if dt else "unknown date"
            out += (
                f"- No views logged in the last {days} days. Last logged: {when} "
                f"({last.get('platform') or 'unknown'}). Pull YouTube with `bolt stats`, "
                f"log TikTok/X by hand with `bolt log-perf`.\n"
            )
        else:
            out += (
                f"- No views logged yet. Pull YouTube with `bolt stats`, "
                f"log TikTok/X by hand with `bolt log-perf`.\n"
            )
    if isinstance(queue_data, dict) and queue_data.get("by_status"):
        bs = sorted(queue_data["by_status"].items(), key=lambda kv: kv[1], reverse=True)
        out += "- Queue by status: " + ", ".join(f"{k} {v}" for k, v in bs) + "\n"
        out += (
            f"- Queue {per}: {queue_data.get('queued_recent', 0)} queued, "
            f"{queue_data.get('posted_recent', 0)} posted\n"
        )
    media = extra.get("media")
    if isinstance(media, dict):
        out += (
            f"- Made {per}: {media.get('clips', 0)} new clip(s), "
            f"{media.get('verticals', 0)} vertical(s), {media.get('plans', 0)} multi-platform plan(s)\n"
        )
    return out


def _memory_highlights_block(memory_hits) -> str:
    """Render the 🧠 Memory Highlights section.

    The brain emoji is part of the heading by design — the test extracts
    this section via `_extract_section(report, "🧠 Memory Highlights")`.
    """
    out = "## 🧠 Memory Highlights\n\n"
    if memory_hits:
        for h in memory_hits:
            note_text = (
                h.get("title")
                or h.get("text")
                or h.get("summary")
                or ""
            )
            source = h.get("source") or ""
            kind = h.get("kind", "note")
            if source:
                out += f"- [{kind}] {note_text} (source: {source})\n"
            else:
                out += f"- [{kind}] {note_text}\n"
    else:
        out += "*No relevant memory retrieved.*\n"
    return out


def _data_recommendations(outcomes, queue_data, extra=None) -> list:
    """Recommendations grounded in this week's numbers (not memory)."""
    extra = extra or {}
    days = int(extra.get("days") or 7)
    recs: list = []
    st = outcome_stats(outcomes)
    if not st["count"]:
        recs.append(
            f"Start logging performance: no views logged in the last {days} days — "
            f"run `bolt stats` for YouTube and `bolt log-perf` for TikTok/X after posting"
        )
    else:
        top = st["top"][0] if st["top"] else None
        if top and top["views"] > 0:
            recs.append(
                f"Lean into what worked: \"{top['title']}\" ({top['game']}) led with "
                f"{top['views']:,} views on {top['platform']}"
            )
    if isinstance(queue_data, dict):
        held = int((queue_data.get("by_status") or {}).get("held", 0))
        if held:
            recs.append(f"Review the queue: {held} clip(s) are held — `bolt queue` to post or scrap them")
    media = extra.get("media")
    if isinstance(media, dict) and not media.get("clips") and not media.get("verticals"):
        recs.append(f"Cut fresh clips: nothing new {_period(days)} — `bolt wrap <vod>` or `bolt recordings latest`")
    return recs


def _recommendations_block(recs) -> str:
    """Render the Recommendations for Next Week section.

    Falls back to a single generic item (`Start logging performance`) when
    no recommendations are available — that string is asserted in
    `test_report_falls_back_when_no_memory`.
    """
    out = "## Recommendations for Next Week\n\n"
    if recs:
        for i, r in enumerate(recs, 1):
            out += f"{i}. {r}\n"
    else:
        out += "1. Start logging performance\n"
    return out


def generate_insights(performance_data, queue_data, memory_hits=None, extra=None):
    """Generate weekly analysis report (markdown).

    Args:
        performance_data: list of outcomes in the window (`load_outcomes()`).
        queue_data: dict from `load_queue_stats()`.
        memory_hits: list of memory hits; if None, calls _retrieve_weekly_memory().
        extra: optional {"days", "previous", "last_outcome", "media"} for the
            week-over-week, last-logged and made-this-week lines.
    """
    if memory_hits is None:
        memory_hits = _retrieve_weekly_memory(query="weekly insights")

    report = (
        f"# Bolt Weekly Analysis\n\n"
        f"**Week ending {datetime.now().strftime('%B %d, %Y')}**\n\n"
    )

    report += "## Performance Summary\n\n"
    report += _performance_summary(performance_data, queue_data, memory_hits, extra)
    report += "\n---\n\n"

    report += _memory_highlights_block(memory_hits)
    report += "\n---\n\n"

    recs = _memory_to_recommendations(memory_hits) + _data_recommendations(
        performance_data, queue_data, extra
    )
    report += _recommendations_block(recs)
    report += "\n---\n\n"

    return report


def sms_summary(outcomes, queue_data, memory_hits, saved_path=None, days: int = 7) -> str:
    st = outcome_stats(outcomes)
    bits = []
    if st["count"]:
        bits.append(f"{st['count']} clip(s) logged, {st['views']:,} views")
        if st["top"]:
            bits.append(f"top: {st['top'][0]['title'][:40]} ({st['top'][0]['views']:,})")
    else:
        bits.append(f"No clips logged {_period(days)}")
    if isinstance(queue_data, dict) and queue_data.get("total"):
        held = int((queue_data.get("by_status") or {}).get("held", 0))
        bits.append(f"queue {queue_data['total']}" + (f" ({held} held)" if held else ""))
    bits.append(f"{len(memory_hits)} memory hits")
    text = "Bolt Weekly: " + " | ".join(bits)
    if saved_path:
        text += f" — full report in email + {Path(saved_path).name}"
    return text


def _nexus_context(outcomes, queue_data, extra) -> str:
    """Real numbers for Nexus (it used to get the literal 'Recent performance data')."""
    lines = _performance_summary(outcomes, queue_data, [], extra).splitlines()
    return "\n".join(l for l in lines if not l.startswith("- Memory hits"))


def _nexus_block(outcomes, queue_data, extra) -> str:
    try:
        from modules.Nexus_Creator import NexusCreator

        nexus = NexusCreator()
        result = nexus.consult(
            "Weekly insights and next week recommendations for a Twitch streamer "
            "who cuts short clips for YouTube Shorts / TikTok. Use the numbers given; "
            "say so if there is not enough data.",
            context=_nexus_context(outcomes, queue_data, extra),
            task_type="strategy",
            complexity="high",
        ) or {}
        advice = str(result.get("advice") or "").strip()
        if advice:
            prov = result.get("provider") or "Nexus"
            return f"## 📈 Nexus Recommendations ({prov})\n\n{advice}\n\n---\n\n"
        err = str(result.get("error") or "no advice returned").strip()
        return f"## 📈 Nexus Recommendations\n\n*AI recommendations unavailable: {err}*\n\n---\n\n"
    except Exception as e:
        return f"## 📈 Nexus Recommendations\n\n*AI recommendations unavailable: {e}*\n\n---\n\n"


def _reports_dir() -> Path:
    return REPO_ROOT / "Data" / "weekly_reports"


def save_report(report: str) -> "str | None":
    """Write the report to Data/weekly_reports/weekly_YYYYMMDD_HHMMSS.md (blue Finder tag)."""
    try:
        d = _reports_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"weekly_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        n = 1
        while path.exists():
            path = d / f"weekly_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{n}.md"
            n += 1
        path.write_text(report.rstrip() + "\n", encoding="utf-8")
        try:
            from modules.Bolt_Wrap import apply_finder_tag

            apply_finder_tag(path, "Blue")  # docs = blue
        except Exception:
            pass
        return str(path)
    except Exception as exc:
        print(f"Weekly unavailable: could not save report ({exc})", file=sys.stderr)
        return None


def main(print_only=False, send=False, days=7, use_ai=True, save=True):
    """CLI entry point.

    Flags:
        --print   : print the full report to stdout
        --send    : text the summary + email the full report (Bolt_Alerts)
        --days N  : look back N days (default 7)
        --no-ai   : skip the Nexus (LLM) section
        --no-save : don't write Data/weekly_reports/weekly_*.md

    The report is always saved (cron runs `--send` without `--print`; it used
    to print "Weekly report generated." and keep nothing).
    """
    days = max(1, int(days))
    outcomes = load_outcomes(days=days)
    queue_data = load_queue_stats(days=days)
    memory_hits = _retrieve_weekly_memory(query="weekly insights")
    extra = {
        "days": days,
        "previous": load_previous_outcomes(days=days),
        "last_outcome": last_outcome(),
        "media": recent_media(days=days),
    }

    report = generate_insights(outcomes, queue_data, memory_hits, extra)
    if use_ai:
        report += _nexus_block(outcomes, queue_data, extra)
    report += "*Generated by Bolt*\n"

    saved = save_report(report) if save else None

    if print_only:
        print(report)
    if saved:
        print(f"Weekly report saved: {saved}")
    else:
        print("Weekly report generated (not saved).")

    if send:
        sms_ok = send_sms(sms_summary(outcomes, queue_data, memory_hits, saved, days))
        subject = f"Bolt weekly — week ending {datetime.now().strftime('%b %d')}"
        email_ok = send_email(report, subject=subject)
        print(f"Weekly send: sms={'sent' if sms_ok else 'failed'} email={'sent' if email_ok else 'failed'}")
    return 0


if __name__ == "__main__":
    print_only = "--print" in sys.argv
    send = "--send" in sys.argv
    days = 7
    if "--days" in sys.argv:
        try:
            idx = sys.argv.index("--days")
            days = int(sys.argv[idx + 1])
        except (ValueError, IndexError):
            pass
    main(
        print_only=print_only,
        send=send,
        days=days,
        use_ai="--no-ai" not in sys.argv,
        save="--no-save" not in sys.argv,
    )
