"""The faster-than-light medium's density across the galaxy: how fast a
ship with its own drive gets through, and where none can.

1 is average. A base field — even across the band most systems lie in,
denser toward the core, thinning beyond `inner_radius_ly` toward the rim,
with a gentle ripple along spiral arms — then regions placed by hand on top,
each multiplying the density inside it:

- `corridor` (> 1) and `thin` (< 1), multiplying by their `factor`;
- `void` (0), and any kind the file lists in `void_kinds`: no faster-than-
  light travel at all.

A region is a circle (`circle: {x, y, r}`), an ellipse (`ellipse: {x, y, rx,
ry, angle}`), a corridor (`path: [[x, y], …]`
with a `width`), a sphere around a system (`system`, `r`), or one derived
from planets: `around` a planet, out to `reach` × the distance to the
nearest of its `seals`. Planets are named, their systems derived, so the
region follows them. With `years` ([from, to], on the calendar's axis,
galaxy.calendar) it holds only then.

The file may name the medium (`name`, shown in what is said about it) and
add void kinds of its own (`void_kinds`).

Galaxy coordinates are light-years, the centre at 0, 0; height (z) is left
out — the disc is thin against its width.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import numpy as np

from galaxy import project

NAME = "medium"
VOID_KINDS = ("void",)
# "nebula": a nebula's footprint in the plane, the medium thicker inside
# (galaxy.nebulae.medium_factor; added by `with_nebulae`, not kept in the file).
REGION_KINDS = ("corridor", "thin", "nebula")


def name(field: dict[str, Any]) -> str:
    """What the medium is called: the file's `name`, else NAME."""
    return field.get("name") or NAME


def void_kinds(field: dict[str, Any]) -> tuple[str, ...]:
    """The region kinds with no faster-than-light travel inside."""
    return VOID_KINDS + tuple(field.get("void_kinds") or ())


def file_name() -> str:
    """The project's medium file's name, for messages."""
    return project.current().medium.name


def load(path: Optional[Path] = None) -> dict[str, Any]:
    """The field as `path` (the project's by default) holds it: the base's
    parameters and the regions."""
    return json.loads((path or project.current().medium).read_text(encoding="utf-8"))


def base(x: np.ndarray, y: np.ndarray, params: dict[str, Any]) -> np.ndarray:
    """The base field at galaxy coordinates (light years), before any region."""
    r = np.hypot(x, y)
    rho = 1 + params.get("core_boost", 0.0) * np.exp(-(r / params.get("core_radius_ly", 1.0)) ** 2)
    # Toward the rim it thins to a floor, never to nothing: the outermost
    # systems stay reachable, slowly.
    beyond = np.maximum(0.0, r - params["inner_radius_ly"])
    floor = params.get("rim_floor", 0.0)
    rho = rho * (floor + (1 - floor) * np.exp(-beyond / params["falloff_ly"]))
    arms = params.get("arms") or {}
    if arms.get("amplitude"):
        theta = np.arctan2(y, x)
        winding = np.log(np.maximum(r, 1.0) / 10000.0) / math.tan(math.radians(arms["pitch_deg"]))
        rho = rho * (1 + arms["amplitude"] * np.cos(arms["count"] * (theta - winding)
                                                   - math.radians(arms.get("phase_deg", 0))))
    return rho


def _holds(region: dict[str, Any], year: Optional[float]) -> bool:
    """Whether a region is there: undated always; dated only for a trip
    whose date falls in it."""
    years = region.get("years")
    if not years:
        return True
    return year is not None and years[0] <= year <= years[1]


def _inside(region: dict[str, Any], x: np.ndarray, y: np.ndarray, systems: dict[str, tuple]) -> np.ndarray:
    """Which points lie inside `region`: a circle, a sphere around a system,
    one `around` a planet (`derived_radius`), or a corridor along its path."""
    if "circle" in region:
        c = region["circle"]
        return np.hypot(x - c["x"], y - c["y"]) <= c["r"]
    if "ellipse" in region:
        e = region["ellipse"]
        a = np.radians(e.get("angle", 0))
        u = (x - e["x"]) * np.cos(a) + (y - e["y"]) * np.sin(a)
        v = -(x - e["x"]) * np.sin(a) + (y - e["y"]) * np.cos(a)
        return (u / e["rx"]) ** 2 + (v / e["ry"]) ** 2 <= 1
    if "system" in region:
        sx, sy = systems[region["system"]]
        return np.hypot(x - sx, y - sy) <= region["r"]
    if "around" in region:
        cx, cy = systems[region["around"]]
        return np.hypot(x - cx, y - cy) <= derived_radius(region, systems)
    inside = np.zeros_like(x, dtype=bool)
    points = region["path"]
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        dx, dy = bx - ax, by - ay
        t = np.clip(((x - ax) * dx + (y - ay) * dy) / max(dx * dx + dy * dy, 1e-9), 0, 1)
        inside |= np.hypot(x - (ax + t * dx), y - (ay + t * dy)) <= region["width"] / 2
    return inside


