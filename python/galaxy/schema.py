"""Validation and derived-field maintenance for galaxy.json.

Deliberately hand-written rather than pulled in via a schema library: the rules
that matter here are not "is this a string" but the two invariants that keep the
file's consumers working — `galaxy-map.js`, a site's own readers and the SVG
renderer.

The schema grows additively.  `stars` and `moons` are optional and absent until
they carry information, so systems nobody has touched stay byte-identical and a
diff shows only what was actually edited.
"""

from __future__ import annotations

import re
from typing import Any

from galaxy.slugs import slugify
from galaxy import nebulae, objects
from galaxy.bodies import RADIUS_LIMITS, RING_DENSITY_LIMITS
from galaxy.jsonstore import ValidationError

# The galaxy is 100,000 ly across and about 10,000 ly thick:
# a coordinate outside is a slip of the keyboard, and one x = 999999999 was
# committed and published without a word.
COORDINATE_LIMITS = {"x": 50_000, "y": 50_000, "z": 5_000}


def coordinate_error(axis: str, value: float) -> str | None:
    """Why a coordinate is refused, or None."""
    limit = COORDINATE_LIMITS[axis]
    if not -limit <= value <= limit:
        return f"{axis} must be between −{limit:,} and {limit:,} ly"
    return None


def radius_error(value: Any) -> str | None:
    """Why a planet's or moon's radius (km) is refused, or None."""
    low, high = RADIUS_LIMITS
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        return f"radius must be a whole number of km between {low:,} and {high:,}"
    return None


# A planet's or moon's look: its palette among its class's and its texture's
# seed (viewer/planet/planet-texture.js, PALETTES).
LOOK_LIMIT = 1_000_000


def look_error(value: Any) -> str | None:
    """Why a look is refused, or None: a whole number from 0 below LOOK_LIMIT."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < LOOK_LIMIT:
        return f"a look is a whole number from 0 to {LOOK_LIMIT - 1:,}"
    return None


# A planet's orbit in AU, a moon's in km; the rest in degrees, or plain
# (eccentricity).
ORBIT_LIMITS = {"au": (0.001, 100_000), "km": (100, 100_000_000), "e": (0, 0.99), "i": (0, 180),
                "node": (0, 360), "periapsis": (0, 360), "anomaly": (0, 360)}


def orbit_error(orbit: Any, moon: bool = False) -> str | None:
    """Why a planet's or moon's orbit is refused, or None."""
    if not isinstance(orbit, dict):
        return "orbit must be an object"
    distance = "km" if moon else "au"
    if distance not in orbit:
        return f"a {'moon' if moon else 'planet'}'s orbit needs '{distance}'"
    for key, value in orbit.items():
        if key not in ORBIT_LIMITS or key == ("au" if moon else "km"):
            return f"unknown orbit field {key!r}"
        low, high = ORBIT_LIMITS[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
            return f"orbit {key} must be a number between {low:g} and {high:g}"
    return None


# Rings in planet radii, belts in AU.
RINGS_LIMITS = (1.0, 20.0)
BELT_LIMITS = (0.001, 100_000)
LAGRANGE_POINTS = ("L1", "L2", "L3", "L4", "L5")


def tilt_error(tilt: Any) -> str | None:
    """Why an axial tilt (degrees, against the orbit; over 90 turns the
    other way, as Venus) is refused, or None."""
    if isinstance(tilt, bool) or not isinstance(tilt, (int, float)) or not 0 <= tilt <= 180:
        return "tilt must be a number of degrees between 0 and 180"
    return None


def bearing_error(bearing: Any) -> str | None:
    """Why the way a planet's pole leans is refused, or None: degrees in the
    system's plane, from 0 to 360, as the orbit's angles."""
    if not isinstance(bearing, (int, float)) or isinstance(bearing, bool) or not 0 <= bearing <= 360:
        return "the way the tilt leans is in degrees, from 0 to 360"
    return None


def ring_density_error(density: Any) -> str | None:
    """Why a ring's density is refused, or None."""
    low, high = RING_DENSITY_LIMITS
    if not isinstance(density, (int, float)) or isinstance(density, bool) or not low <= density <= high:
        return f"a ring's density runs from {low:g} (faint, as Jupiter's) to {high:g} (dense, as Saturn's B ring)"
    return None


