"""Travel modes: the project's own, declared in travel.json `modes`."""

import pytest

from galaxy import public, travel


def test_a_mode_gets_its_leg_kind_and_label():
    found = travel.modes({"modes": {"Warp": {"kind": "jump", "minutes": 5},
                                    "Sling": {"kind": "straight", "ly_per_day": 100, "label": "Slingshot",
                                              "leg": "sling", "from_point": "beacon"}}})
    assert found["Warp"] == {"kind": "jump", "minutes": 5, "leg": "warp", "label": "Warp"}
    assert found["Sling"]["label"] == "Slingshot" and found["Sling"]["leg"] == "sling"
    assert list(found) == ["Warp", "Sling"], "in the order travel.json gives them"


def test_no_modes_by_default_and_an_unknown_kind_is_refused():
    assert travel.modes({}) == {}
    with pytest.raises(ValueError, match="kind is one of straight, jump"):
        travel.modes({"modes": {"Teleport": {"kind": "magic"}}})


def test_a_shortcut_has_no_speed_while_moving():
    leg = travel.Leg("warp", "A", "B", 100.0, 0.01)
    assert travel.Option("Warp", [leg], 0.01, shortcut=True).average is None
    assert travel.Option("Sling", [leg], 0.01).average == pytest.approx(10_000)


def test_the_maps_learn_a_modes_name_not_its_numbers():
    settings = public.travel_settings({"maps": {}, "modes": {"Warp": {"kind": "jump", "minutes": 5, "about": "x"}}})
    assert settings["modes"] == {"Warp": {"kind": "jump", "leg": "warp", "label": "Warp"}}


def test_the_maps_learn_the_top_thrust():
    assert public.travel_settings({"sublight": {"g": 1.5, "star_clearance_au": 0.1}})["sublight"] == {"g": 1.5}
    assert "sublight" not in public.travel_settings({})
