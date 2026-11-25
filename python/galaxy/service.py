"""In-session edit state for galaxy.json.

Edits accumulate here and nothing touches disk until Save, which is what the
explicit-save model requires: a dirty indicator to point at, and a discard that
costs nothing.

Single-user local tool, so one module-level session is enough — but it is a
class so that assumption sits in one place rather than being spread across the
routers.
"""

from __future__ import annotations

import copy
import json
import math
import random
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

from galaxy.fs import write_atomic
from galaxy.slugs import slugify
from galaxy import bodies, brightstars, catalogue, hierarchy, medium, nebulae, orbits, project, travel
from galaxy import trips as galaxy_trips
from galaxy import stars as star_data
from galaxy import schema as galaxy_schema
from galaxy.schema import coordinate_error
from galaxy.coords import CoordinateConverter
from galaxy.jsonstore import ValidationError


# The canvas the CLI renders at, and therefore the coordinate space the preview
# backdrop and its overlay share.
CANVAS = 5600
CONVERTER = CoordinateConverter(CANVAS / 2, CANVAS / 2)
# Draws of a planet's class before one that makes no unstable pair is given up on.
DRAW_TRIES = 20


def _normalised_text(text: str) -> str:
    """The saved file as the draft is compared with it: normalised, so that a
    form the file has not caught up with yet (one ring as a bare object,
    an older form) is no change — the next Commit writes it as the draft
    has it."""
    from galaxy.jsonstore import dumps
    return dumps(galaxy_schema.normalise(json.loads(text)))


class Fixed(ValueError):
    """A real star's position (galaxy.brightstars.is_real): not to be moved."""


def _movable(system: dict[str, Any]) -> None:
    """Refuse (Fixed) to move a real star's system."""
    if brightstars.is_real(system):
        raise Fixed(f"{system.get('name')} is a real star: its position is the sky's and does not move")


class SystemNotFound(Exception):
    """No system of the working copy has the name asked for."""
    pass


class ConflictError(Exception):
    """galaxy.json changed on disk, in records the draft changed too.
    `conflicts` lists them (see GalaxySession.conflicts)."""

    def __init__(self, message: str, conflicts: Optional[list[dict[str, Any]]] = None):
        super().__init__(message)
        self.conflicts = conflicts or []


# ── records, for comparing three versions of galaxy.json ──────────────────────
#
# A commit compares per record, not per file: a pull that changed
# other systems no longer blocks it, and is taken into the commit. A record
# is a system (by name), a sector name (by id), or the labels as one list.

def _records(doc: dict[str, Any]) -> dict[tuple, Any]:
    """The document's records by key: ("system", name), ("sector", id), ("labels",)."""
    out: dict[tuple, Any] = {("system", s.get("name")): s for s in doc.get("star_systems", [])}
    out.update({("sector", k): v for k, v in (doc.get("sector_names") or {}).items()})
    out[("labels",)] = doc.get("labels", [])
    return out


def describe_record(key: tuple) -> str:
    """A record's key in words: the system's name, "sector A7", "the labels"."""
    if key[0] == "system":
        return key[1]
    if key[0] == "sector":
        return f"sector {key[1]}"
    return "the labels"


def _differences(theirs: Any, mine: Any) -> list[str]:
    """What a conflict shows: the fields that differ between the file
    now and the draft, each with both values."""
    if theirs is None:
        return ["removed in the file, kept in your draft"]
    if mine is None:
        return ["changed in the file, removed in your draft"]
    if not isinstance(theirs, dict) or not isinstance(mine, dict):
        return [f"file: {theirs}; yours: {mine}"] if not isinstance(theirs, list) else ["the list differs"]
    out = []
    for field in sorted(set(theirs) | set(mine)):
        a, b = theirs.get(field), mine.get(field)
        if a == b:
            continue
        if isinstance(a, list) or isinstance(b, list):
            names = lambda xs: ", ".join(x.get("name") or "?" for x in xs or []) or "none"
            out.append(f"{field}: file {names(a)}; yours {names(b)}")
        else:
            out.append(f"{field}: file {a if a is not None else '—'}; yours {b if b is not None else '—'}")
    return out


system_order = catalogue.system_order      # the order the catalogue keeps its systems in