def rings_error(rings: Any) -> str | None:
    """Why a planet's rings are refused, or None: a list of bands, each an
    inner and outer edge in planet radii, the inner the smaller; innermost
    first, a gap between each and the next (a division, as Saturn's Cassini
    Division), and optionally its density. One band as a bare object is an
    older form."""
    low, high = RINGS_LIMITS
    bands = [rings] if isinstance(rings, dict) else rings
    if not isinstance(bands, list) or not bands:
        return "rings are a list of bands, each with 'inner' and 'outer' in planet radii"
    for k, band in enumerate(bands):
        if not isinstance(band, dict) or not {"inner", "outer"} <= set(band) <= {"inner", "outer", "density"}:
            return "a ring needs 'inner' and 'outer', in planet radii, and may have a 'density'"
        inner, outer = band["inner"], band["outer"]
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (inner, outer)) \
                or not low <= inner < outer <= high:
            return f"rings run from {low:g} to {high:g} planet radii, the inner edge first"
        if "density" in band and (error := ring_density_error(band["density"])):
            return error
        if k and inner <= bands[k - 1]["outer"]:
            return "rings run innermost first, each beginning beyond the last one's outer edge"
    return None


def host_error(host: Any) -> str | None:
    """Why a host is refused, or None: a star's name, or stars' names joined
    with "+" (galaxy.hierarchy). Whether the system's stars make it is a
    finding, `star-host`."""
    if not isinstance(host, str) or not host.strip() or any(not part.strip() for part in host.split("+")):
        return "a host is a star's name, or stars' names joined with '+'"
    return None


def belt_error(belt: Any) -> str | None:
    """Why an asteroid belt is refused, or None."""
    if not isinstance(belt, dict):
        return "a belt must be an object"
    low, high = BELT_LIMITS
    inner, outer = belt.get("inner"), belt.get("outer")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (inner, outer)) \
            or not low <= inner < outer <= high:
        return "a belt runs from its inner to its outer edge, in AU, the inner the smaller"
    return None


def _check_belts(belts: Any, where: str) -> None:
    """Refuse (ValidationError) a system's belts unless they are a list of
    valid belts, each host written as a host is."""
    if belts is None:
        return
    if not isinstance(belts, list):
        raise ValidationError(f"{where}: 'belts' must be a list")
    for k, belt in enumerate(belts):
        if (error := belt_error(belt)) or ("host" in belt and (error := host_error(belt["host"]))):
            raise ValidationError(f"{where}, belt {k + 1}: {error}")


def body_ids(system: dict[str, Any]) -> set[str]:
    """What a point of interest can be anchored to: "star", a planet's id, or a moon's
    as "<planet id>/<moon id>"."""
    out = {"star"}
    for planet in system.get("planets") or []:
        out.add(str(planet.get("id")))
        out.update(f"{planet.get('id')}/{moon.get('id')}" for moon in planet.get("moons") or [])
    return out


