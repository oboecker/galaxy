"""Trips within a star system:
from a planet, moon, star or point of interest to another, on a date — the
bodies move, so where each one is comes from its orbit at the moment it is
left or reached, as the system map places it (galaxy.systemmap, the star
tree walked from the system's centre of gravity).

- **sublight**: constant thrust at `sublight.g`, turning over halfway —
  t = 2 √(d / a) over the path's length — to where the destination will be
  on arrival, clear of what is in the way: no closer to
  a star than `star_clearance_au`, to a planet than `planet_clearance_hill`
  of its Hill radius, each where it is when the ship passes; a leg that
  would come closer bends around it. What the trip starts or ends within
  does not count (Earth for a gate at its L1);
  With `sublight.g` 0 (a trip's thrust, travel.thrust) it **coasts**: a
  Hohmann transfer around the centre both ends share, leaving at the next
  launch window — the wait is a leg of its own — or, where one end is that
  centre, at once from its low orbit. The jumpgates' legs to and from the
  gates fly the same way;
- **own drive**: the same route as sublight, at
  `own_drive.ly_per_day` × the web's density where the system lies ×
  `in_system_efficiency` — 1, as fast as between the stars, planet to
  planet near-instant; less for a drive that does worse near a star,
  chosen per trip (a slider, not the date); none below
  `min_density`, as in a void;
- **jumpgates**: a jumpgate is a point of interest of kind
  jumpgate with a `pair`, the id of its partner in the system; a hop takes
  `jumpgates.early.au_per_hour` over the distance between them, or
  `jumpgates.mature.minutes` flat, by the gate's `grade` (early gates took hours between planets). Sublight to the first gate and
  from the last; gates chained where that is faster.

Positions are in AU, x and y in the reference plane, z out of it, about the
system's centre of gravity. A moon sits on its orbit in its planet's
reference plane (the map turns it into the planet's equator: at most a few
thousandths of an AU apart); a point of interest in orbit around a body sits
at the body.
"""

from __future__ import annotations

import heapq
import math
from typing import Any, Optional

from galaxy import orbits, systemmap
from galaxy.travel_config import TravelConfig
from galaxy.travel import DAY_HOURS, YEAR_DAYS, Leg, Option, date_text, load, merged

AU_M, DAY_S, LY_AU = TravelConfig.AU_M, TravelConfig.DAY_S, TravelConfig.LY_AU
LIGHT_SPEED = 299_792_458.0          # m/s: a nebula caps sublight at a share of it


# ── where things are ──────────────────────────────────────────────────────────

def _add(a, b, k=1.0):
    """`a` + `k` × `b`, for points and vectors of three."""
    return (a[0] + k * b[0], a[1] + k * b[1], a[2] + k * b[2])


def _hosts(tree: Optional[dict[str, Any]], years: float) -> dict[str, tuple]:
    """Each host's centre (a star, or a group's centre of gravity) at a
    date: its satellites circle its core, both sides about their shared
    centre by the other's share of the mass."""
    out: dict[str, tuple] = {}

    def walk(node, at):
        out[node["key"]] = at
        if "star" in node:
            return
        sats = [(s, orbits.position(s["orbit"], years, s["period"])) for s in node["satellites"]]
        shift = (0.0, 0.0, 0.0)
        for s, rel in sats:
            shift = _add(shift, rel, s["node"]["mass"] / node["mass"])
        walk(node["core"], _add(at, shift, -1))
        for s, rel in sats:
            walk(s["node"], _add(_add(at, rel), shift, -1))

    if tree:
        walk(tree, (0.0, 0.0, 0.0))
    return out


def label_of(body: dict[str, Any], planet: Optional[str] = None) -> str:
    """A body's name; an unnamed one ("?") by its orbit — "Planet at 0.29
    AU", "Moon at 384,400 km of Earth" — as the system map's trip panel
    lists it."""
    name = (body.get("name") or "").strip()
    if name and name != "?":
        return name
    orbit = body.get("orbit") or {}
    if planet is None:
        return f"Planet at {orbit.get('au', 0):g} AU"
    return f"Moon at {orbit.get('km', 0):,.0f} km of {planet}"


