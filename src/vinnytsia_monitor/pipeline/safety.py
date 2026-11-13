"""Safety gate.

A heading toward a configured place is a local alert and is not matched here.
Coordinates and launch or basing details still withhold the message.
"""

from __future__ import annotations

from vinnytsia_monitor.catalog import Catalog


def match_safety(text: str, catalog: Catalog) -> tuple[str, ...]:
    hits = [name for name, pattern in catalog.safety if pattern.search(text) is not None]
    return tuple(hits)
