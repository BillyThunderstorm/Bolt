#!/usr/bin/env python3
"""
Social_Stats.py — TikTok / YouTube performance pull status + sync helpers
========================================================================
Wraps existing Performance_Sync + token setup into a simple morning-friendly
surface: ``bolt stats``.

Does not invent APIs — uses:
  - modules.Performance_Sync.sync_tiktok_stats / sync_youtube_stats
  - tokens in .env via TikTok_Auth / YouTube_Auth

Scopes note:
  TikTok needs ``video.list`` approved for stats (not only upload).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO = Path(__file__).resolve().parents[2]
_CORE = Path(__file__).resolve().parents[1]


def _load_env_file(path: Path) -> None:
    """Minimal KEY=VALUE loader (no python-dotenv required)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, _, val = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue  # never override existing env
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        os.environ[key] = val


def _load_env() -> None:
    """Load repo-root .env (and Core/.env if present) without requiring cwd."""
    paths = (_REPO / ".env", _CORE / ".env")
    try:
        from dotenv import load_dotenv

        for path in paths:
            if path.is_file():
                load_dotenv(path, override=False)
        return
    except ImportError:
        pass
    for path in paths:
        if path.is_file():
            _load_env_file(path)


_load_env()


def _env_set(*keys: str) -> bool:
    return any(bool((os.getenv(k) or "").strip()) for k in keys)


def tiktok_ready() -> Dict[str, Any]:
    has_client = _env_set("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_ID")
    has_secret = _env_set("TIKTOK_CLIENT_SECRET")
    has_token = _env_set("TIKTOK_ACCESS_TOKEN")
    has_refresh = _env_set("TIKTOK_REFRESH_TOKEN")
    scope = (os.getenv("TIKTOK_SCOPE") or "").lower()
    has_list = "video.list" in scope or not scope  # unknown scope → try later
    ok = has_token or (has_client and has_secret and has_refresh)
    return {
        "platform": "tiktok",
        "ready": bool(ok),
        "has_access_token": has_token,
        "has_refresh_token": has_refresh,
        "has_client": has_client and has_secret,
        "scope_mentions_video_list": "video.list" in scope if scope else None,
        "next_step": (
            "ok — try: bolt stats tiktok --dry-run"
            if ok
            else 'bolt tiktok_token  # scopes: user.info.basic,video.list,…'
        ),
    }


def youtube_ready() -> Dict[str, Any]:
    has_token = _env_set("YOUTUBE_ACCESS_TOKEN")
    has_refresh = _env_set("YOUTUBE_REFRESH_TOKEN")
    has_client = _env_set("YOUTUBE_CLIENT_ID", "GOOGLE_CLIENT_ID")
    ok = has_token or has_refresh
    return {
        "platform": "youtube",
        "ready": bool(ok),
        "has_access_token": has_token,
        "has_refresh_token": has_refresh,
        "has_client_hint": has_client,
        "next_step": (
            "ok — try: bolt stats youtube --dry-run"
            if ok
            else "bolt youtube_token  # Google OAuth desktop client + YouTube Data API"
        ),
    }


def readiness_summary() -> str:
    t = tiktok_ready()
    y = youtube_ready()
    parts = []
    parts.append("TikTok " + ("ready" if t["ready"] else "needs token"))
    parts.append("YouTube " + ("ready" if y["ready"] else "needs token"))
    return " · ".join(parts)


def recent_outcomes_summary(limit: int = 5) -> str:
    """One-liner from performance_outcomes.jsonl (latest lines)."""
    path = _REPO / "Data" / "performance_outcomes.jsonl"
    if not path.is_file():
        return "no outcomes file yet"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        rows: List[str] = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            import json

            try:
                o = json.loads(line)
            except Exception:
                continue
            plat = o.get("platform") or "?"
            views = o.get("views")
            title = (o.get("title") or "")[:36]
            if views is None:
                continue
            rows.append(f"{plat} {views:,}v · {title}")
            if len(rows) >= limit:
                break
        if not rows:
            return f"{path.name} empty / no view rows"
        return f"last {len(rows)}: " + " | ".join(rows)
    except Exception as exc:
        return f"(could not read outcomes: {exc})"


def print_status() -> None:
    print("\n  Social stats readiness")
    print("  " + "─" * 40)
    for block in (tiktok_ready(), youtube_ready()):
        flag = "✓" if block["ready"] else "○"
        print(f"  {flag}  {block['platform'].title()}")
        for k, v in block.items():
            if k in ("platform", "ready", "next_step"):
                continue
            print(f"      {k}: {v}")
        print(f"      → {block['next_step']}")
    print()
    print(f"  Outcomes: {recent_outcomes_summary(3)}")
    print()
    print("  Pull into learning store (Data/performance_outcomes.jsonl):")
    print("    bolt stats --dry-run          # both platforms, no write")
    print("    bolt stats youtube --dry-run")
    print("    bolt stats tiktok --dry-run")
    print("    bolt stats sync               # both, live write")
    print()
    print("  Tokens (when not ready):")
    print("    bolt youtube_token            # YouTube Data API readonly")
    print("    bolt tiktok_token             # needs video.list scope")
    print()


