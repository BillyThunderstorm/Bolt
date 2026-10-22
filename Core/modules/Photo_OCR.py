#!/usr/bin/env python3
"""
Photo_OCR.py — photo / handwriting OCR → editable .txt (READY)
==============================================================
Wraps ``scripts/ocr_to_editable.py`` (Apple Vision first, Tesseract fallback)
with a soft-fail CLI: ``bolt photo-ocr``.

``bolt photo-ocr run <photo or folder>`` writes one editable ``<stem>.txt`` per
photo into ``~/Documents/Bolt OCR`` (or ``-o DIR``). JPG/PNG/HEIC/WebP/TIFF;
HEIC goes to Vision natively and is converted with ``sips`` for tesseract.
Photos already done are skipped unless ``--force``. Source photos are never
moved, changed or deleted.

Soft-fail prefix: ``Photo OCR unavailable:`` (always with the exact fix).
Distinct from READY ``bolt ocr`` (Video_Intelligence HUD OCR on clips).

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

FIX_VISION = "uv pip install --python .venv/bin/python pyobjc-framework-Vision"
FIX_TESSERACT = "brew install tesseract"
_ENGINES = ("auto", "vision", "tesseract")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _soft(msg: str) -> str:
    if msg.startswith(_SOFT):
        return msg
    return f"{_SOFT} {msg}"


def _vision_importable() -> bool:
    """Best-effort: can we import Apple Vision (pyobjc-framework-Vision)?"""
    try:
        import Vision  # noqa: F401
        from Foundation import NSURL  # noqa: F401

        return True
    except Exception:
        return False


def _load_engine():
    """Import scripts/ocr_to_editable.py as a module."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("ocr_to_editable", _SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def status(*, probe: bool = False) -> Dict[str, Any]:
    """Readiness for photo/handwriting OCR (Vision and/or tesseract)."""
    try:
        darwin = platform.system() == "Darwin"
        script_ok = _SCRIPT.is_file()
        tess = bool(shutil.which("tesseract"))
        vision_ok = _vision_importable() if (darwin or probe) else False
        out: Dict[str, Any] = {
            "checked_at": _utc_now(),
            "ready": False,
            "partial": False,
            "readiness": "READY",
            "soft_fail_prefix": _SOFT,
            "darwin": darwin,
            "vision_importable": vision_ok,
            "tesseract_present": tess,
            "sips_present": bool(shutil.which("sips")),
            "script_path": str(_SCRIPT),
            "script_present": script_ok,
            "default_out_dir": str(_DEFAULT_OUT_DIR),
            "cli": "bolt photo-ocr",
            "note": (
                "photo/handwriting OCR → one editable .txt per photo; "
                "not bolt ocr (Video_Intelligence HUD on clips)"
            ),
            "probe": bool(probe),
            "engines": [],
            "fixes": [],
            "error": "",
            "hint": "",
        }
        if not script_ok:
            out["error"] = _soft(f"engine missing ({_SCRIPT}) — restore scripts/ocr_to_editable.py")
            out["hint"] = out["error"]
            return out

        engines = (["vision"] if vision_ok else []) + (["tesseract"] if tess else [])
        out["engines"] = engines
        fixes = []
        if darwin and not vision_ok:
            fixes.append(f"Apple Vision (best for handwriting): {FIX_VISION}")
        if not tess:
            fixes.append(f"tesseract fallback: {FIX_TESSERACT}")
        out["fixes"] = fixes
        if not engines:
            fix = FIX_VISION if darwin else FIX_TESSERACT
            out["error"] = _soft(f"no OCR engine — fix: {fix}" + (f" (or {FIX_TESSERACT})" if darwin else ""))
            out["hint"] = out["error"]
            return out

        out["ready"] = True
        out["hint"] = (
            f"{' + '.join(engines)} · out ~/Documents/Bolt OCR · "
            "run: bolt photo-ocr run <photo or folder>"
        )
        return out
    except Exception as exc:
        return {
            "checked_at": _utc_now(),
            "ready": False,
            "readiness": "READY",
            "soft_fail_prefix": _SOFT,
            "error": _soft(f"status failed ({exc})"),
            "hint": _soft(f"status failed ({exc})"),
        }


