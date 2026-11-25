"""The travel planner's working constants, in one place.

The setting's numbers — speeds, reaches, clearances, the gate network's
rule, the maps' route colours — are the project's travel.json's and
medium.json's, and nowhere else: these here are how the planner computes,
not what the world is.

Cross-dependency notes
----------------------
DETOUR_HIT_SHARE < 1 < DETOUR_CLEARANCE: a leg is bent when it comes
    closer than DETOUR_HIT_SHARE × the clearance, and the bend keeps
    DETOUR_CLEARANCE × it — the margin between the two keeps an obstacle
    that moves while the ship passes from catching the bend again.
LEG_SAMPLES × MAX_DETOURS bound the work per leg: fewer samples can miss a
    small obstacle on a long leg; more detours only matter in crowded
    systems.
AIM_ROUNDS and BEND_ROUNDS: the aim at a moving destination converges in a
    few rounds (the bodies move little during a flight); bending is costly,
    so fewer rounds there.
"""

from __future__ import annotations

from galaxy import orbits


class TravelConfig:
    """The planner's working constants, grouped by where they are used."""

    # ── units ──────────────────────────────────────────────────────────────
    DAY_HOURS = 24.0
    YEAR_DAYS = 365.25
    DAY_S = 86_400.0
    AU_M = orbits.AU_KM * 1000
    LY_AU = 63_241.077                 # astronomical units in a light-year

    # ── between the stars (galaxy.travel) ─────────────────────────────────
    # A straightened leg may take this much longer than the grid's route
    # before the straight cut is refused (floating-point slack).
    STRAIGHTEN_SLACK = 1.0001

    # ── within a system (galaxy.insystem) ─────────────────────────────────
    LEG_SAMPLES = 32                   # points along a leg checked against what is in the way
    MAX_DETOURS = 6                    # bends at most, one per obstacle hit
    DETOUR_HIT_SHARE = 0.97            # closer than this share of a clearance: bend
    DETOUR_CLEARANCE = 1.02            # the bend keeps this share of the clearance
    DETOUR_CHECK_POINTS = 96           # points of a candidate bend checked for clearance
    DETOUR_DRAWN_POINTS = 48           # points of the bend as drawn
    DETOUR_SEARCH_STEPS = 30           # bisection steps for how far a bend swings out
    AIM_ROUNDS = 12                    # aim corrections at a moving destination, straight
    BEND_ROUNDS = 4                    # … and once bent around obstacles
    TRACK_POINTS = 17                  # where the destination moves while a leg is flown
    ORBIT_SENSE_SHARE = 1 / 1000       # a body's period share looked ahead, for its sense of orbit

    # ── ballistic flight (galaxy.insystem) ──
    MIN_THRUST_G = 0.1                 # below this the star's pull rivals the thrust: not modelled
    WINDOW_STEPS = 360                 # samples per synodic period in the search for a launch window
    WINDOW_BISECT = 40                 # bisection steps for the window's moment
    MAX_SYNODIC_YEARS = 2000.0         # orbits this alike never line up within a story: no window
    BALLISTIC_POINTS = 48              # points of a transfer's half ellipse as drawn
