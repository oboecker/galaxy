"""Where a project's files are: its catalogue and the files beside it, where
an editor keeps its working state, and where the maps' data is written.

A project describes itself in a `project.toml`; relative paths in it are
read against the file's folder:

    root = "../.."                      paths in messages are written relative to it
    catalogue = "galaxy.json"           the layer an editor writes
    layers = ["@real-sky", "galaxy.json"]   optional: the catalogue's layers in order, the default
                                        shown; `@name` for one the engine ships (galaxy.catalogue);
                                        a layer may be a table naming how the map lists it:
                                        {file = "galaxy.json", label = "My story", icon = "planet"}
    nations = "nations.json"
    travel = "travel.json"              the travel planner's numbers
    medium = "medium.json"              the faster-than-light medium's density field
    constellations = "constellations.json"
    procedural = "procedural.json"      the procedural galaxy's measured numbers
    density = "@milky-way"              the image the procedural galaxy's density is read from: the
                                        engine's (the Milky Way's arms), or a project's own image or
                                        a drawing (.svg) with one embedded
    calendar = "calendar.json"
    namer = "package.module:function"   optional: names for the procedural galaxy
    objects = "objects.json"            optional: kinds of point of interest of its own (galaxy.objects)
    drafts = "…"                        optional: an editor's working state
    planet_maps = "…"                   optional: one folder per planet map
    public = "…"                        optional: the folder the maps read their data from
    public_planets = "…"                optional: the planet textures the maps read
    svg = "…"                           optional: the 2D galaxy map

    project.use(Path("…/project.toml"))     # once, at start
    project.current().catalogue

Without `use`, `current()` reads the file named by the GALAXY_PROJECT
environment variable.
"""

from __future__ import annotations

import importlib
from importlib import resources
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Union

ENV = "GALAXY_PROJECT"

_REQUIRED = ("catalogue", "nations", "travel", "medium", "constellations", "procedural", "density", "calendar")
_OPTIONAL = ("drafts", "planet_maps", "public", "public_planets", "svg", "objects")


@dataclass(frozen=True)
class Project:
    root: Path
    catalogue: Path
    nations: Path
    travel: Path
    medium: Path
    constellations: Path
    procedural: Path
    density: Path
    calendar: Path
    namer: Optional[str] = None
    drafts: Optional[Path] = None
    planet_maps: Optional[Path] = None
    public: Optional[Path] = None
    public_planets: Optional[Path] = None
    svg: Optional[Path] = None
    objects: Optional[Path] = None
    layers: tuple[Path, ...] = ()
    # How the map lists each layer, in the order of `layers`: {label?, icon?}.
    layer_looks: tuple[dict, ...] = ()

    def relative(self, path: Path) -> str:
        """`path` as written relative to the project's root, or absolute if
        it is outside it."""
        try:
            return str(Path(path).resolve().relative_to(self.root.resolve()))
        except ValueError:
            return str(path)

    def name_generator(self) -> Optional[Callable]:
        """The function `namer` names (`module:function`), or None."""
        if not self.namer:
            return None
        module, _, function = self.namer.partition(":")
        return getattr(importlib.import_module(module), function)


def load(path: Union[str, Path]) -> Project:
    """The project described by the `project.toml` at `path`."""
    path = Path(path)
    with path.open("rb") as f:
        raw = tomllib.load(f)
    base = path.parent
    missing = [key for key in _REQUIRED if key not in raw]
    if missing:
        raise ValueError(f"{path}: missing {', '.join(missing)}")
    unknown = set(raw) - {"root", "namer", "layers", *_REQUIRED, *_OPTIONAL}
    if unknown:
        raise ValueError(f"{path}: unknown {', '.join(sorted(unknown))}")
    paths = {key: _file(base, raw[key]) for key in (*_REQUIRED, *_OPTIONAL) if key in raw}
    entries = [entry if isinstance(entry, dict) else {"file": entry}
               for entry in raw.get("layers", ["@real-sky", raw["catalogue"]])]
    for entry in entries:
        if not isinstance(entry.get("file"), str) or set(entry) - {"file", "label", "icon"}:
            raise ValueError(f"{path}: a layer is a file, or a table of file, label and icon")
    layers = tuple(_layer(base, entry["file"]) for entry in entries)
    if not layers or layers[-1] != paths["catalogue"]:
        raise ValueError(f"{path}: the last of `layers` is the catalogue, the layer an editor writes")
    looks = tuple({k: entry[k] for k in ("label", "icon") if k in entry} for entry in entries)
    return Project(root=_joined(base, raw.get("root", ".")), namer=raw.get("namer"), layers=layers,
                   layer_looks=looks, **paths)


def _layer(base: Path, name: str) -> Path:
    """A layer's file: one the engine ships (`@name`), else the project's."""
    if name.startswith("@"):
        from galaxy import catalogue
        return catalogue.built_in(name[1:])
    return _joined(base, name)


# Files the engine ships that a project may name with `@`, beside its layers.
BUILT_IN = {"milky-way": "milky-way.jpg"}


def _file(base: Path, name: str) -> Path:
    """A project's file, or one the engine ships (`@name`, BUILT_IN)."""
    if name.startswith("@"):
        if name[1:] not in BUILT_IN:
            raise ValueError(f"no file @{name[1:]}; the engine ships {', '.join('@' + n for n in BUILT_IN)}")
        return Path(str(resources.files("galaxy") / "data" / BUILT_IN[name[1:]]))
    return _joined(base, name)


def _joined(base: Path, relative: str) -> Path:
    """`relative` against `base`, its `..` folded away (no symlinks resolved)."""
    return Path(os.path.normpath(base / relative))


_current: Optional[Project] = None


def use(project: Union[Project, str, Path]) -> Project:
    """Make `project` (or the project.toml at that path) the current one."""
    global _current
    _current = project if isinstance(project, Project) else load(project)
    return _current


def current() -> Project:
    """The project `use` set, else the one GALAXY_PROJECT names."""
    global _current
    if _current is None:
        named = os.environ.get(ENV)
        if not named:
            raise RuntimeError(f"No galaxy project: call galaxy.project.use(…) or set {ENV} "
                               "to a project.toml")
        _current = load(named)
    return _current


def add_argument(parser) -> None:
    """A CLI's `--project` (argparse)."""
    parser.add_argument("--project", type=Path, help=f"the project's project.toml (default: ${ENV})")


def from_args(args) -> Project:
    """The project a CLI's `--project` names, else the current one."""
    return use(args.project) if getattr(args, "project", None) else current()
