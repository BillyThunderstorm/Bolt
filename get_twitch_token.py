#!/usr/bin/env python3
"""
Compatibility wrapper.

This root entrypoint now forwards to scripts/get_twitch_token.py so the project
has a single canonical token setup script.
"""

from scripts.get_twitch_token import main


if __name__ == "__main__":
    main()
