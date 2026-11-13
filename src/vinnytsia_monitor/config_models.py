"""Pydantic models for the YAML configuration files."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TelegramConfig(StrictModel):
    source_channels: list[str] = Field(min_length=1)
    destination_channel: str = Field(min_length=1)


class RuntimeConfig(StrictModel):
    dedup_cache_size: int = Field(default=5000, ge=1, le=100_000)
    flood_wait_max_seconds: int = Field(default=300, ge=0, le=3600)


class AppFile(StrictModel):
    telegram: TelegramConfig
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)


class LocationConfig(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    canonical: str = Field(min_length=1)
    kind: Literal["city", "nearby"]
    # A primary nearby place is the city edge itself. When it appears together
    # with another village, it is the locality that makes the message local.
    primary: bool = False
    forms: list[str] = Field(min_length=1)


class LocationsFile(StrictModel):
    locations: list[LocationConfig] = Field(min_length=1)


class RuleConfig(StrictModel):
    name: str = Field(min_length=1)
    enabled: bool = True
    mode: Literal["ANY", "ALL"]
    keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    excluded_patterns: list[str] = Field(default_factory=list)

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_mode(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class NamedPattern(StrictModel):
    name: str = Field(min_length=1)
    regex: str = Field(min_length=1)


class RulesFile(StrictModel):
    require_any_enabled_rule: bool = True
    global_excluded_keywords: list[str] = Field(default_factory=list)
    global_excluded_patterns: list[NamedPattern] = Field(default_factory=list)
    rules: list[RuleConfig] = Field(min_length=1)


class SafetyFile(StrictModel):
    patterns: list[NamedPattern] = Field(min_length=1)


class ContextPhrase(StrictModel):
    name: str = Field(min_length=1)
    forms: list[str] = Field(min_length=1)


class ContextFile(StrictModel):
    other_region: list[ContextPhrase] = Field(default_factory=list)
    ukraine_general: list[ContextPhrase] = Field(default_factory=list)


class IgnoredPhrase(StrictModel):
    name: str = Field(min_length=1)
    text: str = Field(min_length=1)


class IgnoreFile(StrictModel):
    phrases: list[IgnoredPhrase] = Field(default_factory=list)
