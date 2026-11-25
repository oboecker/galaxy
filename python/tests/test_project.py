"""galaxy.project: a project.toml read, its paths against its folder."""

from pathlib import Path

import pytest

from galaxy import project

MINIMAL = """
catalogue = "galaxy.json"
nations = "nations.json"
travel = "travel.json"
medium = "medium.json"
constellations = "constellations.json"
procedural = "procedural.json"
density = "density.svg"
calendar = "calendar.json"
"""


def test_paths_are_read_against_the_files_folder(tmp_path):
    (tmp_path / "project.toml").write_text(MINIMAL + 'drafts = "../drafts"\n', encoding="utf-8")
    here = project.load(tmp_path / "project.toml")
    assert here.catalogue == tmp_path / "galaxy.json"
    assert here.drafts == tmp_path.parent / "drafts"
    assert here.root == tmp_path
    assert here.public is None and here.namer is None and here.name_generator() is None


def test_a_missing_or_unknown_key_is_refused(tmp_path):
    (tmp_path / "project.toml").write_text(MINIMAL.replace('calendar = "calendar.json"\n', ""), encoding="utf-8")
    with pytest.raises(ValueError, match="missing calendar"):
        project.load(tmp_path / "project.toml")
    (tmp_path / "project.toml").write_text(MINIMAL + 'catalog = "x"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="unknown catalog"):
        project.load(tmp_path / "project.toml")


def test_the_namer_is_a_module_and_function(tmp_path):
    (tmp_path / "project.toml").write_text(MINIMAL + 'namer = "galaxy.names:generate"\n', encoding="utf-8")
    from galaxy import names
    assert project.load(tmp_path / "project.toml").name_generator() is names.generate


def test_relative_writes_a_path_inside_the_root_relative_to_it(tmp_path):
    (tmp_path / "project.toml").write_text(MINIMAL, encoding="utf-8")
    here = project.load(tmp_path / "project.toml")
    assert here.relative(tmp_path / "a" / "b.json") == str(Path("a") / "b.json")
    assert here.relative(Path("/elsewhere/c.json")) == "/elsewhere/c.json"
