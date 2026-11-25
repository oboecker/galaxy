"""The gate network drawn from its rules: every pair of systems a
permanent gate reaches (`gates.permanent.range_ly`) is linked, unless the
way between them passes a third system closely — within
`gates.network.pass_by_share` of the jump's length from its line, between
its ends — where the network runs through that system instead, or a void lies between them.

Every link follows the rules, drawn by hand or not: a
run makes the network the rules give, a link they do not give goes, and
one they give keeps its grade. A pair in `gate_blocked` — a link someone
removed — is never generated again.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np

from galaxy import brightstars, medium, travel


def _passes(c: tuple, a: tuple, b: tuple, share: float) -> bool:
    """Whether `c` lies between `a` and `b` within `share` of the jump's
    length from its line."""
    ab = [q - p for p, q in zip(a, b)]
    span = sum(v * v for v in ab)
    if span == 0:
        return False
    t = sum((ci - ai) * v for ci, ai, v in zip(c, a, ab)) / span
    if not 0 < t < 1:
        return False
    foot = [ai + t * v for ai, v in zip(a, ab)]
    return math.dist(c, foot) <= share * math.sqrt(span)


def _story(doc: dict[str, Any]) -> dict[str, tuple]:
    """Where the systems the network joins are: the catalogue's own, not the
    real sky's bright stars (galaxy.brightstars)."""
    real = {s.get("name") for s in doc.get("star_systems") or [] if brightstars.is_real(s)}
    return {name: at for name, at in travel.systems(doc).items() if name not in real}


def _shrouded(doc: dict[str, Any]) -> dict[str, str]:
    """Why each system inside a nebula too dense for a gate has none: its name
    to the reason (galaxy.nebulae.gates_allowed)."""
    from galaxy import nebulae
    if not doc.get("nebulae"):
        return {}
    out = {}
    for name, at in travel.systems(doc).items():
        barring = [n for n in nebulae.containing(doc, at) if not nebulae.gates_allowed(n)]
        if barring:
            n = barring[0]
            out[name] = (f"{name} lies in {n['name']}: its gas and dust, {nebulae.density(n):,.0f} particles "
                         "per cm³, leave no place for a gate")
    return out


def generate(doc: dict[str, Any], settings: Optional[dict[str, Any]] = None,
             field: Optional[dict[str, Any]] = None) -> list[tuple[str, str]]:
    """Every pair the rules link, sorted, whatever is drawn already."""
    settings, field = settings or travel.load(), field or medium.load()
    grid = medium.grid(field, medium.places(doc), None)
    shrouded = _shrouded(doc)
    links = network(_story(doc), grid, travel.gate_range(settings), settings["gates"]["network"]["pass_by_share"])
    return [pair for pair in links if not set(pair) & set(shrouded)]


def network(where: dict[str, tuple], grid, reach: float, share: float) -> list[tuple[str, str]]:
    """Every pair of `where` the rules link, sorted: the rules of `_why_not`,
    with a spatial index to find the pairs within reach and the systems near
    each one's line — thousands of systems (the procedural galaxy) as well as
    the catalogue's hundred and fifty."""
    from scipy.spatial import cKDTree
    names = sorted(where)
    if len(names) < 2:
        return []
    at = np.asarray([where[n] for n in names], dtype=float)
    tree = cKDTree(at)
    pairs = np.asarray(sorted(tree.query_pairs(reach)), dtype=int).reshape(-1, 2)
    if not len(pairs):
        return []
    a, b = at[pairs[:, 0]], at[pairs[:, 1]]
    length = np.linalg.norm(b - a, axis=1)
    # A third system passes close only within share × length of the line,
    # between its ends: inside this sphere round the middle.
    near = tree.query_ball_point((a + b) / 2, length / 2 + share * length)
    passed = np.zeros(len(pairs), dtype=bool)
    for start in range(0, len(pairs), _CHUNK):
        passed[start:start + _CHUNK] = _passed(at, pairs[start:start + _CHUNK], near[start:start + _CHUNK], share)
    kept = pairs[~passed]
    void = _voids(grid, at[kept[:, 0]], at[kept[:, 1]])
    return sorted((names[i], names[j]) for (i, j), v in zip(kept, void) if not v)


_CHUNK = 50_000         # pairs whose candidates are checked at once: bounds the arrays to some 100 MB


