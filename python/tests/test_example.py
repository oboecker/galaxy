"""The example project (examples/minimal) through the whole engine: its
layers merged, the maps' files built, travel planned with its own modes."""

import json
from pathlib import Path

import pytest

from galaxy import build, catalogue, project, travel, trips

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "minimal" / "project.toml"


@pytest.fixture
def example(monkeypatch):
    here = project.load(EXAMPLE)
    monkeypatch.setattr(project, "_current", here)
    return here


def test_the_story_extends_the_real_sky(example):
    doc = catalogue.read()
    names = {s["name"] for s in doc["star_systems"]}
    assert {"Sol", "Sirius", "Aster", "Brannock", "Corvel"} <= names
    vega = next(s for s in doc["star_systems"] if s["name"] == "Vega")
    assert vega["planets"][0]["name"] == "Vega Prime" and vega["stars"][0]["hip"], "a real star, with the story's planet"
    assert catalogue.split(doc, catalogue._layers(example)[:-1]) == json.loads(example.catalogue.read_text())


def test_the_build_writes_what_the_maps_read(example, tmp_path):
    build.write(tmp_path, procedural_galaxy=True, within=1500)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    galaxy = manifest["galaxy"]
    assert [layer["id"] for layer in galaxy["layers"]] == ["real-sky", "galaxy"]
    for name in [layer["url"] for layer in galaxy["layers"]] + [
            galaxy["trips"], galaxy["travelSettings"], galaxy["procedural"], galaxy["proceduralGates"],
            galaxy["territories"] + "index.json", *[v for v in manifest["system"].values() if v]]:
        assert (tmp_path / name).exists(), name
    assert manifest["calendar"]["epoch"] == "AD 2400"
    settings = json.loads((tmp_path / "travel-settings.json").read_text())
    assert set(settings["modes"]) == {"Slingshot", "Warp"} and settings["modes"]["Warp"]["label"] == "Warp jump"


def test_its_own_modes_join_the_engines(example):
    found = {o.name: o for o in travel.plan(catalogue.read(), "Sol", "Brannock", depart=2400.0)}
    assert {"own drive", "gates", "Warp"} <= set(found) and "Slingshot" not in found, "no beacon at Sol"
    assert found["Warp"].shortcut and found["Warp"].days * 24 * 60 == pytest.approx(10)
    assert found["gates"].days < found["own drive"].days
    route = trips.route(catalogue.read(), catalogue.read()["trips"][0])
    assert route["option"]["name"] == "gates", "the fastest that flies, not the jump"
    assert route["check"]["in_time"]


def test_a_jumpgate_without_an_id_is_left_unpaired():
    from galaxy import insystem
    system = {"points_of_interest": [{"kind": "jumpgate", "pair": "g2"},
                                     {"kind": "jumpgate", "id": "g2", "pair": "g3"},
                                     {"kind": "jumpgate", "id": "g3", "pair": "g2", "grade": "early"}]}
    assert insystem.jumpgate_pairs(system) == {"g2": ("g3", "mature"), "g3": ("g2", "early")}
