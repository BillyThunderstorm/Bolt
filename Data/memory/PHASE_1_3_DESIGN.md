# Phase 1.3 — Video Processing Test Repairs

**Status:** ✅ Complete (2026-07-31, evening session, immediately after Phase 1.2).
**Outcome:** Bolt test suite is now **310 tests, 7 skipped, 0 broken**.
**Author:** Carter + Agent.

---

## Problem statement

After Phase 1.2 closed, 4 errors remained in `Data/tests/`:

| # | Test | Root cause |
|---|---|---|
| 1 | `test_video_intelligence.BlackFrameDetectionTests.test_solid_black_is_black` | `ModuleNotFoundError: No module named 'PIL'` |
| 2 | `test_video_intelligence.BlackFrameDetectionTests.test_solid_white_is_not_black` | `ModuleNotFoundError: No module named 'PIL'` |
| 3 | `test_highlight_series` (loader) | `NameError: name 'Image' is not defined` in `Core/modules/Clip_Deduplicator.py:311` |
| 4 | `test_video_to_title_integration` (loader) | same root cause as #3 |

Verified pre-existing via `git stash` baseline — not introduced by Phase 1.2.

## Root cause

`Clip_Deduplicator.py` does `from PIL import Image` under a `try/except ImportError`.
When Pillow is missing:

1. `Image` is never bound.
2. Module-level functions still reference `Image.Image` in their type hints
   (`def _is_black_frame(img: Image.Image) -> bool:`).
3. Python evaluates those annotations at function-definition time **unless**
   the module opts in to PEP 563 (`from __future__ import annotations`).
4. Result: `NameError` at import time, even though the function body would
   never actually run (runtime usage is gated by `HAS_PHASH`).

So errors #3 and #4 weren't really about PIL or imagehash — they were about
the module failing to *import* when PIL was absent, breaking every test that
imported `Clip_Deduplicator` (transitively, via `test_highlight_series` and
`test_video_to_title_integration`).

Errors #1 and #2 were straightforward: the env was missing Pillow. The
`requirements.txt` already lists it (`Pillow  # Image processing (frame
extraction for pHash)`) but it wasn't installed in the active Python.

## Fix

1. **Install Pillow + imagehash in the active Python**:
   ```
   python -m pip install --break-system-packages Pillow imagehash
   ```
   The env is uv-managed; `--break-system-packages` was required because of
   PEP 668. If/when Bolt moves to a project venv, this becomes a normal
   `pip install` again.
2. **Add `from __future__ import annotations`** at the top of
   `Core/modules/Clip_Deduplicator.py`. This defers evaluation of all
   annotations to a forward reference — so `Image.Image` in a type hint
   no longer blocks import when PIL is missing. The runtime `Image.open`
   calls in `_compute_phash` are already guarded by `if not HAS_PHASH: return None`,
   so no other change was needed.

## Verification

After both changes:

```
$ python -m unittest discover Data/tests
Ran 310 tests in 8.0s
OK (skipped=7)
```

The 7 skipped tests are intentionally skipped (e.g. require ffmpeg /
pytesseract that aren't installed). None are broken.

## What we did NOT do

- **Did not migrate to a project venv.** The Bolt repo uses the system's
  uv-managed Python 3.11 with `--break-system-packages` for ad-hoc installs.
  Moving to `requirements.txt`+venv would be a larger refactor (out of scope).
- **Did not change the run-time guards** (`if not HAS_PHASH: return None`)
  on `_compute_phash` / `_extract_content_phash`. They're correct as-is.
- **Did not introduce Pillow as a hard runtime dependency** in any new
  code path. `Clip_Deduplicator` still degrades to "timestamp + size only"
  when Pillow is unavailable — the future-proofing fix only changes how
  the *import* behaves, not the *functionality* the missing dep unlocks.

## Effort

Single session, ~10 minutes.

- 2 min: diagnose the 4 errors from the Phase 1.2 baseline.
- 3 min: install Pillow + imagehash.
- 2 min: add `from __future__ import annotations` to `Clip_Deduplicator.py`.
- 3 min: re-run full suite to confirm 310/310.

## Suggested follow-up (not Phase 1.3 scope)

- **`requirements.txt` install command** — add a one-liner to `Docs/Setup`
  or a `scripts/install_deps.sh` so the next person who clones the repo
  doesn't hit this same Pillow-missing issue. Keep the `--break-system-packages`
  flag if the env remains uv-managed; otherwise drop it once a project venv
  is introduced.
- **Optional: project venv** — `.venv/` is currently in `.gitignore` (check)
  but isn't actively set up. If Bolt starts using heavier deps (torch,
  whisper), a real venv would be cleaner than `--break-system-packages`.

## Test fixtures that survived this phase

All 304 tests that previously passed still pass. The 4 newly-fixed tests
now join them. No tests regressed.
