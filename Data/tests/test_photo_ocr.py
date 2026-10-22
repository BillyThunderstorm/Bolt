"""Tests for Core/modules/Photo_OCR.py (temp files only; never ~/Documents)."""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

_repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo / "Core"))

from modules import Photo_OCR as po  # noqa: E402


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = po.main(argv)
    return rc, out.getvalue(), err.getvalue()


class _FakeEngineMixin:
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.src = self.root / "photos"
        self.src.mkdir()
        self.out = self.root / "out"
        real = po._load_engine()
        self.calls = []

        def fake_extract(path, engine="auto"):
            self.calls.append((Path(path).name, engine))
            return f"text of {Path(path).name}", "vision"

        real.extract_text = fake_extract
        self.p_engine = patch.object(po, "_load_engine", return_value=real)
        self.p_status = patch.object(
            po, "status",
            return_value={"ready": True, "vision_importable": True, "tesseract_present": True},
        )
        self.p_engine.start()
        self.p_status.start()

    def tearDown(self):
        self.p_engine.stop()
        self.p_status.stop()
        self.td.cleanup()


class RunTests(_FakeEngineMixin, unittest.TestCase):
    def test_one_txt_per_photo_same_stem_and_source_untouched(self):
        a = self.src / "note.jpg"
        b = self.src / "list.heic"
        a.write_bytes(b"A")
        b.write_bytes(b"B")
        rc, out, _ = _run(["run", str(self.src), "-o", str(self.out)])
        self.assertEqual(rc, 0)
        self.assertIn("text of note.jpg", (self.out / "note.txt").read_text())
        self.assertIn("text of list.heic", (self.out / "list.txt").read_text())
        self.assertEqual(a.read_bytes(), b"A")
        self.assertEqual(b.read_bytes(), b"B")
        self.assertFalse(list(self.out.glob("*.part")))

    def test_skips_done_unless_force(self):
        (self.src / "note.png").write_bytes(b"x")
        _run(["run", str(self.src), "-o", str(self.out)])
        self.calls.clear()
        rc, out, _ = _run(["run", str(self.src), "-o", str(self.out), "--json"])
        data = json.loads(out)
        self.assertEqual(data["counts"]["skipped"], 1)
        self.assertEqual(self.calls, [])
        rc, out, _ = _run(["run", str(self.src), "-o", str(self.out), "--force", "--json"])
        self.assertEqual(json.loads(out)["counts"]["done"], 1)

    def test_same_stem_different_ext_do_not_collide(self):
        (self.src / "page.jpg").write_bytes(b"x")
        (self.src / "page.heic").write_bytes(b"y")
        _run(["run", str(self.src), "-o", str(self.out)])
        self.assertTrue((self.out / "page-jpg.txt").is_file())
        self.assertTrue((self.out / "page-heic.txt").is_file())

    def test_engine_flag_passed_through(self):
        (self.src / "n.png").write_bytes(b"x")
        _run(["run", str(self.src), "-o", str(self.out), "--engine", "tesseract"])
        self.assertEqual(self.calls, [("n.png", "tesseract")])

    def test_missing_file_soft_fails_with_rc1(self):
        rc, _, err = _run(["run", str(self.root / "nope.jpg")])
        self.assertEqual(rc, 1)
        self.assertIn(po._SOFT, err)


class StatusTests(unittest.TestCase):
    def test_no_engine_gives_exact_fix(self):
        with patch.object(po, "_vision_importable", return_value=False), \
             patch.object(po.shutil, "which", return_value=None), \
             patch.object(po.platform, "system", return_value="Darwin"):
            info = po.status()
        self.assertFalse(info["ready"])
        self.assertIn("pyobjc-framework-Vision", info["error"])
        self.assertIn("brew install tesseract", info["error"])

    def test_tesseract_only_is_ready(self):
        with patch.object(po, "_vision_importable", return_value=False), \
             patch.object(po.shutil, "which", return_value="/opt/homebrew/bin/tesseract"):
            info = po.status()
        self.assertTrue(info["ready"])
        self.assertEqual(info["readiness"], "READY")


@unittest.skipUnless(shutil.which("tesseract"), "tesseract not installed")
class LiveTesseractTest(unittest.TestCase):
    def test_png_roundtrip(self):
        try:
            from PIL import Image, ImageDraw, ImageFont
            font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 56)
        except Exception:
            self.skipTest("Pillow/Arial unavailable")
        with tempfile.TemporaryDirectory() as td:
            img = Image.new("RGB", (900, 160), "white")
            ImageDraw.Draw(img).text((30, 40), "Hello Bolt photo", fill="black", font=font)
            src = Path(td) / "hello.png"
            img.save(src)
            rc, _, _ = _run(["run", str(src), "-o", td + "/out", "--engine", "tesseract"])
            self.assertEqual(rc, 0)
            self.assertIn("Hello Bolt photo", (Path(td) / "out" / "hello.txt").read_text())


if __name__ == "__main__":
    unittest.main()
