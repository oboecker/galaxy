"""Trips between stars: routes, times and arrival dates.

A trip runs from a star system to a star system — it starts and ends at the
stars; the legs within a system are the system map's — by any of the ways
of travel, compared:

- **own drive**: through the faster-than-light medium (galaxy.medium), at
  `ly_per_day` × the local density, steering around thin regions and voids,
  sustained — no range, no recharge;
- **gates**: along the gate links between systems, at their
  grade's speed, a link no longer than its grade's `range_ly` (a longer
  one is not used), with `stop_hours` at each system passed through — mixed
  with own-drive stretches to the first gate and from the last, always;
- **catapult**: straight, one way, from a system with one
  (a point of interest of kind catapult);
- **AEGIS**: minutes, anywhere outside a void.

The numbers come from the project's travel.json, which a trip can override;
the date is optional — with one, a trip has an arrival date and the dated
regions of the medium in force.
"""

from __future__ import annotations

import copy
import heapq
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from galaxy import calendar, medium, project
from galaxy.travel_config import TravelConfig

DAY_HOURS, YEAR_DAYS = TravelConfig.DAY_HOURS, TravelConfig.YEAR_DAYS


def load(path: Optional[Path] = None) -> dict[str, Any]:
    """The planner's settings as `path` (travel.json; the project's by
    default) holds them."""
    return json.loads((path or project.current().travel).read_text(encoding="utf-8"))


def merged(settings: dict[str, Any], overrides: Optional[dict[str, Any]]) -> dict[str, Any]:
    """The settings with a trip's overrides on top, key by key."""
    out = copy.deepcopy(settings)
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merged(out[key], value)
        else:
            out[key] = value
    return out


@dataclass
class Leg:
    """One stretch of a way: its kind, its ends, how far (`ly`; within a
    system, AU), how long in days, and the path the maps draw."""
    kind: str                       # own drive, gate, catapult, aegis
    start: str
    end: str
    ly: float
    days: float
    path: list[tuple[float, float]] = field(default_factory=list)   # galaxy x, y, for the maps
    grade: str = ""                 # gate: permanent or provisional
    track: list[tuple] = field(default_factory=list)   # in a system: where the end moves while the leg is flown
    speeds: tuple = ()              # a coast: km/s around its centre on leaving and on arriving


@dataclass
class Option:
    """One way to make a trip: its legs and days door to door, or why it
    cannot be made."""
    name: str                       # own drive, gates, catapult, AEGIS
    legs: list[Leg]
    days: float                     # door to door, stops included
    reachable: bool = True
    why: str = ""
    arrival: Optional[float] = None  # on the calendar's axis, with a departure
    rate: Optional[float] = None     # the drive's own speed where it is constant: ly a day, in a system AU a day

    @property
    def average(self) -> Optional[float]:
        """Distance over time while moving — a wait for a launch window is
        not travel — in the legs' unit a day; None where it cannot be flown,
        and for AEGIS: a shortcut, not a flight through the space between."""
        if any(leg.kind == "aegis" for leg in self.legs):
            return None
        moving = [leg for leg in self.legs if leg.kind != "wait"]
        days = sum(leg.days for leg in moving)
        return sum(leg.ly for leg in moving) / days if self.reachable and days > 0 else None

    @property
    def stops(self) -> list[str]:
        """Where the way stops between its ends: each leg's end but the last."""
        return [leg.end for leg in self.legs[:-1]]


# ── the systems ───────────────────────────────────────────────────────────────

def systems(doc: dict[str, Any]) -> dict[str, tuple[float, float, float]]:
    """Every system's place by name: galaxy coordinates (x, y, z) in light years."""
    return {s["name"]: (float(s["x"]), float(s["y"]), float(s.get("z", 0))) for s in doc.get("star_systems") or []}


def catapults(doc: dict[str, Any]) -> set[str]:
    """Systems with a catapult: a point of interest of that kind."""
    return {s["name"] for s in doc.get("star_systems") or []
            if any(p.get("kind") == "catapult" for p in s.get("points_of_interest") or [])}