class Places:
    """Where every stop of a system is, at any date: by reference — a star's
    name as "star:<name>", a planet's id, a moon's "<planet id>/<moon id>",
    a point of interest's id."""

    def __init__(self, doc_system: dict[str, Any]):
        self.data = systemmap.system(doc_system)
        # The hosts at the last date asked for: a trip's check asks for every
        # obstacle at one date before the next.
        self._hosts: Optional[tuple[float, dict[str, tuple]]] = None
        self.names: dict[str, str] = {}
        self.kinds: dict[str, str] = {}
        for star in self.data["stars"]:
            if star.get("placed"):
                self._name(f"star:{star['name']}", star["name"], "star")
        for planet in self.data["planets"]:
            if (planet.get("orbit") or {}).get("au") and planet.get("period"):
                label = label_of(planet)
                self._name(str(planet["id"]), label, "planet")
                for moon in planet["moons"]:
                    if (moon.get("orbit") or {}).get("km") and moon.get("period"):
                        self._name(f"{planet['id']}/{moon['id']}", label_of(moon, label), "moon")
        for poi in self.data["points_of_interest"]:
            self._name(str(poi["id"]), poi["name"], poi.get("kind") or "point")

    def obstacles(self, sublight: dict[str, Any]) -> list[tuple[str, float]]:
        """What a sublight leg keeps clear of, as (reference, AU)."""
        out = [(ref, sublight["star_clearance_au"]) for ref, kind in self.kinds.items() if kind == "star"]
        factor = sublight["planet_clearance_hill"]
        for planet in self.data["planets"]:
            if str(planet["id"]) in self.names and planet.get("hill") and factor > 0:
                out.append((str(planet["id"]), planet["hill"] / orbits.AU_KM * factor))
        return out

    def _name(self, ref: str, name: str, kind: str) -> None:
        self.names[ref], self.kinds[ref] = name, kind

    def ref(self, text: str) -> str:
        """The reference `text` is, or that of the stop named `text`.
        Refused (KeyError) when the system has neither."""
        if text in self.names:
            return text
        found = [r for r, n in self.names.items() if n == text]
        if not found:
            raise KeyError(f"{text} is not a body or point of interest of {self.data['name']}")
        return found[0]

    def hosts(self, years: float) -> dict[str, tuple]:
        """Each host's centre `years` after the epoch (`_hosts`)."""
        if self._hosts is None or self._hosts[0] != years:
            self._hosts = (years, _hosts(self.data.get("tree"), years))
        return self._hosts[1]

    def at(self, ref: str, years: float) -> tuple[float, float, float]:
        """Where `ref` is `years` after the epoch, in AU."""
        hosts = self.hosts(years)
        if ref.startswith("star:"):
            return hosts.get(ref[5:], (0.0, 0.0, 0.0))
        planet, moon = self._body(ref)
        if planet is not None:
            return self._body_at(planet, moon, hosts, years)
        poi = next(p for p in self.data["points_of_interest"] if str(p["id"]) == ref)
        anchor = poi["anchor"]
        if anchor["body"] == "star":
            host = self.data["hosts"].get(anchor.get("host"))
            centre = hosts.get(anchor.get("host"), (0.0, 0.0, 0.0))
            mass = host["mass"] if host else 1.0
            return _add(centre, orbits.position({"au": anchor["au"]}, years, math.sqrt(anchor["au"] ** 3 / mass)))
        planet, moon = self._body(anchor["body"])
        if "point" not in anchor:
            return self._body_at(planet, moon, hosts, years)
        return self._lagrange(planet, moon, anchor["point"], hosts, years)

    def _body(self, ref: str):
        """The planet and moon `ref` names, the moon None for a planet;
        (None, None) where no planet has its id."""
        pid, _, mid = ref.partition("/")
        planet = next((p for p in self.data["planets"] if str(p["id"]) == pid), None)
        if planet is None:
            return None, None
        moon = next((m for m in planet["moons"] if str(m["id"]) == mid), None) if mid else None
        return planet, moon

    def _centre_rel(self, planet, moon, hosts, years):
        """What the body orbits, and where the body is from it."""
        host = hosts.get(planet.get("host"), (0.0, 0.0, 0.0))
        rel = orbits.position(planet["orbit"], years, planet["period"])
        if moon is None:
            return host, rel
        km = orbits.position(moon["orbit"], years, moon["period"])
        return _add(host, rel), tuple(v / orbits.AU_KM for v in km)

    def _body_at(self, planet, moon, hosts, years):
        """Where the planet, or its moon, is `years` after the epoch, in AU."""
        centre, rel = self._centre_rel(planet, moon, hosts, years)
        return _add(centre, rel)

    def _lagrange(self, planet, moon, point, hosts, years):
        """L4 and L5 60° ahead and behind on the body's orbit, L3 opposite,
        L1 and L2 its Hill radius inside and outside."""
        centre, rel = self._centre_rel(planet, moon, hosts, years)
        body = moon or planet
        if point == "L3":
            return _add(centre, rel, -1)
        if point in ("L4", "L5"):
            # The way it goes round: the orbit's sense about the plane's normal.
            _, ahead = self._centre_rel(planet, moon, hosts, years + (body.get("period") or 1) * TravelConfig.ORBIT_SENSE_SHARE)
            sense = 1 if rel[0] * ahead[1] - rel[1] * ahead[0] >= 0 else -1
            turn = (1 if point == "L4" else -1) * sense * math.pi / 3
            c, s = math.cos(turn), math.sin(turn)
            return _add(centre, (rel[0] * c - rel[1] * s, rel[0] * s + rel[1] * c, rel[2]))
        d = math.sqrt(sum(v * v for v in rel)) or 1.0
        hill = (body.get("hill") or 0.0) / orbits.AU_KM
        return _add(centre, rel, (d + (hill if point == "L2" else -hill)) / d)


