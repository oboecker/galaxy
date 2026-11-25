"""Nation territories: dates, colours, and the volume rule.

Synthetic systems, so the tests do not depend on what galaxy.json holds.
"""

import pytest

from galaxy import calendar
from galaxy.territories import (compute, hatch_angle, held_at, nation_colors,
                                ownership)


def test_colours_are_stable_distinct_and_overridable():
    nations = {"a": {}, "b": {}, "c": {"color": "#123456"}}
    colours = nation_colors(nations)
    assert colours["c"] == "#123456"
    assert len(set(colours.values())) == 3
    # Appending a nation leaves the existing ones alone.
    assert nation_colors({**nations, "d": {}})["a"] == colours["a"]
    assert hatch_angle(0) != hatch_angle(1)


def system(name, x, y, z, *affiliations):
    return {"name": name, "x": x, "y": y, "z": z, "affiliations": list(affiliations)}


def test_held_at_respects_dates_and_world():
    data = {"star_systems": [
        system("A", 0, 0, 0, {"nation": "n", "from": "AD 100", "to": "AD 200"}),
        system("B", 0, 0, 0, {"nation": "n", "from": "AD 100", "world": "+"}),
    ]}
    held = lambda at, world=None: sorted(s["name"] for s, _ in held_at(data, calendar.current().point(at), world))
    assert held("AD 150") == ["A"]
    assert held("AD 150", "+") == ["A", "B"]
    assert held("AD 200", "+") == ["B"], "'to' is exclusive"
    assert held("AD 50", "+") == []


def stacked(dz):
    """Two nations, one system each, at the same x–y, `dz` apart in z."""
    return {
        "nations": {"low": {"claim_radius": 1000}, "high": {"claim_radius": 1000}},
        "star_systems": [
            system("L", 0, 0, -dz / 2, {"nation": "low", "from": "AD 0"}),
            system("H", 0, 0, dz / 2, {"nation": "high", "from": "AD 0"}),
        ],
    }


@pytest.mark.parametrize("dz, gap", [(3000, True), (1200, False)])
def test_nations_stacked_in_z_are_separate_volumes(dz, gap):
    data = stacked(dz)
    grid = ownership(data, held_at(data, calendar.current().point("AD 1"), None))
    # Sampled from one system to the other, so the ends are certainly claimed.
    column = [grid.at(0, 0, -dz / 2 + dz * i / 12) for i in range(13)]
    assert column[0] == 0 and column[-1] == 1, "low below, high above"
    assert (-1 in column) == gap, column
    # Never interleaved: once 'high' starts, 'low' does not come back.
    assert column[column.index(1):].count(0) == 0


def test_each_nation_gets_a_closed_mesh_and_an_overlapping_footprint():
    data = stacked(1200)
    territories = compute(data, calendar.current().point("AD 1"))
    assert [t.nation for t in territories] == ["low", "high"]
    for t in territories:
        assert t.vertices and t.faces and t.footprint and t.label
    # Same x–y, so their projections overlap — by design.
    from shapely.geometry import Polygon
    low, high = (Polygon(t.footprint[0][0]) for t in territories)
    assert low.intersection(high).area > 0.8 * low.area


def test_nothing_held_means_no_territories():
    assert compute({"nations": {}, "star_systems": []}, (0, 0, 0)) == []


# ── through time ─────────────────────────────────────────────────────────────

from galaxy.territories import snapshots, worlds


def timeline():
    return {
        "nations": {"a": {}, "b": {}},
        "star_systems": [
            system("S1", 0, 0, 0, {"nation": "a"}),
            system("S2", 3000, 0, 0, {"nation": "a", "to": "AD 500"},
                   {"nation": "b", "from": "AD 500"}),
            system("S3", 6000, 0, 0, {"nation": "b", "from": "AD 300", "world": "+"}),
            # Ends and restarts on the same date: no change, so no new interval.
            system("S4", 9000, 0, 0, {"nation": "b", "to": "AD 700"}, {"nation": "b", "from": "AD 700"}),
        ],
    }


def intervals(data, world):
    return [(s.start, s.end, sorted(s.key)) for s in snapshots(data, world)]


def test_history_splits_at_every_change_and_merges_non_changes():
    got = intervals(timeline(), None)
    assert [(a, b) for a, b, _ in got] == [(None, "AD 500"), ("AD 500", None)]
    assert ("S2", "a") in got[0][2] and ("S2", "b") in got[1][2]


def test_a_branch_adds_its_own_changes_to_the_shared_ones():
    data = timeline()
    assert worlds(data) == [None, "+"]
    got = intervals(data, "+")
    assert [(a, b) for a, b, _ in got] == [(None, "AD 300"), ("AD 300", "AD 500"), ("AD 500", None)]
    assert ("S3", "b") in got[1][2]
    assert all(("S3", "b") not in k for _, _, k in intervals(data, None))


def test_nations_json_holdings_are_attached_to_their_systems():
    from galaxy.territories import attach

    data = {"star_systems": [system("S1", 0, 0, 0), system("S2", 0, 0, 0)]}
    unknown = attach(data, {"nations": {"a": {"name": "A", "claim_radius": 800, "holdings": [
        "S1", {"system": "S2", "from": "AD 5", "world": "+"}, "Atlantis"]}}})
    assert data["nations"] == {"a": {"name": "A", "claim_radius": 800}}
    assert data["star_systems"][0]["affiliations"] == [{"nation": "a"}]
    assert data["star_systems"][1]["affiliations"] == [{"nation": "a", "from": "AD 5", "world": "+"}]
    assert unknown == ["Atlantis"], "skipped here, reported by canon"