def anchor_error(anchor: Any, system: dict[str, Any]) -> str | None:
    """Why a point of interest's anchor is refused, or None: a body of the
    system, and around the star an orbit at a distance in AU (`au`); around a
    planet or moon a Lagrange point of it (`point`) or an orbit at a height
    above its surface in km (`km`)."""
    def positive(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0

    if not isinstance(anchor, dict) or anchor.get("body") not in body_ids(system):
        return "a point of interest is anchored to a body of its system"
    if anchor["body"] == "star":
        if set(anchor) - {"host"} != {"body", "au"} or not positive(anchor["au"]):
            return "a point of interest orbits the star at a distance in AU"
        return host_error(anchor["host"]) if "host" in anchor else None
    if "point" in anchor:
        if anchor["point"] not in LAGRANGE_POINTS or set(anchor) != {"body", "point"}:
            return f"a Lagrange point is one of {', '.join(LAGRANGE_POINTS)} of a planet or moon"
    elif set(anchor) != {"body", "km"} or not positive(anchor["km"]):
        return "a point of interest orbits a planet or moon at a height in km, or sits at one of its Lagrange points"
    return None


# What a point of interest is; absent is just a point of interest. The
# engine's own kinds — a project adds its own (galaxy.objects). Jumpgates are
# the travel planner's nodes in a system.
POI_KINDS = tuple(objects.POINTS)
# A jumpgate's `pair` is its partner's id, both ways; its `grade` how fast a
# hop is (travel.json `jumpgates`): early gates took hours between planets,
# mature ones minutes.
JUMPGATE_GRADES = ("early", "mature")

# Gate links between systems; provisional gates are the low-power ones exploration ships set
# up, permanent ones the installations that replace them.
GATE_GRADES = ("permanent", "provisional")


def _check_trips(data: dict[str, Any]) -> None:
    """Refuse (ValidationError) the stored trips (galaxy.trips) on the first
    thing that does not hold."""
    trips = data.get("trips")
    if trips is None:
        return
    if not isinstance(trips, list):
        raise ValidationError("'trips' must be a list")
    from galaxy.trips import problems         # galaxy.trips plans: loaded only when there are trips
    if found := problems(data):
        raise ValidationError(found[0])


def _check_gate_links(data: dict[str, Any]) -> None:
    """Refuse (ValidationError) gate links that are not pairs of two known
    systems, of a known grade, each pair once; and `gate_blocked` unless it
    is a list of {from, to} pairs of systems."""
    links = data.get("gate_links")
    if links is None:
        return
    if not isinstance(links, list):
        raise ValidationError("'gate_links' must be a list")
    names = {s.get("name") for s in data.get("star_systems") or []}
    seen = set()
    for k, link in enumerate(links):
        at = f"gate link {k + 1}"
        if not isinstance(link, dict) or set(link) - {"from", "to", "grade"}:
            raise ValidationError(f"{at}: a link has 'from', 'to' and optionally 'grade'")
        for end in ("from", "to"):
            if link.get(end) not in names:
                raise ValidationError(f"{at}: {link.get(end)!r} is not a system")
        if link["from"] == link["to"]:
            raise ValidationError(f"{at}: a gate links two systems")
        if link.get("grade", "permanent") not in GATE_GRADES:
            raise ValidationError(f"{at}: its grade is one of {', '.join(GATE_GRADES)}")
        pair = frozenset((link["from"], link["to"]))
        if pair in seen:
            raise ValidationError(f"{at}: {link['from']} and {link['to']} are linked twice")
        seen.add(pair)
    # Generated links someone removed: never generated again (galaxy.gatenet).
    blocked = data.get("gate_blocked")
    if blocked is not None:
        if not isinstance(blocked, list) or any(not isinstance(p, dict) or set(p) != {"from", "to"}
                                                or p["from"] not in names or p["to"] not in names for p in blocked):
            raise ValidationError("'gate_blocked' is a list of {from, to} pairs of systems")


def _check_pois(system: dict[str, Any], where: str) -> None:
    """Refuse (ValidationError) a system's points of interest without a name,
    a valid anchor, a known kind, or a jumpgate's pair and grade as they must be."""
    points = system.get("points_of_interest")
    if points is None:
        return
    if not isinstance(points, list):
        raise ValidationError(f"{where}: 'points_of_interest' must be a list")
    for k, point in enumerate(points):
        if not isinstance(point, dict) or not (point.get("name") or "").strip():
            raise ValidationError(f"{where}, point of interest {k + 1} needs a name")
        if error := anchor_error(point.get("anchor"), system):
            raise ValidationError(f"{where}, point of interest {point['name']}: {error}")
        if "kind" in point and point["kind"] not in (kinds := objects.point_kinds()):
            raise ValidationError(f"{where}, point of interest {point['name']}: its kind is one of "
                                  + ", ".join(kinds))
        if error := _jumpgate_error(point, points):
            raise ValidationError(f"{where}, point of interest {point['name']}: {error}")


def _jumpgate_error(point: dict[str, Any], points: list[dict[str, Any]]) -> str | None:
    """Why a point's `pair` or `grade` is refused, or None: only a jumpgate has
    them, and its pair is another jumpgate of `points` paired with it."""
    if "pair" not in point and "grade" not in point:
        return None
    if point.get("kind") != "jumpgate":
        return "only a jumpgate has a pair or a grade"
    if "grade" in point and point["grade"] not in JUMPGATE_GRADES:
        return "a jumpgate's grade is one of " + ", ".join(JUMPGATE_GRADES)
    if "pair" in point:
        other = next((p for p in points if p.get("id") == point["pair"]), None)
        if other is None or other is point or other.get("kind") != "jumpgate" or other.get("pair") != point.get("id"):
            return "its pair is another jumpgate of the system, paired with it"
    return None


# The eight classes the planet module draws (viewer/planet/planet-look.js:
# a texture for each, an atmosphere for some).
# 'volcanic' is supported by the renderer but unused in the data; an empty
# class is valid and resolves (resolveClass) as: explicit class, else a globe
# texture (listed in the maps' manifest, public/planets/index.json) implies
# terrestrial-habitable, else unknown. A planet carries no texture key of its
# own.
PLANET_CLASSES = (
    "terrestrial-barren",
    "terrestrial-habitable",
    "terrestrial-desert",
    "gas-giant-cold",
    "gas-giant-warm",
    "ice-world",
    "volcanic",
    "unknown",
)

# How the classes read on screen: the slugs are
# technical terms, kept in galaxy.json and URLs, not display text.
PLANET_CLASS_LABELS = {
    "terrestrial-barren": "Terrestrial, barren",
    "terrestrial-habitable": "Terrestrial, habitable",
    "terrestrial-desert": "Terrestrial, desert",
    "gas-giant-cold": "Gas giant, cold",
    "gas-giant-warm": "Gas giant, warm",
    "ice-world": "Ice world",
    "volcanic": "Volcanic",
    "unknown": "Unknown",
}

# The types the SVG renderer knows.  Absent means 'star'.
OBJECT_TYPES = (
    "star",
    "black_hole",
    "neutron_star",
    "pulsar",
    "white_dwarf",
    # A nebula is a region, not a system: galaxy.nebulae.
    "wormhole",
    "anomaly",
    "quasar",
)

SPECTRAL_LETTERS = "OBAFGKM"
# The shape of an MK class: letter, subtype, luminosity class, peculiarity
# marks — K3V, M4.5Ve, K3IIIb, G2. The whole shape is checked, not only the
# letter, so a name such as "Alpha Test" is not taken for a class.
SPECTRAL_SHAPE = re.compile(r"[OBAFGKM](\d(\.\d+)?)?(Iab|Ia\+|Ia|Ib|VII|VI|IV|V|III|II|I|0)?[a-z:]*")

# The grid the renderer draws: a centre sector "0", then 15 rings x 24 beams
# lettered A–X. Naming a sector is what makes the renderer stroke its wedge red,
# so an id that does not exist would silently name nothing.
SECTOR_IDS = ("0",) + tuple(
    f"{chr(ord('A') + beam)}{ring}" for ring in range(1, 16) for beam in range(24)
)
SECTOR_ID_SET = frozenset(SECTOR_IDS)


def normalise(data: dict[str, Any]) -> dict[str, Any]:
    """Recompute derived fields in place and return the document.

    Two fields are derived and are never trusted on read:

    - `spectral_class` mirrors `stars[0].spectral_class` when `stars` exists.
      Keeping it is what lets every existing consumer carry on unchanged while
      multi-star systems are represented underneath.
    - `planet_count` is the number of planets, dwarf planets not counted
      (`dwarf: true`). It was already denormalised and
      already capable of drifting; deriving it removes the possibility.

    `stars` is dropped when it carries no information — a single unnamed star
    says nothing that `spectral_class` did not already say — so the array only
    appears in the file once it means something.
    """
    for system in data.get("star_systems", []):
        stars = system.get("stars")
        if stars is not None:
            if len(stars) == 1 and not (stars[0].get("name") or "").strip():
                system.pop("stars", None)
            else:
                primary = stars[0].get("spectral_class")
                if primary:
                    system["spectral_class"] = primary

        planets = system.get("planets")
        if planets is not None:
            if planets:
                system["planet_count"] = sum(1 for p in planets if not p.get("dwarf"))
                _renumber(planets)
                # One ring as a bare object, an older form: a list.
                for planet in planets:
                    if isinstance(planet.get("rings"), dict):
                        planet["rings"] = [planet["rings"]]
            else:
                system.pop("planets", None)
                system.pop("planet_count", None)
    nebulae.normalise(data)
    return data


def next_id(bodies: list[dict[str, Any]], prefix: str) -> str:
    """The id a new body among these takes: one past the highest given."""
    taken = [int(b["id"][1:]) for b in bodies
             if isinstance(b.get("id"), str) and b["id"][1:].isdigit()]
    return f"{prefix}{max(taken, default=0) + 1}"


def _renumber(bodies: list[dict[str, Any]], prefix: str = "p") -> None:
    """Make `index` follow orbital position, and give each body an `id`.

    Derivable: across every system that has planets, index is
    already position + 1 without exception. Deriving it means inserting or
    removing a planet cannot leave a gap or a duplicate behind. Planets and
    dwarf planets are counted apart, each by orbit among its own kind:
    Jupiter is planet 5 with Ceres, dwarf planet 1, inside it.

    `id` is the opposite: given once, never renumbered — "p3" stays p3 when p2
    is removed. Index and name both change, so a draft compared with the
    committed file by either paired the wrong bodies: removing one named planet
    among unnamed ones reported three removed. Unique within
    the system (planets) or the planet (moons); a new body takes the next number.
    """
    counted = {False: 0, True: 0}
    for body in bodies:
        kind = bool(body.get("dwarf"))
        counted[kind] += 1
        body["index"] = counted[kind]
        if not isinstance(body.get("id"), str) or not body["id"]:
            body["id"] = next_id(bodies, prefix)
        moons = body.get("moons")
        if moons is not None:
            if moons:
                _renumber(moons, "m")
            else:
                body.pop("moons", None)


def validate(data: Any) -> None:
    """Raise ValidationError if the document would break a consumer."""
    if not isinstance(data, dict):
        raise ValidationError("galaxy.json must be a JSON object")

    for key in ("labels", "star_systems"):
        if key in data and not isinstance(data[key], list):
            raise ValidationError(f"'{key}' must be a list")
    if "sector_names" in data:
        if not isinstance(data["sector_names"], dict):
            raise ValidationError("'sector_names' must be an object")
        for sid, label in data["sector_names"].items():
            if sid not in SECTOR_ID_SET:
                raise ValidationError(
                    f"unknown sector {sid!r} — expected '0' or a letter A–X with a ring 1–15"
                )
            if not isinstance(label, str) or not label.strip():
                raise ValidationError(f"sector {sid} needs a non-empty name")

    seen: set[str] = set()
    promoted: dict[str, str] = {}
    for i, system in enumerate(data.get("star_systems", [])):
        # Named for the reader of a refused Save, not by array index, and
        # counted from 1 as an editor shows them.
        where = f"system {i + 1}"
        if not isinstance(system, dict):
            raise ValidationError(f"{where} must be an object")

        name = system.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValidationError(f"{where} needs a non-empty name")
        if name in seen:
            raise ValidationError(f"duplicate system name {name!r}")
        seen.add(name)
        where = name

        for axis in ("x", "y", "z"):
            if not isinstance(system.get(axis), (int, float)):
                raise ValidationError(f"{where}: '{axis}' must be a number")
            if error := coordinate_error(axis, system[axis]):
                raise ValidationError(f"{where}: {error}")

        # A system promoted from the procedural galaxy keeps its id there
        # (galaxy.procedural): the layer skips it, and its place is not carved.
        if "procedural" in system:
            pid = system["procedural"]
            if not isinstance(pid, str) or not re.fullmatch(r"c\d{6}-\d{1,2}", pid):
                raise ValidationError(f"{where}: 'procedural' is the id it had in the procedural galaxy, as c123456-0")
            if pid in promoted:
                raise ValidationError(f"{where}: {pid} is promoted twice (also {promoted[pid]})")
            promoted[pid] = name

        # The system's reference plane in the galaxy (galaxy.orbits.draw_plane).
        if "plane" in system:
            plane = system["plane"]
            if not (isinstance(plane, dict) and set(plane) == {"i", "node", "zero"}
                    and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in plane.values())
                    and 0 <= plane["i"] <= 180 and 0 <= plane["node"] < 360 and 0 <= plane["zero"] < 360):
                raise ValidationError(f"{where}: 'plane' must be {{i: 0–180, node: 0–360, zero: 0–360}} in degrees")

        obj_type = system.get("object_type")
        if obj_type is not None and obj_type not in OBJECT_TYPES:
            raise ValidationError(f"{where}: unknown object_type {obj_type!r}")

        # Every consumer reads spectral_class; galaxy-map.js only uses its first
        # character, but the data carries full MK strings like 'K3V', so this
        # checks the letter and leaves the rest alone.
        _check_spectral(system.get("spectral_class"), where)

        for j, star in enumerate(system.get("stars", []) or []):
            at = f"{where}, star {j + 1}"
            if not isinstance(star, dict):
                raise ValidationError(f"{at} must be an object")
            _check_spectral(star.get("spectral_class"), at)
            # A companion's orbit around the primary (galaxy.orbits); the
            # primary has none of its own.
            if "orbit" in star or "host" in star:
                if j == 0:
                    raise ValidationError(f"{at}: the primary star has no orbit — its companions orbit it")
                if "orbit" in star and (error := orbit_error(star["orbit"])):
                    raise ValidationError(f"{at}: {error}")
                if "host" in star and (error := host_error(star["host"])):
                    raise ValidationError(f"{at}: {error}")
            if "+" in (star.get("name") or ""):
                raise ValidationError(f"{at}: a star's name has no '+' — it joins the names of a group")

        stars = system.get("stars")
        if stars is not None and len(stars) > 1:
            # The star tree (galaxy.hierarchy) knows its stars by name: a second
            # of the same name would vanish from it.
            named: dict[str, int] = {}
            for j, star in enumerate(stars):
                star_name = (star.get("name") or "").strip()
                if not star_name:
                    raise ValidationError(
                        f"{where}: star {j + 1} needs a name — "
                        "companions in a multi-star system must be named"
                    )
                if star_name in named:
                    raise ValidationError(f"{where}: star {j + 1} is named {star_name}, "
                                          f"as star {named[star_name] + 1} is")
                named[star_name] = j

        _check_bodies(system.get("planets"), where, "planets")
        _check_belts(system.get("belts"), where)
        _check_pois(system, where)

    if problems := nebulae.check(data):
        raise ValidationError(problems[0][0].upper() + problems[0][1:])
    check_names(data)
    _check_gate_links(data)
    _check_trips(data)