# ── a trip ────────────────────────────────────────────────────────────────────

def sublight_days(au: float, g: float, cap: Optional[float] = None) -> float:
    """Days for `au` AU at `g` g: thrust to halfway, turn over, brake —
    t = 2 √(d / a). With a `cap` (a share of light speed: a nebula's safe
    speed, galaxy.nebulae.sublight_limit) a flight that would pass it
    thrusts up to it, cruises, and brakes: t = d / v + v / a."""
    d, a = au * AU_M, g * orbits.STANDARD_GRAVITY
    if cap and math.sqrt(a * d) > cap * LIGHT_SPEED:
        v = cap * LIGHT_SPEED
        return (d / v + v / a) / DAY_S
    return 2 * math.sqrt(d / a) / DAY_S


def _dist(a, b) -> float:
    return math.dist(a, b)


def _length(path: list[tuple]) -> float:
    """The length of a path of points, in their unit."""
    return sum(_dist(p, q) for p, q in zip(path, path[1:]))




def _clear(places: Places, path: list[tuple], years: float, days: float,
           obstacles: list[tuple[str, float]]) -> list[tuple]:
    """The path bent around whatever it comes too close to, each obstacle
    where it is when the ship passes (time taken as even along the path —
    close enough for where it is)."""
    start, end = path[0], path[-1]
    at_end = years + days / YEAR_DAYS
    # What the trip starts or ends within does not count.
    keep = [(ref, r) for ref, r in obstacles
            if _dist(start, places.at(ref, years)) > r and _dist(end, places.at(ref, at_end)) > r]
    passes = _passes(places, path, years, days, keep)
    for _ in range(TravelConfig.MAX_DETOURS):
        if not passes:
            return path
        _, k, point, centre, ref, r = passes[0]
        # The bend runs between the nearest corners outside the clearance: one
        # inside it (a bend around something else put it there) would stay.
        times = _times(path, years, days)
        i, j = k, k + 1
        while i > 0 and _dist(path[i], places.at(ref, times[i])) < TravelConfig.DETOUR_HIT_SHARE * r:
            i -= 1
        while j < len(path) - 1 and _dist(path[j], places.at(ref, times[j])) < TravelConfig.DETOUR_HIT_SHARE * r:
            j += 1
        bent = path[:i + 1] + _around(path[i], path[j], centre, r, point) + path[j:]
        # Checked against everything in the way, not only what it bends
        # around; a bend that does not bring the way closer to clear ends it.
        found = _passes(places, bent, years, days, keep)
        if _shortfall(found) >= _shortfall(passes):
            return path
        path, passes = bent, found
    return path


def _times(path: list[tuple], years: float, days: float) -> list[float]:
    """When the ship passes each point of `path` (time taken as even along it)."""
    total, run, out = _length(path) or 1.0, 0.0, [years]
    for p, q in zip(path, path[1:]):
        run += _dist(p, q)
        out.append(years + days / YEAR_DAYS * run / total)
    return out


