#!/usr/bin/env python3
"""
Photo_OCR.py — photo / handwriting OCR → editable .txt (PARTIAL)
================================================================
Wraps ``scripts/ocr_to_editable.py`` (Apple Vision + Tesseract fallback)
with a soft-fail CLI: ``bolt photo-ocr``.

Soft-fail prefix: ``Photo OCR unavailable:``. Darwin/Vision or Tesseract
gated — stay PARTIAL (not stranger-ready). Distinct from READY ``bolt ocr``
(Video_Intelligence HUD OCR on clips).

Public API:
  status() / list_items() / try_run() / print_status() / main()
"""

from __future__ import annotations

import json
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Photo OCR unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "ocr_to_editable.py"
_DEFAULT_OUT_DIR = Path.home() / "Documents" / "Bolt OCR"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _vision_importable() -> bool:
    """Best-effort: can we import Apple Vision (pyobjc)?"""
    try:
        import Vision  # noqa: F401
        from Foundation import NSURL  # noqa: F401

        return True
    except Exception:
        return False


def _load_engine():
    """Import helpers from scripts/ocr_to_editable.py (add scripts dir to path)."""
    scripts_dir = str(_REPO / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    # Import as a plain module name so we don't conflict with a packages named scripts
    import importlib.util

    spec = importlib.util.spec_from_file_location("ocr_to_editable", _SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness for photo/handwriting OCR (PARTIAL — Darwin/Vision or Tesseract)."""
    try:
        darwin = platform.system() == "Darwin"
        script_ok = _SCRIPT.is_file()
        tess = bool(shutil.which("tesseract"))
        # Light Vision import: always best-effort on Darwin or when --probe
        vision_ok: Optional[bool] = None
        if probe or darwin:
            try:
                vision_ok = _vision_importable()
            except Exception:
                vision_ok = False

        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": True,
            "readiness": "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "darwin": darwin,
            "vision_importable": vision_ok,
            "tesseract_present": tess,
            "script_path": str(_SCRIPT),
            "script_present": script_ok,
            "default_out_dir": str(_DEFAULT_OUT_DIR),
            "cli": "bolt photo-ocr",
            "note": (
                "photo/handwriting OCR (Apple Vision → editable .txt); "
                "not bolt ocr (Video_Intelligence HUD on clips)"
            ),
            "is_stranger_ready": False,
            "probe": bool(probe),
            "error": "",
            "hint": "",
        }

        if not script_ok:
            out["error"] = _soft(f"engine missing ({_SCRIPT})")
            out["hint"] = out["error"]
            return out

        # Soft readiness: script present + (darwin with Vision OR tesseract on PATH).
        # Non-darwin without tesseract → soft-fail error.
        has_vision = bool(vision_ok)
        if darwin:
            engine_ok = has_vision or tess
            if not engine_ok:
                out["error"] = _soft(
                    "Vision not importable and tesseract not on PATH"
                )
                out["hint"] = out["error"]
                return out
        else:
            if not tess:
                out["error"] = _soft(
                    "not macOS and tesseract not on PATH (need Vision or tesseract)"
                )
                out["hint"] = out["error"]
                return out
            engine_ok = True

        out["ready"] = True
        engines = []
        if has_vision:
            engines.append("Vision")
        if tess:
            engines.append("tesseract")
        eng = " + ".join(engines) if engines else "engine"
        out["hint"] = (
            f"script ok · {eng} · out ~/Documents/Bolt OCR · "
            "photo/handwriting (not bolt ocr video HUD)"
        )
        return out
    except Exception as exc:
        return {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": True,
            "readiness": "PARTIAL",
            "soft_fail_prefix": _SOFT,
            "is_stranger_ready": False,
            "error": _soft(f"status failed ({exc})"),
            "hint": _soft(f"status failed ({exc})"),
        }


def list_items(*, as_json: bool = False) -> int:
    """Checklist of photo OCR pieces (no OCR run)."""
    try:
        info = status(probe=False)
        rows = [
            ("script ocr_to_editable.py", bool(info.get("script_present"))),
            ("platform_darwin", bool(info.get("darwin"))),
            ("Vision importable", bool(info.get("vision_importable"))),
            ("tesseract on PATH", bool(info.get("tesseract_present"))),
            (f"default out ({info.get('default_out_dir')})", True),
            ("soft-fail CLI (bolt photo-ocr)", True),
            ("distinct from bolt ocr (video HUD)", True),
            ("Darwin/Vision or Tesseract gated (stay PARTIAL)", True),
        ]
        if as_json:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "readiness": "PARTIAL",
                        "items": [{"name": n, "ok": ok} for n, ok in rows],
                        "hint": info.get("hint"),
                        "error": info.get("error"),
                    },
                    indent=2,
                )
            )
            return 0
        print("Photo OCR (PARTIAL — Darwin/Vision or Tesseract gated)")
        for name, ok in rows:
            mark = "OK" if ok else "--"
            print(f"  [{mark}] {name}")
        if info.get("hint"):
            print(f"  → {info['hint']}")
        print("  (run: bolt photo-ocr run <images…> [--open] [--stdout] [-o PATH])")
        return 0
    except Exception as exc:
        msg = _soft(f"list failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def try_run(
    images: List[str],
    *,
    open_file: bool = False,
    stdout: bool = False,
    output: Optional[str] = None,
    as_json: bool = False,
) -> int:
    """Soft-fail OCR on image paths via ocr_to_editable helpers (never raises)."""
    try:
        info = status(probe=False)
        if not info.get("script_present"):
            msg = info.get("error") or _soft("engine script missing")
            if as_json:
                print(json.dumps({"ok": False, "error": msg, "readiness": "PARTIAL"}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0
        if not info.get("ready"):
            msg = info.get("error") or _soft("Photo OCR tooling not ready")
            if as_json:
                print(json.dumps({"ok": False, "error": msg, "readiness": "PARTIAL"}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0

        paths = [str(p) for p in (images or []) if str(p).strip()]
        if not paths:
            msg = _soft("no images — pass JPG/HEIC/PNG files or a folder")
            if as_json:
                print(json.dumps({"ok": False, "error": msg, "readiness": "PARTIAL"}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0

        try:
            eng = _load_engine()
        except Exception as exc:
            msg = _soft(f"could not load ocr_to_editable ({exc})")
            if as_json:
                print(json.dumps({"ok": False, "error": msg, "readiness": "PARTIAL"}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0

        found = eng.collect_images(paths)
        if not found:
            msg = _soft("no images found. Pass JPG/HEIC/PNG files or a folder.")
            if as_json:
                print(json.dumps({"ok": False, "error": msg, "readiness": "PARTIAL"}, indent=2))
            else:
                print(msg, file=sys.stderr)
            return 0

        results = []
        for p in found:
            try:
                text, engine_name = eng.extract_text(p)
                results.append((p, text, engine_name))
            except Exception as exc:
                results.append((p, f"[could not read text: {exc}]", "none"))

        document = eng.format_document(results)
        engines_used = sorted({e for _, _, e in results})

        if stdout:
            if as_json:
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "readiness": "PARTIAL",
                            "images": [str(p) for p, _, _ in results],
                            "engines": engines_used,
                            "text": document,
                        },
                        indent=2,
                    )
                )
            else:
                sys.stdout.write(document)
            return 0

        dest = (
            Path(output).expanduser()
            if output
            else eng.default_output_path()
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(document, encoding="utf-8")
        if open_file:
            try:
                eng.open_in_editor(dest)
            except Exception:
                pass

        payload: Dict[str, Any] = {
            "ok": True,
            "readiness": "PARTIAL",
            "output": str(dest),
            "images": [str(p) for p, _, _ in results],
            "engines": engines_used,
            "opened": bool(open_file),
        }
        if as_json:
            print(json.dumps(payload, indent=2))
        else:
            print(dest)
            print(f"  images: {len(results)} · engines: {', '.join(engines_used)}")
        return 0
    except Exception as exc:
        msg = _soft(f"run failed ({exc})")
        if as_json:
            print(json.dumps({"ok": False, "error": msg, "readiness": "PARTIAL"}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    try:
        info = status(probe=probe)
        if as_json:
            print(json.dumps(info, indent=2, default=str))
            return 0
        print("Photo OCR readiness (PARTIAL)")
        print(f"  ready: {info.get('ready')}")
        print(f"  readiness: {info.get('readiness')}")
        print(
            f"  darwin: {info.get('darwin')} · Vision: {info.get('vision_importable')} · "
            f"tesseract: {info.get('tesseract_present')} · script: {info.get('script_present')}"
        )
        print(f"  out: {info.get('default_out_dir')}")
        print(f"  note: {info.get('note')}")
        print(f"  soft_fail_prefix: {info.get('soft_fail_prefix')}")
        if info.get("error"):
            print(f"  → {info['error']}")
        elif info.get("hint"):
            print(f"  → {info['hint']}")
        return 0
    except Exception as exc:
        msg = _soft(f"status print failed ({exc})")
        if as_json:
            print(json.dumps({"ready": False, "error": msg, "readiness": "PARTIAL"}, indent=2))
        else:
            print(msg, file=sys.stderr)
        return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt photo-ocr — photo/handwriting OCR → editable .txt (PARTIAL)

  bolt photo-ocr                                   # status (default)
  bolt photo-ocr status [--json] [--probe]
  bolt photo-ocr list [--json]
  bolt photo-ocr run <images…> [--open] [--stdout] [-o PATH] [--json]

Soft-fail: "Photo OCR unavailable:".
Darwin/Vision or Tesseract gated — stay PARTIAL.
Distinct from bolt ocr (Video_Intelligence HUD on clips).
Engine: scripts/ocr_to_editable.py
"""
        )
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    open_file = "--open" in args
    do_stdout = "--stdout" in args
    output: Optional[str] = None
    cleaned: List[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-o", "--output") and i + 1 < len(args):
            output = args[i + 1]
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        cleaned.append(a)
        i += 1

    if not cleaned:
        return print_status(as_json=json_out, probe=probe)

    cmd = cleaned[0].lower()
    if cmd in ("status", "check", "ready"):
        return print_status(as_json=json_out, probe=probe)
    if cmd in ("list", "ls", "channels", "checklist"):
        return list_items(as_json=json_out)
    if cmd in ("run", "ocr", "extract", "scan"):
        return try_run(
            cleaned[1:],
            open_file=open_file,
            stdout=do_stdout,
            output=output,
            as_json=json_out,
        )

    # Bare image paths → treat as run
    maybe_images = cleaned
    if any(
        Path(p).expanduser().exists()
        or "*" in p
        or Path(p).suffix.lower()
        in {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff", ".gif", ".bmp"}
        for p in maybe_images
    ):
        return try_run(
            maybe_images,
            open_file=open_file,
            stdout=do_stdout,
            output=output,
            as_json=json_out,
        )

    print(
        _soft(f"unknown command '{cmd}' — try status|list|run"),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
