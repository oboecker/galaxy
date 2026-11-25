"""The size of planets and moons, and what follows from it.

`radius` (km) is a body's own field in galaxy.json, drawn at random by class
once the body has one, and edited by hand after. Without a class — or with
"unknown" — there is nothing to infer a size from, so none is drawn: such a body has a radius only if one is typed. Gravity, circumference,
surface area and km per degree are derived from it, never stored.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from typing import Any, Optional

EARTH_RADIUS = 6_371            # km
RADIUS_LIMITS = (1, 200_000)    # what the schema accepts, any class: Deimos is 6 km
# A ring's density: the share of the densest ring's rocks (Saturn's B ring,
# 1); absent is 1. Jupiter's is a few hundredths.
RING_DENSITY_LIMITS = (0.01, 1.0)


@dataclass(frozen=True)
class Range:
    """The radii a class is drawn from, in km: the median and the bounds."""
    median: int
    low: int
    high: int

    def holds(self, radius: int) -> bool:
        """Whether `radius` lies within the range, bounds included."""
        return self.low <= radius <= self.high


# By class; a moon with a class from MOON; a body with none, or "unknown",
# draws nothing. Plausible around an Earth-like scale.
RANGES: dict[str, Range] = {
    "terrestrial-habitable": Range(6_200, 3_500, 10_000),
    "terrestrial-desert": Range(5_500, 3_000, 9_500),
    "terrestrial-barren": Range(4_000, 1_500, 9_000),
    "volcanic": Range(5_000, 1_800, 9_000),
    "ice-world": Range(4_500, 1_500, 9_000),
    "gas-giant-cold": Range(25_000, 15_000, 60_000),
    "gas-giant-warm": Range(60_000, 30_000, 100_000),
}
MOON = Range(1_200, 100, 3_000)
SPREAD = 0.25                   # σ of the log-normal draw: most land within ±25 % of the median

# Known bodies get their real radius when the fill reaches them: Sol's.
KNOWN = {("Sol", name): radius for name, radius in (
    ("Mercury", 2_440), ("Venus", 6_052), ("Earth", EARTH_RADIUS), ("Luna", 1_737), ("Mars", 3_390),
    ("Phobos", 110), ("Deimos", 100), ("Jupiter", 69_911), ("Io", 1_822), ("Europa", 1_561),
    ("Ganymede", 2_634), ("Callisto", 2_410), ("Saturn", 58_232), ("Titan", 2_575),
    ("Uranus", 25_362), ("Neptune", 24_622), ("Triton", 1_353), ("Pluto", 1_188), ("Charon", 606))}

# Typical surface gravity of a gas giant, in g, at the cloud tops: its mass
# does not follow from its radius (Saturn is smaller than Jupiter and has
# less than half its gravity).
GAS_GIANT_GRAVITY = {"gas-giant-cold": 1.1, "gas-giant-warm": 2.0}
ICE_DENSITY = 0.6               # relative to rock, for an ice world


def range_of(body_class: Optional[str], moon: bool = False) -> Optional[Range]:
    """The range a radius of the class is drawn from; None for no class or
    "unknown", which say nothing about size."""
    if body_class not in RANGES:
        return None
    return MOON if moon else RANGES[body_class]


def draw(body_class: Optional[str], moon: bool = False, rng: Optional[random.Random] = None) -> Optional[int]:
    """A plausible radius for the class: log-normal around its median,
    within its range, rounded to 10 km. None without a class to go by."""
    r = range_of(body_class, moon)
    if r is None:
        return None
    value = r.median * math.exp((rng or random).gauss(0.0, SPREAD))
    return int(round(min(r.high, max(r.low, value)) / 10) * 10)


def seeded(system: str, body_id: str, *parents: str) -> random.Random:
    """The random source of the fill, reproducible per body."""
    key = "/".join((system, *parents, body_id))
    return random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big"))


def gravity(radius: int, body_class: Optional[str]) -> float:
    """Surface gravity in g. Rocky bodies grow denser as they grow, so
    gravity rises faster than the radius: (R/R⊕)^1.7 — Mars comes out at
    0.34 g (really 0.38). Ice is lighter; a gas giant has a typical value."""
    if body_class in GAS_GIANT_GRAVITY:
        return GAS_GIANT_GRAVITY[body_class]
    g = (radius / EARTH_RADIUS) ** 1.7
    return g * ICE_DENSITY if body_class == "ice-world" else g


def facts(body: dict[str, Any]) -> Optional[dict[str, Any]]:
    """What follows from the body's radius; None without one."""
    radius = body.get("radius")
    if not isinstance(radius, int):
        return None
    cls = body.get("class")
    return {
        "radius": radius,
        "gravity": round(gravity(radius, cls), 2),
        "gravity_at_cloud_tops": cls in GAS_GIANT_GRAVITY,
        "circumference": round(2 * math.pi * radius),
        "surface_area": round(4 * math.pi * radius ** 2),
        "km_per_degree": round(2 * math.pi * radius / 360, 1),
    }