_LUMINOSITY = ("Ia+", "Iab", "Ia", "Ib", "VII", "VI", "IV", "V", "III", "II", "I", "0")
_SPECTRAL = re.compile(r"^([A-Za-z])(\d+(?:\.\d+)?)?(.*)$")


def normalise_spectral(value: str) -> str:
    """Upper-case what MK writes upper case — the spectral letter and the
    luminosity class — and leave the rest as typed: 'k5v' → 'K5V',
    'm4.5ve' → 'M4.5Ve', 'K3IIIb' unchanged. A peculiarity suffix (e, b, p)
    is lower case by convention, so the whole string is not upper-cased.
    """
    m = _SPECTRAL.match(value.strip())
    if not m:
        return value.strip()
    letter, subtype, rest = m.group(1).upper(), m.group(2) or "", m.group(3)
    for lum in _LUMINOSITY:
        if rest.upper().startswith(lum.upper()):
            return f"{letter}{subtype}{lum}{rest[len(lum):]}"
    return f"{letter}{subtype}{rest}"


def check_spectral(value: str) -> None:
    """Refuse a class whose letter is not one of SPECTRAL_LETTERS — the same
    rule the whole-file validation applies at Save, so an edit can be refused
    where it is typed rather than when saving."""
    if value[:1].upper() not in SPECTRAL_LETTERS:
        raise ValueError(f"{value!r} must start with one of {SPECTRAL_LETTERS}")
    if not SPECTRAL_SHAPE.fullmatch(value):
        raise ValueError(f"{value!r} is not a spectral class like K3V, M4.5Ve or G2")


