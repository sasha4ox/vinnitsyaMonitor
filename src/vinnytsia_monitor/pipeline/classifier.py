"""Deterministic context labels.

Safety overrides locality. Locality overrides oblast-wide and nationwide
wording. Anything left over stays uncertain and is not published.
"""

from __future__ import annotations

from vinnytsia_monitor.catalog import CompiledMarker
from vinnytsia_monitor.pipeline.models import Label


def match_markers(text: str, markers: tuple[CompiledMarker, ...]) -> tuple[str, ...]:
    found: list[tuple[int, str]] = []
    for marker in markers:
        match = marker.pattern.search(text)
        if match:
            found.append((match.start(), marker.name))
    found.sort(key=lambda item: item[0])
    return tuple(name for _, name in found)


def classify(
    *,
    has_location: bool,
    has_other_region: bool,
    has_ukraine_general: bool,
    has_safety: bool,
) -> Label:
    if has_safety:
        return Label.SENSITIVE_OPERATIONAL_DETAILS
    if has_location:
        return Label.VINNYTSIA_RELEVANT
    if has_other_region:
        return Label.OTHER_REGION
    if has_ukraine_general:
        return Label.UKRAINE_GENERAL
    return Label.UNCERTAIN

