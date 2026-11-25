"""What a star's spectral class says about it: mass, luminosity, temperature,
and the zones around it.

Values by luminosity class, interpolated in log space between anchors per
letter and subtype: the main sequence (V, and IV and VI with it), giants
(III), bright giants (II) and supergiants (Ib, Iab, Ia) — typical values,
the real stars vary widely around them. A hypergiant (Ia+, 0) gets the Ia
values and is marked approximate.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass
from typing import Any, Optional

# (spectral position, mass in suns, luminosity in suns, temperature K) for
# main-sequence stars; the position is letter index × 10 + subtype.
_LETTERS = "OBAFGKM"
_ANCHORS = (
    ("O5", 37.0, 3.2e5, 41_400),
    ("B0", 17.5, 3.2e4, 31_400),
    ("B5", 4.7, 540, 15_700),
    ("A0", 2.18, 40, 9_700),
    ("A5", 1.86, 13, 8_100),
    ("F0", 1.61, 5.0, 7_220),
    ("F5", 1.33, 2.9, 6_550),
    ("G0", 1.06, 1.3, 5_920),
    ("G2", 1.00, 1.0, 5_770),
    ("G5", 0.98, 0.80, 5_660),
    ("K0", 0.88, 0.46, 5_270),
    ("K5", 0.70, 0.16, 4_440),
    ("M0", 0.57, 0.069, 3_850),
    ("M5", 0.16, 0.0022, 3_060),
    ("M9", 0.08, 0.0003, 2_400),
)
# Giants and supergiants, (position, mass, luminosity, temperature) as above
# (after Straižys & Kuriliene 1981; Drilling & Landolt, Allen's
# Astrophysical Quantities, 2000).
_GIANTS = {
    "III": (("B0", 20.0, 5.5e4, 29_000), ("B5", 7.0, 1.1e3, 15_000), ("A0", 4.0, 100, 10_100),
            ("F0", 2.5, 30, 7_150), ("G0", 2.5, 35, 5_850), ("G5", 2.5, 50, 5_150), ("K0", 2.0, 60, 4_750),
            ("K5", 1.5, 400, 3_950), ("M0", 1.5, 600, 3_800), ("M5", 1.5, 2_000, 3_330)),
    "Ib": (("B0", 25.0, 2.6e5, 26_000), ("B5", 13.0, 4.0e4, 13_600), ("A0", 12.0, 3.5e4, 9_730),
           ("F0", 10.0, 1.5e4, 7_700), ("G0", 10.0, 1.0e4, 5_550), ("K0", 12.0, 1.5e4, 4_420),
           ("M0", 13.0, 4.0e4, 3_650), ("M5", 15.0, 1.0e5, 2_800)),
    "Ia": (("B0", 40.0, 5.0e5, 25_000), ("B5", 25.0, 2.0e5, 13_000), ("A0", 20.0, 1.5e5, 9_500),
           ("F0", 15.0, 1.0e5, 7_400), ("G0", 15.0, 8.0e4, 5_500), ("K0", 15.0, 8.0e4, 4_300),
           ("M0", 20.0, 1.5e5, 3_600), ("M5", 20.0, 2.0e5, 2_900)),
}
# Between two classes: the geometric mean of their rows, anchor by anchor.
_BETWEEN = {"II": ("III", "Ib"), "Iab": ("Ib", "Ia")}
_SAME = {"IV": "V", "VI": "V", "VII": "V", "I": "Iab", "Ia+": "Ia", "0": "Ia"}
_SUN_TEMPERATURE = 5_772

_CLASS = re.compile(r"^([OBAFGKM])(\d(?:\.\d+)?)?(Iab|Ia\+|Ia|Ib|VII|VI|IV|V|III|II|I|0)?[a-z:]*$")


def _position(letter: str, subtype: float) -> float:
    """A class's place on one scale, its letter's rank × 10 + subtype: G2 → 42."""
    return _LETTERS.index(letter) * 10 + subtype


def _table(anchors) -> list[tuple]:
    """Anchor rows ("G2", values, …) with the class turned into its position."""
    return [(_position(a[0][0], float(a[0][1:])), *a[1:]) for a in anchors]


def _at(table: list[tuple], pos: float) -> list[float]:
    """A table's row at a spectral position: log-interpolated, clamped at its ends."""
    if pos <= table[0][0]:
        return list(table[0][1:])
    if pos >= table[-1][0]:
        return list(table[-1][1:])
    k = next(k for k in range(len(table) - 1) if table[k][0] <= pos <= table[k + 1][0])
    (p0, *a), (p1, *b) = table[k], table[k + 1]
    t = (pos - p0) / (p1 - p0)
    return [math.exp(math.log(x) + t * (math.log(y) - math.log(x))) for x, y in zip(a, b)]


_TABLE = _table(_ANCHORS)
_TABLES = {"V": _TABLE, **{k: _table(v) for k, v in _GIANTS.items()}}
for _name, (_a, _b) in _BETWEEN.items():
    _TABLES[_name] = [(p, *[math.sqrt(x * y) for x, y in zip(_at(_TABLES[_a], p), _at(_TABLES[_b], p))])
                      for p in sorted({row[0] for row in _TABLES[_a] + _TABLES[_b]})]


