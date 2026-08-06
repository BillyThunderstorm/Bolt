"""Allow ``python -m bolt_cli`` / ``uv run python -m bolt_cli``."""

from __future__ import annotations

from bolt_cli.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
