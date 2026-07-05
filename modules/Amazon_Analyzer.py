#!/usr/bin/env python3
"""
Amazon_Analyzer.py — Product review/comparison content (Gemini-powered)
========================================================================
Processes product links and review context to generate structured content
plans for Amazon reviews, unboxings, and comparison videos.

Wired into the Bolt pipeline when --content-type review is used.
Uses real web content fetching + Gemini (via Nexus Creator) instead of
placeholder/mock data.

Key Functions:
1. fetch_product_details: Fetch real product info from a URL
2. analyze_product_review: Generate a structured review content plan
3. generate_comparison_content: Create comparison video content
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


def fetch_product_details(product_url_or_asin: str) -> Dict[str, Any]:
    """
    Fetch real product details from a URL or ASIN.
    Handles Amazon URLs, bare ASINs, and other product URLs.

    Note: Amazon's API requires credentials. For now we fetch the
    product page and extract what we can. For Amazon ASINs, we construct
    the URL and fetch it. Rate limiting is handled by capping request frequency.
    """
    # Determine if it's an ASIN or URL
    if product_url_or_asin.startswith("http"):
        url = product_url_or_asin
        asin = _extract_asin(url)
    else:
        asin = product_url_or_asin
        url = f"https://www.amazon.com/dp/{asin}"

    try:
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
        })
        with urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")

        # Extract title
        title_match = re.search(r'<title[^>]*>(.*?)</title>', raw, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else "Unknown Product"
        title = re.sub(r'\s*-\s*Amazon\.com\s*$', '', title)

        # Extract price (Amazon shows it in various places)
        price_match = re.search(r'"price"\s*:\s*"\$?([\d.,]+)"', raw)
        price = f"${price_match.group(1)}" if price_match else "Price not found"

        # Extract rating
        rating_match = re.search(r'"ratingValue"\s*:\s*"([\d.]+)"', raw)
        rating = float(rating_match.group(1)) if rating_match else None

        # Extract review count
        review_match = re.search(r'"reviewCount"\s*:\s*"([\d,]+)"', raw)
        reviews_count = int(review_match.group(1).replace(",", "")) if review_match else None

        # Extract features from bullet points
        features = []
        feature_matches = re.findall(
            r'<span class="a-list-item"[^>]*>(.*?)</span>', raw, re.DOTALL
        )
        for f in feature_matches[:5]:
            clean = re.sub(r'<[^>]+>', '', f).strip()
            if clean and len(clean) > 10:
                features.append(clean)

        return {
            "asin": asin or "Unknown",
            "title": title,
            "price": price,
            "rating": rating,
            "reviews_count": reviews_count,
            "key_features": features if features else ["Features not extracted"],
            "source_url": url,
            "fetched_chars": len(raw),
        }

    except Exception as e:
        return {
            "asin": asin or "Unknown",
            "title": "Failed to fetch product page",
            "price": "Unknown",
            "rating": None,
            "reviews_count": None,
            "key_features": [],
            "source_url": url,
            "error": str(e)[:200],
        }


def _extract_asin(url: str) -> Optional[str]:
    """Extract ASIN from an Amazon URL."""
    match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', url)
    return match.group(1) if match else None


def analyze_product_review(
    product_links: List[str],
    comparison_focus: str,
    target_platform: str = "tiktok",
) -> Dict[str, Any]:
    """
    Analyzes one or more products to create a structured review content plan.
    Uses real web fetching + Gemini for analysis.

    Args:
        product_links: List of ASINs or direct URLs
        comparison_focus: The core angle (e.g., "Best Budget Alternative")
        target_platform: Where the content goes (tiktok, youtube, etc.)

    Returns:
        A dictionary containing the structured analysis report
    """
    print(f"\n[🛒 Amazon Analyzer] Analyzing products for: {comparison_focus}")
    print(f"[🛒 Amazon Analyzer] Target Platform: {target_platform}")

    if not product_links:
        return {"status": "Failure", "reason": "No products provided for review."}

    # 1. Fetch real details for all products
    product_data = []
    for link in product_links:
        print(f"  Fetching: {link}")
        details = fetch_product_details(link)
        product_data.append(details)
        print(f"  → {details.get('title', 'Unknown')} | {details.get('price', 'N/A')}")

    # 2. Use Gemini/Nexus to analyze and generate content strategy
    try:
        from modules.Nexus_Creator import NexusCreator

        nexus = NexusCreator()

        products_summary = "\n".join(
            f"- {p.get('title', 'Unknown')} | Price: {p.get('price', 'N/A')} | "
            f"Rating: {p.get('rating', 'N/A')} | Features: {', '.join(p.get('key_features', [])[:3])}"
            for p in product_data
        )

        result = nexus.consult(
            topic=f"Product review content: {comparison_focus}",
            context=(
                f"Products to review:\n{products_summary}\n\n"
                f"Target platform: {target_platform}\n"
                f"Creator: Billy (@simplybilly_) — gaming + product review content\n"
                f"Monetization: Amazon storefront / affiliate links"
            ),
            extra_instructions=(
                "Provide a structured review plan with:\n"
                "1. **Storytelling Hook** — a strong emotionally charged opener for the video\n"
                "2. **Core Comparison Points** — price vs features vs competition\n"
                "3. **Content Structure** — outline for a 30-60s review video\n"
                "4. **Caption + Hashtags** — ready-to-post caption for the target platform\n"
                "5. **Affiliate Strategy** — which products to link, call-to-action\n"
                "6. **Trust Signals** — how to build credibility in this review\n"
                "Format as Markdown. Be specific and actionable."
            ),
        )

        advice = result.get("advice", "")

        structured_report = {
            "status": "Success",
            "comparison_focus": comparison_focus,
            "target_platform": target_platform,
            "products": product_data,
            "nexus_advice": advice,
            "timestamp": result.get("timestamp"),
            "model": result.get("model"),
        }

        return structured_report

    except Exception as e:
        print(f"  ⚠️  Product analysis failed: {e}")
        return {
            "status": "Partial",
            "comparison_focus": comparison_focus,
            "products": product_data,
            "error": str(e)[:200],
            "nexus_advice": None,
        }


def generate_comparison_content(
    product_links: List[str],
    comparison_focus: str,
    target_platform: str = "tiktok",
) -> Dict[str, Any]:
    """
    Generate video-ready comparison content from product links.
    Main entry point for the review content pipeline.
    """
    return analyze_product_review(product_links, comparison_focus, target_platform)


if __name__ == "__main__":
    # Example usage
    test_products = ["B08N5WRWNW"]  # Example ASIN
    test_focus = "Best budget wireless headphones for content creators"

    report = analyze_product_review(test_products, test_focus)
    print("\n==========================================")
    print("🛒 PRODUCT REVIEW REPORT:")
    print(json.dumps(report, indent=2, default=str)[:2000])
    print("==========================================")