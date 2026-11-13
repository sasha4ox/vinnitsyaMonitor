"""Keyword rules. A keyword hit never bypasses the geographic filter."""

from __future__ import annotations

from dataclasses import dataclass

from vinnytsia_monitor.catalog import Catalog, CompiledRule, Term


@dataclass(frozen=True)
class RuleOutcome:
    matched: tuple[str, ...]
    suppressed: tuple[str, ...]


def term_matches(term: Term, text: str, catalog: Catalog) -> bool:
    if term.kind == "location":
        location = catalog.locations_by_id[term.value]
        return location.pattern.search(text) is not None
    if term.pattern is None:
        return False
    return term.pattern.search(text) is not None


def matching_rules(text: str, catalog: Catalog) -> RuleOutcome:
    """Match enabled rules. An excluded rule does not count as a match."""
    matched: list[str] = []
    suppressed: list[str] = []
    for rule in catalog.rules:
        if not rule.enabled:
            continue
        if not _positive_match(rule, text, catalog):
            continue
        exclusion = _rule_exclusion(rule, text, catalog)
        if exclusion is not None:
            suppressed.append(f"{rule.name} ({exclusion})")
            continue
        matched.append(rule.name)
    return RuleOutcome(matched=tuple(matched), suppressed=tuple(suppressed))


def exclusion_reason(text: str, catalog: Catalog) -> str | None:
    """Return a global exclusion label, if the message must be dropped."""
    for term in catalog.global_excluded_keywords:
        if term_matches(term, text, catalog):
            return term.value
    for name, pattern in catalog.global_excluded_patterns:
        if pattern.search(text) is not None:
            return name
    return None


def _positive_match(rule: CompiledRule, text: str, catalog: Catalog) -> bool:
    keyword_hits = [term_matches(term, text, catalog) for term in rule.keywords]
    pattern_hits = [pattern.search(text) is not None for pattern in rule.patterns]
    has_keywords = bool(rule.keywords)
    has_patterns = bool(rule.patterns)
    if not has_keywords and not has_patterns:
        return False
    if rule.mode == "ANY":
        return any(keyword_hits) or any(pattern_hits)
    keywords_ok = all(keyword_hits) if has_keywords else True
    patterns_ok = all(pattern_hits) if has_patterns else True
    return keywords_ok and patterns_ok


def _rule_exclusion(rule: CompiledRule, text: str, catalog: Catalog) -> str | None:
    for term in rule.excluded_keywords:
        if term_matches(term, text, catalog):
            return term.value
    for pattern in rule.excluded_patterns:
        if pattern.search(text) is not None:
            return "excluded pattern"
    return None
