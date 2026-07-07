#!/usr/bin/env python3
"""
AI_Analyzer.py — Tech/AI content analysis (Gemini-powered)
==========================================================
Processes URLs and tech content sources to generate structured analysis,
talking points, and video scripts.

Wired into the Bolt pipeline when --content-type tech is used.
Uses real web_fetch + Gemini (via Nexus Creator) instead of placeholder data.

Key Functions:
1. analyze_tech_source: Analyze a URL based on a query and parameters
2. fetch_and_clean_url: Fetch real content from a URL
3. generate_tech_content: Create video-ready content from tech analysis
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


def fetch_and_clean_url(url: str, extract_mode: str = "markdown") -> str:
    """
    Fetch real content from a URL.
    Uses urllib to download, then strips HTML to readable text.
    """
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")

        if extract_mode == "markdown":
            # Simple HTML to text conversion
            # Remove scripts and styles
            raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=re.DOTALL | re.IGNORECASE)
            # Remove tags
            text = re.sub(r"<[^>]+>", " ", raw)
            # Clean whitespace
            text = re.sub(r"\s+", " ", text).strip()
            # Decode common entities
            text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            text = text.replace("&#39;", "'").replace("&quot;", '"')
            return text[:10000]  # Cap at 10k chars
        return raw[:10000]
    except Exception as e:
        return f"Error fetching {url}: {str(e)[:200]}"


def analyze_tech_source(
    url: str,
    query: str,
    params: List[str],
    target_platform: str = "tiktok",
) -> Dict[str, Any]:
    """
    Analyzes a tech/AI source URL based on a specific query and required parameters.
    Uses real web content + Gemini for analysis.

    Args:
        url: The URL of the source material (e.g., research paper link, blog post)
        query: The user's high-level goal (e.g., "Compare GPT-4o and Claude 3")
        params: Parameters to focus on (e.g., ["Cost", "Speed", "Safety"])
        target_platform: Where the content will be posted

    Returns:
        A dictionary containing the structured analysis report
    """
    print(f"\n[⚡ AI Analyzer] Analyzing: {url}")
    print(f"[⚡ AI Analyzer] Focus: {query}")
    print(f"[⚡ AI Analyzer] Parameters: {', '.join(params)}")

    # 1. Fetch real content from the URL
    raw_content = fetch_and_clean_url(url)

    if raw_content.startswith("Error"):
        return {"status": "Failed", "reason": raw_content}

    print(f"[⚡ AI Analyzer] Fetched {len(raw_content)} chars from URL")

    # 2. Use Gemini/Nexus to analyze the content
    try:
        from modules.Nexus_Creator import NexusCreator

        nexus = NexusCreator()

        result = nexus.consult(
            topic=f"Tech content analysis: {query}",
            context=(
                f"Source URL: {url}\n"
                f"Raw content (truncated):\n{raw_content[:5000]}\n\n"
                f"Focus parameters: {', '.join(params)}\n"
                f"Target platform: {target_platform}\n"
                f"Creator: Billy (@simplybilly_) — tech + gaming content"
            ),
            extra_instructions=(
                "Provide a structured analysis with:\n"
                "1. **Analysis Summary** — key findings from the source\n"
                "2. **Key Comparisons** — for each focus parameter, what does the source say?\n"
                "3. **Scripting Notes** — 3 'wow factor' hooks for a video script\n"
                "4. **Content Recommendations** — what to make next based on this source\n"
                "Format as Markdown. Be specific and cite the source content."
            ),
        )

        advice = result.get("advice", "")

        structured_report = {
            "status": "Success",
            "source_url": url,
            "query": query,
            "parameters": params,
            "nexus_advice": advice,
            "content_fetched_chars": len(raw_content),
            "timestamp": result.get("timestamp"),
            "model": result.get("model"),
        }

        return structured_report

    except Exception as e:
        print(f"  ⚠️  Tech analysis failed: {e}")
        return {
            "status": "Partial",
            "source_url": url,
            "query": query,
            "raw_content_preview": raw_content[:500],
            "error": str(e)[:200],
            "nexus_advice": None,
        }


def generate_tech_content(
    url: str,
    query: str,
    params: List[str] = None,
    target_platform: str = "tiktok",
) -> Dict[str, Any]:
    """
    Generate video-ready content from a tech source URL.
    Main entry point for the tech content pipeline.
    """
    params = params or ["Performance", "Cost", "Features"]
    return analyze_tech_source(url, query, params, target_platform)


if __name__ == "__main__":
    # Example usage
    test_url = "https://blog.google/technology/ai/google-gemini-ai/"
    test_query = "What makes Gemini different from other AI models?"
    test_params = ["Speed", "Cost", "Capabilities"]

    report = analyze_tech_source(test_url, test_query, test_params)
    print("\n==========================================")
    print("⚡ TECH ANALYSIS REPORT:")
    print(json.dumps(report, indent=2, default=str)[:2000])
    print("==========================================")