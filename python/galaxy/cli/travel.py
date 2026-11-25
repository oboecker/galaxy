"""Plan a trip between two star systems, or two bodies of one, every way
compared.

    uv run python cli/travel.py Sol Vega
    uv run python cli/travel.py Vega Sol --depart "AD 2400" --set own_drive.ly_per_day=400
    uv run python cli/travel.py Vega Sol --depart "AD 2400" --by "AD 2400-09-01"
    uv run python cli/travel.py Earth Mars --system Sol --depart "AD 2400, day 333"
    uv run python cli/travel.py Vega Sol --depart "AD 2400" --json      # for a tool to read

`--set key.path=value` overrides a number of the project's travel.json for
this trip only.
"""

from __future__ import annotations

import argparse
import json

from galaxy import catalogue, project, travel, trips


def _override(pairs: list[str]) -> dict:
    """The `--set key.path=value` pairs as nested overrides, each value read as JSON."""
    out: dict = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        *path, last = key.split(".")
        at = out
        for part in path:
            at = at.setdefault(part, {})
        at[last] = json.loads(value)
    return out


def _duration(days: float) -> str:
    """`days` written in seconds, minutes, hours or days, whichever fits."""
    if days < 1 / 24 / 60:
        return f"{days * 86400:.2g} s"
    if days < 1 / 24:
        return f"{days * 24 * 60:.0f} min"
    if days < 2:
        return f"{days * 24:.1f} h"
    return f"{days:.1f} days"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("start")
    parser.add_argument("end")
    parser.add_argument("--depart", help='a date like "AD 2523.5", "AD 2400-03-01"')
    parser.add_argument("--by", help="a date to arrive by: each way in time or late, and by how much")
    parser.add_argument("--system", help="a trip within this system, between its bodies (galaxy.insystem)")
    parser.add_argument("--json", action="store_true", help="every way as JSON (galaxy.trips.summary)")
    parser.add_argument("--efficiency", type=float, help="the own drive's share of its speed (between the stars, or within --system)")
    parser.add_argument("--thrust", type=float, help="within --system, the sublight drive's thrust in g: 0 coasts (ballistic), 0.1–3")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    project.add_argument(parser)
    args = parser.parse_args()
    doc = catalogue.read(project.from_args(args))
    if args.json or args.system:
        try:
            found = trips.summary(doc, args.start, args.end, args.depart, args.by, args.system, args.efficiency,
                                  args.thrust)
        except (KeyError, ValueError) as e:
            found = {"error": str(e.args[0] if e.args else e)}
        if args.json:
            print(json.dumps(found, ensure_ascii=False))
            return
        if "error" in found:
            raise SystemExit(found["error"])
        print(f"{found['start']} → {found['end']} in {found['system']}, leaving {found['depart']}")
        for way in found["ways"]:
            check = way.get("check")
            verdict = "" if not check else (f", {check['spare_days']:.1f} days to spare" if check["in_time"]
                                            else f", LATE by {-check['spare_days']:.1f} days")
            print(f"{way['name']:10}  {_duration(way['days']):>12}  arrives {way['arrival']}{verdict}")
            for leg in way["legs"]:
                print(f"            {leg['kind']:9} {leg['from']} → {leg['to']}: {leg['AU']:.3f} AU, {_duration(leg['days'])}")
        return
    depart = travel.parse_date(args.depart) if args.depart else None
    by = travel.parse_date(args.by) if args.by else None
    overrides = travel.merged(_override(args.set), travel.drive_share(args.efficiency) or {})
    for option in travel.plan(doc, args.start, args.end, depart, overrides):
        if not option.reachable:
            print(f"{option.name:10}  —  {option.why}")
            continue
        arrival = f"  arrives {travel.date_text(option.arrival)}" if option.arrival is not None else ""
        if check := travel.in_time(option.arrival, by):
            arrival += (f", {check['spare_days']:.1f} days to spare" if check["in_time"]
                        else f", LATE by {-check['spare_days']:.1f} days")
        print(f"{option.name:10}  {_duration(option.days):>12}{arrival}")
        for leg in option.legs:
            extra = f", {leg.grade}" if leg.grade else ""
            print(f"            {leg.kind:9} {leg.start} → {leg.end}: {leg.ly:,.0f} ly, {_duration(leg.days)}{extra}")


if __name__ == "__main__":
    main()
