"""Orbits of planets and moons: the elements, their draw as a group, where a
body is at a date, and what does not fit.

A planet's `orbit` holds `au` (semi-major axis), a moon's `km`; both hold
`e` (eccentricity), `i` (inclination, degrees: a planet's against the
system's plane, a moon's against its planet's equator), `node` (longitude of
the ascending node), `periapsis` (argument of periapsis) and `anomaly` (mean
anomaly at the epoch), all in degrees. A planet's `tilt` is its axial tilt
against its orbit, in degrees — its equator, where its rings and the plane
its moons are measured from lie. Periods are derived (Kepler), never stored.
The epoch is the calendar's (galaxy.calendar).

Drawn by star and class, as a group: spacing geometric
(mostly 1.4–2×, wider beyond the frost line, now and then a wide gap), a
habitable planet in the habitable zone, cold gas giants beyond the frost
line, the order of the orbits kept, an orbit already set kept. Without a
spectral class for the star there is nothing to go by, and none is drawn;
a moon's needs its planet's mass, so its planet's radius and class.
"""

from __future__ import annotations

import copy
import math
import random
from typing import Any, Optional

from galaxy import bodies, calendar
from galaxy.hierarchy import (Node, Tree, host_names, host_star, inner_limit, outer_limit, p_ratio, s_ratio, tree,
                              hosts as host_list)
from galaxy.stars import Star, star


def epoch() -> str:
    """The date the orbits' phases are given for: the calendar's epoch."""
    return calendar.current().epoch


def epoch_year() -> int:
    """The epoch as a year on the calendar's axis."""
    return calendar.current().epoch_year


G = 6.674e-11               # m³ kg⁻¹ s⁻²
SUN_MASS = 1.989e30         # kg
EARTH_MASS = 5.972e24       # kg
AU_KM = 1.496e8
STANDARD_GRAVITY = 9.80665  # m/s², what "1 g" is

# How far a draw tries before it settles for the best: each try is a whole
# system, and a system has at most a dozen planets.
TRIES = 400


# ── derived ───────────────────────────────────────────────────────────────────

def mass(body: dict[str, Any]) -> Optional[float]:
    """A planet's or moon's mass in kg, from its derived gravity and radius:
    m = g·R²/G. None without a radius or a class to go by."""
    facts = bodies.facts(body)
    if facts is None or body.get("class") not in bodies.RANGES:
        return None
    radius_m = facts["radius"] * 1000
    return facts["gravity"] * STANDARD_GRAVITY * radius_m ** 2 / G


def period_years(au: float, star_mass: float) -> float:
    """Kepler's third law, in years: P² = a³ / M (a in AU, M in suns)."""
    return math.sqrt(au ** 3 / star_mass)


def moon_period_days(km: float, planet_mass: float) -> float:
    """A moon's period in days around a planet of `planet_mass` kg."""
    return 2 * math.pi * math.sqrt((km * 1000) ** 3 / (G * planet_mass)) / 86_400


def hill_radius_km(au: float, e: float, planet_mass: float, star_mass: float) -> float:
    """Within this the planet holds its moons (at periapsis, to be safe):
    a(1 − e)·(m / 3M)^(1/3)."""
    return au * AU_KM * (1 - e) * (planet_mass / (3 * star_mass * SUN_MASS)) ** (1 / 3)


def position(orbit: dict[str, Any], years: float, period: float) -> tuple[float, float, float]:
    """Where the body is `years` after the epoch, in the orbit's own unit
    (AU or km), x and y in the reference plane: Kepler's equation solved
    by Newton's method."""
    a = orbit.get("au") or orbit.get("km") or 0.0
    e = orbit.get("e", 0.0)
    # Reduced to one turn: Newton's start at π holds only within it.
    m = (math.radians(orbit.get("anomaly", 0.0)) + 2 * math.pi * years / period) % (2 * math.pi)
    big_e = m if e < 0.8 else math.pi
    for _ in range(30):
        step = (big_e - e * math.sin(big_e) - m) / (1 - e * math.cos(big_e))
        big_e -= step
        if abs(step) < 1e-12:
            break
    x = a * (math.cos(big_e) - e)
    y = a * math.sqrt(1 - e * e) * math.sin(big_e)
    w, node, inc = (math.radians(orbit.get(k, 0.0)) for k in ("periapsis", "node", "i"))
    xw, yw = x * math.cos(w) - y * math.sin(w), x * math.sin(w) + y * math.cos(w)
    return (xw * math.cos(node) - yw * math.cos(inc) * math.sin(node),
            xw * math.sin(node) + yw * math.cos(inc) * math.cos(node),
            yw * math.sin(inc))


# ── more than one star ───────────────
# Everything orbits a host: a star, or a group of stars' shared centre of
# gravity (galaxy.hierarchy); a planet's, a belt's and a companion star's
# default is the primary.

def host_node(system: dict[str, Any], body: dict[str, Any], t: Optional[Tree] = None) -> Optional[Node]:
    """What the planet, belt or point of interest orbits; None for a host
    the system's stars do not make."""
    t = t or tree(system)
    return t.node(host_names(system, body.get("host")))


def host_mass(system: dict[str, Any], body: dict[str, Any], t: Optional[Tree] = None) -> Optional[float]:
    """The mass of what `body` orbits, in suns; None where the host is not
    made or has no class to go by."""
    node = host_node(system, body, t)
    return node.mass if node else None


def star_orbits(t: Tree) -> dict[str, tuple[dict[str, Any], Node, Node]]:
    """Each companion star's (orbit, host, itself with whatever orbits it),
    by name."""
    out = {}
    for group in t.by_names.values():
        for orbit, sub in group.satellites:
            leaf = sub
            while leaf.core is not None:
                leaf = leaf.core
            out[leaf.name] = (orbit, group.core, sub)
    return out


def companion_period(t: Tree, name: str) -> Optional[float]:
    """A companion's period around its host, in years."""
    found = star_orbits(t).get(name)
    if found is None:
        return None
    orbit, host, sub = found
    if not orbit.get("au") or host.mass is None or sub.mass is None:
        return None
    return math.sqrt(orbit["au"] ** 3 / (host.mass + sub.mass))


def _extent(node: Node) -> float:
    """How far a group's stars reach from its centre, in AU (roughly)."""
    if node.core is None:
        return 0.0
    return max([o.get("au", 0.0) * (1 + o.get("e", 0.0)) for o, _ in node.satellites] + [_extent(node.core)])


