"""nations.json: who held which star system, when, and in which world branch.

Kept apart from galaxy.json so politics does not churn the astronomical data,
and kept per nation because that is how a history is written ("the Empire held
these systems from … to …"):

    {"nations": {
        "<id>": {
            "name": "The Empire",
            "claim_radius": 1000,          optional, default 1000
            "color": "#c0392b",            optional, else derived from position
            "holdings": [
                "Sol",                     held throughout
                {"system": "Vega", "from": "AD 2709", "to": "AD 3450", "world": "+"}
            ]}}}

`from` absent = since before any record; `to` absent = still held, and
exclusive; `world` absent = in every branch. The order of nations is
append-only, because colours are derived from position.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any



@dataclass(frozen=True)
class Holding:
    """One nation's hold on one star system: from, to, and in which world."""

    nation: str
    system: str
    start: str | None = None
    end: str | None = None
    world: str | None = None

    def as_affiliation(self) -> dict[str, str]:
        """The shape the territory generator attaches to a system."""
        out = {"nation": self.nation}
        for key, value in (("from", self.start), ("to", self.end), ("world", self.world)):
            if value:
                out[key] = value
        return out


def read(path: Path) -> tuple[dict[str, Any], str | None]:
    """The document, and why it could not be read if it could not.

    A missing file is not an error: there are no nations until there are.
    """
    if not path.exists():
        return {"nations": {}}, None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"nations": {}}, f"line {e.lineno}: {e.msg}"
    if not isinstance(doc, dict) or not isinstance(doc.get("nations", {}), dict):
        return {"nations": {}}, "expected an object with a 'nations' object"
    return doc, None


def holdings(doc: dict[str, Any]) -> list[Holding]:
    """Every nation's holdings in `doc`, a bare system name as held throughout."""
    out = []
    for nation, data in doc.get("nations", {}).items():
        for entry in data.get("holdings") or []:
            if isinstance(entry, str):
                out.append(Holding(nation, entry))
            else:
                out.append(Holding(nation, entry.get("system", ""), entry.get("from"),
                                   entry.get("to"), entry.get("world")))
    return out
