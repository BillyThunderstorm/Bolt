#!/usr/bin/env python3
"""Voice front door for vault changes. Confirms before it writes.

Later phases add handlers here. A message that is not a vault request
returns None so the rest of the intent router, then chat, can take it.
"""

from __future__ import annotations

from typing import Optional

from modules.Vault_Capture import try_capture
from modules.Vault_Pending import try_pending
from modules.Vault_Store import VaultError


def try_vault_chat(text: str) -> Optional[str]:
    try:
        pending = try_pending(text)
    except VaultError as exc:
        return str(exc)
    if pending is not None:
        return pending
    try:
        return try_capture(text)
    except VaultError as exc:
        return str(exc)
