"""Back-compat alias for the misspelled module name.

Prefer importing from modules.Google_Calendar. This shim keeps older
call sites working after the Jul 2026 rename.
"""

from .Google_Calendar import *  # noqa: F401,F403
