"""Compatibility wrapper for the existing Google_Calender module.

The original file name is misspelled, but existing code may already import it.
New code can import modules.Google_Calendar while the old path keeps working.
"""

from .Google_Calender import *  # noqa: F401,F403
