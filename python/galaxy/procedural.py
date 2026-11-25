"""The procedural galaxy: the systems of the Milky Way the catalogue does not
name, made by the generators — a layer over the catalogue on the maps, toggled like the real
stars, each system promoted into galaxy.json one at a time.

    model = load()                                  # the project's procedural.json
    dots = layer(model, catalogue)                  # every system: id, name, place, class
    system = details(model, dot, dots, catalogue)   # one, whole: stars, planets, moons

Where the systems lie follows the Milky Way's arms as the galaxy map was
first drawn on them: the Spitzer image (NASA/JPL-Caltech, R. Hurt), brighter than its surroundings on an arm, darker in a
gap — sharpened, so the arms show — and thicker toward the centre, the
bulge. Scaled so that round Sol the density is the catalogue's (the density round Sol sets the scale, the arms the layout).
The catalogue's authored systems count toward it: each takes the place of the
procedural system nearest it.

Stable under edits (a promoted system must still be where it was): the
numbers measured off the catalogue (`measure`) are kept in
the project's procedural.json, changed only by measuring again; every cell
of the density grid draws its systems from its own seed, every system its
details from its id. An authored system added removes one near it; a promoted
system carries its id (`procedural`) and is skipped, replacing itself.

What is authored stays out: nations, trips, sector names, labels, points of
interest. Names come from the project's generator (`namer`), never one
the catalogue has.
"""

from __future__ import annotations

import base64
import io
import json
import math
import random
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree

from galaxy import bodies, brightstars, names, orbits, project, schema
from galaxy.coords import CoordinateConverter
from galaxy.stars import star

# Where the catalogue's density is measured: round Sol, in the galactic
# plane, out to here. Steady to about 2,000 ly (5-6 systems per 1,000 ly²),
# thinner beyond, where the catalogue has few systems.
NEIGHBOURHOOD = 2_000
GALAXY_RADIUS = 50_000          # the disc filled, round the centre (schema: 100,000 ly across)
# The rim: the disc thins out beyond RIM (ly) — e^(−(r − rim)/RIM_FALLOFF) —
# the rim itself wandering RIM_WANDER either way round the disc, so the edge
# frays, with outliers far out, rather than stopping at GALAXY_RADIUS: a hard
# cut-off looks wrong.
RIM = 40_000
RIM_WANDER = 3_000
RIM_FALLOFF = 3_500
HEIGHT_SPREAD = 100             # ly: a height drawn from the neighbourhood's, moved by this much
# Toward the centre the galaxy thickens into its bulge:
# a height times 1 + BULGE·e^(−(r/BULGE_RADIUS)²) — about five times Sol's
# neighbourhood at the centre, half that 8,000 ly out, as Sol's from 20,000.
BULGE = 4.0
BULGE_RADIUS = 10_000
# The arms: the drawing's Spitzer image, read at GRID × GRID cells; a cell's
# brightness against the mean of its SURROUNDING (ly), to the power SHARPEN.
# Plain brightness left the gaps at 3/4 of an arm's density: no arms to see.
DRAWING = 5600                  # px, the drawing the image fills (galaxy.coords)
GRID = 700
SURROUNDING = 3_000
SHARPEN = 8
MOST_PER_CELL = 99              # a cell's count is drawn up to this (the densest knot expects ~60; ids allow 99)
# Stellar remnants among the systems, at
# about their real rates: white dwarfs anywhere; neutron stars, pulsars and
# black holes — the remnants of massive stars — more where stars form, their
# chance times the cell's density against the galaxy's mean (the arms, the
# bar), so the overall rates hold. A remnant keeps its planets only now and
# then, and has no companion.
REMNANT_RATES = {"white_dwarf": 0.06, "neutron_star": 0.004, "pulsar": 0.001, "black_hole": 0.001}
BORN_MASSIVE = ("neutron_star", "pulsar", "black_hole")
MASSIVE_RADIUS = 15_000         # ly: how fast massive stars' remnants thin out from the centre
REMNANT_PLANETS = 0.3           # the chance a remnant keeps the planets drawn for it
HABITABLE_SHARE = 0.3           # of the planets in the habitable zone
RING_SHARE = 0.3                # of the gas giants
MOONS = {                       # how many moons, by planet class: the choices, evenly
    "gas-giant-warm": (1, 2, 3, 4, 5, 6, 8, 12),
    "gas-giant-cold": (1, 2, 3, 4, 5, 6, 8),
    "ice-world": (0, 0, 0, 1, 2),
}
ROCKY_MOONS = (0, 0, 0, 0, 1, 1, 2)


# ── the numbers the layer follows ─────────────────────────────────────────────

