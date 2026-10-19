"""Targeted tests for READY `bolt game-config` (Game_Config per-game profiles).

Temp files only — never touches the real Core/config.json or
Data/configs/game_configs.json.
"""

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / "Core"]:
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from modules import Game_Config as gc


class _TempPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.core = root / "config.json"
        self.custom = root / "Data" / "configs" / "game_configs.json"
        self.legacy = root / "game_configs.json"
        self.core.write_text(json.dumps({
            "game": "Marvel Rivals",
            "highlight_sensitivity": 0.45,
            "pad_before": 8,
            "pad_after": 12,
            "tiktok_style": None,
        }))
        self._patches = [
            patch.object(gc, "_CORE_CONFIG", self.core),
            patch.object(gc, "_CUSTOM", self.custom),
            patch.object(gc, "_LEGACY_CUSTOM", self.legacy),
            patch.dict("os.environ", {"GAME_NAME": ""}),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self.tmp.cleanup()

    def _override(self, data):
        self.custom.parent.mkdir(parents=True, exist_ok=True)
        self.custom.write_text(json.dumps(data))


class EffectiveConfigTests(_TempPaths):
    def test_precedence_override_config_builtin_default(self):
        self._override({"marvel rivals": {"pad_after": 15}})
        eff = gc.effective_config()
        self.assertEqual(eff["game"], "Marvel Rivals")
        v, s = eff["values"], eff["sources"]
        self.assertEqual((v["pad_after"], s["pad_after"]), (15, "override"))
        self.assertEqual((v["pad_before"], s["pad_before"]), (8, "config"))
        self.assertEqual((v["spike_multiplier"], s["spike_multiplier"]), (2.4, "builtin"))
        self.assertEqual((v["min_clip_score"], s["min_clip_score"]), (40.0, "default"))

    def test_none_in_config_falls_through(self):
        eff = gc.effective_config("marvel rivals")
        self.assertEqual(eff["sources"]["tiktok_style"], "default")

    def test_unknown_game_uses_config_and_defaults(self):
        eff = gc.effective_config("Some New Game")
        self.assertFalse(eff["has_builtin"])
        self.assertEqual(eff["sources"]["spike_multiplier"], "default")
        self.assertEqual(eff["values"]["highlight_sensitivity"], 0.45)

    def test_broken_override_file_never_raises(self):
        self.custom.parent.mkdir(parents=True, exist_ok=True)
        self.custom.write_text("{not json")
        eff = gc.effective_config()
        self.assertEqual(eff["sources"]["pad_after"], "config")


class ApplyProfileTests(_TempPaths):
    def test_apply_returns_copy_and_metadata(self):
        self._override({"marvel rivals": {"highlight_sensitivity": 0.3}})
        base = json.loads(self.core.read_text())
        merged = gc.apply_game_profile(base, base["game"])
        self.assertEqual(base["highlight_sensitivity"], 0.45)  # not mutated
        self.assertEqual(merged["highlight_sensitivity"], 0.3)
        self.assertEqual(merged["_game_profile"]["overrides_applied"], ["highlight_sensitivity"])
        self.assertIn("overrides highlight_sensitivity", gc.profile_summary(merged))

    def test_apply_on_garbage_returns_dict(self):
        self.assertIsInstance(gc.apply_game_profile(None), dict)

    def test_set_then_effective_round_trip(self):
        res = gc.try_set("Marvel Rivals", ["pad_after=18", "game_events_enabled=false"])
        self.assertTrue(res["ok"], res)
        self.assertTrue(self.custom.is_file())
        res2 = gc.try_set("Marvel Rivals", ["pad_before=9"])  # merge keeps pad_after
        self.assertEqual(res2["overrides"]["pad_after"], 18)
        eff = gc.effective_config()
        self.assertEqual(eff["values"]["pad_before"], 9)
        self.assertIs(eff["values"]["game_events_enabled"], False)


class StatusCliTests(_TempPaths):
    def test_status_ready_and_wired(self):
        st = gc.status(probe=True)
        self.assertTrue(st["ready"])
        self.assertEqual(st["readiness"], "READY")
        self.assertTrue(st["probe_ok"])
        self.assertIn("bolt wrap", st["pipeline_wired"])
        self.assertEqual(st["effective"]["spike_multiplier"], 2.4)

    def test_show_prints_sources(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gc.main(["show", "marvel", "rivals"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("spike_multiplier: 2.4  [builtin]", out)
        self.assertIn("pad_before: 8  [config]", out)


class WiringTests(_TempPaths):
    def test_obs_monitor_gets_profile_spike(self):
        from modules import OBS_Integration as oi

        seen = {}

        class FakeMonitor:
            def __init__(self, spike_multiplier=2.8, **kw):
                seen["spike"] = spike_multiplier

        with patch.object(oi, "StreamMonitor", FakeMonitor), patch.object(oi, "_monitor", None):
            oi.get_obs_monitor()
        self.assertEqual(seen["spike"], 2.4)

    def test_pipeline_sources_apply_profile_and_pads(self):
        bot = (_repo_root / "Core" / "bot.py").read_text()
        wrap = (_repo_root / "Core" / "modules" / "Bolt_Wrap.py").read_text()
        self.assertIn("apply_game_profile(config", bot)
        self.assertIn('pad_before=float(config.get("pad_before"', bot)
        self.assertIn("apply_game_profile(cfg", wrap)
        self.assertIn("sensitivity=float(_sens)", wrap)


if __name__ == "__main__":
    unittest.main()
