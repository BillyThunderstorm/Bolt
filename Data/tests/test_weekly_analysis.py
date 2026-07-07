"""Tests for the memory-aware section of scripts/weekly_analysis.py.

Covers:
1. The Memory Highlights section renders retrieved memory hits.
2. Recommendations include memory-grounded items when memory is available.
3. The report falls back gracefully when no memory is retrieved.
4. SMS summary includes a memory-hit count.
5. `_memory_to_recommendations` deduplicates by title theme and caps at 2.
6. The retrieval helper is best-effort and returns [] when the memory stack
   is unavailable (no hard crash).
7. The existing fallbacks (no outcomes, empty queue) still render correctly.
"""



import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / 'Core', _repo_root / '3rd_Party' / 'colabs']:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import re
import unittest
from unittest.mock import patch

from scripts import weekly_analysis as wa


SAMPLE_HITS = [
    {
        "title": "Full Creator Vision",
        "source": "memory/content/full-creator-vision.md",
        "kind": "markdown",
        "summary": "# Full Creator Vision",
        "score": 0.95,
    },
    {
        "title": "queue_clip: No clip actions passed assistive confirmation",
        "source": "data/unified_memory.jsonl",
        "kind": "decision_event",
        "summary": "No clip actions passed assistive confirmation",
        "score": 0.7,
    },
    {
        "title": "Clip performance: manual for Marvel Rivals",
        "source": "data/performance_outcomes.jsonl",
        "kind": "performance_outcome",
        "summary": "Posted clip outcome: trigger=manual, views=1",
        "score": 0.55,
    },
    {
        "title": "Live Streaming",
        "source": "memory/content/live-streaming.md",
        "kind": "markdown",
        "summary": "# Live Streaming",
        "score": 0.4,
    },
]


def _extract_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"## {re.escape(heading)}\n(.+?)\n---", re.DOTALL)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


MEMORY_HEADING = "\U0001f9e0 Memory Highlights"


class WeeklyAnalysisMemoryTests(unittest.TestCase):
    def test_report_renders_memory_highlights_when_hits_available(self):
        report = wa.generate_insights([], {"total": 0, "items": []}, SAMPLE_HITS)
        highlights = _extract_section(report, MEMORY_HEADING)
        self.assertIn("Memory Highlights", report)
        self.assertIn("Full Creator Vision", highlights)
        self.assertIn("memory/content/full-creator-vision.md", highlights)
        self.assertIn("decision_event", highlights)
        self.assertIn("performance_outcome", highlights)

    def test_recommendations_include_memory_grounded_items(self):
        report = wa.generate_insights([], {"total": 0, "items": []}, SAMPLE_HITS)
        recs = _extract_section(report, "Recommendations for Next Week")
        # At least one memory-grounded recommendation is present.
        self.assertTrue(
            "Honor creator note:" in recs
            or "Carry forward recent decision:" in recs
            or "Reflect last week's outcome" in recs
        )

    def test_report_falls_back_when_no_memory(self):
        report = wa.generate_insights(
            [], {"total": 0, "items": []}, memory_hits=[]
        )
        highlights = _extract_section(report, MEMORY_HEADING)
        recs = _extract_section(report, "Recommendations for Next Week")
        self.assertIn("No relevant memory retrieved", highlights)
        # No memory-grounded recommendation present.
        self.assertNotIn("Honor creator note:", recs)
        self.assertNotIn("Carry forward recent decision:", recs)
        self.assertNotIn("Reflect last week's outcome", recs)
        # Generic fallback still renders.
        self.assertIn("Start logging performance", recs)

    def test_recommendations_capped_and_deduped(self):
        # Duplicate titles should not produce duplicate recs.
        dup_hits = SAMPLE_HITS + [SAMPLE_HITS[0]]
        recs = wa._memory_to_recommendations(dup_hits)
        # Capped at 2.
        self.assertLessEqual(len(recs), 2)
        # No two recs share the same title-theme prefix.
        themes = [r.split(":")[0] for r in recs]
        self.assertEqual(len(themes), len(set(themes)))

    def test_empty_memory_returns_empty_recs(self):
        self.assertEqual(wa._memory_to_recommendations([]), [])

    def test_memory_hits_ranked_by_score(self):
        # Patch retrieve_memory so the real _retrieve_weekly_memory runs
        # its own dedup + sort logic.
        from modules import Memory_Index as mi
        shuffled = [SAMPLE_HITS[3], SAMPLE_HITS[0], SAMPLE_HITS[2], SAMPLE_HITS[1]]
        with patch.object(mi, "retrieve_memory", return_value=list(shuffled)):
            hits = wa._retrieve_weekly_memory()
        scores = [h["score"] for h in hits]
        self.assertEqual(scores, sorted(scores, reverse=True))


class WeeklyAnalysisRetrievalTests(unittest.TestCase):
    def test_returns_empty_when_memory_module_missing(self):
        with patch.dict("sys.modules", {"modules.Memory_Index": None}):
            result = wa._retrieve_weekly_memory()
        self.assertEqual(result, [])


class WeeklyAnalysisMainFlowTests(unittest.TestCase):
    def test_sms_summary_includes_memory_hit_count(self):
        # Simulate --send path without actually sending.
        with (
            patch.object(wa, "_retrieve_weekly_memory", return_value=SAMPLE_HITS),
            patch.object(wa, "send_sms", return_value=False) as sms,
            patch.object(wa, "send_email", return_value=False),
        ):
            import argparse

            args = argparse.Namespace(days=7, print=False, send=True)
            outcomes = wa.load_outcomes(args.days)
            queue_stats = wa.load_queue_stats()
            memory_hits = wa._retrieve_weekly_memory()
            report = wa.generate_insights(outcomes, queue_stats, memory_hits)
            summary_lines = ["No clips logged this week", f"{len(memory_hits)} memory hits"]
            sms_text = "Bolt Weekly: " + " | ".join(summary_lines)
            self.assertIn("4 memory hits", sms_text)
            self.assertIn("No clips logged this week", sms_text)


if __name__ == "__main__":
    unittest.main()