def _reach(system: dict[str, Any], t: Tree, inside: Node) -> float:
    """How far from `inside`'s centre the planets and belts orbiting it,
    or anything in it, reach, in AU."""
    reach = _extent(inside)
    for body in list(system.get("planets") or []) + list(system.get("belts") or []):
        node = host_node(system, body, t)
        if node is None or not node.names <= inside.names:
            continue
        if "outer" in body:
            far = body["outer"]
        else:
            orbit = body.get("orbit") or {}
            if not orbit.get("au"):
                continue
            far = orbit["au"] * (1 + orbit.get("e", 0.0))
        reach = max(reach, far + (0.0 if node is inside else _extent(inside)))
    return reach


def _closest_around(system: dict[str, Any], t: Tree, group: Node) -> Optional[float]:
    """The nearest a planet or belt orbiting `group`, or a group around it,
    comes to its centre, in AU."""
    near = []
    for body in list(system.get("planets") or []) + list(system.get("belts") or []):
        node = host_node(system, body, t)
        if node is None or not group.names <= node.names:
            continue
        if "inner" in body:
            near.append(body["inner"])
        elif (body.get("orbit") or {}).get("au"):
            near.append(body["orbit"]["au"] * (1 - body["orbit"].get("e", 0.0)))
    return min(near) if near else None


def companion_range(system: dict[str, Any], t: Tree, name: str, e: float) -> Optional[tuple[float, float]]:
    """Where a companion's orbit may lie, in AU, for an eccentricity: far
    enough that what orbits its host and itself stays, close enough that
    what orbits the two of them does. None without the masses to go by."""
    found = star_orbits(t).get(name)
    if found is None:
        return None
    _, host, sub = found
    if host.mass is None or sub.mass is None:
        return None
    total = host.mass + sub.mass
    low = 0.0
    for side, other in ((host, sub), (sub, host)):
        reach = _reach(system, t, side)
        if reach:
            low = max(low, reach / s_ratio(e, other.mass / total))
    if host.core is not None:
        low = max(low, (inner_limit(host) or 0.0) / (1 - e))
    high = math.inf
    pair = sub.parent
    near = _closest_around(system, t, pair) if pair is not None else None
    if near:
        high = near / p_ratio(e, sub.mass / total)
    # A planet around the pair that has no orbit yet still needs its zone:
    # the pair close enough for a habitable one to circle it in its
    # habitable zone (a habitable planet around a binary).
    # The planets inside it take room too: each orbit 1.4–2× the last.
    if pair is not None:
        lit, inside = host_star(pair), 0
        for planet in system.get("planets") or []:
            node = host_node(system, planet, t)
            if lit is None or node is not pair:
                continue
            if not (planet.get("orbit") or {}).get("au"):
                low_z, high_z = zone(planet.get("class"), lit)
                if high_z < math.inf:                 # a zone with an outer edge: room to its middle
                    high = min(high, (low_z + high_z) / 2 / 1.5 ** inside / p_ratio(e, sub.mass / total))
            inside += 1
    return low, high


def draw_companions(system: dict[str, Any], rng: Optional[random.Random] = None, redraw: bool = False) -> int:
    """Draw an orbit for each companion with a class but none (every one,
    with `redraw`), fitted to the hosts: wide of what orbits its host and
    itself, close enough for what orbits the two of them; with neither,
    anywhere from 0.05 to 100 AU. None where no distance fits — a finding.
    How many were drawn."""
    rng, count = rng or random.Random(), 0
    for companion in (system.get("stars") or [])[1:]:
        name = (companion.get("name") or "").strip()
        if star(companion.get("spectral_class")) is None or (companion.get("orbit") and not redraw):
            continue
        if redraw:
            companion.pop("orbit", None)
        t = tree(system)
        e = round(rng.uniform(0, 0.5), 3)
        found = companion_range(system, t, name, e)
        if found is None:
            continue
        low, high = found
        if low >= high * 0.9:
            e = 0.0
            low, high = companion_range(system, t, name, e)
            if low >= high * 0.9:
                continue                              # no distance fits: a finding
        # Never touching: at least twice their radii apart (R ∝ M^0.8).
        found_ = star_orbits(t)[name]
        touch = 2 * 0.00465 * sum(m ** 0.8 for m in (found_[1].mass, found_[2].mass))
        if high < math.inf:
            low = max(low * 1.1, touch / (1 - e), high * 0.05)
            au = math.exp(rng.uniform(math.log(low), math.log(high * 0.9)))
        elif low > 0:
            au = low * 1.1 * math.exp(rng.uniform(0, math.log(10)))
        else:
            au = math.exp(rng.uniform(math.log(0.05), math.log(100)))
        # A close pair is made round by its tides: within 0.1 AU nearly
        # circular, and never closer than twice their radii at periapsis.
        if au < 0.1:
            e = round(rng.uniform(0, 0.05), 3)
        au = max(au, touch / (1 - e))
        bodies.set_field(companion, "orbit", {"au": _au(au), "e": e,
                                              "i": round(_rayleigh(rng, 5, 30), 1), **_angles(rng)})
        count += 1
    return count


# ── zones ─────────────────────────────────────────────────────────────────────

def zone(body_class: Optional[str], star: Star) -> tuple[float, float]:
    """Where a planet of the class belongs, in AU; (0, ∞) for any distance."""
    inner, outer = star.habitable_zone
    return {
        "terrestrial-habitable": (inner, outer),
        "terrestrial-desert": (inner * 0.75, outer * 1.5),
        "ice-world": (outer, math.inf),
        "gas-giant-cold": (star.frost_line, math.inf),
        # From hot Jupiters to Saturn's place: galaxy.json calls Jupiter and
        # Saturn warm, at about 2 and 3.5 frost lines.
        "gas-giant-warm": (star.inner_limit, 4 * star.frost_line),
    }.get(body_class or "", (0.0, math.inf))


# What an editor's 🎲 draws a class from: never habitable — those are set by
# hand — nor "unknown", which is no class to draw.
DRAWN_CLASSES = ("terrestrial-barren", "terrestrial-desert", "gas-giant-cold", "gas-giant-warm",
                 "ice-world", "volcanic")
