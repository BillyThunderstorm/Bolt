"""modules/_lazy_imports.py — Lazy import proxy for heavy third-party libs.

Some Bolt modules depend on heavy third-party libraries (moviepy, librosa,
opencv, PIL) that take 100s of ms to import. CLI tools and lightweight
scripts often only need a small piece of those modules, so paying the
full import cost on every entry is wasteful.

This module provides a single helper:

    heavy = lazy_import("moviepy.editor")

`heavy` is a lightweight proxy. The real module is imported on first
attribute access (e.g. `heavy.VideoFileClip(...)`) and the result is
cached, so subsequent accesses are O(1).

Usage:

    from modules._lazy_imports import lazy_import

    cv2 = lazy_import("cv2")
    librosa = lazy_import("librosa")
    moviepy_editor = lazy_import("moviepy.editor")

    # First access triggers the import:
    frame = cv2.imread("frame.jpg")

    # Cached thereafter:
    img = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType
from typing import Any


class _LazyModule:
    """Proxy that defers ``import`` until first attribute access.

    Behaves like a regular module for attribute access, iteration, and
    ``repr()``, but doesn't pay the import cost until you actually need it.

    We avoid ``__slots__`` here because we want to cache resolved
    attributes on the proxy after first lookup; ``__slots__`` would
    forbid that.
    """

    def __init__(self, name: str, alias: str | None = None) -> None:
        self._name = name
        self._alias = alias or name.rsplit(".", 1)[-1]
        self._cache: ModuleType | None = None
        self._resolved = False

    def _resolve(self) -> ModuleType:
        if not self._resolved:
            self._cache = importlib.import_module(self._name)
            self._resolved = True
        return self._cache  # type: ignore[return-value]

    def __getattr__(self, attr: str) -> Any:
        # __getattr__ is only called when normal lookup fails, so by the
        # time we get here we know we need to import.
        module = self._resolve()
        value = getattr(module, attr)
        # Cache the attribute on the proxy so future access is a normal
        # attribute lookup (avoids re-walking the module dict every time).
        # We bypass our own __setattr__ via object.__setattr__ to avoid
        # recursion if anyone overrides attribute storage later.
        object.__setattr__(self, attr, value)
        return value

    def __iter__(self):
        # Allow `for name in heavy_module` style usage.
        return iter(dir(self._resolve()))

    def __repr__(self) -> str:
        status = "loaded" if self._resolved else "lazy"
        return f"<LazyModule {self._name!r} ({status})>"

    def __bool__(self) -> bool:
        # Truthy only after we've actually resolved; lets callers do
        # `if heavy_module: use_it()` as a defensive guard.
        return self._resolved

    @property
    def resolved(self) -> bool:
        return self._resolved

    @property
    def name(self) -> str:
        return self._name


def lazy_import(name: str, alias: str | None = None) -> _LazyModule:
    """Return a lazy proxy for the given module.

    Parameters
    ----------
    name: dotted module path, e.g. ``"moviepy.editor"`` or ``"cv2"``.
    alias: optional local alias name (currently only used for repr).
    """
    return _LazyModule(name, alias)


def is_loaded(proxy: _LazyModule) -> bool:
    """Return True if the proxy has already triggered its import."""
    return isinstance(proxy, _LazyModule) and proxy.resolved


def force_load(proxy: _LazyModule) -> ModuleType:
    """Eagerly resolve a lazy proxy. Returns the real module."""
    if not isinstance(proxy, _LazyModule):
        raise TypeError(f"force_load expects a LazyModule, got {type(proxy).__name__}")
    return proxy._resolve()


# Registry of all proxies created in this process, for diagnostics.
_REGISTRY: list[_LazyModule] = []


def tracked_lazy_import(name: str, alias: str | None = None) -> _LazyModule:
    """Like ``lazy_import`` but the proxy is added to a process-wide registry.

    Tests and the performance baseline use the registry to assert that a
    heavy module was NOT loaded during a fast path.
    """
    proxy = lazy_import(name, alias)
    _REGISTRY.append(proxy)
    return proxy


def registered_proxies() -> list[_LazyModule]:
    """Return a snapshot of all tracked lazy proxies created so far."""
    return list(_REGISTRY)


def is_module_loaded(module_name: str) -> bool:
    """Return True if `module_name` is currently in sys.modules."""
    return module_name in sys.modules
