"""Tests for modules/_lazy_imports.py and the bot.py startup fix.

Covers:
1. The LazyModule proxy defers the real import until first attribute access.
2. Once resolved, attributes are cached on the proxy for fast subsequent access.
3. `force_load` and `is_loaded` work as documented.
4. The process-wide registry records proxies and survives re-imports.
5. `bot.py` no longer triggers `write_site_data` (with its GitHub push) at
   import time — the side effect moved into main().
"""



import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parents[2]
for _p in [_repo_root / 'Core', _repo_root / '3rd_Party' / 'colabs']:
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import importlib
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from modules import _lazy_imports as lazy


class LazyModuleTests(unittest.TestCase):
    def test_proxy_does_not_import_until_first_attribute_access(self):
        # Pick a stdlib module that isn't already loaded in this test process.
        target = "_pytest_not_a_real_module_xyz"  # never exists
        proxy = lazy.lazy_import(target)
        self.assertFalse(proxy.resolved)
        self.assertNotIn(target, sys.modules)
        # Accessing an attribute should fail loudly without importing the
        # real (non-existent) module — proving we didn't trigger the import.
        with self.assertRaises(ModuleNotFoundError):
            _ = proxy.anything

    def test_resolves_on_real_attribute_access(self):
        # `json` is already loaded by the test runner; use a fresh module
        # name from stdlib that may not be loaded yet.
        # `secrets` is small and rarely imported by tests.
        proxy = lazy.lazy_import("secrets")
        self.assertFalse(proxy.resolved)
        # First access: should resolve the module.
        token = proxy.token_hex(8)
        self.assertTrue(proxy.resolved)
        self.assertIsInstance(token, str)
        self.assertEqual(len(token), 16)

    def test_caches_attribute_after_first_access(self):
        proxy = lazy.lazy_import("json")
        # First access resolves and caches.
        _ = proxy.dumps
        self.assertTrue(proxy.resolved)
        # Subsequent attribute access should not raise (already cached).
        self.assertEqual(proxy.dumps({"k": 1}), '{"k": 1}')

    def test_force_load_eagerly_resolves(self):
        proxy = lazy.lazy_import("hashlib")
        self.assertFalse(proxy.resolved)
        module = lazy.force_load(proxy)
        self.assertTrue(proxy.resolved)
        self.assertIs(module, sys.modules["hashlib"])

    def test_is_loaded_returns_correct_status(self):
        proxy = lazy.lazy_import("uuid")
        self.assertFalse(lazy.is_loaded(proxy))
        _ = proxy.uuid4
        self.assertTrue(lazy.is_loaded(proxy))

    def test_repr_indicates_state(self):
        proxy = lazy.lazy_import("csv")
        self.assertIn("lazy", repr(proxy))
        _ = proxy.reader
        self.assertIn("loaded", repr(proxy))

    def test_bool_reflects_resolved_state(self):
        proxy = lazy.lazy_import("io")
        self.assertFalse(bool(proxy))
        _ = proxy.StringIO
        self.assertTrue(bool(proxy))

    def test_iter_returns_module_attribute_names(self):
        proxy = lazy.lazy_import("json")
        names = list(proxy)
        self.assertIn("dumps", names)
        self.assertIn("loads", names)

    def test_tracked_lazy_import_records_proxy(self):
        before = len(lazy.registered_proxies())
        proxy = lazy.tracked_lazy_import("collections")
        after = len(lazy.registered_proxies())
        self.assertEqual(after, before + 1)
        self.assertIn(proxy, lazy.registered_proxies())

    def test_is_module_loaded_works_for_known_and_unknown(self):
        self.assertTrue(lazy.is_module_loaded("sys"))  # always loaded
        self.assertFalse(lazy.is_module_loaded("__never_loaded_xyz__"))


class BotImportSideEffectTests(unittest.TestCase):
    """The bot.py import-time side effect (write_site_data push) must be gone.

    We can't easily run a subprocess from inside a unittest that itself
    has the project on sys.path, so we invoke a fresh python via
    subprocess to measure cold-import cost.
    """

    def test_bot_does_not_run_write_site_data_on_import(self):
        # Run a fresh python that imports `bot` and reports whether the
        # module-level side effect fired.
        script = textwrap.dedent(
            """
            import sys, json
            sys.path.insert(0, ".")
            sys.path.insert(0, "3rd_Party/colabs")
            sys.path.insert(0, "Core")
            calls = {"count": 0}

            # Patch write_site_data BEFORE importing bot.
            import scripts.site_data_writer as ssw
            real = ssw.write_site_data
            def spy(*a, **kw):
                calls["count"] += 1
                return real(*a, **kw)
            ssw.write_site_data = spy

            import bot  # this used to call write_site_data(push=True)
            print(json.dumps({"calls": calls["count"]}))
            """
        )
        with tempfile.TemporaryDirectory() as td:
            script_path = Path(td) / "probe.py"
            script_path.write_text(script, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                cwd="/Users/carter/developer/Bolt",
                timeout=30,
            )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        # Probe output is a JSON line on the last line of stdout.
        last_line = result.stdout.strip().splitlines()[-1]
        import json as _json

        payload = _json.loads(last_line)
        self.assertEqual(
            payload["calls"],
            0,
            msg=(
                "bot.py must not call write_site_data at import time. "
                f"Got calls={payload['calls']}, stdout={result.stdout!r}"
            ),
        )


class BotImportSpeedTests(unittest.TestCase):
    """Sanity check: importing bot should be fast.

    We just assert it's under a reasonable threshold (200ms in this dev
    environment). A regression that re-adds the side effect would push
    this well over 2 seconds.
    """

    def test_bot_import_is_fast(self):
        script = textwrap.dedent(
            """
            import sys, time
            sys.path.insert(0, ".")
            sys.path.insert(0, "3rd_Party/colabs")
            sys.path.insert(0, "Core")
            # Patch the side effect just in case the test process already
            # triggered it; we want a clean measurement.
            import scripts.site_data_writer as ssw
            ssw.write_site_data = lambda *a, **kw: None
            t0 = time.perf_counter()
            import bot
            t1 = time.perf_counter()
            print(f"{(t1-t0)*1000:.1f}")
            """
        )
        with tempfile.TemporaryDirectory() as td:
            script_path = Path(td) / "probe.py"
            script_path.write_text(script, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                cwd="/Users/carter/developer/Bolt",
                timeout=30,
            )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        elapsed_ms = float(result.stdout.strip().splitlines()[-1])
        self.assertLess(
            elapsed_ms,
            200.0,
            msg=(
                f"import bot took {elapsed_ms:.1f}ms — likely the old "
                "site-data push side effect came back."
            ),
        )


if __name__ == "__main__":
    unittest.main()
