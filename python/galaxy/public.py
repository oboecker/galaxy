"""The public maps site's data.

A public site shows only what is chosen field by field from an allowed
list, not by taking out what is known to be private — a field added to
galaxy.json later stays out until it is added here. Public: the systems,
their stars, planets, moons, rings, belts and points of interest with their
names, classes, orbits and sizes; the gate links; the region labels and
sector names; the planet maps as globe textures and height maps. Not public:
trips, nation territories, anything only an editor uses.

`bundle(out)` writes it all into a fresh directory:

    galaxy.json            the allowed fields of the whole catalogue, the layers merged
    layers/<name>.json     each layer (real-sky, then the project's), the same fields: a switch each on the map,
    layers/index.json      listed (galaxy.catalogue.layer_index)
    systems.json           what the system maps draw (systemmap.export of it)
    glow.json              the galaxy's light, for the band in their skies
                           (galaxy.procedural.glow: no systems in it)
    travel-settings.json   travel.json's `maps` — colours, the gate overlay
    planets/               the planet maps' textures and height maps, with
                           index.json and heights.json naming them
"""

from __future__ import annotations

import copy
import json
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from galaxy import catalogue, project, systemmap

ORBIT = {"au": None, "km": None, "e": None, "i": None, "node": None, "periapsis": None, "anomaly": None}
BODY = {"name": None, "id": None, "index": None, "class": None, "radius": None, "look": None, "tilt": None,
        "tilt_bearing": None, "host": None, "dwarf": None, "orbit": ORBIT}
MOON = {k: v for k, v in BODY.items() if k not in ("host", "dwarf")}

# The allowed fields, path by path: None takes a value as it is (a number,
# a name, a class); a dict a record's allowed fields; a one-item list each
# entry of a list by its item's spec.
GALAXY = {
    "star_systems": [{
        "name": None, "x": None, "y": None, "z": None, "coordinate_system": None, "spectral_class": None,
        "planet_count": None, "plane": {"i": None, "node": None, "zero": None},
        "stars": [{"name": None, "spectral_class": None, "hip": None, "host": None, "orbit": ORBIT}],
        "planets": [{**BODY, "rings": [{"inner": None, "outer": None, "density": None}], "moons": [MOON]}],
        "belts": [{"name": None, "id": None, "inner": None, "outer": None, "host": None}],
        "points_of_interest": [{"name": None, "id": None, "kind": None,
                                "anchor": {"body": None, "au": None, "km": None, "point": None, "host": None}}],
    }],
    "gate_links": [{"from": None, "to": None}],
    # Nebulae, public as the rest: the maps site draws them.
    "nebulae": [{"id": None, "name": None, "kind": None, "x": None, "y": None, "z": None, "size": [None],
                 "tilt": [None], "density": None, "colour": None, "real": None, "heart": None}],
    "labels": [{"label": None, "x": None, "y": None, "rotation": None}],
    "sector_names": "names",            # a map of sector id to name: both are names
}

# travel.json's settings for drawing, without its notes: numbers and
# colours only ("settings"), at any depth — no text gets through.
TRAVEL_MAPS = {"route_colours": "settings", "stream": "settings", "route_opacity": "settings",
               "stop_pixels": None, "drive_share_min": "settings", "gate_overlay": "settings"}
# What the maps learn of a travel mode: its kind, label, leg kind, and where it starts.
TRAVEL_MODE = ("kind", "label", "leg", "from_point")
COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}")


def allowed(value: Any, spec: Any) -> Any:
    """`value` with only what `spec` allows: a record or list where the spec
    takes a plain value is dropped, as is text that is not a colour in
    "settings". Refused (ValueError) for a spec it does not know."""
    if spec is None:
        if isinstance(value, (dict, list)):
            # A value taken as it is must be one: a record or list here was not
            # allowed for, and is dropped rather than passed on whole.
            return None
        return value
    if spec == "names":
        return {str(k): v for k, v in value.items() if isinstance(v, str)} if isinstance(value, dict) else None
    if spec == "settings":
        if isinstance(value, dict):
            kept = {str(k): allowed(v, "settings") for k, v in value.items()}
            return {k: v for k, v in kept.items() if v is not None}
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return None
        return value if not isinstance(value, str) or COLOUR.fullmatch(value) else None
    if isinstance(spec, list):
        return [allowed(item, spec[0]) for item in value] if isinstance(value, list) else None
    if isinstance(spec, dict):
        if not isinstance(value, dict):
            return None
        out = {}
        for key, sub in spec.items():
            if key in value:
                kept = allowed(value[key], sub)
                if kept is not None:
                    out[key] = kept
        return out
    raise ValueError(f"unknown spec {spec!r}")


