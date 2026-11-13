"""Plain-text notification body posted to the destination channel."""

from __future__ import annotations

TELEGRAM_LIMIT = 4096


def format_notification(text: str, source_label: str) -> str:
    cleaned = text.replace("\x00", "").strip()
    if not cleaned:
        raise ValueError("Cannot publish an empty message")

    label = " ".join(source_label.split())[:80] or "Telegram"
    footer = f"\n\nДжерело: {label}"
    if len(cleaned) + len(footer) <= TELEGRAM_LIMIT:
        return cleaned + footer

    keep = max(0, TELEGRAM_LIMIT - len(footer) - 1)
    return cleaned[:keep].rstrip() + "…" + footer