def run_sync(
    platform: str,
    *,
    dry_run: bool = False,
    limit: int = 50,
    min_age_hours: float = 24.0,
    shorts_only: bool = False,
    json_out: bool = False,
) -> int:
    """platform: tiktok | youtube | both"""
    import json

    from modules.Performance_Sync import (
        print_sync_report,
        sync_tiktok_stats,
        sync_youtube_stats,
    )

    results: List[Dict[str, Any]] = []
    plat = (platform or "both").lower().strip()
    ok_all = True

    if plat in ("tiktok", "both", "all"):
        print("\n  ── TikTok sync ──")
        r = sync_tiktok_stats(
            limit=limit,
            min_age_hours=min_age_hours,
            dry_run=dry_run,
            feed_learning=not dry_run,
        )
        results.append({"platform": "tiktok", **r})
        if json_out:
            print(json.dumps(r, indent=2, default=str))
        else:
            print_sync_report(r)
        if not r.get("ok"):
            ok_all = False
            print(f"  → {tiktok_ready()['next_step']}")

    if plat in ("youtube", "yt", "shorts", "both", "all"):
        print("\n  ── YouTube sync ──")
        r = sync_youtube_stats(
            limit=limit,
            min_age_hours=min_age_hours,
            dry_run=dry_run,
            feed_learning=not dry_run,
            shorts_only=shorts_only or plat == "shorts",
        )
        results.append({"platform": "youtube", **r})
        if json_out:
            print(json.dumps(r, indent=2, default=str))
        else:
            print_sync_report(r)
        if not r.get("ok"):
            ok_all = False
            print(f"  → {youtube_ready()['next_step']}")

    return 0 if ok_all else 1


def main(argv: Optional[List[str]] = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            """bolt stats — social performance pull

  bolt stats                 # readiness (tokens) + recent outcomes
  bolt stats --dry-run       # both platforms, fetch only (no write)
  bolt stats tiktok [--dry-run] [--limit N] [--min-age-hours H]
  bolt stats youtube [--dry-run] [--shorts-only] …
  bolt stats sync            # both platforms, live write
  bolt stats sync --dry-run  # both, no write

Requires TikTok video.list scope and/or YouTube OAuth:
  bolt tiktok_token
  bolt youtube_token
"""
        )
        return 0

    dry = "--dry-run" in args or "--dry" in args
    json_out = "--json" in args
    shorts = "--shorts-only" in args
    limit = 50
    min_age = 24.0
    # Values that belong to option flags (not subcommands)
    value_taken: set[int] = set()
    if "--limit" in args:
        i = args.index("--limit")
        if i + 1 < len(args):
            limit = int(args[i + 1])
            value_taken.add(i + 1)
    if "--min-age-hours" in args:
        i = args.index("--min-age-hours")
        if i + 1 < len(args):
            min_age = float(args[i + 1])
            value_taken.add(i + 1)

    # Flag-only: bolt stats --dry-run  →  both platforms, always dry (safe).
    # Live writes need an explicit verb: bolt stats sync
    positionals = [
        a
        for i, a in enumerate(args)
        if not a.startswith("-") and i not in value_taken
    ]
    if not positionals:
        if dry or json_out or shorts or "--limit" in args or "--min-age-hours" in args:
            return run_sync(
                "both",
                dry_run=True,
                limit=limit,
                min_age_hours=min_age,
                shorts_only=shorts,
                json_out=json_out,
            )
        print_status()
        return 0

    cmd = positionals[0].lower()
    if cmd in ("status", "check", "ready"):
        print_status()
        return 0
    if cmd in ("sync", "pull", "all"):
        return run_sync(
            "both",
            dry_run=dry,
            limit=limit,
            min_age_hours=min_age,
            shorts_only=shorts,
            json_out=json_out,
        )
    if cmd in ("tiktok", "tt"):
        return run_sync(
            "tiktok",
            dry_run=dry,
            limit=limit,
            min_age_hours=min_age,
            json_out=json_out,
        )
    if cmd in ("youtube", "yt", "shorts"):
        return run_sync(
            "youtube" if cmd != "shorts" else "shorts",
            dry_run=dry,
            limit=limit,
            min_age_hours=min_age,
            shorts_only=shorts or cmd == "shorts",
            json_out=json_out,
        )
    print(f"unknown stats action: {cmd}", file=sys.stderr)
    print("  try: bolt stats | bolt stats --dry-run | bolt stats youtube --dry-run", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