def _check_spectral(value: Any, where: str) -> None:
    """Refuse (ValidationError) a spectral class that is not a string starting
    with one of SPECTRAL_LETTERS; none is fine."""
    if value is None:
        return
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{where}: spectral_class must be a non-empty string")
    if value[0].upper() not in SPECTRAL_LETTERS:
        raise ValidationError(
            f"{where}: spectral_class {value!r} must start with one of {SPECTRAL_LETTERS}"
        )


def named(data: dict[str, Any]):
    """Every named star, planet and moon: (system, kind, body). An unnamed
    star ("") or body ("?") has no name to share."""
    for system in data.get("star_systems", []):
        for star in system.get("stars") or []:
            if (star.get("name") or "").strip():
                yield system, "star", star
        for planet in system.get("planets") or []:
            for body, kind in [(planet, "planet")] + [(m, "moon") for m in planet.get("moons") or []]:
                if body.get("name") not in (None, "?"):
                    yield system, kind, body


def check_names(data: dict[str, Any]) -> None:
    """Refuse a star, planet or moon named as another anywhere in the galaxy,
    compared as the slug a map folder is named by. A system
    may share its name with its own primary."""
    seen: dict[str, tuple[str, str, str]] = {}
    for system, kind, body in named(data):
        name = body["name"].strip()
        slug = slugify(name)
        if slug in seen:
            other, other_kind, other_system = seen[slug]
            raise ValidationError(f"{system['name']}: {kind} {name} has the name of {other_kind} {other} "
                                  f"in {other_system} — star, planet and moon names are unique across the galaxy")
        seen[slug] = (name, kind, system["name"])
    # A nebula's name is none of these, nor a system's, nor another nebula's.
    systems = {slugify(s.get("name") or ""): s.get("name") for s in data.get("star_systems") or []}
    for nebula in data.get("nebulae") or []:
        name = (nebula.get("name") or "").strip() if isinstance(nebula, dict) else ""
        slug = slugify(name)
        if not slug:
            continue
        if slug in systems:
            raise ValidationError(f"Nebula {name} has the name of the system {systems[slug]}")
        if slug in seen:
            other, other_kind, other_system = seen[slug]
            where = f" in {other_system}" if other_kind != "nebula" else ""
            raise ValidationError(f"Nebula {name} has the name of {other_kind} {other}{where}")
        seen[slug] = (name, "nebula", "")


