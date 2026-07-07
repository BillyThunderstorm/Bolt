#!/usr/bin/env python3
"""
modules/LLM_Handler.py — OpenAI chat completions wrapper
=========================================================
Lazy-loads OpenAI client on first use to avoid import-time credential errors.
"""

import os
from typing import Optional

_client = None


def _get_client():
    """Lazy-load the OpenAI client only when needed."""
    global _client
    if _client is None:
        try:
            from openai import OpenAI

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set in environment")
            _client = OpenAI(api_key=api_key)
        except Exception as e:
            print(f"LLM Handler init error: {e}")
            return None
    return _client


def ask_llm(prompt: str, model: str = "gpt-4o-mini") -> str:
    """
    Ask OpenAI a question.

    Args:
        prompt: The question/prompt to send
        model: Model name (default: gpt-4o-mini)

    Returns:
        The response text, or error message if unavailable
    """
    try:
        client = _get_client()
        if not client:
            return "LLM unavailable: client initialization failed."

        response = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"LLM Error: {e}")
        return f"LLM unavailable: {str(e)[:80]}"


if __name__ == "__main__":
    result = ask_llm("What is the capital of France?")
    print(f"Response: {result}")
