"""Constellation figures in the skies of the 3D maps: the sidecar
constellations.json, by the system they are seen from — Sol's the IAU
figures, any other's as the catalogue's author draws them.

    {"Sol": [{"name": "Orion", "lines": [["Betelgeuse", "Bellatrix"], …]}, …]}

A line is a chain of stars, each named by its system, its star or its Bayer
name (Alpha Orionis; galaxy.brightstars); a star the galaxy does not have is
skipped, its neighbours joined.

    figures(doc, "Sol")   → [{"name": "Orion", "lines": [["Betelgeuse", "Bellatrix"], …]}]  (system names)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from galaxy import project

_SUPERSCRIPTS = str.maketrans("", "", "¹²³⁴⁵⁶⁷⁸⁹")


def load(path: Optional[Path] = None) -> dict[str, list[dict[str, Any]]]:
    """The figures by system; none without the file. `_`-keys are notes."""
    path = path or project.current().constellations
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def names(doc: dict[str, Any]) -> dict[str, str]:
    """Every name a star may go by → its system's name: the system's, its
    stars', and the bright stars' Bayer names (with and without ¹²)."""
    from galaxy import brightstars
    out: dict[str, str] = {}
    by_hip = brightstars.by_hip()
    for system in doc.get("star_systems") or []:
        name = system.get("name")
        aliases = [name]
        for star in system.get("stars") or []:
            aliases.append(star.get("name"))
            known = by_hip.get(star.get("hip"))
            if known and known.get("designation"):
                aliases.append(known["designation"])
        for alias in aliases:
            if alias:
                out.setdefault(alias, name)
                out.setdefault(alias.translate(_SUPERSCRIPTS), name)
    return out


def figures(doc: dict[str, Any], system: str, table: Optional[dict] = None,
            unknown: Optional[set] = None) -> list[dict[str, Any]]:
    """The figures seen from `system`, each line a chain of system names —
    its stars not in the galaxy left out (and added to `unknown`)."""
    table = load() if table is None else table
    if system not in table:
        return []
    known = names(doc)
    out = []
    for figure in table[system]:
        lines = []
        for chain in figure.get("lines") or []:
            found = []
            for star in chain:
                name = known.get(star) or known.get(star.translate(_SUPERSCRIPTS))
                if name is None:
                    if unknown is not None:
                        unknown.add(star)
                    continue
                found.append(name)
            if len(found) > 1:
                lines.append(found)
        if lines:
            out.append({"name": figure.get("name"), "lines": lines})
    return out
