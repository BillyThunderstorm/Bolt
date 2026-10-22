"""Tests for scripts/ocr_to_editable.py (no live Vision calls)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo / "scripts"))

import ocr_to_editable as ocr


class CollectImagesTests(unittest.TestCase):
    def test_collects_images_and_skips_other_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            jpg = root / "note.jpg"
            txt = root / "skip.txt"
            jpg.write_bytes(b"fake")
            txt.write_text("nope")
            found = ocr.collect_images([str(jpg), str(txt), str(root)])
            self.assertEqual(found, [jpg])


class FormatDocumentTests(unittest.TestCase):
    def test_includes_source_and_text(self):
        path = Path("/tmp/handwritten.heic")
        doc = ocr.format_document([(path, "buy snail mucin", "vision")])
        self.assertIn("handwritten.heic", doc)
        self.assertIn("buy snail mucin", doc)
        self.assertIn("Engine: vision", doc)


class MainTests(unittest.TestCase):
    def test_writes_editable_txt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            img = root / "page.png"
            img.write_bytes(b"x")
            dest = root / "out.txt"
            with patch.object(ocr, "extract_text", return_value=("hello from photo", "vision")):
                rc = ocr.main([str(img), "-o", str(dest)])
            self.assertEqual(rc, 0)
            text = dest.read_text(encoding="utf-8")
            self.assertIn("hello from photo", text)
            self.assertIn("page.png", text)

    def test_errors_when_no_images(self):
        self.assertEqual(ocr.main([]), 2)


class ExtractTextFallbackTests(unittest.TestCase):
    def test_falls_back_to_tesseract_when_vision_fails(self):
        with patch.object(ocr, "ocr_vision", side_effect=RuntimeError("no Vision")), \
             patch.object(ocr, "ocr_tesseract", return_value="from tess"):
            self.assertEqual(ocr.extract_text(Path("/tmp/x.png")), ("from tess", "tesseract"))

    def test_falls_back_when_vision_finds_nothing(self):
        with patch.object(ocr, "ocr_vision", return_value=""), \
             patch.object(ocr, "ocr_tesseract", return_value="tess text"):
            self.assertEqual(ocr.extract_text(Path("/tmp/x.png"))[1], "tesseract")

    def test_both_fail_reports_errors(self):
        with patch.object(ocr, "ocr_vision", side_effect=RuntimeError("v")), \
             patch.object(ocr, "ocr_tesseract", side_effect=RuntimeError("t")):
            text, eng = ocr.extract_text(Path("/tmp/x.png"))
        self.assertEqual(eng, "none")
        self.assertIn("could not read text", text)

    def test_png_not_converted(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "a.png"
            self.assertEqual(ocr.convert_for_tesseract(src, Path(td)), src)


if __name__ == "__main__":
    unittest.main()