def list_items(*, as_json: bool = False) -> int:
    """Checklist of photo OCR pieces (no OCR run)."""
    try:
        info = status(probe=False)
        rows = [
            ("script ocr_to_editable.py", bool(info.get("script_present"))),
            ("macOS", bool(info.get("darwin"))),
            ("Apple Vision (pyobjc-framework-Vision)", bool(info.get("vision_importable"))),
            ("tesseract on PATH", bool(info.get("tesseract_present"))),
            ("sips (HEIC → PNG for tesseract)", bool(info.get("sips_present"))),
            (f"out folder ({info.get('default_out_dir')})", True),
        ]
        if as_json:
            print(json.dumps({
                "ok": True,
                "readiness": "READY",
                "items": [{"name": n, "ok": ok} for n, ok in rows],
                "fixes": info.get("fixes", []),
                "hint": info.get("hint"),
                "error": info.get("error"),
            }, indent=2))
            return 0
        print("Photo OCR checklist")
        for name, ok in rows:
            print(f"  [{'OK' if ok else '--'}] {name}")
        for fix in info.get("fixes", []):
            print(f"  fix: {fix}")
        if info.get("error") or info.get("hint"):
            print(f"  → {info.get('error') or info.get('hint')}")
        print("  (run: bolt photo-ocr run <photo or folder> [--force] [-o DIR] [--open])")
        return 0
    except Exception as exc:
        msg = _soft(f"list failed ({exc})")
        print(json.dumps({"ok": False, "error": msg}, indent=2) if as_json else msg,
              file=sys.stdout if as_json else sys.stderr)
        return 0


def _fail(msg: str, as_json: bool) -> int:
    msg = _soft(msg)
    if as_json:
        print(json.dumps({"ok": False, "error": msg, "readiness": "READY"}, indent=2))
    else:
        print(msg, file=sys.stderr)
    return 1


def _out_names(found: List[Path]) -> Dict[Path, str]:
    """<stem>.txt per photo; same stem twice in one batch → <stem>-<ext>.txt."""
    counts: Dict[str, int] = {}
    for p in found:
        counts[p.stem.lower()] = counts.get(p.stem.lower(), 0) + 1
    names: Dict[Path, str] = {}
    for p in found:
        if counts[p.stem.lower()] > 1:
            names[p] = f"{p.stem}-{p.suffix.lstrip('.').lower()}.txt"
        else:
            names[p] = f"{p.stem}.txt"
    return names


def try_run(
    images: List[str],
    *,
    open_file: bool = False,
    stdout: bool = False,
    output: Optional[str] = None,
    as_json: bool = False,
    force: bool = False,
    engine: str = "auto",
) -> int:
    """OCR photos → one editable <stem>.txt each. Soft-fail; never raises.

    Returns 0 on success (including "all skipped"), 1 on a soft failure.
    """
    try:
        if engine not in _ENGINES:
            return _fail(f"unknown engine '{engine}' — use auto, vision or tesseract", as_json)
        info = status(probe=False)
        if not info.get("ready"):
            return _fail(info.get("error") or "Photo OCR tooling not ready", as_json)
        if engine == "vision" and not info.get("vision_importable"):
            return _fail(f"Apple Vision not installed — fix: {FIX_VISION}", as_json)
        if engine == "tesseract" and not info.get("tesseract_present"):
            return _fail(f"tesseract not installed — fix: {FIX_TESSERACT}", as_json)

        paths = [str(p) for p in (images or []) if str(p).strip()]
        if not paths:
            return _fail("no images — pass JPG/HEIC/PNG files or a folder", as_json)
        missing = [p for p in paths if not Path(p).expanduser().exists()]
        try:
            eng = _load_engine()
        except Exception as exc:
            return _fail(f"could not load ocr_to_editable ({exc})", as_json)
        found = eng.collect_images(paths)
        if not found:
            extra = f" (not found: {', '.join(missing)})" if missing else ""
            return _fail(f"no images found{extra}. Pass JPG/HEIC/PNG files or a folder.", as_json)

        # --stdout: print text only, write nothing.
        if stdout:
            results = [(p, *eng.extract_text(p, engine)) for p in found]
            document = eng.format_document(results)
            if as_json:
                print(json.dumps({
                    "ok": True, "readiness": "READY",
                    "images": [str(p) for p, _, _ in results],
                    "engines": sorted({e for _, _, e in results}),
                    "text": document,
                }, indent=2))
            else:
                sys.stdout.write(document)
            return 0

        # -o: a folder (default), or a single .txt file when one photo is given.
        single_file: Optional[Path] = None
        out_dir = _DEFAULT_OUT_DIR
        if output:
            o = Path(output).expanduser()
            if o.suffix.lower() == ".txt" and len(found) == 1:
                single_file = o
                out_dir = o.parent
            else:
                out_dir = o
        out_dir.mkdir(parents=True, exist_ok=True)
        names = _out_names(found)

        rows: List[Dict[str, Any]] = []
        for p in found:
            dest = single_file or (out_dir / names[p])
            row: Dict[str, Any] = {"image": str(p), "output": str(dest)}
            if dest.exists() and not force:
                row.update(status="skipped", reason="already done (use --force to redo)")
                rows.append(row)
                continue
            text, used = eng.extract_text(p, engine)
            failed = used == "none"
            row.update(
                engine=used,
                chars=0 if failed else len(text),
                status="failed" if failed else ("empty" if not text else "done"),
            )
            if failed:
                row["error"] = text
            else:
                tmp = dest.with_name(dest.name + ".part")
                tmp.write_text(eng.format_document([(p, text, used)]), encoding="utf-8")
                tmp.replace(dest)
            rows.append(row)

        done = [r for r in rows if r["status"] in ("done", "empty")]
        if open_file:
            for r in done:
                try:
                    eng.open_in_editor(Path(r["output"]))
                except Exception:
                    pass
        counts = {k: sum(1 for r in rows if r["status"] == k) for k in ("done", "empty", "skipped", "failed")}
        ok = counts["failed"] == 0
        if as_json:
            print(json.dumps({
                "ok": ok, "readiness": "READY", "out_dir": str(out_dir),
                "counts": counts, "results": rows, "opened": bool(open_file and done),
            }, indent=2))
        else:
            for r in rows:
                name = Path(r["image"]).name
                if r["status"] == "skipped":
                    print(f"  skip  {name} → {r['output']} (already done; --force to redo)")
                elif r["status"] == "failed":
                    print(f"  FAIL  {name}: {r.get('error')}")
                else:
                    note = " (no text found)" if r["status"] == "empty" else f" ({r['chars']} chars)"
                    print(f"  done  {name} → {r['output']} [{r['engine']}]{note}")
            print(
                f"Photo OCR: {counts['done'] + counts['empty']} written · "
                f"{counts['skipped']} skipped · {counts['failed']} failed · out {out_dir}"
            )
        return 0 if ok else 1
    except Exception as exc:
        return _fail(f"run failed ({exc})", as_json)