def _passes(places: Places, path: list[tuple], years: float, days: float,
            keep: list[tuple[str, float]]) -> list[tuple]:
    """What `path` comes too close to: for each such obstacle the closest
    pass, as (gap / clearance, segment, point, centre, reference,
    clearance), the closest first."""
    closest: dict[str, tuple] = {}
    total = _length(path) or 1.0
    run = 0.0
    for k, (p, q) in enumerate(zip(path, path[1:])):
        seg = _dist(p, q)
        for n in range(1, TravelConfig.LEG_SAMPLES):
            s = n / TravelConfig.LEG_SAMPLES
            point = _add(p, _add(q, p, -1), s)
            when = years + days / YEAR_DAYS * (run + s * seg) / total
            for ref, r in keep:
                centre = places.at(ref, when)
                gap = _dist(point, centre)
                # A little give: an arc drawn at the clearance stays clear
                # of where the obstacle has moved to by then.
                if gap < TravelConfig.DETOUR_HIT_SHARE * r and (ref not in closest or gap / r < closest[ref][0]):
                    closest[ref] = (gap / r, k, point, centre, ref, r)
        run += seg
    return sorted(closest.values(), key=lambda found: found[0])


def _shortfall(passes: list[tuple]) -> float:
    """How far, summed over the obstacles, a path's closest passes fall
    short of what clears them, in shares of their clearance."""
    return sum(TravelConfig.DETOUR_HIT_SHARE - found[0] for found in passes)


def _unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return tuple(x / n for x in v) if n > 0 else (0.0, 0.0, 0.0)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _around(p: tuple, q: tuple, centre: tuple, r: float, near: tuple) -> list[tuple]:
    """A smooth way from `p` to `q` past a circle of radius `r` about
    `centre` (smooth, not edged): one gentle curve — a
    quadratic Bézier, its control point pushed away from the centre just
    far enough that the curve keeps the distance — the points between `p`
    and `q`. It bends to the side the straight way passes on; straight at
    the centre, to the side of `near`, else in the reference plane."""
    clear = TravelConfig.DETOUR_CLEARANCE * r
    line = _add(q, p, -1)
    span = _dot(line, line) or 1.0
    s = min(1.0, max(0.0, _dot(_add(centre, p, -1), line) / span))
    side = _add(_add(p, line, s), centre, -1)            # from the centre to the straight way's closest point
    if math.sqrt(_dot(side, side)) < 1e-9 * r:
        side = _add(near, centre, -1)
        side = _add(side, _unit(line), -_dot(side, _unit(line)))
        if math.sqrt(_dot(side, side)) < 1e-9 * r:
            side = _cross((0.0, 0.0, 1.0), _unit(line))
    out = _unit(side)
    middle = _add(p, line, 0.5)

    def curve(push: float, n: int) -> list[tuple]:
        k = _add(middle, out, push)
        return [tuple((1 - u) ** 2 * a + 2 * u * (1 - u) * c + u * u * b for a, c, b in zip(p, k, q))
                for u in (m / n for m in range(1, n))]

    def keeps(push: float) -> bool:
        return all(_dist(x, centre) >= clear for x in curve(push, TravelConfig.DETOUR_CHECK_POINTS))

    low, high = 0.0, clear * 2
    while not keeps(high):
        high *= 2
        if high > 1e3 * math.sqrt(span):
            return []
    for _ in range(TravelConfig.DETOUR_SEARCH_STEPS):
        mid = (low + high) / 2
        low, high = (low, mid) if keeps(mid) else (mid, high)
    return curve(high, TravelConfig.DETOUR_DRAWN_POINTS)


