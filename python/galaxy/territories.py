"""Nation territories derived from held systems.

A territory is a *volume*:
every held system claims a sphere of its nation's claim radius (standing in for
the undocumented stars around it), and where claims meet a point belongs to the
nearest held system whose sphere reaches it. The 3D map shows that volume as a
mesh; the SVG map shows its projection onto the galactic plane, where nations
stacked in z overlap — by design.

Everything here is in galactic coordinates. Dates are `ERA YEAR` strings,
compared with month and day on one axis (galaxy.calendar). Holdings come
from nations.json (galaxy.nations) and are attached to the systems as
`affiliations` in memory only, by `attach()`.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass, field
from functools import reduce
from typing import Any

import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree
from shapely.geometry import Polygon
from shapely.ops import polylabel
from skimage.measure import find_contours, marching_cubes

from galaxy import calendar
from galaxy.calendar import Point
from galaxy.nations import holdings

DEFAULT_CLAIM_RADIUS = 1000.0
CELL = 250.0
GOLDEN_ANGLE = 137.508

def attach(galaxy: dict[str, Any], nations_doc: dict[str, Any]) -> list[str]:
    """Copy nations.json onto `galaxy` (in memory): its `nations`, and each
    holding as an `affiliations` entry on its system.

    Returns the holdings' system names that galaxy.json does not have; they are
    skipped here, for the caller to report.
    """
    galaxy["nations"] = {nid: {k: v for k, v in n.items() if k != "holdings"}
                         for nid, n in nations_doc.get("nations", {}).items()}
    by_name = {s["name"]: s for s in galaxy.get("star_systems", [])}
    unknown = []
    for h in holdings(nations_doc):
        system = by_name.get(h.system)
        if system is None:
            unknown.append(h.system)
            continue
        system.setdefault("affiliations", []).append(h.as_affiliation())
    return unknown


def nation_colors(nations: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Golden-angle hues by position in the (append-only) nations block.

    Consecutive indices land maximally far apart on the hue circle. An explicit `color` wins.
    """
    out = {}
    for i, (nid, nation) in enumerate(nations.items()):
        if nation.get("color"):
            out[nid] = nation["color"]
            continue
        r, g, b = colorsys.hls_to_rgb((i * GOLDEN_ANGLE % 360) / 360, 0.58, 0.72)
        out[nid] = "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))
    return out


def hatch_angle(index: int) -> float:
    """Golden-ratio spread over the half circle, so stacked nations hatch apart."""
    return (index * 0.618033988749895 % 1.0) * 180.0


def held_at(data: dict[str, Any], at: Point, world: str | None) -> list[tuple[dict, str]]:
    """(system, nation id) for every system held at `at` in `world`.

    An affiliation without `world` holds in every branch; without `from` it has
    held since before any recorded date; without `to` it still holds.
    """
    out = []
    for system in data.get("star_systems", []):
        for a in system.get("affiliations") or []:
            if a.get("world") not in (None, world):
                continue
            start = calendar.current().point(a["from"]) if a.get("from") else None
            end = calendar.current().point(a["to"]) if a.get("to") else None
            if (start is None or start <= at) and (end is None or at < end):
                out.append((system, a["nation"]))
                break
    return out


@dataclass
class Snapshot:
    """One interval of one branch during which nobody gains or loses a system."""

    world: str | None
    start: str | None  # date as written in the data; None = since before any record
    end: str | None    # exclusive; None = still current
    held: list[tuple[dict, str]]

    @property
    def key(self) -> frozenset:
        """The holdings as (system, nation id) pairs: snapshots with the same
        key hold the same territory."""
        return frozenset((s["name"], n) for s, n in self.held)


def worlds(data: dict[str, Any]) -> list[str | None]:
    """None (affiliations valid in every branch) plus each branch that differs."""
    named = {a["world"] for s in data.get("star_systems", [])
             for a in s.get("affiliations") or [] if a.get("world")}
    return [None, *sorted(named)]


