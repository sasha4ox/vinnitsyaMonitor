"""Decide whether a Telegram FloodWait is short enough to wait out."""

from __future__ import annotations


def flood_wait_delay(seconds: int, max_seconds: int) -> int | None:
    """Return the delay to sleep, or None when the send should be skipped.

    Skipping a single publish keeps the live listener running. Connection-level
    waits are handled separately and may use the raw delay.
    """
    if seconds < 0 or max_seconds < 0:
        return None
    if seconds > max_seconds:
        return None
    return seconds
