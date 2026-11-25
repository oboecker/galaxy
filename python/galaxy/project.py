"""Where a project's files are: its catalogue and the files beside it, where
an editor keeps its working state, and where the maps' data is written.

A project describes itself in a `project.toml`; relative paths in it are
read against the file's folder:

    root = "../.."                      paths in messages are written relative to it
    catalogue = "galaxy.json"
    nations = "nations.json"
    travel = "travel.json"              the travel planner's numbers
    medium = "medium.json"              the faster-than-light medium's density field
    constellations = "constellations.json"
    procedural = "procedural.json"      the procedural galaxy's measured numbers
    density = "density.svg"             the image the procedural galaxy's density is read from
    calendar = "calendar.json"
    namer = "package.module:function"   optional: names for the procedural galaxy
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
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Union

ENV = "GALAXY_PROJECT"

_REQUIRED = ("catalogue", "nations", "travel", "medium", "constellations", "procedural", "density", "calendar")
_OPTIONAL = ("drafts", "planet_maps", "public", "public_planets", "svg")


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
    unknown = set(raw) - {"root", "namer", *_REQUIRED, *_OPTIONAL}
    if unknown:
        raise ValueError(f"{path}: unknown {', '.join(sorted(unknown))}")
    paths = {key: _joined(base, raw[key]) for key in (*_REQUIRED, *_OPTIONAL) if key in raw}
    return Project(root=_joined(base, raw.get("root", ".")), namer=raw.get("namer"), **paths)


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
