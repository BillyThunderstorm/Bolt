#!/usr/bin/env python3
"""
Amazon_Analyzer.py — Product review/comparison content (Gemini-powered)
========================================================================
Processes product links and review context to generate structured content
plans for Amazon reviews, unboxings, and comparison videos.

Wired into the Bolt pipeline when --content-type review is used
(`bolt recordings … --content-type review`). Also: `bolt amazon <ASIN|URL>`.
Uses real web content fetching + Nexus (Ollama / optional paid) instead of
placeholder/mock data. Fetch or Nexus failure = warn + Partial / continue.

Key Functions:
1. fetch_product_details: Fetch real product info from a URL
2. analyze_product_review: Generate a structured review content plan
3. generate_comparison_content: Create comparison video content
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Dict, List, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


def _looks_blocked(raw: str, title: str) -> Optional[str]:
    """Detect Amazon bot-check / soft-block pages. Never raises."""
    blob = f"{title}\n{raw[:8000]}".lower()
    markers = (
        ("robot check", "Amazon unavailable: robot check / captcha page"),
        ("enter the characters you see", "Amazon unavailable: captcha challenge"),
        ("api-services-support@amazon.com", "Amazon unavailable: automated access blocked"),
        ("sorry, we just need to make sure you're not a robot",
         "Amazon unavailable: robot check / captcha page"),
        ("to discuss automated access to amazon data",
         "Amazon unavailable: automated access blocked"),
    )
    for needle, msg in markers:
        if needle in blob:
            return msg
    # Very short HTML with no product signals → likely interstitial
    if len(raw) < 2500 and "asin" not in blob and "dp/" not in blob:
        if "amazon" in blob:
            return "Amazon unavailable: page too thin (likely block or redirect)"
    return None


def _failure_payload(
    *,
    asin: Optional[str],
    url: str,
    error: str,
    title: str = "Failed to fetch product page",
) -> Dict[str, Any]:
    return {
        "ok": False,
        "asin": (asin or "").strip().upper() or "Unknown",
        "title": title,
        "price": "Unknown",
        "rating": None,
        "reviews_count": None,
        "key_features": [],
        "source_url": url,
        "error": error[:240],
    }


def fetch_product_details(product_url_or_asin: str) -> Dict[str, Any]:
    """
    Fetch real product details from a URL or ASIN (HTML scrape — no PA-API).

    Soft-fails: never raises. On network / captcha / parse failure returns
    ``ok=False`` + ``error`` (prefix ``Amazon unavailable:`` when blocked).
    Callers (store verify, review pipeline) keep going.
    """
    raw_in = (product_url_or_asin or "").strip()
    if not raw_in:
        return _failure_payload(
            asin=None,
            url="",
            error="Amazon unavailable: empty ASIN/URL",
        )

    # Determine if it's an ASIN or URL
    if raw_in.startswith("http"):
        url = raw_in
        asin = _extract_asin(url)
    else:
        asin = raw_in.upper()
        url = f"https://www.amazon.com/dp/{asin}"

    try:
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        })
        with urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")

        # Extract title
        title_match = re.search(r'<title[^>]*>(.*?)</title>', raw, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""
        title = re.sub(r'\s*-\s*Amazon\.com\s*$', '', title)
        title = re.sub(r'\s+', ' ', title).strip()

        blocked = _looks_blocked(raw, title)
        if blocked:
            return _failure_payload(asin=asin, url=url, error=blocked, title=title or "Blocked")

        if not title or title.lower() in {"amazon.com", "amazon"}:
            return _failure_payload(
                asin=asin,
                url=url,
                error="Amazon unavailable: no product title on page",
                title="Unknown Product",
            )

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
            "ok": True,
            "asin": asin or "Unknown",
            "title": title,
            "price": price,
            "rating": rating,
            "reviews_count": reviews_count,
            "key_features": features if features else ["Features not extracted"],
            "source_url": url,
            "fetched_chars": len(raw),
            "error": None,
        }

    except Exception as e:
        return _failure_payload(
            asin=asin,
            url=url,
            error=f"Amazon unavailable: {type(e).__name__}: {e}",
        )


def status() -> Dict[str, Any]:
    """
    Store / ASIN-verify readiness. Never raises.
    HTML scrape only (no PA-API). ready=True means the helper is callable;
    a live Amazon fetch may still soft-fail when Amazon blocks bots.
    """
    return {
        "ready": True,
        "method": "html_scrape",
        "pa_api": False,
        "hint": (
            "ASIN verify via HTML scrape (no PA-API). "
            "bolt store add --asin B0… verifies by default; Amazon blocks → "
            "soft-fail (item still saved, verify_status=error). "
            "Review content path: bolt amazon <ASIN> --fetch-only"
        ),
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


def main(argv: Optional[list[str]] = None) -> int:
    """CLI: `bolt amazon <ASIN|URL> […]` — fetch + optional Nexus review plan."""
    parser = argparse.ArgumentParser(
        prog="bolt amazon",
        description=(
            "Amazon product fetch + review content plan (Amazon_Analyzer). "
            "Same enrichment bot.py runs for --content-type review."
        ),
    )
    parser.add_argument(
        "products",
        nargs="+",
        help="One or more ASINs or product URLs",
    )
    parser.add_argument(
        "--focus",
        "-f",
        default="Honest product review for content creators",
        help="Comparison / review angle (default: honest product review)",
    )
    parser.add_argument(
        "--platform",
        "-p",
        default="tiktok",
        help="Target platform for captions (default: tiktok)",
    )
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        help="Only fetch product page details (skip Nexus advice)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON report",
    )
    args = parser.parse_args(argv)

    if args.fetch_only:
        rows = [fetch_product_details(p) for p in args.products]
        if args.json:
            print(json.dumps(rows, indent=2, default=str))
        else:
            for d in rows:
                title = d.get("title") or "Unknown"
                price = d.get("price") or "?"
                err = d.get("error")
                flag = "✓" if d.get("ok") else "○"
                print(f"{flag}  {d.get('asin', '?')}  {title}  |  {price}")
                if err:
                    print(f"     {err}")
        # Exit 0 even on fetch errors — soft-fail (page blocks are common).
        return 0

    report = generate_comparison_content(
        product_links=list(args.products),
        comparison_focus=str(args.focus),
        target_platform=str(args.platform),
    )
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        status = (report or {}).get("status", "unknown")
        print(f"\n=== Amazon review plan ({status}) ===\n")
        products = (report or {}).get("products") or []
        for d in products:
            print(
                f"- {d.get('asin', '?')}: {d.get('title', 'Unknown')} "
                f"| {d.get('price', '?')}"
            )
            if d.get("error"):
                print(f"  ⚠️  fetch: {d['error']}")
        advice = (report or {}).get("nexus_advice") or ""
        if advice:
            print("\n--- Nexus advice ---\n")
            print(advice[:4000])
        elif (report or {}).get("error"):
            print(f"\n⚠️  {(report or {}).get('error')}")
        else:
            print(
                "\n(no Nexus advice — start Ollama, or set NEXUS_ALLOW_PAID "
                "+ XAI_API_KEY; fetch results above still usable)"
            )
    return 0 if (report or {}).get("status") in ("Success", "Partial") else 1


if __name__ == "__main__":
    sys.exit(main())