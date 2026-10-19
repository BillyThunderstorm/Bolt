#!/usr/bin/env python3
"""
Song_Release.py — package finished songs for a distributor (READY; soft-fail)
============================================================================
``bolt release <folder>`` turns a folder of finished audio (Suno downloads,
bounces, etc.) into an upload-ready release folder for DistroKid / TuneCore /
CD Baby → Apple Music / Spotify:

  audio/NN - Title.wav    WAV 44.1 kHz / 16-bit stereo (ffmpeg converts; true
                          44.1k/16-bit WAVs are copied untouched)
  cover.(jpg|png)         copied only after checking ≥ 3000×3000 and square
  metadata.csv / .json    one row per track: title, artist, ISRC (blank —
                          distributor assigns), explicit, genre, release date,
                          songwriter, producer, … — fill blanks before upload
  CHECKLIST.md            upload checklist (incl. verify Suno plan commercial rights)
  release.json            machine report (conversions, warnings)

**Nothing is uploaded.** William uploads through the distributor's site.

CLI (via ``bolt release``):
  status [--json]
  list   [--json]                               (past release folders)
  run <folder> [--artist NAME] [--title NAME] [--cover FILE] [--genre G]
      [--release-date YYYY-MM-DD] [--songwriter NAME] [--explicit yes|no]
      [--out DIR] [--dry-run] [--json]

Soft-fail prefix: ``Release unavailable:``. Missing art / ffmpeg = clear
warnings (package still written where possible).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOFT = "Release unavailable:"
_REPO = Path(__file__).resolve().parents[2]
_CORE = _REPO / "Core"
_RELEASES = _REPO / "media" / "output" / "releases"
_AUDIO_EXT = {".wav", ".mp3", ".m4a", ".flac", ".aif", ".aiff", ".ogg", ".opus", ".aac"}
_COVER_NAMES = ("cover", "artwork", "art", "folder", "front")
_MIN_ART = 3000
_FIELDS = [
    "track_number", "title", "artist", "featured_artists", "release_title",
    "isrc", "explicit", "genre", "secondary_genre", "release_date", "songwriter",
    "producer", "language", "ai_assisted", "duration_s", "wav_file", "source_file",
]


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


def _ffprobe() -> Optional[str]:
    try:
        _ensure_core()
        from modules.FFmpeg_Bin import ffprobe_bin

        return ffprobe_bin()
    except Exception:
        return None


def _has_pil() -> bool:
    try:
        import PIL  # noqa: F401

        return True
    except Exception:
        return False


def status() -> Dict[str, Any]:
    ff = _ffmpeg()
    info = {
        "checked_at": _iso(),
        "readiness": "READY" if ff else "PARTIAL",
        "ready": bool(ff),
        "ffmpeg": ff,
        "pillow": _has_pil(),
        "releases_dir": str(_RELEASES),
        "targets": "DistroKid / TuneCore / CD Baby → Apple Music (no upload from Bolt)",
        "soft_fail_prefix": _SOFT,
        "error": "" if ff else _soft("no working ffmpeg — only existing 44.1k/16-bit WAVs can be packaged "
                                     "(brew reinstall ffmpeg-full)"),
    }
    if not info["pillow"]:
        info["art_hint"] = "Pillow missing → cover size check falls back to sips (macOS)"
    return info


def _probe_wav_stdlib(path: Path) -> Dict[str, Any]:
    """No-ffmpeg fallback: read a PCM WAV header with the stdlib."""
    import wave

    try:
        with wave.open(str(path), "rb") as wf:
            rate, ch, width, n = wf.getframerate(), wf.getnchannels(), wf.getsampwidth(), wf.getnframes()
        return {"codec": "pcm", "sample_rate": rate, "channels": ch, "bits": width * 8,
                "duration_s": round(n / float(rate or 1), 2)}
    except Exception:
        return {}


def _probe_audio(path: Path) -> Dict[str, Any]:
    fp = _ffprobe() if _ffmpeg() else None
    if not fp:
        return _probe_wav_stdlib(path) if path.suffix.lower() == ".wav" else {}
    try:
        r = subprocess.run(
            [fp, "-v", "error", "-select_streams", "a:0", "-show_entries",
             "stream=codec_name,sample_rate,channels,bits_per_sample,sample_fmt:format=duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        d = json.loads(r.stdout or "{}")
        st = (d.get("streams") or [{}])[0]
        return {
            "codec": st.get("codec_name"),
            "sample_rate": int(st.get("sample_rate") or 0),
            "channels": int(st.get("channels") or 0),
            "bits": int(st.get("bits_per_sample") or 0),
            "duration_s": round(float((d.get("format") or {}).get("duration") or 0), 2),
        }
    except Exception:
        return {}


def _peak_db(ff: str, path: Path) -> Optional[float]:
    try:
        r = subprocess.run([ff, "-hide_banner", "-nostats", "-i", str(path), "-af", "volumedetect",
                            "-f", "null", "-"], capture_output=True, text=True, timeout=120)
        m = re.search(r"max_volume:\s*(-?[\d.]+) dB", r.stderr or "")
        return float(m.group(1)) if m else None
    except Exception:
        return None


_NUMBERED = re.compile(r"^\s*(?:\d{1,2}-)?\d{1,3}[\s\-_.)]")
_LOSSLESS_RANK = {".wav": 0, ".aif": 0, ".aiff": 0, ".flac": 1}


def clean_title(stem: str, strip_number: bool = False) -> str:
    """Turn a file stem into a store title.

    ``strip_number`` is set when every file in the folder starts with a track
    number, so "10 Break Your Spirit" and "1-01 Take You" lose the prefix too.
    Without it only unambiguous prefixes go ("01_Song", "02-Song", "03 Song"),
    so a title like "7 Rings" survives.
    """
    t = stem
    t = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "", t, flags=re.I)
    if strip_number:
        t = re.sub(r"^\s*(?:\d{1,2}-)?\d{1,3}(?:\s*[-_.)]\s*|\s+)", "", t)
    else:
        t = re.sub(r"^\s*\d{1,3}\s*[-_.)]\s*", "", t)           # "01_" / "02-" / "3."
        t = re.sub(r"^\s*0\d\s+", "", t)                         # zero-padded "01 Song"
    t = re.sub(r"\s*\((\d+|v\d+|remastered|final)\)\s*$", "", t, flags=re.I)
    t = re.sub(r"(?<=[A-Za-z])-\d$", "", t)                      # Finder copy "Song-2"
    t = re.sub(r"[_]+", " ", t)
    if " " not in t.strip() and re.search(r"[A-Za-z]-[A-Za-z]", t):
        t = t.replace("-", " ")                                   # "I-Wont-Fold"
    t = re.sub(r"\s{2,}", " ", t).strip(" -_.")
    return t or stem


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def _dedupe(files: List[Path], titles: Dict[Path, str]) -> tuple:
    """Same song exported twice (e.g. .aif + .m4a) → keep the lossless/larger one."""
    best: Dict[str, Path] = {}
    order: List[str] = []
    for f in files:
        k = _title_key(titles[f]) or f.name
        if k not in best:
            best[k] = f
            order.append(k)
            continue
        cur = best[k]
        rank = lambda x: (_LOSSLESS_RANK.get(x.suffix.lower(), 2), -x.stat().st_size)  # noqa: E731
        if rank(f) < rank(cur):
            best[k] = f
    kept = [best[k] for k in order]
    dropped = [(f, best[_title_key(titles[f]) or f.name]) for f in files if f not in kept]
    return kept, dropped


def _safe_name(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]+', "", s).strip()
    return s[:80] or "Untitled"


def check_cover(path: Optional[Path]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"path": str(path) if path else None, "ok": False, "issues": []}
    if not path or not path.is_file():
        out["issues"].append("no cover art found (add cover.jpg ≥ 3000×3000 or pass --cover)")
        return out
    w = h = 0
    mode = fmt = ""
    try:
        from PIL import Image

        with Image.open(path) as im:
            w, h = im.size
            mode, fmt = im.mode, (im.format or "")
    except Exception:
        try:
            r = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
                               capture_output=True, text=True, timeout=10)
            w = int(re.search(r"pixelWidth:\s*(\d+)", r.stdout).group(1))
            h = int(re.search(r"pixelHeight:\s*(\d+)", r.stdout).group(1))
        except Exception as exc:
            out["issues"].append(f"cannot read image size ({exc})")
            return out
    out.update({"width": w, "height": h, "mode": mode, "format": fmt})
    if w != h:
        out["issues"].append(f"not square ({w}×{h})")
    if min(w, h) < _MIN_ART:
        out["issues"].append(f"too small ({w}×{h}; Apple Music needs ≥ {_MIN_ART}×{_MIN_ART})")
    if path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
        out["issues"].append(f"use JPG or PNG (got {path.suffix})")
    if mode and mode not in ("RGB", "L", "P", "RGBA"):
        out["issues"].append(f"colour mode {mode} — export as RGB")
    if mode == "RGBA":
        out["issues"].append("has transparency — flatten to RGB (some stores reject alpha)")
    out["ok"] = not out["issues"]
    return out


def _find_cover(folder: Path, explicit: Optional[str], release_title: str = "") -> Optional[Path]:
    if explicit:
        return Path(explicit).expanduser()
    imgs = sorted(f for f in folder.iterdir() if f.is_file() and not f.name.startswith(".")
                  and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"))
    for name in _COVER_NAMES:
        for f in imgs:
            if f.stem.lower().startswith(name):
                return f
    # Art named after the release ("The Manic Gay Disco Party.JPG" for that folder)
    want = re.sub(r"^the", "", _title_key(release_title))
    if want:
        for f in imgs:
            have = re.sub(r"^the", "", _title_key(f.stem))
            if have and (have == want or (len(want) >= 6 and want in have)):
                return f
    return imgs[0] if len(imgs) == 1 else None


def _release_dir(title: str, base: Optional[Path]) -> Path:
    root = base or _RELEASES
    stem = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")[:50] or "release"
    d = root / f"{date.today().isoformat()}_{stem}_release"
    n = 2
    while d.exists():
        d = root / f"{date.today().isoformat()}_{stem}_release-{n}"
        n += 1
    return d


def _checklist(meta: Dict[str, Any], tracks: List[Dict[str, Any]], cover: Dict[str, Any],
               warnings: List[str]) -> str:
    box = lambda ok: "[x]" if ok else "[ ]"  # noqa: E731
    wav_ok = bool(tracks) and all(t.get("wav_ok") for t in tracks)
    L = [
        f"# Release checklist — {meta['release_title']}", "",
        f"Artist: **{meta['artist'] or '(fill in)'}** · Tracks: {len(tracks)} · "
        f"Target release date: {meta['release_date']}", "",
        "Bolt packaged this folder. **Nothing was uploaded.** You upload via the distributor.", "",
        "## Rights (do this first)",
        "- [ ] **Verify Suno plan commercial rights** — songs must have been made on a paid plan "
        "(Pro/Premier) *at the time of creation* for you to own and distribute them. Free-plan songs "
        "are not yours to monetize. Check suno.com → account → billing history / song dates.",
        "- [ ] Any samples, beats, or co-writers cleared in writing",
        "- [ ] Distributor's AI-content disclosure answered honestly (DistroKid/TuneCore ask)", "",
        "## Audio",
        f"- {box(wav_ok)} WAV 44.1 kHz / 16-bit stereo for every track (`audio/`)",
        "- [ ] Listened start→end on headphones: no clicks, cut-offs, or Suno artifacts",
        "- [ ] Peaks below 0 dBFS (see `release.json` peak_db) and levels consistent across tracks", "",
        "## Artwork",
        f"- {box(cover.get('ok'))} Cover ≥ 3000×3000, square, JPG/PNG, RGB"
        + (f" — issues: {'; '.join(cover.get('issues') or [])}" if not cover.get("ok") else ""),
        "- [ ] No URLs, social handles, prices, store logos, or blurry/pixelated text on the cover",
        "- [ ] Artist + title on cover (if any) match metadata exactly", "",
        "## Metadata (`metadata.csv`)",
        "- [ ] Artist name spelled exactly the same as on existing Apple Music / Spotify profile",
        "- [ ] Titles: no \"(Official)\", no emojis, Title Case consistent; versions as (Remix)/(Live)",
        "- [ ] Explicit flag set per track (yes / no / clean)",
        "- [ ] Songwriter **legal** first + last name (Apple requires real names, not artist names)",
        "- [ ] Genre / secondary genre chosen",
        "- [ ] ISRC left blank → distributor assigns free (or paste existing ISRCs for re-releases)",
        "- [ ] Release date ≥ 2–4 weeks out (pitching + store processing; Apple can take days to 2 weeks)", "",
        "## Distributor",
        "- [ ] Pick one: DistroKid (annual flat fee) · TuneCore · CD Baby (one-time per release)",
        "- [ ] Stores: **Apple Music / iTunes** ticked (+ Spotify, etc.)",
        "- [ ] Upload WAVs from `audio/` + `cover` file; copy fields from `metadata.csv`",
        "- [ ] Save the distributor's confirmation / UPC / ISRCs back into `metadata.csv`", "",
    ]
    if warnings:
        L += ["## Bolt warnings", *[f"- {w}" for w in warnings], ""]
    return "\n".join(L) + "\n"


def run(folder: str, *, artist: str = "", title: str = "", cover: Optional[str] = None,
        genre: str = "", release_date: str = "", songwriter: str = "", explicit: str = "",
        out: Optional[str] = None, dry_run: bool = False, log=print) -> Dict[str, Any]:
    res: Dict[str, Any] = {"ok": False, "dry_run": dry_run, "warnings": [], "uploaded": False}
    src = Path(folder).expanduser()
    if not src.is_dir():
        res["error"] = _soft(f"folder not found: {src}")
        return res
    files = sorted(f for f in src.iterdir() if f.is_file() and f.suffix.lower() in _AUDIO_EXT
                   and not f.name.startswith("."))
    if not files:
        res["error"] = _soft(f"no audio files in {src} ({', '.join(sorted(_AUDIO_EXT))})")
        return res
    ff = _ffmpeg()
    numbered = len(files) > 1 and all(_NUMBERED.match(f.stem) for f in files)
    titles = {f: clean_title(f.stem, strip_number=numbered) for f in files}
    files, dropped = _dedupe(files, titles)
    rel_title = title or (titles[files[0]] if len(files) == 1 else src.name)
    rdate = release_date or (date.today() + timedelta(days=21)).isoformat()
    meta = {"release_title": rel_title, "artist": artist, "genre": genre, "release_date": rdate,
            "songwriter": songwriter, "explicit": explicit,
            "release_type": "Single" if len(files) == 1 else ("EP" if len(files) <= 6 else "Album")}
    dest = Path(out).expanduser() if out else _release_dir(rel_title, None)
    cov = check_cover(_find_cover(src, cover, rel_title))
    for f, keep in dropped:
        res["warnings"].append(f"skipped duplicate {f.name} (same song as {keep.name}; kept the "
                               f"{'lossless' if _LOSSLESS_RANK.get(keep.suffix.lower(), 2) < 2 else 'larger'} file)")
    if not cov["ok"]:
        res["warnings"] += [f"cover: {i}" for i in cov["issues"]]
    if not artist:
        res["warnings"].append("artist not set — pass --artist (must match your Apple Music artist name)")
    if not ff:
        res["warnings"].append(status()["error"])
    res.update({"source": str(src), "output_dir": str(dest), "meta": meta, "cover": cov})

    tracks: List[Dict[str, Any]] = []
    for i, f in enumerate(files, 1):
        info = _probe_audio(f)
        native = (f.suffix.lower() == ".wav" and info.get("sample_rate") == 44100
                  and info.get("bits") == 16 and info.get("channels") == 2)
        t_title = titles[f]
        wav_name = f"{i:02d} - {_safe_name(t_title)}.wav"
        tracks.append({"track_number": i, "title": t_title, "source_file": str(f),
                       "wav_file": f"audio/{wav_name}", "probe": info,
                       "action": "copy" if native else ("convert" if ff else "skip"),
                       "duration_s": info.get("duration_s", "")})
    res["tracks"] = tracks
    log(f"[release] {meta['release_type']} '{rel_title}' — {len(files)} track(s) → {dest}")
    for t in tracks:
        log(f"  {t['track_number']:02d}. {t['title']}  [{t['action']}]  ← {Path(t['source_file']).name}")
    log(f"  cover: {'OK' if cov['ok'] else 'NEEDS WORK — ' + '; '.join(cov['issues'])}")
    if dry_run:
        res["ok"] = True
        return res

    (dest / "audio").mkdir(parents=True, exist_ok=True)
    for t in tracks:
        target = dest / t["wav_file"]
        src_f = Path(t["source_file"])
        try:
            if t["action"] == "copy":
                shutil.copy2(src_f, target)
            elif t["action"] == "convert":
                r = subprocess.run([ff, "-y", "-v", "error", "-i", str(src_f), "-vn", "-map_metadata", "-1",
                                    "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(target)],
                                   capture_output=True, text=True, timeout=600)
                if r.returncode != 0:
                    raise RuntimeError((r.stderr or "ffmpeg failed")[-200:])
            else:
                t["wav_ok"] = False
                res["warnings"].append(f"{src_f.name}: not converted (no ffmpeg)")
                continue
            chk = _probe_audio(target)
            t["wav_ok"] = (chk.get("sample_rate") == 44100 and chk.get("bits") == 16) if chk else True
            t["duration_s"] = chk.get("duration_s", t["duration_s"])
            if ff:
                pk = _peak_db(ff, target)
                t["peak_db"] = (0.0 if pk == 0 else pk) if pk is not None else None   # no "-0.0"
                if t["peak_db"] is not None and t["peak_db"] >= -0.1:
                    res["warnings"].append(f"{t['title']}: peak {t['peak_db']} dBFS — may clip on some stores")
            if t["duration_s"] and float(t["duration_s"]) < 30:
                res["warnings"].append(f"{t['title']}: under 30 s — stores may reject or not pay")
        except Exception as exc:
            t["wav_ok"] = False
            res["warnings"].append(f"{src_f.name}: {exc}")

    if cov.get("path") and Path(cov["path"]).is_file():
        cp = Path(cov["path"])
        shutil.copy2(cp, dest / f"cover{cp.suffix.lower()}")
        cov["copied_to"] = str(dest / f"cover{cp.suffix.lower()}")

    rows = []
    for t in tracks:
        rows.append({
            "track_number": t["track_number"], "title": t["title"], "artist": artist,
            "featured_artists": "", "release_title": rel_title, "isrc": "",
            "explicit": explicit, "genre": genre, "secondary_genre": "", "release_date": rdate,
            "songwriter": songwriter, "producer": "", "language": "English",
            "ai_assisted": "yes (Suno)" if "suno" in str(t["source_file"]).lower() else "",
            "duration_s": t.get("duration_s", ""), "wav_file": t["wav_file"],
            "source_file": t["source_file"],
        })
    with open(dest / "metadata.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        w.writeheader()
        w.writerows(rows)
    (dest / "metadata.json").write_text(json.dumps({"release": {**meta, "upc": "", "label": "",
                                                                "copyright_line": f"℗ {date.today().year} {artist}".strip()},
                                                    "tracks": rows}, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
    (dest / "CHECKLIST.md").write_text(_checklist(meta, tracks, cov, res["warnings"]), encoding="utf-8")
    res["ok"] = any(t.get("wav_ok") for t in tracks)
    res["finished_at"] = _iso()
    (dest / "release.json").write_text(json.dumps(res, indent=2, default=str, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    tagged = 0
    try:
        _ensure_core()
        from modules.Bolt_Wrap import apply_finder_tag, tag_tool

        if tag_tool():
            for f in dest.rglob("*"):
                ext = f.suffix.lower()
                color = ("Purple" if ext in (".wav", ".jpg", ".jpeg", ".png") else
                         "Blue" if ext == ".md" else "Orange" if ext in (".csv", ".json") else None)
                if color:
                    tagged += apply_finder_tag(f, color)
            tagged += apply_finder_tag(dest, "Purple")
    except Exception:
        pass
    res["finder_tagged"] = tagged
    try:   # rewrite in place (keeps the Finder tag xattr) so the report has the tag count
        (dest / "release.json").write_text(json.dumps(res, indent=2, default=str, ensure_ascii=False) + "\n",
                                           encoding="utf-8")
    except Exception:
        pass
    log(f"[release] wrote {sum(1 for t in tracks if t.get('wav_ok'))}/{len(tracks)} WAV · metadata.csv/json · "
        f"CHECKLIST.md · tagged {tagged} → {dest}")
    return res


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(prog="bolt release", description="Package songs for distributors (no upload)")
    p.add_argument("action", nargs="?", default="status", choices=["status", "list", "run"])
    p.add_argument("folder", nargs="?")
    p.add_argument("--artist", default="")
    p.add_argument("--title", default="", help="release title (default: folder name / single track title)")
    p.add_argument("--cover", default=None)
    p.add_argument("--genre", default="")
    p.add_argument("--release-date", default="")
    p.add_argument("--songwriter", default="")
    p.add_argument("--explicit", default="", choices=["", "yes", "no", "clean"])
    p.add_argument("--out", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    try:
        if a.action == "status":
            st = status()
            if a.json:
                print(json.dumps(st, indent=2))
            else:
                print(f"release readiness: {st['readiness']}  ready={'yes' if st['ready'] else 'no'}")
                print(f"  ffmpeg={st['ffmpeg']}  pillow={st['pillow']}")
                print(f"  releases: {st['releases_dir']}")
                print(f"  {st['targets']}")
                print(f"  {st['error'] or 'hint: bolt release <folder> --artist NAME [--cover cover.jpg]'}")
            return 0
        if a.action == "list":
            rs = sorted([d for d in _RELEASES.glob("*_release*") if d.is_dir()], reverse=True) if _RELEASES.is_dir() else []
            if a.json:
                print(json.dumps({"releases": [str(r) for r in rs]}, indent=2))
            else:
                for r in rs[:20]:
                    print(r)
                if not rs:
                    print("(no releases yet — bolt release <folder>)")
            return 0
        if not a.folder:
            print(_soft("run needs a folder: bolt release <folder-of-songs>"))
            return 0
        res = run(a.folder, artist=a.artist, title=a.title, cover=a.cover, genre=a.genre,
                  release_date=a.release_date, songwriter=a.songwriter, explicit=a.explicit,
                  out=a.out, dry_run=a.dry_run, log=(lambda *_: None) if a.json else print)
        if a.json:
            print(json.dumps(res, indent=2, default=str, ensure_ascii=False))
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