def galaxy(doc: dict[str, Any]) -> dict[str, Any]:
    """galaxy.json with only the fields GALAXY lets through to the public site."""
    return allowed(doc, GALAXY)


def travel_settings(doc: dict[str, Any]) -> dict[str, Any]:
    """travel.json's drawing settings (`maps`) with only what TRAVEL_MAPS
    allows, its modes as the maps name them (TRAVEL_MODE: no numbers), and
    the sublight drive's top thrust."""
    from galaxy import travel
    out = {"maps": allowed(doc.get("maps") or {}, TRAVEL_MAPS),
           "modes": {name: {k: v for k, v in mode.items() if k in TRAVEL_MODE}
                     for name, mode in travel.modes(doc).items()}}
    # The sublight drive's top thrust, the system map's thrust slider's end.
    if (doc.get("sublight") or {}).get("g") is not None:
        out["sublight"] = {"g": doc["sublight"]["g"]}
    return out


def bundle(out: Path, *, galaxy_json: Optional[Path] = None, travel_json: Optional[Path] = None,
           planets: Optional[Path] = None, with_procedural: bool = True,
           procedural_within: Optional[float] = None) -> list[Path]:
    """Write the site's data into `out`, emptied first. The files written.
    `planets` is where the build put the planet maps' textures (they are
    rendered, not committed); a planet in neither galaxy.json nor there is
    left out. The procedural galaxy with it, unless `with_procedural` is
    False; only within `procedural_within` ly of Sol if given (the test's
    quick look at what it publishes)."""
    here = project.current()
    travel_json = travel_json or here.travel
    planets = planets or here.public_planets
    if out.exists():
        shutil.rmtree(out)
    (out / "planets" / "height").mkdir(parents=True)
    whole = catalogue.read(here, galaxy_json)
    doc = galaxy(copy.deepcopy(whole))
    written = []

    def dump(name: str, data: Any) -> None:
        path = out / name
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        written.append(path)

    dump("galaxy.json", doc)
    # Each layer beside it, a switch each on the galaxy map: a system is in
    # every layer that names it (Sol in the project's as well as the real sky's).
    written += catalogue.write_layers(out / "layers", here, transform=galaxy, last=galaxy_json)
    dump("systems.json", systemmap.export(doc))
    # The skies' nebulae, beside systems.json as a site has them.
    dump("nebulae.json", systemmap.sky_nebulae(doc))
    from galaxy import procedural
    dump("glow.json", procedural.glow(procedural.load()))
    # The procedural galaxy (galaxy.procedural): drawn from the whole catalogue
    # (its authored systems take their places, its names are not reused), but it
    # writes only its own systems and the gate network's names, which the
    # public galaxy.json has already.
    if with_procedural:
        procedural.bundle(out, whole, within=procedural_within)
        written += [out / "procedural.json", out / "procedural-gates.json"]
        written += sorted((out / "procedural").glob("*.json"))
    dump("travel-settings.json", travel_settings(json.loads(travel_json.read_text(encoding="utf-8"))))

    # The planet maps: only those of planets in the public galaxy, by name.
    names = {p.get("name") for s in doc["star_systems"] for p in s.get("planets") or []}
    names |= {m.get("name") for s in doc["star_systems"] for p in s.get("planets") or [] for m in p.get("moons") or []}
    textures, heights = {}, {}
    for manifest, kept, sub in (("index.json", textures, ""), ("heights.json", heights, "height/")):
        source = planets / manifest
        listed = json.loads(source.read_text(encoding="utf-8")) if source.is_file() else {}
        for name, url in listed.items():
            file = planets / sub / Path(url).name
            if name in names and file.is_file():
                shutil.copy2(file, out / "planets" / sub / file.name)
                written.append(out / "planets" / sub / file.name)
                kept[name] = f"planets/{sub}{file.name}"        # relative: the site lives under a path
    dump("planets/index.json", textures)
    dump("planets/heights.json", heights)
    return written
