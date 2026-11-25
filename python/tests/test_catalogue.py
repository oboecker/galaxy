"""galaxy.catalogue: layers merged in order, and a project's layer split off."""

import pytest

from galaxy import catalogue, project
from galaxy.jsonstore import dumps

SKY = {"star_systems": [{"name": "Sirius", "x": 1, "spectral_class": "A1V"},
                        {"name": "Vega", "x": 2, "spectral_class": "A0V"}],
       "nebulae": [{"name": "Orion Nebula", "real": "M42"}]}
STORY = {"labels": [{"text": "Rim"}],
         "star_systems": [{"name": "Aster", "x": 5},
                          {"name": "Vega", "planets": [{"name": "Vega b"}]},
                          {"name": "Unnamed 001", "x": 9}],
         "gate_links": [{"a": "Aster", "b": "Vega"}]}


def test_layers_merge_by_name_in_system_order():
    doc = catalogue.merge([SKY, STORY])
    assert [s["name"] for s in doc["star_systems"]] == ["Aster", "Sirius", "Vega", "Unnamed 001"]
    vega = doc["star_systems"][2]
    assert vega == {"name": "Vega", "x": 2, "spectral_class": "A0V", "planets": [{"name": "Vega b"}]}
    assert list(doc) == ["labels", "star_systems", "gate_links", "nebulae"]
    assert doc["nebulae"] == SKY["nebulae"]


def test_splitting_the_merged_document_gives_the_layer_back():
    doc = catalogue.merge([SKY, STORY])
    assert catalogue.split(doc, [SKY]) == STORY
    assert dumps(catalogue.merge([SKY, catalogue.split(doc, [SKY])])) == dumps(doc)


def test_a_field_taken_away_and_a_layer_that_cannot_remove():
    doc = catalogue.merge([SKY, STORY])
    del doc["star_systems"][1]["spectral_class"]                     # Sirius's
    own = catalogue.split(doc, [SKY])
    assert {"name": "Sirius", "_removed": ["spectral_class"]} in own["star_systems"]
    assert "spectral_class" not in catalogue.merge([SKY, own])["star_systems"][1]
    del doc["star_systems"][1]
    with pytest.raises(ValueError, match="Sirius: in an earlier layer"):
        catalogue.split(doc, [SKY])


def test_a_layer_naming_an_earlier_system_keeps_it_by_its_name():
    story = {**STORY, "star_systems": [*STORY["star_systems"], {"name": "Sirius"}]}
    doc = catalogue.merge([SKY, story])
    sirius = next(s for s in doc["star_systems"] if s["name"] == "Sirius")
    assert sirius == SKY["star_systems"][0], "the earlier layer's fields"
    assert catalogue.split(doc, [SKY]) == STORY, "without the layer, nothing says it is the story's"
    assert {"name": "Sirius"} in catalogue.split(doc, [SKY], story)["star_systems"]


def test_the_project_names_its_layers_the_engines_with_an_at(tmp_path):
    (tmp_path / "story.json").write_text(dumps(STORY), encoding="utf-8")
    base = project.current()
    keys = {k: getattr(base, k) for k in ("nations", "travel", "medium", "constellations", "procedural",
                                          "density", "calendar")}
    lines = [f'{k} = "{v}"' for k, v in keys.items()] + ['catalogue = "story.json"',
                                                          'layers = ["@real-sky", "story.json"]']
    (tmp_path / "project.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    here = project.load(tmp_path / "project.toml")
    assert here.layers[0] == catalogue.built_in("real-sky") and here.layers[1] == tmp_path / "story.json"
    doc = catalogue.read(here)
    assert {"Sol", "Sirius", "Aster"} <= {s["name"] for s in doc["star_systems"]}
    assert catalogue.write(doc, here=here) is False, "nothing changed: the layer is as it was"
    assert catalogue.own(doc, here) == STORY
    with pytest.raises(ValueError, match="no layer @moon"):
        catalogue.built_in("moon")


def test_the_layers_listed_for_the_map_with_their_looks(tmp_path):
    (tmp_path / "story.json").write_text(dumps(STORY), encoding="utf-8")
    (tmp_path / "extra.json").write_text(dumps({"star_systems": [{"name": "Corvel", "x": 1, "y": 2}]}), encoding="utf-8")
    base = project.current()
    keys = {k: getattr(base, k) for k in ("nations", "travel", "medium", "constellations", "procedural",
                                          "density", "calendar")}
    lines = [f'{k} = "{v}"' for k, v in keys.items()] + [
        'catalogue = "story.json"',
        'layers = ["@real-sky", {file = "extra.json", icon = "flag"}, {file = "story.json", label = "My story"}]']
    (tmp_path / "project.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    here = project.load(tmp_path / "project.toml")
    assert catalogue.layer_index(here) == [
        {"id": "real-sky", "label": "the real sky's stars", "icon": "star", "url": "real-sky.json", "real": True},
        {"id": "extra", "label": "extra", "icon": "flag", "url": "extra.json"},
        {"id": "story", "label": "My story", "icon": "planet", "url": "story.json"}]
    written = catalogue.write_layers(tmp_path / "out", here)
    assert [p.name for p in written] == ["real-sky.json", "extra.json", "story.json", "index.json"]
    (tmp_path / "project.toml").write_text("\n".join(lines[:-1] + ['layers = [{label = "no file"}, "story.json"]']) + "\n",
                                           encoding="utf-8")
    with pytest.raises(ValueError, match="a layer is a file"):
        project.load(tmp_path / "project.toml")