MOON_CLASSES = ("terrestrial-barren", "terrestrial-desert", "ice-world", "volcanic")


def _where(low: float, high: float) -> str:
    """A zone in words: "at 1.28–1.84 AU", or "beyond 3.61 AU" when it has no end."""
    return f"at {low:.2f}–{high:.2f} AU" if high != math.inf else f"beyond {low:.2f} AU"


def _clashes(planets: list[dict[str, Any]], star_: Star) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """(inner, outer) for each two planets around one star whose classes no
    orbits can fit: the inner one's class belongs
    farther out than the outer one's may lie — a cold gas giant inside the
    habitable world. Planets in their order around the star."""
    out = []
    for k, inner in enumerate(planets):
        low = zone(inner.get("class"), star_)[0]
        for outer in planets[k + 1:]:
            # Equal is a clash too: two planets cannot share the one distance.
            if low >= zone(outer.get("class"), star_)[1]:
                out.append((inner, outer))
    return out


def _fits_order(body_class: str, planet: dict[str, Any], planets: list[dict[str, Any]], star_: Star) -> bool:
    """Whether `planet` may take `body_class` among the classes the other
    `planets` (in their order) already have: no clash with any of them."""
    k = planets.index(planet)
    low, high = zone(body_class, star_)
    return (all(zone(p.get("class"), star_)[0] < high for p in planets[:k] if p.get("class"))
            and all(low < zone(p.get("class"), star_)[1] for p in planets[k + 1:] if p.get("class")))


def draw_class(system: dict[str, Any], planet: dict[str, Any], moon: bool = False,
               rng: Optional[random.Random] = None) -> str:
    """A class for a planet, or with `moon` for a moon of it: one whose zone
    holds the planet's orbit around its star — so the draw never makes an
    orbit-zone finding — evenly among those; any of them without an orbit or
    a star to go by. A moon is no gas giant. A planet's class never clashes
    with those the planets around the same star already have: none that
    belongs beyond a habitable world further out."""
    rng = rng or random.Random()
    choices = MOON_CLASSES if moon else DRAWN_CLASSES
    au = (planet.get("orbit") or {}).get("au")
    node = tree(system).node(host_names(system, planet.get("host")))
    star_ = host_star(node) if node else None
    if au and star_ is not None:
        fitting = [c for c in choices if zone(c, star_)[0] <= au <= zone(c, star_)[1]]
        choices = fitting or choices
    if not moon and star_ is not None:
        around = host_names(system, planet.get("host"))
        siblings = [p for p in system.get("planets") or [] if host_names(system, p.get("host")) == around]
        ordered = [c for c in choices if _fits_order(c, planet, siblings, star_)]
        choices = ordered or choices
    return rng.choice(choices)


def _miss(au: float, where: tuple[float, float]) -> float:
    """How far outside its zone a distance lies, as a log ratio; 0 inside."""
    low, high = where
    if au < low:
        return math.log(low / au)
    if au > high:
        return math.log(au / high)
    return 0.0


# ── the draw ──────────────────────────────────────────────────────────────────

def _rayleigh(rng: random.Random, sigma: float, cap: float) -> float:
    """A Rayleigh-distributed draw of scale `sigma`, at most `cap`: for
    eccentricities and inclinations, mostly small."""
    return min(cap, sigma * math.sqrt(-2 * math.log(1 - rng.random())))


def _angles(rng: random.Random) -> dict[str, float]:
    """An orbit's node, periapsis and anomaly at random, in degrees."""
    return {k: round(rng.uniform(0, 360), 1) for k in ("node", "periapsis", "anomaly")}


def _au(value: float) -> float:
    """A distance in AU rounded as it is stored: 3 decimals below 10 AU, 2 beyond."""
    return round(value, 3 if value < 10 else 2)


def draw_planets(system: dict[str, Any], rng: Optional[random.Random] = None,
                 redraw: bool = False, around: Optional[str] = None) -> int:
    """Draw orbits for the system's planets that have none (all, with
    `redraw`), as a group per host around the existing ones: of TRIES spacings,
    the one whose planets lie best in their zones and within where their
    host's orbits stay. How many were drawn; none for a host without the
    stars' classes to go by. `around` "star" or "group" draws only the
    planets of single stars, or of groups."""
    rng, t, count = rng or random.Random(), tree(system), 0
    by_host: dict[frozenset, list[dict[str, Any]]] = {}
    for planet in system.get("planets") or []:
        by_host.setdefault(host_names(system, planet.get("host")), []).append(planet)
    for names, planets in by_host.items():
        if around is not None and (len(names) > 1) != (around == "group"):
            continue
        node = t.node(names)
        host = host_star(node) if node else None
        if host is None:
            continue
        near = inner_limit(node) or 0.0
        far = (outer_limit(node) or (math.inf, ""))[0]
        count += _draw_group(planets, host, near, far, rng, redraw)
    return count


def _spacing(rng: random.Random, previous: float, star: Star) -> float:
    """How much wider the next orbit is than the last (wider gaps). Mostly 1.4–2×, as close-packed systems are; beyond the
    frost line 1.5–2.5×, as Sol's outer planets; and now and then a wide
    gap of 2–3.5×, as from Mars to Jupiter."""
    if rng.random() < 0.2:
        return rng.uniform(2.0, 3.5)
    if previous > star.frost_line:
        return rng.uniform(1.5, 2.5)
    return rng.uniform(1.4, 2.0)


def _draw_group(planets: list[dict[str, Any]], star: Star, near: float, far: float,
                rng: random.Random, redraw: bool) -> int:
    """Draw orbits for one host's planets that have none (all, with
    `redraw`), spaced geometrically between `near` and `far` AU. How many."""
    fixed = [None if redraw else (p.get("orbit") or {}).get("au") for p in planets]
    if all(a is not None for a in fixed):
        return 0
    best, best_score = None, math.inf
    for _ in range(TRIES):
        sequence, score, previous = [], 0.0, None
        for k, planet in enumerate(planets):
            if fixed[k] is not None:
                a = fixed[k]
            elif previous is None:
                # As far out as the habitable zone: a system's first planet
                # may be its habitable one — but outside a pair it circles.
                low = max(star.inner_limit * 2, near * 1.2)
                a = math.exp(rng.uniform(math.log(low), math.log(max(low * 1.5, star.habitable_zone[1]))))
            else:
                a = previous * _spacing(rng, previous, star)
            a = _au(a)                            # scored as it will be stored
            if previous is not None and fixed[k] is not None and a < previous * 1.1:
                score += 10                       # it ran into an orbit already set
            if fixed[k] is None:
                score += _miss(a, zone(planet.get("class"), star))
                if a < near * 1.1 or a > far * 0.85:
                    score += 10                   # where its host would not keep it
            sequence.append(a)
            previous = a
        if score < best_score:
            best, best_score = sequence, score
    count = 0
    for planet, a, keep in zip(planets, best, fixed):
        if keep is not None:
            continue
        calm = planet.get("class") in ("terrestrial-habitable", "terrestrial-desert")
        bodies.set_field(planet, "orbit", {
            "au": _au(a), "e": round(_rayleigh(rng, 0.03 if calm else 0.06, 0.1 if calm else 0.35), 3),
            "i": round(_rayleigh(rng, 1.5, 12), 1), **_angles(rng)})
        count += 1
    return count


