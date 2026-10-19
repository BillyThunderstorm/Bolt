#!/usr/bin/env python3
"""
Bolt_Wrap.py — one-command post-stream wrap-up (READY; soft-fail)
===================================================================
``bolt wrap`` after a stream:

  1. Find the latest VOD (``--vod`` or newest video in Core/config.json
     ``recordings_folder`` [media/Recordings], ``wrap_vod_dirs`` (optional list),
     and ``vod_samples/``).
  2. Audio highlights via Highlight_Detector (same engine as bot.py).
  3. Motion scores via Motion_Detector (if numpy + ffmpeg/opencv); merged into
     the ranking (70% audio / 30% motion); audio peaks first, then strong
     motion-only windows fill the remaining slots.
  4. Cut the top N clips via Clip_Generator (config pad_before / pad_after).
  5. Captions: Subtitle_Generator (Whisper) → .srt + Clip_Factory drawtext
     burn-in → ``*_captioned.mp4``. Whisper = venv module or the Mac's
     ``whisper`` CLI; neither = skipped with a clear note.
  6. Stitch a highlight reel (ffmpeg concat).
  7. Write everything to ``media/output/wraps/YYYY-MM-DD_<vod>_wrap/`` with
     ``wrap.json`` + ``WRAP.md`` and apply Finder tags (media = Purple; the
     report = Blue) via the built-in ``xattr`` (or ``tag`` CLI if installed).

CLI (via ``bolt wrap``):
  run [--vod FILE] [--top N] [--dry-run] [--no-motion] [--no-captions]
      [--no-reel] [--out DIR] [--json]          (bare ``bolt wrap`` = run)
  status [--json]
  list   [--json]                                (past wraps)

Never deletes or moves the source VOD. Never posts anything.
Soft-fail prefix: ``Wrap unavailable:``.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Wrap unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_CORE = _REPO / "Core"
_CONFIG = _CORE / "config.json"
_WRAPS = _REPO / "media" / "output" / "wraps"
_VIDEO_EXT = {".mp4", ".mkv", ".mov", ".flv", ".m4v", ".ts"}

# Bolt Finder colour convention (Docs: red Bolt, yellow code, orange data,
# green scripts, blue docs, purple media, gray vendors). Finder label numbers.
FINDER_TAGS = {
    "Red": 6, "Yellow": 5, "Orange": 7, "Green": 2,
    "Blue": 4, "Purple": 3, "Gray": 1,
}


def _soft(msg: str) -> str:
    return msg if msg.startswith(_SOFT) else f"{_SOFT} {msg}"


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_core() -> None:
    if str(_CORE) not in sys.path:
        sys.path.insert(0, str(_CORE))


def _config() -> Dict[str, Any]:
    try:
        d = json.loads(_CONFIG.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _ffmpeg() -> Optional[str]:
    try:
        _ensure_core()
        from modules.FFmpeg_Bin import working_ffmpeg

        return working_ffmpeg()
    except Exception:
        return None


def _has(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except Exception:
        return False


# ── Finder tags ─────────────────────────────────────────────────────────────

def tag_tool() -> Optional[str]:
    if platform.system() != "Darwin":
        return None
    if shutil.which("tag"):
        return "tag"
    if shutil.which("xattr"):
        return "xattr"
    return None


def apply_finder_tag(path: Path, color: str = "Purple") -> bool:
    """Set a Finder colour tag (replaces existing tags on that file). Soft."""
    tool = tag_tool()
    if not tool or color not in FINDER_TAGS:
        return False
    try:
        if tool == "tag":
            r = subprocess.run(["tag", "--set", color, str(path)], capture_output=True, timeout=10)
            return r.returncode == 0
        data = plistlib.dumps([f"{color}\n{FINDER_TAGS[color]}"], fmt=plistlib.FMT_BINARY)
        r = subprocess.run(
            ["xattr", "-wx", "com.apple.metadata:_kMDItemUserTags", data.hex(), str(path)],
            capture_output=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


# ── VOD discovery ───────────────────────────────────────────────────────────

def vod_dirs() -> List[Path]:
    cfg = _config()
    dirs: List[Path] = []
    rec = cfg.get("recordings_folder") or "media/Recordings"
    for d in [rec, *(cfg.get("wrap_vod_dirs") or []), "vod_samples"]:
        p = Path(os.path.expanduser(str(d)))
        if not p.is_absolute():
            p = _REPO / p
        if p not in dirs:
            dirs.append(p)
    return dirs


def find_vods(limit: int = 10) -> List[Path]:
    found: List[Path] = []
    for d in vod_dirs():
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.is_file() and f.suffix.lower() in _VIDEO_EXT and not f.name.startswith("."):
                found.append(f)
    found.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return found[:limit]


def latest_vod() -> Optional[Path]:
    v = find_vods(1)
    return v[0] if v else None


def _duration(path: Path) -> float:
    try:
        _ensure_core()
        from modules.FFmpeg_Bin import ffprobe_bin

        r = subprocess.run(
            [ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _safe(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in "-_" else "-" for c in name)
    while "--" in keep:
        keep = keep.replace("--", "-")
    return keep.strip("-")[:60] or "vod"


def wrap_dir_for(vod: Path, base: Optional[Path] = None) -> Path:
    day = datetime.now().strftime("%Y-%m-%d")
    root = base or _WRAPS
    d = root / f"{day}_{_safe(vod.stem)}_wrap"
    n = 2
    while d.exists():
        d = root / f"{day}_{_safe(vod.stem)}_wrap-{n}"
        n += 1
    return d


# ── status ──────────────────────────────────────────────────────────────────

def status() -> Dict[str, Any]:
    ff = _ffmpeg()
    vod = latest_vod()
    try:
        _ensure_core()
        from modules.Subtitle_Generator import whisper_backend

        backend = whisper_backend()
    except Exception:
        backend = "module" if _has("whisper") else None
    whisper = backend is not None
    try:
        _ensure_core()
        from modules.Motion_Detector import status as _ms

        motion = _ms()
    except Exception as exc:
        motion = {"ready": False, "error": str(exc)}
    info = {
        "checked_at": _iso(),
        "readiness": "READY",
        "ready": bool(ff and vod),
        "ffmpeg": ff,
        "vod_dirs": [str(d) for d in vod_dirs()],
        "latest_vod": str(vod) if vod else None,
        "latest_vod_mtime": (datetime.fromtimestamp(vod.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                             if vod else None),
        "highlights_engine": _has("numpy"),
        "motion_ready": bool(motion.get("ready")),
        "captions_ready": whisper,
        "captions_backend": backend,
        "captions_hint": "" if whisper else ("Whisper not found → captions skipped "
                                             "(uv sync --extra subtitles, or pip3 install openai-whisper)"),
        "finder_tag_tool": tag_tool(),
        "wraps_dir": str(_WRAPS),
        "soft_fail_prefix": _SOFT,
        "error": "",
    }
    if not ff:
        info["error"] = _soft("no working ffmpeg (brew reinstall ffmpeg-full)")
    elif not vod:
        info["error"] = _soft(f"no VOD found in {', '.join(info['vod_dirs'])}")
    return info


# ── pipeline ────────────────────────────────────────────────────────────────

def _rank(events, motion_rep, top: int, vod_len: float) -> List[Dict[str, Any]]:
    """Merge audio events + motion windows into ranked candidate peaks."""
    from modules.Motion_Detector import score_at

    cands: List[Dict[str, Any]] = []
    for e in events:
        audio = float(getattr(e, "score", 0.0) or 0.0)
        mot = score_at(motion_rep, e.timestamp) if motion_rep else None
        combined = audio if mot is None else 0.7 * audio + 0.3 * mot
        cands.append({"t": float(e.timestamp), "trigger": getattr(e, "trigger", "audio_spike"),
                      "audio": round(audio, 1), "motion": mot, "score": round(combined, 1)})
    if motion_rep:
        for seg in motion_rep.get("segments") or []:
            if seg["score"] < 60:
                continue
            if any(abs(c["t"] - seg["peak"]) < 15 for c in cands):
                continue
            cands.append({"t": float(seg["peak"]), "trigger": "motion", "audio": None,
                          "motion": seg["score"], "score": round(0.6 * seg["score"], 1)})
    # Audio peaks are Bolt's proven signal (already thresholded by the detector):
    # rank them first by combined score, then fill spare slots with motion-only.
    cands.sort(key=lambda c: (c["trigger"] == "motion", -c["score"]))
    picked: List[Dict[str, Any]] = []
    for c in cands:
        if len(picked) >= top:
            break
        if all(abs(c["t"] - p["t"]) >= 20 for p in picked) and 0 <= c["t"] <= (vod_len or 1e12):
            picked.append(c)
    picked.sort(key=lambda c: c["t"])
    return picked


def _burn_captions(ff: str, clip: Path, out_dir: Path, model: str) -> Dict[str, Any]:
    from modules.Subtitle_Generator import generate_subtitles_with_timestamps, write_srt
    from modules.Clip_Factory import build_caption_drawtext_filter

    segs, _ = generate_subtitles_with_timestamps(str(clip), model_size=model)
    if not segs:
        return {"ok": False, "note": "no speech segments"}
    srt = write_srt(str(clip), segs, str(out_dir / (clip.stem + ".srt")))
    vf = build_caption_drawtext_filter(segs)
    if not vf:
        return {"ok": False, "srt": srt, "note": "no caption text"}
    out = out_dir / f"{clip.stem}_captioned.mp4"
    r = subprocess.run(
        [ff, "-y", "-v", "error", "-i", str(clip), "-vf", vf, "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "20", "-c:a", "copy", str(out)],
        capture_output=True, text=True, timeout=900,
    )
    if r.returncode != 0:
        return {"ok": False, "srt": srt, "note": f"drawtext failed: {r.stderr[-200:]}"}
    return {"ok": True, "srt": srt, "captioned": str(out)}


def _concat(ff: str, clips: List[Path], out: Path) -> Optional[str]:
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{c.resolve().as_posix()}'\n" for c in clips), encoding="utf-8")
    try:
        r = subprocess.run([ff, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-c", "copy", "-movflags", "+faststart", str(out)],
                           capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            r = subprocess.run([ff, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac",
                                str(out)], capture_output=True, text=True, timeout=1800)
        return None if r.returncode == 0 else (r.stderr or "concat failed")[-200:]
    finally:
        try:
            lst.unlink()
        except OSError:
            pass


def run(*, vod: Optional[str] = None, top: int = 5, dry_run: bool = False,
        motion: bool = True, captions: bool = True, reel: bool = True,
        out: Optional[str] = None, log=print) -> Dict[str, Any]:
    t_start = time.time()
    res: Dict[str, Any] = {"ok": False, "dry_run": dry_run, "steps": [], "warnings": []}
    st = status()
    ff = st["ffmpeg"]
    src = Path(vod).expanduser() if vod else latest_vod()
    if not src or not src.is_file():
        res["error"] = _soft(f"VOD not found: {vod}" if vod else st["error"] or "no VOD found")
        return res
    if not ff:
        res["error"] = st["error"]
        return res
    vlen = _duration(src)
    folder = Path(out).expanduser() if out else wrap_dir_for(src)
    cfg = _config()
    pad_b = float(cfg.get("pad_before", 12.0))
    pad_a = float(cfg.get("pad_after", 20.0))
    res.update({"vod": str(src), "vod_duration_s": round(vlen, 1), "output_dir": str(folder),
                "plan": {
                    "highlights": "Highlight_Detector (audio)",
                    "motion": ("Motion_Detector" + (" --fast (keyframes)" if vlen > 1200 else ""))
                    if motion and st["motion_ready"] else "skipped",
                    "clips": f"top {top} via Clip_Generator (pad {pad_b}s/{pad_a}s)",
                    "captions": "Whisper + drawtext" if captions and st["captions_ready"]
                    else ("skipped (--no-captions)" if not captions else "skipped — Whisper not installed"),
                    "reel": "ffmpeg concat" if reel else "skipped",
                    "finder_tags": f"Purple media / Blue report via {st['finder_tag_tool']}"
                    if st["finder_tag_tool"] else "skipped (no xattr/tag)",
                }})
    log(f"[wrap] VOD: {src} ({vlen / 60:.1f} min)")
    log(f"[wrap] output: {folder}")
    if dry_run:
        for k, v in res["plan"].items():
            log(f"  plan {k:<11} {v}")
        res["ok"] = True
        return res

    _ensure_core()
    clips_dir = folder / "clips"
    cap_dir = folder / "captions"
    clips_dir.mkdir(parents=True, exist_ok=True)

    # 1) audio highlights
    try:
        from modules.Highlight_Detector import detect_highlights

        events = detect_highlights(str(src))
        res["steps"].append({"step": "highlights", "ok": True, "events": len(events)})
        log(f"[wrap] audio highlights: {len(events)}")
    except Exception as exc:
        events = []
        res["steps"].append({"step": "highlights", "ok": False, "error": str(exc)})
        res["warnings"].append(f"highlights failed: {exc}")

    # 2) motion
    motion_rep = None
    if motion and st["motion_ready"]:
        try:
            from modules.Motion_Detector import analyze

            motion_rep = analyze(str(src), fast=vlen > 1200, top=max(10, top * 2))
            (folder / "motion.json").write_text(json.dumps(motion_rep, indent=2) + "\n", encoding="utf-8")
            res["steps"].append({"step": "motion", "ok": True,
                                 "segments": len(motion_rep["segments"]),
                                 "backend": motion_rep["backend"]})
            log(f"[wrap] motion windows: {len(motion_rep['segments'])}")
        except Exception as exc:
            res["steps"].append({"step": "motion", "ok": False, "error": str(exc)})
            res["warnings"].append(f"motion skipped: {exc}")
    elif motion:
        res["warnings"].append("motion skipped: Motion_Detector not ready (bolt motion status)")

    # 3) rank + cut
    picks = _rank(events, motion_rep, top, vlen)
    res["candidates"] = picks
    clips: List[Path] = []
    if picks:
        from modules.Clip_Generator import generate_clips
        from modules.Highlight_Detector import HighlightEvent

        evs = [HighlightEvent(timestamp=c["t"], type=c["trigger"], confidence=c["score"] / 100.0,
                              score=c["score"]) for c in picks]
        try:
            gen = generate_clips(str(src), evs, output_dir=str(clips_dir), pad_before=pad_b,
                                 pad_after=pad_a, min_duration=float(cfg.get("min_clip_duration", 5) or 5),
                                 max_duration=float(cfg.get("max_clip_duration", 120) or 120))
            clips = [Path(g.output_file) for g in gen if g.success and Path(g.output_file).is_file()]
            fails = [g.error for g in gen if not g.success]
            res["steps"].append({"step": "clips", "ok": bool(clips), "count": len(clips), "errors": fails})
            log(f"[wrap] clips cut: {len(clips)}")
        except Exception as exc:
            res["steps"].append({"step": "clips", "ok": False, "error": str(exc)})
            res["warnings"].append(f"clip cutting failed: {exc}")
    else:
        res["warnings"].append("no highlight candidates (quiet VOD?) — nothing to cut")

    # 4) captions
    res["captions"] = []
    if captions and clips:
        if st["captions_ready"]:
            cap_dir.mkdir(exist_ok=True)
            model = str(cfg.get("whisper_model") or "base")
            for c in clips:
                try:
                    res["captions"].append({"clip": c.name, **_burn_captions(ff, c, cap_dir, model)})
                except Exception as exc:
                    res["captions"].append({"clip": c.name, "ok": False, "note": str(exc)})
            res["steps"].append({"step": "captions", "ok": any(x.get("ok") for x in res["captions"]),
                                 "backend": st.get("captions_backend"),
                                 "burned": sum(1 for x in res["captions"] if x.get("ok"))})
        else:
            res["warnings"].append("captions skipped: Whisper not found (uv sync --extra subtitles, "
                                   "or pip3 install openai-whisper)")
            res["steps"].append({"step": "captions", "ok": False, "skipped": "whisper missing"})

    # 5) reel
    reel_path = None
    if reel and len(clips) >= 2:
        reel_path = folder / f"{folder.name.replace('_wrap', '')}_highlight_reel.mp4"
        err = _concat(ff, clips, reel_path)
        res["steps"].append({"step": "reel", "ok": err is None, "error": err})
        if err:
            res["warnings"].append(f"reel failed: {err}")
            reel_path = None
        else:
            log(f"[wrap] reel: {reel_path.name}")

    # 6) report + tags
    res["clips"] = [str(c) for c in clips]
    res["reel"] = str(reel_path) if reel_path else None
    res["finished_at"] = _iso()
    res["elapsed_s"] = round(time.time() - t_start, 1)
    res["ok"] = bool(clips)
    (folder / "wrap.json").write_text(json.dumps(res, indent=2, default=str) + "\n", encoding="utf-8")
    md = [f"# Stream wrap — {src.name}", "",
          f"- VOD: `{src}` ({vlen / 60:.1f} min)",
          f"- Wrapped: {datetime.now().strftime('%Y-%m-%d %I:%M %p')} (local)",
          f"- Clips: {len(clips)}" + (f" · Reel: `{reel_path.name}`" if reel_path else ""), "",
          "| # | Time | Trigger | Audio | Motion | Score |", "|---|---|---|---|---|---|"]
    for i, c in enumerate(picks, 1):
        tt = int(c["t"])
        md.append(f"| {i} | {tt // 3600}:{(tt % 3600) // 60:02d}:{tt % 60:02d} | {c['trigger']} | "
                  f"{c['audio'] if c['audio'] is not None else '-'} | "
                  f"{c['motion'] if c['motion'] is not None else '-'} | {c['score']} |")
    if res["warnings"]:
        md += ["", "## Warnings", *[f"- {w}" for w in res["warnings"]]]
    md += ["", "Nothing was posted. Review clips, then `bolt queue` / `bolt multi plan` as usual."]
    (folder / "WRAP.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    tagged = 0
    if tag_tool():
        for f in folder.rglob("*"):
            if f.suffix.lower() in _VIDEO_EXT:
                tagged += apply_finder_tag(f, "Purple")
            elif f.suffix.lower() in (".md", ".srt"):
                tagged += apply_finder_tag(f, "Blue")
            elif f.suffix.lower() == ".json":
                tagged += apply_finder_tag(f, "Orange")
        tagged += apply_finder_tag(folder, "Purple")
    res["finder_tagged"] = tagged
    (folder / "wrap.json").write_text(json.dumps(res, indent=2, default=str) + "\n", encoding="utf-8")
    log(f"[wrap] done in {res['elapsed_s']}s · tagged {tagged} item(s) · {folder / 'WRAP.md'}")
    return res


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(prog="bolt wrap", description="Post-stream wrap (READY; soft-fail)")
    p.add_argument("action", nargs="?", default="run", choices=["run", "status", "list"])
    p.add_argument("--vod", default=None)
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-motion", action="store_true")
    p.add_argument("--no-captions", action="store_true")
    p.add_argument("--no-reel", action="store_true")
    p.add_argument("--out", default=None)
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    try:
        if a.action == "status":
            st = status()
            if a.json:
                print(json.dumps(st, indent=2))
            else:
                print(f"wrap readiness: READY  ready={'yes' if st['ready'] else 'no'}")
                print(f"  latest VOD: {st['latest_vod']}  ({st['latest_vod_mtime']})")
                print(f"  ffmpeg={st['ffmpeg']}  motion={st['motion_ready']}  captions={st['captions_ready']} ({st.get('captions_backend') or 'none'})  "
                      f"tags={st['finder_tag_tool']}")
                if st["captions_hint"]:
                    print(f"  {st['captions_hint']}")
                print(f"  wraps: {st['wraps_dir']}")
                if st["error"]:
                    print(f"  {st['error']}")
            return 0
        if a.action == "list":
            ws = sorted([d for d in _WRAPS.glob("*_wrap*") if d.is_dir()], reverse=True) if _WRAPS.is_dir() else []
            if a.json:
                print(json.dumps({"wraps": [str(w) for w in ws]}, indent=2))
            else:
                for w in ws[:20]:
                    print(w)
                if not ws:
                    print("(no wraps yet — bolt wrap)")
            return 0
        res = run(vod=a.vod, top=a.top, dry_run=a.dry_run, motion=not a.no_motion,
                  captions=not a.no_captions, reel=not a.no_reel, out=a.out,
                  log=(lambda *_: None) if a.json else print)
        if a.json:
            print(json.dumps(res, indent=2, default=str))
        else:
            if res.get("error"):
                print(res["error"])
            for w in res.get("warnings") or []:
                print(f"  WARNING: {w}")
    except Exception as exc:
        msg = _soft(str(exc) or type(exc).__name__)
        print(json.dumps({"ok": False, "error": msg}) if a.json else msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