class GalaxySession:
    """An editor's working copy of galaxy.json: a draft, kept on disk across
    restarts, that edits go into until a Commit writes it or Discard drops it."""

    def __init__(self) -> None:
        # Reentrant: every mutator below holds this while calling `edit()`,
        # which takes it too. A plain Lock would deadlock on the first edit.
        self._lock = threading.RLock()
        # What the last commit took from the file (changes made outside the
        # editor to records the draft left alone), for its toast.
        self.merged: list[str] = []
        # The map folders the last commit moved along with a renamed planet,
        # for its toast.
        self.moved: list[str] = []
        # Planet maps are folders named after the planet (<planet_maps>/
        # <slug>/), so a rename moves its map at the next Commit:
        # {old slug: new slug}, kept with the draft.
        self._map_moves: dict[str, str] = {}
        # The last refused Commit, {"system", "message"}, kept until the next
        # attempt so both tabs can point at the record.
        self.refusal: Optional[dict[str, str]] = None
        self._draft: Optional[dict[str, Any]] = None
        self._baseline: Optional[str] = None
        # Bumped on every mutation so the preview cache knows to re-render.
        self._version = 0
        self._preview: Optional[tuple[int, bytes]] = None
        self._restore()

    # ── the draft on disk ─────────────────────────────────────────────────────
    #
    # The draft is written to the project's drafts folder on every change, so
    # that a restart (a dev server reloading on a code edit) loses nothing,
    # with the text of galaxy.json it started from, which Save still checks
    # for a concurrent edit. Save and Discard remove it.

    @staticmethod
    def _draft_paths() -> tuple[Path, Path]:
        """Where the draft and the galaxy.json text it started from are kept."""
        drafts = project.current().drafts
        return drafts / "draft.json", drafts / "baseline.json"

    _MOVES = "map_moves.json"

    def _persist(self) -> None:
        """Write the draft, its baseline and the pending map moves to the
        project's drafts folder; without a draft, remove them."""
        draft_path, baseline_path = self._draft_paths()
        moves_path = project.current().drafts / self._MOVES
        if self._draft is None:
            draft_path.unlink(missing_ok=True)
            baseline_path.unlink(missing_ok=True)
            moves_path.unlink(missing_ok=True)
            return
        from galaxy.jsonstore import dumps
        project.current().drafts.mkdir(parents=True, exist_ok=True)
        for path, text in ((baseline_path, self._baseline or ""), (draft_path, dumps(self._draft))):
            write_atomic(path, text)
        if self._map_moves:
            write_atomic(moves_path, json.dumps(self._map_moves))
        else:
            moves_path.unlink(missing_ok=True)

    def _restore(self) -> None:
        """Take up the draft a previous process left in the project's drafts
        folder, if any; a damaged one is dropped."""
        draft_path, baseline_path = self._draft_paths()
        if not (draft_path.exists() and baseline_path.exists()):
            return
        try:
            self._draft = json.loads(draft_path.read_text(encoding="utf-8"))
        except ValueError:
            return                          # a damaged draft is dropped, not fatal
        self._baseline = _normalised_text(baseline_path.read_text(encoding="utf-8"))
        moves_path = project.current().drafts / self._MOVES
        if moves_path.exists():
            try:
                self._map_moves = json.loads(moves_path.read_text(encoding="utf-8"))
            except ValueError:
                self._map_moves = {}

    @contextmanager
    def editing(self):
        """Hold the session for the duration of one edit.

        Every mutator takes this, in both this class and `SystemDetail`. An edit
        is rarely a single operation — a rename removes and re-inserts, a delete
        rebuilds the whole array and assigns it back — and two of those
        interleaving loses one outright. Measured before this existed, with a
        near-zero switch interval: **1227 of 3545 concurrent adds silently
        vanished** when a delete ran alongside, because the delete's wholesale
        assignment discarded whatever had been inserted meanwhile.

        Not merely theoretical for a single-user tool: a web editor fires
        overlapping requests, and a server may run each sync handler in its own
        threadpool thread.
        """
        with self._lock:
            yield

    # ── state ─────────────────────────────────────────────────────────────────

    def data(self) -> dict[str, Any]:
        """A snapshot of the working copy: the draft if edited, else what is on disk.

        **Always a copy.** It used to hand back the live draft when one existed
        and a copy otherwise, so what a caller could safely do with the result
        depended on whether anyone had edited yet — and a reader iterating the
        live draft could be preempted by a mutation mid-iteration. Templates,
        `overlay()` and `preview_svg()` all read through this, so one copy here
        makes every one of them safe. Measured at 0.311ms against an 8.5ms page.
        """
        with self._lock:
            if self._draft is not None:
                return copy.deepcopy(self._draft)
            # The layers merged: a private copy, so an edit never touches the store's cache.
            return catalogue.read()

    def edit(self) -> dict[str, Any]:
        """Return the draft, promoting the on-disk document into one if needed."""
        with self._lock:
            if self._draft is None:
                self._draft = catalogue.read()
                self._baseline = _normalised_text(catalogue.text())
            return self._draft

    @property
    def dirty(self) -> bool:
        """Whether the draft differs from the file it started from, compared
        normalised."""
        with self._lock:
            if self._draft is None:
                return False
            from galaxy.jsonstore import dumps

            return dumps(galaxy_schema.normalise(copy.deepcopy(self._draft))) != self._baseline

    def discard(self) -> None:
        """Drop the draft, its map moves and the last refusal, on disk too."""
        with self._lock:
            self._draft = None
            self._baseline = None
            self._map_moves = {}
            self.refusal = None
            self._version += 1
            self._persist()

    def saved_systems(self) -> Optional[dict[str, dict[str, Any]]]:
        """The star systems as last saved, by name — None when nothing is
        drafted, so a caller can tell "no changes" from "compare these".

        For marking unsaved changes in an editor's table of systems: a system whose
        name is not here is new to the draft, a field that differs is unsaved.
        """
        with self._lock:
            if self._baseline is None:
                return None
            saved = json.loads(self._baseline).get("star_systems", [])
            return {s.get("name"): s for s in saved}

    def sectors_unsaved(self) -> bool:
        """Whether the sector names differ from the last Save: an editor's
        mark of unsaved sector names."""
        with self._lock:
            if self._baseline is None:
                return False
            saved = json.loads(self._baseline).get("sector_names", {})
            return (self._draft.get("sector_names") or {}) != saved

    def removed_systems(self) -> list[str]:
        """Names saved but no longer in the draft — renamed or removed."""
        with self._lock:
            saved = self.saved_systems()
            if saved is None:
                return []
            now = {s.get("name") for s in self._draft.get("star_systems", [])}
            return sorted(n for n in saved if n not in now)

    def removed_described(self) -> list[str]:
        """The Removed line's entries: each removed system with what went
        with it, "Vega (4 planets)"."""
        with self._lock:
            saved = self.saved_systems() or {}
            return [name + (f" ({count})" if (count := describe_count(saved[name])) else "")
                    for name in self.removed_systems()]

    def current_refusal(self) -> Optional[dict[str, str]]:
        """The last refused Commit, while its system still fails the check:
        corrected, its mark goes without waiting for the next attempt."""
        with self._lock:
            name = (self.refusal or {}).get("system")
            system = next((s for s in (self._draft or {}).get("star_systems", [])
                           if s.get("name") == name), None) if name else None
            if system is None:
                return None
            try:
                galaxy_schema.validate({"star_systems": [_normalised(system)]})
            except ValidationError as e:
                return {"system": name, "message": str(e)}
            return None

    def unsaved_names(self) -> set[str]:
        """Systems that differ from the last Save, or are not in it: the ● in
        the Star Systems list (S2). Compared normalised, as `dirty` is, so an
        edit undone by hand counts as no change."""
        with self._lock:
            saved = self.saved_systems()
            if saved is None:
                return set()
            out = set()
            for system in self._draft.get("star_systems", []):
                before = saved.get(system.get("name"))
                if before is None or _normalised(system) != before:
                    out.add(system.get("name"))
            return out

    def revert_system(self, name: str) -> dict[str, Any]:
        """Put one system back as it was saved, stars, planets and moons
        A system not in the last Save — new, or renamed since
        — has nothing to go back to: refused (ValueError)."""
        with self.editing():
            before = (self.saved_systems() or {}).get(name)
            if before is None:
                raise ValueError(f"{name} is not in the last Save, so there is nothing to revert to")
            systems = self.edit().get("star_systems", [])
            i = next((k for k, sys in enumerate(systems) if sys.get("name") == name), None)
            if i is None:
                raise SystemNotFound(name)
            systems[i] = copy.deepcopy(before)
            self._touch()
            return systems[i]

    def _three(self) -> tuple[dict, dict, dict]:
        """The last commit, the file now, the draft — as records."""
        base = _records(json.loads(self._baseline))
        now = _records(json.loads(_normalised_text(catalogue.text())))
        mine = _records(galaxy_schema.normalise(copy.deepcopy(self._draft)))
        return base, now, mine

    def conflicts(self) -> list[dict[str, Any]]:
        """Records changed both in the file since the last commit and in the
        draft, differently: what stops a Commit, each with what differs."""
        with self._lock:
            if self._draft is None or self._baseline is None:
                return []
            base, now, mine = self._three()
            out = []
            for key in sorted(set(base) | set(now) | set(mine), key=lambda k: (k[0], str(k[1:]))):
                if base.get(key) != now.get(key) and base.get(key) != mine.get(key) and now.get(key) != mine.get(key):
                    out.append({"key": key, "id": "/".join(map(str, key)), "name": describe_record(key),
                                "differences": _differences(now.get(key), mine.get(key))})
            return out

    def _set_record(self, doc: dict[str, Any], key: tuple, value: Any) -> None:
        """Put `value` into `doc` as the record `key` (a system in its place in
        system_order); None removes the record."""
        if key[0] == "system":
            systems = doc.setdefault("star_systems", [])
            i = next((k for k, sys in enumerate(systems) if sys.get("name") == key[1]), None)
            if i is not None:
                del systems[i]
            if value is not None:
                systems.insert(_insert_at(systems, key[1]), copy.deepcopy(value))
        elif key[0] == "sector":
            names = doc.setdefault("sector_names", {})
            if value is None:
                names.pop(key[1], None)
            else:
                names[key[1]] = value
        else:
            doc["labels"] = copy.deepcopy(value or [])

    def resolve(self, record_id: str, choice: str) -> None:
        """Resolve the conflict on `record_id`: "theirs" puts the file's
        version into the draft, losing the draft's change to that record;
        "mine" keeps the draft's, which Commit then writes over the file's.
        Refused (ValueError) for a record not in conflict or another choice."""
        with self.editing():
            conflict = next((c for c in self.conflicts() if c["id"] == record_id), None)
            if conflict is None:
                raise ValueError(f"{record_id} is not in conflict")
            key = conflict["key"]
            _, now, _ = self._three()
            if choice == "theirs":
                self._set_record(self.edit(), key, now.get(key))
            elif choice == "mine":
                # The file's version becomes what the draft started from, so
                # the draft's change is the only change left for that record.
                from galaxy.jsonstore import dumps
                base_doc = json.loads(self._baseline)
                self._set_record(base_doc, key, now.get(key))
                self._baseline = dumps(galaxy_schema.normalise(base_doc))
            else:
                raise ValueError(f"Unknown choice {choice!r}")
            self._touch()

    def _touch(self) -> None:
        """Mark the draft changed: a new version for the preview, and persisted."""
        with self._lock:
            self._version += 1
            self._persist()

    # ── objects ───────────────────────────────────────────────────────────────

    def systems(self, query: str = "", hide_real: bool = False) -> list[dict[str, Any]]:
        """The systems whose name holds `query`; without the real sky's
        bright stars (galaxy.brightstars) with `hide_real`."""
        rows = self.data().get("star_systems", [])
        if query:
            q = query.strip().lower()
            rows = [s for s in rows if q in s.get("name", "").lower()]
        if hide_real:
            rows = [s for s in rows if not brightstars.is_real(s)]
        return rows

    def find(self, name: str) -> dict[str, Any]:
        """The draft's system `name`, live for editing (the draft is made if
        there is none). Refused (SystemNotFound) when there is no such system."""
        for s in self.edit().get("star_systems", []):
            if s.get("name") == name:
                return s
        raise SystemNotFound(name)

    def add_system(self, name: str, object_type: str, z: float,
                   gx: float, gy: float, spectral_class: str = "") -> dict[str, Any]:
        """Place a new object from a click on the map.

        The click gives graphic coordinates; everything in galaxy.json is
        galactic, so it is converted on the way in rather than storing a second
        coordinate system.  z cannot come from a 2D click — the projection
        ignores it — so it is supplied by the form. Refused (ValueError) without
        a name, for a name already taken, or a position outside the galaxy.
        """
        with self.editing():
            name = name.strip()
            if not name:
                raise ValueError("Name is required")

            data = self.edit()
            if any(s.get("name") == name for s in data.get("star_systems", [])):
                raise ValueError(f"A system named {name!r} already exists")

            x_gal, y_gal = CONVERTER.graphic_to_galactic(gx, gy)
            _check_position(x_gal, y_gal, z)
            system: dict[str, Any] = {
                "name": name,
                "x": int(x_gal),
                "y": int(y_gal),
                "coordinate_system": "galactic",
                "z": int(z),
            }
            # Absent object_type already means 'star' to every reader, so only write
            # it when it says something.
            if object_type and object_type != "star":
                system["object_type"] = object_type
            if spectral_class.strip():
                system["spectral_class"] = spectral_class.strip()

            systems = data.setdefault("star_systems", [])
            systems.insert(_insert_at(systems, name), system)
            self._touch()
            return system

    # ── the procedural galaxy (galaxy.procedural) ──────────────────

    def procedural(self) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        """The layer over the draft and the gate network over both, as the
        editor's maps show them: the layer and the pairs the rules link
        worked out again when the draft's systems changed (seconds), the
        links when only its stored links or blocked pairs did."""
        from galaxy import procedural
        data = self.data()
        key = json.dumps([[s.get("name"), s.get("x"), s.get("y"), s.get("z"), s.get("procedural"),
                           brightstars.is_real(s)] for s in data.get("star_systems") or []]
                         # The dots' names avoid every catalogue name, bodies' too.
                         + [sorted(procedural._taken(data))], sort_keys=True)
        links_key = json.dumps([data.get("gate_links"), data.get("gate_blocked")], sort_keys=True)
        cached = getattr(self, "_procedural", None)
        if cached is None or cached[0] != key:
            dots = procedural.layer(procedural.load(), data)
            cached = self._procedural = (key, dots, procedural.pairs(dots, data), None, [])
        if cached[3] != links_key:
            cached = self._procedural = (*cached[:3], links_key, procedural.graded(cached[2], data))
        return cached[1], cached[4]

    def uncharted(self, pid: str) -> dict[str, Any]:
        """The procedural system `pid`, whole, as it would be promoted."""
        from galaxy import procedural
        dots, _ = self.procedural()
        dot = next((d for d in dots if d["id"] == pid), None)
        if dot is None:
            raise SystemNotFound(f"{pid} is not in the procedural galaxy: promoted, or a story system took its place")
        return procedural.details(procedural.load(), dot, dots, self.data())

    def promote(self, pid: str) -> dict[str, Any]:
        """Put the procedural system `pid` into the draft, as it is: its stars,
        planets and moons, with its id (`procedural`), so the layer skips it —
        and the nebula at its heart where the layer draws one. From then on it
        is the catalogue's, edited like any other; it goes with the next Commit."""
        from galaxy import procedural
        system = self.uncharted(pid)
        # The nebula at its heart, if the layer draws one there (a remnant, a
        # planetary nebula): it comes along, the catalogue's from now on.
        dots, _ = self.procedural()
        shells = [n for n in procedural.nebulae(procedural.load(), self.data(), dots) if n.get("procedural_heart") == pid]
        with self.editing():
            data = self.edit()
            if any(s.get("name") == system["name"] for s in data.get("star_systems") or []):
                raise ValueError(f"A system named {system['name']!r} already exists")
            systems = data.setdefault("star_systems", [])
            systems.insert(_insert_at(systems, system["name"]), system)
            items = data.setdefault("nebulae", []) if shells else None
            for shell in shells:
                kept = {k: v for k, v in shell.items() if k not in ("procedural", "procedural_heart")}
                kept["heart"] = system["name"]
                kept["id"] = galaxy_schema.next_id(items, "n")
                items.append(kept)
            self._touch()
        return system

    def delete_system(self, name: str) -> None:
        """Remove the system `name` from the draft, with its gate links, blocked
        pairs and the trips that start, end or run in it. Refused
        (SystemNotFound) when there is no such system."""
        with self.editing():
            data = self.edit()
            systems = data.get("star_systems", [])
            remaining = [s for s in systems if s.get("name") != name]
            if len(remaining) == len(systems):
                raise SystemNotFound(name)
            gone = next(s for s in systems if s.get("name") == name)
            _check_medium_names([name, *(p.get("name") for p in gone.get("planets") or [])])
            data["star_systems"] = remaining
            # A nebula keeps its place, without the system at its heart.
            for nebula in data.get("nebulae") or []:
                if nebula.get("heart") == name:
                    nebula.pop("heart")
            # Its gate links go with it.
            if "gate_links" in data:
                data["gate_links"] = [link for link in data["gate_links"] if name not in (link["from"], link["to"])]
                if not data["gate_links"]:
                    data.pop("gate_links")
            if "gate_blocked" in data:
                data["gate_blocked"] = [p for p in data["gate_blocked"] if name not in (p["from"], p["to"])]
                if not data["gate_blocked"]:
                    data.pop("gate_blocked")
            # So do the trips that start, end or run in it.
            if "trips" in data:
                data["trips"] = [t for t in data["trips"] if name not in (t.get("start"), t.get("end"), t.get("system"))]
                if not data["trips"]:
                    data.pop("trips")
            self._touch()

    def update_field(self, name: str, field: str, value: str) -> dict[str, Any]:
        """Set one field of the system `name` from the form's text: x, y or z
        (whole light years, inside the galaxy; not a real star's), name (gate
        links, blocked pairs and trips follow it), spectral_class or
        object_type. Refused (ValueError) for a value that does not hold or
        another field. The system."""
        with self.editing():
            system = self.find(name)

            if field in ("x", "y", "z"):
                _movable(system)
                # OverflowError as well as ValueError: 'inf' parses as a float
                # perfectly well and only falls over at int(), which used to escape
                # as a 500. 'nan' raises ValueError and was already handled.
                # Coordinates are whole light years. 1500.7 used to be truncated
                # to 1500 while the field went on showing 1500.7; refuse it.
                if not value.strip():
                    raise ValueError(f"{field} is required")
                try:
                    number = float(value)
                    if not number.is_integer():
                        raise ValueError
                except (ValueError, OverflowError):
                    raise ValueError(f"{field} must be a whole number")
                if error := coordinate_error(field, number):
                    raise ValueError(error)
                system[field] = int(number)
            elif field == "name":
                new = value.strip()
                if not new:
                    raise ValueError("Name cannot be empty")
                if new != name and any(
                    s.get("name") == new for s in self.edit().get("star_systems", [])
                ):
                    raise ValueError(f"A system named {new!r} already exists")
                if new != name:
                    _check_medium_names([name])
                system["name"] = new
                # Gate links name systems: they follow the rename.
                for link in self.edit().get("gate_links") or []:
                    for end in ("from", "to"):
                        if link[end] == name:
                            link[end] = new
                for pair in self.edit().get("gate_blocked") or []:
                    for end in ("from", "to"):
                        if pair[end] == name:
                            pair[end] = new
                for trip in self.edit().get("trips") or []:
                    for key in ("start", "end", "system"):
                        if trip.get(key) == name and (key == "system" or not trip.get("system")):
                            trip[key] = new
                # A nebula's heart names a system: it follows the rename.
                for nebula in self.edit().get("nebulae") or []:
                    if nebula.get("heart") == name:
                        nebula["heart"] = new
                # A rename can move a system in the ordering; put it where it now
                # belongs rather than leaving the array subtly out of order.
                systems = self.edit()["star_systems"]
                systems.remove(system)
                systems.insert(_insert_at(systems, new), system)
            elif field == "spectral_class":
                # Checked here as an editor's form does, rather than only at
                # Save, where the error arrived far from the field.
                v = galaxy_schema.normalise_spectral(value)
                if v:
                    galaxy_schema.check_spectral(v)
                    system["spectral_class"] = v
                else:
                    system.pop("spectral_class", None)
            elif field == "object_type":
                v = value.strip()
                if v and v != "star":
                    system["object_type"] = v
                else:
                    system.pop("object_type", None)
            else:
                raise ValueError(f"Unknown field {field!r}")

            self._touch()
            return system

    def move_system(self, name: str, gx: float, gy: float) -> dict[str, Any]:
        """Reposition a system from a drag on the map.

        Only x and y: the 2D projection ignores z, so a drag carries no
        information about it and must leave it alone.
        """
        with self.editing():
            system = self.find(name)
            _movable(system)
            x_gal, y_gal = CONVERTER.graphic_to_galactic(gx, gy)
            _check_position(x_gal, y_gal)
            system["x"] = int(x_gal)
            system["y"] = int(y_gal)
            self._touch()
            return system

    def set_position(self, name: str, x: int, y: int) -> dict[str, Any]:
        """Put a system at exact galactic coordinates — the Undo of a drag.

        Not `move_system` with the old graphic position: that goes through
        graphic→galactic rounding and lands a light year off.
        """
        with self.editing():
            system = self.find(name)
            _movable(system)
            system["x"] = int(x)
            system["y"] = int(y)
            self._touch()
            return system

    @staticmethod
    def transform() -> dict[str, float]:
        """The linear graphic<->galactic transform, for the drag readout.

        The client needs it to show live galactic coordinates while dragging.
        Derived from the same converter the server uses rather than restated, so
        the readout cannot drift from what actually gets stored.
        """
        cx = CONVERTER.center_graphic["x"]
        cy = CONVERTER.center_graphic["y"]
        return {
            "cx": cx,
            "cy": cy,
            "fx": (CONVERTER.sol_graphic["x"] - cx) / CONVERTER.sol_galactic["x"],
            "fy": (CONVERTER.sol_graphic["y"] - cy) / CONVERTER.sol_galactic["y"],
        }

    # ── sector names ──────────────────────────────────────────────────────────

    def sector_names(self) -> list[tuple[str, str]]:
        """Named sectors in the order galaxy.json stores them."""
        names = self.data().get("sector_names", {})
        return sorted(names.items(), key=lambda kv: _sector_order(kv[0]))

    def set_sector_name(self, sector_id: str, name: str) -> None:
        """Name a sector — which is also what makes the renderer outline it red.
        Refused (ValueError) for an id not on the grid or an empty name."""
        with self.editing():
            sector_id = sector_id.strip().upper()
            if sector_id not in galaxy_schema.SECTOR_ID_SET:
                raise ValueError(f"{sector_id!r} is not a sector on the grid")
            name = name.strip()
            if not name:
                raise ValueError("Sector name cannot be empty")

            data = self.edit()
            names = dict(data.get("sector_names", {}))
            names[sector_id] = name
            # Rebuilt in order rather than appended, so a new entry lands where the
            # file's convention puts it instead of at the end.
            data["sector_names"] = {k: names[k] for k in sorted(names, key=_sector_order)}
            self._touch()

    def saved_sector_names(self) -> Optional[dict[str, str]]:
        """The sector names as last committed — None with nothing drafted —
        for marking the changed and new rows."""
        with self._lock:
            if self._baseline is None:
                return None
            return json.loads(self._baseline).get("sector_names", {})

    def delete_sector_name(self, sector_id: str) -> None:
        """Remove sector `sector_id`'s name. Refused (SystemNotFound) when it
        has none."""
        with self.editing():
            # Normalised the same way set_sector_name does it. Without this the two
            # disagreed: naming 'a7' worked and stored 'A7', while clearing 'a7'
            # reported that it was not named.
            sector_id = sector_id.strip().upper()
            names = self.edit().get("sector_names", {})
            if sector_id not in names:
                raise SystemNotFound(sector_id)
            del names[sector_id]
            self._touch()

    # ── nebulae ───────────────────────────
    #
    # Regions, not systems: a list of their own, edited here as sectors are.

    def nebulae(self) -> list[dict[str, Any]]:
        """The draft's nebulae (the saved file's while nothing is drafted)."""
        return self.data().get("nebulae") or []

    def nebula(self, nid: str) -> dict[str, Any]:
        """Nebula `nid` of the draft, live for editing. Refused
        (SystemNotFound) when there is none."""
        for nebula in self.edit().get("nebulae") or []:
            if nebula.get("id") == nid:
                return nebula
        raise SystemNotFound(f"nebula {nid}")

    def _check_nebula_names(self) -> None:
        """Refuse (ValueError) a nebula's name taken by another, a system or a
        body — the schema's own check, said as a refusal."""
        try:
            galaxy_schema.check_names(self.edit())
        except ValidationError as e:
            raise ValueError(str(e))

    def add_nebula(self, name: str, kind: str, x: float, y: float, z: float = 0.0) -> dict[str, Any]:
        """Add a nebula of `kind` named `name`, centred at galaxy coordinates
        (ly), 10 ly across each way until its size is given. Refused
        (ValueError) for an empty or taken name, an unknown kind or a place
        outside the galaxy. The nebula."""
        with self.editing():
            name = name.strip()
            if not name:
                raise ValueError("Name cannot be empty")
            nebula = {"name": name, "kind": kind, "x": round(float(x), 1), "y": round(float(y), 1),
                      "z": round(float(z), 1), "size": [10, 10, 10]}
            for field in ("kind", "x", "y", "z"):
                if error := nebulae.field_error(field, nebula[field]):
                    raise ValueError(error[0].upper() + error[1:])
            items = self.edit().setdefault("nebulae", [])
            nebula["id"] = galaxy_schema.next_id(items, "n")
            items.append(nebula)
            try:
                self._check_nebula_names()
            except ValueError:
                items.remove(nebula)
                if not items:
                    self.edit().pop("nebulae")
                raise
            self._touch()
            return nebula

    def set_nebula_field(self, nid: str, field: str, value: str) -> None:
        """Set nebula `nid`'s `field` from the form's text: name, kind, x, y,
        z, size or tilt (one number, or three: "30, 20, 12"), density or
        colour (cleared, the kind's), heart (a system's name; cleared, none).
        Refused (ValueError) for a value that does not hold, and a real
        nebula's place or size, which are the sky's."""
        with self.editing():
            nebula = self.nebula(nid)
            text = value.strip()
            if nebula.get("real") and field in ("x", "y", "z", "size"):
                raise ValueError(f"{nebula['name']} is the real sky's ({nebula['real']}): its place and size are the sky's")
            if field in ("density", "colour", "heart") and not text:
                nebula.pop(field, None)
                self._touch()
                return
            if field in ("x", "y", "z", "density"):
                new: Any = _number(text, "ly" if field != "density" else "")
            elif field in ("size", "tilt"):
                parts = [_number(t, "ly" if field == "size" else "°") for t in text.replace(";", ",").split(",") if t.strip()]
                new = parts * 3 if len(parts) == 1 else parts
                new = [int(v) if float(v).is_integer() else v for v in new]
            elif field in ("name", "kind", "colour", "heart"):
                new = text
            else:
                raise ValueError(f"Unknown nebula field {field!r}")
            if error := nebulae.field_error(field, new):
                raise ValueError(error[0].upper() + error[1:])
            if field == "heart" and new not in {s.get("name") for s in self.edit().get("star_systems") or []}:
                raise ValueError(f"{new} is not a system")
            if field == "density" and float(new).is_integer():
                new = int(new)
            old = nebula.get(field)
            nebula[field] = new
            if field == "name":
                try:
                    self._check_nebula_names()
                except ValueError:
                    nebula[field] = old
                    raise
            self._touch()

    def place_nebula(self, name: str, kind: str, z: float, gx: float, gy: float) -> dict[str, Any]:
        """Add a nebula where the 2D map was clicked (graphic `gx`, `gy`), at
        height `z` — as add_system places a system."""
        x, y = CONVERTER.graphic_to_galactic(gx, gy)
        return self.add_nebula(name, kind, x, y, z)

    def add_real_nebulae(self) -> list[str]:
        """Add the real sky's nebulae the draft lacks, and put those in back to
        the sky's place and size (galaxy.nebulae.add_real). The names added."""
        with self.editing():
            doc = self.edit()
            moved = not nebulae.real_current(doc)
            added = nebulae.add_real(doc)
            galaxy_schema.normalise(doc)
            self._check_nebula_names()
            if added or moved:
                self._touch()
            return added

    def nebulae_overlay(self) -> list[dict[str, Any]]:
        """The nebulae in graphic coordinates, for the 2D map's overlay: the
        centre, the ellipse's semi-axes in the plane (x, y; turned by the
        tilt's third angle) and its colour."""
        fx, fy = abs(self.transform()["fx"]), abs(self.transform()["fy"])
        out = []
        for n in self.data().get("nebulae") or []:
            gx, gy = CONVERTER.galactic_to_graphic(n["x"], n["y"])
            out.append({"id": n["id"], "name": n["name"], "kind": n["kind"], "gx": round(gx, 2), "gy": round(gy, 2),
                        "rx": round(n["size"][0] * fx, 3), "ry": round(n["size"][1] * fy, 3),
                        "angle": (n.get("tilt") or [0, 0, 0])[2], "colour": nebulae.colour(n),
                        "real": bool(n.get("real"))})
        return out

    def nebulae_unsaved(self) -> bool:
        """Whether the draft's nebulae differ from the committed file's."""
        with self._lock:
            if self._baseline is None:
                return False
            return (json.loads(self._baseline).get("nebulae") or []) != (self.data().get("nebulae") or [])

    def delete_nebula(self, nid: str) -> None:
        """Remove nebula `nid`; the last one takes the list with it."""
        with self.editing():
            items = self.edit().get("nebulae") or []
            nebula = self.nebula(nid)
            items.remove(nebula)
            if not items:
                self.edit().pop("nebulae")
            self._touch()

    # ── planet maps ───────────────────────────────────────────────────────────
    #
    # A planet's map is the folder <planet_maps>/<slug of its name>/, its
    # files named <slug>.*. A rename is recorded and Commit moves the folder
    # along, so the map is never left attached to nothing. Keyed by slug,
    # never by the stable body id, because that is how a map is found.

    def map_folder(self, planet_name: Optional[str]) -> Optional[Path]:
        """The map folder a planet of this name has: its own, or the one a
        rename in the draft takes along to it at the next Commit."""
        slug, maps = slugify(planet_name), project.current().planet_maps
        if not slug or maps is None:
            return None
        with self._lock:
            source = next((old for old, new in self._map_moves.items() if new == slug), None)
        folder = maps / (source or slug)
        return folder if folder.is_dir() else None

    def pending_map_moves(self) -> dict[str, str]:
        """The map folders the next Commit moves: {old slug: new slug}."""
        with self._lock:
            return dict(self._map_moves)

    def _note_rename(self, old_name: str, new_name: str) -> None:
        """Record that a planet's map follows its rename (inside an edit).
        Renamed twice, the move goes from the first name to the last; renamed
        back, there is nothing to move."""
        old, new = slugify(old_name), slugify(new_name)
        if not old or old == new or project.current().planet_maps is None:
            return
        source = next((o for o, n in self._map_moves.items() if n == old), None)
        if source is not None:
            del self._map_moves[source]
        elif (project.current().planet_maps / old).is_dir():
            source = old
        else:
            return
        if source != new:
            self._map_moves[source] = new

    def _move_maps(self, draft: dict[str, Any]) -> list[str]:
        """Move the map folders of renamed planets (at Commit). Only where
        the draft still says so — the new name present, the old one gone (a
        per-system Discard puts it back) — and nothing is in the way."""
        names = {slugify(p.get("name")) for s in draft.get("star_systems", [])
                 for p in s.get("planets") or []}
        moved, maps = [], project.current().planet_maps
        for old, new in self._map_moves.items():
            src, dst = maps / old, maps / new
            if new not in names or old in names or not src.is_dir() or dst.exists():
                continue
            src.rename(dst)
            for f in sorted(dst.iterdir()):
                if f.name.startswith(old + "."):
                    f.rename(dst / (new + f.name[len(old):]))
            moved.append(f"{project.current().relative(src)} → {project.current().relative(dst)}")
        return moved

        # ── preview ───────────────────────────────────────────────────────────────

    def overlay(self) -> list[dict[str, Any]]:
        """Objects in graphic coordinates, for the interactive overlay.

        The backdrop is a 400 KB SVG served as an image and never parsed into
        the DOM; the overlay is this, which is a few KB.
        """
        out = []
        for s in self.data().get("star_systems", []):
            if s.get("coordinate_system", "graphic") == "galactic":
                gx, gy = CONVERTER.galactic_to_graphic(s.get("x", 0), s.get("y", 0))
            else:
                gx, gy = s.get("x", 0), s.get("y", 0)
            out.append({
                "name": s.get("name", ""),
                "type": s.get("object_type") or "star",
                "spectral_class": s.get("spectral_class") or "",
                "gx": round(gx, 2),
                "gy": round(gy, 2),
                "real": brightstars.is_real(s),
            })
        return out

    def preview_svg(self) -> bytes:
        """Render the *working copy* — unsaved edits included.

        Rendering takes ~78 ms and is byte-reproducible, so there is no reason
        to show an approximation of the map when the real one is this cheap.
        Cached against the edit version so panning and zooming do not re-render.
        """
        with self._lock:
            cached = self._preview
            version = self._version
        if cached is not None and cached[0] == version:
            return cached[1]

        data = self.data()
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "galaxy.json"
            out = Path(tmp) / "galaxy.svg"
            src.write_text(json.dumps(data), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "galaxy.cli.galaxy_generate", "-i", str(src), "-o", str(out),
                 "-w", str(CANVAS), "--height", str(CANVAS)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"preview render failed: {result.stderr.strip()}")
            svg = out.read_bytes()

        with self._lock:
            self._preview = (version, svg)
        return svg

    # ── persistence ───────────────────────────────────────────────────────────

    def save(self) -> tuple[bool, bool]:
        """Validate, write galaxy.json, regenerate the SVG.

        Returns (json_written, svg_written).  Raises ValidationError, in which
        case nothing is written and the draft is left intact to be corrected;
        ConflictError likewise where the file changed in records the draft
        changed too. What changed only in the file is taken in (`merged`).
        """
        # Held for the whole save, including the write and the ~75ms SVG render.
        # An edit landing between normalise() and store.write() would be written
        # without having been validated; one landing after the write would be
        # silently dropped when the draft is cleared below. Blocking edits for
        # the duration of a save is the intended behaviour, not a cost.
        with self._lock:
            draft = self._draft
            if draft is None:
                return (False, False)

            # The draft was copied from the file as it stood when editing began.
            # If the file has moved on since — a hand edit, a CLI run, git —
            # writing the draft would silently discard that. Per record:
            # what changed only in the file is taken into the commit; what
            # changed in both, differently, stops it until resolved.
            self.merged = []
            self.moved = []
            self.refusal = None
            if self._baseline is not None:
                conflicts = self.conflicts()
                if conflicts:
                    names = ", ".join(c["name"] for c in conflicts)
                    raise ConflictError(
                        f"galaxy.json changed on disk where your draft changed too: {names}. "
                        "Nothing was written — choose for each which version to keep.", conflicts)
                base, now, mine = self._three()
                for key in set(base) | set(now):
                    if base.get(key) != now.get(key) and base.get(key) == mine.get(key):
                        self._set_record(draft, key, now.get(key))
                        self.merged.append(describe_record(key))

            galaxy_schema.normalise(draft)
            try:
                wrote = catalogue.write(draft, validator=_validate)
            except ValidationError as e:
                self.refusal = {"system": _system_named_in(str(e), draft), "message": str(e)}
                raise
            if wrote:
                self.publish_copy()
            self.moved = self._move_maps(draft)

            # Also when galaxy.json is newer than the SVG: a render that failed
            # after the write leaves the file unchanged for the retry, which
            # would otherwise skip the render and keep the stale map for good.
            svg_written = self.render_svg() if wrote or self._svg_stale() else False

            self._draft = None
            self._baseline = None
            self._map_moves = {}
            self._version += 1
            self._persist()
            return (wrote, svg_written)

    @staticmethod
    def _svg_stale() -> bool:
        """Whether the published SVG is missing or older than galaxy.json."""
        svg, own = project.current().svg, project.current().catalogue
        return (svg is not None and svg.parent.exists() and own.exists()
                and (not svg.exists() or svg.stat().st_mtime < own.stat().st_mtime))

    @staticmethod
    def publish_copy() -> None:
        """Copy galaxy.json to where the 3D map fetches it, so the dev site
        shows a save without a rebuild — as committing a map publishes it.
        The build does the same."""
        public = project.current().public
        if public is not None and public.exists():
            # The layers merged: the maps read the whole catalogue.
            text = catalogue.text()
            write_atomic(public / "galaxy.json", text)
            # And what the star-system map draws from it (galaxy.systemmap).
            from galaxy import systemmap
            doc = json.loads(text)
            systemmap.write(doc, public / "systems.json")
            # And the stored trips' routes (galaxy.trips).
            galaxy_trips.write(doc, public / "trips.json")

    def render_svg(self) -> bool:
        """Regenerate the published galaxy SVG from what is now on disk.

        Run as a subprocess rather than in-process: the renderer registers
        namespaces on ElementTree globally, and generation is ~78 ms, so there is
        nothing to gain from sharing the interpreter and something to lose.
        """
        svg = project.current().svg
        if svg is None or not svg.parent.exists():
            return False
        # The layers merged, in a file the renderer reads.
        with tempfile.TemporaryDirectory() as tmp:
            merged = Path(tmp) / "galaxy.json"
            merged.write_text(catalogue.text(), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "galaxy.cli.galaxy_generate", "-i", str(merged), "-o", str(svg)],
                capture_output=True,
                text=True,
            )
        if result.returncode != 0:
            raise RuntimeError(f"galaxy SVG generation failed: {result.stderr.strip()}")
        return True


