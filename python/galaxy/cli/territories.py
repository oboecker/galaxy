#!/usr/bin/env python3
"""Compute nation territories through time and write them for both galaxy maps.

--out DIR writes the series the 3D map reads: index.json lists every interval of
every world branch, each pointing at a snapshot file; snapshots with identical
holdings share a file. --svg renders the galaxy SVG at one moment (--at, --world).

Nations and their holdings come from nations.json beside galaxy.json (format in
galaxy/nations.py); --nations points elsewhere, for instance at
throwaway test nations. Neither file is written.
"""

import argparse
import json
import sys
from pathlib import Path

from galaxy import calendar, catalogue, nations, project
from galaxy.renderer import GalaxyMapGenerator
from galaxy.territories import attach, compute, snapshots, territories, worlds
from galaxy.fs import write_atomic


def write_series(data: dict, out: Path) -> None:
    """Write the territory series into `out`: the snapshots, then the index
    that names them, then delete the files no index names any more — a reader
    during the rewrite finds the old series or the new one, where deleting
    first left it nothing."""
    files: dict[frozenset, str] = {}
    index = []
    for world in worlds(data):
        for snap in snapshots(data, world):
            if snap.key not in files:
                files[snap.key] = f"s{len(files)}.json"
                result = [t.as_dict() for t in territories(data, snap.held)]
                write_atomic(out / files[snap.key],
                             json.dumps({"territories": result}, separators=(",", ":")))
            index.append({"world": snap.world, "from": snap.start, "to": snap.end,
                          "file": files[snap.key]})
    write_atomic(out / "index.json", json.dumps({"snapshots": index}, indent=1))
    for old in out.glob("*.json"):
        if old.name != "index.json" and old.name not in files.values():
            old.unlink()
    size = sum(f.stat().st_size for f in out.glob("*.json")) // 1024
    print(f"{len(index)} intervals over {len(worlds(data))} branch(es), "
          f"{len(files)} distinct snapshots → {out} ({size} KB)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    project.add_argument(parser)
    parser.add_argument("--galaxy", type=Path, help="the catalogue (default: the project's)")
    parser.add_argument("--nations", type=Path, help="Nations and their holdings (default: the project's)")
    parser.add_argument("--out", type=Path, help="Directory for index.json and the snapshot files")
    parser.add_argument("--svg", type=Path, help="Render the galaxy SVG with territories at --at")
    parser.add_argument("--at", help="Moment for --svg, e.g. 'AD 9500'")
    parser.add_argument("--world", help="World branch for --svg (+, -, ~); default: every-branch holdings only")
    parser.add_argument("--interactive", action="store_true", help="Zoomable SVG")
    args = parser.parse_args()
    if args.svg and not args.at:
        parser.error("--svg needs --at")

    here = project.from_args(args)
    args.nations = args.nations or here.nations
    data = catalogue.read(here, args.galaxy)
    doc, error = nations.read(args.nations)
    if error:
        sys.exit(f"Error: {args.nations}: {error}")
    for name in attach(data, doc):
        print(f"Warning: holding names unknown system {name!r}, skipped (see make check)",
              file=sys.stderr)

    if args.out:
        write_series(data, args.out)
    if args.svg:
        moment = [t.as_dict() for t in compute(data, calendar.current().point(args.at), args.world)]
        GalaxyMapGenerator(5600, 5600, interactive=args.interactive).generate(data, str(args.svg), moment)


if __name__ == "__main__":
    main()
