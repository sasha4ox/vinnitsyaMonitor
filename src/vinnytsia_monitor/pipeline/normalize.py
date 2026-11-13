"""Text normalization before matching.

The original Telegram text is kept for publication. Only a copy is normalized.
"""

from __future__ import annotations

import re
import unicodedata

_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff\u00ad"), None)

_TRANSLATION = str.maketrans(
    {
        "\u00a0": " ",
        "\u202f": " ",
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u2019": "'",
        "\u02bc": "'",
        "\u0060": "'",
        "\u00b4": "'",
    }
)

_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Return a stable matching form: NFC, casefold, collapsed whitespace."""
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.translate(_ZERO_WIDTH)
    normalized = normalized.translate(_TRANSLATION)
    normalized = normalized.casefold().replace("ё", "е")
    normalized = _WHITESPACE.sub(" ", normalized).strip()
    return normalized
