#!/usr/bin/env python3
"""
modules/Nexus_Creator.py — Gemini-powered Content Creator Consultant
=====================================================================
Nexus is Bolt's strategic brain for content decisions. It uses Google's
Gemini API to provide actionable advice on hooks, monetization, engagement,
and content strategy across Tech, Gaming, Skincare, and Beauty verticals.

Usage:
    from modules.Nexus_Creator import NexusCreator

    nexus = NexusCreator()
    advice = nexus.consult(
        topic="Hades 2 highlight clips",
        context="Posted 5 Hades 2 clips, 2,393 views across TikTok + YouTube"
    )
    print(advice)

CLI:
    python3 -m modules.Nexus_Creator "best time to post skincare reviews"
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
NEXUS_LOG_FILE = DATA_DIR / "nexus_advice.jsonl"


# ── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Nexus Creator, an expert Content Creator Consultant specializing in Tech, Gaming, Skincare, and Beauty products.

You help Bolt (an AI content assistant) and its creator Billy make smart, strategic decisions about what content to make, how to post it, and how to grow.

Your advice must be:
- Actionable and specific (no vague platitudes)
- Concise, punchy, formatted in Markdown
- Grounded in current platform trends (TikTok, YouTube Shorts, X/Twitter, Instagram Reels)
- Tailored to the creator's actual performance data when provided

Focus areas:
1. Content Hooks & Sensory Visual Storytelling (formulation textures, dermal patch trials, hardware macros, gameplay moments)
2. Monetization (Amazon Storefront / Affiliate links, brand sponsorships)
3. Audience Engagement & Credibility/Trust parameters
4. Testing/Review workflow optimization (pH levels, adverse reaction logs, safety protocols)
5. Cross-platform posting strategy (timing, formatting, hashtag strategy)
6. What to make NEXT based on performance data

When given performance data, identify patterns and recommend the next 3-5 pieces of content to create.
"""


# ── Nexus Creator ─────────────────────────────────────────────────────────────


class NexusCreator:
    """Gemini-powered content strategy consultant."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model
        self._client = None

        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY not set. Add it to .env or pass api_key directly."
            )

    def _get_client(self):
        """Lazy-load the Gemini client (google-genai SDK)."""
        if self._client is None:
            try:
                from google import genai

                self._client = genai.Client(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "google-genai package not installed. "
                    "Run: pip install google-genai"
                )
        return self._client

    def consult(
        self,
        topic: str,
        context: str = "",
        extra_instructions: str = "",
    ) -> Dict[str, Any]:
        """
        Ask Nexus for strategic content advice.

        Args:
            topic: What you want advice about (e.g. "Hades 2 content strategy")
            context: Relevant background — performance data, what's been posted, etc.
            extra_instructions: Optional additional instructions to refine the response.

        Returns:
            Dict with:
                - advice: The strategic advice (Markdown string)
                - topic: What was asked
                - timestamp: When it was generated
                - model: Which Gemini model was used
        """
        client = self._get_client()

        # Build the user prompt
        user_prompt = f"""Provide actionable, strategic advice for the following topic: "{topic}".

Current Context: {context}
"""
        if extra_instructions:
            user_prompt += f"\nAdditional Instructions: {extra_instructions}\n"

        user_prompt += """
Focus on:
1. Content Hooks & Sensory Visual Storytelling (especially formulation textures, dermal patch trial logs, or hardware macros)
2. Monetization (Amazon Storefront / Affiliate links, brand sponsorships)
3. Audience Engagement & Credibility/Trust parameters
4. Testing/Review workflow optimization (pH levels, adverse reaction logs, safety protocols)

