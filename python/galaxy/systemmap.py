"""What the star-system map draws, worked out here so that the browser only
moves bodies along their orbits.

`export(doc)` gives each system its star (mass, luminosity, temperature,
radius, the zones), each planet and moon its elements, period, radius,
gravity and Hill radius, and the belts and points of interest as they are.
An editor serves it from the draft; the build writes it as
public/galaxy/systems.json (cli/system_maps.py).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Optional

from galaxy import bodies, brightstars, calendar, celestial, constellations, hierarchy, nebulae, orbits
from galaxy.stars import primary
from galaxy.stars import star as star_of

SUN_RADIUS_KM = 696_000


def _star_radius(star) -> int:
    """A star's radius in km (galaxy.stars.Star.radius): to 100 km, a
    remnant's to the km — rounded to 100 km, a black hole's 24 km horizon
    was 0, and the map's camera, flown to it, could no longer zoom."""
    km = SUN_RADIUS_KM * star.radius
    return int(round(km, -2)) if km >= 1_000 else max(1, int(round(km)))


def _body(body: dict[str, Any]) -> dict[str, Any]:
    """A planet or moon with the fields the map draws, its rings as bands and
    its gravity (g) where it has a radius."""
    out = {k: body[k] for k in ("id", "name", "dwarf", "class", "look", "radius", "tilt", "tilt_bearing", "orbit") if k in body}
    if body.get("rings"):
        out["rings"] = bodies.ring_bands(body)          # always bands, the old single object too
    facts = bodies.facts(body)
    if facts:
        out["gravity"] = facts["gravity"]
    return out


def sky(doc_system: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Where the system stands in Earth's sky (galaxy.celestial): RA and Dec
    in degrees, light years from Sol, the constellation and the line that
    says it. None for Sol."""
    try:
        at = celestial.to_sky(doc_system.get("x", 0), doc_system.get("y", 0), doc_system.get("z", 0))
    except ValueError:
        return None
    return {"ra": round(at.ra, 4), "dec": round(at.dec, 4), "ly": round(at.ly, 1),
            "constellation": at.constellation, "constellation_name": at.constellation_name,
            "text": at.describe()}


def absolute_magnitude(doc_system: dict[str, Any]) -> Optional[float]:
    """How bright the system's primary is, as the absolute visual magnitude:
    a real star's from the catalogue (its magnitude from Earth and its
    distance), another's from its class's light and temperature with a
    bolometric correction (Reed 1998). None without a class."""
    for star in doc_system.get("stars") or []:
        known = brightstars.by_hip().get(star.get("hip"))
        if known:
            return round(known["mag"] - 5 * math.log10(known["ly"] / 32.6156), 2)
    star = primary(doc_system)
    if star is None or star.luminosity <= 0 or not 0 < star.temperature <= 60_000:
        # A black hole shows nothing of its own; a neutron star's light is
        # X-rays, where the correction below (fitted 3,000-50,000 K) says nothing.
        return None
    t = math.log10(star.temperature) - 4
    correction = -8.499 * t ** 4 + 13.421 * t ** 3 - 8.131 * t ** 2 - 3.901 * t - 0.438
    return round(4.74 - 2.5 * math.log10(star.luminosity) - correction, 2)


def place(doc_system: dict[str, Any]) -> dict[str, Any]:
    """Where the system is and how its own axes lie, for the sky of every
    other: `at` in the frame (light years), `axes` the turn from its axes
    into the frame's (galaxy.celestial.plane_matrix; none for no plane),
    `abs_mag` its brightness."""
    plane = doc_system.get("plane")
    return {"at": [doc_system.get("x", 0), doc_system.get("y", 0), doc_system.get("z", 0)],
            "axes": [[round(float(v), 6) for v in row] for row in celestial.plane_matrix(plane)] if plane else None,
            "abs_mag": absolute_magnitude(doc_system)}


def sky_stars(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Every system as a star of the others' skies: name, class, place."""
    out = []
    for s in doc.get("star_systems") or []:
        here = place(s)
        if here["abs_mag"] is not None:
            out.append({"name": s.get("name"), "spectral_class": s.get("spectral_class"),
                        "at": here["at"], "abs_mag": here["abs_mag"]})
    return out


