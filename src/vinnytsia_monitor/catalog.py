"""Compiled, immutable matching catalog built from YAML."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vinnytsia_monitor.config_models import ContextFile, IgnoreFile, LocationsFile, RulesFile, SafetyFile
from vinnytsia_monitor.errors import ConfigError
from vinnytsia_monitor.pipeline.normalize import normalize
from vinnytsia_monitor.pipeline.textmatch import compile_exact, compile_forms, compile_regex


@dataclass(frozen=True)
class CompiledLocation:
    id: str
    canonical: str
    kind: Literal["city", "nearby"]
    primary: bool
    pattern: object


@dataclass(frozen=True)
class Term:
    kind: Literal["exact", "location"]
    value: str
    pattern: object | None = None


@dataclass(frozen=True)
class CompiledRule:
    name: str
    enabled: bool
    mode: Literal["ANY", "ALL"]
    keywords: tuple[Term, ...]
    excluded_keywords: tuple[Term, ...]
    patterns: tuple[object, ...]
    excluded_patterns: tuple[object, ...]


@dataclass(frozen=True)
class CompiledMarker:
    name: str
    pattern: object


@dataclass(frozen=True)
class Catalog:
    locations: tuple[CompiledLocation, ...]
    locations_by_id: dict[str, CompiledLocation]
    require_any_enabled_rule: bool
    rules: tuple[CompiledRule, ...]
    global_excluded_keywords: tuple[Term, ...]
    global_excluded_patterns: tuple[tuple[str, object], ...]
    safety: tuple[tuple[str, object], ...]
    other_region: tuple[CompiledMarker, ...]
    ukraine_general: tuple[CompiledMarker, ...]
    ignored_phrases: tuple[tuple[str, str], ...]


def compile_catalog(
    locations_file: LocationsFile,
    rules_file: RulesFile,
    safety_file: SafetyFile,
    context_file: ContextFile,
    ignore_file: IgnoreFile,
) -> Catalog:
    locations, form_owner = _compile_locations(locations_file)
    by_id = {location.id: location for location in locations}
    rules = tuple(_compile_rule(rule, by_id, form_owner) for rule in rules_file.rules)
    names = [rule.name for rule in rules]
    if len(names) != len(set(names)):
        raise ConfigError("Rule names must be unique")

    enabled = [rule for rule in rules if rule.enabled]
    if rules_file.require_any_enabled_rule and not enabled:
        raise ConfigError("At least one keyword rule must be enabled")

    return Catalog(
        locations=locations,
        locations_by_id=by_id,
        require_any_enabled_rule=rules_file.require_any_enabled_rule,
        rules=rules,
        global_excluded_keywords=tuple(
            _compile_term(term, by_id, form_owner, "global excluded keyword")
            for term in rules_file.global_excluded_keywords
        ),
        global_excluded_patterns=tuple(
            (item.name, compile_regex(item.regex, f"global exclusion {item.name}"))
            for item in rules_file.global_excluded_patterns
        ),
        safety=tuple(
            (item.name, compile_regex(item.regex, f"safety pattern {item.name}")) for item in safety_file.patterns
        ),
        other_region=_compile_markers(context_file.other_region, "other region marker"),
        ukraine_general=_compile_markers(context_file.ukraine_general, "nationwide marker"),
        ignored_phrases=_compile_ignored(ignore_file),
    )


def _compile_ignored(ignore_file: IgnoreFile) -> tuple[tuple[str, str], ...]:
    phrases = [(item.name, normalize(item.text)) for item in ignore_file.phrases]
    phrases = [(name, text) for name, text in phrases if text]
    phrases.sort(key=lambda item: len(item[1]), reverse=True)
    return tuple(phrases)


def _compile_locations(
    locations_file: LocationsFile,
) -> tuple[tuple[CompiledLocation, ...], dict[str, str]]:
    seen_ids: set[str] = set()
    form_owner: dict[str, str] = {}
    compiled: list[CompiledLocation] = []

    for location in locations_file.locations:
        if location.id in seen_ids:
            raise ConfigError(f"Duplicate location id: {location.id}")
        seen_ids.add(location.id)

        normalized_forms: list[str] = []
        for form in location.forms:
            normalized = normalize(form)
            if not normalized:
                raise ConfigError(f"Location {location.id} contains an empty form")
            owner = form_owner.get(normalized)
            if owner is not None and owner != location.id:
                raise ConfigError(f"Form {form!r} is listed for both {owner} and {location.id}")
            form_owner[normalized] = location.id
            normalized_forms.append(normalized)

        compiled.append(
            CompiledLocation(
                id=location.id,
                canonical=location.canonical,
                kind=location.kind,
                primary=location.primary or location.kind == "city",
                pattern=compile_forms(normalized_forms, f"location {location.id}"),
            )
        )

    return tuple(compiled), form_owner


def _compile_markers(phrases: list, label: str) -> tuple[CompiledMarker, ...]:
    markers: list[CompiledMarker] = []
    seen: set[str] = set()
    for phrase in phrases:
        if phrase.name in seen:
            raise ConfigError(f"Duplicate {label}: {phrase.name}")
        seen.add(phrase.name)
        markers.append(
            CompiledMarker(
                name=phrase.name,
                pattern=compile_forms(phrase.forms, f"{label} {phrase.name}"),
            )
        )
    return tuple(markers)


def _compile_rule(rule, by_id: dict[str, CompiledLocation], form_owner: dict[str, str]) -> CompiledRule:
    if not rule.keywords and not rule.patterns:
        raise ConfigError(f"Rule {rule.name!r} needs at least one keyword or pattern")
    return CompiledRule(
        name=rule.name,
        enabled=rule.enabled,
        mode=rule.mode,
        keywords=tuple(_compile_term(term, by_id, form_owner, f"rule {rule.name}") for term in rule.keywords),
        excluded_keywords=tuple(
            _compile_term(term, by_id, form_owner, f"rule {rule.name} exclusion") for term in rule.excluded_keywords
        ),
        patterns=tuple(
            compile_regex(pattern, f"rule {rule.name}") for pattern in rule.patterns if pattern.strip()
        ),
        excluded_patterns=tuple(
            compile_regex(pattern, f"rule {rule.name} exclusion")
            for pattern in rule.excluded_patterns
            if pattern.strip()
        ),
    )


def _compile_term(
    raw: str,
    by_id: dict[str, CompiledLocation],
    form_owner: dict[str, str],
    label: str,
) -> Term:
    stripped = raw.strip()
    if not stripped:
        raise ConfigError(f"Empty term in {label}")
    if stripped.casefold().startswith("location:"):
        location_id = stripped.split(":", 1)[1].strip()
        if location_id not in by_id:
            raise ConfigError(f"Unknown location id {location_id!r} in {label}")
        return Term(kind="location", value=location_id)
    normalized = normalize(stripped)
    owner = form_owner.get(normalized)
    if owner is not None:
        return Term(kind="location", value=owner)
    return Term(kind="exact", value=normalized, pattern=compile_exact(normalized))
