"""Installable Bolt CLI package.

Provides the ``bolt`` console script so these all work:

    uv run bolt <subcommand>
    .venv/bin/bolt <subcommand>
    bolt <subcommand>          # with shell alias / PATH
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
