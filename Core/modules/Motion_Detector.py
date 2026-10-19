#!/usr/bin/env python3
"""
Motion_Detector.py — visual high-action scoring for VODs/clips (READY; soft-fail)
================================================================================
Former deferred IDEA (Docs/AI_Guide.md open decision #4 "motion detection").
Promoted PARTIAL → READY 18 Oct 2026 (end-to-end smoke on VOD + clip, both backends).

How it works (frame differencing, no ML):
  1. Decode the video at a low sample rate (default 4 fps) as small grayscale
     frames — ffmpeg rawvideo pipe (fast, uses FFmpeg_Bin) or OpenCV fallback.
  2. Per sample: mean absolute pixel difference vs the previous sample (0–1).
     Hard scene cuts (huge one-frame jumps) are damped so menu/loading cuts
     do not dominate.
  3. Roll into windows (default 4 s), robust z-score vs the whole video
     (median / MAD), then pick the top-N non-overlapping high-action windows.

CLI (via ``bolt motion``):
  status [--json]
  list                       (recent motion reports)
  run <video> [--top N] [--window S] [--fps F] [--start S] [--duration S]
              [--fast] [--out FILE] [--json]

Library:
  analyze(video, ...) -> dict  (segments + per-second curve)
  score_at(report, t, radius) -> 0..100  (feed Highlight_Detector events)

Soft-fail prefix: ``Motion unavailable:``. Needs numpy + (ffmpeg or opencv).
Reports: media/output/motion/<stem>_motion.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Motion unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_CORE = _REPO / "Core"
_OUT_DIR = _REPO / "media" / "output" / "motion"
_W, _H = 160, 90  # analysis frame size


def _soft(msg: str) -> str:
    return msg if msg.startswith(_SOFT) else f"{_SOFT} {msg}"


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_core() -> None:
    if str(_CORE) not in sys.path:
        sys.path.insert(0, str(_CORE))


def _ffmpeg() -> Optional[str]:
    try:
        _ensure_core()
        from modules.FFmpeg_Bin import working_ffmpeg

        return working_ffmpeg()
    except Exception:
        return None


def _ffprobe_duration(path: str) -> Optional[float]:
    try:
        _ensure_core()
        from modules.FFmpeg_Bin import ffprobe_bin

        r = subprocess.run(
            [ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=20,
        )
        return float(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
    except Exception:
        return None


def _one_line(err: str, limit: int = 160) -> str:
    """Collapse multi-line ffmpeg stderr into one readable soft-fail line."""
    lines: List[str] = []
    for ln in err.strip().splitlines():
        ln = re.sub(r"^\[[^\]]*\]\s*", "", ln.strip()).strip()
        if ln and ln not in lines:
            lines.append(ln)
    msg = " · ".join(lines[:2]) or "unknown error"
    return msg[:limit]


def _has(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def status() -> Dict[str, Any]:
    ff = _ffmpeg()
    np_ok, cv_ok = _has("numpy"), _has("cv2")
    backend = "ffmpeg" if (ff and np_ok) else ("opencv" if (cv_ok and np_ok) else "")
    info: Dict[str, Any] = {
        "checked_at": _iso(),
        "readiness": "READY",
        "ready": bool(backend),
        "backend": backend or None,
        "ffmpeg": ff,
        "numpy": np_ok,
        "opencv": cv_ok,
        "reports_dir": str(_OUT_DIR),
        "soft_fail_prefix": _SOFT,
        "cli": "bolt motion <video>",
        "error": "",
    }
    if not np_ok:
        info["error"] = _soft("numpy missing (uv sync)")
    elif not backend:
        info["error"] = _soft(
            "no decoder: ffmpeg not launchable and opencv-python missing "
            "(brew reinstall ffmpeg-full, or uv pip install opencv-python-headless)"
        )
    return info


# ── decoding ────────────────────────────────────────────────────────────────

def _frames_ffmpeg(path: str, fps: float, start: float, duration: Optional[float], fast: bool):
    import numpy as np

    cmd = [_ffmpeg() or "ffmpeg", "-v", "error", "-nostdin"]
    if fast:
        cmd += ["-skip_frame", "nokey"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", path]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    # fps filter keeps timestamps exact; --fast only decodes keyframes (long VODs)
    cmd += ["-an", "-vf", f"fps={fps},scale={_W}:{_H},format=gray",
            "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    size = _W * _H
    i = 0
    try:
        while True:
            buf = proc.stdout.read(size) if proc.stdout else b""
            if len(buf) < size:
                break
            t = start + (i / fps)
            yield t, np.frombuffer(buf, dtype=np.uint8).astype(np.int16)
            i += 1
    finally:
        try:
            proc.kill()
        except Exception:
            pass
        err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
        proc.wait()
        if i == 0 and err.strip():
            raise RuntimeError(f"ffmpeg decode failed: {_one_line(err)}")


def _frames_opencv(path: str, fps: float, start: float, duration: Optional[float]):
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"opencv cannot open {path}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(src_fps / fps)))
    if start:
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)
    idx = 0
    end = (start + duration) if duration else None
    try:
        while True:
            if idx % step == 0:
                ok, frame = cap.read()
                if not ok:
                    break
                t = start + idx / src_fps
                if end and t > end:
                    break
                g = cv2.cvtColor(cv2.resize(frame, (_W, _H)), cv2.COLOR_BGR2GRAY)
                yield t, g.astype(np.int16).ravel()
            else:
                if not cap.grab():
                    break
            idx += 1
    finally:
        cap.release()


# ── analysis ────────────────────────────────────────────────────────────────

def analyze(
    video: str,
    *,
    fps: float = 4.0,
    window: float = 4.0,
    top: int = 10,
    min_gap: Optional[float] = None,
    start: float = 0.0,
    duration: Optional[float] = None,
    fast: bool = False,
    backend: Optional[str] = None,
) -> Dict[str, Any]:
    """Score motion across *video*. Raises on hard failure (CLI soft-wraps)."""
    import numpy as np

    path = str(Path(video).expanduser())
    if not Path(path).is_file():
        raise FileNotFoundError(f"video not found: {path}")
    st = status()
    use = backend or st["backend"]
    if not use:
        raise RuntimeError(st["error"] or "no decoder")
    if fast:
        fps = min(fps, 1.0)
    gen = (_frames_ffmpeg(path, fps, start, duration, fast) if use == "ffmpeg"
           else _frames_opencv(path, fps, start, duration))

    times: List[float] = []
    diffs: List[float] = []
    prev = None
    for t, fr in gen:
        if prev is not None:
            times.append(t)
            diffs.append(float(np.abs(fr - prev).mean()) / 255.0)
        prev = fr
    if len(diffs) < 3:
        raise RuntimeError(f"too few frames decoded ({len(diffs) + (1 if prev is not None else 0)})")

    d = np.asarray(diffs, dtype=np.float64)
    tt = np.asarray(times, dtype=np.float64)
    if fast:
        # keyframe mode: the fps filter repeats keyframes → exact-zero diffs
        # are duplicates, not stillness. Drop them so the baseline is honest.
        keep = d > 0
        if keep.sum() >= 3:
            d, tt = d[keep], tt[keep]
    # Damp hard cuts: a single-sample jump far above both neighbours.
    med = float(np.median(d))
    cut_thr = max(0.18, med * 8)
    cuts = 0
    for i in range(len(d)):
        lo = d[i - 1] if i > 0 else d[i]
        hi = d[i + 1] if i + 1 < len(d) else d[i]
        if d[i] > cut_thr and d[i] > 3 * max(lo, hi, 1e-6):
            d[i] = max(lo, hi)
            cuts += 1

    # Per-window score
    t0, t1 = float(tt[0]), float(tt[-1])
    n_win = max(1, int(np.ceil((t1 - t0) / window)))
    w_scores = np.zeros(n_win)
    for k in range(n_win):
        a, b = t0 + k * window, t0 + (k + 1) * window
        m = (tt >= a) & (tt < b)
        w_scores[k] = float(d[m].mean()) if m.any() else 0.0
    wmed = float(np.median(w_scores))
    mad = float(np.median(np.abs(w_scores - wmed))) or 1e-6
    z = (w_scores - wmed) / (1.4826 * mad)
    # 0–100 score: logistic on z so typical = ~10, very high action → 90+
    score100 = 100.0 / (1.0 + np.exp(-(z - 2.0)))

    gap = min_gap if min_gap is not None else window * 2
    order = np.argsort(-w_scores)
    picked: List[int] = []
    for k in order:
        if len(picked) >= top:
            break
        if z[k] < 1.0:
            break
        center = t0 + (k + 0.5) * window
        if all(abs(center - (t0 + (j + 0.5) * window)) >= gap for j in picked):
            picked.append(int(k))
    segments = []
    for k in sorted(picked, key=lambda j: -w_scores[j]):
        a, b = t0 + k * window, t0 + (k + 1) * window
        m = (tt >= a) & (tt < b)
        peak = float(tt[m][int(np.argmax(d[m]))]) if m.any() else a
        segments.append({
            "start": round(a, 2), "end": round(b, 2), "peak": round(peak, 2),
            "score": round(float(score100[k]), 1), "z": round(float(z[k]), 2),
            "motion": round(float(w_scores[k]), 4),
        })

    # 1 Hz curve for downstream merges (Bolt_Wrap / highlights)
    curve = []
    sec = int(t0)
    while sec <= int(t1):
        m = (tt >= sec) & (tt < sec + 1)
        if m.any():
            curve.append([sec, round(float(d[m].mean()), 4)])
        sec += 1

    return {
        "video": path,
        "analyzed_at": _iso(),
        "backend": use,
        "fps": fps,
        "fast_keyframes": bool(fast),
        "window_s": window,
        "start_s": round(t0, 2),
        "end_s": round(t1, 2),
        "duration_s": round(t1 - t0, 2),
        "samples": int(len(d)),
        "cuts_damped": cuts,
        "baseline_motion": round(wmed, 4),
        "segments": segments,
        "curve_1hz": curve,
    }


def score_at(report: Dict[str, Any], t: float, radius: float = 3.0) -> float:
    """Motion score 0–100 around time *t* using a report's 1 Hz curve."""
    curve = report.get("curve_1hz") or []
    if not curve:
        return 0.0
    vals = sorted(v for s, v in curve if v > 0)
    if not vals:
        return 0.0
    base = vals[len(vals) // 2] or 1e-6
    near = [v for s, v in curve if abs(s - t) <= radius]
    if not near:
        return 0.0
    ratio = max(near) / base
    # ratio 1 → ~10, ratio 3 → ~50, ratio 6+ → ~90
    import math

    return round(100.0 / (1.0 + math.exp(-(ratio - 3.0) * 0.9)), 1)


def default_report_path(video: str) -> Path:
    return _OUT_DIR / f"{Path(video).stem}_motion.json"


def _fmt(t: float) -> str:
    t = int(t)
    return f"{t // 3600:d}:{(t % 3600) // 60:02d}:{t % 60:02d}"


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(prog="bolt motion", description="Visual motion scoring (READY; soft-fail)")
    p.add_argument("action", nargs="?", default="status", choices=["status", "list", "run"])
    p.add_argument("video", nargs="?")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--window", type=float, default=4.0)
    p.add_argument("--fps", type=float, default=4.0)
    p.add_argument("--start", type=float, default=0.0)
    p.add_argument("--duration", type=float, default=None)
    p.add_argument("--fast", action="store_true", help="keyframes only (long VODs)")
    p.add_argument("--backend", choices=["ffmpeg", "opencv"], default=None)
    p.add_argument("--out", default=None, help="report path (default media/output/motion/)")
    p.add_argument("--no-save", action="store_true")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    try:
        if a.action == "status":
            st = status()
            if a.json:
                print(json.dumps(st, indent=2))
            else:
                print(f"motion readiness: {st['readiness']}  ready={'yes' if st['ready'] else 'no'}  backend={st['backend']}")
                print(f"  ffmpeg={st['ffmpeg']}  numpy={st['numpy']}  opencv={st['opencv']}")
                print(f"  reports: {_OUT_DIR}")
                print(f"  {st['error'] or 'hint: bolt motion <video> [--top N] [--json]'}")
            return 0
        if a.action == "list":
            files = sorted(_OUT_DIR.glob("*_motion.json"), key=lambda f: f.stat().st_mtime, reverse=True)
            if a.json:
                print(json.dumps({"reports": [str(f) for f in files]}, indent=2))
            else:
                for f in files[:20]:
                    print(f)
                if not files:
                    print("(no motion reports yet — bolt motion <video>)")
            return 0
        if not a.video:
            print(_soft("run needs a video path: bolt motion <video>"))
            return 0
        rep = analyze(a.video, fps=a.fps, window=a.window, top=a.top, start=a.start,
                      duration=a.duration, fast=a.fast, backend=a.backend)
        if not a.no_save:
            out = Path(a.out).expanduser() if a.out else default_report_path(a.video)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
            rep["report_path"] = str(out)
        if a.json:
            slim = {k: v for k, v in rep.items() if k != "curve_1hz"}
            print(json.dumps(slim, indent=2))
        else:
            print(f"motion: {Path(rep['video']).name}  {rep['duration_s']:.0f}s  backend={rep['backend']}  "
                  f"samples={rep['samples']}  cuts_damped={rep['cuts_damped']}")
            if not rep["segments"]:
                print("  no high-action windows above baseline")
            for i, s in enumerate(rep["segments"], 1):
                print(f"  {i:>2}. {_fmt(s['start'])}–{_fmt(s['end'])}  peak {_fmt(s['peak'])}  "
                      f"score {s['score']:>5.1f}  z={s['z']}")
            if rep.get("report_path"):
                print(f"  report: {rep['report_path']}")
    except Exception as exc:
        msg = _soft(str(exc) or type(exc).__name__)
        print(json.dumps({"ok": False, "error": msg}, indent=2) if a.json else msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
