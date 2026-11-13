"""Geographic matching against the configured locality list."""

from __future__ import annotations

from vinnytsia_monitor.catalog import Catalog, CompiledLocation


def match_locations(text: str, catalog: Catalog) -> tuple[CompiledLocation, ...]:
    found: list[tuple[int, CompiledLocation]] = []
    for location in catalog.locations:
        match = location.pattern.search(text)
        if match:
            found.append((match.start(), location))
    found.sort(key=lambda item: (0 if item[1].primary else 1, item[0]))
    return tuple(location for _, location in found)
