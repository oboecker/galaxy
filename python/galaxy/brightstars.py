"""The real sky's bright stars as systems of galaxy.json: every star of the HYG
catalogue down to magnitude 3.5 — the stars that draw the constellations —
with Alpha Centauri's Proxima, placed by galaxy.celestial.

The list is data/bright-stars.csv, taken once from the HYG catalogue (v1,
astronexus.com, CC BY-SA) by cli/bright_stars.py; `add` puts what galaxy.json
lacks of it into a document.

    brightstars.add(doc)   → ["Sirius", "Canopus", …], the systems added
"""

from __future__ import annotations

import csv
import io
import math
import re
from functools import cache
from importlib import resources
from typing import Any, Iterable

from galaxy import celestial

MAGNITUDE = 3.5             # the faintest taken: the constellations' figures
DATA = "data/bright-stars.csv"
FIELDS = ("system", "star", "designation", "hip", "ra", "dec", "ly", "mag", "spectral_class")

# A star that belongs to a system without being bright: Alpha Centauri's third.
EXTRA = {70890: ("Alpha Centauri", "Proxima Centauri")}
# Names the catalogue has otherwise than the IAU (WGSN, 2016–).
NAMES = {"Rigel Kentaurus A": ("Alpha Centauri", "Rigil Kentaurus"),
         "Rigel Kentaurus B": ("Alpha Centauri", "Toliman")}
# Companions' real orbits, where known (around their system's primary, or
# `host`): Alpha Centauri B — 79.91 years, periastron AD 1955.56 — and
# Proxima round the pair, near its farthest now. The mean anomaly at the
# epoch (galaxy.orbits.epoch_year()).
ORBITS = {
    "Toliman": {"orbit": {"au": 23.52, "e": 0.518, "i": 0.0, "node": 0.0, "periapsis": 0.0, "anomaly": 122.4}},
    "Proxima Centauri": {"host": "Rigil Kentaurus+Toliman",
                         "orbit": {"au": 8700.0, "e": 0.5, "i": 0.0, "node": 0.0, "periapsis": 0.0, "anomaly": 180.0}},
}
# Where the catalogue's spectrum is wrong: Capella is two yellow giants.
CLASSES = {24608: "G8III"}
CLOSE = 1.0                 # light years: stars closer than this are one system

GREEK = {"Alp": "Alpha", "Bet": "Beta", "Gam": "Gamma", "Del": "Delta", "Eps": "Epsilon", "Zet": "Zeta",
         "Eta": "Eta", "The": "Theta", "Iot": "Iota", "Kap": "Kappa", "Lam": "Lambda", "Mu": "Mu", "Nu": "Nu",
         "Xi": "Xi", "Omi": "Omicron", "Pi": "Pi", "Rho": "Rho", "Sig": "Sigma", "Tau": "Tau", "Ups": "Upsilon",
         "Phi": "Phi", "Chi": "Chi", "Psi": "Psi", "Ome": "Omega"}
SUPERSCRIPT = str.maketrans("123456789", "¹²³⁴⁵⁶⁷⁸⁹")
_DESIGNATION = re.compile(r"^(\d*)([A-Z][a-z]{1,2})?(\d)?\s*([A-Z][A-Za-z]{2})$")
_SHAPE = re.compile(r"[OBAFGKM]\d(?:\.\d+)?(?:Iab|Ia|Ib|IV|V|III|II|I)?")


def designation(bayer_flamsteed: str) -> str:
    """HYG's '24Omi2CMa' as a name: Omicron² Canis Majoris; '61    Cyg' as
    61 Cygni; '' for none."""
    m = _DESIGNATION.match((bayer_flamsteed or "").strip())
    names = celestial.constellations()
    if not m or m.group(4) not in names:
        return ""
    number, greek, index, con = m.groups()
    genitive = names[con][1]
    if greek in GREEK:
        return f"{GREEK[greek]}{(index or '').translate(SUPERSCRIPT)} {genitive}"
    return f"{number} {genitive}" if number else ""


def spectral_class(spectrum: str) -> str:
    """The first MK class the catalogue's spectrum holds, as galaxy.json takes
    it: 'A0m...' → A0, 'F7:Ib-IIv SB' → F7Ib, 'WC8 + O9I' → O9I; '' for none."""
    m = _SHAPE.search((spectrum or "").replace(":", ""))
    return m.group(0) if m else ""


