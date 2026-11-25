"""Nebulae: regions of the galaxy, not systems.

galaxy.json holds them in a list of their own, `nebulae`, beside
`star_systems`:

    {"id": "n1", "name": "Orion Nebula", "kind": "emission",
     "x": -1150.2, "y": 26080.4, "z": -470.0,     # the centre, ly, as a system's
     "size": [12, 12, 8],                          # the ellipsoid's semi-axes, ly
     "tilt": [0, 0, 0],                            # its orientation, degrees (optional)
     "density": 600,                               # particles per cm³ (optional: the kind's)
     "colour": "#ff5a85",                          # optional: the kind's
     "real": "M42",                                # the sky's designation, for a real one
     "heart": "Theta1 Orionis"}                    # the system at its centre, if any

The kind sets the look and a typical density, the density the effects:
the medium thicker, sublight slowed or barred.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from galaxy import medium

# The kinds: a label, the colour they are drawn in, and a typical density in
# particles per cm³ — an H II region's hundreds, a molecular cloud's tens of
# thousands, a supernova remnant's hot, thin interior.
KINDS: dict[str, dict[str, Any]] = {
    "emission": {"label": "Emission region", "colour": "#ff5a85", "density": 600},
    "reflection": {"label": "Reflection nebula", "colour": "#7fa7ff", "density": 300},
    "dark": {"label": "Dark cloud", "colour": "#3a2f27", "density": 10_000},
    "planetary": {"label": "Planetary nebula", "colour": "#4fd6c4", "density": 1_000},
    "remnant": {"label": "Supernova remnant", "colour": "#ffa65c", "density": 1},
}

# A nebula's semi-axes, ly: a planetary nebula's tenth of a light year to a
# giant molecular cloud's few hundred.
SIZE_LIMITS = (0.01, 5_000)
DENSITY_LIMITS = (0.001, 10_000_000)
TILT_LIMIT = 360
_COLOUR = re.compile(r"#[0-9a-fA-F]{6}")
_ID = re.compile(r"n\d+")


def colour(nebula: dict[str, Any]) -> str:
    """The colour a nebula is drawn in: its own, else its kind's."""
    return nebula.get("colour") or KINDS.get(nebula.get("kind"), KINDS["emission"])["colour"]


def density(nebula: dict[str, Any]) -> float:
    """A nebula's density, particles per cm³: its own, else its kind's."""
    return nebula.get("density") or KINDS.get(nebula.get("kind"), KINDS["emission"])["density"]


def label(kind: Optional[str]) -> str:
    """A kind in words: "Dark cloud"."""
    return KINDS[kind]["label"] if kind in KINDS else (kind or "Nebula")


def field_error(field: str, value: Any) -> Optional[str]:
    """Why `value` is refused as a nebula's `field`, or None. The centre's
    axes are checked as a system's (schema.coordinate_error)."""
    from galaxy.schema import coordinate_error

    def number(v: Any) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    if field == "name":
        return None if isinstance(value, str) and value.strip() else "a nebula needs a name"
    if field == "kind":
        return None if value in KINDS else f"its kind is one of {', '.join(KINDS)}"
    if field in ("x", "y", "z"):
        return coordinate_error(field, value) if number(value) else f"'{field}' must be a number"
    if field == "size":
        low, high = SIZE_LIMITS
        if not (isinstance(value, list) and len(value) == 3 and all(number(v) and low <= v <= high for v in value)):
            return f"its size is three semi-axes, each {low:g} to {high:,} ly"
        return None
    if field == "tilt":
        if not (isinstance(value, list) and len(value) == 3 and all(number(v) and -TILT_LIMIT <= v <= TILT_LIMIT for v in value)):
            return f"its tilt is three angles, each within ±{TILT_LIMIT}°"
        return None
    if field == "density":
        low, high = DENSITY_LIMITS
        return None if number(value) and low <= value <= high else \
            f"its density is {low:g} to {high:,} particles per cm³"
    if field == "colour":
        return None if isinstance(value, str) and _COLOUR.fullmatch(value) else "its colour is written #rrggbb"
    if field in ("real", "heart", "id"):
        return None if isinstance(value, str) and value.strip() else f"its {field} is a name"
    return f"a nebula has no field {field!r}"


REQUIRED = ("name", "kind", "x", "y", "z", "size")
OPTIONAL = ("id", "tilt", "density", "colour", "real", "heart")