def _passed(at: np.ndarray, pairs: np.ndarray, near: list, share: float) -> np.ndarray:
    """For each pair (rows of indices into `at`), whether a third system of
    its `near` candidates passes close (`_passes`), all at once. The same
    sums in the same order; a distance within rounding of the limit is
    decided by `_passes` itself, so the network is the same to the link."""
    counts = np.fromiter((len(c) for c in near), dtype=int, count=len(near))
    owner = np.repeat(np.arange(len(pairs)), counts)
    cand = np.fromiter((c for cs in near for c in cs), dtype=int, count=int(counts.sum()))
    i, j = pairs[owner, 0], pairs[owner, 1]
    third = (cand != i) & (cand != j)
    owner, cand, i, j = owner[third], cand[third], i[third], j[third]
    a, b, c = at[i], at[j], at[cand]
    ab = b - a
    span = ab[:, 0] * ab[:, 0] + ab[:, 1] * ab[:, 1] + ab[:, 2] * ab[:, 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        t = ((c[:, 0] - a[:, 0]) * ab[:, 0] + (c[:, 1] - a[:, 1]) * ab[:, 1]
             + (c[:, 2] - a[:, 2]) * ab[:, 2]) / span
    between = (span > 0) & (0 < t) & (t < 1)
    gap = np.linalg.norm(c - (a + t[:, None] * ab), axis=1)
    limit = share * np.sqrt(span)
    doubt = between & (np.abs(gap - limit) <= 1e-9 * limit)
    out = np.zeros(len(pairs), dtype=bool)
    out[owner[between & ~doubt & (gap <= limit)]] = True
    for k in np.flatnonzero(doubt):
        if not out[owner[k]] and _passes(tuple(at[cand[k]]), tuple(at[i[k]]), tuple(at[j[k]]), share):
            out[owner[k]] = True
    return out


def _voids(grid, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """For each line from a row of `a` to the same of `b`, whether it
    crosses a void (travel._void_between), all at once: the same samples
    and the same cells."""
    length = np.asarray([math.dist(p, q) for p, q in zip(a[:, :2].tolist(), b[:, :2].tolist())])
    samples = np.maximum(2, (length / (grid.step / 2)).astype(int))
    line = np.repeat(np.arange(len(a)), samples)
    k = np.arange(len(line)) - np.repeat(np.cumsum(samples) - samples, samples)
    t = (k + 0.5) / samples[line]
    x = a[line, 0] + (b[line, 0] - a[line, 0]) * t
    y = a[line, 1] + (b[line, 1] - a[line, 1]) * t
    col = np.clip(np.rint((x + grid.extent) / grid.step).astype(int), 0, grid.n - 1)
    row = np.clip(np.rint((y + grid.extent) / grid.step).astype(int), 0, grid.n - 1)
    out = np.zeros(len(a), dtype=bool)
    out[line[grid.rho[row, col] < 1e-9]] = True
    return out


def _why_not(a: str, b: str, where: dict[str, tuple], grid, reach: float, share: float) -> Optional[str]:
    """Why the rules give no link between `a` and `b`, or None."""
    pa, pb = where[a], where[b]
    ly = math.dist(pa, pb)
    if ly > reach:
        return f"{a} and {b} are {ly:,.0f} ly apart: a gate reaches {reach:,.0f} ly — join them by a chain"
    if travel._void_between(grid, pa, pb):
        return f"a void lies between {a} and {b}: no gate works there"
    by = next((c for c in where if c not in (a, b) and _passes(where[c], pa, pb, share)), None)
    if by is not None:
        return f"the way from {a} to {b} passes {by}: the network runs through {by} instead"
    return None


def refusal(doc: dict[str, Any], a: str, b: str, grade: str = "permanent",
            settings: Optional[dict[str, Any]] = None, field: Optional[dict[str, Any]] = None) -> Optional[str]:
    """Why a link between `a` and `b` of `grade` breaks the rules — a link
    drawn by hand follows them too — or None where it may be drawn."""
    settings, field = settings or travel.load(), field or medium.load()
    where = _story(doc)
    outside = next((n for n in (a, b) if n not in where and n in travel.systems(doc)), None)
    if outside:
        return f"{outside} is a real star: the gate network joins the story's systems only"
    shrouded = _shrouded(doc)
    if a in shrouded or b in shrouded:
        return shrouded[a] if a in shrouded else shrouded[b]
    grid = medium.grid(field, medium.places(doc), None)
    why = _why_not(a, b, where, grid, travel.gate_range(settings, grade), settings["gates"]["network"]["pass_by_share"])
    return why and why.replace("a gate reaches", f"a {grade} gate reaches")


def allowed(doc: dict[str, Any], name: str, settings: Optional[dict[str, Any]] = None,
            field: Optional[dict[str, Any]] = None) -> dict[str, Optional[str]]:
    """For every other system, why a permanent link from `name` breaks the
    rules, or None where the rules give it."""
    settings, field = settings or travel.load(), field or medium.load()
    where = _story(doc)
    grid = medium.grid(field, medium.places(doc), None)
    reach, share = travel.gate_range(settings), settings["gates"]["network"]["pass_by_share"]
    shrouded = _shrouded(doc)
    return {other: shrouded.get(name) or shrouded.get(other) or _why_not(name, other, where, grid, reach, share)
            for other in sorted(where) if other != name}


def apply(doc: dict[str, Any], settings: Optional[dict[str, Any]] = None,
          field: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Make `doc`'s links the network the rules give (in place): blocked
    pairs left out, the grade of a link kept. What changed: how many links
    were `added` and `kept`, the pairs `removed` as against the rules, and
    how many are `blocked`."""
    before = {frozenset((link["from"], link["to"])): link for link in doc.get("gate_links") or []}
    blocked = {frozenset((pair["from"], pair["to"])) for pair in doc.get("gate_blocked") or []}
    links = []
    for a, b in generate(doc, settings, field):
        pair = frozenset((a, b))
        if pair in blocked:
            continue
        old = before.get(pair)
        links.append(old if old is not None else {"from": a, "to": b})
    kept = {frozenset((link["from"], link["to"])) for link in links}
    doc["gate_links"] = links
    if not links:
        doc.pop("gate_links")
    return {"added": len(kept - set(before)), "kept": len(kept & set(before)),
            "removed": sorted(" – ".join(sorted(p)) for p in set(before) - kept), "blocked": len(blocked)}
