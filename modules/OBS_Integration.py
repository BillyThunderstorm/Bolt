"""
OBS Integration — shim
=======================
Keeps old-style imports working:
    from modules.OBS_Integration import get_obs_monitor, mark_highlight

All real OBS logic (including audio-spike detection + replay buffer saves)
lives in Stream_Monitor.py.
"""

from modules.Stream_Monitor import StreamMonitor

_monitor = None


def get_obs_monitor() -> StreamMonitor:
    """Return (or create) the shared StreamMonitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = StreamMonitor()
    return _monitor


def mark_highlight(label: str = "") -> dict:
    """
    Manually trigger a replay buffer save right now.
    (Equivalent to pressing your OBS replay hotkey.)
    """
    monitor = get_obs_monitor()
    import time
    ts = time.time()
    monitor._save_replay()
    return {"timestamp": ts, "label": label or "manual"}


def save_replay_buffer(label: str = "") -> dict:
    return mark_highlight(label)


__all__ = [
    "StreamMonitor",
    "get_obs_monitor",
    "mark_highlight",
    "save_replay_buffer",
]