def print_status(*, as_json: bool = False, probe: bool = False) -> int:
    try:
        info = status(probe=probe)
        if as_json:
            print(json.dumps(info, indent=2, default=str))
            return 0
        print(f"bolt photo-ocr: READY · {'ready' if info.get('ready') else 'not ready'}")
        print(
            f"  Vision: {info.get('vision_importable')} · tesseract: {info.get('tesseract_present')} · "
            f"sips: {info.get('sips_present')} · script: {info.get('script_present')}"
        )
        print(f"  out: {info.get('default_out_dir')}")
        print(f"  note: {info.get('note')}")
        for fix in info.get("fixes", []):
            print(f"  optional fix: {fix}")
        print(f"  → {info.get('error') or info.get('hint')}")
        return 0
    except Exception as exc:
        print(_soft(f"status print failed ({exc})"), file=sys.stderr)
        return 0


_HELP = """bolt photo-ocr — photo/handwriting OCR → editable .txt (READY)

  bolt photo-ocr                          # status (default)
  bolt photo-ocr status [--json] [--probe]
  bolt photo-ocr list [--json]
  bolt photo-ocr run <photos or folder> [--force] [-o DIR|FILE.txt]
                     [--engine auto|vision|tesseract] [--open] [--stdout] [--json]

One <stem>.txt per photo in ~/Documents/Bolt OCR. JPG/PNG/HEIC/WebP/TIFF.
Already-done photos are skipped unless --force. Source photos are never moved
or deleted. Apple Vision first (handwriting), tesseract fallback.
Soft-fail: "Photo OCR unavailable:" with the exact fix.
Distinct from bolt ocr (Video_Intelligence HUD on clips).
"""


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(_HELP)
        return 0

    json_out = "--json" in args
    probe = "--probe" in args
    open_file = "--open" in args
    do_stdout = "--stdout" in args
    force = "--force" in args or "-f" in args
    output: Optional[str] = None
    engine = "auto"
    cleaned: List[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-o", "--output", "--out") and i + 1 < len(args):
            output = args[i + 1]
            i += 2
            continue
        if a == "--engine" and i + 1 < len(args):
            engine = args[i + 1].lower()
            i += 2
            continue
        if a.startswith("--engine="):
            engine = a.split("=", 1)[1].lower()
            i += 1
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
    kw = dict(open_file=open_file, stdout=do_stdout, output=output,
              as_json=json_out, force=force, engine=engine)
    if cmd in ("run", "ocr", "extract", "scan"):
        return try_run(cleaned[1:], **kw)

    # Bare image paths → treat as run
    if any(
        Path(p).expanduser().exists()
        or Path(p).suffix.lower()
        in {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff", ".gif", ".bmp"}
        for p in cleaned
    ):
        return try_run(cleaned, **kw)

    print(_soft(f"unknown command '{cmd}' — try status|list|run"), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