def _check_bodies(bodies: Any, where: str, label: str) -> None:
    """Refuse (ValidationError) the first planet or moon (`label` "planets" or
    "moons") whose fields break the schema; a planet's moons are checked too."""
    if bodies is None:
        return
    if not isinstance(bodies, list):
        raise ValidationError(f"{where}: '{label}' must be a list")
    ids: set = set()
    for k, body in enumerate(bodies):
        at = f"{where}, {label[:-1]} {k + 1}"
        if not isinstance(body, dict):
            raise ValidationError(f"{at} must be an object")
        if not isinstance(body.get("index"), int):
            raise ValidationError(f"{at} needs an integer 'index'")
        if "id" in body and body["id"] in ids:
            raise ValidationError(f"{at}: duplicate id {body['id']!r}")
        ids.add(body.get("id"))
        cls = body.get("class")
        if cls is not None and cls not in PLANET_CLASSES:
            raise ValidationError(f"{at}: unknown class {cls!r}")
        if "radius" in body and (error := radius_error(body["radius"])):
            raise ValidationError(f"{at}: {error}")
        if "look" in body and (error := look_error(body["look"])):
            raise ValidationError(f"{at}: {error}")
        if "orbit" in body and (error := orbit_error(body["orbit"], moon=label == "moons")):
            raise ValidationError(f"{at}: {error}")
        if "rings" in body and (error := rings_error(body["rings"])):
            raise ValidationError(f"{at}: {error}")
        if "tilt" in body and (error := tilt_error(body["tilt"])):
            raise ValidationError(f"{at}: {error}")
        if "tilt_bearing" in body and (error := bearing_error(body["tilt_bearing"])):
            raise ValidationError(f"{at}: {error}")
        if "dwarf" in body and (label == "moons" or body["dwarf"] is not True):
            raise ValidationError(f"{at}: 'dwarf' is true for a dwarf planet, or absent — moons have none")
        if "host" in body and (label == "moons" or (error := host_error(body["host"]))):
            raise ValidationError(f"{at}: {error if label != 'moons' else 'a moon orbits its planet, not a host'}")
        _check_bodies(body.get("moons"), at, "moons")