def draw_system(system: dict[str, Any], rng: Optional[random.Random] = None, redraw: bool = False) -> int:
    """Draw every orbit the system lacks — all, with `redraw` — in the order the
    stars allow: the planets of
    single stars, then the companions fitted around them, then the planets
    of groups outside their stars; then tilts and moons. How many."""
    rng = rng or random.Random()
    if redraw:
        for item in list(system.get("planets") or []) + list((system.get("stars") or [])[1:]):
            item.pop("orbit", None)
    count = _sol(system, rng) if system.get("name") == "Sol" else 0
    count += (draw_planets(system, rng, around="star") + draw_companions(system, rng)
             + draw_planets(system, rng, around="group") + draw_tilts(system, rng) + draw_plane(system))
    for planet in system.get("planets") or []:
        count += draw_moons(system, planet, rng, redraw=redraw)
    return count


# What makes an arrangement unrealistic: the draw tries again.
_BAD = ("orbit-binary", "star-binary", "star-host", "orbit-host")


def draw_arrangement(system: dict[str, Any], rng: Optional[random.Random] = None, tries: int = 40) -> str:
    """Draw the stars' arrangement whole: a class for each companion without one, the outer
    stars of three or more around the inner pair or the primary, and what
    the planets orbit, by how often each occurs — close pairs mostly with
    planets around both, wide ones with planets around each star, now and
    then both at once. Then every planet's and companion's orbit drawn
    again, until one draws without a warning (at most `tries`). What was
    drawn, in words. Refused (ValueError) without a primary with a spectral
    class and a companion."""
    from galaxy.stars import draw_companion_class
    rng = rng or random.Random()
    stars = system.get("stars") or []
    main = star((stars[0].get("spectral_class") if stars else None) or system.get("spectral_class"))
    if main is None or len(stars) < 2:
        raise ValueError("An arrangement needs a primary with a spectral class and a companion")
    for companion in stars[1:]:
        if star(companion.get("spectral_class")) is None:
            companion["spectral_class"] = draw_companion_class(main, rng)
    names = [(s.get("name") or "").strip() for s in stars]
    planets = system.get("planets") or []
    best, best_bad = None, math.inf
    for _ in range(tries):
        # Hierarchical, as real triples are: an outer star around the pair
        # (or group) inside it, more often than around the primary alone.
        for k, companion in enumerate(stars[2:], start=2):
            if rng.random() < 0.7:
                companion["host"] = "+".join(names[:k])
            else:
                companion.pop("host", None)
        root = "+".join(names)
        r = rng.random()
        if r < 0.3:
            kind, hosts = "close", [root] * len(planets)
        elif r < 0.4 and len(planets) > 1:
            outer = rng.randint(1, max(1, len(planets) // 2))
            kind, hosts = "mixed", [names[0]] * (len(planets) - outer) + [root] * outer
        else:
            masses = [star(s.get("spectral_class")).mass for s in stars]
            kind, hosts = "wide", [rng.choices(names, weights=masses)[0] for _ in planets]
        for planet, host in zip(planets, hosts):
            if host == names[0]:
                planet.pop("host", None)
            else:
                bodies.set_field(planet, "host", host)
        for item in planets + stars[1:]:
            item.pop("orbit", None)
        draw_system(system, rng)
        bad = sum(1 for f in findings(system) if f[0] in _BAD or (f[0] in ("orbit-zone", "orbit-spacing") and not f[2]))
        if bad < best_bad:
            best, best_bad = copy.deepcopy((stars, planets, kind)), bad
        if bad == 0:
            break
    system["stars"][:] = best[0]
    if planets:                  # a system without planets has no list to put back
        system["planets"][:] = best[1]
    kind = best[2]
    words = {"close": "a close pair, every planet around all the stars",
             "mixed": "planets around the primary, the outermost around all the stars",
             "wide": "the stars wide apart, each planet around one of them"}[kind] if planets else \
        "the stars' orbits; no planets to place"
    return words + ("" if best_bad == 0 else f" — {best_bad} warning{'s' if best_bad > 1 else ''} left")


def draw_tilt(rng: random.Random) -> float:
    """An axial tilt: mostly modest — Earth's 23°, Mars' 25° — and now and
    then extreme, as Uranus' 98° or Venus' 177°."""
    if rng.random() < 0.1:
        return round(rng.uniform(0, 180), 1)
    return round(min(89.0, abs(rng.gauss(0, 20))), 1)


def draw_tilts(system: dict[str, Any], rng: Optional[random.Random] = None) -> int:
    """Draw an axial tilt for each planet that has none, and the way it leans
    (`tilt_bearing`, degrees in the system's plane, any way at all) for each
    without one; how many."""
    rng, count = rng or random.Random(), 0
    for planet in system.get("planets") or []:
        if "tilt" not in planet:
            bodies.set_field(planet, "tilt", draw_tilt(rng))
            count += 1
        if "tilt_bearing" not in planet:
            bodies.set_field(planet, "tilt_bearing", round(rng.uniform(0, 360), 1))
            count += 1
    return count


def draw_plane(system: dict[str, Any]) -> int:
    """Give the system its reference plane in the galaxy, where it has none:
    Sol's the ecliptic, as it is; any other's any way at all — the
    pole evenly over the sphere, seeded by the system's name, so the same
    each time whatever else is drawn. Angles as galaxy.celestial.plane_angles
    gives them. How many: 1 or 0."""
    from galaxy import celestial
    if "plane" in system:
        return 0
    if system.get("name") == "Sol":
        system["plane"] = celestial.ecliptic()
        return 1
    rng = bodies.seeded(system.get("name") or "", "plane")
    system["plane"] = {"i": round(math.degrees(math.acos(rng.uniform(-1, 1))), 1),
                       # Rounded, 359.96 would be 360, which the schema refuses: 0.
                       "node": round(rng.uniform(0, 360), 1) % 360, "zero": round(rng.uniform(0, 360), 1) % 360}
    return 1


def draw_moons(system: dict[str, Any], planet: dict[str, Any], rng: Optional[random.Random] = None,
               redraw: bool = False) -> int:
    """Draw orbits for the planet's moons that have none (all, with
    `redraw`), in km: geometric spacing from a few planet radii outwards,
    kept well inside the planet's Hill radius. How many were drawn; none
    without the planet's orbit, mass or the star."""
    central, rng = host_mass(system, planet), rng or random.Random()
    moons = planet.get("moons") or []
    orbit, m = planet.get("orbit") or {}, mass(planet)
    if central is None or not moons or not orbit.get("au") or m is None:
        return 0
    radius = planet["radius"]
    limit = 0.4 * hill_radius_km(orbit["au"], orbit.get("e", 0.0), m, central)
    previous, count = None, 0
    for moon in moons:
        if not redraw and (moon.get("orbit") or {}).get("km"):
            previous = moon["orbit"]["km"]
            continue
        km = radius * rng.uniform(3, 8) if previous is None else previous * rng.uniform(1.5, 2.5)
        km = min(km, limit * (0.5 + 0.5 * rng.random()))
        bodies.set_field(moon, "orbit", {"km": int(round(km, -2)), "e": round(_rayleigh(rng, 0.02, 0.2), 3),
                                         "i": round(_rayleigh(rng, 2.0, 15), 1), **_angles(rng)})
        previous = moon["orbit"]["km"]
        count += 1
    return count


def missing(doc: dict[str, Any]) -> tuple[int, int]:
    """How many planets and moons have no orbit, and systems no plane: those
    the draw can give one, and those it cannot — no star to go by, or a moon whose planet has
    no mass (class and radius) or orbit to go by."""
    drawable = undrawable = 0
    for system in doc.get("star_systems") or []:
        if "plane" not in system:
            drawable += 1                   # its reference plane (draw_plane)
        t = tree(system)
        for planet in system.get("planets") or []:
            node = host_node(system, planet, t)
            star = host_star(node) if node else None
            if not planet.get("orbit"):
                if star is None:
                    undrawable += 1
                else:
                    drawable += 1
            elif "tilt" not in planet or "tilt_bearing" not in planet:
                drawable += 1               # a tilt to draw, whatever the star
            for moon in planet.get("moons") or []:
                if moon.get("orbit"):
                    continue
                if star is not None and mass(planet) is not None:
                    drawable += 1
                else:
                    undrawable += 1
    return drawable, undrawable


# ── Sol, as it is ─────────────────────────────────────────────────────────────

# J2000 elements: a (AU), e, i, Ω, ϖ (longitude of perihelion), L (mean
# longitude); carried to the calendar's epoch by the mean motion.
_SOL_J2000 = {
    "Mercury": (0.38710, 0.20563, 7.005, 48.331, 77.456, 252.251),
    "Venus": (0.72333, 0.00677, 3.395, 76.680, 131.533, 181.980),
    "Earth": (1.00000, 0.01671, 0.000, 348.739, 102.947, 100.464),
    "Mars": (1.52368, 0.09340, 1.850, 49.558, 336.041, 355.453),
    "Jupiter": (5.20260, 0.04849, 1.303, 100.464, 14.331, 34.351),
    "Saturn": (9.55491, 0.05551, 2.489, 113.666, 93.057, 50.077),
    "Uranus": (19.21845, 0.04630, 0.773, 74.006, 173.005, 314.055),
    "Neptune": (30.11039, 0.00899, 1.770, 131.784, 48.124, 304.349),
    "Pluto": (39.482, 0.2488, 17.14, 110.30, 224.07, 238.93),
    # The other dwarf planets and large bodies beyond Neptune: a,
    # e, i, Ω and ϖ as published; L from the date of perihelion, so where each
    # is along its orbit is as near as that date.
    "Ceres": (2.7675, 0.0758, 10.59, 80.3, 153.90, 160.92),
    "Haumea": (43.13, 0.195, 28.21, 121.9, 1.40, 192.36),
    "Makemake": (45.43, 0.161, 29.01, 79.62, 14.42, 155.74),
    "Eris": (67.86, 0.436, 44.04, 35.95, 187.55, 22.04),
    "Sedna": (506.0, 0.855, 11.93, 144.25, 95.60, 93.19),
    "Gonggong": (67.4, 0.5, 30.66, 336.8, 184.00, 277.04),
    "Quaoar": (43.69, 0.04, 7.99, 188.8, 336.30, 242.80),
    "Orcus": (39.42, 0.22, 20.57, 268.8, 341.10, 133.10),
}
# Moons: a (km), e, i to their planet's equator — their angles are drawn.
# Every moon of 100 km radius and more, and Mars's two.
_SOL_MOONS = {
    "Luna": (384_400, 0.0549, 5.145), "Phobos": (9_376, 0.0151, 1.08), "Deimos": (23_463, 0.0003, 1.79),
    "Io": (421_700, 0.0041, 0.05), "Europa": (671_034, 0.009, 0.47), "Ganymede": (1_070_412, 0.0013, 0.2),
    "Callisto": (1_882_709, 0.0074, 0.19),
    "Mimas": (185_539, 0.0196, 1.57), "Enceladus": (237_948, 0.0047, 0.02), "Tethys": (294_619, 0.0001, 1.09),
    "Dione": (377_396, 0.0022, 0.02), "Rhea": (527_108, 0.0012, 0.35), "Titan": (1_221_870, 0.0288, 0.35),
    "Hyperion": (1_500_880, 0.1230, 0.43), "Iapetus": (3_560_820, 0.0286, 15.47),
    "Phoebe": (12_947_780, 0.1562, 175.3),
    "Miranda": (129_390, 0.0013, 4.34), "Ariel": (190_900, 0.0012, 0.04), "Umbriel": (266_000, 0.0039, 0.13),
    "Titania": (435_910, 0.0011, 0.08), "Oberon": (583_520, 0.0014, 0.07),
    "Triton": (354_759, 0.00002, 156.9), "Proteus": (117_647, 0.0005, 0.08), "Nereid": (5_513_818, 0.7507, 7.09),
    "Charon": (19_591, 0.0002, 0.0),
}


def _sol_orbit(name: str) -> Optional[dict[str, float]]:
    """The real orbit of Sol's planet `name` as galaxy.json holds one, its
    anomaly carried from J2000 to the epoch; None for one not listed."""
    found = _SOL_J2000.get(name)
    if found is None:
        return None
    a, e, i, node, perihelion, longitude = found
    years = epoch_year() - 2000
    anomaly = (longitude - perihelion + 360 * years / period_years(a, 1.0)) % 360
    return {"au": _au(a), "e": e, "i": i, "node": node,
            "periapsis": round((perihelion - node) % 360, 3), "anomaly": round(anomaly, 1)}


# The way Sol's poles lean, in degrees of ecliptic longitude: from the IAU
# north poles (right ascension, declination), turned round for Venus and
# Uranus, which spin the other way — the pole here is the one they turn
# about counterclockwise.
_SOL_BEARINGS = {"Mercury": 318.2, "Venus": 210.2, "Earth": 90.0, "Mars": 352.9, "Jupiter": 247.8,
                 "Saturn": 79.5, "Uranus": 77.6, "Neptune": 319.2, "Pluto": 137.4}

# Sol's axial tilts, as they are.
_SOL_TILTS = {"Mercury": 0.03, "Venus": 177.4, "Earth": 23.44, "Mars": 25.19, "Jupiter": 3.13, "Saturn": 26.73,
              "Uranus": 97.77, "Neptune": 28.32, "Pluto": 119.6}

# Sol's rings (planet radii, bands innermost first) and belts (AU), as they
# are. Saturn's D–B rings, the Cassini Division (1.95–2.03), and the A ring.
_SOL_RINGS = {"Jupiter": [(1.4, 1.8)], "Saturn": [(1.11, 1.95), (2.03, 2.27)], "Uranus": [(1.64, 2.0)],
              "Neptune": [(1.69, 2.54)]}
_SOL_BELTS = (("Main belt", 2.2, 3.2), ("Kuiper belt", 30.0, 50.0))


def _sol_extras(system: dict[str, Any]) -> int:
    """Give Sol's planets their real tilts, the way they lean and rings, and
    Sol its belts, where none are recorded. How many were set."""
    count = 0
    for planet in system.get("planets") or []:
        if planet.get("name") in _SOL_TILTS and "tilt" not in planet:
            bodies.set_field(planet, "tilt", _SOL_TILTS[planet["name"]])
            count += 1
        if planet.get("name") in _SOL_BEARINGS and "tilt_bearing" not in planet:
            bodies.set_field(planet, "tilt_bearing", _SOL_BEARINGS[planet["name"]])
            count += 1
        known = _SOL_RINGS.get(planet.get("name"))
        if known and "rings" not in planet:
            bodies.set_field(planet, "rings", [{"inner": a, "outer": b} for a, b in known])
            count += 1
    if not system.get("belts"):
        system["belts"] = [{"name": n, "id": f"b{k + 1}", "inner": i, "outer": o}
                           for k, (n, i, o) in enumerate(_SOL_BELTS)]
        count += len(_SOL_BELTS)
    return count


def _sol(system: dict[str, Any], rng: random.Random) -> int:
    """Set Sol as it is, wherever something is missing: its planets' and
    moons' orbits, tilts and the way they lean, rings and belts. Every draw
    of Sol starts here, so that none of it is drawn at random. How many."""
    count = _sol_extras(system)
    for planet in system.get("planets") or []:
        known = _sol_orbit(planet.get("name"))
        if known and not planet.get("orbit"):
            bodies.set_field(planet, "orbit", known)
            count += 1
        for moon in planet.get("moons") or []:
            real = _SOL_MOONS.get(moon.get("name"))
            if real and not moon.get("orbit"):
                bodies.set_field(moon, "orbit", {"km": real[0], "e": real[1], "i": real[2], **_angles(rng)})
                count += 1
    return count


def fill(doc: dict[str, Any], seed=None) -> int:
    """Give every planet and moon without an orbit one, system by system,
    seeded per system — Sol's real ones where known. How many were filled."""
    count = 0
    for system in doc.get("star_systems") or []:
        rng = bodies.seeded(system.get("name") or "", "orbits") if seed is None else random.Random(seed)
        count += draw_system(system, rng)
    return count


# ── what does not fit ─────────────────────────────────────────────────────────

# ── belts among the planets ───────────────────────────────
# A belt lies in a gap between planets: offered the gaps when it is added, and
# told when its edges reach across a planet's orbit. Dwarf planets live in
# belts (Ceres, Pluto), so only planets count; and only those around the same
# star or group as the belt.

def _around(system: dict[str, Any], item: dict[str, Any]) -> frozenset[str]:
    """The stars `item` orbits, by name: its host, else the primary."""
    return host_names(system, item.get("host"))


def _swept(system: dict[str, Any], host: dict[str, Any]) -> list[tuple[float, float, dict[str, Any]]]:
    """(perihelion, aphelion, planet) of every planet with an orbit around what
    `host` orbits, innermost first; dwarf planets left out."""
    around = _around(system, host)
    out = []
    for planet in system.get("planets") or []:
        orbit = planet.get("orbit") or {}
        if planet.get("dwarf") or not orbit.get("au") or _around(system, planet) != around:
            continue
        e = orbit.get("e") or 0
        out.append((orbit["au"] * (1 - e), orbit["au"] * (1 + e), planet))
    return sorted(out, key=lambda t: t[0])


def _middle(low: float, high: float) -> tuple[float, float]:
    """The middle half of the gap from `low` to `high`, on a log scale (as
    Mars–Jupiter is a gap): clear of both edges."""
    ratio = high / low
    return _au(low * ratio ** 0.25), _au(low * ratio ** 0.75)


def belt_gaps(system: dict[str, Any], host: Optional[str] = None) -> list[dict[str, Any]]:
    """Where a new belt around `host` (the primary when None) may go: inside
    the innermost planet, between each two neighbours whose orbits leave room,
    and beyond the outermost planet or belt — each {label, inner, outer}, its
    edges clear of the planets' orbits."""
    item = {"host": host} if host else {}
    swept = _swept(system, item)
    gaps = []
    if swept:
        first = swept[0]
        gaps.append({"label": f"inside {_label(first[2])}", **dict(zip(("inner", "outer"), _middle(first[0] / 4, first[0])))})
    for (_, apo, a), (peri, _, b) in zip(swept, swept[1:]):
        if peri > apo * 1.1:
            gaps.append({"label": f"between {_label(a)} and {_label(b)}", **dict(zip(("inner", "outer"), _middle(apo, peri)))})
    around = _around(system, item)
    belts = [b.get("outer", 0) for b in system.get("belts") or [] if _around(system, b) == around]
    outer = max([apo for _, apo, _ in swept] + belts + [1.0])
    gaps.append({"label": f"beyond {_label(swept[-1][2]) if swept else 'the star'}",
                 "inner": _au(outer * 1.3), "outer": _au(outer * 1.8)})
    return gaps


# How often a drawn system gets a belt between its planets (Mars–Jupiter),
# and one beyond them (the Kuiper belt) — the generators'.
BELT_SHARE = 0.4
OUTER_BELT_SHARE = 0.3


def draw_belts(system: dict[str, Any], rng: Optional[random.Random] = None) -> int:
    """Add now and then a belt in a gap between the planets around the
    primary, and now and then one beyond them — each where belt_gaps puts
    one, clear of every orbit, unnamed ("?"). How many were added."""
    rng = rng or random.Random()
    from galaxy import schema
    belts = system.setdefault("belts", [])
    added = 0
    between = [g for g in belt_gaps(system) if g["label"].startswith("between")]
    if between and rng.random() < BELT_SHARE:
        place = rng.choice(between)
        belts.append({"name": "?", "id": schema.next_id(belts, "b"), "inner": place["inner"], "outer": place["outer"]})
        added += 1
    if (system.get("planets") or []) and rng.random() < OUTER_BELT_SHARE:
        place = belt_gaps(system)[-1]
        belts.append({"name": "?", "id": schema.next_id(belts, "b"), "inner": place["inner"], "outer": place["outer"]})
        added += 1
    if not belts:
        system.pop("belts")
    return added


def belt_crossings(system: dict[str, Any], belt: dict[str, Any]) -> list[str]:
    """The planets whose orbits `belt` reaches across, as "Jupiter (4.94–5.46 AU)"."""
    return [f"{_label(planet)} ({peri:.3g}–{apo:.3g} AU)" for peri, apo, planet in _swept(system, belt)
            if apo > belt["inner"] and peri < belt["outer"]]


def label(body: dict[str, Any], kind: str = "Planet") -> str:
    """A body as the findings name it: its name, or "Planet 3" by its place."""
    return _label(body, kind)


def _label(body: dict[str, Any], kind: str = "Planet") -> str:
    return body.get("name") if body.get("name") not in (None, "?") else f"{kind} {body.get('index')}"


def findings(system: dict[str, Any]) -> list[tuple[str, str, bool]]:
    """(kind, message, note) for the system's orbits: a host its stars do
    not make, a companion that cannot be placed, an orbit its host would
    not keep, out of order, a planet outside its class's zone, a moon
    beyond its planet's hold, neighbours too close to keep their orbits."""
    out, t = [], tree(system)
    hosts = ", ".join(host_list(system)) or "its stars"
    for name in t.unplaced:
        out.append(("star-host", f"{name} orbits a host the system's stars do not make — one of {hosts}", False))
    orbits_of = star_orbits(t)
    for companion in (system.get("stars") or [])[1:]:
        name = (companion.get("name") or "").strip() or "A companion star"
        if star(companion.get("spectral_class")) is None:
            out.append(("star-orbit", f"{name} has no spectral class: its mass, and so its orbit and the "
                                      "stars' shared centre of gravity, cannot be worked out", True))
            continue
        if name not in orbits_of:
            continue
        orbit = companion.get("orbit") or {}
        found = companion_range(system, t, name, orbit.get("e", 0.0))
        if found is None:
            continue
        low, high = found
        host = orbits_of[name][1].key
        if not orbit.get("au"):
            if low >= high * 0.9:
                out.append(("star-binary", f"No orbit of {name} around {host} keeps both what orbits them "
                                            f"each (from {low:.2f} AU) and what orbits the two (to "
                                            f"{high:.2f} AU)", False))
            continue
        sides = orbits_of[name][1:]
        if all(n.mass is not None for n in sides):
            touch = 2 * 0.00465 * sum(n.mass ** 0.8 for n in sides)
            if orbit["au"] * (1 - orbit.get("e", 0.0)) < touch:
                out.append(("star-binary", f"{name} comes within {orbit['au'] * (1 - orbit.get('e', 0.0)):.4f} AU "
                                           f"of {host}: closer than twice their radii ({touch:.4f} AU), they "
                                           "would pull each other apart", False))
            elif orbit["au"] < 0.1 and orbit.get("e", 0.0) > 0.1:
                out.append(("star-binary", f"{name} and {host}, {orbit['au']} AU apart, would have been made "
                                           f"round by their tides long ago — an eccentricity of {orbit['e']} "
                                           "is unlikely (below 0.05)", True))
        if orbit["au"] < low:
            out.append(("star-binary", f"{name} at {orbit['au']} AU from {host} comes too near what orbits "
                                        f"them: from {low:.2f} AU it would not throw it off", False))
        elif orbit["au"] > high:
            out.append(("star-binary", f"{name} at {orbit['au']} AU from {host} is too wide for what orbits "
                                        f"the two of them: within {high:.2f} AU it would stay", False))

    by_host: dict[frozenset, list[dict[str, Any]]] = {}
    for planet in system.get("planets") or []:
        by_host.setdefault(host_names(system, planet.get("host")), []).append(planet)
    for names, planets in by_host.items():
        node = t.node(names)
        if node is None:
            for planet in planets:
                out.append(("orbit-host", f"{_label(planet)} orbits {planet.get('host')}, which the system's "
                                         f"stars do not make — one of {hosts}", False))
            continue
        host = host_star(node)
        near, far = inner_limit(node), outer_limit(node)
        if host is not None:
            around = (f"around {'an' if host.spectral_class[:1] in 'AFMO' else 'a'} {host.spectral_class} star"
                      if node.core is None else f"around {node.key}")
            for inner, outer in _clashes(planets, host):
                out.append(("orbit-classes",
                            f"{_label(inner)}, {bodies_label(inner.get('class'))}, belongs "
                            f"{_where(*zone(inner.get('class'), host))} {around}, but orbits inside "
                            f"{_label(outer)}, {bodies_label(outer.get('class'))}, which belongs "
                            f"{_where(*zone(outer.get('class'), host))}: no orbits fit both — swap their "
                            "places, or change one of the classes", False))
        previous = None
        for planet in planets:
            name, orbit = _label(planet), planet.get("orbit") or {}
            a = orbit.get("au")
            if a is None:
                continue
            e = orbit.get("e", 0.0)
            if previous is not None and a <= previous[1]:
                out.append(("orbit-order", f"{name} ({a} AU) orbits inside {previous[0]} ({previous[1]} AU), "
                                           "which comes before it", False))
            previous = (name, a)
            if near and a * (1 - e) < near:
                out.append(("orbit-binary", f"{name} at {a} AU circles too close to {node.key}: outside "
                                            f"{near:.2f} AU it would stay on its orbit", False))
            if near and host is not None and zone(planet.get("class"), host)[1] < near:
                low, high = zone(planet.get("class"), host)
                out.append(("orbit-binary", f"{name}, {bodies_label(planet.get('class'))}, belongs at "
                                            f"{low:.2f}–{high:.2f} AU around {node.key}, but its stars are too far "
                                            f"apart for anything to stay inside {near:.2f} AU — they would have to "
                                            "be much closer (their orbit, or Redraw all orbits)", False))
                continue
            if far and a * (1 + e) > far[0]:
                out.append(("orbit-binary", f"{name} at {a} AU from {node.key} reaches too near {far[1]}: "
                                            f"within {far[0]:.2f} AU it would stay on its orbit", False))
            if host is None:
                continue
            low, high = zone(planet.get("class"), host)
            if not low <= a <= high:
                what = bodies_label(planet.get("class"))
                where = (f"at {low:.2f}–{high:.2f} AU" if high != math.inf else f"beyond {low:.2f} AU")
                around = (f"around {'an' if host.spectral_class[:1] in 'AFMO' else 'a'} {host.spectral_class} star"
                          if node.core is None else f"around {node.key}")
                out.append(("orbit-zone", f"{name}, {what}, at {a} AU: its class belongs {where} {around}",
                            planet.get("class") != "terrestrial-habitable"))
            m = mass(planet)
            if m is None:
                continue
            hill = hill_radius_km(a, e, m, host.mass)
            for moon in planet.get("moons") or []:
                km = (moon.get("orbit") or {}).get("km")
                if km and km > 0.5 * hill:
                    out.append(("moon-orbit", f"{moon.get('name') or 'A moon'} of {name} at {km:,} km: beyond half "
                                              f"its planet's hold ({hill / 2:,.0f} km), it would be lost", False))
        out.extend(_spacing_findings(planets, node))
    return out


# Two planets closer than this many mutual Hill radii, at the inner one's
# farthest and the outer one's nearest, pull each other off their orbits
# (Gladman 1993). The many-planet rules (8–10) are not used: Sol's
# Jupiter and Saturn lie 8.0 apart and keep their orbits.
HILL_SPACING = 2 * math.sqrt(3)
# Below this mass (kg) a body is a dwarf planet, Pluto's kind: their orbits
# cross each other's and Neptune's, as in the Kuiper belt — no finding; a
# resonance that holds one apart is still noted. Between Pluto (6e21 here)
# and Mercury (1.75e23).
MINOR_MASS = 1e23
# Period ratios that hold two orbits apart even where they cross, as 3:2
# holds Pluto from Neptune; within this share of the ratio.
RESONANCES = ((2, 1), (3, 2), (4, 3), (5, 3), (5, 2), (3, 1))
RESONANCE_SHARE = 0.01


def _spacing_findings(planets: list[dict[str, Any]], node: Node) -> list[tuple[str, str, bool]]:
    """Neighbouring planets of one host that would not keep their orbits:
    too few mutual Hill radii apart (with both masses), or crossing (with or
    without). A resonance that holds them apart makes it a note."""
    out = []
    placed = sorted((p for p in planets if (p.get("orbit") or {}).get("au")), key=lambda p: p["orbit"]["au"])
    for inner, outer in zip(placed, placed[1:]):
        a1, e1 = inner["orbit"]["au"], inner["orbit"].get("e", 0.0)
        a2, e2 = outer["orbit"]["au"], outer["orbit"].get("e", 0.0)
        gap = a2 * (1 - e2) - a1 * (1 + e1)
        m1, m2 = mass(inner), mass(outer)
        pair = f"{_label(inner)} and {_label(outer)}"
        if gap <= 0:
            what = f"{pair}: their orbits cross"
        elif m1 is not None and m2 is not None and node.mass:
            hills = gap / (((m1 + m2) / (3 * node.mass * SUN_MASS)) ** (1 / 3) * (a1 + a2) / 2)
            if hills >= HILL_SPACING:
                continue
            what = (f"{pair}: {hills:.1f} mutual Hill radii apart where they come nearest, under "
                    f"{HILL_SPACING:.1f}")
        else:
            continue
        ratio = (a2 / a1) ** 1.5
        held = next(((p, q) for p, q in RESONANCES if abs(ratio / (p / q) - 1) < RESONANCE_SHARE), None)
        dwarf = next((b for b, m in ((inner, m1), (outer, m2))
                      if b.get("dwarf") or (m is not None and m < MINOR_MASS)), None)
        if held:
            out.append(("orbit-spacing", f"{what}, held apart by a {held[0]}:{held[1]} resonance", True))
        elif dwarf is not None:
            continue            # a dwarf planet's orbit crossing another's is the Kuiper belt's way
        else:
            out.append(("orbit-spacing", f"{what} — they would pull each other off their orbits", False))
    return out


def bodies_label(body_class: Optional[str]) -> str:
    """A body class's label in lower case, as a finding writes it: "no class" for none."""
    from galaxy.schema import PLANET_CLASS_LABELS
    return PLANET_CLASS_LABELS.get(body_class or "", "no class").lower()
