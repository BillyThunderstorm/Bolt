"""Voice 3 is the alert voice — never a bare `say` without -v."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo / "Core"))

from modules import Bolt_Alerts as alerts
from modules import Bolt_Voice as voice


class Voice3AlertTests(unittest.TestCase):
    def test_macos_say_passes_voice_3(self):
        with patch.object(voice, "MUTED", False), patch.object(
            voice, "VOICE", "Voice 3"
        ), patch("modules.Bolt_Voice.subprocess.run") as run:
            run.return_value = None
            ok = voice.macos_say("Briefing is ready")
        self.assertTrue(ok)
        args = run.call_args[0][0]
        self.assertEqual(args[:4], ["say", "-v", "Voice 3", "-r"])
        self.assertIn("Briefing is ready", args)

    def test_banner_can_skip_speech(self):
        with patch.object(alerts, "_speak_alert") as speak, patch(
            "modules.Bolt_Alerts.subprocess.run"
        ) as run:
            run.return_value = type("R", (), {"returncode": 0})()
            alerts.mac_banner("Bolt", "hello", speak=False)
        speak.assert_not_called()


if __name__ == "__main__":
    unittest.main()