@dataclass(frozen=True)
class Star:
    """What a spectral class, or a remnant, says about a star (`star`)."""
    spectral_class: str
    mass: float             # suns
    luminosity: float       # suns
    temperature: int        # K
    approximate: bool       # a hypergiant: a supergiant's values
    luminosity_class: str = "V"
    fixed_radius: Optional[float] = None      # suns: a remnant's own (REMNANTS)
    object_type: Optional[str] = None         # a remnant's type, None for a star

    @property
    def radius(self) -> float:
        """In suns: a remnant's own; a dwarf's from its mass, R ∝ M^0.8; a
        giant's from its light and temperature, L = R² T⁴."""
        if self.fixed_radius is not None:
            return self.fixed_radius
        if self.luminosity_class == "V":
            return self.mass ** 0.8
        return math.sqrt(self.luminosity) * (_SUN_TEMPERATURE / self.temperature) ** 2

    @property
    def habitable_zone(self) -> tuple[float, float]:
        """Where liquid water can be, in AU: √(L/1.1) to √(L/0.53)."""
        return math.sqrt(self.luminosity / 1.1), math.sqrt(self.luminosity / 0.53)

    @property
    def frost_line(self) -> float:
        """Beyond which ices condense and gas giants usually form, in AU."""
        return 2.7 * math.sqrt(self.luminosity)

    @property
    def inner_limit(self) -> float:
        """Closer than this a planet would not keep its orbit (or its
        surface), in AU — a rough floor for the draw."""
        return max(0.015, 0.03 * math.sqrt(self.luminosity))


# What a stellar remnant is: fixed values per type, enough for
# its planets' orbits and zones, the system map and the skies. A remnant has
# no MK class; `object_type` names it.
_SUN_RADIUS_KM = 695_700
REMNANTS: dict[str, dict[str, float]] = {
    # Earth-sized, hot and faint: absolute magnitude about +11.5.
    "white_dwarf": {"mass": 0.6, "radius_km": 8_800, "temperature": 10_000, "luminosity": 0.003},
    # A city across; its glow X-rays, all but none of it visible light.
    "neutron_star": {"mass": 1.4, "radius_km": 12, "temperature": 600_000, "luminosity": 1e-6},
    "pulsar": {"mass": 1.4, "radius_km": 12, "temperature": 600_000, "luminosity": 1e-6},
    # A stellar black hole: its horizon, 2.95 km per sun; no light of its own.
    "black_hole": {"mass": 8.0, "radius_km": 2.95 * 8.0, "temperature": 0, "luminosity": 0.0},
}
REMNANT_LABELS = {"white_dwarf": "White dwarf", "neutron_star": "Neutron star", "pulsar": "Pulsar",
                  "black_hole": "Black hole"}


def remnant(object_type: Optional[str]) -> Optional[Star]:
    """The remnant `object_type` names, as a Star; None for anything else."""
    facts = REMNANTS.get(object_type or "")
    if facts is None:
        return None
    return Star(REMNANT_LABELS[object_type], facts["mass"], facts["luminosity"], int(facts["temperature"]),
                approximate=False, luminosity_class="remnant",
                fixed_radius=facts["radius_km"] / _SUN_RADIUS_KM, object_type=object_type)


def star(spectral_class: Optional[str], object_type: Optional[str] = None) -> Optional[Star]:
    """The star a spectral class describes — or, with a remnant's
    `object_type`, that remnant; None for none or one this table does not
    cover."""
    if object_type in REMNANTS:
        return remnant(object_type)
    m = _CLASS.match((spectral_class or "").strip())
    if not m:
        return None
    pos = _position(m.group(1), float(m.group(2) or 5))
    written = m.group(3) or "V"
    lum_class = _SAME.get(written, written)
    mass, luminosity, temperature = _at(_TABLES[lum_class], pos)
    return Star(spectral_class.strip(), round(mass, 3), luminosity, int(round(temperature, -1)),
                approximate=written in ("Ia+", "0"), luminosity_class=lum_class)


def class_for_mass(mass: float) -> str:
    """The main-sequence class whose mass is nearest, O5V to M9V."""
    grid = [f"{letter}{n}V" for letter in _LETTERS for n in range(10)
            if _TABLE[0][0] <= _position(letter, n) <= _TABLE[-1][0]]
    return min(grid, key=lambda c: abs(math.log(star(c).mass / mass)))


def draw_companion_class(primary_star: Star, rng: random.Random) -> str:
    """A companion's class: the mass ratio to the primary is about evenly
    spread from 0.1 to 1 (as for observed binaries), never below a red
    dwarf's 0.08 suns."""
    return class_for_mass(max(0.08, primary_star.mass * rng.uniform(0.1, 1.0)))


def primary(system: dict[str, Any]) -> Optional[Star]:
    """The system's primary star, which its planets orbit: a remnant
    where the system's `object_type` names one."""
    stars = system.get("stars") or []
    return star((stars[0].get("spectral_class") if stars else None) or system.get("spectral_class"),
                system.get("object_type"))
