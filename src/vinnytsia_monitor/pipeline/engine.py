"""Run geographic, keyword, and safety stages and explain the result."""

from __future__ import annotations

from vinnytsia_monitor.catalog import Catalog
from vinnytsia_monitor.pipeline.classifier import classify, match_markers
from vinnytsia_monitor.pipeline.geographic import match_locations
from vinnytsia_monitor.pipeline.keywords import exclusion_reason, matching_rules
from vinnytsia_monitor.pipeline.models import Decision, Label
from vinnytsia_monitor.pipeline.normalize import normalize
from vinnytsia_monitor.pipeline.safety import match_safety


def evaluate(text: str, catalog: Catalog) -> Decision:
    normalized = _without_ignored_phrases(normalize(text), catalog.ignored_phrases)
    if not normalized:
        return _decision(
            label=Label.UNCERTAIN,
            should_forward=False,
            geographically_relevant=False,
            reasons=("Rejected: the message has no text.",),
        )

    locations = match_locations(normalized, catalog)
    other_region = match_markers(normalized, catalog.other_region)
    ukraine_general = match_markers(normalized, catalog.ukraine_general)
    rule_outcome = matching_rules(normalized, catalog)
    rules = rule_outcome.matched
    exclusion = exclusion_reason(normalized, catalog)
    safety_hits = match_safety(normalized, catalog)

    reasons: list[str] = []
    if locations:
        primary = [location for location in locations if location.primary]
        secondary = [location for location in locations if not location.primary]
        matched = primary or list(locations)
        reasons.append("Geographic match: " + _render_locations(matched) + ".")
        if primary and secondary:
            reasons.append("Also named: " + _render_locations(secondary) + ".")
    else:
        reasons.append("No configured Vinnytsia city or nearby locality.")
    if other_region:
        reasons.append("Other regional marker: " + ", ".join(other_region) + ".")
    if ukraine_general:
        reasons.append("Nationwide marker: " + ", ".join(ukraine_general) + ".")
    if rules:
        reasons.append("Keyword rule matched: " + ", ".join(rules) + ".")
    elif catalog.require_any_enabled_rule:
        reasons.append("No enabled keyword rule matched.")
    if rule_outcome.suppressed:
        reasons.append("Keyword rule suppressed: " + ", ".join(rule_outcome.suppressed) + ".")
    if exclusion:
        reasons.append(f"Excluded term: {exclusion}.")
    if safety_hits:
        joined = ", ".join(safety_hits)
        reasons.append(f"Safety policy matched: {joined}. Operational tracking details are not published.")

    label = classify(
        has_location=bool(locations),
        has_other_region=bool(other_region),
        has_ukraine_general=bool(ukraine_general),
        has_safety=bool(safety_hits),
    )
    keyword_pass = exclusion is None and (bool(rules) or not catalog.require_any_enabled_rule)
    should_forward = label is Label.VINNYTSIA_RELEVANT and keyword_pass

    if should_forward:
        reasons.append("Accepted: the message names a configured locality and passed keyword and safety checks.")
    elif label is Label.SENSITIVE_OPERATIONAL_DETAILS:
        reasons.append("Rejected: the message contains operational tracking details and is not published.")
    elif label is not Label.VINNYTSIA_RELEVANT:
        reasons.append("Rejected: no configured Vinnytsia city or nearby locality.")
    elif exclusion:
        reasons.append(f"Rejected: excluded term {exclusion}.")
    else:
        reasons.append("Rejected: no enabled keyword rule matched.")

    return _decision(
        label=label,
        should_forward=should_forward,
        geographically_relevant=bool(locations),
        reasons=tuple(reasons),
        location_ids=tuple(location.id for location in locations),
        location_names=tuple(location.canonical for location in locations),
        matched_rules=rules,
        safety_hits=safety_hits,
    )


def _without_ignored_phrases(text: str, phrases: tuple[tuple[str, str], ...]) -> str:
    cleaned = text
    for _name, phrase in phrases:
        cleaned = cleaned.replace(phrase, " ")
    return normalize(cleaned)


def _render_locations(locations: list) -> str:
    return ", ".join(f"{location.canonical} ({location.kind})" for location in locations)


def _decision(
    *,
    label: Label,
    should_forward: bool,
    geographically_relevant: bool,
    reasons: tuple[str, ...],
    location_ids: tuple[str, ...] = (),
    location_names: tuple[str, ...] = (),
    matched_rules: tuple[str, ...] = (),
    safety_hits: tuple[str, ...] = (),
) -> Decision:
    return Decision(
        label=label,
        should_forward=should_forward,
        geographically_relevant=geographically_relevant,
        reasons=reasons,
        location_ids=location_ids,
        location_names=location_names,
        matched_rules=matched_rules,
        safety_hits=safety_hits,
    )
