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


if __name__ == "__main__":
    unittest.main()