def with_nebulae(field: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    """The field with `doc`'s nebulae among its regions: each its footprint
    in the plane (an ellipse, turned by its tilt's third angle), the density
    inside times galaxy.nebulae.medium_factor (the medium is bound to
    matter). The field itself when there are none."""
    from galaxy import nebulae
    items = doc.get("nebulae") or []
    if not items:
        return field
    regions = [{"name": n["name"], "kind": "nebula", "factor": round(nebulae.medium_factor(n), 4),
                "ellipse": {"x": n["x"], "y": n["y"], "rx": n["size"][0], "ry": n["size"][1],
                            "angle": (n.get("tilt") or [0, 0, 0])[2]}} for n in items]
    return {**field, "regions": [*(field.get("regions") or []), *regions]}


def derived_radius(region: dict[str, Any], places: dict[str, tuple]) -> float:
    """A region `around` a planet reaches `reach` × the distance to the
    nearest of its `seals`."""
    cx, cy = places[region["around"]]
    nearest = min(math.dist((cx, cy), places[seal]) for seal in region["seals"])
    return region.get("reach", 0.2) * nearest


def places(doc: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """Where regions can be pinned: every system, and every planet at its
    system, by name."""
    out = {s["name"]: (float(s["x"]), float(s["y"])) for s in doc.get("star_systems") or []}
    for system in doc.get("star_systems") or []:
        for planet in system.get("planets") or []:
            if planet.get("name") not in (None, "?"):
                out.setdefault(planet["name"], out[system["name"]])
    return out


def problems(field: dict[str, Any], where: dict[str, tuple]) -> list[str]:
    """What in the field does not hold: an unknown region kind, or a planet
    or system it names that the galaxy does not have."""
    out = []
    for k, region in enumerate(field.get("regions") or [], start=1):
        label = region.get("name") or f"region {k}"
        kinds = REGION_KINDS + void_kinds(field)
        if region.get("kind") not in kinds:
            out.append(f"{label}: its kind is one of {', '.join(kinds)}")
        for name in [region.get("system"), region.get("around"), *(region.get("seals") or [])]:
            if name is not None and name not in where:
                out.append(f"{label}: no system or planet named {name}")
    return out


def naming(field: dict[str, Any], name: str) -> list[str]:
    """The regions that name `name` as their system, the planet they lie
    around or one of its seals."""
    return [region.get("name") or f"region {k}"
            for k, region in enumerate(field.get("regions") or [], start=1)
            if name in [region.get("system"), region.get("around"), *(region.get("seals") or [])]]


def check(field: dict[str, Any], where: dict[str, tuple]) -> None:
    """Refuse (ValueError) a field `problems` finds fault with, naming each."""
    found = problems(field, where)
    if found:
        raise ValueError("; ".join(f"{file_name()}: {problem}" for problem in found))


def density(x, y, field: dict[str, Any], systems: dict[str, tuple] | None = None,
            year: Optional[float] = None) -> np.ndarray:
    """The density at galaxy coordinates (arrays or numbers), regions
    included. Refused (ValueError) where a region names a planet or system
    `systems` does not have."""
    check(field, systems or {})
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    rho = base(x, y, field["base"])
    voids = void_kinds(field)
    for region in field.get("regions") or []:
        if _holds(region, year):
            factor = 0.0 if region["kind"] in voids else region.get("factor", 1.0)
            rho = np.where(_inside(region, x, y, systems or {}), rho * factor, rho)
    return rho


class Grid:
    """The field sampled on square cells, for the route search."""

    def __init__(self, field: dict[str, Any], systems: dict[str, tuple], year: Optional[float] = None):
        self.step = float(field.get("grid_ly", 250))
        self.extent = float(field.get("extent_ly", 46000))
        self.n = int(round(2 * self.extent / self.step)) + 1
        axis = np.linspace(-self.extent, self.extent, self.n)
        self.xs, self.ys = np.meshgrid(axis, axis)          # [row = y, column = x]
        self.rho = density(self.xs, self.ys, field, systems, year)

    def cell(self, x: float, y: float) -> tuple[int, int]:
        """The (row, column) of the cell nearest `x`, `y`, clamped to the grid."""
        col = int(round((x + self.extent) / self.step))
        row = int(round((y + self.extent) / self.step))
        return min(max(row, 0), self.n - 1), min(max(col, 0), self.n - 1)

    def point(self, index: int) -> tuple[float, float]:
        """The centre of cell `index` (row × n + column), in galaxy coordinates."""
        row, col = divmod(index, self.n)
        return float(self.xs[row, col]), float(self.ys[row, col])


def field_key(field: dict[str, Any]) -> str:
    """`field` as a cache key: its JSON, keys sorted."""
    return json.dumps(field, sort_keys=True)


@lru_cache(maxsize=8)
def _grid(key: str, systems_key: str, year: Optional[float]) -> Grid:
    return Grid(json.loads(key), json.loads(systems_key), year)


def grid(field: dict[str, Any], systems: dict[str, tuple], year: Optional[float] = None) -> Grid:
    """The sampled field, kept while the field, the systems and the regions
    in force stay the same."""
    dated = any(r.get("years") for r in field.get("regions") or [])
    return _grid(field_key(field), json.dumps(systems, sort_keys=True), year if dated else None)
