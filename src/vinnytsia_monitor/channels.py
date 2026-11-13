"""Parse public channel links into Telethon identifiers."""

from __future__ import annotations

import re

from vinnytsia_monitor.errors import ConfigError

_LINK_PREFIXES = (
    "https://t.me/",
    "http://t.me/",
    "https://telegram.me/",
    "http://telegram.me/",
    "t.me/",
)

_USERNAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{3,31}")


def parse_channel_ref(value: str) -> str | int:
    """Accept @name, t.me/name, or a numeric id. Invite links are rejected."""
    raw = value.strip()
    if not raw:
        raise ConfigError("Channel reference is empty")

    lowered = raw.casefold()
    for prefix in _LINK_PREFIXES:
        if lowered.startswith(prefix):
            raw = raw[len(prefix) :]
            break

    raw = raw.split("?", 1)[0].strip().strip("/")
    if raw.startswith("@"):
        raw = raw[1:]

    if not raw or raw.startswith("+") or "/" in raw:
        raise ConfigError(
            f"Unsupported channel reference {value!r}. Use a public @username, a t.me/username link, or a numeric id."
        )

    if raw.lstrip("-").isdigit():
        return int(raw)

    if not _USERNAME.fullmatch(raw):
        raise ConfigError(f"Unsupported channel reference {value!r}. Expected a public Telegram username.")
    return raw


def channel_key(value: str) -> str:
    parsed = parse_channel_ref(value)
    if isinstance(parsed, int):
        return str(parsed)
    return parsed.casefold()
