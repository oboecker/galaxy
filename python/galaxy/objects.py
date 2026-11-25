"""The objects a system map draws inside a system besides its bodies: points
of interest, each of a kind — the engine's own (POINTS) and any a project
declares in its objects file (project.toml `objects`):

    {"points": {"relay": {"label": "Relay", "shape": "cone", "colour": "#d07aff", "size": 1}}}

A kind's look is one of SHAPES in a colour, `size` times its usual size;
viewer/space/objects.js draws them, and a host may draw a kind with code of
its own instead (the system map's `objects` option). Galaxy-level objects —
stars, black holes, pulsars, nebulae — are the engine's own.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from galaxy import project

# The shapes a look can take (viewer/space/objects.js draws each).
SHAPES = ("octahedron", "torus", "box", "bar", "tetrahedron", "sphere", "cone")
COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")

# The engine's own kinds of point of interest.
POINTS: dict[str, dict[str, Any]] = {
    "station": {"label": "Station", "shape": "octahedron", "colour": "#ffd24a"},
    "jumpgate": {"label": "Jumpgate", "shape": "torus", "colour": "#7fe0ff"},
    "outpost": {"label": "Outpost", "shape": "box", "colour": "#b8e07a"},
    "shipyard": {"label": "Shipyard", "shape": "bar", "colour": "#ffa04a"},
    "wreck": {"label": "Wreck", "shape": "tetrahedron", "colour": "#9a8f86"},
    "beacon": {"label": "Beacon", "shape": "sphere", "colour": "#ff5a5a"},
}


def _current() -> Optional[project.Project]:
    """The current project, or None where none is chosen."""
    try:
        return project.current()
    except RuntimeError:
        return None


def project_points(here: Optional[project.Project] = None) -> dict[str, dict[str, Any]]:
    """The kinds the project's objects file declares, checked. Refused
    (ValueError) for an unknown shape, a colour that is not #rrggbb, or a
    kind the engine already has."""
    here = here or _current()
    if here is None or here.objects is None or not here.objects.exists():
        return {}
    declared = json.loads(here.objects.read_text(encoding="utf-8")).get("points") or {}
    out = {}
    for kind, look in declared.items():
        if kind in POINTS:
            raise ValueError(f"{here.objects.name}: {kind} is one of the engine's own kinds")
        if look.get("shape") not in SHAPES:
            raise ValueError(f"{here.objects.name}: {kind}'s shape is one of {', '.join(SHAPES)}")
        if not COLOUR.match(look.get("colour") or ""):
            raise ValueError(f"{here.objects.name}: {kind}'s colour is #rrggbb")
        out[kind] = {"label": look.get("label") or kind, "shape": look["shape"], "colour": look["colour"],
                     **({"size": look["size"]} if "size" in look else {})}
    return out


def points(here: Optional[project.Project] = None) -> dict[str, dict[str, Any]]:
    """Every kind of point of interest: the engine's, then the project's."""
    return {**POINTS, **project_points(here)}


def point_kinds(here: Optional[project.Project] = None) -> tuple[str, ...]:
    """The kinds a point of interest may be."""
    return tuple(points(here))