def extract(rows: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
    """The bright stars of HYG catalogue rows, each with its system's and its
    own name: brightest first, a fainter one within CLOSE of a brighter one
    its companion."""
    PARSEC = 3.26156
    stars = []
    for row in rows:
        hip = int(row["HIP"]) if row.get("HIP") and int(row["HIP"]) else None
        bright = row.get("Mag") and float(row["Mag"]) <= MAGNITUDE
        if row.get("ProperName") == "Sol" or not (bright or hip in EXTRA):
            continue
        cls = CLASSES.get(hip) or spectral_class(row.get("Spectrum", ""))
        name = ((row.get("ProperName") or "").strip() or designation(row.get("BayerFlamsteed", ""))
                or (f"HIP {hip}" if hip else ""))
        ra, dec, ly = float(row["RA"]) * 15, float(row["Dec"]), float(row["Distance"]) * PARSEC
        if not cls or ly > 50_000:          # no class to draw it by, or no distance worth the name
            continue
        system, star = NAMES.get(name, EXTRA.get(hip, (None, name)))
        stars.append({"system": system, "star": star, "designation": designation(row.get("BayerFlamsteed", "")),
                      "hip": hip, "ra": round(ra, 5), "dec": round(dec, 5),
                      "ly": round(ly, 2), "mag": float(row["Mag"]), "spectral_class": cls})
    stars.sort(key=lambda s: s["mag"])
    placed: list[tuple[tuple[float, float, float], dict[str, Any]]] = []
    for s in stars:
        at = celestial.to_frame(s["ra"], s["dec"], s["ly"])
        host = next((h for p, h in placed if math.dist(p, at) < CLOSE), None)
        if s["system"] is None:
            s["system"] = host["system"] if host else s["star"]
        if host and host["system"] == s["system"] and s["star"] in ("", host["star"]):
            s["star"] = f"{host['star']} B"        # a companion without a name of its own
        if s["system"]:
            placed.append((at, s))
    return [s for s in stars if s["system"]]


def write(stars: list[dict[str, Any]]) -> str:
    """`stars` as the DATA file's text: the catalogue's credit, then the CSV."""
    out = io.StringIO()
    out.write("# The bright stars (galaxy.brightstars): HYG catalogue v1, astronexus.com, CC BY-SA.\n")
    writer = csv.DictWriter(out, FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(stars)
    return out.getvalue()


def stars() -> list[dict[str, Any]]:
    """The bright stars as the DATA file lists them, the numbers parsed."""
    text = resources.files("galaxy").joinpath(DATA).read_text(encoding="utf-8")
    rows = csv.DictReader(line for line in text.splitlines() if not line.startswith("#"))
    return [{**r, "hip": int(r["hip"]) if r["hip"] else None, "ra": float(r["ra"]), "dec": float(r["dec"]), "ly": float(r["ly"]),
             "mag": float(r["mag"])} for r in rows]


@cache
def by_hip() -> dict[int, dict[str, Any]]:
    """The catalogue's stars by Hipparcos number."""
    return {s["hip"]: s for s in stars() if s["hip"]}


def systems() -> list[dict[str, Any]]:
    """The bright stars as galaxy.json's systems: at the brightest star's
    place, each star with its `hip` number."""
    out: dict[str, dict[str, Any]] = {}
    for s in stars():
        system = out.get(s["system"])
        if system is None:
            x, y, z = celestial.to_frame(s["ra"], s["dec"], s["ly"])
            # To a thousandth of a light year: Alpha Centauri's direction from
            # Sol to within a few arcminutes (a tenth was 1.4° off).
            system = out[s["system"]] = {"name": s["system"], "x": round(x, 3), "y": round(y, 3),
                                         "z": round(z, 3), "coordinate_system": "galactic",
                                         "spectral_class": s["spectral_class"], "stars": []}
        star = {"name": s["star"], "spectral_class": s["spectral_class"], **ORBITS.get(s["star"], {})}
        system["stars"].append({**star, "hip": s["hip"]} if s["hip"] else star)
    return list(out.values())


def is_real(system: dict[str, Any]) -> bool:
    """Whether `system` is one of the real sky's: one of its stars has a
    Hipparcos number. Its position is the sky's — an editor does not move it."""
    return any(star.get("hip") for star in system.get("stars") or [])


def lacking(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """The bright stars' systems the document lacks — known by a star's `hip`
    or the system's name."""
    have = doc.get("star_systems") or []
    names = {s.get("name") for s in have}
    hips = {star.get("hip") for s in have for star in s.get("stars") or []} - {None}
    return [s for s in systems() if s["name"] not in names and not any(star.get("hip") in hips for star in s["stars"])]


def _order(name: str):
    """The sort key of a system named `name` (service.system_order)."""
    from galaxy.service import system_order        # the order galaxy.json keeps
    return system_order(name)


def current(doc: dict[str, Any]) -> bool:
    """Whether the bright stars in the document are as the list has them:
    in the file's order (those added first were appended at the end) and
    where the catalogue puts them (to a thousandth of a light year, as
    `systems` rounds)."""
    keys = [_order(s.get("name") or "") for s in doc.get("star_systems") or []]
    where = {s["name"]: (s["x"], s["y"], s["z"]) for s in systems()}
    return keys == sorted(keys) and all((s.get("x"), s.get("y"), s.get("z")) == where[s["name"]]
                                        for s in doc.get("star_systems") or [] if s.get("name") in where and is_real(s))


def add(doc: dict[str, Any]) -> list[str]:
    """Put the bright stars' systems the document lacks into it, each where
    the file's order has it and with its plane drawn (galaxy.orbits.
    draw_plane); move those already in to their place in the list and to
    the catalogue's position. The names added."""
    from galaxy import orbits
    added = lacking(doc)
    for system in added:
        orbits.draw_plane(system)
    where = {s["name"]: s for s in systems()}
    listed = doc.setdefault("star_systems", [])
    for system in listed:
        if is_real(system) and system.get("name") in where:
            system.update({axis: where[system["name"]][axis] for axis in ("x", "y", "z")})
    real = [s for s in listed if is_real(s)] + added
    listed[:] = [s for s in listed if not is_real(s)]
    for system in real:
        key = _order(system["name"])
        at = next((i for i, s in enumerate(listed) if _order(s.get("name") or "") > key), len(listed))
        listed.insert(at, system)
    return [s["name"] for s in added]
