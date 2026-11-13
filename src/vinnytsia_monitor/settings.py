"""Environment settings for local development and Railway."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from vinnytsia_monitor.errors import ConfigError, SettingsError

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str = field(repr=False)
    session_path: Path
    session_string: str | None = field(default=None, repr=False)
    interactive_auth: bool = False
    config_dir: Path = Path("config")
    log_level: str = "INFO"
    log_format: str = "text"
    log_message_text: bool = False

    def redaction_secrets(self) -> list[str]:
        secrets = [self.api_hash]
        if self.session_string:
            secrets.append("".join(self.session_string.split()))
        return secrets


def load_settings() -> Settings:
    load_dotenv()
    return settings_from_mapping(os.environ, cwd=Path.cwd())


def settings_from_mapping(environ: Mapping[str, str], cwd: Path | None = None) -> Settings:
    api_id = _required_int(environ, "API_ID")
    api_hash = _required_text(environ, "API_HASH")
    session_path = Path(_required_text(environ, "TELEGRAM_SESSION_PATH"))
    session_raw = environ.get("TELEGRAM_SESSION_STRING", "")
    session_string = session_raw.strip() or None
    return Settings(
        api_id=api_id,
        api_hash=api_hash,
        session_path=session_path,
        session_string=session_string,
        interactive_auth=parse_bool(environ.get("INTERACTIVE_AUTH"), default=False),
        config_dir=resolve_config_dir(environ, cwd),
        log_level=_choice(environ, "LOG_LEVEL", "INFO", _LEVELS),
        log_format=_choice(environ, "LOG_FORMAT", "text", {"text", "json"}),
        log_message_text=parse_bool(environ.get("LOG_MESSAGE_TEXT"), default=False),
    )


def resolve_config_dir(environ: Mapping[str, str] | None = None, cwd: Path | None = None) -> Path:
    if environ is None:
        load_dotenv()
        environ = os.environ
    cwd = cwd or Path.cwd()
    raw = environ.get("CONFIG_DIR", "").strip()
    if raw:
        path = Path(raw)
        if not path.is_dir():
            raise ConfigError(f"CONFIG_DIR does not exist: {path}")
        return path
    local = cwd / "config"
    if (local / "config.yaml").is_file():
        return local
    packaged = Path(__file__).resolve().parents[2] / "config"
    if (packaged / "config.yaml").is_file():
        return packaged
    raise ConfigError("Cannot find config.yaml. Set CONFIG_DIR or run the command from the project root.")


def parse_bool(value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().casefold()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    raise SettingsError(f"Expected a boolean value, got {value!r}")


def _required_text(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise SettingsError(f"{name} is required")
    return value


def _required_int(environ: Mapping[str, str], name: str) -> int:
    raw = _required_text(environ, name)
    try:
        value = int(raw)
    except ValueError as exc:
        raise SettingsError(f"{name} must be an integer") from exc
    if value <= 0:
        raise SettingsError(f"{name} must be a positive integer")
    return value


def _choice(environ: Mapping[str, str], name: str, default: str, allowed: set[str]) -> str:
    raw = environ.get(name, default).strip()
    value = raw.lower() if name == "LOG_FORMAT" else raw.upper()
    if name == "LOG_FORMAT":
        value = raw.lower()
    if value not in allowed and value.upper() in allowed:
        value = value.upper()
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise SettingsError(f"{name} must be one of: {choices}")
    return value