def _has_map_folder(name: str) -> bool:
    """Whether the project has a map folder under `name`'s slug."""
    maps = project.current().planet_maps
    return maps is not None and (maps / slugify(name)).is_dir()


def _normalised(system: dict[str, Any]) -> dict[str, Any]:
    """One system as Save would write it, for comparing with the saved file."""
    return galaxy_schema.normalise({"star_systems": [copy.deepcopy(system)]})["star_systems"][0]


def _check_medium_names(names: list[Optional[str]]) -> None:
    """Refuse (ValueError) to rename or remove a planet or system that a
    region of the medium's field names: travel planning would
    lose it."""
    field = medium.load()
    for name in names:
        regions = medium.naming(field, name) if name not in (None, "?") else []
        if regions:
            raise ValueError(f"{', '.join(regions)} in {medium.file_name()} names {name} — "
                             "change it there first")


def _validate(doc: dict[str, Any]) -> None:
    """Refuse (ValidationError) what galaxy_schema.validate refuses, and a
    galaxy without a planet or system the medium's field names."""
    galaxy_schema.validate(doc)
    try:
        medium.check(medium.load(), medium.places(doc))
    except ValueError as e:
        raise ValidationError(str(e)) from None


def describe_count(system: dict[str, Any]) -> str:
    """What a system holds, counted: "4 planets, 2 moons", or ""."""
    planets = system.get("planets") or []
    moons = sum(len(p.get("moons") or []) for p in planets)
    parts = [f"{n} {word}{'s' if n != 1 else ''}" for n, word in ((len(planets), "planet"), (moons, "moon")) if n]
    return ", ".join(parts)


