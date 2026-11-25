"""Write the stored trips with their routes (galaxy.trips) for the
maps of a site: public/galaxy/trips.json; or, with --check, print each
one against its date to arrive by.

    uv run python cli/trips.py [--galaxy PATH] [--out PATH]
    uv run python cli/trips.py --check
"""

import argparse
import json
from pathlib import Path

from galaxy import project, trips


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    project.add_argument(parser)
    parser.add_argument("--galaxy", type=Path, help="the catalogue (default: the project's)")
    parser.add_argument("--out", type=Path, help="default: trips.json in the project's public folder")
    parser.add_argument("--check", action="store_true", help="print each trip and whether it arrives in time")
    args = parser.parse_args()
    here = project.from_args(args)
    doc = json.loads((args.galaxy or here.catalogue).read_text(encoding="utf-8"))
    if not args.check:
        args.out = args.out or here.public / "trips.json"
        trips.write(doc, args.out)
        print(f"  → {args.out}")
        return
    for trip in doc.get("trips") or []:
        found = trips.route(doc, trip)
        where = f" in {trip['system']}" if trip.get("system") else ""
        head = f"{found['name']}: {trip['start']} → {trip['end']}{where}"
        if "error" in found:
            print(f"{head} — {found['error']}")
            continue
        option, check = found["option"], found.get("check")
        verdict = ""
        if check:
            verdict = (f", in time by {check['spare_days']:.1f} days" if check["in_time"]
                       else f", LATE by {-check['spare_days']:.1f} days") + f" (by {check['by']})"
        print(f"{head} — {option['name']}, {option['days']:.2f} days, arrives {option['arrival'] or '—'}{verdict}")


if __name__ == "__main__":
    main()
