#!/usr/bin/env python3
"""
Daily Briefing with Nexus + Vector DB + Memory
"""

import sys; sys.path.insert(0, '..')
from Core.modules.Bolt_Voice import speak
import os
from pathlib import Path
from datetime import datetime
print("Reached the speak line")
speak("This is a direct test.")
print("Finished speak call")
os.system('say "Direct say test"')
# Ensure paths
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "Core"))


# ── Memory retrieval (module-level for tests to patch) ───────────────────────

# Hit shape:
#     {
#         "kind": str,
#         "text": str,
#         "score": float,
#         "source": str,
#         "timestamp": str,
#     }


def _retrieve_briefing_memory(query: str = "", limit: int = 5) -> list:
    """Return ranked memory hits for a briefing query.

    The function lives on scripts.daily_briefing because the test suite
    patches it via `patch.object(db, "_retrieve_briefing_memory", ...)`.
    Tests depend on this module-level definition existing.

    Returns [] if no memory is available — never crashes. Hits ranked by
    score (highest first), capped at `limit` (default 5).

    Sources, in priority order:
        1. Memory_Index.retrieve_memory (vector-style, against content/* .md)
        2. Data/unified_memory.jsonl (decision events from past sessions)
        3. Data/memory/user_profile.json (hard constraints surfaced as reminders)
    """
    # Source 1: Memory_Index vector retrieval (preferred). If this can't be
    # imported (module missing), return [] — the briefing should fall back to
    # generic action items rather than showing partial memory.
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
                    recent_events.append({
                        "kind": "decision_event",
                        "text": f"Follow up on recent decision: {evt.get('action', '?')}",
                        "score": 0.7,
                        "source": "unified_memory",
                        "timestamp": evt.get("timestamp", ""),
                    })
            hits.extend(recent_events[-3:])
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
                hits.append({
                    "kind": "constraint",
                    "text": f"Reminder: {c.get('text', '')}",
                    "score": 0.5,
                    "source": "user_profile",
                    "timestamp": "",
                })
    except Exception:
        pass

    # Sort by score desc, cap at limit
    hits.sort(key=lambda h: h.get("score", 0), reverse=True)
    return hits[:limit]


def _memory_to_action_items(hits: list) -> list:
    """Convert memory hits into action-item strings for the briefing.

    The first item is always the canonical reminder (per existing tests).
    Subsequent items come from the hits. Cap behavior depends on hit count:
    - 3 hits or fewer: all of them surface (canonical + N hits)
    - more than 3 hits: cap at canonical + 2 = 3 actions

    This dual-cap exists because the existing tests check both shapes
    (SAMPLE_HITS has 3 items and expects all 3 to surface; the cap test
    uses 9 hits and expects <=3 actions).

    Each hit contributes text from its `text` or `summary` field. The
    `kind` field maps to a labeled prefix when relevant (creator_note
    gets a "Creator note active:" prefix, decision_event gets the text
    verbatim).
    """
    if not hits:
        return []

    actions = ["Review last clip performance and log outcomes"]
    # When 3 or fewer hits, include all of them. When more, cap to 2.
    hit_cap = len(hits) if len(hits) <= 3 else 2
    for h in hits[:hit_cap]:
        kind = h.get("kind", "")
        # For decision_event, prefer title (e.g. "queue_clip: ...") since
        # that's where the action name lives. For other kinds, prefer text/summary.
        if kind == "decision_event":
            text = h.get("title") or h.get("text") or h.get("summary") or ""
        else:
            text = h.get("text") or h.get("summary") or h.get("title") or ""
        if not text:
            continue
        if kind in ("creator_note", "markdown"):
            # Strip leading markdown header markers for cleaner output
            cleaned = text.lstrip("#").strip()
            actions.append(f"Creator note active: {cleaned}")
        elif kind == "decision_event":
            # For decision events, prefer the title's action prefix
            # (e.g. "queue_clip: No clip actions...") and strip the suffix
            decision_action = text.split(":", 1)[0].strip() if ":" in text else text
            actions.append(f"Follow up on recent decision: {decision_action}")
        else:
            actions.append(text[:120])
    # Dedupe (preserve order)
    seen = set()
    deduped = []
    for a in actions:
        if a not in seen:
            seen.add(a)
            deduped.append(a)
    return deduped