def describe_contents(system: dict[str, Any]) -> str:
    """What goes with a system when it is removed, for its confirm and
    toast: " and its 4 planets (Mercury, Venus, …) and 2
    moons", or ""."""
    planets = system.get("planets") or []
    if not planets:
        return ""
    named = [p["name"] for p in planets if p.get("name") not in (None, "", "?")]
    moons = sum(len(p.get("moons") or []) for p in planets)
    text = f" and its {len(planets)} planet{'s' if len(planets) != 1 else ''}"
    if named:
        text += f" ({', '.join(named[:3])}{', …' if len(named) > 3 or len(named) < len(planets) else ''})"
    if moons:
        text += f" and {moons} moon{'s' if moons != 1 else ''}"
    return text


def _system_named_in(message: str, doc: dict[str, Any]) -> str:
    """The system a validation message is about, or "": the schema starts
    its messages with the system's name ("Vega: star 2 needs a name")."""
    names = sorted((s.get("name") or "" for s in doc.get("star_systems", [])), key=len, reverse=True)
    return next((n for n in names if n and message.startswith((n + ":", n + ","))), "")


def _sector_order(sector_id: str) -> tuple[int, int]:
    """The order galaxy.json keeps sector names in: centre first, then by beam
    letter, then by ring.

    Verified against the file — its eight original entries are exactly
    0, A7, A8, I3, W6, W7, W10, X7, which is letter-major. A plain string sort
    would put W10 before W6, and a ring-major sort disagrees with the file.
    """
    if sector_id == "0":
        return (0, 0)
    return (ord(sector_id[0]), int(sector_id[1:] or 0))


_insert_at = catalogue.insert_at


# ── star system detail ────────────────────────────────────────────────────────
#
# Stars, planets and moons are addressed by array position. `index` is derived
# from position on save (see galaxy_schema._renumber), so it is data rather than
# an identifier and must not be used to address anything.

def _check_position(x: float, y: float, z: float = 0) -> None:
    """Refuse (ValueError) a position outside the galaxy (schema.COORDINATE_LIMITS)."""
    for axis, value in (("x", x), ("y", y), ("z", z)):
        if error := coordinate_error(axis, value):
            raise ValueError(error)


def _hosted(system: dict[str, Any]) -> list[dict[str, Any]]:
    """Everything that may name a host: companion stars, planets, belts, and
    the anchors of points of interest around a star."""
    return ((system.get("stars") or [])[1:] + list(system.get("planets") or []) + list(system.get("belts") or [])
            + [p["anchor"] for p in system.get("points_of_interest") or [] if isinstance(p.get("anchor"), dict)])


