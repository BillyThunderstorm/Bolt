#!/usr/bin/env python3
"""
LLM_Budget.py — SuperGrok + light API policy for Bolt
=====================================================
Maps the "SuperGrok for you, light xAI API for Bolt" plan into routing rules.

Modes (``BOLT_LLM_MODE``):
  local  — never call paid cloud APIs (Ollama / offline only)
  light  — recommended: Grok API only for high-value thinking tasks
  full   — Grok API allowed for everyday chat + Nexus

SuperGrok (app/web subscription) is separate and is **not** billed here.
API spend is only ``XAI_API_KEY`` / console.x.ai usage.

Env knobs:
  BOLT_LLM_MODE          local | light | full     (default: light)
  BOLT_XAI_MODEL         flagship model           (default: grok-4.5)
  BOLT_XAI_MODEL_LIGHT   cheaper model for medium  (default: grok-4.3)
  BOLT_XAI_MODEL_FAST    titles / tiny tasks        (default: grok-4.3)
  NEXUS_ALLOW_PAID       true to permit Grok for high-value Nexus
  NEXUS_PREFERRED        ollama | grok | gemini    (default: ollama)
  BOLT_API_MONTHLY_CAP_USD  soft spend ceiling (default 35; 0 = unlimited)
  BOLT_BRIEFING_PROVIDER    auto | grok | local | ollama  (daily briefing Nexus)
"""

from __future__ import annotations

import os
from typing import FrozenSet, Optional, Tuple


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def llm_mode() -> str:
    """Return normalized budget mode: local | light | full."""
    mode = (os.getenv("BOLT_LLM_MODE") or "light").strip().lower()
    if mode in ("free", "offline", "ollama"):
        return "local"
    if mode in ("paid", "heavy", "unlimited"):
        return "full"
    if mode in ("local", "light", "full"):
        return mode
    return "light"


# Task types that justify Grok API spend under *light* mode.
HIGH_VALUE_TASKS: FrozenSet[str] = frozenset(
    {
        "strategy",
        "decision",
        "deep_analysis",
        "research",
        "career",
        "product_testing",
        "sponsor",
        "m_tier",
        "review",
        "morning",
        "mission",
        "planning",
    }
)

# Everyday / high-volume work — stay free or cheap.
LOW_VALUE_TASKS: FrozenSet[str] = frozenset(
    {
        "general",
        "chat",
        "title",
        "titles",
        "status",
        "queue",
        "caption",
        "tagline",
        "rewrite_short",
    }
)


def is_high_value(task_type: Optional[str], complexity: str = "medium") -> bool:
    t = (task_type or "general").strip().lower()
    if complexity and complexity.strip().lower() == "high":
        return True
    return t in HIGH_VALUE_TASKS


def paid_api_allowed(
    task_type: Optional[str] = None,
    complexity: str = "medium",
    *,
    allow_paid: Optional[bool] = None,
) -> bool:
    """
    Whether a paid xAI API call is permitted for this task.

    *local*  → never
    *light*  → only high-value tasks (and allow_paid not false)
    *full*   → yes when keys exist / not explicitly denied
    Soft monthly cap (``BOLT_API_MONTHLY_CAP_USD``) forces local when exceeded.
    """
    mode = llm_mode()
    if mode == "local":
        return False

    # Soft monthly cap — once exceeded, no more paid calls this month.
    try:
        from modules.XAI_Usage import force_local_due_to_cap

        if force_local_due_to_cap():
            return False
    except Exception:
        pass

    # Explicit call-site override wins.
    if allow_paid is False:
        return False
    if allow_paid is True:
        return is_high_value(task_type, complexity) or mode == "full"

    # Global gate: light/full need NEXUS_ALLOW_PAID (or mode=full with key later).
    allow_env = _env_bool("NEXUS_ALLOW_PAID", default=False)

    if mode == "full":
        # full: paid OK by default (cap still applies above)
        return True

    # light: must have NEXUS_ALLOW_PAID=true AND high-value task
    if not allow_env:
        return False
    return is_high_value(task_type, complexity)


def briefing_provider_preference() -> str:
    """
    Daily briefing Nexus path.

    BOLT_BRIEFING_PROVIDER:
      auto   — follow light/high-value rules (Grok when paid allowed)
      grok   — always prefer Grok API for briefing strategy (if cap allows)
      local / ollama — always local, never paid for briefing
    """
    raw = (os.getenv("BOLT_BRIEFING_PROVIDER") or "auto").strip().lower()
    if raw in ("local", "ollama", "free"):
        return "local"
    if raw in ("grok", "xai", "paid"):
        return "grok"
    return "auto"


def briefing_consult_kwargs() -> Tuple[Optional[bool], Optional[str]]:
    """
    Return (allow_paid, force_provider) for daily_briefing nexus.consult().

    Examples:
      auto  → (None, None)  — normal light routing (strategy → Grok if allowed)
      grok  → (True, "grok") unless cap exceeded → (False, "ollama")
      local → (False, "ollama")
    """
    pref = briefing_provider_preference()
    if pref == "local":
        return False, "ollama"
    if pref == "grok":
        try:
            from modules.XAI_Usage import force_local_due_to_cap

            if force_local_due_to_cap():
                return False, "ollama"
        except Exception:
            pass
        return True, "grok"
    # auto: high-value strategy with default gates; cap still applied in paid_api_allowed
    try:
        from modules.XAI_Usage import force_local_due_to_cap

        if force_local_due_to_cap():
            return False, "ollama"
    except Exception:
        pass
    return None, None


def model_for_task(
    task_type: Optional[str] = None,
    complexity: str = "medium",
    provider: str = "xai",
) -> str:
    """Pick model name for a provider under the current budget mode."""
    provider = (provider or "xai").lower().strip()
    if provider in ("xai", "grok"):
        flagship = os.getenv("BOLT_XAI_MODEL") or os.getenv("GROK_MODEL") or "grok-4.5"
        light = os.getenv("BOLT_XAI_MODEL_LIGHT", "grok-4.3")
        fast = os.getenv("BOLT_XAI_MODEL_FAST", light)
        t = (task_type or "general").strip().lower()
        if t in ("title", "titles", "caption", "tagline", "status", "queue"):
            return fast
        if is_high_value(task_type, complexity) or complexity == "high":
            return flagship
        return light
    if provider == "openai":
        return os.getenv("BOLT_OPENAI_MODEL", "gpt-4o-mini")
    if provider == "ollama":
        return os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    return os.getenv("BOLT_XAI_MODEL", "grok-4.5")


def describe_policy() -> str:
    """One-line human summary for status / voice."""
    mode = llm_mode()
    cap_note = ""
    try:
        from modules.XAI_Usage import status_dict

        s = status_dict()
        if s.get("cap_usd"):
            cap_note = (
                f" Cap ${s['cap_usd']:.0f}/mo, spent ${s['spend_usd']:.2f}."
            )
            if s.get("cap_exceeded"):
                cap_note += " Cap hit — forcing local."
    except Exception:
        pass

    if mode == "local":
        return "LLM budget: local only (no paid API)." + cap_note
    if mode == "full":
        return "LLM budget: full API — Grok allowed for everyday Bolt work." + cap_note
    return (
        "LLM budget: light — Grok API only for strategy/research/decisions; "
        "Ollama for everyday. SuperGrok app is separate."
        + cap_note
    )