def snapshots(data: dict[str, Any], world: str | None) -> list[Snapshot]:
    """Split history at every date an affiliation in `world` starts or ends.

    Territory cannot change between two such dates, so one computation per
    interval covers every moment. Adjacent intervals with the same holdings
    (an affiliation ending the year another begins, say) are merged.
    """
    dates: dict[Point, str] = {}
    for system in data.get("star_systems", []):
        for a in system.get("affiliations") or []:
            if a.get("world") not in (None, world):
                continue
            for key in ("from", "to"):
                if a.get(key):
                    dates.setdefault(calendar.current().point(a[key]), a[key])
    bounds = sorted(dates)
    edges: list[Point | None] = [None, *bounds, None]
    out: list[Snapshot] = []
    for start, end in zip(edges, edges[1:]):
        probe = start if start is not None else ((end[0] - 1, 0, 0) if end is not None else (0, 0, 0))
        held = held_at(data, probe, world)
        snap = Snapshot(world, dates.get(start), dates.get(end), held)
        if out and out[-1].key == snap.key:
            out[-1].end = snap.end
            continue
        out.append(snap)
    # Nothing held before the first record is not worth a snapshot.
    return [s for s in out if s.held]


@dataclass
class Territory:
    """One nation's territory at a moment: its surface in galactic
    coordinates (`vertices`, `faces`), its footprint on the plane, and where
    its label goes."""
    nation: str
    name: str
    color: str
    hatch: float
    members: list[str]
    vertices: list[list[float]] = field(default_factory=list)  # galactic x, y, z
    faces: list[list[int]] = field(default_factory=list)
    footprint: list[list[list[list[float]]]] = field(default_factory=list)  # polygons → rings → [x, y]
    label: list[float] | None = None

    def as_dict(self) -> dict[str, Any]:
        """The territory's fields as a plain dict, for JSON."""
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class Ownership:
    """Which nation owns each grid cell: index into `nations`, -1 for unclaimed."""

    owner: np.ndarray  # shape (nx, ny, nz)
    origin: np.ndarray  # galactic coordinates of cell (0, 0, 0)
    cell: float

    def at(self, x: float, y: float, z: float) -> int:
        """The owner of the cell holding galactic point (`x`, `y`, `z`); -1
        outside the grid or unclaimed."""
        i, j, k = np.round((np.array([x, y, z]) - self.origin) / self.cell).astype(int)
        if not all(0 <= v < n for v, n in zip((i, j, k), self.owner.shape)):
            return -1
        return int(self.owner[i, j, k])


def compute(data: dict[str, Any], at: Point, world: str | None = None,
            cell: float = CELL) -> list[Territory]:
    """The territories held at `at` in `world` (None: only the holdings of
    every branch), on cells of `cell` ly."""
    return territories(data, held_at(data, at, world), cell)


def territories(data: dict[str, Any], held: list[tuple[dict, str]],
                cell: float = CELL) -> list[Territory]:
    """Each nation's territory from the systems it holds (`held`): surface,
    footprint and label. A nation that owns no cell is left out."""
    nations = data.get("nations", {})
    grid = ownership(data, held, cell)
    if grid is None:
        return []
    colors = nation_colors(nations)
    out = []
    for i, (nid, nation) in enumerate(nations.items()):
        mask = grid.owner == i
        if not mask.any():
            continue
        t = Territory(nid, nation.get("name", nid), colors[nid], hatch_angle(i),
                      sorted(s["name"] for s, n in held if n == nid))
        _mesh(t, mask, grid.origin, cell)
        _footprint(t, mask.any(axis=2), grid.origin, cell)
        out.append(t)
    _place_labels(out, cell)
    return out


def ownership(data: dict[str, Any], held: list[tuple[dict, str]], cell: float = CELL) -> Ownership | None:
    """Which nation owns each cell of a grid around the held systems: that
    of the nearest held system whose nation's `claim_radius` (ly) reaches
    it. None when nothing is held."""
    if not held:
        return None
    nations = data.get("nations", {})
    index = {nid: i for i, nid in enumerate(nations)}
    radius = {nid: float(n.get("claim_radius", DEFAULT_CLAIM_RADIUS)) for nid, n in nations.items()}

    points = np.array([[s["x"], s["y"], s["z"]] for s, _ in held], dtype=float)
    owner_of = np.array([index[n] for _, n in held])
    reach = np.array([radius[n] for _, n in held])
    max_r = reach.max()

    # Grid of cell centres, padded by two cells so every surface closes.
    lo = points.min(axis=0) - max_r - 2 * cell
    hi = points.max(axis=0) + max_r + 2 * cell
    axes = [np.arange(lo[d], hi[d] + cell, cell) for d in range(3)]
    gx, gy, gz = np.meshgrid(*axes, indexing="ij")
    centres = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)

    # Nearest held systems first; the owner is the first whose own radius reaches.
    k = min(8, len(points))
    dist, idx = cKDTree(points).query(centres, k=k, distance_upper_bound=max_r)
    dist, idx = dist.reshape(len(centres), k), idx.reshape(len(centres), k)
    owner = np.full(len(centres), -1)
    undecided = np.ones(len(centres), dtype=bool)
    for j in range(k):
        valid = undecided & (idx[:, j] < len(points))
        hit = np.zeros(len(centres), dtype=bool)
        hit[valid] = dist[valid, j] <= reach[idx[valid, j]]
        owner[hit] = owner_of[idx[hit, j]]
        undecided &= ~hit
    return Ownership(owner.reshape(gx.shape), lo, cell)


