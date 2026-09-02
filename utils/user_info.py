"""User-context helpers (device time formatting used by notifications)."""

from __future__ import annotations

from datetime import datetime


def get_current_time() -> str:
    """Current local time as ``YYYY-MM-DD HH:MM:SS``, e.g. ``2026-09-02 19:40:05``."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
