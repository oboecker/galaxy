"""Stellar remnants as a system's primary (galaxy.stars.REMNANTS):
white dwarfs, neutron stars, pulsars, black holes — their mass, size and
light, and what the orbits, the hierarchy and the system map make of them."""

import random

import pytest

from galaxy import hierarchy, orbits, schema, stars, systemmap


def system(object_type, planets=0):
    out = {"name": "Remnant", "x": 0, "y": 20_000, "z": 0, "coordinate_system": "galactic",
           "object_type": object_type, "plane": {"i": 10.0, "node": 0.0, "zero": 0.0}}
    if planets:
        out["planets"] = [{"name": f"R{k}"} for k in range(planets)]
    return out


@pytest.mark.parametrize("kind", sorted(stars.REMNANTS))
def test_a_remnant_is_its_systems_primary(kind):
    primary = stars.primary(system(kind))
    assert primary.object_type == kind and primary.mass == stars.REMNANTS[kind]["mass"]
    assert primary.radius * 695_700 == pytest.approx(stars.REMNANTS[kind]["radius_km"])
    assert hierarchy.tree(system(kind), physical=True).root.mass == primary.mass


def test_only_a_white_dwarf_shows_in_the_skies():
    assert systemmap.absolute_magnitude(system("white_dwarf")) == pytest.approx(11.5, abs=0.3)
    for kind in ("neutron_star", "pulsar", "black_hole"):
        assert systemmap.absolute_magnitude(system(kind)) is None


def test_a_black_holes_planets_orbit_it_and_the_map_draws_them():
    s = system("black_hole", planets=3)
    orbits.draw_system(s, random.Random(1))
    for planet in s["planets"]:
        planet["class"] = orbits.draw_class(s, planet, rng=random.Random(2))
        assert planet["orbit"]["au"] > 0 and planet["class"] != "terrestrial-habitable"
    schema.validate(schema.normalise({"star_systems": [s]}))
    drawn = systemmap.system(s)
    assert drawn["object_type"] == "black_hole" and drawn["star"]["object_type"] == "black_hole"
    assert drawn["star"]["mass"] == 8.0 and drawn["star"]["habitable_zone"] == [0.0, 0.0]
    assert all(p["period"] > 0 for p in drawn["planets"])


def test_a_star_is_still_a_star():
    assert stars.star("G2V").object_type is None and stars.star("G2V", "nebula").object_type is None
    assert systemmap.system({"name": "S", "x": 0, "y": 20_000, "z": 0, "spectral_class": "G2V"})["object_type"] is None
