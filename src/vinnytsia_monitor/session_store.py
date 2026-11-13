"""Persist a Telethon StringSession without logging it.

The session file is plain text, not a SQLite database. Telethon's default
file session uses SQLite; this application does not.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vinnytsia_monitor.errors import SessionMissingError, SettingsError


@dataclass(frozen=True)
class LoadedSession:
    value: str
    source: Literal["file", "environment"]


def clean_session(value: str) -> str:
    return "".join(value.split())


def resolve_session(path: Path, env_value: str | None) -> LoadedSession:
    """Prefer an existing file. Otherwise materialize TELEGRAM_SESSION_STRING."""
    if path.exists() and not path.is_file():
        raise SettingsError(f"TELEGRAM_SESSION_PATH is not a file: {path}")

    file_value = ""
    if path.is_file():
        file_value = clean_session(path.read_text(encoding="utf-8"))
    if file_value:
        return LoadedSession(value=file_value, source="file")

    env_clean = clean_session(env_value or "")
    if not env_clean:
        raise SessionMissingError(
            "No Telegram session found. Run `python -m vinnytsia_monitor.auth` locally, "
            "then set TELEGRAM_SESSION_STRING or copy the session file to TELEGRAM_SESSION_PATH."
        )

    _write(path, env_clean)
    return LoadedSession(value=env_clean, source="environment")


def read_existing_session(path: Path, env_value: str | None) -> str:
    """Read a session for interactive auth. Missing credentials are allowed."""
    if path.is_file():
        return clean_session(path.read_text(encoding="utf-8"))
    return clean_session(env_value or "")


def save_session(path: Path, session: str) -> None:
    cleaned = clean_session(session)
    if len(cleaned) < 10:
        raise SessionMissingError("Telegram did not return a usable session")
    _write(path, cleaned)


def _write(path: Path, session: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session + "\n", encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)
