"""Construct the Telethon client. Sessions are strings, never SQLite files."""

from __future__ import annotations

from telethon import TelegramClient
from telethon.sessions import StringSession


def build_client(api_id: int, api_hash: str, session: str) -> TelegramClient:
    stored = StringSession(session) if session else StringSession()
    return TelegramClient(
        stored,
        api_id,
        api_hash,
        auto_reconnect=True,
        connection_retries=5,
        retry_delay=2,
        request_retries=3,
        flood_sleep_threshold=0,
    )