def _mesh(t: Territory, mask: np.ndarray, origin: np.ndarray, cell: float) -> None:
    """Set `t`'s surface: the cells of `mask`, smoothed, as a triangle mesh in
    galactic coordinates."""
    # Smoothing turns the voxel staircase into a surface; level 0.5 keeps it on
    # the original boundary.
    field_ = gaussian_filter(mask.astype(float), sigma=1.0)
    verts, faces, _, _ = marching_cubes(field_, level=0.5)
    t.vertices = np.round(verts * cell + origin, 1).tolist()
    t.faces = faces.tolist()


def _footprint(t: Territory, mask2d: np.ndarray, origin: np.ndarray, cell: float) -> None:
    """Set `t`'s footprint: the outline of `mask2d` on the galactic plane,
    holes included, smoothed (`_smooth`)."""
    field_ = gaussian_filter(mask2d.astype(float), sigma=1.0)
    rings = [Polygon(c * cell + origin[:2]) for c in find_contours(field_, 0.5) if len(c) >= 4]
    rings = [r.buffer(0) for r in rings]
    if not rings:
        return
    # Parity: a ring inside another is a hole, so symmetric difference sorts
    # exteriors from holes without having to inspect orientation.
    shape = reduce(lambda a, b: a.symmetric_difference(b), rings)
    polygons = [p for p in getattr(shape, "geoms", [shape]) if not p.is_empty]
    t.footprint = [[_smooth(np.array(ring.coords), cell) for ring in [p.exterior, *p.interiors]]
                   for p in polygons]


def _smooth(ring: np.ndarray, cell: float, passes: int = 3) -> list[list[float]]:
    """Chaikin corner cutting: the contour follows the grid, which shows as
    straight runs at map zoom; cutting corners rounds them without moving the
    outline by more than a fraction of a cell."""
    pts = ring[:-1] if np.allclose(ring[0], ring[-1]) else ring
    for _ in range(passes):
        nxt = np.roll(pts, -1, axis=0)
        pts = np.stack([0.75 * pts + 0.25 * nxt, 0.25 * pts + 0.75 * nxt], axis=1).reshape(-1, 2)
    smooth = Polygon(pts).simplify(cell * 0.05)
    return np.round(np.array(smooth.exterior.coords), 1).tolist()


def _place_labels(territories: list[Territory], cell: float) -> None:
    """Label each nation where no other nation covers it, if it has such a part.

    Stacked nations share most of their projection, and a label at the centre
    of each full footprint puts both names in the same place.
    """
    shapes = {t.nation: _shape(t) for t in territories}
    for t in territories:
        own = shapes[t.nation]
        if own.is_empty:
            continue
        others = [s for n, s in shapes.items() if n != t.nation and not s.is_empty]
        free = own.difference(reduce(lambda a, b: a.union(b), others)) if others else own
        # A sliver of free area is no better than overlapping: require a real share.
        target = free if free.area > 0.15 * own.area else own
        largest = max(getattr(target, "geoms", [target]), key=lambda p: p.area)
        point = polylabel(largest, tolerance=cell)
        t.label = [round(point.x, 1), round(point.y, 1)]


def _shape(t: Territory):
    """`t`'s footprint as one shapely shape."""
    polygons = [Polygon(rings[0], rings[1:]) for rings in t.footprint]
    return reduce(lambda a, b: a.union(b), polygons) if polygons else Polygon()
