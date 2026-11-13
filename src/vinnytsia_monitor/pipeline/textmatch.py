"""Word-boundary matching for place names and phrases."""

from __future__ import annotations

import re

from vinnytsia_monitor.errors import ConfigError
from vinnytsia_monitor.pipeline.normalize import normalize


def compile_regex(pattern: str, label: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ConfigError(f"Invalid regular expression in {label}: {exc}") from exc


def compile_forms(forms: list[str], label: str) -> re.Pattern[str]:
    """Match any full form, longest first, without matching inside a larger word."""
    normalized = sorted({normalize(form) for form in forms if normalize(form)}, key=len, reverse=True)
    if not normalized:
        raise ConfigError(f"{label} needs at least one matchable form")
    parts = [rf"(?<![\w]){re.escape(form)}(?![\w])" for form in normalized]
    return re.compile("|".join(parts), re.IGNORECASE)


def compile_exact(term: str) -> re.Pattern[str]:
    normalized = normalize(term)
    return re.compile(rf"(?<![\w]){re.escape(normalized)}(?![\w])", re.IGNORECASE)