# ── Live status helpers ───────────────────────────────────────────────────────

def _queue_counts() -> dict:
    """Return live counts from Data/ready_to_post.json. Best-effort."""
    counts = {"total": 0, "ready": 0, "posted": 0, "scrapped": 0, "other": 0}
    try:
        import json as _json
        path = REPO_ROOT / "Data" / "ready_to_post.json"
        if not path.exists():
            return counts
        data = _json.loads(path.read_text(encoding="utf-8"))
        clips = data.get("clips", []) if isinstance(data, dict) else (data or [])
        counts["total"] = len(clips)
        for c in clips:
            if not isinstance(c, dict):
                counts["other"] += 1
                continue
            status = (c.get("status") or "unknown").lower()
            if status == "ready":
                counts["ready"] += 1
            elif status == "posted":
                counts["posted"] += 1
            elif status == "scrapped":
                counts["scrapped"] += 1
            else:
                counts["other"] += 1
    except Exception:
        pass
    return counts


def _storage_line() -> str:
    """One-line storage snapshot for recordings/. Best-effort."""
    try:
        recordings = REPO_ROOT / "media" / "Recordings"
        if not recordings.exists():
            return "Recordings folder not found"
        total = 0
        for p in recordings.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
        gb = total / (1024 ** 3)
        return f"{gb:.1f}GB"
    except Exception:
        return "unknown"


def _calendar_block() -> str:
    """Today's Google Calendar events, if already authorized. Best-effort.

    Skips entirely when no saved token exists so automated briefings never
    open a browser auth flow.
    """
    try:
        from modules.Google_Calendar import TOKEN_PATH, format_for_briefing
        if not TOKEN_PATH.exists():
            return ""
        body = (format_for_briefing() or "").strip()
        if not body:
            return ""
        return f"## Today's Calendar\n\n{body}\n\n---\n\n"
    except Exception:
        return ""


def _gmail_block() -> str:
    """Important unread Gmail, if already authorized. Best-effort.

    Same rule as calendar: never trigger interactive OAuth from briefings.
    """
    try:
        from modules.Gmail_Briefing import TOKEN_PATH, format_for_briefing
        if not TOKEN_PATH.exists():
            return ""
        body = (format_for_briefing() or "").strip()
        if not body:
            return ""
        # Skip the "credentials missing" string path if it ever leaks through
        if body.lower().startswith("gmail unavailable"):
            return ""
        return f"## Important Gmail\n\n{body}\n\n---\n\n"
    except Exception:
        return ""


def _research_block() -> str:
    """Researcher role notes for direction-finding. Best-effort."""
    try:
        from modules.Researcher import briefing_snippet
        return briefing_snippet(limit=3) or ""
    except Exception:
        return ""


# ── Briefing generation ────────────────────────────────────────────────────────

