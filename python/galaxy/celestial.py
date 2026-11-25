"""The sky as seen from Earth, and galaxy.json's frame.

The frame is light years with the galactic centre at 0 and Sol at
(−513, 24 995, 50). Three facts tie it to the real sky — Sol and the centre
alone leave the turn about the line between them free:

- the north galactic pole (b = +90°) is +z: the map's plane is the galactic plane;
- l = 0° is Sol → centre, laid into that plane: (513, −24 995, 0);
- l = 90° is the way the galaxy turns, clockwise seen from +z (the map is
  drawn from the Spitzer image): +z × l0, about +x.

Anchored on Sol: a real star keeps its true distance from Sol; the frame's
25 000 ly to the centre (real ≈ 26 700) and Sol's 50 ly above the plane
(real ≈ 65) stay as they are, so nothing in galaxy.json moves.

    to_frame(279.23, 38.78, 25.0)   → Vega: (−491.0, 24 986.4, 58.2)
    to_sky(2077.3, 24789.4, 140.6)  → Sky(ra=310.4, dec=45.3, ly=2600, constellation='Cyg')
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cache
from typing import Optional
from importlib import resources

import numpy as np

SOL = np.array([-513.0, 24995.0, 50.0])

# ICRS (J2000 equator and equinox) → galactic, the Hipparcos matrix (ESA 1997,
# vol. 1, §1.5.3): rows are the galactic x (l 0°), y (l 90°), z (b 90°) axes.
_GALACTIC = np.array([[-0.0548755604, -0.8734370902, -0.4838350155],
                      [+0.4941094279, -0.4448296300, +0.7469822445],
                      [-0.8676661490, -0.1980763734, +0.4559837762]])


def _frame_axes() -> np.ndarray:
    """The galactic axes in the frame, as columns: l = 0° from Sol toward the
    centre in the plane, l = 90° the pole × that, b = 90° the frame's +z."""
    l0 = -SOL * np.array([1.0, 1.0, 0.0])
    l0 /= np.linalg.norm(l0)
    pole = np.array([0.0, 0.0, 1.0])
    return np.column_stack([l0, np.cross(pole, l0), pole])


# galactic → frame directions; ICRS → frame is the two together.
_AXES = _frame_axes()
_ICRS_TO_FRAME = _AXES @ _GALACTIC

# The J2000 obliquity of the ecliptic (IAU 2006), degrees.
OBLIQUITY = 23.439279


def _unit(ra: float, dec: float) -> np.ndarray:
    """The unit vector toward RA and Dec (degrees) in the equator's own axes."""
    r, d = math.radians(ra), math.radians(dec)
    return np.array([math.cos(d) * math.cos(r), math.cos(d) * math.sin(r), math.sin(d)])


def _angles(v: np.ndarray) -> tuple[float, float]:
    """RA and Dec in degrees of a direction."""
    v = v / np.linalg.norm(v)
    return math.degrees(math.atan2(v[1], v[0])) % 360, math.degrees(math.asin(max(-1.0, min(1.0, v[2]))))


def direction(ra: float, dec: float) -> np.ndarray:
    """The frame's unit vector toward a point of the sky (degrees, J2000)."""
    return _ICRS_TO_FRAME @ _unit(ra, dec)


def to_frame(ra: float, dec: float, ly: float) -> tuple[float, float, float]:
    """Where a star `ly` light years from Sol at (RA, Dec) — degrees, J2000 —
    stands in the frame."""
    x, y, z = SOL + ly * direction(ra, dec)
    return float(x), float(y), float(z)


@dataclass(frozen=True)
class Sky:
    """Where a point of the frame stands in Earth's sky."""
    ra: float               # degrees, J2000
    dec: float              # degrees
    ly: float               # from Sol
    constellation: str      # IAU abbreviation: Cyg

    @property
    def constellation_name(self) -> str:
        """The constellation's name, e.g. Cygnus."""
        return constellations()[self.constellation][0]

    def describe(self) -> str:
        """The place in words: `RA 20h 41m, Dec +45° 17′, in Cygnus`."""
        minutes = round(self.ra / 15 * 60) % (24 * 60)
        arc = round(abs(self.dec) * 60)
        return (f"RA {minutes // 60}h {minutes % 60:02d}m, Dec {'+' if self.dec >= 0 else '−'}{arc // 60}° "
                f"{arc % 60:02d}′, in {self.constellation_name}")


def to_sky(x: float, y: float, z: float) -> Sky:
    """A point of the frame as Earth sees it."""
    v = _ICRS_TO_FRAME.T @ (np.array([x, y, z], dtype=float) - SOL)
    ly = float(np.linalg.norm(v))
    if ly == 0:
        raise ValueError("Sol has no place in its own sky")
    ra, dec = _angles(v)
    return Sky(ra, dec, ly, constellation(ra, dec))


# ── constellations ────────────────────────────────────────────────────────────
# The Delporte boundaries of 1930, drawn along B1875's hours and degrees, as
# Roman 1987 tabulates them (CDS VI/42; data/constellation-boundaries.dat):
# rows from north to south, each a band from RA low to high (hours) above a
# declination; a point belongs to the first row it falls in.

