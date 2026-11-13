"""Configuration and session errors."""


class ConfigError(Exception):
    """The YAML configuration is missing or invalid."""


class SettingsError(Exception):
    """Required environment settings are missing or invalid."""


class SessionMissingError(Exception):
    """No Telethon session is available for a non-interactive start."""