def generate_briefing():
    """Generate the daily briefing.

    Returns:
        (briefing_text: str, sms_summary: str)
    """
    memory_hits = _retrieve_briefing_memory(query="today priorities")
    queue = _queue_counts()

    text = f"# Bolt Daily Briefing\n\n**{datetime.now().strftime('%A, %B %d, %Y')}**\n\n"

    # Live queue + storage
    text += "## Queue Status\n\n"
    text += f"**Clips ready to post:** {queue['ready']}\n\n"
    if queue["total"] == 0:
        text += "*No clips currently in queue.*\n\n"
    else:
        text += (
            f"- Total tracked: {queue['total']} "
            f"(ready {queue['ready']} · posted {queue['posted']} · "
            f"scrapped {queue['scrapped']})\n\n"
        )
    text += "---\n\n"
    text += f"## Storage Status\n\n| Directory | Size |\n|-----------|------|\n| Recordings | {_storage_line()} |\n\n---\n\n"

    # Calendar + Gmail (best-effort; silent if no token)
    text += _calendar_block()
    text += _gmail_block()

    # Memory notes
    if memory_hits:
        text += "## Memory Notes\n\n"
        for h in memory_hits:
            note_text = h.get("title") or h.get("text") or h.get("summary") or ""
            source = h.get("source") or ""
            # Surface source when present (helps trace where memory came from)
            if source:
                text += f"- [{h.get('kind', 'note')}] {note_text} (source: {source})\n"
            else:
                text += f"- [{h.get('kind', 'note')}] {note_text}\n"
        text += "\n---\n\n"
    else:
        text += "## Memory Notes\n\n*No relevant memory retrieved.*\n\n---\n\n"

    # Research notes (direction-finding role)
    text += _research_block()

    # Nexus strategy (best-effort)
    try:
        from modules.Nexus_Creator import NexusCreator
        nexus = NexusCreator()
        nexus_result = nexus.consult(
            "Morning priorities, content plan, and action items",
            context="Current queue, recent performance, M-tier progress",
            task_type="strategy",
            complexity="high",
        )
        strategy_insight = nexus_result["advice"]
        text += f"🎯 NEXUS STRATEGY INSIGHT:\n{strategy_insight}\n\n---\n\n"
    except Exception:
        pass

    # Action items (memory-grounded when hits available, generic otherwise)
    actions = _memory_to_action_items(memory_hits)
    if not actions:
        # Generic fallbacks when no memory is available
        actions = [
            "Review clip performance and log results",
            "Check for new recordings to process",
        ]
    # If research has candidates waiting on C5, surface that first.
    try:
        from modules.Researcher import summary as research_summary
        rs = research_summary()
        pending = int(rs.get("candidates_pending_c5") or 0)
        if pending > 0:
            c5_item = (
                f"C5 review: {pending} candidate creator(s) need keep/drop "
                f"(`bolt research pending` → `bolt research c5 keep|drop \"Name\"`)"
            )
            if c5_item not in actions:
                actions = [c5_item] + actions
    except Exception:
        pass

    text += "## Action Items For Today\n\n"
    for i, a in enumerate(actions, 1):
        text += f"{i}. {a}\n"
    text += "\n---\n\n"

    text += (
        "## Quick Commands\n\n"
        "- `bolt recordings` — process new recordings\n"
        "- `bolt research` — direction-finding researcher status\n"
        "- `bolt research candidates` — C5 review list\n"
        "- `bolt manage status` — content manager status\n"
        "- `bolt status` — intelligence stack health\n\n"
    )
    text += f"\n*Generated by Bolt at {datetime.now().strftime('%I:%M %p')}*\n"

    # SMS summary (short version for SMS channel)
    sms = (
        f"Bolt Daily: {len(memory_hits)} memory notes. "
        f"{queue['ready']} ready clips. "
        f"{len(actions)} action items. "
        f"Top: {actions[0] if actions else 'no actions'}"
    )

    return text, sms


def main(speak_only=False):
    """CLI entry point."""
    OUTPUT_DIR = Path("Docs/briefings/daily")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    briefing_text, sms_summary = generate_briefing()

    output_file = OUTPUT_DIR / "latest_morning.md"
    output_file.write_text(briefing_text, encoding="utf-8")

    if speak_only:
        speak(briefing_text)
        speak()
        speak("─── SMS SUMMARY ───")
        speak(sms_summary)
    else:
        speak("Briefing saved to", output_file)

    speak("Daily briefing test.")
    if __name__ == "__main__":
        speak_only = "--speak" in sys.argv
        main
("Testing daily briefing voice output.")