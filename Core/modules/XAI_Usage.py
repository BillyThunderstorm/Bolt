#!/usr/bin/env python3
"""
XAI_Usage.py — Paid xAI API usage log + monthly soft cap
========================================================
Every paid Grok API call should call ``record_usage(...)`` so we can:

  1. Append a line to ``logs/xai_usage.jsonl``
  2. Enforce ``BOLT_API_MONTHLY_CAP_USD`` (soft cap → force local)

Env:
  BOLT_API_MONTHLY_CAP_USD   soft ceiling for the calendar month (default 35)
  BOLT_API_CAP_HARD          if true, raise instead of only forcing local
  XAI_PRICE_*                optional price overrides ($/1M tokens)

Prices default to published grok-4.5 / 4.3 rates (short context).
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_lock = threading.Lock()

# Repo root: Core/modules/XAI_Usage.py → parents[2]
_REPO = Path(__file__).resolve().parents[2]
USAGE_LOG = _REPO / "logs" / "xai_usage.jsonl"
MONTHLY_SUMMARY = _REPO / "logs" / "xai_usage_month.json"
# Tracks which budget thresholds already fired this month (avoid spam)
ALERT_STATE = _REPO / "logs" / "xai_budget_alerts.json"

# Soft-cap alert levels (fraction of BOLT_API_MONTHLY_CAP_USD)
_ALERT_THRESHOLDS = (0.50, 0.90, 1.00)

# Approximate $/1M tokens (short context). Override via env if xAI changes rates.
_DEFAULT_PRICES: Dict[str, Tuple[float, float]] = {
    # model_prefix → (input_per_m, output_per_m)
    "grok-4.5": (2.00, 6.00),
    "grok-4.3": (1.25, 2.50),
    "grok-4.20": (1.25, 2.50),
    "grok-4.1": (0.20, 0.50),
    "grok-build": (1.00, 2.00),
    "default": (2.00, 6.00),
}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def monthly_cap_usd() -> float:
    """Soft monthly API budget in USD. 0 = unlimited."""
    return max(0.0, _env_float("BOLT_API_MONTHLY_CAP_USD", 35.0))


def _price_for_model(model: str) -> Tuple[float, float]:
    m = (model or "").lower().strip()
    for key, prices in _DEFAULT_PRICES.items():
        if key != "default" and key in m:
            return prices
    return _DEFAULT_PRICES["default"]


def estimate_cost_usd(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> float:
    """Estimate USD cost from token counts and model price table."""
    in_rate, out_rate = _price_for_model(model)
    # Allow global overrides
    in_rate = _env_float("XAI_PRICE_INPUT_PER_M", in_rate)
    out_rate = _env_float("XAI_PRICE_OUTPUT_PER_M", out_rate)
    return (input_tokens / 1_000_000.0) * in_rate + (output_tokens / 1_000_000.0) * out_rate


def _month_key(when: Optional[datetime] = None) -> str:
    dt = when or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m")


def _read_jsonl_month(month: str) -> list:
    if not USAGE_LOG.exists():
        return []
    rows = []
    try:
        with USAGE_LOG.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = row.get("timestamp") or ""
                if ts.startswith(month) or row.get("month") == month:
                    rows.append(row)
    except OSError:
        return []
    return rows


def month_spend_usd(month: Optional[str] = None) -> float:
    """Sum estimated_cost_usd for the given YYYY-MM (default: current UTC month)."""
    key = month or _month_key()
    total = 0.0
    for row in _read_jsonl_month(key):
        try:
            total += float(row.get("estimated_cost_usd") or 0.0)
        except (TypeError, ValueError):
            continue
    return total


def remaining_budget_usd() -> Optional[float]:
    """None if unlimited; else cap − spend (can be negative if over)."""
    cap = monthly_cap_usd()
    if cap <= 0:
        return None
    return cap - month_spend_usd()


def cap_exceeded() -> bool:
    """True when soft monthly cap is set and current spend is at/over it."""
    cap = monthly_cap_usd()
    if cap <= 0:
        return False
    return month_spend_usd() >= cap


def force_local_due_to_cap() -> bool:
    """
    Whether routing should refuse paid xAI calls this month.
    Soft by default — callers fall back to Ollama.
    """
    return cap_exceeded()


def _load_alert_state() -> Dict[str, Any]:
    if not ALERT_STATE.exists():
        return {}
    try:
        return json.loads(ALERT_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_alert_state(state: Dict[str, Any]) -> None:
    ALERT_STATE.parent.mkdir(parents=True, exist_ok=True)
    ALERT_STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def check_and_notify_budget(*, force: bool = False) -> list:
    """
    Fire SMS + email + Mac banner when monthly spend crosses 50% / 90% / 100%.
    Each threshold notifies at most once per calendar month (unless force=True).
    Returns list of thresholds that fired this call (e.g. [0.5, 0.9]).
    """
    cap = monthly_cap_usd()
    if cap <= 0:
        return []

    spent = month_spend_usd()
    ratio = spent / cap if cap else 0.0
    month = _month_key()
    state = _load_alert_state()
    month_state = state.setdefault(month, {"fired": []})
    fired = set(month_state.get("fired") or [])
    newly: list = []

    for thr in _ALERT_THRESHOLDS:
        key = f"{int(thr * 100)}"
        if ratio + 1e-9 < thr:
            continue
        if key in fired and not force:
            continue
        # Build messages
        pct = int(thr * 100)
        if thr >= 1.0:
            title = "Bolt API cap reached"
            msg = (
                f"Estimated xAI spend ${spent:.2f} hit the ${cap:.0f} soft cap. "
                f"Bolt is forcing local models for the rest of the month."
            )
        elif thr >= 0.9:
            title = "Bolt API 90% of budget"
            msg = (
                f"Estimated xAI spend ${spent:.2f} of ${cap:.0f} "
                f"(~{pct}%). Light mode still active — watch usage."
            )
        else:
            title = "Bolt API 50% of budget"
            msg = (
                f"Estimated xAI spend ${spent:.2f} of ${cap:.0f} "
                f"(~{pct}%). SuperGrok app is separate; this is API only."
            )
        try:
            from modules.Bolt_Alerts import notify

            notify(
                msg,
                title=title,
                subject=title,
                email_body=(
                    f"{msg}\n\n"
                    f"Month: {month}\n"
                    f"Cap: ${cap:.2f}\n"
                    f"Spent (est.): ${spent:.4f}\n"
                    f"Remaining: ${max(0.0, cap - spent):.2f}\n"
                    f"Log: {USAGE_LOG}\n"
                    f"\nDiscord is not used for these alerts.\n"
                ),
            )
        except Exception as exc:
            print(f"budget alert notify failed: {exc}")
        fired.add(key)
        newly.append(thr)

    month_state["fired"] = sorted(fired)
    month_state["last_spent"] = round(spent, 4)
    month_state["updated_at"] = datetime.now(timezone.utc).isoformat()
    state[month] = month_state
    try:
        _save_alert_state(state)
    except Exception:
        pass
    return newly


def record_usage(
    *,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    task_type: str = "general",
    source: str = "unknown",
    provider: str = "xai",
    success: bool = True,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Append one paid-API usage row and return the written record.
    Safe to call from any thread; never raises to callers.
    Also evaluates budget thresholds (50/90/100%) for SMS/email/Mac alerts.
    """
    now = datetime.now(timezone.utc)
    month = _month_key(now)
    cost = estimate_cost_usd(model, input_tokens, output_tokens)
    entry: Dict[str, Any] = {
        "timestamp": now.isoformat(),
        "month": month,
        "provider": provider,
        "model": model,
        "task_type": task_type,
        "source": source,
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "estimated_cost_usd": round(cost, 6),
        "success": bool(success),
    }
    if extra:
        entry["extra"] = extra

    try:
        with _lock:
            USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
            with USAGE_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            # Refresh monthly rollup
            spent = month_spend_usd(month)
            summary = {
                "month": month,
                "spend_usd": round(spent, 4),
                "cap_usd": monthly_cap_usd(),
                "remaining_usd": (
                    None
                    if monthly_cap_usd() <= 0
                    else round(monthly_cap_usd() - spent, 4)
                ),
                "updated_at": now.isoformat(),
            }
            MONTHLY_SUMMARY.write_text(
                json.dumps(summary, indent=2) + "\n", encoding="utf-8"
            )
    except Exception as exc:
        entry["log_error"] = str(exc)[:200]

    # Threshold alerts (outside lock; uses log file)
    try:
        fired = check_and_notify_budget()
        if fired:
            entry["budget_alerts_fired"] = fired
    except Exception:
        pass

    return entry