def _bodies(system: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """The system's list under `key`, made empty where it has none."""
    return system.setdefault(key, [])


class SystemDetail:
    """Editing operations for one system's stars, planets and moons.

    Split out from GalaxySession only for readability; it works on the same
    draft, so edits here are part of the same explicit-save cycle.
    """

    def __init__(self, session: "GalaxySession") -> None:
        self.s = session
        # A point of interest's last position at each body, for the session
        # (set_poi_field): (system, id, body[, "orbit" | "point"]) → anchor.
        self._anchor_memo: dict[tuple, dict[str, Any]] = {}

    # ── stars ─────────────────────────────────────────────────────────────────

    def stars_view(self, system: dict[str, Any]) -> list[dict[str, Any]]:
        """Stars as the UI shows them.

        A system with no `stars` array is still a single star — it just has
        nowhere to record a name yet. Presenting one synthetic row means the
        name field exists to be filled in, which is what materialises the array.
        """
        stars = system.get("stars")
        if stars:
            return stars
        return [{"name": "", "spectral_class": system.get("spectral_class", "")}]

    def _materialise_stars(self, system: dict[str, Any]) -> list[dict[str, Any]]:
        """The system's `stars`, made where it has none: one unnamed star with
        the system's spectral class."""
        if not system.get("stars"):
            system["stars"] = [{
                "name": "",
                "spectral_class": system.get("spectral_class", ""),
            }]
        return system["stars"]

    def add_star(self, name: str) -> dict[str, Any]:
        """Add a companion.

        The primary is seeded from `spectral_class` and, if still unnamed, from
        the system name — a reasonable starting point that is freely
        editable, since a catalogue may name companions independently:
        Alpha Centauri is Rigil Kentaurus + Toliman.
        """
        with self.s.editing():
            system = self.s.find(name)
            stars = self._materialise_stars(system)
            if not stars[0].get("name"):
                stars[0]["name"] = name
            # No spectral_class key at all: unknown is absent, not empty. An empty
            # string would fail validation, and every consumer treats absent as
            # "not recorded" already.
            stars.append({"name": ""})
            self.s._touch()
            return system

    def delete_star(self, name: str, i: int) -> dict[str, Any]:
        """Remove star `i` of system `name`: what orbited it, or a group with it,
        orbits the primary now; the system's class follows a new primary.
        Refused (ValueError) for the last star. The system."""
        with self.s.editing():
            system = self.s.find(name)
            stars = system.get("stars") or []
            if not 0 <= i < len(stars):
                raise SystemNotFound(f"{name} star {i}")
            if len(stars) == 1:
                raise ValueError("A system needs at least one star")
            gone = (stars[i].get("name") or "").strip()
            del stars[i]
            # What orbited it, or a group with it, orbits the primary now.
            for item in _hosted(system):
                if gone and gone in hierarchy.names_of(item.get("host") or ""):
                    item.pop("host", None)
            # spectral_class mirrors the primary, so removing star 0 changes which
            # star it reflects. If the promoted star has none recorded, it adopts
            # the system's rather than leaving the system describing a star that is
            # no longer there.
            if stars[0].get("spectral_class"):
                system["spectral_class"] = stars[0]["spectral_class"]
            elif system.get("spectral_class"):
                stars[0]["spectral_class"] = system["spectral_class"]
            self.s._touch()
            return system

    def set_star_orbit(self, name: str, i: int, field: str, value: str) -> None:
        """Set one element of companion star `i`'s orbit around its host, in
        AU and degrees (galaxy.orbits). Refused (ValueError) for the primary,
        which has none."""
        with self.s.editing():
            system = self.s.find(name)
            stars = system.get("stars") or []
            if not 1 <= i < len(stars):
                raise ValueError("Only a companion star orbits — the primary is what it orbits")
            self._set_orbit(stars[i], field, value, moon=False)
            self.s._touch()

    def set_host(self, name: str, item: dict[str, Any], value: str, system: dict[str, Any]) -> None:
        """Set what a companion star, planet, belt or point of interest orbits:
        a star or a group the system's stars make (galaxy.hierarchy); the
        primary is the default and goes unwritten. Refused (ValueError) when
        the stars would not make it — a star around itself, say."""
        value = value.strip()
        before = item.get("host")
        if not value or hierarchy.names_of(value) == {hierarchy.primary_name(system)}:
            item.pop("host", None)
        else:
            if error := galaxy_schema.host_error(value):
                raise ValueError(error[0].upper() + error[1:])
            bodies.set_field(item, "host", value)
        t = hierarchy.tree(system)
        if t.unplaced or (item.get("host") and t.node(hierarchy.names_of(item["host"])) is None):
            if before is None:
                item.pop("host", None)
            else:
                item["host"] = before
            raise ValueError(f"{value} is not something {name}'s stars make — one of "
                             + ", ".join(hierarchy.hosts(system)))

    def set_star_host(self, name: str, i: int, value: str) -> Optional[str]:
        """Set what companion star `i` orbits (`_rehost`), its orbit drawn
        again. What else changed, in words, or None. Refused (ValueError) for
        the primary."""
        with self.s.editing():
            system = self.s.find(name)
            stars = system.get("stars") or []
            if not 1 <= i < len(stars):
                raise ValueError("Only a companion star orbits — the primary is what it orbits")
            note = self._rehost(name, stars[i], value, system)
            self.s._touch()
            return note

    def _rehost(self, name: str, item: dict[str, Any], value: str, system: dict[str, Any]) -> Optional[str]:
        """Give a planet or companion a new host, and draw its orbit again
        around it: the old one was measured from the old host. What changed,
        in words, or None."""
        before = item.get("host")
        self.set_host(name, item, value, system)
        self.s._touch()
        if item.get("host") == before or not item.get("orbit"):
            return None
        old = item.pop("orbit")
        if orbits.draw_system(system) and item.get("orbit"):
            return f"Orbit drawn again around {item.get('host') or hierarchy.primary_name(system)}: {item['orbit']['au']} AU"
        item["orbit"] = old
        return None

    def set_all_hosts(self, name: str, value: str) -> int:
        """Put every planet around one host, and draw the planets' and
        companions' orbits again for it (galaxy.orbits.draw_system): an S-type
        system made P-type wants its stars closer, and the other way round.
        Moons keep theirs. How many orbits were drawn. Refused (ValueError)
        in a system without planets."""
        with self.s.editing():
            system = self.s.find(name)
            planets = system.get("planets") or []
            if not planets:
                raise ValueError(f"{name} has no planets")
            for planet in planets:
                self.set_host(name, planet, value, system)
            for item in planets + (system.get("stars") or [])[1:]:
                item.pop("orbit", None)
            count = orbits.draw_system(system)
            self.s._touch()
            return count

    def draw_arrangement(self, name: str) -> str:
        """Draw the stars' arrangement whole (galaxy.orbits); what was
        drawn, in words."""
        with self.s.editing():
            words = orbits.draw_arrangement(self.s.find(name))
            self.s._touch()
            return words

    def draw_star_class(self, name: str, i: int) -> tuple[str, bool]:
        """Draw star `i`'s spectral class: the primary's as the authored systems
        have theirs (galaxy.procedural's model), a
        companion's from the primary's mass (galaxy.stars), and its orbit if
        it has none. The class, and whether an orbit was drawn. Refused
        (ValueError) for a real star's primary, whose class is the sky's, or
        a companion while the primary has no class."""
        with self.s.editing():
            system = self.s.find(name)
            stars = system.get("stars") or []
            if i == 0:
                if brightstars.is_real(system):
                    raise ValueError(f"{name} is a real star: its class is the sky's")
                from galaxy import procedural
                drawn = random.choice(procedural.load()["classes"])
                self.set_star_field(name, 0, "spectral_class", drawn)
                return drawn, False
            if not 1 <= i < len(stars):
                raise ValueError(f"{name} has no star {i + 1}")
            main = star_data.primary(system)
            if main is None:
                raise ValueError("The primary star needs a spectral class first")
            drawn = star_data.draw_companion_class(main, random.Random())
            self.set_star_field(name, i, "spectral_class", drawn)
            orbited = orbits.draw_companions(self.s.find(name)) > 0
            if orbited:
                self.s._touch()
        return drawn, orbited

    def generate_system(self, name: str) -> str:
        """Generate system `name` whole, in place: a primary
        class and a number of planets as the authored systems have them, and the
        rest as the procedural galaxy makes its systems (procedural.details) —
        companions, orbits, classes, sizes, moons, rings, names new to the
        galaxy. Its name and place stay; its stars, planets, belts and points
        of interest go. Refused (ValueError) for a real star, an object that
        is no star, a planet with a map or a name the medium's field uses. What
        was made, in words."""
        from galaxy import procedural
        with self.s.editing():
            system = self.s.find(name)
            if brightstars.is_real(system):
                raise ValueError(f"{name} is a real star: its stars are the sky's — add planets one by one")
            if (system.get("object_type") or "star") != "star":
                raise ValueError(f"{name} is a {system['object_type'].replace('_', ' ')}, not a star system")
            planets = system.get("planets") or []
            mapped = [p["name"] for p in planets if p.get("name") not in (None, "?")
                      and _has_map_folder(p["name"])]
            if mapped:
                raise ValueError(f"{', '.join(mapped)} {'has a map' if len(mapped) == 1 else 'have maps'} — "
                                 "a system with mapped planets is not generated anew")
            _check_medium_names([p.get("name") for p in planets])
            model, rng = procedural.load(), random.Random()
            cls = rng.choice(model["classes"])
            count = rng.choice([n for n in model["planet_counts"] if n] or [1])
            # A dot of the procedural galaxy, in this system's place: an id of
            # its own, so each draw differs.
            dot = {"id": f"generated-{rng.randrange(10 ** 9)}", "name": name, "x": system["x"], "y": system["y"],
                   "z": system["z"], "spectral_class": cls, "planet_count": count}
            made = procedural.details(model, dot, [], self.s.edit())
            for key in ("stars", "planets", "belts", "points_of_interest", "spectral_class"):
                system.pop(key, None)
            system["spectral_class"] = cls
            for key in ("stars", "planets"):
                if made.get(key):
                    system[key] = made[key]
            orbits.draw_belts(system, rng)
            galaxy_schema.normalise({"star_systems": [system]})
            self.s._touch()
            stars = system.get("stars") or [{}]
            moons = sum(len(p.get("moons") or []) for p in system.get("planets") or [])
            belts = len(system.get("belts") or [])
            return (f"{len(stars)} star{'s' if len(stars) > 1 else ''} ({cls}"
                    f"{', ' + ', '.join(st.get('spectral_class') or '?' for st in stars[1:]) if len(stars) > 1 else ''}), "
                    f"{count} planet{'s' if count != 1 else ''}, {moons} moon{'s' if moons != 1 else ''}"
                    + (f", {belts} belt{'s' if belts != 1 else ''}" if belts else ""))

    def fill_system(self, name: str) -> Optional[str]:
        """Fill in what system `name` lacks, keeping what it has
        (procedural.fill_in). Refused (ValueError) for an
        object around which nothing orbits. What was added, in words, or None
        when nothing was missing."""
        from galaxy import procedural
        with self.s.editing():
            system = self.s.find(name)
            if star_data.primary(system) is None and (system.get("object_type") or "star") != "star":
                raise ValueError(f"{name} is a {system['object_type'].replace('_', ' ')}: nothing orbits it")
            before = json.dumps(system, sort_keys=True)

            def tally(s: dict[str, Any]) -> dict[str, int]:
                planets = s.get("planets") or []
                return {"planet": len(planets), "moon": sum(len(p.get("moons") or []) for p in planets),
                        "ring": sum(1 for p in planets if p.get("rings")), "belt": len(s.get("belts") or []),
                        "class": sum(1 for p in planets for b in [p] + (p.get("moons") or []) if b.get("class"))
                                 + sum(1 for st in s.get("stars") or [] if st.get("spectral_class")),
                        "orbit": sum(1 for p in planets for b in [p] + (p.get("moons") or []) if b.get("orbit"))
                                 + sum(1 for st in (s.get("stars") or [])[1:] if st.get("orbit"))}
            was = tally(system)
            procedural.fill_in(system, procedural.load(), random.Random())
            if json.dumps(system, sort_keys=True) == before:
                return None
            self.s._touch()
            now = tally(system)
            words = {"planet": ("planet", "planets"), "moon": ("moon", "moons"),
                     "ring": ("planet with rings", "planets with rings"), "belt": ("belt", "belts"),
                     "class": ("class", "classes"), "orbit": ("orbit", "orbits")}
            said = [f"{now[k] - was[k]} {one if now[k] - was[k] == 1 else many}"
                    for k, (one, many) in words.items() if now[k] > was[k]]
            return ", ".join(said) or "radii and axial tilts"

    def draw_body_class(self, name: str, i: int, j: Optional[int] = None) -> tuple[str, Optional[str]]:
        """Draw a class for planet `i`, or its moon `j` (orbits.draw_class:
        fitting its orbit, never habitable), and set it as a typed one is — its
        radius drawn to fit. A planet's is drawn again (DRAW_TRIES) while it
        leaves the planet unstable beside a neighbour. The class, and what else
        changed in words."""
        with self.s.editing():
            if j is not None:
                drawn = orbits.draw_class(self.s.find(name), self._planet(self.s.find(name), i), moon=True)
                return drawn, self.set_moon_field(name, i, j, "class", drawn)
            # A draw that would leave the planet too close to a neighbour to
            # keep its orbit — giants side by side — is drawn again.
            def unstable() -> bool:
                system = self.s.find(name)
                label = orbits.label(self._planet(system, i))
                return any(kind == "orbit-spacing" and not note and label in m.split(":")[0].split(" and ")
                           for kind, m, note in orbits.findings(system))
            for _ in range(DRAW_TRIES):
                system = self.s.find(name)
                drawn = orbits.draw_class(system, self._planet(system, i))
                note = self.set_planet_field(name, i, "class", drawn)
                if not unstable():
                    break
            return drawn, note

    def draw_look(self, name: str, i: int, j: Optional[int] = None) -> int:
        """Draw another look for planet `i`, or its moon `j`: another palette
        of its class and another pattern (planet-look.js). The look drawn."""
        with self.s.editing():
            planet = self._planet(self.s.find(name), i)
            body = planet
            if j is not None:
                moons = planet.get("moons") or []
                if not 0 <= j < len(moons):
                    raise SystemNotFound(f"moon {j}")
                body = moons[j]
            old = body.get("look")
            look = old
            while look == old:
                look = random.randrange(galaxy_schema.LOOK_LIMIT)
            bodies.set_field(body, "look", look)
            self.s._touch()
            return look

    def draw_classes(self, name: str) -> int:
        """Draw a class for every planet and moon of the system without one;
        a class already set, habitable or not, is kept. How many were drawn."""
        with self.s.editing():
            system = self.s.find(name)
            count = 0
            for i, planet in enumerate(system.get("planets") or []):
                if not planet.get("class"):
                    self.draw_body_class(name, i)
                    count += 1
                for j, moon in enumerate(planet.get("moons") or []):
                    if not moon.get("class"):
                        self.draw_body_class(name, i, j)
                        count += 1
            return count

    def set_star_field(self, name: str, i: int, field: str, value: str) -> dict[str, Any]:
        """Set star `i`'s name (hosts follow a rename) or spectral class (the
        primary's is the system's too). Refused (ValueError) for a name with
        '+', one another star has, a class that is not one, or another field.
        The system."""
        with self.s.editing():
            if field not in ("name", "spectral_class"):
                raise ValueError(f"Unknown star field {field!r}")
            system = self.s.find(name)
            stars = self._materialise_stars(system)
            if not 0 <= i < len(stars):
                raise SystemNotFound(f"{name} star {i}")

            value = value.strip()
            if field == "spectral_class":
                value = galaxy_schema.normalise_spectral(value)
                if value:
                    galaxy_schema.check_spectral(value)
            if field == "name":
                if "+" in value:
                    raise ValueError("A star's name has no '+' — it joins the names of a group")
                if value and value in {(st.get("name") or "").strip() for k, st in enumerate(stars) if k != i}:
                    raise ValueError(f"{value} is already a star of {name}")
                self._check_unique(stars[i], value, star=True)
                old = (stars[i].get("name") or "").strip()
                # Hosts name stars: they follow a rename, as references do.
                for item in _hosted(system):
                    parts = hierarchy.names_of(item.get("host") or "")
                    if old and old in parts:
                        item["host"] = "+".join(value if part == old else part
                                                for part in (item["host"].split("+")))
            if field == "spectral_class" and not value:
                stars[i].pop("spectral_class", None)
            else:
                stars[i][field] = value

            # The system's class mirrors the primary's — clearing included, or
            # the list kept showing a class the star no longer had.
            if field == "spectral_class" and i == 0:
                if value:
                    system["spectral_class"] = value
                else:
                    system.pop("spectral_class", None)
            self.s._touch()
            return system

    # ── planets and moons ─────────────────────────────────────────────────────

    def _planet(self, system: dict[str, Any], i: int) -> dict[str, Any]:
        """Planet `i` of `system`. Refused (SystemNotFound) when there is none."""
        planets = system.get("planets") or []
        if not 0 <= i < len(planets):
            raise SystemNotFound(f"planet {i}")
        return planets[i]

    def add_planet(self, name: str) -> dict[str, Any]:
        """Add an unnamed planet ("?") to system `name`, its orbit drawn outside
        the others. The system."""
        with self.s.editing():
            system = self.s.find(name)
            planets = _bodies(system, "planets")
            # '?' is how galaxy.json writes an unnamed planet.
            planets.append({"name": "?", "index": len(planets) + 1,
                            "id": galaxy_schema.next_id(planets, "p")})
            galaxy_schema.normalise({"star_systems": [system]})          # its index and the count
            # Outside the others, drawn around them.
            orbits.draw_planets(system)
            self.s._touch()
            return system

    def delete_planet(self, name: str, i: int) -> dict[str, Any]:
        """Remove planet `i`, with the points of interest anchored to it or its
        moons; the others renumbered. The system."""
        with self.s.editing():
            system = self.s.find(name)
            planets = system.get("planets") or []
            if not 0 <= i < len(planets):
                raise SystemNotFound(f"planet {i}")
            _check_medium_names([planets[i].get("name")])
            gone = str(planets[i].get("id"))
            del planets[i]
            _drop_pois(system, lambda body: body == gone or body.startswith(gone + "/"))
            galaxy_schema.normalise({"star_systems": [system]})
            self.s._touch()
            return system

    def set_planet_field(self, name: str, i: int, field: str, value: str) -> Optional[str]:
        """Set one field of planet `i`: those `_set_body_field` takes, its host
        (`_rehost`) or whether it is a dwarf; a rename takes its map along, a
        new distance renumbers it in orbit order. What else the edit changed,
        in words, or None."""
        with self.s.editing():
            system = self.s.find(name)
            planet = self._planet(system, i)
            old = planet.get("name") or "?"
            if field == "name":
                self._check_map_rename(old, value.strip() or "?")
                if (value.strip() or "?") != old:
                    _check_medium_names([old])
            if field == "host":
                return self._rehost(name, planet, value, system)
            if field == "dwarf":
                # A dwarf planet or a planet: each kind is
                # numbered among its own, and only planets are counted.
                if value.strip().lower() in ("", "0", "false", "no"):
                    planet.pop("dwarf", None)
                else:
                    bodies.set_field(planet, "dwarf", True)
                galaxy_schema.normalise({"star_systems": [system]})
                self.s._touch()
                return None
            note = self._set_body_field(planet, field, value)
            if field == "name":
                self.s._note_rename(old, planet["name"])
            before = planet.get("index")
            if field == "au" and _in_orbit_order(system["planets"], planet, "au",
                                                 lambda b: hierarchy.host_names(system, b.get("host"))):
                galaxy_schema.normalise({"star_systems": [system]})
                # Numbered among its own kind: a dwarf planet passing a planet renumbers neither.
                if planet.get("index") != before:
                    note = _renumbered("Dwarf planet" if planet.get("dwarf") else "Planet",
                                       (before, planet["index"]), note)
            self.s._touch()
            return note

    def _check_map_rename(self, old: str, new: str) -> None:
        """Refuse (ValueError) a planet rename its map folder cannot follow."""
        folder = self.s.map_folder(old)
        if folder is None or slugify(new) == slugify(old):
            return
        if new == "?":
            raise ValueError(f"{old} has a map ({project.current().relative(folder)}) — give it another name "
                             "rather than none, or the map is attached to nothing")
        target = slugify(new)
        if target != folder.name and (folder.parent / target).exists():
            raise ValueError(f"{project.current().relative(folder.parent / target)} already exists, so {old}'s map "
                             f"cannot move there — choose another name")

    def add_moon(self, name: str, i: int) -> dict[str, Any]:
        """Add an unnamed moon ("?") to planet `i`, its orbit drawn where the
        planet allows. The system."""
        with self.s.editing():
            system = self.s.find(name)
            moons = _bodies(self._planet(system, i), "moons")
            moons.append({"name": "?", "index": len(moons) + 1,
                          "id": galaxy_schema.next_id(moons, "m")})
            orbits.draw_moons(system, self._planet(system, i))
            self.s._touch()
            return system

    def delete_moon(self, name: str, i: int, j: int) -> dict[str, Any]:
        """Remove moon `j` of planet `i`, with the points of interest anchored
        to it. The system."""
        with self.s.editing():
            system = self.s.find(name)
            moons = self._planet(system, i).get("moons") or []
            if not 0 <= j < len(moons):
                raise SystemNotFound(f"moon {j}")
            gone = f"{self._planet(system, i).get('id')}/{moons[j].get('id')}"
            del moons[j]
            _drop_pois(system, lambda body: body == gone)
            galaxy_schema.normalise({"star_systems": [system]})
            self.s._touch()
            return system

    def set_moon_field(self, name: str, i: int, j: int, field: str, value: str) -> Optional[str]:
        """Set one field of moon `j` of planet `i` (`_set_body_field`); a new
        distance renumbers the moons in orbit order. What else changed, in
        words, or None."""
        with self.s.editing():
            system = self.s.find(name)
            moons = self._planet(system, i).get("moons") or []
            if not 0 <= j < len(moons):
                raise SystemNotFound(f"moon {j}")
            moon = moons[j]
            note = self._set_body_field(moon, field, value, moon=True)
            if field == "km" and (moved := _in_orbit_order(moons, moon, "km", lambda b: None)):
                for k, m in enumerate(moons, start=1):
                    m["index"] = k
                note = _renumbered("Moon", moved, note)
            self.s._touch()
            return note

    def _check_unique(self, body: dict[str, Any], new: str, star: bool = False) -> None:
        """Refuse (ValueError) `new` as `body`'s name where another star, planet
        or moon has it: names are unique across the galaxy (stars too), compared as the slug a map folder is named by; "?"
        and "" (unnamed) are exempt. Two planets called Mars would share one
        map. A planet or moon cannot take the slug a pending
        map move takes either."""
        slug = slugify(new)
        if new == "?" or not slug:
            return
        # A name taken by a map that a rename in the draft moves away — unless
        # it is this body's own, renamed back.
        moves = self.s.pending_map_moves()
        if not star and slug in moves and moves[slug] != slugify(body.get("name")):
            raise ValueError(f"{project.current().relative(project.current().planet_maps / slug)} moves with a renamed planet at the "
                             f"next Commit — choose another name")
        for system, kind, other in galaxy_schema.named(self.s.edit()):
            if other is not body and slugify(other["name"]) == slug:
                raise ValueError(f"There is already a {kind} named {other['name']} "
                                 f"(in {system.get('name')}) — star, planet and moon names are "
                                 "unique across the galaxy")

    def _set_body_field(self, body: dict[str, Any], field: str, value: str,
                        moon: bool = False) -> Optional[str]:
        """Set one field of a planet or moon from the form's text: name, class,
        an orbital element, tilt, tilt_bearing, look or radius. Planets and
        moons carry the same fields, so they share this. Refused (ValueError)
        for a value that does not hold or another field. What else changed,
        in words, or None: a class whose range a planet's
        radius lies outside of draws it again, and the first class a body
        gets draws one: without a class there is nothing
        to infer a size from."""
        value = value.strip()
        if field == "name":
            self._check_unique(body, value or "?")
            # '?' rather than empty: an unnamed planet still occupies an orbit.
            body["name"] = value or "?"
        elif field == "class":
            if not value:
                # Absent is meaningful — a published globe texture (the maps'
                # manifest) implies habitable, else unknown.
                body.pop("class", None)
            elif value in galaxy_schema.PLANET_CLASSES:
                body["class"] = value
                # Its look among the class's palettes (planet-look.js), drawn
                # once: a new class keeps it, as a rename does.
                if "look" not in body:
                    bodies.set_field(body, "look", random.randrange(galaxy_schema.LOOK_LIMIT))
            else:
                raise ValueError(f"Unknown class {value!r}")
            fits = bodies.range_of(body.get("class"), moon)
            radius = body.get("radius")
            if fits is None:
                return None
            if not isinstance(radius, int):
                bodies.set_radius(body, bodies.draw(body.get("class"), moon))
                return f"Radius drawn for the class: {body['radius']:,} km — change it if it should be another"
            if not moon and not fits.holds(radius):
                bodies.set_radius(body, bodies.draw(body.get("class")))
                return (f"Its radius, {radius:,} km, is implausible for that class — drawn again: "
                        f"{body['radius']:,} km")
        elif field in ORBIT_FIELDS:
            return self._set_orbit(body, field, value, moon)
        elif field in ("tilt", "tilt_bearing"):
            text = value.replace("°", "").strip()
            if not text:
                body.pop(field, None)
                return None
            number = _number(text, "")
            check = galaxy_schema.tilt_error if field == "tilt" else galaxy_schema.bearing_error
            if error := check(number):
                raise ValueError(error[0].upper() + error[1:])
            bodies.set_field(body, field, number)
        elif field == "look":
            # Which of its class's palettes, and its pattern (planet-look.js):
            # typed for a body that should look as it does, as Io's sulphur.
            try:
                look = int(value)
            except ValueError:
                raise ValueError(f"{value!r} is not a look — a whole number") from None
            if error := galaxy_schema.look_error(look):
                raise ValueError(error[0].upper() + error[1:])
            bodies.set_field(body, "look", look)
        elif field == "radius":
            digits = value.replace(",", "").replace("_", "").replace(" ", "").removesuffix("km")
            if not digits:
                body.pop("radius", None)
                return None
            try:
                radius = int(digits)
            except ValueError:
                raise ValueError(f"{value!r} is not a radius in km, like 6371")
            if error := galaxy_schema.radius_error(radius):
                raise ValueError(error[0].upper() + error[1:])
            bodies.set_radius(body, radius)
        else:
            raise ValueError(f"Unknown field {field!r}")
        return None

    def _set_orbit(self, body: dict[str, Any], field: str, value: str, moon: bool) -> Optional[str]:
        """Set one orbital element, typed: the distance (AU for a planet, km for
        a moon), the eccentricity, or an angle in degrees — inclination, node,
        periapsis, the position at the epoch. Clearing the
        distance removes the orbit. Refused (ValueError) for a value that is
        not a number or breaks the schema, or an element before the distance."""
        distance = "km" if moon else "au"
        if field in ("au", "km") and field != distance:
            raise ValueError(f"A {'moon' if moon else 'planet'}'s orbit is in {distance}")
        text = value.replace(",", "").replace(" ", "").replace("°", "").removesuffix("km").removesuffix("AU").removesuffix("au")
        orbit = dict(body.get("orbit") or {})
        if not text:
            if field == distance:
                body.pop("orbit", None)      # no distance, no orbit
                return None
            orbit.pop(field, None)
        else:
            try:
                number = float(text)
            except ValueError:
                raise ValueError(f"{value!r} is not a number")
            orbit[field] = int(number) if field == "km" else number
        if distance not in orbit:
            raise ValueError(f"Give the orbit's distance ({distance}) first")
        if error := galaxy_schema.orbit_error(orbit, moon):
            raise ValueError(error[0].upper() + error[1:])
        bodies.set_field(body, "orbit", orbit)
        return None

    def draw_orbits(self, name: str, redraw: bool = False) -> int:
        """Draw the system's orbits as a group — those missing, or all with
        `redraw` — planets, then each planet's moons (galaxy.orbits.draw_system).
        How many were drawn."""
        with self.s.editing():
            system = self.s.find(name)
            count = orbits.draw_system(system, redraw=redraw)
            if count:
                self.s._touch()
            return count

    # ── gate links ──────────────────────────────

    def gate_links_of(self, name: str) -> list[dict[str, Any]]:
        """The system's gate links, each as {other, grade, ly, range}, nearest
        first; one longer than its range the planner does not use."""
        data, settings = self.s.data(), travel.load()
        where = {s["name"]: (s["x"], s["y"], s.get("z", 0)) for s in data.get("star_systems") or []}
        out = []
        for link in data.get("gate_links") or []:
            if name in (link["from"], link["to"]):
                other = link["to"] if link["from"] == name else link["from"]
                grade = link.get("grade", "permanent")
                out.append({"other": other, "grade": grade, "ly": math.dist(where[name], where[other]),
                            "range": travel.gate_range(settings, grade)})
        return sorted(out, key=lambda row: row["ly"])

    def add_gate_link(self, name: str, other: str, grade: str = "permanent") -> None:
        """Link `name` and `other` by a gate of `grade`; a blocked
        pair is unblocked. Refused (ValueError) for a system linked to itself,
        an unknown grade, a pair already linked, or a link the rules do not
        give (galaxy.gatenet.refusal)."""
        with self.s.editing():
            data = self.s.edit()
            self.s.find(name)
            self.s.find(other)
            if other == name:
                raise ValueError("A gate links two systems")
            if grade not in galaxy_schema.GATE_GRADES:
                raise ValueError(f"A gate link is {' or '.join(galaxy_schema.GATE_GRADES)}")
            if any({link["from"], link["to"]} == {name, other} for link in data.get("gate_links") or []):
                raise ValueError(f"{name} and {other} are linked already")
            # Drawn by hand, it follows the rules as a generated one.
            from galaxy import gatenet
            if why := gatenet.refusal(data, name, other, grade):
                raise ValueError(why[0].upper() + why[1:])
            links = data.setdefault("gate_links", [])
            links.append({"from": name, "to": other, **({"grade": grade} if grade != "permanent" else {})})
            # Added again by hand: no longer blocked.
            if data.get("gate_blocked"):
                data["gate_blocked"] = [p for p in data["gate_blocked"] if {p["from"], p["to"]} != {name, other}]
                if not data["gate_blocked"]:
                    data.pop("gate_blocked")
            self.s._touch()

    def set_gate_grade(self, name: str, other: str, grade: str) -> None:
        """Set the grade of the link between `name` and `other`. Refused
        (ValueError) for an unknown grade, no such link, or one farther apart
        than a gate of the grade reaches."""
        with self.s.editing():
            if grade not in galaxy_schema.GATE_GRADES:
                raise ValueError(f"A gate link is {' or '.join(galaxy_schema.GATE_GRADES)}")
            link = self._gate_link(name, other)
            self._check_reach(name, other, grade)
            if grade == "permanent":
                link.pop("grade", None)
            else:
                link["grade"] = grade
            self.s._touch()

    def delete_gate_link(self, name: str, other: str) -> None:
        """Remove the link between `name` and `other`, and block the pair: the
        next generation leaves it out (galaxy.gatenet)."""
        with self.s.editing():
            data = self.s.edit()
            link = self._gate_link(name, other)
            data["gate_links"].remove(link)
            data.setdefault("gate_blocked", []).append({"from": link["from"], "to": link["to"]})
            if not data["gate_links"]:
                data.pop("gate_links")
            self.s._touch()

    def generate_gate_network(self) -> dict[str, int]:
        """Make the draft's gate network the one its rules give (galaxy.gatenet);
        blocked pairs left out. What changed (gatenet.apply)."""
        from galaxy import gatenet
        with self.s.editing():
            counts = gatenet.apply(self.s.edit())
            self.s._touch()
            return counts

    def _check_reach(self, name: str, other: str, grade: str) -> None:
        """Refuse (ValueError) a link of `grade` between systems farther apart
        than such a gate reaches."""
        a, b = self.s.find(name), self.s.find(other)
        ly = math.dist((a["x"], a["y"], a.get("z", 0)), (b["x"], b["y"], b.get("z", 0)))
        reach = travel.gate_range(travel.load(), grade)
        if ly > reach:
            raise ValueError(f"{name} and {other} are {ly:,.0f} ly apart: a {grade} gate reaches "
                             f"{reach:,.0f} ly — join them by a chain")

    # ── stored trips (galaxy.trips) ──────────────────────────────────────────────

    def save_trip(self, trip: dict[str, Any]) -> dict[str, Any]:
        """Keep a trip, from a map's planner: a new name adds
        it, a name it has replaces that one. Refused (ValueError) without a
        name or where galaxy.trips.problems finds one. The trip as kept."""
        trip = {k: v.strip() if isinstance(v, str) else v for k, v in trip.items() if v not in (None, "")}
        if not trip.get("name"):
            raise ValueError("A trip needs a name")
        with self.s.editing():
            data = self.s.edit()
            kept = [t for t in data.get("trips") or [] if t.get("name") != trip["name"]]
            if found := galaxy_trips.problems({**data, "trips": kept + [trip]}):
                raise ValueError(found[0])
            data["trips"] = kept + [trip]
            self.s._touch()
            return trip

    def delete_trip(self, name: str) -> None:
        """Remove the stored trip `name`. Refused (ValueError) when there is none."""
        with self.s.editing():
            data = self.s.edit()
            trips = data.get("trips") or []
            if not any(t.get("name") == name for t in trips):
                raise ValueError(f"No trip named {name}")
            data["trips"] = [t for t in trips if t.get("name") != name]
            if not data["trips"]:
                data.pop("trips")
            self.s._touch()

    def _gate_link(self, name: str, other: str) -> dict[str, Any]:
        """The draft's link between `name` and `other`, either way round.
        Refused (ValueError) when they are not linked."""
        for link in self.s.edit().get("gate_links") or []:
            if {link["from"], link["to"]} == {name, other}:
                return link
        raise ValueError(f"{name} and {other} are not linked")

    # ── belts, rings, points of interest ──────────

    def add_belt(self, name: str, gap: Optional[int] = None) -> dict[str, Any]:
        """Add an unnamed belt in gap `gap` of galaxy.orbits.belt_gaps —
        between two planets, inside the innermost or beyond the outermost
        (the last, and the default) — until its edges are typed. The system."""
        with self.s.editing():
            system = self.s.find(name)
            gaps = orbits.belt_gaps(system)
            place = gaps[gap] if gap is not None and 0 <= gap < len(gaps) else gaps[-1]
            belts = _bodies(system, "belts")
            belts.append({"name": "?", "id": galaxy_schema.next_id(belts, "b"),
                          "inner": place["inner"], "outer": place["outer"]})
            self.s._touch()
            return system

    def set_belt_field(self, name: str, k: int, field: str, value: str) -> Optional[str]:
        """Set belt `k`'s name, host, or inner or outer edge (AU). Refused
        (ValueError) for an edge that breaks the schema or another field. An
        edge or host that takes the belt across a planet's orbit is kept,
        and said: the note, or None."""
        with self.s.editing():
            system = self.s.find(name)
            belt = self._item(system, "belts", k)
            value = value.strip()
            if field == "name":
                belt["name"] = value or "?"
            elif field == "host":
                self.set_host(name, belt, value, system)
            elif field in ("inner", "outer"):
                changed = dict(belt, **{field: _number(value, "AU")})
                if error := galaxy_schema.belt_error(changed):
                    raise ValueError(error[0].upper() + error[1:])
                belt[field] = changed[field]
            else:
                raise ValueError(f"Unknown field {field!r}")
            self.s._touch()
            if field != "name" and (crossed := orbits.belt_crossings(system, belt)):
                return f"The belt crosses the orbit of {', '.join(crossed)}"
            return None

    def delete_belt(self, name: str, k: int) -> None:
        """Remove belt `k`; the last one takes the field with it."""
        with self.s.editing():
            system = self.s.find(name)
            self._item(system, "belts", k)
            del system["belts"][k]
            if not system["belts"]:
                system.pop("belts")
            self.s._touch()

    def add_ring(self, name: str, i: int) -> int:
        """Add a ring to planet `i`, until typed from 1.5 to 2.5 of its radii —
        or beyond its outermost, a division between (as Saturn's
        Cassini Division) — its density drawn. Which ring it is, innermost 0.
        Refused (ValueError) when there is no room beyond the outermost."""
        with self.s.editing():
            planet = self._planet(self.s.find(name), i)
            bands = bodies.ring_bands(planet)
            start = round(bands[-1]["outer"] + 0.1, 2) if bands else 1.5
            if start + 0.1 > galaxy_schema.RINGS_LIMITS[1]:
                raise ValueError(f"No room beyond the outermost ring, at {bands[-1]['outer']:g} planet radii")
            bands.append({"inner": start, "outer": min(round(start + 0.5, 2) if bands else 2.5,
                                                       galaxy_schema.RINGS_LIMITS[1]),
                          "density": bodies.draw_ring_density()})
            bodies.set_field(planet, "rings", bands)
            self.s._touch()
            return len(bands) - 1

    def set_ring_field(self, name: str, i: int, k: int, field: str, value: str) -> None:
        """Set ring `k`'s edge, in planet radii, or its density (0.01–1;
        cleared, the densest). Refused (ValueError) for rings that break the
        schema or another field."""
        with self.s.editing():
            planet = self._planet(self.s.find(name), i)
            bands = [dict(b) for b in bodies.ring_bands(planet)]
            if field not in ("inner", "outer", "density") or not 0 <= k < len(bands):
                raise ValueError(f"Unknown field {field!r}")
            if field == "density" and not value.strip():
                bands[k].pop("density", None)
            else:
                bands[k][field] = _number(value, "")
            if error := galaxy_schema.rings_error(bands):
                raise ValueError(error[0].upper() + error[1:])
            planet["rings"] = bands
            self.s._touch()

    def draw_ring_density(self, name: str, i: int, k: int) -> float:
        """Draw another density for ring `k`, at random (bodies.draw_ring_density).
        The density drawn."""
        with self.s.editing():
            planet = self._planet(self.s.find(name), i)
            bands = [dict(b) for b in bodies.ring_bands(planet)]
            if not 0 <= k < len(bands):
                raise ValueError(f"No ring {k + 1}")
            old = bands[k].get("density", 1.0)
            density = old
            while density == old:
                density = bodies.draw_ring_density()
            bands[k]["density"] = density
            planet["rings"] = bands
            self.s._touch()
            return density

    def delete_ring(self, name: str, i: int, k: int) -> None:
        """Remove ring `k` of planet `i`; the last one takes the field with it."""
        with self.s.editing():
            planet = self._planet(self.s.find(name), i)
            bands = bodies.ring_bands(planet)
            if 0 <= k < len(bands):
                del bands[k]
            if bands:
                planet["rings"] = bands
            else:
                planet.pop("rings", None)
            self.s._touch()

    def add_poi(self, name: str) -> dict[str, Any]:
        """Add a point of interest at the first planet's L4 — or in a system
        without planets around the star, at 1 AU — until its anchor is
        chosen. The system."""
        with self.s.editing():
            system = self.s.find(name)
            points = _bodies(system, "points_of_interest")
            planets = system.get("planets") or []
            anchor = ({"body": str(planets[0].get("id")), "point": "L4"} if planets
                      else {"body": "star", "au": 1.0})
            points.append({"name": f"Point of interest {len(points) + 1}",
                             "id": galaxy_schema.next_id(points, "i"), "anchor": anchor})
            self.s._touch()
            return system

    def set_poi_field(self, name: str, k: int, field: str, value: str) -> Optional[str]:
        """Set one field of point of interest `k`: its name; its kind — a
        station, a jumpgate, a wreck — and a jumpgate's pair and grade; its
        body; where at the body — a Lagrange point, or "orbit"; and how far:
        around the star a distance in AU (`au`), around a planet or moon a
        height above it in km (`km`). What else changed, in words, or None:
        a gate left without a pair; a position set aside — the last one at
        each body, and in orbit or at a point, comes back when chosen again
        (in the session, not the file). Refused (ValueError) for a value that
        does not hold or another field."""
        with self.s.editing():
            system = self.s.find(name)
            point = self._item(system, "points_of_interest", k)
            value = value.strip()
            anchor = dict(point.get("anchor") or {})
            note = None
            memo = self._anchor_memo
            mine = (name, point.get("id"))
            if field == "name":
                if not value:
                    raise ValueError("A point of interest needs a name")
                point["name"] = value
            elif field == "kind":
                if value and value not in galaxy_schema.POI_KINDS:
                    raise ValueError("A point of interest is one of " + ", ".join(galaxy_schema.POI_KINDS))
                if value != "jumpgate":
                    note = _alone([_unpair(system, point)])
                    point.pop("grade", None)
                if value:
                    items = [(k, v) for k, v in point.items() if k != "kind"]
                    at = next((n + 1 for n, (k, _) in enumerate(items) if k == "id"), len(items))
                    point.clear()
                    point.update(items[:at] + [("kind", value)] + items[at:])
                else:
                    point.pop("kind", None)
            elif field == "pair":
                # Both ends at once; each one's earlier partner let go.
                if point.get("kind") != "jumpgate":
                    raise ValueError("Only a jumpgate has a pair")
                other = next((p for p in system["points_of_interest"] if p.get("id") == value), None) if value else None
                if value and (other is None or other is point or other.get("kind") != "jumpgate"):
                    raise ValueError("A jumpgate pairs with another jumpgate of the system")
                alone = [_unpair(system, point)]
                if other is not None:
                    alone.append(_unpair(system, other))
                    point["pair"], other["pair"] = other["id"], point["id"]
                note = _alone([n for n in alone if n not in (point.get("name"), other and other.get("name"))])
            elif field == "grade":
                if point.get("kind") != "jumpgate" or value not in galaxy_schema.JUMPGATE_GRADES:
                    raise ValueError("A jumpgate's grade is one of " + ", ".join(galaxy_schema.JUMPGATE_GRADES))
                point["grade"] = value
            elif field == "body":
                memo[mine + (_anchor_key(anchor),)] = anchor
                back = memo.get(mine + (value if value.startswith("star:") or value != "star" else "star:",))
                if back is not None:
                    anchor = dict(back)
                elif value == "star" or value.startswith("star:"):
                    # Around a star or a group of them: "star:B", "star:A+B".
                    host = value.removeprefix("star").removeprefix(":")
                    anchor = {"body": "star", "au": anchor.get("au", 1.0)}
                    if host:
                        self.set_host(name, anchor, host, system)
                else:
                    keep = {k: v for k, v in anchor.items() if k in ("point", "km")}
                    anchor = {"body": value, **(keep or {"point": "L4"})}
                before = dict(point.get("anchor") or {})
                if back is not None:
                    note = f"{point.get('name')} is {_where(anchor)} again, as before"
                elif _where(before) != _where(anchor):
                    note = (f"{point.get('name')} was {_where(before)}; now {_where(anchor)} — "
                            "choosing its former body again puts it back")
            elif field == "where":
                if "km" in anchor:
                    memo[mine + (_anchor_key(anchor), "orbit")] = anchor
                back = memo.get(mine + (_anchor_key(anchor), "orbit")) if value == "orbit" else None
                if back is not None:
                    anchor = dict(back)
                else:
                    anchor = {"body": anchor.get("body"),
                              **({"km": 400} if value == "orbit" else {"point": value})}
            elif field in ("km", "au"):
                anchor = {"body": anchor.get("body"), field: _number(value, field),
                          **({"host": anchor["host"]} if "host" in anchor else {})}
            else:
                raise ValueError(f"Unknown field {field!r}")
            if field not in ("name", "kind", "pair", "grade"):
                if error := galaxy_schema.anchor_error(anchor, system):
                    raise ValueError(error[0].upper() + error[1:])
                point["anchor"] = anchor
            self.s._touch()
            return note

    def delete_poi(self, name: str, k: int) -> Optional[str]:
        """Remove point of interest `k`, a jumpgate's partner let go. Who is left
        without a pair, in words, or None."""
        with self.s.editing():
            system = self.s.find(name)
            alone = _unpair(system, self._item(system, "points_of_interest", k))
            del system["points_of_interest"][k]
            if not system["points_of_interest"]:
                system.pop("points_of_interest")
            self.s._touch()
            return _alone([alone])

    @staticmethod
    def _item(system: dict[str, Any], key: str, k: int) -> dict[str, Any]:
        """Item `k` of the system's list `key`. Refused (SystemNotFound) when
        there is none."""
        items = system.get(key) or []
        if not 0 <= k < len(items):
            raise SystemNotFound(f"{key[:-1]} {k}")
        return items[k]

    def fill_orbits(self) -> int:
        """Give every planet and moon without an orbit one, galaxy-wide, in
        the draft (galaxy.orbits.fill). How many."""
        with self.s.editing():
            count = orbits.fill(self.s.edit())
            if count:
                self.s._touch()
            return count

    def add_bright_stars(self) -> list[str]:
        """Add the real sky's bright stars the draft lacks, as systems of their
        own, and put those already in back in place (galaxy.brightstars.add). The names added."""
        with self.s.editing():
            doc = self.s.edit()
            moved = not brightstars.current(doc)
            added = brightstars.add(doc)
            if added or moved:
                self.s._touch()
            return added

    def fill_radii(self) -> int:
        """Give every planet and moon without a radius one, in the draft
        (galaxy.bodies.fill). How many."""
        with self.s.editing():
            count = bodies.fill(self.s.edit())
            if count:
                self.s._touch()
            return count


def _in_orbit_order(items: list[dict[str, Any]], moved: dict[str, Any], unit: str, host) -> Optional[tuple[int, int]]:
    """Put `items` back in orbit order after `moved`'s distance changed:
    orbital number follows position. Only among those around the
    same host and with a distance, in the places they hold — the others
    stay where they are. (old, new) positions, 1-based, when `moved` moved."""
    def far(b: dict[str, Any]):
        return (b.get("orbit") or {}).get(unit)
    if far(moved) is None:
        return None
    places = [k for k, b in enumerate(items) if far(b) is not None and host(b) == host(moved)]
    group = sorted((items[k] for k in places), key=far)
    before = items.index(moved)
    for k, b in zip(places, group):
        items[k] = b
    after = items.index(moved)
    return (before + 1, after + 1) if after != before else None


def _renumbered(kind: str, moved: tuple[int, int], note: Optional[str]) -> str:
    """`note` with the renumbering said after it: "Planet 3 is now planet 2: …"."""
    said = f"{kind} {moved[0]} is now {kind.lower()} {moved[1]}: numbered by orbit, the others renumbered"
    return f"{note}. {said}" if note else said


def _anchor_key(anchor: dict[str, Any]) -> str:
    """What a point of interest is anchored to, as the At select names it."""
    return f"star:{anchor.get('host') or ''}" if anchor.get("body") == "star" else str(anchor.get("body"))


def _where(anchor: dict[str, Any]) -> str:
    """Where at its body, in words."""
    if "au" in anchor:
        return f"{anchor['au']:g} AU from {anchor.get('host') or 'the star'}"
    if "km" in anchor:
        return f"{anchor['km']:,g} km above it"
    return f"at {anchor.get('point')}"


def _number(value: str, unit: str) -> float:
    """The number typed in `value`, its `unit` suffix allowed. Refused
    (ValueError) when empty or not a number."""
    text = value.strip().replace(",", "").replace(" ", "")
    if unit:
        text = text.removesuffix(unit).removesuffix(unit.lower())
    if not text:
        raise ValueError(f"Give a number{' of ' + unit if unit else ''}: the field is empty")
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"{value!r} is not a number{' of ' + unit if unit else ''}")


