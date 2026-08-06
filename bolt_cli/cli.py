"""Console-script entry point for the Bolt CLI.

The real CLI lives at ``bin/bolt`` (self-contained, no package imports so it
still works when the tree is half-broken). This module only exists so
``[project.scripts]`` can expose ``bolt`` after ``uv sync``.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

_BOLT_SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "bolt"


def _load_bolt_module() -> ModuleType:
    """Load ``bin/bolt`` even though it has no ``.py`` suffix."""
    if not _BOLT_SCRIPT.is_file():
        raise FileNotFoundError(
            f"Bolt CLI script not found at {_BOLT_SCRIPT}. "
            "Is the repo checkout complete?"
        )
    # spec_from_file_location returns None for extensionless paths; use
    # SourceFileLoader so we can keep the historical `bin/bolt` name.
    loader = SourceFileLoader("bolt_bin_wrapper", str(_BOLT_SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise ImportError(f"Could not load Bolt CLI from {_BOLT_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def main() -> int:
    """Entry point used by the ``bolt`` console script."""
    # Nicer argv0 in help / error text ("bolt: ..." instead of a long path).
    if sys.argv:
        sys.argv[0] = "bolt"
    return int(_load_bolt_module().main())


if __name__ == "__main__":
    raise SystemExit(main())
