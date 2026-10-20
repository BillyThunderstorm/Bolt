"""Tests for Core/modules/Evening_Checkin.py (bolt checkin).

Everything runs on temp copies: catalog, assessments, config, week card and
check-in logs. No network, no Drive, no TTS, no Finder tags.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules import Briefing_Focus as BF
from modules import Evening_Checkin as EC
from modules import Week_Card as WC

DAY = "2026-10-19"

ASSESS_BLANK = """# Assessment: Capture Card (4K HDMI)

- **Price paid / where bought / date:** $21.49 · Amazon · 2026-09-30
- **Claims tested:**
  1. 1080p capture.
- **Day-by-day notes:**
  - Day 1: Simple.
- **Cons:** Short cords.
- **Who it's for:** Anyone who needs a capture card.
- **Who it's NOT for:** _(not filled yet)_
- **Verdict + score (10/10):** Buy it.
- **Disclosure:**
"""

CATALOG = {
    "items": [
        {"id": "cap", "name": "capture card", "lane": "tech", "status": "drafting",
         "notes_log": [{"day": 1, "text": "ok"}], "verdict": "10/10", "score": 10,
         "assessment": "ASSESS/cap.md"},
        {"id": "neck", "name": "K&F Concept Neck Phone Holder", "lane": "tech", "status": "drafting",
         "notes_log": [{"day": 90, "text": "x"}], "verdict": "8/10", "score": 8},
        {"id": "new", "name": "Game Controller", "lane": "tech", "status": "testing", "notes_log": []},
        {"id": "half", "name": "Headset", "lane": "tech", "status": "testing",
         "notes_log": [{"day": 1, "text": "a"}, {"day": 2, "text": "b"}]},
        {"id": "nov", "name": "Webcam", "lane": "tech", "status": "drafting",
         "notes_log": [{"day": 1, "text": "a"}], "verdict": "good"},
        {"id": "old", "name": "Old Posted", "lane": "tech", "status": "posted", "notes_log": []},
        {"id": "other", "name": "Lipstick", "lane": "beauty", "status": "testing", "notes_log": []},
    ]
}


class EveningCheckinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="checkin_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "assess").mkdir()
        cat = json.loads(json.dumps(CATALOG))
        cat["items"][0]["assessment"] = str(self.tmp / "assess" / "cap.md")
        self.catalog = self.tmp / "catalog.json"
        self.catalog.write_text(json.dumps(cat), encoding="utf-8")
        (self.tmp / "assess" / "cap.md").write_text(ASSESS_BLANK, encoding="utf-8")
        self.config = self.tmp / "config.json"
        self.config.write_text(json.dumps({
            "briefing_focus": {"enabled": True, "lane": "tech", "focus_item": "neck"},
            "evening_checkin": {"read_drive_log": False},
        }), encoding="utf-8")
        self.week = self.tmp / "week_card.json"
        self.checkins = self.tmp / "checkins"
        patches = [
            patch.object(EC, "CATALOG", self.catalog),
            patch.object(EC, "CONFIG", self.config),
            patch.object(EC, "ASSESSMENTS_DIR", self.tmp / "assess"),
            patch.object(EC, "CHECKINS_DIR", self.checkins),
            patch.object(EC, "WEEK_CARD", self.week),
            patch.object(EC, "REPO_ROOT", self.tmp),
            patch.object(EC, "tag_blue", lambda p: False),
            patch.object(BF, "CATALOG", self.catalog),
            patch.object(BF, "CONFIG", self.config),
            patch.object(WC, "WEEK_FILE", self.week),
            patch.object(EC, "_drive_log_fields", side_effect=AssertionError("no drive in tests")),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def cat(self):
        return {i["id"]: i for i in json.loads(self.catalog.read_text())["items"]}

    # ------------------------------------------------------------ find_gaps
    def test_gaps_ordered_and_scoped_to_lane(self):
        gaps = EC.find_gaps(DAY)
        keys = [g["key"] for g in gaps]
        self.assertEqual(keys[0], "catalog:new:notes")       # no notes first
        self.assertIn("catalog:half:notes", keys)
        self.assertIn("catalog:nov:score", keys)
        self.assertIn("assessment:cap:who-it-s-not-for", keys)
        self.assertIn("assessment:cap:disclosure", keys)
        self.assertNotIn("assessment:cap:cons", keys)
        self.assertNotIn("assessment:cap:claims-tested", keys)  # has sub-lines
        self.assertFalse(any("other" in k or "old" in k for k in keys))
        prios = [g["priority"] for g in gaps]
        self.assertEqual(prios, sorted(prios))
        # focus item comes first among drafting items
        short = [g for g in gaps if g["kind"] == "short_progress"]
        self.assertEqual([g["key"] for g in short], ["short:neck"])

    def test_day_number_for_partial_journal(self):
        g = next(g for g in EC.find_gaps(DAY) if g["key"] == "catalog:half:notes")
        self.assertEqual(g["day_n"], 3)

    def test_lane_falls_back_to_week_card(self):
        self.config.write_text(json.dumps({}), encoding="utf-8")
        self.week.write_text(json.dumps({"this_week": {"topic": "gaming / tech"}}), encoding="utf-8")
        self.assertEqual(EC.current_lane(), "tech")

    def test_drive_not_called_unless_enabled(self):
        EC.find_gaps(DAY)  # side_effect would raise if called
        with patch.object(EC, "_drive_log_fields", return_value={"result": "", "lesson": "done"}):
            keys = [g["key"] for g in EC.find_gaps(DAY, drive=True)]
        self.assertIn("daily_log:result", keys)
        self.assertNotIn("daily_log:lesson", keys)

    def test_drive_offline_skips_silently(self):
        with patch.object(EC, "_drive_log_fields", return_value=None):
            keys = [g["key"] for g in EC.find_gaps(DAY, drive=True)]
        self.assertFalse(any(k.startswith("daily_log") for k in keys))

    # ------------------------------------------------------------ questions
    def test_questions_max_three_one_line(self):
        qs = EC.questions(3, DAY)
        self.assertEqual(len(qs), 3)
        self.assertEqual([q["n"] for q in qs], [1, 2, 3])
        for q in qs:
            self.assertNotIn("\n", q["question"])
            self.assertLess(len(q["question"]), 110)
        self.assertIn("game controller", qs[0]["question"])

    def test_questions_read_only(self):
        before = self.catalog.read_text()
        EC.main(["--questions", "--json", "--date", DAY])
        self.assertEqual(self.catalog.read_text(), before)
        self.assertFalse(self.checkins.exists())

    # --------------------------------------------------------------- saving
    def test_answer_note_appends_notes_log_and_evening_log(self):
        res = EC.save_answers(["catalog:half:notes=Mic is clear on calls"], DAY)
        self.assertEqual(res[0]["key"], "catalog:half:notes")
        last = self.cat()["half"]["notes_log"][-1]
        self.assertEqual((last["day"], last["date"], last["text"]), (3, DAY, "Mic is clear on calls"))
        log = (self.checkins / f"{DAY}.md").read_text()
        self.assertIn("Mic is clear on calls", log)
        self.assertIn("Tomorrow's step:", log)
        self.assertIn("Day 4 journal note on Headset", res[0]["next_step"])

    def test_answer_by_number(self):
        EC.save_answers(["1=Feels solid"], DAY)
        self.assertEqual(self.cat()["new"]["notes_log"][0]["text"], "Feels solid")

    def test_answered_gap_not_asked_again(self):
        EC.save_answers(["catalog:new:notes=first"], DAY)
        # notes exist now -> becomes a day-2 gap, but tonight's key is already answered
        keys = [g["key"] for g in EC.find_gaps(DAY)]
        self.assertNotIn("catalog:new:notes", keys)

    def test_assessment_field_fill_in(self):
        EC.save_answers(["assessment:cap:who-it-s-not-for=Pros who need 4K60 passthrough"], DAY)
        text = (self.tmp / "assess" / "cap.md").read_text()
        self.assertIn("- **Who it's NOT for:** Pros who need 4K60 passthrough", text)
        self.assertNotIn("_(not filled yet)_", text)
        self.assertIn("- **Cons:** Short cords.", text)  # untouched

    def test_score_answer(self):
        EC.save_answers(["catalog:nov:score=7 out of 10"], DAY)
        self.assertEqual(self.cat()["nov"]["score"], 7)

    def test_short_posted_updates_status_and_week_card(self):
        res = EC.save_answers(["short:neck=posted on TikTok tonight"], DAY)
        self.assertEqual(self.cat()["neck"]["status"], "posted")
        card = json.loads(self.week.read_text())
        self.assertTrue(any("Neck Phone Holder" in d for d in card["this_week"]["done"]))
        self.assertIn("week_card done", res[0]["saved_to"])

    def test_short_progress_not_posted_keeps_drafting(self):
        EC.save_answers(["short:neck=filmed the workout part"], DAY)
        item = self.cat()["neck"]
        self.assertEqual(item["status"], "drafting")
        self.assertEqual(item["notes_log"][-1]["text"], "Short: filmed the workout part")

    def test_skip_and_unknown_keys(self):
        res = EC.save_answers(["catalog:new:notes=skip", "nope:key=x", "badpair"], DAY)
        self.assertTrue(res[0]["skipped"])
        self.assertIn("error", res[1])
        self.assertIn("error", res[2])
        self.assertEqual(self.cat()["new"]["notes_log"], [])

    def test_cli_answer_exit_codes(self):
        self.assertEqual(EC.main(["--answer", "1=hello", "--date", DAY]), 0)
        self.assertEqual(EC.main(["--answer", "zzz=hello", "--date", DAY]), 1)

    # ---------------------------------------------------------- interactive
    def test_interactive_uses_input_and_skips_blank(self):
        answers = iter(["Clicky buttons", "", "6"])
        out = []
        res = EC.run_interactive(3, DAY, ask=lambda p: next(answers), say=out.append)
        self.assertEqual(len(res), 3)
        self.assertTrue(res[1]["skipped"])
        self.assertEqual(self.cat()["new"]["notes_log"][0]["text"], "Clicky buttons")
        self.assertTrue(any(line.startswith("Saved 2 answers") for line in out))

    # ---------------------------------------------------------------- voice
    def test_voice_hook_lines_without_tts(self):
        out = EC.voice_hook(day=DAY)
        self.assertEqual(len(out["lines"]), 3)
        spoken, heard = [], iter(["great grip", "skip", "skip"])
        EC.voice_hook(day=DAY, speak=spoken.append, listen=lambda: next(heard))
        self.assertTrue(spoken)
        self.assertEqual(self.cat()["new"]["notes_log"][0]["text"], "great grip")

    def test_nothing_missing(self):
        self.catalog.write_text(json.dumps({"items": []}), encoding="utf-8")
        (self.tmp / "assess" / "cap.md").unlink()
        self.assertEqual(EC.questions(3, DAY), [])
        self.assertEqual(EC.voice_hook(day=DAY)["lines"], ["Nothing missing tonight. Nice work."])


if __name__ == "__main__":
    unittest.main()