def _sublight(places: Places, a: str, b: str, years: float, sublight: dict[str, Any],
              obstacles: list[tuple[str, float]], speed: Optional[float] = None) -> tuple[float, list[tuple], list[tuple]]:
    """Days from `a` left at `years` to `b` where it will be on arrival,
    the path — the aim corrected until it holds, then bent around what is
    in the way and corrected again for the longer way — and where `b`
    moves meanwhile, from where it is at the start to the meeting. With a
    `speed` (AU an hour, the own drive) the same way at that speed."""
    g = sublight["g"]
    start = places.at(a, years)

    def flight(au: float) -> float:
        return au / speed / DAY_HOURS if speed else sublight_days(au, g, sublight.get("cap"))

    def aim(days: float, bend: bool) -> tuple[float, list[tuple]]:
        path = [start, places.at(b, years + days / YEAR_DAYS)]
        if bend:
            path = _clear(places, path, years, days, obstacles)
        return flight(_length(path)), path

    # The straight aim first (cheap), then around what is in the way.
    days = flight(_dist(start, places.at(b, years)))
    for bend in (False, True):
        for _ in range(TravelConfig.BEND_ROUNDS if bend else TravelConfig.AIM_ROUNDS):
            aimed = days
            again, path = aim(days, bend)
            done = abs(again - days) < 1e-5
            days = again
            if done:
                break
    last = TravelConfig.TRACK_POINTS - 1
    track = [places.at(b, years + aimed / YEAR_DAYS * k / last) for k in range(TravelConfig.TRACK_POINTS)]
    return days, path, track


# ── ballistic flight ────────────────
# A Hohmann transfer: half an ellipse from one orbit to the other around the
# centre both ends share, t = π √(((r₁ + r₂)/2)³ / GM), leaving when the
# destination will be opposite on arrival. Orbits taken as circular, at the
# distance each end is at, and in the reference plane; leaving and arriving
# cost nothing (no Δv budget); no slingshots.

def _chain(places: Places, ref: str) -> Optional[list[str]]:
    """What `ref` orbits, outermost first, ending with itself: a planet
    ["host:<key>", "<id>"], a moon one more; a point of interest its anchor's
    chain and itself — L1, L2 and an orbit above a body around that body,
    L3–L5 beside it. None for a star: no place to coast to."""
    if ref.startswith("star:"):
        return None
    planet, moon = places._body(ref)
    if planet is not None:
        out = [f"host:{planet.get('host')}", str(planet["id"])]
        return out + [ref] if moon is not None else out
    poi = next(p for p in places.data["points_of_interest"] if str(p["id"]) == ref)
    anchor = poi["anchor"]
    if anchor["body"] == "star":
        return [f"host:{anchor.get('host')}", ref]
    body = _chain(places, str(anchor["body"]))
    if body is None:
        return None
    return (body[:-1] if anchor.get("point") in ("L3", "L4", "L5") else body) + [ref]


def _centre_at(places: Places, centre: str, years: float) -> tuple:
    """Where `centre` — a "host:<key>" or a body's reference — is `years`
    after the epoch, in AU."""
    if centre.startswith("host:"):
        return places.hosts(years).get(centre[5:], (0.0, 0.0, 0.0))
    return places.at(centre, years)


def _gm(places: Places, centre: str) -> Optional[float]:
    """The centre's G·M in m³/s²: a host's from its stars' mass, a body's
    from its gravity and radius (orbits.mass)."""
    if centre.startswith("host:"):
        host = places.data["hosts"].get(centre[5:])
        return host["mass"] * orbits.SUN_MASS * orbits.G if host else None
    planet, moon = places._body(centre)
    body = moon or planet
    if not body or not body.get("gravity") or not body.get("radius"):
        return None
    return body["gravity"] * orbits.STANDARD_GRAVITY * (body["radius"] * 1000) ** 2


def _period(places: Places, ref: str) -> Optional[float]:
    """How long `ref` takes round what it orbits, in years: a point at a
    Lagrange point as long as its body."""
    planet, moon = places._body(ref)
    if planet is not None:
        return (moon or planet).get("period")
    poi = next(p for p in places.data["points_of_interest"] if str(p["id"]) == ref)
    anchor = poi["anchor"]
    if anchor["body"] == "star":
        host = places.data["hosts"].get(anchor.get("host"))
        return math.sqrt(anchor["au"] ** 3 / host["mass"]) if host else None
    if anchor.get("point"):
        planet, moon = places._body(str(anchor["body"]))
        return (moon or planet or {}).get("period")
    return poi.get("period")


def _transfer_years(r1: float, r2: float, gm: float) -> float:
    """A Hohmann transfer's time in years, from an orbit of `r1` AU to one of
    `r2` AU around a centre of G·M `gm` (m³/s²)."""
    a = (r1 + r2) / 2 * AU_M
    return math.pi * math.sqrt(a ** 3 / gm) / DAY_S / YEAR_DAYS


def _wrap(angle: float) -> float:
    """`angle` (radians) brought into −π to π."""
    return (angle + math.pi) % (2 * math.pi) - math.pi


