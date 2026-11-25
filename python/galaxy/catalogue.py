"""The catalogue as layers: files read in order and merged into one document,
so a map is extended by adding a file, never by rewriting one.

The engine ships the real sky (`@real-sky`: Sol and its bodies, the bright
stars, the real nebulae). A project names its layers in project.toml,
`@name` for a layer the engine ships, and the last one, `catalogue`, is the
one an editor writes:

    layers = ["@real-sky", "galaxy.json"]      # the default
    catalogue = "galaxy.json"

Merging, layer by layer (`merge`):

- systems and nebulae by name: a later layer's entry with a name already
  there extends or overrides it field by field (its `_removed` lists fields
  it takes away); a new one joins. An entry is in every layer that names it,
  so `{"name": "Sol"}` alone puts the real Sol into a story's layer as well:
  the galaxy map shows it while either layer is switched on. The project's own order is kept, and an
  earlier layer's systems take their place in system_order;
- lists (labels, gate links, trips) are joined; mappings (sector names) are
  merged, the later layer's keys winning; anything else, the later wins.

An editor works on the merged document; `write` keeps of it only what the
earlier layers do not already say (`split`) and writes that to the project's
layer.

    doc = catalogue.read()          # merged, a private copy
    catalogue.write(doc)            # the project's layer, split off
"""

from __future__ import annotations

import copy
from importlib import resources
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from galaxy import project
from galaxy.fs import write_atomic
from galaxy.jsonstore import dumps, store

BUILT_IN = {"real-sky": "real-sky.json"}
BY_NAME = ("star_systems", "nebulae")
REMOVED = "_removed"


def built_in(name: str) -> Path:
    """The file of a layer the engine ships."""
    if name not in BUILT_IN:
        raise ValueError(f"no layer @{name}; the engine ships {', '.join('@' + n for n in BUILT_IN)}")
    return Path(str(resources.files("galaxy") / "data" / BUILT_IN[name]))


def system_order(name: str) -> tuple[bool, str]:
    """The order the catalogue keeps its systems in: by name, the ``Unnamed
    NNN`` placeholders together at the end."""
    return (name.startswith("Unnamed "), name.lower())


def insert_at(systems: list[dict[str, Any]], name: str) -> int:
    """Index at which `name` belongs, keeping the list in system_order. A
    linear scan, correct even where the list is not perfectly ordered."""
    key = system_order(name)
    for i, s in enumerate(systems):
        if system_order(s.get("name", "")) > key:
            return i
    return len(systems)


def _overlaid(earlier: dict[str, Any], later: dict[str, Any]) -> dict[str, Any]:
    """`earlier` with `later`'s fields over it and the fields `later` lists
    as `_removed` taken away (the list kept, for a layer earlier still)."""
    out = {**earlier, **later}
    for key in later.get(REMOVED) or []:
        if key != REMOVED:
            out.pop(key, None)
    return out


