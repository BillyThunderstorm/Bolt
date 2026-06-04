#!/usr/bin/env python3
"""Summarize title-generation readiness and posted-clip learning signals."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "config.json"
TITLE_CACHE_FILE = ROOT / "data" / "title_cache.json"
TEN_CLIP_REPORT = ROOT / "data" / "title_upgrade_10_clip_test.json"
PERFORMANCE_OUTCOMES_FILE = ROOT / "data" / "performance_outcomes.jsonl"


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            rows.append({"parse_error": line[:120]})
    return rows


def main() -> int:
    config = load_json(CONFIG_FILE, {})
    title_config = config.get("title_generation", {})
    quality_tiers = config.get("quality_tiers", {})
    enabled = title_config.get("enabled")
    if enabled is None:
        enabled = quality_tiers.get("use_ai_titles", False)

    cache = load_json(TITLE_CACHE_FILE, {})
    ten_clip_report = load_json(TEN_CLIP_REPORT, {})
    outcomes = load_jsonl(PERFORMANCE_OUTCOMES_FILE)
    title_outcomes = [
        row for row in outcomes
        if "title" in str(row).lower() or row.get("clip_path") or row.get("trigger")
    ]

    print("Bolt title upgrade monitor")
    print("==========================")
    print(f"AI titles enabled: {'yes' if enabled else 'no'}")
    print(f"Title cache entries: {len(cache)}")
    if ten_clip_report:
        print(
            "10-clip smoke test: "
            f"{ten_clip_report.get('passed', 0)}/{ten_clip_report.get('scenario_count', 0)} passed "
            f"at {ten_clip_report.get('generated_at', 'unknown time')}"
        )
    else:
        print("10-clip smoke test: no report found")
    print(f"Performance outcomes logged: {len(outcomes)}")
    print(f"Title/clip learning signals available: {len(title_outcomes)}")

    if title_outcomes:
        latest = title_outcomes[-1]
        print("\nLatest learning signal:")
        print(json.dumps(latest, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