def _drop_pois(system: dict[str, Any], gone) -> None:
    """Remove the points of interest anchored to a body that is gone (`gone`
    says which), their jumpgate partners let go."""
    points = [p for p in system.get("points_of_interest") or [] if not gone(str((p.get("anchor") or {}).get("body")))]
    for point in system.get("points_of_interest") or []:
        if point not in points:
            _unpair(system, point)
    if points:
        system["points_of_interest"] = points
    else:
        system.pop("points_of_interest", None)


def _unpair(system: dict[str, Any], point: dict[str, Any]) -> Optional[str]:
    """Let a jumpgate and its partner go of each other. The partner's name,
    left without a pair, or None."""
    pair = point.pop("pair", None)
    for other in system.get("points_of_interest") or []:
        if pair is not None and other.get("id") == pair and other.get("pair") == point.get("id"):
            other.pop("pair")
            return other.get("name") or "a jumpgate"
    return None


def _alone(names: list[Optional[str]]) -> Optional[str]:
    """The note that `names` are left without a pair, or None for none."""
    names = [n for n in names if n]
    if not names:
        return None
    return f"{' and '.join(names)} {'is' if len(names) == 1 else 'are'} left without a pair"


# The orbital elements a planet's or moon's row edits (galaxy.orbits).
ORBIT_FIELDS = ("au", "km", "e", "i", "node", "periapsis", "anomaly")


def __getattr__(name: str):
    """`session`, the one editing session, and `detail`, the edits of one
    system on it, made on first use: the session restores the draft from the
    project's drafts folder, so the project is chosen first (galaxy.project.use)."""
    if name == "session":
        globals()["session"] = GalaxySession()
        return globals()["session"]
    if name == "detail":
        globals()["detail"] = SystemDetail(globals().get("session") or __getattr__("session"))
        return globals()["detail"]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
