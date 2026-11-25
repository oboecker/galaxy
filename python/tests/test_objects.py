"""Points of interest by kind: the engine's own, and a project's (galaxy.objects)."""

import json
from pathlib import Path

import pytest

from galaxy import catalogue, objects, project, schema, systemmap
from galaxy.jsonstore import ValidationError

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "minimal" / "project.toml"


@pytest.fixture
def example(monkeypatch):
    here = project.load(EXAMPLE)
    monkeypatch.setattr(project, "_current", here)
    return here


def test_the_engines_kinds_and_none_of_a_projects_without_a_file():
    assert objects.point_kinds() == ("station", "jumpgate", "outpost", "shipyard", "wreck", "beacon")
    assert objects.project_points() == {}


def test_a_projects_kind_is_valid_and_its_look_travels_with_the_system(example):
    assert "relay" in objects.point_kinds()
    doc = catalogue.read()
    schema.validate(doc)
    brannock = next(s for s in doc["star_systems"] if s["name"] == "Brannock")
    drawn = systemmap.system(brannock)
    assert drawn["objects"] == {"relay": {"label": "Relay", "shape": "cone", "colour": "#5fd0a0", "size": 1.2}}
    aster = systemmap.system(next(s for s in doc["star_systems"] if s["name"] == "Aster"))
    assert "objects" not in aster, "only where the project's kinds are used"


def test_an_unknown_kind_is_refused(example):
    doc = catalogue.read()
    point = next(s for s in doc["star_systems"] if s["name"] == "Brannock")["points_of_interest"][0]
    point["kind"] = "castle"
    with pytest.raises(ValidationError, match="its kind is one of station, .*relay"):
        schema.validate(doc)


@pytest.mark.parametrize("look, why", [({"shape": "teapot", "colour": "#ffffff"}, "shape is one of"),
                                       ({"shape": "cone", "colour": "red"}, "colour is #rrggbb")])
def test_a_bad_look_is_refused(tmp_path, look, why):
    (tmp_path / "objects.json").write_text(json.dumps({"points": {"relay": look}}), encoding="utf-8")
    here = project.load(EXAMPLE)
    from dataclasses import replace
    with pytest.raises(ValueError, match=why):
        objects.project_points(replace(here, objects=tmp_path / "objects.json"))


def test_a_project_cannot_redefine_an_engine_kind(tmp_path):
    (tmp_path / "objects.json").write_text(json.dumps({"points": {"wreck": {"shape": "cone", "colour": "#ffffff"}}}),
                                           encoding="utf-8")
    from dataclasses import replace
    with pytest.raises(ValueError, match="one of the engine's own kinds"):
        objects.project_points(replace(project.load(EXAMPLE), objects=tmp_path / "objects.json"))