def check(data: dict[str, Any]) -> list[str]:
    """What is wrong with `data`'s nebulae, in words, first problems first;
    empty when they hold. Names are checked by the schema with the bodies'."""
    items = data.get("nebulae")
    if items is None:
        return []
    if not isinstance(items, list):
        return ["'nebulae' must be a list"]
    systems = {s.get("name") for s in data.get("star_systems") or []}
    problems, ids = [], set()
    for k, nebula in enumerate(items):
        where = f"nebula {k + 1}"
        if not isinstance(nebula, dict):
            problems.append(f"{where} must be an object")
            continue
        if isinstance(nebula.get("name"), str) and nebula["name"].strip():
            where = nebula["name"]
        for field in REQUIRED:
            if field not in nebula:
                problems.append(f"{where}: {'a nebula needs a name' if field == 'name' else f'it needs {field!r}'}")
        for field, value in nebula.items():
            if field not in REQUIRED + OPTIONAL:
                problems.append(f"{where}: a nebula has no field {field!r}")
            elif (error := field_error(field, value)):
                problems.append(f"{where}: {error}")
        if "id" in nebula:
            if not (isinstance(nebula["id"], str) and _ID.fullmatch(nebula["id"])):
                problems.append(f"{where}: its id is n1, n2, …")
            elif nebula["id"] in ids:
                problems.append(f"{where}: its id {nebula['id']} is another's")
            ids.add(nebula.get("id"))
        if isinstance(nebula.get("heart"), str) and nebula["heart"] not in systems:
            problems.append(f"{where}: {nebula['heart']} is not a system")
    return problems


def normalise(data: dict[str, Any]) -> None:
    """Give every nebula an id (n1, n2, …), once, never reused; drop an empty
    list."""
    from galaxy.schema import next_id
    items = data.get("nebulae")
    if items is None:
        return
    if not items:
        data.pop("nebulae")
        return
    for nebula in items:
        if isinstance(nebula, dict) and "id" not in nebula:
            nebula["id"] = next_id(items, "n")


# ── the real sky's ────────────────────────────────────────────────────────────
# A kept table, as the bright stars' (galaxy.brightstars): position and angular
# size from OpenNGC, distance from the literature, each row with its sources.

DATA = "data/real-nebulae.csv"


def real_table() -> list[dict[str, Any]]:
    """The real nebulae as the DATA file lists them, the numbers parsed."""
    import csv
    from importlib import resources
    text = resources.files("galaxy").joinpath(DATA).read_text(encoding="utf-8")
    rows = csv.DictReader(line for line in text.splitlines() if not line.startswith("#"))
    return [{**r, **{k: float(r[k]) for k in ("ra", "dec", "ly", "major_arcmin", "minor_arcmin")}} for r in rows]


def _half(ly: float, arcmin: float) -> float:
    """The half-axis, ly, that an angular size spans at a distance."""
    import math
    return ly * math.tan(math.radians(arcmin / 60 / 2))


def real() -> list[dict[str, Any]]:
    """The real nebulae as galaxy.json holds them: centred where the sky has
    them (galaxy.celestial), the two half-axes the sky shows from their
    angular size at their distance, the depth — which it does not show —
    their geometric mean."""
    import math
    from galaxy import celestial
    out = []
    for r in real_table():
        x, y, z = celestial.to_frame(r["ra"], r["dec"], r["ly"])
        a, b = _half(r["ly"], r["major_arcmin"]), _half(r["ly"], r["minor_arcmin"])
        out.append({"name": r["name"], "kind": r["kind"], "x": round(x, 3), "y": round(y, 3), "z": round(z, 3),
                    "size": [round(v, 3) for v in (a, b, math.sqrt(a * b))], "real": r["real"]})
    return out


_PLACE = ("x", "y", "z", "size")


def add_real(doc: dict[str, Any]) -> list[str]:
    """Put the real nebulae `doc` lacks into its `nebulae` (matched by their
    designation, `real`), and those already in back to the sky's place and
    size; what an author changed besides — name, kind, density, colour,
    heart — stays. The names added."""
    items = doc.setdefault("nebulae", [])
    have = {n.get("real"): n for n in items if n.get("real")}
    added = []
    for n in real():
        if n["real"] in have:
            have[n["real"]].update({k: n[k] for k in _PLACE})
        else:
            items.append(n)
            added.append(n["name"])
    if not items:
        doc.pop("nebulae")
    return added


def real_current(doc: dict[str, Any]) -> bool:
    """Whether every real nebula is in `doc`, at the sky's place and size."""
    have = {n.get("real"): n for n in doc.get("nebulae") or [] if n.get("real")}
    return all(n["real"] in have and all(have[n["real"]].get(k) == n[k] for k in _PLACE) for n in real())


# ── effects ───────────────────────────────────────────────────────────────────
# FTL through the medium is untouched by the matter, and the medium is bound
# to matter: thicker inside a nebula, faster to cross. Sublight is slowed by
# the gas and dust — a grain met at a fraction of light speed hits like a
# shell — and barred past a density; gates stand only where it is thin enough.

