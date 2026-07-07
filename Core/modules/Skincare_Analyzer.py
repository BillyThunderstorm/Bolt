#!/usr/bin/env python3
"""
Skincare_Analyzer.py — Skincare/Beauty content analysis (Gemini-powered)
========================================================================
Processes product info and skincare context to generate actionable content
strategies, ingredient analysis, and routine recommendations.

Wired into the Bolt pipeline when --content-type skincare is used.
Uses Gemini (via Nexus Creator) for real intelligence instead of hardcoded data.

Key Functions:
1. analyze_skincare_routine: Analyze products + generate a structured review plan
2. fetch_ingredient_data: Get real ingredient info via Gemini
3. generate_review_content: Create video-ready content from skincare analysis
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def fetch_ingredient_data(ingredient_name: str) -> Dict[str, Any]:
    """
    Fetch real ingredient data using Gemini.
    Replaces the old hardcoded placeholder database.
    """
    try:
        from modules.Nexus_Creator import NexusCreator

        nexus = NexusCreator()
        result = nexus.consult(
            topic=f"Ingredient analysis: {ingredient_name}",
            context=f"Provide scientific info about {ingredient_name} for skincare content.",
            extra_instructions=(
                f"Return a JSON object with these keys: category, effect, strength (Low/Medium/High), "
                f"precautions (list of strings), and benefits (list of strings). "
                f"Be scientifically accurate. Only return the JSON, no markdown."
            ),
        )

        advice = result.get("advice", "")
        # Try to parse JSON from the advice
        try:
            # Strip markdown code fences if present
            clean = advice.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            data = json.loads(clean)
            return data
        except (json.JSONDecodeError, IndexError):
            # Fallback: return structured text if JSON parse fails
            return {
                "category": "Unknown",
                "effect": advice[:200] if advice else "Unknown",
                "strength": "N/A",
                "precautions": ["Consult a dermatologist."],
                "benefits": [],
                "raw_advice": advice,
            }
    except Exception as e:
        print(f"  ⚠️  Skincare ingredient lookup failed: {e}")
        return {
            "category": "Unknown",
            "effect": "Lookup failed",
            "strength": "N/A",
            "precautions": ["Consult a dermatologist."],
            "benefits": [],
            "error": str(e)[:100],
        }


def analyze_skincare_routine(
    product_list: List[Dict[str, Any]],
    user_goal: str,
    target_platform: str = "tiktok",
) -> Dict[str, Any]:
    """
    Analyzes a list of products against a user goal to create a structured
    routine plan and content strategy. Uses Gemini for real analysis.

    Args:
        product_list: [{name: "Product A", ingredients: ["Ingredient X", ...], type: "Serum"}, ...]
        user_goal: The core purpose (e.g., "Anti-acne routine for oily skin")
        target_platform: Where the content goes (tiktok, youtube, etc.)

    Returns:
        A dictionary containing the structured analysis report with
        content hooks, ingredient analysis, and posting strategy.
    """
    print(f"\n[🧪 Skincare Analyzer] Analyzing routine for: {user_goal}")

    if not product_list:
        return {"status": "Failure", "reason": "No products provided for analysis."}

    try:
        from modules.Nexus_Creator import NexusCreator

        nexus = NexusCreator()

        # Build context from product list
        products_summary = "\n".join(
            f"- {p.get('name', 'Unknown')}: {', '.join(p.get('ingredients', []))} "
            f"({p.get('type', 'unknown type')})"
            for p in product_list
        )

        result = nexus.consult(
            topic=f"Skincare content strategy: {user_goal}",
            context=(
                f"Products to review:\n{products_summary}\n\n"
                f"Target platform: {target_platform}\n"
                f"Creator: Billy (@simplybilly_) — gaming + skincare content\n"
                f"Goal: Create engaging skincare review content that builds credibility"
            ),
            extra_instructions=(
                "Provide a structured analysis with:\n"
                "1. **Key Findings** — ingredient interactions, warnings, standout products\n"
                "2. **Content Hooks** — 3-5 video hook ideas for these products\n"
                "3. **Routine Plan** — AM/PM routine using these products\n"
                "4. **Safety Notes** — any ingredient conflicts or precautions\n"
                "5. **Posting Strategy** — best platform, timing, caption approach\n"
                "Format as Markdown. Be specific and actionable."
            ),
        )

        advice = result.get("advice", "")

        structured_report = {
            "status": "Success",
            "user_goal_addressed": user_goal,
            "target_platform": target_platform,
            "products_analyzed": len(product_list),
            "nexus_advice": advice,
            "timestamp": result.get("timestamp"),
            "model": result.get("model"),
            "products": product_list,
        }

        return structured_report

    except Exception as e:
        print(f"  ⚠️  Skincare analysis failed, using fallback: {e}")
        return {
            "status": "Partial",
            "user_goal_addressed": user_goal,
            "error": str(e)[:200],
            "products": product_list,
            "nexus_advice": None,
            "summary_hook": f"A custom routine based on {user_goal} using {len(product_list)} products.",
            "key_findings": ["Analysis requires GEMINI_API_KEY to be set."],
            "suggested_routine": {"AM": [], "PM": []},
        }


def generate_review_content(
    product_list: List[Dict[str, Any]],
    review_angle: str,
    target_platform: str = "tiktok",
) -> Dict[str, Any]:
    """
    Generate video-ready content from a skincare product review.
    This is the main entry point for the skincare content pipeline.

    Args:
        product_list: Products being reviewed
        review_angle: The angle/hook (e.g., "Best budget vitamin C serum")
        target_platform: Where it'll be posted

    Returns:
        Content plan with hooks, script outline, captions, and hashtags
    """
    return analyze_skincare_routine(
        product_list=product_list,
        user_goal=review_angle,
        target_platform=target_platform,
    )


if __name__ == "__main__":
    # Example usage with real data
    test_products = [
        {
            "name": "The Ordinary Niacinamide 10%",
            "ingredients": ["Niacinamide", "Zinc", "Water"],
            "type": "Serum",
        },
        {
            "name": "CeraVe PM Moisturizer",
            "ingredients": ["Niacinamide", "Ceramide", "Hyaluronic Acid"],
            "type": "Moisturizer",
        },
    ]
    test_goal = "Budget-friendly barrier repair routine for sensitive skin"

    report = analyze_skincare_routine(test_products, test_goal)
    print("\n==========================================")
    print("🧪 SKINCARE ANALYSIS REPORT:")
    print(json.dumps(report, indent=2, default=str)[:2000])
    print("==========================================")