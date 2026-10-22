#!/usr/bin/env python3
"""
ocr_to_editable.py — scan writing in photos into a .txt you can edit
====================================================================
Reads one or more image files (JPG/HEIC/PNG/WebP/TIFF), extracts text
with Apple Vision (handwriting + print), falling back to tesseract\n(HEIC/WebP converted with `sips`), and writes a UTF-8 .txt file.\nNever moves or deletes the source photos.

Usage:
  python3 scripts/ocr_to_editable.py photo1.jpg photo2.heic
  python3 scripts/ocr_to_editable.py --open ~/Desktop/*.jpg
  python3 scripts/ocr_to_editable.py --stdout image.png
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".heic",
    ".heif",
    ".webp",
    ".tif",
    ".tiff",
    ".gif",
    ".bmp",
}

DEFAULT_OUT_DIR = Path.home() / "Documents" / "Bolt OCR"


def _looks_like_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES


def collect_images(args: list[str]) -> list[Path]:
    found: list[Path] = []
    for raw in args:
        p = Path(raw).expanduser()
        if p.is_dir():
            for child in sorted(p.iterdir()):
                if _looks_like_image(child):
                    found.append(child)
        elif _looks_like_image(p):
            found.append(p)
    # de-dupe while keeping order
    seen = set()
    out = []
    for p in found:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def ocr_vision(path: Path) -> str:
    """Apple Vision — same Live Text engine, including handwriting."""
    import Vision
    from Foundation import NSURL

    url = NSURL.fileURLWithPath_(str(path.resolve()))
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    try:
        request.setAutomaticallyDetectsLanguage_(True)
    except Exception:
        try:
            request.setRecognitionLanguages_(["en-US"])
        except Exception:
            pass
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
    ok, err = handler.performRequests_error_([request], None)
    if not ok:
        raise RuntimeError(err or "Vision request failed")
    lines: list[str] = []
    for obs in request.results() or []:
        candidates = obs.topCandidates_(1)
        if not candidates:
            continue
        text = str(candidates[0].string() or "").rstrip()
        if text:
            lines.append(text)
    return "\n".join(lines).strip()


# Formats tesseract (Leptonica) can't read directly; convert with macOS `sips`.
_TESS_NEEDS_CONVERT = {".heic", ".heif", ".webp", ".gif"}


def vision_available() -> bool:
    """True when Apple Vision (pyobjc-framework-Vision) imports."""
    try:
        import Vision  # noqa: F401
        from Foundation import NSURL  # noqa: F401

        return True
    except Exception:
        return False


def tesseract_available() -> bool:
    return bool(shutil.which("tesseract"))


def convert_for_tesseract(path: Path, workdir: Path) -> Path:
    """Return a PNG copy tesseract can read (HEIC/WebP/GIF via `sips`).

    Never touches the source photo; the copy lives in ``workdir``.
    """
    if path.suffix.lower() not in _TESS_NEEDS_CONVERT:
        return path
    sips = shutil.which("sips") or "/usr/bin/sips"
    if not Path(sips).exists():
        raise RuntimeError(
            f"{path.suffix} needs converting but `sips` (macOS) is missing — "
            "convert the photo to JPG/PNG first"
        )
    dest = workdir / (path.stem + ".png")
    result = subprocess.run(
        [sips, "-s", "format", "png", str(path), "--out", str(dest)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not dest.is_file():
        err = (result.stderr or result.stdout or "sips failed").strip()
        raise RuntimeError(f"could not convert {path.name} to PNG: {err}")
    return dest


def ocr_tesseract(path: Path) -> str:
    if not tesseract_available():
        raise RuntimeError("tesseract not installed — fix: brew install tesseract")
    with tempfile.TemporaryDirectory(prefix="bolt-ocr-") as td:
        src = convert_for_tesseract(path, Path(td))
        result = subprocess.run(
            ["tesseract", str(src), "stdout", "--oem", "1", "--psm", "6"],
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "tesseract failed").strip()
        raise RuntimeError(err)
    return (result.stdout or "").strip()


def extract_text(path: Path, engine: str = "auto") -> tuple[str, str]:
    """Return (text, engine_name). engine: auto | vision | tesseract.

    auto: Apple Vision first (handwriting + HEIC native); if Vision is missing,
    errors or finds nothing, fall back to tesseract.
    """
    errors: list[str] = []
    vision_text = ""
    if engine in ("auto", "vision"):
        try:
            vision_text = ocr_vision(path)
            if vision_text or engine == "vision":
                return vision_text, "vision"
        except Exception as exc:
            errors.append(f"vision: {exc}")
            if engine == "vision":
                return f"[could not read text: vision: {exc}]", "none"
    if engine in ("auto", "tesseract"):
        try:
            text = ocr_tesseract(path)
            if text or not vision_text:
                return text, "tesseract"
        except Exception as exc:
            errors.append(f"tesseract: {exc}")
    if vision_text:
        return vision_text, "vision"
    if not errors:
        return "", "vision" if engine != "tesseract" else "tesseract"
    return f"[could not read text: {'; '.join(errors)}]", "none"


def format_document(results: list[tuple[Path, str, str]]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = [
        "Extracted text (editable copy)",
        f"Scanned: {now}",
        "Fix anything the OCR misread, then save.",
        "",
    ]
    for path, text, engine in results:
        parts.append("=" * 60)
        parts.append(f"Source: {path.name}")
        parts.append(f"Path:   {path}")
        parts.append(f"Engine: {engine}")
        parts.append("-" * 60)
        parts.append(text if text else "[no text found in this image]")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def default_output_path() -> Path:
    DEFAULT_OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    return DEFAULT_OUT_DIR / f"{stamp}_extracted.txt"


def open_in_editor(path: Path) -> None:
    # TextEdit: always editable. `open` alone may pick Preview for some types.
    subprocess.run(["open", "-e", str(path)], check=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="*", help="Image files or folders")
    parser.add_argument("-o", "--output", help="Output .txt path")
    parser.add_argument("--stdout", action="store_true", help="Print instead of writing")
    parser.add_argument("--open", action="store_true", dest="open_file", help="Open in TextEdit")
    args = parser.parse_args(argv)

    images = collect_images(args.images)
    if not images:
        print("No images found. Pass JPG/HEIC/PNG files or a folder.", file=sys.stderr)
        return 2

    results = [(p, *extract_text(p)) for p in images]
    document = format_document(results)

    if args.stdout:
        sys.stdout.write(document)
        return 0

    dest = Path(args.output).expanduser() if args.output else default_output_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(document, encoding="utf-8")
    print(dest)
    if args.open_file or os.environ.get("BOLT_OCR_OPEN") == "1":
        open_in_editor(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
