"""Regression test: every creator lane Billy declared must remain reachable
through Bolt's local memory retrieval.

Billy's stated creator vision (memory/content/full-creator-vision.md) has
seven lanes:

  1. gaming
  2. tech
  3. AI development
  4. product testing
  5. Amazon storefront
  6. beauty/skincare
  7. Bolt-building (meta-lane)

The risk PROJECT_STATUS.md warns about is: "Do not shrink the creator
vision to only Twitch clips or gaming." If a lane file goes stale, gets
renamed, or its content is replaced with something generic, retrieval
should fail and this test should fail loudly.

The test uses each lane's natural vocabulary as the query (the way Billy
or Bolt would actually phrase it), then asserts the relevant memory file
appears within the top results.

Skipped if the memory index hasn't been built yet (first run before
`refresh_memory_index.py`), but only after refreshing once on the fly.
"""



import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / 'Core']:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import unittest
from pathlib import Path

from modules import Memory_Index as mi
from modules.Memory_Index import MEMORY_INDEX_FILE


# (lane label, natural query, expected source substrings)
LANES = [
    ("gaming",            "game testing review verdict honest",
     ["Data/content/game-testing.md"]),
    ("tech",              "tech learning gadget review first impressions",
     ["Data/content/product-reviews.md"]),
    ("AI development",    "AI development learning bolt building",
     ["Data/content/ai-development.md"]),
    ("product testing",   "product testing first impressions verdict review",
     ["Data/content/product-reviews.md"]),
    ("Amazon storefront", "amazon influencer storefront",
     ["Data/content/product-reviews.md"]),
    ("beauty/skincare",   "beauty skincare routine test results",
     ["Data/content/beauty-skincare.md"]),
    ("Bolt-building",     "build bolt virtual teammate features roadmap",
     ["Data/content/ai-development.md",
      "Data/content/assistant-productivity.md"]),
]

TOP_N = 8  # How deep to look in the results before declaring "unreachable".


class CreatorLaneReachabilityTests(unittest.TestCase):
    """Each test asserts one lane stays queryable through Memory_Index."""

    @classmethod
    def setUpClass(cls):
        # Always rebuild the index so the test catches BOTH file drift and
        # stale-index drift. Without this, deleting a file wouldn't be
        # detected until someone remembered to run refresh_memory_index.
        mi.refresh_memory_index()

    def _assert_lane_reachable(self, label, query, expected_sources):
        hits = mi.retrieve_memory(query, limit=TOP_N)
        sources = [hit.get("source", "") for hit in hits]
        reachable = any(
            any(expected in src for expected in expected_sources)
            for src in sources
        )
        if not reachable:
            self.fail(
                f"Creator lane '{label}' is no longer reachable through "
                f"memory retrieval.\n  query: {query!r}\n  expected any of: "
                f"{expected_sources}\n  got top {TOP_N}: {sources}"
            )

    def test_gaming_lane_reachable(self):
        self._assert_lane_reachable(*LANES[0])

    def test_tech_lane_reachable(self):
        self._assert_lane_reachable(*LANES[1])

    def test_ai_development_lane_reachable(self):
        self._assert_lane_reachable(*LANES[2])

    def test_product_testing_lane_reachable(self):
        self._assert_lane_reachable(*LANES[3])

    def test_amazon_storefront_lane_reachable(self):
        self._assert_lane_reachable(*LANES[4])

    def test_beauty_skincare_lane_reachable(self):
        self._assert_lane_reachable(*LANES[5])

    def test_bolt_building_lane_reachable(self):
        self._assert_lane_reachable(*LANES[6])


class CreatorLaneFilesExistTests(unittest.TestCase):
    """Guard against a lane file being deleted or renamed silently."""

    EXPECTED_FILES = [
        Path("Data/content/game-testing.md"),
        Path("Data/content/product-reviews.md"),
        Path("Data/content/ai-development.md"),
        Path("Data/content/beauty-skincare.md"),
        Path("Data/content/assistant-productivity.md"),
        Path("Data/content/full-creator-vision.md"),
        Path("Data/content/live-streaming.md"),
        Path("Data/content/content-creation.md"),
        Path("Data/content/social-media-management.md"),
    ]

    def test_all_lane_files_present(self):
        missing = [
            str(p) for p in self.EXPECTED_FILES if not p.exists()
        ]
        self.assertEqual(missing, [], f"Missing creator-lane files: {missing}")


class CreatorLaneContentQualityTests(unittest.TestCase):
    """Each lane file should have a Direction/Heading section, not be a stub.

    Catches the case where someone accidentally overwrites a lane file
    with placeholder text.
    """

    EXPECTED_HEADINGS = {
        Path("Data/content/game-testing.md"): ["direction", "review shape"],
        Path("Data/content/product-reviews.md"): ["direction", "amazon"],
        Path("Data/content/ai-development.md"): ["direction"],
        Path("Data/content/beauty-skincare.md"): ["direction"],
        Path("Data/content/assistant-productivity.md"): ["direction"],
        Path("Data/content/full-creator-vision.md"): ["north star", "risk"],
    }

    def test_each_lane_has_meaningful_content(self):
        problems = []
        for path, must_contain in self.EXPECTED_HEADINGS.items():
            if not path.exists():
                problems.append(f"{path}: missing")
                continue
            text = path.read_text(encoding="utf-8").lower()
            if len(text) < 200:
                problems.append(f"{path}: only {len(text)} chars")
                continue
            for needle in must_contain:
                if needle not in text:
                    problems.append(f"{path}: missing keyword {needle!r}")
        self.assertEqual(problems, [], "Lane content problems: " + "; ".join(problems))


if __name__ == "__main__":
    unittest.main()