Keep the response concise, punchy, and formatted in Markdown.
"""

        try:
            response = client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                },
            )
            advice_text = response.text
        except Exception as e:
            advice_text = f"Nexus unavailable: {str(e)[:120]}"
            return {
                "advice": advice_text,
                "topic": topic,
                "context": context,
                "timestamp": datetime.now().isoformat(),
                "model": self.model,
                "error": str(e)[:200],
            }

        result = {
            "advice": advice_text,
            "topic": topic,
            "context": context,
            "timestamp": datetime.now().isoformat(),
            "model": self.model,
        }

        # Log the advice for future reference
        self._log_advice(result)

        return result

    def suggest_next_content(
        self,
        performance_data: Dict[str, Any],
        content_lanes: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze performance data and suggest what content to make next.

        Args:
            performance_data: Dict with view counts, engagement metrics, etc.
            content_lanes: List of content types (e.g. ["gaming", "skincare"])

        Returns:
            Nexus advice dict with next content recommendations
        """
        context_parts = []
        context_parts.append(f"Performance data: {json.dumps(performance_data, indent=2)}")

        if content_lanes:
            context_parts.append(f"Content lanes: {', '.join(content_lanes)}")

        context_parts.append(
            "Based on this data, recommend the next 3-5 pieces of content to create. "
            "For each, include: title concept, platform, posting time window, and why."
        )

        context = "\n".join(context_parts)
        return self.consult(
            topic="What content should I make next?",
            context=context,
            extra_instructions="Be specific. Give me 3-5 concrete content ideas ranked by expected impact.",
        )

    def optimize_caption(
        self,
        clip_name: str,
        clip_description: str = "",
        platform: str = "tiktok",
    ) -> Dict[str, Any]:
        """
        Get an optimized caption + hashtag set for a specific clip.

        Args:
            clip_name: Name of the clip file
            clip_description: What happens in the clip
            platform: Target platform (tiktok, youtube_shorts, x, instagram_reels)

        Returns:
            Nexus advice with optimized caption and hashtags
        """
        platform_specs = {
            "tiktok": "TikTok — max 150 chars caption, 3-5 hashtags, emoji encouraged",
            "youtube_shorts": "YouTube Shorts — max 100 chars title, 3-5 hashtags in description",
            "x": "X/Twitter — max 280 chars, 1-2 hashtags, punchy",
            "instagram_reels": "Instagram Reels — max 220 chars, 5-10 hashtags, emoji encouraged",
        }

        spec = platform_specs.get(platform.lower(), platform_specs["tiktok"])

        return self.consult(
            topic=f"Optimize caption for {clip_name} on {platform}",
            context=f"Clip: {clip_name}\nDescription: {clip_description}\nPlatform specs: {spec}",
            extra_instructions=(
                "Give me: 1) The caption text (ready to paste) 2) 3-5 hashtags 3) "
                "A one-line hook/teaser for the video description. Keep it concise."
            ),
        )

    def _log_advice(self, result: Dict[str, Any]) -> None:
        """Append advice to the nexus advice log for future reference."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(NEXUS_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(result) + "\n")
        except Exception as e:
            print(f"Nexus log error (non-fatal): {e}")


# ── CLI ───────────────────────────────────────────────────────────────────────


def _load_performance_data() -> Dict[str, Any]:
    """Load recent performance data from Bolt's data files."""
    perf_file = DATA_DIR / "performance_outcomes.jsonl"
    if not perf_file.exists():
        return {}

    entries = []
    try:
        with open(perf_file, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass

    return {"recent_posts": entries[-20:] if entries else []}


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Nexus Creator — AI Content Strategy Consultant for Bolt"
    )
    parser.add_argument(
        "topic",
        nargs="?",
        default=None,
        help="Topic to get advice about",
    )
    parser.add_argument(
        "--context",
        "-c",
        default="",
        help="Additional context (performance data, what's been posted, etc.)",
    )
    parser.add_argument(
        "--next",
        action="store_true",
        help="Suggest next content based on performance data",
    )
    parser.add_argument(
        "--caption",
        metavar="CLIP_NAME",
        help="Get optimized caption for a clip (add --desc for description)",
    )
    parser.add_argument(
        "--desc",
        default="",
        help="Clip description for caption optimization",
    )
    parser.add_argument(
        "--platform",
        "-p",
        default="tiktok",
        choices=["tiktok", "youtube_shorts", "x", "instagram_reels"],
        help="Target platform for caption optimization",
    )
    parser.add_argument(
        "--model",
        default="gemini-2.5-flash",
        help="Gemini model to use (default: gemini-2.5-flash)",
    )

    args = parser.parse_args()

    try:
        nexus = NexusCreator(model=args.model)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except ImportError as e:
        print(f"Error: {e}")
        sys.exit(1)

    if args.next:
        print("📊 Loading performance data...")
        perf_data = _load_performance_data()
        print(f"   Found {len(perf_data.get('recent_posts', []))} recent posts\n")
        result = nexus.suggest_next_content(
            performance_data=perf_data,
            content_lanes=["gaming", "skincare"],
        )
    elif args.caption:
        print(f"✍️  Optimizing caption for: {args.caption}\n")
        result = nexus.optimize_caption(
            clip_name=args.caption,
            clip_description=args.desc,
            platform=args.platform,
        )
    elif args.topic:
        print(f"🧠 Nexus Creator — Consulting on: {args.topic}\n")
        result = nexus.consult(topic=args.topic, context=args.context)
    else:
        parser.print_help()
        return

    print("=" * 60)
    print(result.get("advice", "No advice returned."))
    print("=" * 60)
    print(f"\n📍 Model: {result.get('model')}")
    print(f"🕐 {result.get('timestamp')}")


if __name__ == "__main__":
    main()