def great_circle(radius: float, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """The distance in km between two points (degrees) on a sphere of
    `radius` km — haversine."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def set_radius(body: dict[str, Any], radius: int) -> None:
    """Set the body's `radius` (km) in its place among its fields: after
    `class`, else after `index` — a diff shows a new line, not a reordered
    record."""
    set_field(body, "radius", radius)


# Where a field goes in a body's record, after the last of these present.
_AFTER = {"dwarf": ("name", "index"), "radius": ("index", "class"), "look": ("index", "class", "radius"),
          "host": ("name", "spectral_class", "index", "class", "radius", "look"),
          "orbit": ("name", "spectral_class", "index", "class", "radius", "look", "host"),
          "tilt": ("index", "class", "radius", "look", "orbit"),
          "tilt_bearing": ("index", "class", "radius", "look", "orbit", "tilt"),
          "rings": ("index", "class", "radius", "look", "orbit", "tilt", "tilt_bearing")}


def draw_ring_density(rng: Optional[random.Random] = None) -> float:
    """A ring's density at random, evenly in its logarithm: most rings are
    faint, as Jupiter's, Uranus's and Neptune's; few as dense as Saturn's."""
    low, high = RING_DENSITY_LIMITS
    return round(low * (high / low) ** (rng or random).random(), 2)


def ring_bands(body: dict[str, Any]) -> list[dict[str, Any]]:
    """A planet's rings as bands, innermost first, each `inner` and `outer`
    in planet radii — a gap between two is a division, as Saturn's Cassini
    Division. One band as a bare object, an older form,
    reads as one band, and the next Commit writes it as a list
    (schema.normalise)."""
    rings = body.get("rings")
    if not rings:
        return []
    return [rings] if isinstance(rings, dict) else list(rings)


def set_field(body: dict[str, Any], key: str, value: Any) -> None:
    """Set `key` to `value`; a new field goes in its place among the body's
    own (`_AFTER`), so a diff shows a new line, not a reordered record."""
    if key in body:
        body[key] = value
        return
    items = list(body.items())
    at = max((k + 1 for k, (name, _) in enumerate(items) if name in _AFTER.get(key, ())), default=len(items))
    items.insert(at, (key, value))
    body.clear()
    body.update(items)


def missing(doc: dict[str, Any]) -> tuple[int, int]:
    """How many planets and moons have no radius: those `fill` would give
    one, and those it cannot — no class to go by."""
    drawable = undrawable = 0
    for system in doc.get("star_systems") or []:
        for planet in system.get("planets") or []:
            for body in [planet, *(planet.get("moons") or [])]:
                if isinstance(body.get("radius"), int):
                    continue
                if (system.get("name"), body.get("name")) in KNOWN or body.get("class") in RANGES:
                    drawable += 1
                else:
                    undrawable += 1
    return drawable, undrawable


def fill(doc: dict[str, Any]) -> int:
    """Give every planet and moon without a radius one, drawn by class and
    seeded per body (KNOWN ones their real one); one without a class keeps
    none. How many were filled."""
    count = 0
    for system in doc.get("star_systems") or []:
        name = system.get("name") or ""
        for planet in system.get("planets") or []:
            bodies = [(planet, False, (str(planet.get("id")),))] + [
                (moon, True, (str(moon.get("id")), str(planet.get("id")))) for moon in planet.get("moons") or []]
            for body, moon, key in bodies:
                if isinstance(body.get("radius"), int):
                    continue
                radius = KNOWN.get((name, body.get("name"))) or draw(
                    body.get("class"), moon=moon, rng=seeded(name, *key))
                if radius is not None:
                    set_radius(body, radius)
                    count += 1
    return count