def _story(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """The catalogue's own systems: not the real sky's, not promoted ones."""
    return [s for s in doc.get("star_systems") or []
            if not brightstars.is_real(s) and not s.get("procedural")]


def measure(doc: dict[str, Any], seed: int = 1) -> dict[str, Any]:
    """What the layer follows, read off `doc`'s authored systems — to be kept
    in the project's procedural.json, so the layer stays where it is when the catalogue changes."""
    story = _story(doc)
    sol = next((s for s in story if s.get("name") == "Sol"), None)
    if sol is None:
        raise ValueError("The catalogue has no Sol to measure the density round")
    near = [s for s in story if math.hypot(s["x"] - sol["x"], s["y"] - sol["y"]) <= NEIGHBOURHOOD]
    return {
        "about": "The procedural galaxy's numbers, measured off the catalogue's own systems "
                 "(galaxy.procedural; python -m galaxy.cli.procedural --measure). Kept, so the "
                 "layer stays where it is when the catalogue changes.",
        "seed": seed,
        "sol": [sol["x"], sol["y"]],
        "density": len(near) / (math.pi * NEIGHBOURHOOD ** 2),   # systems per ly² of the plane
        "heights": [s["z"] for s in near],
        "classes": [s["spectral_class"] for s in story],
        "companion_share": round(sum(1 for s in story if len(s.get("stars") or []) > 1) / len(story), 4),
        # Planets, not dwarf planets: Sol's seventeen bodies drawn as planets ran
        # out past 100,000 AU.
        "planet_counts": [s.get("planet_count") or 0 for s in story],
    }


def load(path: Optional[Path] = None) -> dict[str, Any]:
    """The measured model (`measure`) as `path` (the project's by default)
    holds it."""
    return json.loads((path or project.current().procedural).read_text(encoding="utf-8"))


def exclusion(model: dict[str, Any]) -> float:
    """One system's share of the plane at the density, as a radius (~255
    ly): an authored system takes the place of a procedural one within twice it."""
    return 1 / math.sqrt(math.pi * model["density"])


# ── where: the arms ───────────────────────────────────────────────────────────

@lru_cache(maxsize=2)
def _image(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """The image's brightness, cell by cell of the drawing (GRID × GRID, row
    0 at the top as drawn), and its mean over SURROUNDING. The image is
    embedded in the drawing, turned half round."""
    if path.suffix.lower() == ".svg":
        text = path.read_text(encoding="utf-8")
        start = text.index("base64,", text.index("<image")) + len("base64,")
        data = base64.b64decode(re.sub(r"\s", "", text[start:text.index('"', start)]))
    else:
        data = path.read_bytes()                 # the image itself, as a drawing embeds it
    image = Image.open(io.BytesIO(data)).rotate(180).convert("L").resize((GRID, GRID), Image.BOX)
    light = np.asarray(image, dtype=float) / 255
    return light, gaussian_filter(light, SURROUNDING * _px_per_ly() * GRID / DRAWING) + 1e-3


def arms(path: Optional[Path] = None) -> np.ndarray:
    """How dense, relative, cell by cell: the image's brightness against its
    surroundings, sharpened. The image is the project's `density` by default."""
    light, around = _image(path or project.current().density)
    return around * (light / around) ** SHARPEN


def _converter() -> CoordinateConverter:
    """The galactic ↔ graphic conversion of the DRAWING-pixel drawing."""
    return CoordinateConverter(DRAWING / 2, DRAWING / 2)


def _px_per_ly() -> float:
    """The drawing's scale (galaxy.coords anchors it on Sol), in its own pixels."""
    x, y = _converter().galactic_to_graphic(-513, 24995)
    return math.hypot(x - DRAWING / 2, y - DRAWING / 2) / math.hypot(-513, 24995)


def _unit(keys: np.ndarray) -> np.ndarray:
    """A number in [0, 1) for each key (uint64), the same each time: a
    counter-based draw (splitmix64), so a cell or a system needs no
    generator of its own and draws the same whatever else is drawn."""
    with np.errstate(over="ignore"):
        z = keys.astype(np.uint64) + np.uint64(0x9E3779B97F4A7C15)
        z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        z = z ^ (z >> np.uint64(31))
    return (z >> np.uint64(11)).astype(np.float64) / float(1 << 53)


def _key(seed: int, cell: np.ndarray, k: np.ndarray, what: int) -> np.ndarray:
    """The key of draw `what` for the `k`-th system of a cell."""
    # The 64th system of a cell and beyond (the densest knots) draw from keys
    # of their own (what + 8), so the first 64 keep the draws they had.
    k = k.astype(np.uint64)
    return ((np.uint64(seed) * np.uint64(1_000_003) + cell.astype(np.uint64)) * np.uint64(64)
            + k % np.uint64(64)) * np.uint64(16) + np.uint64(what) + np.uint64(8) * (k // np.uint64(64))


def _normal(u1: np.ndarray, u2: np.ndarray) -> np.ndarray:
    """Standard normal draws from two uniform ones in [0, 1) (Box–Muller)."""
    return np.sqrt(-2 * np.log1p(-u1)) * np.cos(2 * math.pi * u2)


def _places(model: dict[str, Any], within: Optional[float] = None) -> tuple[np.ndarray, np.ndarray]:
    """Every place, with its id number (cell × 128 + k): by the arms' density,
    scaled to the catalogue's round Sol, in the galaxy's disc or the part of
    it `within` light years of Sol; heights from the neighbourhood's, thicker
    toward the centre (BULGE)."""
    converter, cell = _converter(), DRAWING / GRID
    rows, cols = np.mgrid[0:GRID, 0:GRID]
    gx, gy = converter.graphic_to_galactic((cols + 0.5) * cell, (rows + 0.5) * cell)
    sol = model["sol"]
    near = np.hypot(gx - sol[0], gy - sol[1]) <= NEIGHBOURHOOD
    relative = arms()
    cell_area = abs(np.prod(np.subtract(converter.graphic_to_galactic(cell, cell), converter.graphic_to_galactic(0, 0))))
    expected = model["density"] * cell_area * relative / relative[near].mean() * _rim(model, gx, gy)
    keep = np.hypot(gx, gy) <= GALAXY_RADIUS
    if within:
        keep &= np.hypot(gx - sol[0], gy - sol[1]) <= within + 2 * cell / _px_per_ly()
    index = np.flatnonzero(keep)
    lam = expected.ravel()[index]
    # How many in each cell: Poisson by its inverse CDF, one draw per cell.
    u = _unit(_key(model["seed"], index, np.zeros_like(index), 0))
    term = np.exp(-lam)
    total, counts = term.copy(), np.zeros(index.size, dtype=np.int64)
    for k in range(1, MOST_PER_CELL + 1):
        counts += u >= total
        term = term * lam / k
        total = total + term
    cells = np.repeat(index, counts)
    k = np.concatenate([np.arange(n) for n in counts[counts > 0]]) if counts.any() else np.zeros(0, int)
    draw = [_unit(_key(model["seed"], cells, k, what)) for what in range(1, 6)]
    px = (cells % GRID + draw[0]) * cell
    py = (cells // GRID + draw[1]) * cell
    x, y = converter.graphic_to_galactic(px, py)
    heights = np.asarray(model["heights"], dtype=float)
    thick = 1 + BULGE * np.exp(-(np.hypot(x, y) / BULGE_RADIUS) ** 2)
    z = (heights[(draw[2] * len(heights)).astype(int)] + _normal(draw[3], draw[4]) * HEIGHT_SPREAD) * thick
    places = np.column_stack((x, y, np.clip(z, -schema.COORDINATE_LIMITS["z"], schema.COORDINATE_LIMITS["z"])))
    ids = cells * 128 + k
    if within:      # the cells at the edge reach a little past it
        inside = np.hypot(places[:, 0] - sol[0], places[:, 1] - sol[1]) <= within
        places, ids = places[inside], ids[inside]
    return places, ids


def _density_weights(model: dict[str, Any]) -> np.ndarray:
    """How much likelier a massive star's remnant is in each cell (flat,
    GRID × GRID), 1 on average over the systems: where stars form — the
    arms' contrast against their surroundings, unsharpened — and toward the
    centre, where far more massive stars have lived (e^(−r/MASSIVE_RADIUS))."""
    converter, cell = _converter(), DRAWING / GRID
    rows, cols = np.mgrid[0:GRID, 0:GRID]
    gx, gy = converter.graphic_to_galactic((cols + 0.5) * cell, (rows + 0.5) * cell)
    light, around = _image(project.current().density)
    r = np.hypot(gx, gy)
    weight = np.where(r <= GALAXY_RADIUS, (light / around) * np.exp(-r / MASSIVE_RADIUS), 0.0)
    systems = arms() * (r <= GALAXY_RADIUS)                # where the systems are, relatively
    return (weight / ((weight * systems).sum() / systems.sum())).ravel()


def _kind(model: dict[str, Any], pid: str, weight: float) -> Optional[str]:
    """What a system's primary is: a remnant's type, or None for a star —
    from its id, apart from its other draws, so a star stays the star it was."""
    u = random.Random(f"{model['seed']}:{pid}:kind").random()
    for kind, rate in REMNANT_RATES.items():
        u -= rate * (weight if kind in BORN_MASSIVE else 1.0)
        if u < 0:
            return kind
    return None


def _rim(model: dict[str, Any], gx: np.ndarray, gy: np.ndarray) -> np.ndarray:
    """How much of the density a place keeps toward the rim: all of it
    inside, thinning beyond a rim that wanders round the disc — a few
    waves, their phases seeded — so the edge frays."""
    rng = np.random.default_rng([model["seed"], 7])
    theta = np.arctan2(gy, gx)
    wave = sum(np.sin(k * theta + rng.uniform(0, 2 * np.pi)) / k for k in (2, 3, 5, 7))
    wave /= np.abs(wave).max() or 1
    beyond = np.hypot(gx, gy) - (RIM + RIM_WANDER * wave)
    return np.exp(-np.clip(beyond, 0, None) / RIM_FALLOFF)


# ── the light: the band in every system's sky ────────────────────────────────

GLOW_CELLS = 160                # a side of the light map: 625 ly cells over the disc


def glow(model: dict[str, Any]) -> dict[str, Any]:
    """The galaxy's light, for the band in a system's sky (space/sky.js
    works it out from where the system stands): the systems' density on the
    plane, as the layer draws them (`_places`), smoothed onto GLOW_CELLS ×
    GLOW_CELLS cells across the disc — row by row in y, from −GALAXY_RADIUS,
    each 0–999 of `scale` systems per ly² — and how they lie in height: a
    normal spread round `mean`, `sigma` wide (ly), both times
    1 + bulge·e^(−(r/bulge_radius)²). No system in it, only light."""
    converter, cell = _converter(), DRAWING / GRID
    rows, cols = np.mgrid[0:GRID, 0:GRID]
    gx, gy = converter.graphic_to_galactic((cols + 0.5) * cell, (rows + 0.5) * cell)
    sol = model["sol"]
    near = np.hypot(gx - sol[0], gy - sol[1]) <= NEIGHBOURHOOD
    relative = arms()
    surface = model["density"] * relative / relative[near].mean() * _rim(model, gx, gy)
    surface = np.where(np.hypot(gx, gy) <= GALAXY_RADIUS, surface, 0.0)
    step = 2 * GALAXY_RADIUS / GLOW_CELLS
    centres = -GALAXY_RADIUS + (np.arange(GLOW_CELLS) + 0.5) * step
    x, y = np.meshgrid(centres, centres)
    px, py = converter.galactic_to_graphic(x, y)
    from scipy.ndimage import map_coordinates
    smooth = gaussian_filter(surface, step * _px_per_ly() / cell / 2)
    light = np.clip(map_coordinates(smooth, [py / cell - 0.5, px / cell - 0.5], order=1, cval=0.0), 0, None)
    top = float(light.max()) or 1.0
    heights = np.asarray(model["heights"], dtype=float)
    return {
        "about": "The procedural galaxy's light, for the band in the skies (galaxy.procedural.glow). "
                 "No systems, only their smoothed density.",
        "radius": GALAXY_RADIUS, "cells": GLOW_CELLS, "scale": top / 999,
        "density": [int(v) for v in np.rint(light / top * 999).ravel()],
        "height": {"mean": round(float(heights.mean()), 1),
                   "sigma": round(float(math.hypot(heights.std(), HEIGHT_SPREAD)), 1),
                   "bulge": BULGE, "bulge_radius": BULGE_RADIUS},
    }


def _id(number: int) -> str:
    """A system's id: its cell and its place in it, "c123456-0"."""
    return f"c{number // 128:06d}-{number % 128}"


# ── the layer: every system as a dot ─────────────────────────────────────────

def layer(model: dict[str, Any], doc: dict[str, Any], within: Optional[float] = None) -> list[dict[str, Any]]:
    """Every procedural system as the maps show it from afar: id, name,
    place, primary class — or a remnant's `object_type` instead — planet
    count and absolute magnitude. One fewer for each authored system,
    near it (`_carve`); none promoted (`procedural` in `doc`)."""
    places, numbers = _places(model, within)
    free = _carve(model, places, _story(doc))
    places, numbers = places[free], numbers[free]
    promoted = {s["procedural"] for s in doc.get("star_systems") or [] if s.get("procedural")}
    taken = {t.casefold() for t in _taken(doc)}
    weights = _density_weights(model)
    dots = []
    for (x, y, z), number in zip(places, numbers):
        pid = _id(int(number))
        if pid in promoted:
            continue
        rng = random.Random(f"{model['seed']}:{pid}")
        cls = rng.choice(model["classes"])
        planets = rng.choice(model["planet_counts"])
        dot = {"id": pid, "name": _name(random.Random(f"{model['seed']}:{pid}:name"), taken, taken),
               "x": round(float(x), 3), "y": round(float(y), 3), "z": round(float(z), 3)}
        kind = _kind(model, pid, float(weights[int(number) // 128]))
        if kind:
            # A remnant: no MK class; its planets only now and then.
            keep = random.Random(f"{model['seed']}:{pid}:kept").random() < REMNANT_PLANETS
            dot |= {"object_type": kind, "planet_count": planets if keep else 0,
                    "abs_mag": magnitude(None, kind)}
        else:
            # How bright it shines, for the system maps' skies (galaxy.systemmap).
            dot |= {"spectral_class": cls, "planet_count": planets, "abs_mag": magnitude(cls)}
        dots.append(dot)
    return dots


def _carve(model: dict[str, Any], places: np.ndarray, story: list[dict[str, Any]]) -> np.ndarray:
    """Which places stay: each authored system takes the place of one — the
    nearest in the plane still there, within twice `exclusion` (authored systems count toward the density). In name order, so
    the same each time; an authored system added takes one near it, and at most
    a few round it move to their next nearest."""
    free = np.ones(len(places), dtype=bool)
    if not len(places) or not story:
        return free
    tree = cKDTree(places[:, :2])
    reach = 2 * exclusion(model)
    for s in sorted(story, key=lambda s: s["name"]):
        distance, index = tree.query([s["x"], s["y"]], k=min(16, len(places)), distance_upper_bound=reach)
        for d, i in zip(np.atleast_1d(distance), np.atleast_1d(index)):
            if np.isfinite(d) and free[i]:
                free[i] = False
                break
    return free


@lru_cache(maxsize=256)
def magnitude(spectral_class: Optional[str], object_type: Optional[str] = None) -> Optional[float]:
    """A primary of the class's (or the remnant's) absolute visual
    magnitude, as the system maps' skies take it
    (galaxy.systemmap.absolute_magnitude); None where it shows no light."""
    from galaxy import systemmap
    return systemmap.absolute_magnitude({"spectral_class": spectral_class, "object_type": object_type})


def _taken(doc: dict[str, Any]) -> set[str]:
    """Every name the catalogue gives: systems, stars, planets, moons."""
    out = set()
    for s in doc.get("star_systems") or []:
        out.add(s.get("name") or "")
        out.update(st.get("name") or "" for st in s.get("stars") or [])
        for p in s.get("planets") or []:
            out.update(b.get("name") or "" for b in [p, *(p.get("moons") or [])])
    out.discard("")
    out.discard("?")
    return out


def taken_names(doc: dict[str, Any], dots: list[dict[str, Any]]) -> set[str]:
    """The names, casefolded, a system's bodies must not have: the
    catalogue's (`_taken`) and the layer's systems'."""
    return {t.casefold() for t in _taken(doc)} | {d["name"].casefold() for d in dots}


def _namer():
    """The project's name generator (`namer`), else the default (galaxy.names)."""
    return project.current().name_generator() or names.generate


def _name(rng: random.Random, taken: set[str], given: set[str]) -> str:
    """A name from the project's generator, new to `taken` and `given`
    (casefolded); it joins `given`. Refused (ValueError) when 200 tries find
    none."""
    for _ in range(200):
        try:
            name = _namer()(rng)
        except RuntimeError:
            continue
        if name.casefold() not in taken and name.casefold() not in given:
            given.add(name.casefold())
            return name
    raise ValueError("The name generator found no new name")


# ── one system, whole ─────────────────────────────────────────────────────────

def details(model: dict[str, Any], dot: dict[str, Any], dots: list[dict[str, Any]],
            doc: dict[str, Any], taken: Optional[set[str]] = None) -> dict[str, Any]:
    """The system at `dot`, as galaxy.json holds one, with `procedural` its
    id: stars, planets with orbits, classes, sizes, moons, rings — the same
    each time. Its bodies' names are new to the catalogue and the layer:
    `taken` where the caller made it once for many (`taken_names`)."""
    rng = random.Random(f"{model['seed']}:{dot['id']}:details")
    fixed = taken if taken is not None else taken_names(doc, dots)
    given: set[str] = set()
    cls = dot.get("spectral_class")
    system: dict[str, Any] = {"name": dot["name"], "x": dot["x"], "y": dot["y"], "z": dot["z"],
                              "coordinate_system": "galactic"}
    if dot.get("object_type"):
        system["object_type"] = dot["object_type"]          # a remnant: no MK class
    else:
        system["spectral_class"] = cls
    system["procedural"] = dot["id"]
    if dot["planet_count"]:
        system["planets"] = [{"name": _name(rng, fixed, given)} for _ in range(dot["planet_count"])]
    if rng.random() < model["companion_share"] and not dot.get("object_type"):
        system["stars"] = [{"name": dot["name"], "spectral_class": cls}, {"name": _name(rng, fixed, given)}]
        orbits.draw_arrangement(system, rng)
    else:
        orbits.draw_system(system, rng)
    one = {"star_systems": [system]}
    for planet in system.get("planets") or []:
        planet["class"] = _planet_class(system, planet, rng)
    bodies.fill(one)
    for planet in system.get("planets") or []:
        _moons_and_rings(system, planet, rng, lambda: _name(rng, fixed, given))
    schema.normalise(one)
    bodies.fill(one)
    for planet in system.get("planets") or []:
        orbits.draw_moons(system, planet, rng)
    return system


def _moons_and_rings(system: dict[str, Any], planet: dict[str, Any], rng: random.Random, name) -> None:
    """Give `planet` moons, as many as its class has now and then, each named
    by `name()` and classed; and a gas giant rings, now and then."""
    moons = rng.choice(MOONS.get(planet["class"], ROCKY_MOONS))
    if moons:
        planet["moons"] = [{"name": name(), "class": orbits.draw_class(system, planet, moon=True, rng=rng)}
                           for _ in range(moons)]
    if planet["class"].startswith("gas-giant") and rng.random() < RING_SHARE:
        planet["rings"] = _rings(rng)


def fill_in(system: dict[str, Any], model: dict[str, Any], rng: Optional[random.Random] = None) -> None:
    """Fill in what `system` lacks, keeping what it has: the
    primary's class as the authored systems have theirs (not a real star's or a
    remnant's), companions' classes from the primary's mass; planets as many
    as the authored systems have, where it has none; then the missing orbits,
    tilts, planet and moon classes (never clashing with the order), radii.
    Moons and rings only for planets that lacked their class or orbit — new
    ones: no moons may be on purpose (Mercury) — and belts only where the
    planets are new altogether."""
    from galaxy import stars as star_data
    rng = rng or random.Random()
    one = {"star_systems": [system]}
    stars_ = system.get("stars") or []
    if (system.get("object_type") or "star") == "star" and not brightstars.is_real(system) \
            and not (stars_[0].get("spectral_class") if stars_ else system.get("spectral_class")):
        cls = rng.choice(model["classes"])
        if stars_:
            stars_[0]["spectral_class"] = cls
        system["spectral_class"] = cls
    main = star_data.primary(system)
    for companion in stars_[1:]:
        if main is not None and not companion.get("spectral_class"):
            companion["spectral_class"] = star_data.draw_companion_class(main, rng)
    created = not system.get("planets")
    if created:
        system["planets"] = [{"name": "?"} for _ in range(rng.choice([n for n in model["planet_counts"] if n] or [1]))]
        schema.normalise(one)
    new = [p for p in system["planets"] if not p.get("class") or not (p.get("orbit") or {}).get("au")]
    orbits.draw_system(system, rng)
    for planet in system["planets"]:
        if not planet.get("class"):
            planet["class"] = _planet_class(system, planet, rng)
        for moon in planet.get("moons") or []:
            if not moon.get("class"):
                moon["class"] = orbits.draw_class(system, planet, moon=True, rng=rng)
    bodies.fill(one)
    for planet in new:
        if not planet.get("moons") and not planet.get("rings"):
            _moons_and_rings(system, planet, rng, lambda: "?")
    schema.normalise(one)
    bodies.fill(one)
    for planet in new:
        orbits.draw_moons(system, planet, rng)
    if created and not system.get("belts"):
        orbits.draw_belts(system, rng)


# ── nebulae ──────────────────────
# Star-forming regions along the arms — where the Spitzer image is brightest,
# thin in height — each with now and then a dark cloud on its arm's inner
# side (toward the centre) and a reflection nebula beside it; a supernova
# remnant round some of the layer's neutron stars and pulsars, a planetary
# nebula round a few of its white dwarfs. Counts for a map that reads, not the
# Milky Way's thousands. None of the clouds within KNOWN_SKY of Sol, where the
# real sky's stand (galaxy.nebulae.real).

EMISSION_REGIONS = 400
DARK_SHARE = 0.5                # of the emission regions, a dark cloud beside each
REFLECTION_SHARE = 0.2
REMNANT_SHARE = 0.3             # of the neutron stars and pulsars
PLANETARY_SHARE = 0.01          # of the white dwarfs
KNOWN_SKY = 3_000               # ly round Sol
NEBULA_HEIGHT = 60              # ly: star-forming regions keep to the plane
SUFFIX = {"emission": "Nebula", "reflection": "Nebula", "dark": "Cloud", "remnant": "Remnant",
          "planetary": "Nebula"}


def nebulae(model: dict[str, Any], doc: dict[str, Any], dots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The layer's nebulae over `doc`, the same each time from the seed: as
    galaxy.json holds a nebula (galaxy.nebulae), with `procedural` its id and,
    round a system of the layer, `heart` its name and `procedural_heart` its id."""
    rng = np.random.default_rng(model["seed"] * 1_000_003 + 17)
    taken, given = taken_names(doc, dots), set()
    converter, cell = _converter(), DRAWING / GRID
    rows, cols = np.mgrid[0:GRID, 0:GRID]
    gx, gy = converter.graphic_to_galactic((cols + 0.5) * cell, (rows + 0.5) * cell)
    sol = model["sol"]
    weight = (arms() ** 2) * _rim(model, gx, gy)
    weight[(np.hypot(gx, gy) > GALAXY_RADIUS) | (np.hypot(gx - sol[0], gy - sol[1]) <= KNOWN_SKY)] = 0
    flat = weight.ravel() / weight.sum()
    cells = rng.choice(flat.size, size=EMISSION_REGIONS, p=flat)
    px = (cells % GRID + rng.random(EMISSION_REGIONS)) * cell
    py = (cells // GRID + rng.random(EMISSION_REGIONS)) * cell
    xs, ys = converter.graphic_to_galactic(px, py)
    out: list[dict[str, Any]] = []

    # Each drawn by its own generator — an emission region by its number, a
    # shell by its system's id — so taking a system away (a promotion)
    # changes no other nebula; ids as stable (pn12, pn12-dark, pr-<id>).
    def add(gen: random.Random, pid: str, kind: str, x: float, y: float, z: float, radius: float, **more: Any) -> None:
        flat_ = (gen.uniform(0.55, 1.0), gen.uniform(0.55, 1.0))
        out.append({"name": f"{_name(gen, taken, given)} {SUFFIX[kind]}", "kind": kind,
                    "x": round(float(x), 1), "y": round(float(y), 1), "z": round(float(z), 1),
                    "size": [round(float(radius), 2), round(float(radius * flat_[0]), 2), round(float(radius * flat_[1]), 2)],
                    "tilt": [0, 0, round(gen.uniform(0, 180))], "procedural": pid, **more})

    for k, (x, y) in enumerate(zip(xs, ys), start=1):
        gen = random.Random(f"{model['seed']}:nebula:{k}")
        thick = 1 + BULGE * math.exp(-(math.hypot(x, y) / BULGE_RADIUS) ** 2)
        z = max(-schema.COORDINATE_LIMITS["z"], min(schema.COORDINATE_LIMITS["z"], gen.gauss(0, NEBULA_HEIGHT) * thick))
        radius = min(120.0, max(6.0, gen.lognormvariate(math.log(25), 0.6)))
        add(gen, f"pn{k}", "emission", x, y, z, radius)
        r = math.hypot(x, y) or 1.0
        if gen.random() < DARK_SHARE:
            # On the arm's inner side: toward the centre, by about its size.
            step = radius * gen.uniform(1.0, 1.6)
            add(gen, f"pn{k}-dark", "dark", x - x / r * step, y - y / r * step, z, radius * gen.uniform(0.4, 0.8))
        if gen.random() < REFLECTION_SHARE:
            a = gen.uniform(0, 2 * math.pi)
            add(gen, f"pn{k}-reflection", "reflection", x + math.cos(a) * radius * 1.5, y + math.sin(a) * radius * 1.5, z,
                radius * gen.uniform(0.15, 0.35))
    for dot in dots:
        kind = dot.get("object_type")
        if kind not in ("pulsar", "neutron_star", "white_dwarf"):
            continue
        gen = random.Random(f"{model['seed']}:{dot['id']}:nebula")
        heart = {"heart": dot["name"], "procedural_heart": dot["id"]}
        if kind != "white_dwarf" and gen.random() < REMNANT_SHARE:
            add(gen, f"pr-{dot['id']}", "remnant", dot["x"], dot["y"], dot["z"], gen.uniform(8, 60), **heart)
        elif kind == "white_dwarf" and gen.random() < PLANETARY_SHARE:
            add(gen, f"pp-{dot['id']}", "planetary", dot["x"], dot["y"], dot["z"], gen.uniform(0.3, 1.5), **heart)
    return out


def _planet_class(system: dict[str, Any], planet: dict[str, Any], rng: random.Random) -> str:
    """As an editor's 🎲 draws one; and now and then, in the habitable zone,
    a habitable world — which the 🎲 leaves to the author."""
    host = star(system.get("spectral_class"), system.get("object_type"))
    au = (planet.get("orbit") or {}).get("au")
    if host and au and not planet.get("host"):
        low, high = orbits.zone("terrestrial-habitable", host)
        if low <= au <= high and rng.random() < HABITABLE_SHARE:
            return "terrestrial-habitable"
    return orbits.draw_class(system, planet, rng=rng)


def _rings(rng: random.Random) -> list[dict[str, float]]:
    """One or two bands, in planet radii, as Saturn's and Jupiter's are."""
    inner = round(rng.uniform(1.2, 1.8), 2)
    outer = round(inner + rng.uniform(0.2, 0.9), 2)
    bands = [{"inner": inner, "outer": outer, "density": bodies.draw_ring_density(rng)}]
    if rng.random() < 0.4:
        start = round(outer + rng.uniform(0.05, 0.2), 2)
        bands.append({"inner": start, "outer": round(start + rng.uniform(0.1, 0.5), 2),
                      "density": bodies.draw_ring_density(rng)})
    return bands


def gates(dots: list[dict[str, Any]], doc: dict[str, Any], settings: Optional[dict[str, Any]] = None,
          field: Optional[dict[str, Any]] = None) -> list[dict[str, str]]:
    """The gate network the rules give over the authored systems and the
    layer's together: shown with the layer on, authored
    links rerouted where a procedural system lies on their way. A pair
    the catalogue blocks stays out, a stored link keeps its grade. The
    stored network and the planner stay the authored systems' (galaxy.gatenet)."""
    return graded(pairs(dots, doc, settings, field), doc)


def pairs(dots: list[dict[str, Any]], doc: dict[str, Any], settings: Optional[dict[str, Any]] = None,
          field: Optional[dict[str, Any]] = None) -> list[tuple[str, str]]:
    """The pairs the rules link over the authored systems and the layer's
    together, whatever the catalogue blocks or grades: the costly part of
    `gates`, which only the systems' places change."""
    from galaxy import gatenet, medium, travel
    settings, field = settings or travel.load(), field or medium.load()
    where = gatenet._story(doc) | {d["name"]: (d["x"], d["y"], d["z"]) for d in dots}
    grid = medium.grid(field, medium.places(doc), None)
    return gatenet.network(where, grid, travel.gate_range(settings),
                           settings["gates"]["network"]["pass_by_share"])


def graded(linked: list[tuple[str, str]], doc: dict[str, Any]) -> list[dict[str, str]]:
    """The links of `linked` the catalogue does not block, a stored link's
    grade kept."""
    blocked = {frozenset((p["from"], p["to"])) for p in doc.get("gate_blocked") or []}
    grade = {frozenset((l["from"], l["to"])): l.get("grade") for l in doc.get("gate_links") or []}
    out = []
    for a, b in linked:
        pair = frozenset((a, b))
        if pair in blocked:
            continue
        link = {"from": a, "to": b}
        if grade.get(pair):
            link["grade"] = grade[pair]
        out.append(link)
    return out


def bundle(out: Path, doc: dict[str, Any], model: Optional[dict[str, Any]] = None,
           within: Optional[float] = None) -> dict[str, int]:
    """Write what the maps load into `out` (a directory, its procedural files
    replaced): procedural.json (the dots, and the layer's nebulae), procedural-gates.json (the network
    over both), procedural/<group>.json (the systems of a block of cells as
    the system map draws them, galaxy.systemmap, by id — fetched when one is
    opened; one file each would be 30,000). How many of each."""
    import shutil
    from galaxy import systemmap
    model = model or load()
    dots = layer(model, doc, within)
    links = gates(dots, doc)
    out.mkdir(parents=True, exist_ok=True)
    one = out / "procedural"
    if one.exists():
        shutil.rmtree(one)
    one.mkdir()

    def dump(path: Path, data: Any) -> None:
        path.write_text(json.dumps(_compact(data), ensure_ascii=False, separators=(",", ":")) + "\n",
                        encoding="utf-8")

    # The layer's nebulae beside its systems.
    dump(out / "procedural.json", {"systems": dots, "nebulae": nebulae(model, doc, dots)})
    dump(out / "procedural-gates.json", {"links": links})
    groups: dict[str, dict[str, Any]] = {}
    taken = taken_names(doc, dots)
    for dot in dots:
        groups.setdefault(group(dot["id"]), {})[dot["id"]] = systemmap.system(
            details(model, dot, dots, doc, taken))
    for name, systems in groups.items():
        dump(one / f"{name}.json", systems)
    return {"systems": len(dots), "links": len(links), "files": len(groups)}


def _compact(value: Any) -> Any:
    """Floats to six significant digits — enough to draw by, and half the
    size of the details at full precision."""
    if isinstance(value, float):
        return float(f"{value:.6g}")
    if isinstance(value, dict):
        return {k: _compact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_compact(v) for v in value]
    return value


GROUP = 10          # cells a side: the systems of GROUP × GROUP cells share one details file


def group(pid: str) -> str:
    """The details file a system is in: "c123456-0" → "1756" (row and column
    of its block of cells). The maps work it out the same way."""
    cell = int(pid[1:pid.index("-")])
    return f"{cell // GRID // GROUP:02d}{cell % GRID // GROUP:02d}"


def nearest_spacing(systems: list[dict[str, Any]]) -> float:
    """The median distance from a system to its nearest neighbour, in light
    years: how dense."""
    at = np.asarray([[s["x"], s["y"], s["z"]] for s in systems])
    return float(np.median(cKDTree(at).query(at, k=2)[0][:, 1])) if len(at) > 1 else math.inf