# The medium's factor: 1 + this × log10(1 + density / 100) — 1.5 in a dark
# cloud, 1.2 in an emission region.
MEDIUM_GAIN = 0.25
SAFE_SPEED = 0.01               # sublight, as a share of light speed, at 100 particles per cm³ …
SAFE_DENSITY = 100              # … falling as the square root of the density
BARRED_DENSITY = 50_000         # past this, no sublight at all: a dense cloud's core
GATE_DENSITY = 5_000            # gates stand only where it is thinner


def medium_factor(nebula: dict[str, Any]) -> float:
    """How much thicker the faster-than-light medium is inside the nebula: 1.5 in a dark cloud,
    about 1.2 in an emission region, hardly more in a supernova remnant."""
    import math
    return 1 + MEDIUM_GAIN * math.log10(1 + density(nebula) / 100)


def sublight_limit(nebula: dict[str, Any]) -> float:
    """The safe sublight speed inside the nebula, as a share of light speed;
    0 where sublight is barred."""
    rho = density(nebula)
    return 0.0 if rho > BARRED_DENSITY else SAFE_SPEED * (SAFE_DENSITY / rho) ** 0.5


def gates_allowed(nebula: dict[str, Any]) -> bool:
    """Whether a gate can stand inside the nebula."""
    return density(nebula) <= GATE_DENSITY


def _rotation(nebula: dict[str, Any]):
    """The nebula's turn (its tilt, degrees, x-y-z) as a matrix."""
    import numpy as np
    ax, ay, az = (np.radians(v) for v in (nebula.get("tilt") or [0, 0, 0]))
    rx = np.array([[1, 0, 0], [0, np.cos(ax), -np.sin(ax)], [0, np.sin(ax), np.cos(ax)]])
    ry = np.array([[np.cos(ay), 0, np.sin(ay)], [0, 1, 0], [-np.sin(ay), 0, np.cos(ay)]])
    rz = np.array([[np.cos(az), -np.sin(az), 0], [np.sin(az), np.cos(az), 0], [0, 0, 1]])
    return rz @ ry @ rx


def containing(doc: dict[str, Any], point) -> list[dict[str, Any]]:
    """The nebulae of `doc` whose ellipsoid holds `point` (x, y, z, ly)."""
    import numpy as np
    out = []
    for n in doc.get("nebulae") or []:
        local = _rotation(n).T @ (np.asarray(point, dtype=float) - [n["x"], n["y"], n["z"]])
        if float(np.sum((local / np.asarray(n["size"], dtype=float)) ** 2)) <= 1:
            out.append(n)
    return out


# What a planet in a nebula meets, as science suggests: a
# warning where it may harm life, a note where it may change the climate;
# reflection and planetary nebulae are mild.
HABITABILITY = {
    "emission": (False, "hard ultraviolet from its young O and B stars strips ozone, and a supernova among them "
                        "is never far off"),
    "remnant": (False, "cosmic rays raised for tens of thousands of years after the supernova: ozone loss, "
                       "mutations, a changed climate"),
    "dark": (True, "the star's wind is squeezed: cosmic rays and dust reach the planets — cooling, ice ages"),
}


def findings(doc: dict[str, Any], system: dict[str, Any]) -> list[tuple[str, str, bool]]:
    """(kind, message, note) for a system inside a nebula: what it means
    there — the medium thicker, sublight slowed or barred, gates or none, a
    dark cloud's cover — and for each habitable planet what it meets."""
    at = (system.get("x", 0), system.get("y", 0), system.get("z", 0))
    out = []
    inside = containing(doc, at)
    called = medium.name(medium.load()) if inside else None
    for n in inside:
        cap = sublight_limit(n)
        said = [f"the {called} {medium_factor(n):.1f}× as thick",
                f"sublight barred by its gas and dust ({density(n):,.0f} particles per cm³)" if cap == 0
                else f"sublight safe to {cap * 100:.2g} % of light speed",
                "gates can stand here" if gates_allowed(n) else "no gate can stand here"]
        if n.get("kind") == "dark":
            said.append("hidden from optical sensors, not from infrared or radio")
        out.append(("nebula", f"{system.get('name')} lies in {n['name']}, {label(n.get('kind')).lower()}: "
                              + "; ".join(said), True))
        if n.get("kind") in HABITABILITY:
            note, what = HABITABILITY[n["kind"]]
            for planet in system.get("planets") or []:
                if planet.get("class") == "terrestrial-habitable":
                    out.append(("nebula-habitability", f"{planet.get('name')}, habitable, in {n['name']}: {what}", note))
    return out
