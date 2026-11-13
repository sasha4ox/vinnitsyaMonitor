"""Classification labels and the explanation attached to each message."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Label(StrEnum):
    VINNYTSIA_RELEVANT = "VINNYTSIA_RELEVANT"
    OTHER_REGION = "OTHER_REGION"
    UKRAINE_GENERAL = "UKRAINE_GENERAL"
    UNCERTAIN = "UNCERTAIN"
    SENSITIVE_OPERATIONAL_DETAILS = "SENSITIVE_OPERATIONAL_DETAILS"


@dataclass(frozen=True)
class Decision:
    label: Label
    should_forward: bool
    geographically_relevant: bool
    reasons: tuple[str, ...]
    location_ids: tuple[str, ...]
    location_names: tuple[str, ...]
    matched_rules: tuple[str, ...]
    safety_hits: tuple[str, ...]

    def render(self) -> str:
        locations = ", ".join(self.location_names) or "-"
        rules = ", ".join(self.matched_rules) or "-"
        lines = [
            f"label: {self.label.value}",
            f"forward: {'yes' if self.should_forward else 'no'}",
            f"geographically_relevant: {'yes' if self.geographically_relevant else 'no'}",
            f"locations: {locations}",
            f"rules: {rules}",
            "reasons:",
            *(f"- {reason}" for reason in self.reasons),
        ]
        return "\n".join(lines)
