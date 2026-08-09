#!/usr/bin/env python3
"""
modules/LLM_Handler.py — Multi-provider LLM wrapper (OpenAI + xAI/Grok + Ollama)
===============================================================================
Single entry point for Bolt LLM calls (chat, titles, conversation).

Budget modes (see ``LLM_Budget``):
  BOLT_LLM_MODE=light  → SuperGrok for you; Grok API only when task is high-value
  BOLT_LLM_MODE=local  → never paid API
  BOLT_LLM_MODE=full   → paid API allowed freely

Environment variables:
  BOLT_LLM_PROVIDER   openai | xai | ollama   (default: ollama in light mode)
  BOLT_LLM_FALLBACK   openai | xai | ollama | none
  OPENAI_API_KEY / XAI_API_KEY
  BOLT_OPENAI_MODEL / BOLT_XAI_MODEL / OLLAMA_MODEL
  OLLAMA_BASE_URL     (default http://localhost:11434/v1)

Usage:
  from modules.LLM_Handler import ask_llm
  reply = ask_llm("What should I post today?", task_type="chat")
  reply = ask_llm("Plan my week", task_type="strategy", complexity="high")
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
            return None
        client = OpenAI(api_key=api_key)

    elif provider in ("xai", "grok"):
        provider = "xai"
        api_key = os.getenv("XAI_API_KEY")
        if not api_key:
            return None
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1",
        )

    elif provider == "ollama":
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        client = OpenAI(base_url=base, api_key="ollama", timeout=45.0)

    else:
        print(f"LLM Handler: unknown provider '{provider}'")
        return None

    _clients[provider] = client
    return client


def _default_model(provider: str, task_type: Optional[str] = None, complexity: str = "medium") -> str:
    try:
        from modules.LLM_Budget import model_for_task

        return model_for_task(task_type, complexity, provider=provider)
    except Exception:
        if provider in ("xai", "grok"):
            return os.getenv("BOLT_XAI_MODEL", "grok-4.5")
        if provider == "ollama":
            return os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        return os.getenv("BOLT_OPENAI_MODEL", "gpt-4o-mini")


def _ollama_healthy() -> bool:
    try:
        import requests

        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        resp = requests.get(base.replace("/v1", "/api/tags"), timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


def _resolve_providers(
    preferred: Optional[str] = None,
    *,
    task_type: Optional[str] = None,
    complexity: str = "medium",
) -> List[str]:
    """
    Ordered providers to try under the current budget mode.
    """
    try:
        from modules.LLM_Budget import llm_mode, paid_api_allowed

        mode = llm_mode()
        can_pay = paid_api_allowed(task_type, complexity)
    except Exception:
        mode = "light"
        can_pay = False

    env_pref = (preferred or os.getenv("BOLT_LLM_PROVIDER") or "").lower().strip()
    fallback = (os.getenv("BOLT_LLM_FALLBACK") or "none").lower().strip()

    # Sensible defaults for SuperGrok + light API
    if not env_pref:
        env_pref = "ollama" if mode in ("light", "local") else "xai"

    order: List[str] = []

    def _add(name: str) -> None:
        n = "xai" if name == "grok" else name
        if n and n != "none" and n not in order:
            # Skip paid xai/openai when budget forbids
            if n in ("xai", "openai") and mode == "local":
                return
            if n == "xai" and not can_pay and mode == "light":
                # In light mode, only allow xai when paid_api_allowed is true
                return
            if n == "ollama" and not _ollama_healthy():
                return
            order.append(n)

    _add(env_pref)
    if fallback and fallback != "none":
        _add(fallback)

    # Always try free local before giving up (light/local)
    if mode in ("light", "local"):
        _add("ollama")

    # full mode: ensure cloud is present when preferred local fails
    if mode == "full" and can_pay:
        _add("xai")
        _add("openai")

    # light high-value: if nothing yet and paid ok, add xai
    if can_pay and "xai" not in order:
        _add("xai")

    return order or ["ollama"]


def ask_llm(
    prompt: str,
    *,
    system: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    max_tokens: int = 400,
    temperature: float = 0.7,
    task_type: str = "chat",
    complexity: str = "medium",
) -> str:
    """
    Ask an LLM a question. Tries preferred provider, then fallback.

    Pass ``task_type`` / ``complexity`` so light-budget routing can keep
    everyday chat on Ollama and send strategy/research to Grok.
    """
    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    last_error = "no providers available"

    for prov in _resolve_providers(provider, task_type=task_type, complexity=complexity):
        client = _get_client(prov)
        if not client:
            last_error = f"{prov} client unavailable"
            continue

        use_model = model or _default_model(prov, task_type, complexity)
        # Never pass cloud model ids to Ollama (common Title_Generator bug)
        if prov == "ollama":
            cloudish = ("grok", "gpt-", "o1", "o3", "chatgpt", "claude")
            if any(x in (use_model or "").lower() for x in cloudish):
                use_model = _default_model("ollama", task_type, complexity)
        if prov == "xai" and (use_model or "").lower().startswith(
            ("gpt-", "o1", "llama", "mistral", "qwen", "gemma")
        ):
            use_model = _default_model("xai", task_type, complexity)
        if prov == "openai" and "grok" in (use_model or "").lower():
            use_model = _default_model("openai", task_type, complexity)

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
            # Log paid xAI usage (tokens + soft-cap accounting)
            if prov in ("xai", "grok"):
                try:
                    from modules.XAI_Usage import (
                        extract_usage_from_response,
                        record_usage,
                    )

                    in_tok, out_tok = extract_usage_from_response(response)
                    record_usage(
                        model=use_model,
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        task_type=task_type or "chat",
                        source="LLM_Handler.ask_llm",
                        provider="xai",
                        success=True,
                    )
                except Exception:
                    pass
            return content.strip()
        except Exception as e:
            last_error = f"{prov}/{use_model}: {str(e)[:120]}"
            print(f"LLM Handler error ({prov}): {e}")
            if prov in ("xai", "grok"):
                try:
                    from modules.XAI_Usage import record_usage

                    record_usage(
                        model=use_model,
                        input_tokens=0,
                        output_tokens=0,
                        task_type=task_type or "chat",
                        source="LLM_Handler.ask_llm",
                        provider="xai",
                        success=False,
                        extra={"error": str(e)[:160]},
                    )
                except Exception:
                    pass
            continue

    return f"LLM unavailable: {last_error}"


def get_active_provider() -> str:
    """Return the currently preferred provider name."""
    preferred = (os.getenv("BOLT_LLM_PROVIDER") or "").strip()
    if preferred:
        return preferred.lower()
    try:
        from modules.LLM_Budget import llm_mode

        return "ollama" if llm_mode() in ("light", "local") else "xai"
    except Exception:
        return "ollama"


def provider_status() -> dict:
    """Quick diagnostic for health checks and CLI status commands."""
    status: Dict[str, Any] = {}
    for name in ("openai", "xai", "ollama"):
        if name == "openai":
            has_key = bool(os.getenv("OPENAI_API_KEY"))
        elif name == "xai":
            has_key = bool(os.getenv("XAI_API_KEY"))
        else:
            has_key = _ollama_healthy()
        client = _get_client(name) if (has_key or name == "ollama") else None
        status[name] = {
            "key_or_ready": has_key,
            "client_ok": client is not None,
            "default_model": _default_model(name),
        }
    status["preferred"] = get_active_provider()
    status["fallback"] = os.getenv("BOLT_LLM_FALLBACK", "none")
    try:
        from modules.LLM_Budget import describe_policy, llm_mode

        status["budget_mode"] = llm_mode()
        status["policy"] = describe_policy()
    except Exception:
        status["budget_mode"] = "unknown"
    try:
        from modules.XAI_Usage import status_dict

        status["xai_usage"] = status_dict()
    except Exception:
        pass
    return status


if __name__ == "__main__":
    print("LLM Handler status:")
    import json

    print(json.dumps(provider_status(), indent=2))
    print()
    result = ask_llm("Reply with exactly: Bolt LLM handler is alive.", task_type="chat")
    print(f"Test response: {result}")