def extract_usage_from_response(response: Any) -> Tuple[int, int]:
    """Pull prompt/completion tokens from an OpenAI-compatible response object."""
    try:
        usage = getattr(response, "usage", None)
        if usage is None and isinstance(response, dict):
            usage = response.get("usage")
        if usage is None:
            return 0, 0
        if isinstance(usage, dict):
            return int(usage.get("prompt_tokens") or 0), int(
                usage.get("completion_tokens") or 0
            )
        return int(getattr(usage, "prompt_tokens", 0) or 0), int(
            getattr(usage, "completion_tokens", 0) or 0
        )
    except Exception:
        return 0, 0


def status_dict() -> Dict[str, Any]:
    """For CLI / voice status."""
    cap = monthly_cap_usd()
    spent = month_spend_usd()
    return {
        "month": _month_key(),
        "spend_usd": round(spent, 4),
        "cap_usd": cap if cap > 0 else None,
        "remaining_usd": None if cap <= 0 else round(cap - spent, 4),
        "cap_exceeded": cap_exceeded(),
        "log_path": str(USAGE_LOG),
        "policy": (
            f"Monthly API soft cap ${cap:.0f}; spent ${spent:.2f} this month."
            if cap > 0
            else f"No monthly cap; spent ${spent:.2f} this month."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(status_dict(), indent=2))
