"""Names to slugs, for the files and folders named after them: ASCII, lower
case, apostrophes dropped, any other run of characters a hyphen — "Sha'ra"
→ shara, "Élan" → elan, "Ai Ceddan" → ai-ceddan."""

from __future__ import annotations

import re
import unicodedata

_APOSTROPHES = re.compile(r"['’ʼ]")
_OTHER = re.compile(r"[^a-z0-9]+")


def slugify(name: str | None) -> str:
    """`name` as a slug, by the rule above; "" for None."""
    ascii_name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return _OTHER.sub("-", _APOSTROPHES.sub("", ascii_name.lower())).strip("-")