def gate_links(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """The gate network: links between systems, each with a grade
    (permanent or provisional)."""
    return list(doc.get("gate_links") or [])


def gate_range(settings: dict[str, Any], grade: str = "permanent") -> float:
    """How far a gate link of the grade reaches: farther
    systems are joined by a chain of links."""
    return float(settings["gates"][grade]["range_ly"])


def _distance(a: tuple, b: tuple) -> float:
    return math.dist(a, b)


# ── own drive through the web ─────────────────────────────────────────────────

_NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _graph(grid: medium.Grid, own: dict[str, Any]) -> csr_matrix:
    """Days from cell to neighbouring cell for an own drive; none into or
    out of a cell thinner than it can cross."""
    key = (own["ly_per_day"], own["min_density"])
    cached = getattr(grid, "_graphs", {})
    if key in cached:
        return cached[key]
    n = grid.n
    slow = np.where(grid.rho >= own["min_density"], 1.0 / np.maximum(grid.rho, 1e-9), np.inf)
    index = np.arange(n * n).reshape(n, n)
    rows, cols, weights = [], [], []
    for dr, dc in _NEIGHBOURS:
        r0, r1 = max(0, -dr), n - max(0, dr)
        c0, c1 = max(0, -dc), n - max(0, dc)
        a, b = slow[r0:r1, c0:c1], slow[r0 + dr:r1 + dr, c0 + dc:c1 + dc]
        days = grid.step * math.hypot(dr, dc) * (a + b) / 2 / own["ly_per_day"]
        ok = np.isfinite(days)
        rows.append(index[r0:r1, c0:c1][ok])
        cols.append(index[r0 + dr:r1 + dr, c0 + dc:c1 + dc][ok])
        weights.append(days[ok])
    graph = csr_matrix((np.concatenate(weights), (np.concatenate(rows), np.concatenate(cols))), shape=(n * n, n * n))
    cached[key] = graph
    grid._graphs = cached
    return graph


def _segment_days(grid: medium.Grid, a: tuple, b: tuple, own: dict[str, Any]) -> float:
    """Days along a straight stretch at the drive's speed; ∞ through a cell
    it cannot cross."""
    length = _distance(a, b)
    samples = max(2, int(length / (grid.step / 2)))
    total = 0.0
    for k in range(samples):
        t = (k + 0.5) / samples
        rho = grid.rho[grid.cell(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)]
        if rho < own["min_density"]:
            return math.inf
        total += length / samples / (own["ly_per_day"] * rho)
    return total


def _void_between(grid: medium.Grid, a: tuple, b: tuple) -> bool:
    """Whether a straight line from a to b crosses a void — no web at all."""
    return _segment_days(grid, a[:2], b[:2], {"ly_per_day": 1.0, "min_density": 1e-9}) == math.inf


def _straighten(grid: medium.Grid, points: list[tuple], own: dict[str, Any]) -> list[tuple]:
    """The grid's path pulled taut: a stretch is cut short wherever the
    straight line is no slower."""
    if len(points) <= 2:
        return points
    times = [0.0]
    for a, b in zip(points, points[1:]):
        times.append(times[-1] + _segment_days(grid, a, b, own))
    out, k = [points[0]], 0
    while k < len(points) - 1:
        far = k + 1
        for j in range(len(points) - 1, k + 1, -1):
            if _segment_days(grid, points[k], points[j], own) <= (times[j] - times[k]) * TravelConfig.STRAIGHTEN_SLACK:
                far = j
                break
        out.append(points[far])
        k = far
    return out


@dataclass
class _Search:
    """A route search's result, from one start cell (`_search`)."""
    times: np.ndarray               # days to each cell, flight only
    previous: np.ndarray


def _search(grid: medium.Grid, own: dict[str, Any], start: tuple) -> _Search:
    """Days by own drive from the cell of `start` to every cell (Dijkstra over
    `_graph`), with each cell's predecessor for `_route`."""
    times, previous = dijkstra(_graph(grid, own), indices=grid.cell(*start)[0] * grid.n + grid.cell(*start)[1],
                               return_predecessors=True)
    return _Search(times, previous)


def _route(grid: medium.Grid, search: _Search, target: tuple) -> list[tuple]:
    """Cell centres from `target` back to where the search started."""
    row, col = grid.cell(*target[:2])
    at, points = row * grid.n + col, []
    while at >= 0:
        points.append(grid.point(at))
        at = search.previous[at]
    return points


def own_leg(grid: medium.Grid, own: dict[str, Any], search: _Search, names: tuple[str, str],
            positions: tuple[tuple, tuple], from_end: bool = False) -> Optional[Leg]:
    """The own-drive leg from the first system to the second, from a
    search run from the first — or, `from_end`, from the second; None
    where the web does not let it through."""
    a, b = positions
    target = a if from_end else b
    row, col = grid.cell(*target[:2])
    if not math.isfinite(search.times[row * grid.n + col]):
        return None
    points = _route(grid, search, target)
    if not from_end:
        points.reverse()
    points = [a[:2]] + points[1:-1] + [b[:2]] if len(points) > 1 else [a[:2], b[:2]]
    points = _straighten(grid, points, own)
    flight = sum(_segment_days(grid, p, q, own) for p, q in zip(points, points[1:]))
    if not math.isfinite(flight):
        flight = float(search.times[row * grid.n + col])
    flat = sum(_distance(p, q) for p, q in zip(points, points[1:]))
    climb = b[2] - a[2]
    flight = _lift(flight, flat, climb, float(grid.rho[row, col]), own)
    return Leg("own drive", names[0], names[1], float(math.hypot(flat, climb)), float(flight),
               [(float(x), float(y)) for x, y in points])


def _lift(flight: float, flat: float, climb: float, rho: float, own: dict[str, Any]) -> float:
    """A flight over the map stretched for the height it climbs on the way
    (the web's density does not change with height): by the 3D length over
    the flat one; straight up where the flat way is next to nothing."""
    if flat < 1.0:
        return abs(climb) / (own["ly_per_day"] * max(rho, own["min_density"]))
    return flight * math.hypot(flat, climb) / flat


def _quick_own_days(grid: medium.Grid, own: dict[str, Any], search: _Search, source: tuple,
                    target: tuple) -> float:
    """An own-drive leg's days from a search, its height
    estimated from the straight distance — for weighing gate transfers and
    proposing links."""
    row, col = grid.cell(*target[:2])
    flight = float(search.times[row * grid.n + col])
    if not math.isfinite(flight):
        return flight
    # The search runs from cell centre to cell centre: scaled to the true
    # flat distance, which matters for near neighbours.
    flat = math.dist(source[:2], target[:2])
    sr, sc = grid.cell(*source[:2])
    centres = math.dist(grid.point(sr * grid.n + sc), grid.point(row * grid.n + col))
    rho = float(grid.rho[row, col])
    flight = flight * flat / centres if centres > 0 else flat / (own["ly_per_day"] * max(rho, own["min_density"]))
    return _lift(flight, flat, target[2] - source[2], rho, own)


# ── a trip ────────────────────────────────────────────────────────────────────

def plan(doc: dict[str, Any], start: str, end: str, depart: Optional[float] = None,
         overrides: Optional[dict[str, Any]] = None, settings: Optional[dict[str, Any]] = None,
         field: Optional[dict[str, Any]] = None) -> list[Option]:
    """Every way from `start` to `end`, fastest first; those that cannot
    make it last, with why. `depart` on the calendar's axis."""
    settings = merged(settings or load(), overrides)
    # The nebulae thicken the web where they lie (galaxy.nebulae).
    field = medium.with_nebulae(field or medium.load(), doc)
    where = systems(doc)
    if start not in where or end not in where:
        raise ValueError(f"No system named {start if start not in where else end}")
    a, b = where[start], where[end]
    grid = medium.grid(field, medium.places(doc), depart)
    own = settings["own_drive"]
    out: list[Option] = []

    # Own drive, straight through the web.
    from_start = _search(grid, own, a[:2])
    leg = own_leg(grid, own, from_start, (start, end), (a, b))
    void = [n for n, p in ((start, a), (end, b)) if grid.rho[grid.cell(*p[:2])] <= 0]
    why = (f"{', '.join(void)} lies in a void" if void else
           "the web is too thin or broken on every way there")
    out.append(Option("own drive", [leg], leg.days, rate=own["ly_per_day"]) if leg
               else Option("own drive", [], math.inf, False, why))

    # Gates, mixed with own drive to the first and from the last — offered
    # only where they beat flying on.
    gates = _gate_option(doc, settings, grid, own, start, end, where, from_start)
    if gates is not None and gates.days < out[0].days:
        out.append(gates)

    # A catapult at the start.
    if start in catapults(doc):
        ly = _distance(a, b)
        blocked = _void_between(grid, a, b)
        out.append(Option("catapult", [], math.inf, False, "a void lies in the way") if blocked else
                   Option("catapult", [Leg("catapult", start, end, ly, ly / settings["catapult"]["ly_per_day"],
                                           [a[:2], b[:2]])], ly / settings["catapult"]["ly_per_day"],
                          rate=settings["catapult"]["ly_per_day"]))

    # AEGIS: a shortcut, not a flight — only a void at either end stops it.
    minutes = settings["aegis"]["minutes"] / 60 / DAY_HOURS
    out.append(Option("AEGIS", [], math.inf, False, f"{', '.join(void)} lies in a void") if void else
               Option("AEGIS", [Leg("aegis", start, end, _distance(a, b), minutes, [a[:2], b[:2]])], minutes))

    for option in out:
        if depart is not None and option.reachable:
            option.arrival = depart + option.days / YEAR_DAYS
    return sorted(out, key=lambda o: (not o.reachable, o.days))


def _gate_option(doc, settings, grid, own, start, end, where, from_start) -> Optional[Option]:
    """The fastest trip using at least one gate hop: own drive from the
    start to a gate system, gate hops, own drive from the last to the end;
    `stop_hours` at every system passed through."""
    links = gate_links(doc)
    if not links:
        return None
    gates = settings["gates"]
    stop = gates["stop_hours"] / DAY_HOURS
    hops: dict[str, list[tuple[str, float, str]]] = {}
    for link in links:
        grade = link.get("grade", "permanent")
        if _void_between(grid, where[link["from"]], where[link["to"]]):
            continue                      # every way of travel needs the medium
        ly = _distance(where[link["from"]], where[link["to"]])
        if ly > gate_range(settings, grade):
            continue                      # beyond its reach: an editor flags it
        days = ly / gates[grade]["ly_per_day"]
        hops.setdefault(link["from"], []).append((link["to"], days, grade))
        hops.setdefault(link["to"], []).append((link["from"], days, grade))
    to_end = _search(grid, own, where[end][:2])
    gated = set(hops)

    # Dijkstra over systems; a state remembers whether a gate was used.
    best: dict[tuple[str, bool], float] = {(start, False): 0.0}
    came: dict[tuple[str, bool], tuple] = {}
    queue = [(0.0, start, False)]
    while queue:
        days, here, used = heapq.heappop(queue)
        if days > best.get((here, used), math.inf):
            continue
        if here == end and used:
            break
        moves = []
        for there, hop, grade in hops.get(here, []):
            if there != start:
                moves.append((there, hop, True, ("gate", grade)))
        if here == start:
            for there in gated - {start}:
                t = _quick_own_days(grid, own, from_start, where[start], where[there])
                if math.isfinite(t):
                    moves.append((there, t, used, ("own", "")))
        if here in gated and here != end:
            t = _quick_own_days(grid, own, to_end, where[end], where[here])
            if math.isfinite(t):
                moves.append((end, t, used, ("own", "")))
        for there, cost, now_used, how in moves:
            wait = stop if here != start else 0.0
            total = days + wait + cost
            if total < best.get((there, now_used), math.inf):
                best[(there, now_used)] = total
                came[(there, now_used)] = (here, used, how)
                heapq.heappush(queue, (total, there, now_used))
    if (end, True) not in came:
        return None
    steps, state = [], (end, True)
    while state in came:
        here, used, how = came[state]
        steps.append((here, state[0], how))
        state = (here, used)
    steps.reverse()
    legs = []
    for here, there, (kind, grade) in steps:
        if kind == "gate":
            ly = _distance(where[here], where[there])
            legs.append(Leg("gate", here, there, ly, ly / gates[grade]["ly_per_day"],
                            [where[here][:2], where[there][:2]], grade=grade))
        else:
            search = from_start if here == start else to_end
            leg = own_leg(grid, own, search, (here, there), (where[here], where[there]), from_end=here != start)
            legs.append(leg)
    total = sum(leg.days for leg in legs) + stop * (len(legs) - 1)
    return Option("gates", legs, total)


# ── proposing gate links ──────────────────────────────────────────────────────

def nearest_by_web(doc: dict[str, Any], name: str, count: int = 3, field: Optional[dict[str, Any]] = None,
                   settings: Optional[dict[str, Any]] = None) -> list[tuple[str, float, float]]:
    """The systems quickest to reach from `name` through the web by own
    drive — where a gate link pays most, as the network grew along the
    medium's strongest paths — within a permanent gate's
    range and not yet linked to it, as (system, days, ly), quickest first."""
    settings = settings or load()
    field = medium.with_nebulae(field or medium.load(), doc)
    where = systems(doc)
    grid = medium.grid(field, medium.places(doc), None)
    own = settings["own_drive"]
    search = _search(grid, own, where[name][:2])
    linked = {link["to"] if link["from"] == name else link["from"]
              for link in gate_links(doc) if name in (link["from"], link["to"])}
    found = []
    for other, position in where.items():
        if other == name or other in linked or _distance(where[name], position) > gate_range(settings):
            continue
        days = _quick_own_days(grid, own, search, where[name], position)
        if math.isfinite(days):
            found.append((other, days, _distance(where[name], position)))
    return sorted(found, key=lambda row: row[1])[:count]


# ── reading a date ────────────────────────────────────────────────────────────

def parse_date(text: str) -> float:
    """A date on the calendar's axis, in years (galaxy.calendar.Calendar.years)."""
    return calendar.current().years(text)


def date_text(absolute: float) -> str:
    """A date on the calendar's axis (years) as the maps show it,
    "AD 523, day 120" (galaxy.calendar.Calendar.text)."""
    return calendar.current().text(absolute)


def drive_share(share: Optional[float], within_system: bool = False,
                settings: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    """A trip's own drive at a share of its speed (a
    slider, not the date), as overrides: between the stars of
    `own_drive.ly_per_day`; within a system of its speed between the stars
    (`in_system_efficiency`). None for the drive as configured."""
    if share is None:
        return None
    if not 0 < share <= 1:
        raise ValueError("the drive's share of its speed is above 0 and at most 1")
    if within_system:
        return {"own_drive": {"in_system_efficiency": share}}
    return {"own_drive": {"ly_per_day": (settings or load())["own_drive"]["ly_per_day"] * share}}


def thrust(g: Optional[float], settings: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    """A trip's sublight thrust in g, as overrides: 0 coasts (ballistic, galaxy.insystem), else from
    TravelConfig.MIN_THRUST_G — below it the star's pull is a fair share of
    the thrust and the flight a spiral, not modelled — up to `sublight.g`.
    None for the drive as configured."""
    if g is None:
        return None
    top = (settings or load())["sublight"]["g"]
    if g != 0 and not TravelConfig.MIN_THRUST_G <= g <= top:
        raise ValueError(f"the thrust is 0 (ballistic) or {TravelConfig.MIN_THRUST_G:g}–{top:g} g")
    return {"sublight": {"g": g}}


def in_system(efficiency: Optional[float], g: Optional[float]) -> dict[str, Any]:
    """A trip within a system's own drive share and sublight thrust, as overrides."""
    return {**(drive_share(efficiency, True) or {}), **(thrust(g) or {})}


def nebula_at(doc: dict[str, Any], name: str) -> Optional[dict[str, Any]]:
    """The nebula system `name` lies in that most limits sublight there
    (galaxy.nebulae.sublight_limit), or None: what galaxy.insystem keeps a
    trip within the system to."""
    from galaxy import nebulae
    holding = nebulae.containing(doc, systems(doc)[name])
    return min(holding, key=nebulae.sublight_limit) if holding else None


def density_at(doc: dict[str, Any], name: str, year: Optional[float] = None,
               field: Optional[dict[str, Any]] = None) -> float:
    """The web's density where a system lies, its regions in force on the
    date (none dated without one): what the own drive makes of it within
    the system (galaxy.insystem)."""
    # The nebulae thicken the web where they lie (galaxy.nebulae).
    field = medium.with_nebulae(field or medium.load(), doc)
    x, y, _ = systems(doc)[name]
    return float(medium.density(x, y, field, medium.places(doc), year))


def as_json(option: Option, where: dict[str, tuple]) -> dict[str, Any]:
    """A way as the maps draw it: each leg's points in galaxy coordinates
    [x, y, height], the height eased from its start to its end."""
    legs = []
    for leg in option.legs:
        z0, z1 = where[leg.start][2], where[leg.end][2]
        flat = [0.0]
        for p, q in zip(leg.path, leg.path[1:]):
            flat.append(flat[-1] + math.dist(p, q))
        points = [[x, y, z0 + (z1 - z0) * (d / flat[-1] if flat[-1] else 0)] for (x, y), d in zip(leg.path, flat)]
        legs.append({"kind": leg.kind, "start": leg.start, "end": leg.end, "ly": round(leg.ly),
                     "days": leg.days, "grade": leg.grade, "points": points})
    return {"name": option.name, "days": option.days if option.reachable else None, "reachable": option.reachable,
            "why": option.why, "stops": option.stops, "legs": legs, "rate": option.rate, "average": option.average,
            "arrival": date_text(option.arrival) if option.arrival is not None else None}


def in_time(arrival: Optional[float], by: Optional[float]) -> Optional[dict[str, Any]]:
    """The arrival check: whether a way arriving at `arrival` is
    there by `by`, and how many days it has to spare (less than none: late
    by that much)."""
    if by is None or arrival is None:
        return None
    spare = (by - arrival) * YEAR_DAYS
    return {"by": date_text(by), "in_time": spare >= 0, "spare_days": round(spare, 2)}
