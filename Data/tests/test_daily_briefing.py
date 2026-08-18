"""Tests for the memory-aware section of scripts/daily_briefing.py.

These tests focus on the new memory-grounded behavior:
1. The Memory Notes section renders retrieved memory hits.
2. Action items are derived from memory hits when available.
3. The briefing still renders cleanly when memory retrieval returns nothing
   (graceful fallback to generic action items).
4. The retrieval helper is best-effort: if the memory stack is unavailable,
   the briefing does not crash.
"""


import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / '3rd_Party' / 'colabs']:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import re
import unittest
from unittest.mock import patch

from scripts import daily_briefing as db


SAMPLE_HITS = [
    {
        "title": "Clip performance: manual for Marvel Rivals",
        "source": "data/performance_outcomes.jsonl",
        "kind": "performance_outcome",
        "summary": "Posted clip outcome for Marvel Rivals: trigger=manual, views=1, likes=0, success=False",
        "score": 0.91,
    },
    {
        "title": "queue_clip: No clip actions passed assistive confirmation",
        "source": "data/unified_memory.jsonl",
        "kind": "decision_event",
        "summary": "No clip actions passed assistive confirmation",
        "score": 0.62,
    },
    {
        "title": "Creator Context",
        "source": "memory/context/creator-setup.md",
        "kind": "markdown",
        "summary": "# Creator Context",
        "score": 0.55,
    },
]


def _extract_section(briefing: str, heading: str) -> str:
    """Return the markdown body between `## heading` and the next `---`."""
    pattern = re.compile(
        rf"## {re.escape(heading)}\n(.+?)\n---", re.DOTALL
    )
    match = pattern.search(briefing)
    return match.group(1).strip() if match else ""


class DailyBriefingMemoryTests(unittest.TestCase):
    def test_briefing_renders_memory_notes_when_hits_available(self):
        with patch.object(db, "_retrieve_briefing_memory", return_value=SAMPLE_HITS):
            briefing, _ = db.generate_briefing()
        notes = _extract_section(briefing, "Memory Notes")
        self.assertIn("Memory Notes", briefing)
        self.assertIn("Clip performance: manual for Marvel Rivals", notes)
        self.assertIn("data/performance_outcomes.jsonl", notes)
        self.assertIn("Creator Context", notes)

    def test_action_items_are_memory_grounded_when_hits_available(self):
        with patch.object(db, "_retrieve_briefing_memory", return_value=SAMPLE_HITS):
            briefing, _ = db.generate_briefing()
        actions = _extract_section(briefing, "Action Items For Today")
        # Memory-driven action items are present.
        self.assertIn("Review last clip performance and log outcomes", actions)
        self.assertIn("Creator note active: Creator Context", actions)
        # The decision_event hit also gets surfaced.
        self.assertIn("Follow up on recent decision: queue_clip", actions)

    def test_briefing_falls_back_when_no_memory(self):
        with patch.object(db, "_retrieve_briefing_memory", return_value=[]):
            briefing, sms = db.generate_briefing()
        notes = _extract_section(briefing, "Memory Notes")
        self.assertIn("No relevant memory retrieved", notes)
        actions = _extract_section(briefing, "Action Items For Today")
        # Generic reminders still appear.
        self.assertIn("Review clip performance and log results", actions)
        self.assertIn("Check for new recordings to process", actions)
        # Memory-driven item is NOT present.
        self.assertNotIn("Creator note active:", actions)
        # SMS summary reflects zero memory hits.
        self.assertIn("0 memory notes", sms)

    def test_sms_summary_includes_memory_count(self):
        with patch.object(db, "_retrieve_briefing_memory", return_value=SAMPLE_HITS):
            _, sms = db.generate_briefing()
        self.assertIn("3 memory notes", sms)

    def test_briefing_does_not_crash_when_memory_stack_missing(self):
        # Simulate Memory_Index being unavailable: the helper should return [].
        with patch.object(db, "_retrieve_briefing_memory", return_value=[]):
            briefing, _ = db.generate_briefing()
        # Briefing still renders the action items section.
        self.assertIn("Action Items For Today", briefing)
        self.assertIn("Quick Commands", briefing)


class MemoryToActionItemsTests(unittest.TestCase):
    def test_first_performance_outcome_becomes_canonical_review_item(self):
        actions = db._memory_to_action_items(SAMPLE_HITS)
        # First action is the canonical reminder, NOT a verbatim title repeat.
        self.assertEqual(actions[0], "Review last clip performance and log outcomes")
        # The duplicate verbatim item from the second perf hit is suppressed.
        self.assertNotIn(
            "Review last clip performance: Clip performance: manual for Marvel Rivals",
            actions,
        )

    def test_decision_and_content_memory_translate_to_action_items(self):
        actions = db._memory_to_action_items(SAMPLE_HITS)
        joined = " || ".join(actions)
        self.assertIn("Follow up on recent decision:", joined)
        self.assertIn("Creator note active: Creator Context", joined)

    def test_empty_memory_yields_empty_actions(self):
        self.assertEqual(db._memory_to_action_items([]), [])

    def test_caps_at_three_memory_actions(self):
        long_hits = SAMPLE_HITS * 3  # 9 hits
        actions = db._memory_to_action_items(long_hits)
        # Canonical review item + up to 2 more memory-driven items = max 3.
        self.assertLessEqual(len(actions), 3)


class SendDeliveryTests(unittest.TestCase):
    def test_send_writes_reminders_before_email(self):
        calls = []

        def fake_replace(actions, **kwargs):
            calls.append(("reminders", list(actions), kwargs.get("summary")))
            return {"ok": True, "actions_created": len(actions), "list": "Bolt"}

        with patch.object(db, "_retrieve_briefing_memory", return_value=[]), patch(
            "modules.Apple_Reminders.replace_today_briefing", fake_replace
        ), patch("modules.Bolt_Alerts.mac_banner", return_value=True), patch.object(
            db, "_refresh_calendar_feeds", return_value=[]
        ), patch(
            "send_notification.send_briefing", return_value=True
        ):
            briefing, sms = db.generate_briefing()
            out = db._deliver_briefing(
                briefing, sms, Path("Docs/briefings/daily/latest_morning.md")
            )
        self.assertTrue(out["reminders"]["ok"])
        self.assertTrue(out["banner"])
        self.assertTrue(calls)
        self.assertGreaterEqual(len(calls[0][1]), 1)


class RetrieveBriefingMemoryTests(unittest.TestCase):
    def test_returns_empty_when_memory_module_missing(self):
        # Force the inner import to fail by patching builtins.__import__ for
        # the duration of the call. We patch the helper's import path directly
        # so we don't affect global imports.
        with patch.dict("sys.modules", {"modules.Memory_Index": None}):
            result = db._retrieve_briefing_memory()
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
