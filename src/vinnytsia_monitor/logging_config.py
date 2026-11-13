"""Logging that never keeps credentials in the message."""

from __future__ import annotations

import json
import logging


class RedactFilter(logging.Filter):
    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self._secrets = [secret for secret in secrets if len(secret) >= 8]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        record.args = self._redact_args(record.args)
        return True

    def _redact_args(self, args: object) -> object:
        if isinstance(args, dict):
            return {key: self._redact(value) if isinstance(value, str) else value for key, value in args.items()}
        if isinstance(args, tuple):
            return tuple(self._redact(value) if isinstance(value, str) else value for value in args)
        return args

    def _redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "[redacted]")
        return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, str] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str, log_format: str, secrets: list[str]) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.addFilter(RedactFilter(secrets))
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("telethon").setLevel(logging.WARNING)
