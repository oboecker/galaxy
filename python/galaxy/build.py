"""Everything the maps read, written into one folder, with a manifest that
names each file for them.

    galaxy.json            the whole catalogue, the layers merged (galaxy.catalogue)
    layers/<name>.json     each layer, a switch on the galaxy map
    systems.json           what the system maps draw (galaxy.systemmap)
    nebulae.json           the skies' nebulae
    glow.json              the galaxy's light, the band in every system's sky
    trips.json             the stored trips with their routes (galaxy.trips)
    travel-settings.json   how travel looks, and the project's modes by name
    territories/           the nations' territories through time, with a nations file
    procedural.json, procedural-gates.json, procedural/
                           the procedural galaxy (with `procedural`: minutes)
    manifest.json          the files above, relative to it, for the maps:
                           {"galaxy": {…the galaxy map's config…}, "system": {…}}

    build.write(Path("public/galaxy"), procedural=True)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Optional

from galaxy import calendar, catalogue, procedural, project, public, systemmap, trips
from galaxy.fs import write_atomic
from galaxy.jsonstore import dumps


def _compact(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"


def write(out: Path, *, here: Optional[project.Project] = None, procedural_galaxy: bool = False,
          within: Optional[float] = None) -> list[Path]:
    """Write the maps' files for `here` (the current project) into `out`; the
    procedural galaxy only with `procedural_galaxy` (within `within` ly of Sol
    if given). The files written; out/manifest.json last."""
    here = here or project.current()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    doc = catalogue.read(here)
    written: list[Path] = []

    def put(name: str, text: str) -> None:
        write_atomic(out / name, text)
        written.append(out / name)

    put("galaxy.json", dumps(doc))
    shutil.rmtree(out / "layers", ignore_errors=True)
    layers = catalogue.write_layers(out / "layers", here)
    written += layers
    systemmap.write(doc, out / "systems.json")
    systemmap.write_nebulae(doc, out / "nebulae.json")
    written += [out / "systems.json", out / "nebulae.json"]
    model = procedural.load(here.procedural) if here.procedural.exists() else None
    if model is not None:
        put("glow.json", _compact(procedural.glow(model)))
    trips.write(doc, out / "trips.json")
    written.append(out / "trips.json")
    travel = json.loads(here.travel.read_text(encoding="utf-8")) if here.travel.exists() else {}
    put("travel-settings.json", _compact(public.travel_settings(travel)))

    territories = None
    if here.nations.exists():
        from galaxy.cli.territories import write_series
        from galaxy import nations, territories as territory
        nations_doc, error = nations.read(here.nations)
        if error:
            raise ValueError(f"{here.nations}: {error}")
        data = catalogue.read(here)
        territory.attach(data, nations_doc)
        shutil.rmtree(out / "territories", ignore_errors=True)
        write_series(data, out / "territories")
        territories = "territories/"
        written.append(out / "territories")

    gates = None
    if procedural_galaxy and model is not None:
        procedural.bundle(out, doc, model, within=within)
        gates = "procedural-gates.json"
        written += [out / "procedural.json", out / gates, out / "procedural"]

    manifest = {
        "galaxy": {
            "layers": catalogue.layer_index(here, lambda name: f"layers/{name}.json"),
            "trips": "trips.json",
            "travelSettings": "travel-settings.json",
            "territories": territories,
            "procedural": "procedural.json" if gates else None,
            "proceduralGates": gates,
        },
        "system": {"systems": "systems.json", "nebulae": "nebulae.json",
                   "glow": "glow.json" if model is not None else None,
                   "travelSettings": "travel-settings.json",
                   "trips": "trips.json",
                   "procedural": "procedural.json" if gates else None},
        "calendar": calendar.load(here.calendar).as_dict(),
    }
    put("manifest.json", dumps(manifest))
    return written