def _ballistic(places: Places, a: str, b: str, years: float) -> tuple[Optional[list[Leg]], float, str]:
    """The legs from `a` to `b` coasting — a wait for the window where there
    is one, then the transfer — their days, or None and why not."""
    ca, cb = _chain(places, a), _chain(places, b)
    if ca is None or cb is None:
        return None, math.inf, "a star is no place to coast to or from"
    k = 0
    while k < min(len(ca), len(cb)) and ca[k] == cb[k]:
        k += 1
    if k == 0:
        return None, math.inf, "they orbit different stars: no one orbit joins them"
    centre, gm = ca[k - 1], _gm(places, ca[k - 1])
    if gm is None:
        return None, math.inf, f"{places.names.get(centre, 'what they orbit')} has no mass to coast around"
    # What each end leaves or arrives as — a moon's planet, when the other end
    # is around the star — or None for the centre itself, from its low orbit.
    oa, ob = (ca[k] if k < len(ca) else None), (cb[k] if k < len(cb) else None)
    surface = ((places._body(centre)[1] or places._body(centre)[0] or {}).get("radius") or 0) / orbits.AU_KM

    def rel(ref, t):
        return _add(places.at(ref, t), _centre_at(places, centre, t), -1)

    def polar(ref, t):
        x, y, z = rel(ref, t)
        return math.sqrt(x * x + y * y + z * z), math.atan2(y, x)

    some = oa or ob
    _, now_angle = polar(some, years)
    _, ahead = polar(some, years + (_period(places, some) or 1.0) * TravelConfig.ORBIT_SENSE_SHARE)
    sense = 1 if _wrap(ahead - now_angle) >= 0 else -1

    def transfer(t):
        """(years in flight, r₁, θ₁, r₂, θ₂) leaving at `t`."""
        r1, th1 = polar(oa, t) if oa else (surface, None)
        r2 = polar(ob, t)[0] if ob else surface
        flight = _transfer_years(r1, r2, gm)
        if ob:
            r2, th2 = polar(ob, t + flight)
            flight = _transfer_years(r1, r2, gm)
            r2, th2 = polar(ob, t + flight)
        else:
            th2 = th1 + sense * math.pi
        return flight, r1, (th1 if oa else th2 - sense * math.pi), r2, th2

    launch = years
    if oa and ob:
        pa, pb = _period(places, oa), _period(places, ob)
        synodic = 1 / abs(1 / pa - 1 / pb) if pa and pb and pa != pb else math.inf
        if synodic > TravelConfig.MAX_SYNODIC_YEARS:
            return None, math.inf, "no launch window: their orbits are too alike to line up (phasing burns, not a coast)"

        def miss(t):
            flight, _, th1, _, th2 = transfer(t)
            return _wrap(th2 - th1 - math.pi)

        steps = int(TravelConfig.WINDOW_STEPS * 1.05)
        dt = synodic * 1.05 / steps
        found, before = None, miss(years)
        for n in range(1, steps + 1):
            t = years + n * dt
            after = miss(t)
            if before * after <= 0 and abs(before) < math.pi / 2 and abs(after) < math.pi / 2:
                low, high = t - dt, t
                for _ in range(TravelConfig.WINDOW_BISECT):
                    mid = (low + high) / 2
                    low, high = (mid, high) if miss(low) * miss(mid) > 0 else (low, mid)
                found = (low + high) / 2
                break
            before = after
        if found is None:
            return None, math.inf, "no launch window found"
        launch = found

    flight, r1, th1, r2, th2 = transfer(launch)
    semi, e = (r1 + r2) / 2, abs(r2 - r1) / (r1 + r2)
    n = TravelConfig.BALLISTIC_POINTS
    # Even in time, not in angle — slow far out, fast near the centre (Kepler's
    # second law): the map moves the ship from point to point at an even pace.
    start_nu = 0.0 if r1 <= r2 else math.pi                     # from periapsis outwards, apoapsis inwards
    # Out of the plane, eased from where the start is to where the end is
    # met: the transfer is worked out flat, the bodies' orbits are inclined.
    z1 = rel(oa, launch)[2] if oa else 0.0
    z2 = rel(ob, launch + flight)[2] if ob else 0.0
    path = []
    for m in range(n + 1):
        mean = start_nu + math.pi * m / n
        big_e = mean
        for _ in range(30):
            step = (big_e - e * math.sin(big_e) - mean) / (1 - e * math.cos(big_e))
            big_e -= step
            if abs(step) < 1e-12:
                break
        nu = 2 * math.atan2(math.sqrt(1 + e) * math.sin(big_e / 2), math.sqrt(1 - e) * math.cos(big_e / 2))
        r = semi * (1 - e * math.cos(big_e))
        th = th1 + sense * (nu - start_nu)
        path.append(_add(_centre_at(places, centre, launch + flight * m / n),
                         (r * math.cos(th), r * math.sin(th), z1 + (z2 - z1) * m / n)))
    last = TravelConfig.TRACK_POINTS - 1
    track = [places.at(b, launch + flight * j / last) for j in range(TravelConfig.TRACK_POINTS)]
    legs = []
    if launch > years:
        waited = [places.at(a, years + (launch - years) * j / last) for j in range(TravelConfig.TRACK_POINTS)]
        legs.append(Leg("wait", places.names[a], places.names[a], 0.0, (launch - years) * YEAR_DAYS, waited))
    # How fast it leaves and arrives around the centre (vis-viva), km/s.
    semi_m = semi * AU_M
    speeds = tuple(math.sqrt(gm * (2 / (r * AU_M) - 1 / semi_m)) / 1000 for r in (r1, r2))
    legs.append(Leg("ballistic", places.names[a], places.names[b], _length(path), flight * YEAR_DAYS, path,
                    track=track, speeds=speeds))
    return legs, (launch - years + flight) * YEAR_DAYS, ""