def sky_nebulae(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Every nebula as the system maps' skies draw it (space/sky.js): name,
    kind, colour (its own or its kind's), centre in the frame and size — the
    sky works out its direction and angular size from each system, or that
    the system lies inside it."""
    return [{"name": n["name"], "kind": n["kind"], "colour": nebulae.colour(n),
             "at": [n["x"], n["y"], n["z"]], "size": n["size"]} for n in doc.get("nebulae") or []]


def write_nebulae(doc: dict[str, Any], path: Path) -> None:
    """Write the skies' nebulae (`sky_nebulae`) to `path`, beside systems.json."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sky_nebulae(doc), separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")


def _calendar() -> dict[str, Any]:
    """The calendar's eras and how dates are written (space/calendar.js reads
    them): each map reads and writes its dates by it."""
    definition = calendar.current().as_dict()
    return {"eras": definition["eras"], "written": definition["written"]}


def system(doc_system: dict[str, Any]) -> dict[str, Any]:
    """One system, as the map draws it."""
    star = primary(doc_system)
    out: dict[str, Any] = {"name": doc_system.get("name"), "object_type": doc_system.get("object_type"),
                           "epoch": orbits.epoch(),
                           "epoch_year": orbits.epoch_year(), "calendar": _calendar(), "star": None, "planets": [],
                           "belts": doc_system.get("belts") or [],
                           "points_of_interest": doc_system.get("points_of_interest") or [],
                           "galaxy": celestial.galaxy_from(doc_system), "sky": sky(doc_system),
                           **place(doc_system)}
    if star is not None:
        inner, outer = star.habitable_zone
        out["star"] = {"spectral_class": star.spectral_class, "object_type": star.object_type, "mass": star.mass,
                       "luminosity": star.luminosity, "temperature": star.temperature,
                       "radius": _star_radius(star), "habitable_zone": [inner, outer],
                       "frost_line": star.frost_line}
    # The stars as a tree (galaxy.hierarchy): each companion with its orbit
    # around its host and its period; one that cannot be placed — no class,
    # so no mass, or no orbit — is left out with whatever orbits it.
    t = hierarchy.tree(doc_system, physical=True)
    out["primary_name"] = hierarchy.primary_name(doc_system)
    out["stars"] = []
    for record in doc_system.get("stars") or []:
        data = star_of(record.get("spectral_class"))
        name = (record.get("name") or "").strip()
        row = {"name": name or "?", "spectral_class": record.get("spectral_class"),
               "placed": name in t.root.names or record is (doc_system.get("stars") or [None])[0]}
        if data is not None:
            row.update(mass=data.mass, radius=_star_radius(data), temperature=data.temperature)
        out["stars"].append(row)
    out["tree"] = _node(t.root)

    def resolve(body: dict[str, Any]) -> Optional[str]:
        node = t.node(hierarchy.host_names(doc_system, body.get("host")))
        return node.key if node is not None else None

    # The zones of each host something orbits — a star's travel with it, a
    # group's lie around its centre, from its stars' light together; with
    # nothing orbiting, the whole system's.
    used = {resolve(p) for p in doc_system.get("planets") or [] if (p.get("orbit") or {}).get("au")}
    used.discard(None)
    out["hosts"] = {}
    for node in t.by_names.values():
        lit = hierarchy.host_star(node)
        if lit is None:
            continue
        inner, outer = lit.habitable_zone
        out["hosts"][node.key] = {"mass": node.mass, "habitable_zone": [inner, outer], "frost_line": lit.frost_line,
                                  "zones": node.key in used or (not used and node is t.root)}
    out["belts"] = [{**b, "host": resolve(b)} for b in out["belts"]]
    out["points_of_interest"] = [
        {**p, "anchor": {**p["anchor"], "host": resolve(p["anchor"])}} if (p.get("anchor") or {}).get("body") == "star"
        else p for p in out["points_of_interest"]]
    for planet in doc_system.get("planets") or []:
        row = _body(planet)
        row["host"] = resolve(planet)
        orbit, mass = planet.get("orbit") or {}, orbits.mass(planet)
        central = t.node(hierarchy.host_names(doc_system, planet.get("host")))
        central = central.mass if central is not None else None
        if central is not None and orbit.get("au"):
            row["period"] = orbits.period_years(orbit["au"], central)        # years
            if mass is not None:
                row["hill"] = orbits.hill_radius_km(orbit["au"], orbit.get("e", 0.0), mass, central)
                row["mass_ratio"] = mass / (central * orbits.SUN_MASS)
        row["moons"] = []
        for moon in planet.get("moons") or []:
            m = _body(moon)
            km = (moon.get("orbit") or {}).get("km")
            if mass is not None and km:
                m["period"] = orbits.moon_period_days(km, mass) / 365.25          # years, as a planet's
            moon_mass = orbits.mass(moon)
            if mass is not None and moon_mass is not None and km:
                m["hill"] = km * (1 - moon["orbit"].get("e", 0.0)) * (moon_mass / (3 * mass)) ** (1 / 3)
            row["moons"].append(m)
        out["planets"].append(row)
    out["points_of_interest"] = [_above(p, doc_system) for p in out["points_of_interest"]]
    return out


def _above(poi: dict[str, Any], doc_system: dict[str, Any]) -> dict[str, Any]:
    """A point `km` above a planet or moon, on a circular orbit in its equator:
    the orbit's radius (the body's radius and the altitude) and its period, as
    a moon's. Without the body's mass or radius, no period: it stays put."""
    at = poi.get("anchor") or {}
    if at.get("body") in (None, "star") or not at.get("km"):
        return poi
    planet_id, _, moon_id = str(at["body"]).partition("/")
    planet = next((p for p in doc_system.get("planets") or [] if str(p.get("id")) == planet_id), None)
    body = (next((m for m in planet.get("moons") or [] if str(m.get("id")) == moon_id), None)
            if planet and moon_id else planet)
    facts, mass = (bodies.facts(body), orbits.mass(body)) if body else (None, None)
    if facts is None or mass is None:
        return poi
    km = facts["radius"] + at["km"]
    return {**poi, "orbit": {"km": km, "e": 0.0}, "period": orbits.moon_period_days(km, mass) / 365.25}


def _node(node: hierarchy.Node) -> dict[str, Any]:
    """The tree as the map walks it: a star by name, or a group's core and
    its satellites, each with its orbit and period around the core."""
    if node.core is None:
        return {"key": node.key, "star": node.name, "mass": node.mass}
    return {"key": node.key, "mass": node.mass, "core": _node(node.core),
            "satellites": [{"orbit": orbit, "node": _node(sub),
                            "period": orbits.period_years(orbit["au"], node.core.mass + sub.mass)}
                           for orbit, sub in node.satellites]}


def export(doc: dict[str, Any]) -> dict[str, Any]:
    """Every system, by name; with the constellation figures of its sky
    where the sidecar has them (galaxy.constellations)."""
    table = constellations.load()
    out = {}
    for s in doc.get("star_systems") or []:
        row = out[s.get("name")] = system(s)
        figures = constellations.figures(doc, s.get("name"), table)
        if figures:
            row["constellations"] = figures
    return out


def write(doc: dict[str, Any], path: Path) -> None:
    """Write every system as the map draws it (`export`) to `path`, as compact JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(export(doc), separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
