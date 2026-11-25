"""Stored trips: the
journeys a story makes, kept in galaxy.json as `trips` — what defines
each, not its route, which is worked out again from the galaxy as it is:

    {"name": "The return", "start": "Vega", "end": "Sol",
     "depart": "AD 2400", "way": "own drive", "by": "AD 2401", "note": "…"}

Between stars `start` and `end` are systems; with a `system`, they are
bodies or points of interest in it (by name or reference) and `depart` is
needed — the bodies move. `way` is the option to show (galaxy.travel or
galaxy.insystem names it), the fastest when absent; `by`, a date the trip
must arrive by — the arrival check: in time or not, and the days to spare;
`efficiency`, the own drive's share of its speed (travel.drive_share):
between the stars of its `ly_per_day`, within a system of its speed
between the stars; all of it when absent. `thrust`, within a system, the
sublight drive's in g (travel.thrust): 0 coasts (ballistic); the
configured 3 g when absent.

An editor saves them from its maps; the build writes their routes
(public/galaxy/trips.json) for a site's maps to show, read-only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from galaxy import insystem, orbits, travel

KEYS = ("name", "start", "end", "depart", "way", "system", "by", "note", "efficiency", "thrust")


def problems(doc: dict[str, Any]) -> list[str]:
    """What in the stored trips does not hold: a field unknown or missing,
    a name twice, a system or date that is not one."""
    out, names = [], set()
    systems = {s.get("name"): s for s in doc.get("star_systems") or []}
    for k, trip in enumerate(doc.get("trips") or [], start=1):
        if not isinstance(trip, dict):
            out.append(f"trip {k}: a trip is an object")
            continue
        label = trip.get("name") or f"trip {k}"
        if set(trip) - set(KEYS):
            out.append(f"{label}: unknown fields {', '.join(sorted(set(trip) - set(KEYS)))}")
        for key in ("name", "start", "end"):
            if not str(trip.get(key) or "").strip():
                out.append(f"{label}: needs a {key}")
        if trip.get("name") in names:
            out.append(f"{label}: the name is taken")
        names.add(trip.get("name"))
        for key in ("depart", "by"):
            if trip.get(key):
                try:
                    travel.parse_date(trip[key])
                except ValueError as e:
                    out.append(f"{label}: {e}")
        if "efficiency" in trip and not (isinstance(trip["efficiency"], (int, float))
                                         and not isinstance(trip["efficiency"], bool) and 0 < trip["efficiency"] <= 1):
            out.append(f"{label}: its efficiency is a share of the drive's speed, above 0 and at most 1")
        if "thrust" in trip:
            if not trip.get("system"):
                out.append(f"{label}: a thrust is for a trip within a system")
            else:
                try:
                    if isinstance(trip["thrust"], bool) or not isinstance(trip["thrust"], (int, float)):
                        raise ValueError("the thrust is a number of g")
                    travel.thrust(trip["thrust"])
                except ValueError as e:
                    out.append(f"{label}: {e}")
        if trip.get("system"):
            if trip["system"] not in systems:
                out.append(f"{label}: {trip['system']} is not a system")
            elif not trip.get("depart"):
                out.append(f"{label}: a trip within a system needs a departure date")
        else:
            for key in ("start", "end"):
                if trip.get(key) and trip[key] not in systems:
                    out.append(f"{label}: {trip[key]} is not a system")
    return out


def route(doc: dict[str, Any], trip: dict[str, Any], settings: Optional[dict[str, Any]] = None,
          field: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """The trip with its way worked out: every way's name and days, the
    chosen one drawn (`option`, as the maps take it), and the arrival check
    against `by`. An `error` instead where it cannot be planned."""
    out = {key: trip[key] for key in KEYS if key in trip}
    depart = travel.parse_date(trip["depart"]) if trip.get("depart") else None
    by = travel.parse_date(trip["by"]) if trip.get("by") else None
    try:
        if trip.get("system"):
            system = next(s for s in doc["star_systems"] if s.get("name") == trip["system"])
            options = insystem.plan(system, trip["start"], trip["end"], depart, settings=settings,
                                    density=travel.density_at(doc, trip["system"], depart, field),
                                    nebula=travel.nebula_at(doc, trip["system"]),
                                    overrides=travel.in_system(trip.get("efficiency"), trip.get("thrust")))
            # For the system map: its bodies by reference, the date in its years.
            places = insystem.Places(system)
            shown = [insystem.as_json(o, places) for o in options]
            out["refs"] = [places.ref(trip["start"]), places.ref(trip["end"])]
        else:
            options = travel.plan(doc, trip["start"], trip["end"], depart, settings=settings, field=field,
                                  overrides=travel.drive_share(trip.get("efficiency"), False, settings))
            where = travel.systems(doc)
            shown = [travel.as_json(o, where) for o in options]
    except (KeyError, ValueError, StopIteration) as e:
        out["error"] = str(e.args[0] if e.args else e)
        return out
    out["ways"] = [{"name": o["name"], "days": o["days"], "arrival": o["arrival"]} for o in shown]
    reachable = [(o, s) for o, s in zip(options, shown) if getattr(o, "reachable", True)]
    chosen = next(((o, s) for o, s in reachable if o.name == trip.get("way")), None)
    if chosen is None and trip.get("way"):
        out["error"] = f"no way {trip['way']!r} from {trip['start']} to {trip['end']}"
        return out
    chosen = chosen or next(((o, s) for o, s in reachable if o.name != "AEGIS"), None) or (reachable or [None])[0]
    if chosen is None:
        out["error"] = f"no way from {trip['start']} to {trip['end']}"
        return out
    out["option"] = chosen[1]
    if depart is not None:
        out["depart_at"] = depart                    # on the shared axis, for the maps' clocks
    check = travel.in_time(chosen[0].arrival, by)
    if check:
        out["check"] = check
    return out


def export(doc: dict[str, Any]) -> dict[str, Any]:
    """Every stored trip with its route: between stars, and by system."""
    out: dict[str, Any] = {"galaxy": [], "systems": {}}
    for trip in doc.get("trips") or []:
        found = route(doc, trip)
        if trip.get("system"):
            out["systems"].setdefault(trip["system"], []).append(found)
        else:
            out["galaxy"].append(found)
    return out


def write(doc: dict[str, Any], path: Path) -> None:
    """Write every stored trip with its route (`export`) to `path`, as compact JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(export(doc), separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")


def summary(doc: dict[str, Any], start: str, end: str, depart: Optional[str] = None, by: Optional[str] = None,
            system: Optional[str] = None, efficiency: Optional[float] = None,
            thrust: Optional[float] = None) -> dict[str, Any]:
    """Every way from `start` to `end` in words and numbers, for a writer
    or a tool (an MCP tool, say): days, arrival, stops, each leg, and
    with `by` whether it arrives in time — no drawing points. `efficiency`:
    the own drive's share of its speed (travel.drive_share); `thrust`, in a
    system, the sublight drive's in g, 0 coasting (travel.thrust). Between stars,
    or with `system` between its bodies (leaving at the epoch without a
    date). Raises ValueError or KeyError for what cannot be planned."""
    when = travel.parse_date(depart) if depart else None
    deadline = travel.parse_date(by) if by else None
    out: dict[str, Any] = {"start": start, "end": end, "depart": travel.date_text(when) if when is not None else None}
    if system:
        found = next((s for s in doc.get("star_systems") or [] if s.get("name") == system), None)
        if found is None:
            raise KeyError(f"No system named {system}")
        if when is None:
            when = found and insystem.Places(found).data["epoch_year"]
            out["depart"] = travel.date_text(when) + " (the epoch: no date given)"
        options = insystem.plan(found, start, end, when, density=travel.density_at(doc, system, when),
                                nebula=travel.nebula_at(doc, system),
                                overrides=travel.in_system(efficiency, thrust))
        unit = "AU"
        out["system"] = system
    else:
        options, unit = travel.plan(doc, start, end, when, overrides=travel.drive_share(efficiency)), "ly"
    out["ways"] = []
    for o in options:
        way = {"name": o.name, "reachable": getattr(o, "reachable", True)}
        if not way["reachable"]:
            way["why"] = o.why
        else:
            way.update(days=_figures(o.days), stops=o.stops,
                       legs=[{"kind": leg.kind, "from": leg.start, "to": leg.end,
                              unit: round(leg.ly, 3 if unit == "AU" else 0), "days": _figures(leg.days),
                              **({"grade": leg.grade} if leg.grade else {})} for leg in o.legs])
            if o.arrival is not None:
                way["arrival"] = travel.date_text(o.arrival)
            if speed := _speed(o, unit):
                way["speed"] = speed
            if check := travel.in_time(o.arrival, deadline):
                way["check"] = check
        out["ways"].append(way)
    if deadline is not None and when is None:
        out["note"] = "no departure date: the arrival, and so the check, needs one"
    return out


def _speed(option: Any, unit: str) -> dict[str, Any]:
    """How fast a way goes, in words for a writer: while moving, on average;
    the drive's own speed where it is constant; sublight's peak; a coast's
    speeds leaving and arriving. Between the stars in ly a day, within a
    system in km/s."""
    if option.average is None:
        return {}
    if unit == "ly":
        out = {"average_ly_per_day": _figures(option.average)}
        if option.rate:
            out["drive_ly_per_day"] = _figures(option.rate)
        return out
    km_s = lambda au_per_day: _figures(au_per_day * orbits.AU_KM / 86_400)
    out = {"average_km_s": km_s(option.average)}
    if option.rate:
        out["drive_km_s"] = km_s(option.rate)
    thrust = [2 * leg.ly / leg.days for leg in option.legs if leg.kind == "sublight" and leg.days > 0]
    if thrust:
        out["peak_km_s"] = km_s(max(thrust))
    coast = next((leg.speeds for leg in option.legs if leg.speeds), None)
    if coast:
        out["coast_km_s"] = [_figures(v) for v in coast]
    return out


def _figures(days: float) -> float:
    """Days to four significant figures: a near-instant hop keeps its size."""
    return float(f"{days:.4g}")