def _fly(places: Places, a: str, b: str, years: float, sublight: dict[str, Any],
         obstacles: list[tuple[str, float]]) -> tuple[Optional[list[Leg]], float, str]:
    """Sublight from `a` to `b`: at its thrust, or coasting at none."""
    if not sublight["g"]:
        return _ballistic(places, a, b, years)
    days, path, track = _sublight(places, a, b, years, sublight, obstacles)
    return [Leg("sublight", places.names[a], places.names[b], _length(path), days, path, track=track)], days, ""


def _hop_days(au: float, grade: str, gates: dict[str, Any]) -> float:
    """Days for a jumpgate hop over `au` AU: an early gate's by the
    distance, a mature one's flat."""
    if grade == "early":
        return au / gates["early"]["au_per_hour"] / DAY_HOURS
    return gates["mature"]["minutes"] / 60 / DAY_HOURS


def jumpgate_pairs(doc_system: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Each jumpgate with a partner: its id → (the partner's id, grade)."""
    gates = {str(p["id"]): p for p in doc_system.get("points_of_interest") or [] if p.get("kind") == "jumpgate"}
    return {ref: (str(p["pair"]), p.get("grade", "mature")) for ref, p in gates.items()
            if str(p.get("pair")) in gates}


def plan(doc_system: dict[str, Any], start: str, end: str, depart: float,
         overrides: Optional[dict[str, Any]] = None, settings: Optional[dict[str, Any]] = None,
         density: Optional[float] = None, nebula: Optional[dict[str, Any]] = None) -> list[Option]:
    """Every way from `start` to `end` (references or names) leaving at
    `depart` (on the calendar's axis), fastest first. `density` is
    the web's where the system lies (galaxy.travel.density_at, which needs
    the whole galaxy for its regions); without it, average web. In a void
    (0) no jumpgate works either: every way of travel needs the web. Refused
    (ValueError) when both are the same stop; KeyError for one the system
    does not have. Inside a `nebula` (galaxy.travel.nebula_at) sublight keeps
    to its safe speed, or is barred — the jumpgates' legs to and from the
    gates with it; the own drive, through the medium, is untouched."""
    from galaxy import nebulae
    settings = merged(settings or load(), overrides)
    sublight, gates = settings["sublight"], settings["jumpgates"]
    cap = nebulae.sublight_limit(nebula) if nebula else None
    if cap:
        sublight = {**sublight, "cap": cap}
    places = Places(doc_system)
    obstacles = places.obstacles(sublight)
    a, b = places.ref(start), places.ref(end)
    if a == b:
        raise ValueError("A trip goes somewhere else")
    years = depart - places.data["epoch_year"]
    if cap == 0:
        legs, days = None, math.inf
        why = (f"Sublight is barred inside {nebula['name']}: its gas and dust, "
               f"{nebulae.density(nebula):,.0f} particles per cm³, would wreck a ship")
    else:
        legs, days, why = _fly(places, a, b, years, sublight, obstacles)
    out = [Option("sublight", legs, days, arrival=depart + days / YEAR_DAYS) if legs is not None
           else Option("sublight", [], math.inf, False, why)]
    rho = 1.0 if density is None else density
    own_drive = settings["own_drive"]
    if rho >= own_drive["min_density"]:
        speed = own_drive["ly_per_day"] * rho * LY_AU / DAY_HOURS * own_drive["in_system_efficiency"]
        own, path, track = _sublight(places, a, b, years, sublight, obstacles, speed)
        out.append(Option("own drive", [Leg("own drive", places.names[a], places.names[b], _length(path), own, path,
                                            track=track)], own, arrival=depart + own / YEAR_DAYS, rate=speed * DAY_HOURS))
    # No gates without the web, nor where sublight cannot reach them.
    pairs = jumpgate_pairs(doc_system) if rho > 0 and cap != 0 else {}
    gated = _jumpgates(places, pairs, a, b, years, sublight, obstacles, gates)
    if gated is not None and gated.days < days:
        gated.arrival = depart + gated.days / YEAR_DAYS
        out.append(gated)
    return sorted(out, key=lambda o: (not o.reachable, o.days))


def _jumpgates(places, pairs, a, b, years, sublight, obstacles, gates) -> Optional[Option]:
    """The fastest trip through at least one gate hop: Dijkstra over the
    gates, each edge timed from when it is taken (the bodies move)."""
    if not pairs:
        return None
    best: dict[tuple[str, bool], float] = {(a, False): 0.0}
    came: dict[tuple[str, bool], tuple] = {}
    queue = [(0.0, a, False)]
    while queue:
        days, here, used = heapq.heappop(queue)
        if days > best.get((here, used), math.inf):
            continue
        if here == b:
            if used:
                break
            continue
        now = years + days / YEAR_DAYS
        steps = []
        for there in [gate for gate in pairs if gate != here] + ([b] if used else []):
            legs, d, _ = _fly(places, here, there, now, sublight, obstacles)
            if legs is not None:
                steps.append((there, used, legs, d))
        if here in pairs:
            other, grade = pairs[here]
            p, q = places.at(here, now), places.at(other, now)
            hop = _hop_days(_dist(p, q), grade, gates)
            steps.append((other, True, [Leg("jumpgate", places.names[here], places.names[other], _dist(p, q),
                                            hop, [p, q], grade=grade)], hop))
        for there, now_used, legs, d in steps:
            total = days + d
            if total < best.get((there, now_used), math.inf):
                best[(there, now_used)] = total
                came[(there, now_used)] = ((here, used), legs)
                heapq.heappush(queue, (total, there, now_used))
    if (b, True) not in best:
        return None
    legs, state = [], (b, True)
    while state in came:
        state, step = came[state]
        legs[:0] = step
    return Option("jumpgates", legs, best[(b, True)])


def as_json(option: Option, places: Optional[Places] = None) -> dict[str, Any]:
    """A way as the system map draws it: each leg's points in AU, where its
    end moves while it is flown, and with `places` the references of its
    ends — the map draws moons' orbits and L1/L2 enlarged, and puts a leg's
    ends on the bodies as it draws them."""
    refs = {}
    if places is not None:
        for ref, name in places.names.items():
            refs.setdefault(name, ref)
    # Thrust to halfway and brake: the peak, at turnover, is twice the average.
    thrust = [2 * leg.ly / leg.days for leg in option.legs if leg.kind == "sublight" and leg.days > 0]
    return {"name": option.name, "days": option.days if option.reachable else None, "reachable": option.reachable,
            "why": option.why, "arrival": date_text(option.arrival) if option.arrival is not None else None,
            "rate": option.rate, "average": option.average, **({"peak": max(thrust)} if thrust else {}),
            "legs": [{"kind": leg.kind, "start": leg.start, "end": leg.end, "au": leg.ly, "days": leg.days,
                      "refs": [refs.get(leg.start), refs.get(leg.end)],
                      "grade": leg.grade, "points": [list(point) for point in leg.path],
                      **({"speeds": list(leg.speeds)} if leg.speeds else {}),
                      "track": [list(point) for point in leg.track]} for leg in option.legs]}
