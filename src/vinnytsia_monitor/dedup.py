"""In-memory record of messages already handled during this process."""

from __future__ import annotations

from collections import OrderedDict


class DedupCache:
    """Remember recent (chat, message) pairs. State is not persisted."""

    def __init__(self, max_size: int) -> None:
        if max_size < 1:
            raise ValueError("dedup cache size must be positive")
        self._max_size = max_size
        self._seen: OrderedDict[tuple[int, int], None] = OrderedDict()

    def is_duplicate(self, key: tuple[int, int]) -> bool:
        if key in self._seen:
            self._seen.move_to_end(key)
            return True
        self._seen[key] = None
        while len(self._seen) > self._max_size:
            self._seen.popitem(last=False)
        return False
