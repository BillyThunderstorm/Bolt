#!/usr/bin/env python3
"""Minimal Gemini REST client (free-tier Google AI Studio keys).

Uses plain HTTPS + `requests` so Bolt does not depend on the optional
`google-genai` package being installed in the active venv.
"""

from __future__ import annotations

import os
from typing import Optional

import requests

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
API_BASE = "https://generativelanguage.googleapis.com/v1beta"


def has_gemini_key() -> bool:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return bool(key)


def ask_gemini(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_output_tokens: int = 1024,
    json_mode: bool = False,
    timeout: float = 45.0,
) -> str:
    """
    Call Gemini generateContent. Returns response text, or a short
    ``LLM unavailable: …`` string on failure (same convention as LLM_Handler).
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return "LLM unavailable: GEMINI_API_KEY not set"

    use_model = model or DEFAULT_MODEL
    url = f"{API_BASE}/models/{use_model}:generateContent"

    user_text = prompt
    if system:
        user_text = f"{system.strip()}\n\n{prompt}"

    body: dict = {
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        },
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"

    try:
        resp = requests.post(
            url,
            params={"key": api_key},
            json=body,
            timeout=timeout,
        )
        if resp.status_code != 200:
            # Avoid leaking key material; keep body short for logs.
            detail = (resp.text or "")[:180].replace("\n", " ")
            return f"LLM unavailable: Gemini HTTP {resp.status_code}: {detail}"

        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            # Blocked / empty — surface finish reason when present.
            feedback = data.get("promptFeedback") or {}
            reason = feedback.get("blockReason") or "empty candidates"
            return f"LLM unavailable: Gemini returned no content ({reason})"

        parts = (candidates[0].get("content") or {}).get("parts") or []
        texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
        text = "".join(texts).strip()
        if not text:
            return "LLM unavailable: Gemini returned empty text"
        return text
    except requests.Timeout:
        return "LLM unavailable: Gemini request timed out"
    except Exception as exc:
        return f"LLM unavailable: {str(exc)[:160]}"