def merge(docs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The layers `docs`, earliest first, as one document."""
    out: dict[str, Any] = {}
    # Keys in the order the latest layer has them, then the earlier layers' own.
    for doc in reversed(docs):
        for key in doc:
            out.setdefault(key, None)
    for key in out:
        present = [doc[key] for doc in docs if key in doc]
        if key in BY_NAME:
            out[key] = _merge_named(present, sort=key == "star_systems")
        elif all(isinstance(v, list) for v in present):
            out[key] = [copy.deepcopy(item) for value in present for item in value]
        elif all(isinstance(v, dict) for v in present):
            out[key] = {k: copy.deepcopy(v) for value in present for k, v in value.items()}
        else:
            out[key] = copy.deepcopy(present[-1])
    return out


def _merge_named(lists: list[list[dict[str, Any]]], sort: bool) -> list[dict[str, Any]]:
    """Named entries of several layers, earliest first, as one list: the
    latest layer's order, the earlier ones' entries under the later ones'
    fields, an earlier one's new entries in system_order (`sort`) or after
    the rest."""
    merged: list[dict[str, Any]] = []
    where: dict[str, int] = {}
    for depth, entries in enumerate(reversed(lists)):
        for entry in entries:
            name = entry.get("name")
            if name in where:
                merged[where[name]] = _overlaid(copy.deepcopy(entry), merged[where[name]])
                continue
            entry = copy.deepcopy(entry)
            if depth == 0 or not sort:
                merged.append(entry)
                where[name] = len(merged) - 1
            else:
                merged.insert(insert_at(merged, name or ""), entry)
                where = {e.get("name"): i for i, e in enumerate(merged)}
    for entry in merged:
        entry.pop(REMOVED, None)
    return merged


def split(doc: dict[str, Any], earlier: Sequence[dict[str, Any]],
          own: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """What of the merged `doc` the earlier layers do not already say: the
    last layer, which merged over them gives `doc` again. An entry the last
    layer as it stands (`own`) names is kept, if only by its name: it is in
    that layer too. Refused (ValueError) for an earlier layer's system or
    nebula `doc` lacks — a layer cannot remove what another holds."""
    base = merge(earlier) if earlier else {}
    out: dict[str, Any] = {}
    for key, value in doc.items():
        if key not in base:
            out[key] = copy.deepcopy(value)
        elif key in BY_NAME:
            named = {e.get("name") for e in (own or {}).get(key) or []}
            entries = _split_named(key, value, base[key], named)
            if entries:
                out[key] = entries
        elif isinstance(value, list) and isinstance(base[key], list):
            items = [copy.deepcopy(item) for item in value if item not in base[key]]
            if items:
                out[key] = items
        elif isinstance(value, dict) and isinstance(base[key], dict):
            items = {k: copy.deepcopy(v) for k, v in value.items() if base[key].get(k) != v}
            if items:
                out[key] = items
        elif value != base[key]:
            out[key] = copy.deepcopy(value)
    return out


def _split_named(key: str, entries: list[dict[str, Any]], base: list[dict[str, Any]],
                 named: frozenset[str] | set[str] = frozenset()) -> list[dict[str, Any]]:
    """The entries of `entries` that are new or changed against `base`, or
    that the layer names already (`named`); a changed one holds only its name
    and what differs."""
    known = {e.get("name"): e for e in base}
    names = {e.get("name") for e in entries}
    gone = [name for name in known if name not in names]
    if gone:
        raise ValueError(f"{', '.join(gone)}: in an earlier layer of the catalogue ({key}), "
                         "which a project's layer cannot remove")
    out = []
    for entry in entries:
        earlier = known.get(entry.get("name"))
        if earlier is None:
            out.append(copy.deepcopy(entry))
            continue
        changed = {k: copy.deepcopy(v) for k, v in entry.items() if k == "name" or earlier.get(k) != v}
        removed = [k for k in earlier if k not in entry]
        if removed:
            changed[REMOVED] = removed
        if len(changed) > 1 or entry.get("name") in named:
            out.append(changed)
    return out


# ── the current project's ─────────────────────────────────────────────────────

def _layers(here: Optional[project.Project] = None, last: Optional[Path] = None) -> list[dict[str, Any]]:
    """The current project's layers, as their files hold them (shared: do not
    mutate); `last` in place of the project's own layer if given."""
    here = here or project.current()
    paths = [*here.layers[:-1], last or here.layers[-1]]
    return [store.read(path) if path.exists() else {} for path in paths]


def read(here: Optional[project.Project] = None, last: Optional[Path] = None) -> dict[str, Any]:
    """The merged catalogue, a private copy; with `last`, that file as the
    project's own layer."""
    return merge(_layers(here, last))


def text(here: Optional[project.Project] = None, last: Optional[Path] = None) -> str:
    """The merged catalogue as its files are formatted; `last` as in `read`."""
    return dumps(read(here, last))


def layer_name(path: Path) -> str:
    """A layer's name, for its file among the maps' data: an engine layer's
    own name (real-sky), else its file's stem."""
    for name in BUILT_IN:
        if path == built_in(name):
            return name
    return path.stem


def write_layers(out: Path, here: Optional[project.Project] = None) -> list[Path]:
    """Each layer as its own file in `out`, `<name>.json` (layer_name): what
    the galaxy map loads, a switch each. The files written."""
    here = here or project.current()
    written = []
    for path, doc in zip(here.layers, _layers(here)):
        target = Path(out) / f"{layer_name(path)}.json"
        write_atomic(target, dumps(doc))
        written.append(target)
    return written


def write(doc: dict[str, Any], validator: Optional[Callable[[Any], None]] = None,
          here: Optional[project.Project] = None) -> bool:
    """Validate the merged `doc` (`validator`), then write the project's
    layer of it. False when the layer is unchanged."""
    here = here or project.current()
    if validator is not None:
        validator(doc)
    layers = _layers(here)
    return store.write(here.catalogue, split(doc, layers[:-1], layers[-1]))