@cache
def constellations() -> dict[str, tuple[str, str]]:
    """IAU abbreviation → (name, genitive)."""
    text = resources.files("galaxy").joinpath("data/constellations.tsv").read_text(encoding="utf-8")
    rows = [line.split("\t") for line in text.splitlines() if line and not line.startswith("#")]
    return {abbr: (name, genitive) for abbr, name, genitive in rows}


@cache
def _boundaries() -> list[tuple[float, float, float, str]]:
    """The boundary rows, north to south: (RA low, RA high in hours, the
    declination above which the band lies, the constellation)."""
    text = resources.files("galaxy").joinpath("data/constellation-boundaries.dat").read_text(encoding="utf-8")
    rows = [line.split() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    return [(float(low), float(high), float(dec), abbr) for low, high, dec, abbr in rows]


def _precession(t: float) -> np.ndarray:
    """J2000 → the mean equator and equinox `t` Julian centuries later (IAU
    1976, Lieske 1977)."""
    arcsec = math.pi / 180 / 3600
    zeta = (2306.2181 * t + 0.30188 * t ** 2 + 0.017998 * t ** 3) * arcsec
    z = (2306.2181 * t + 1.09468 * t ** 2 + 0.018203 * t ** 3) * arcsec
    theta = (2004.3109 * t - 0.42665 * t ** 2 - 0.041833 * t ** 3) * arcsec

    def rz(a):
        c, s = math.cos(a), math.sin(a)
        return np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])

    def ry(a):
        c, s = math.cos(a), math.sin(a)
        return np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])

    return rz(-z) @ ry(theta) @ rz(-zeta)


# B1875.0 (JD 2405889.2585505) from J2000.0, in Julian centuries.
_TO_B1875 = _precession((2405889.2585505 - 2451545.0) / 36525)


def constellation(ra: float, dec: float) -> str:
    """The IAU abbreviation of the constellation a J2000 position lies in."""
    ra75, dec75 = _angles(_TO_B1875 @ _unit(ra, dec))
    hours = ra75 / 15
    for low, high, lower, abbr in _boundaries():
        if dec75 >= lower and low <= hours < high:
            return abbr
    return "Oct"  # below every row: the south pole's own


# ── Sol's ecliptic ────────────────────────────────────────────────────────────

def plane_angles(pole: np.ndarray, zero: np.ndarray) -> dict[str, float]:
    """A system's reference plane in the frame, as an orbit's angles are:
    `i` its tilt to the galactic plane, `node` the frame longitude (from +x
    toward +y) where it rises through that plane, `zero` the angle in the
    plane from that node to the system's longitude 0°. Degrees."""
    pole = pole / np.linalg.norm(pole)
    i = math.degrees(math.acos(max(-1.0, min(1.0, pole[2]))))
    node = np.cross([0.0, 0.0, 1.0], pole)
    if np.linalg.norm(node) < 1e-12:      # in the galactic plane: the node is +x
        node = np.array([1.0, 0.0, 0.0])
    node /= np.linalg.norm(node)
    zero = zero - pole * (zero @ pole)
    turn = math.degrees(math.atan2(np.cross(node, zero) @ pole, node @ zero)) % 360
    return {"i": round(i, 3), "node": round(math.degrees(math.atan2(node[1], node[0])) % 360, 3),
            "zero": round(turn, 3)}


def plane_matrix(plane: dict[str, float]) -> np.ndarray:
    """The turn from a system's own axes (x its longitude 0°, z its pole)
    into the frame's, by plane_angles' three angles: Rz(node) Rx(i) Rz(zero)."""
    def rz(a):
        c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
        return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    c, s = math.cos(math.radians(plane["i"])), math.sin(math.radians(plane["i"]))
    return rz(plane["node"]) @ np.array([[1, 0, 0], [0, c, -s], [0, s, c]]) @ rz(plane["zero"])


def galaxy_from(system: dict) -> Optional[dict[str, list[float]]]:
    """How the galaxy lies in a system's own axes: the galactic pole and the
    direction to the centre, unit vectors — the sky's band in its map. None
    without a plane."""
    plane = system.get("plane")
    if not plane:
        return None
    back = plane_matrix(plane).T
    at = np.array([system.get("x", 0), system.get("y", 0), system.get("z", 0)], dtype=float)
    centre = -at / (np.linalg.norm(at) or 1)
    return {"pole": [round(float(v), 5) for v in back @ np.array([0.0, 0.0, 1.0])],
            "centre": [round(float(v), 5) for v in back @ centre]}


def ecliptic() -> dict[str, float]:
    """Sol's reference plane: the ecliptic, its 0° the March equinox."""
    eps = math.radians(OBLIQUITY)
    pole = _ICRS_TO_FRAME @ np.array([0.0, -math.sin(eps), math.cos(eps)])
    equinox = _ICRS_TO_FRAME @ np.array([1.0, 0.0, 0.0])
    return plane_angles(pole, equinox)
