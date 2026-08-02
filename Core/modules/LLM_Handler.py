#!/usr/bin/env python3
"""
modules/LLM_Handler.py — Multi-provider LLM wrapper (OpenAI + xAI/Grok)
=======================================================================
Single entry point for all Bolt LLM calls.

Environment variables:
  BOLT_LLM_PROVIDER   openai | xai          (default: openai)
  BOLT_LLM_FALLBACK   openai | xai | none   (default: openai)
  OPENAI_API_KEY
  XAI_API_KEY
  BOLT_OPENAI_MODEL   (default: gpt-4o-mini)
  BOLT_XAI_MODEL      (default: grok-4.5)

Usage:
  from modules.LLM_Handler import ask_llm

  reply = ask_llm("What should I post today?")
  reply = ask_llm(
      "Summarize this",
      system="You are Bolt...",
      history=[{"role": "user", "content": "..."}, ...],
      max_tokens=200,
      temperature=0.85,
  )
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

_clients: Dict[str, Any] = {}


def _get_client(provider: str):
    """Lazy-load and cache the OpenAI-compatible client for a provider."""
    provider = provider.lower().strip()
    if provider in _clients:
        return _clients[provider]

    try:
        from openai import OpenAI
    except ImportError:
        print("LLM Handler: openai package not installed")
        return None

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("LLM Handler: OPENAI_API_KEY not set")
            return None
        client = OpenAI(api_key=api_key)

    elif provider == "xai":
        api_key = os.getenv("XAI_API_KEY")
        if not api_key:
            print("LLM Handler: XAI_API_KEY not set")
            return None
        # xAI is fully OpenAI-compatible
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1",
        )

    else:
        print(f"LLM Handler: unknown provider '{provider}'")
        return None

    _clients[provider] = client
    return client


def _default_model(provider: str) -> str:
    if provider == "xai":
        return os.getenv("BOLT_XAI_MODEL", "grok-4.5")
    return os.getenv("BOLT_OPENAI_MODEL", "gpt-4o-mini")


def _resolve_providers(
    preferred: Optional[str] = None,
) -> List[str]:
    """
    Return ordered list of providers to try.
    Example: preferred=xai, fallback=openai → ["xai", "openai"]
    """
    preferred = (preferred or os.getenv("BOLT_LLM_PROVIDER", "openai")).lower().strip()
    fallback = os.getenv("BOLT_LLM_FALLBACK", "openai").lower().strip()

    order = [preferred]
    if fallback and fallback != "none" and fallback != preferred:
        order.append(fallback)
    return order


def ask_llm(
    prompt: str,
    *,
    system: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    max_tokens: int = 400,
    temperature: float = 0.7,
) -> str:
    """
    Ask an LLM a question. Tries preferred provider, then fallback.

    Args:
        prompt:     The user message.
        system:     Optional system prompt.
        history:    Optional list of prior messages [{"role": "...", "content": "..."}].
        model:      Override model name (otherwise uses provider default).
        provider:   Force a provider for this call (otherwise uses BOLT_LLM_PROVIDER).
        max_tokens: Maximum tokens in the reply.
        temperature: Sampling temperature.

    Returns:
        Response text, or a short error string if all providers fail.
    """
    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    last_error = "no providers available"

    for prov in _resolve_providers(provider):
        client = _get_client(prov)
        if not client:
            last_error = f"{prov} client unavailable"
            continue

        use_model = model or _default_model(prov)

        try:
            response = client.chat.completions.create(
                model=use_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = response.choices[0].message.content
            if content is None:
                last_error = f"{prov} returned empty content"
                continue
            return content.strip()
        except Exception as e:
            last_error = f"{prov}/{use_model}: {str(e)[:120]}"
            print(f"LLM Handler error ({prov}): {e}")
            continue

    return f"LLM unavailable: {last_error}"


def get_active_provider() -> str:
    """Return the currently preferred provider name."""
    return os.getenv("BOLT_LLM_PROVIDER", "openai").lower().strip()


def provider_status() -> dict:
    """Quick diagnostic for health checks and CLI status commands."""
    status = {}
    for name in ("openai", "xai"):
        key_var = "OPENAI_API_KEY" if name == "openai" else "XAI_API_KEY"
        has_key = bool(os.getenv(key_var))
        client = _get_client(name) if has_key else None
        status[name] = {
            "key_present": has_key,
            "client_ok": client is not None,
            "default_model": _default_model(name),
        }
    status["preferred"] = get_active_provider()
    status["fallback"] = os.getenv("BOLT_LLM_FALLBACK", "openai")
    return status


if __name__ == "__main__":
    print("LLM Handler status:")
    import json
    print(json.dumps(provider_status(), indent=2))
    print()
    result = ask_llm("Reply with exactly: Bolt LLM handler is alive.")
    print(f"Test response: {result}")
