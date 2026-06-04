#!/usr/bin/env python3
"""Run the LLM title upgrade against 10 representative clip scenarios.

This is a smoke test for the production title path. It uses a mocked LLM so it
does not spend API credits, but it still exercises Bolt's real title generator,
JSON parsing, cache writes, hashtag cleanup, and template fallback behavior.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import Title_Generator as titles  # noqa: E402


SCENARIOS = [
    {"trigger": "kill", "score": 72, "context": {"transcript": "Wait, how did that land?"}},
    {"trigger": "multi_kill", "score": 88, "context": {"kill_count": 3, "window_seconds": 9}},
    {"trigger": "ace", "score": 95, "context": {"transcript": "No way. That was all five."}},
    {"trigger": "chat_hype", "score": 82, "context": {"transcript": "Chat called it before I did."}},
    {"trigger": "reaction", "score": 78, "context": {"transcript": "I actually cannot believe that worked."}},
    {"trigger": "highlight", "score": 70, "context": {"transcript": "That was cleaner than it had any right to be."}},
    {"trigger": "manual", "score": 76, "context": {"transcript": "Saving that one. Easy."}},
    {"trigger": "donation", "score": 84, "context": {"donor_name": "chat"}},
    {"trigger": "raid", "score": 86, "context": {"raid_size": "12"}},
    {"trigger": "sub", "score": 80, "context": {"transcript": "Perfect timing on that sub."}},
]


def fake_ask_llm(prompt: str, model: str = "") -> str:
    marker = "Clip details:"
    details = {}
    if marker in prompt:
        after_marker = prompt.split(marker, 1)[1]
        details_json = after_marker.split("\n\n", 1)[0].strip()
        details = json.loads(details_json)

    trigger = details.get("trigger", "highlight").replace("_", " ")
    game = details.get("game", "Marvel Rivals")
    return json.dumps({
        "titles": [
            f"Billy turned this {trigger} into a moment.",
            f"This {game} clip got weird fast.",
            "The replay makes it even better.",
        ],
        "hashtags": ["#MarvelRivals", "#Gaming", "#Clips", "#BillyThunderstorm"],
    })


def main() -> int:
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scenario_count": len(SCENARIOS),
        "passed": 0,
        "failed": 0,
        "results": [],
    }

    with tempfile.TemporaryDirectory() as tmp:
        cache_path = Path(tmp) / "title_cache.json"
        with patch.object(titles, "TITLE_CACHE", cache_path), \
             patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-title-upgrade"}, clear=False), \
             patch("modules.LLM_Handler.ask_llm", side_effect=fake_ask_llm):
            for index, scenario in enumerate(SCENARIOS, start=1):
                context = {
                    "config": {"quality_tiers": {"use_ai_titles": True}},
                    "creator_brain": "Billy is direct, funny, practical, and reacts honestly.",
                    **scenario["context"],
                }
                clip_result = {
                    "clip_number": index,
                    "trigger": scenario["trigger"],
                    "score": scenario["score"],
                }
                try:
                    generated, hashtags = titles.generate_titles(
                        trigger=scenario["trigger"],
                        game="Marvel Rivals",
                        score=scenario["score"],
                        context=context,
                    )
                    if len(generated) < 3:
                        raise AssertionError("Expected at least 3 generated title options")
                    if not all(title.strip() for title in generated):
                        raise AssertionError("Generated titles must not be blank")
                    if not any(tag == "#MarvelRivals" for tag in hashtags):
                        raise AssertionError("Expected #MarvelRivals in hashtags")
                    clip_result.update({
                        "status": "passed",
                        "title": generated[0],
                        "hashtags": hashtags,
                    })
                    report["passed"] += 1
                except Exception as exc:
                    clip_result.update({"status": "failed", "error": str(exc)})
                    report["failed"] += 1
                report["results"].append(clip_result)

    output_path = ROOT / "data" / "title_upgrade_10_clip_test.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Title upgrade smoke test: {report['passed']}/{report['scenario_count']} clips passed")
    print(f"Report: {output_path}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
