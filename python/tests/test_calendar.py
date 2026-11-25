"""galaxy.calendar: eras on one axis, dates read and written."""

import pytest

from galaxy import calendar

GREGORIAN = calendar.from_dict({
    "eras": {"BC": {"zero": 0, "direction": -1}, "AD": {"zero": 0, "direction": 1}},
    "written": [{"era": "AD", "from": 1}, {"era": "BC"}],
    "epoch": "AD 2000",
})


def test_eras_place_their_years_on_the_axis():
    assert GREGORIAN.absolute_year("AD 2000") == 2000
    assert GREGORIAN.absolute_year("BC 44") == -44
    assert GREGORIAN.epoch_year == 2000


def test_points_order_within_a_year_and_past_its_end():
    assert GREGORIAN.point("AD 5-03-02") == (5, 3, 2)
    assert GREGORIAN.point("AD 5") < GREGORIAN.point("AD 5-01-01")
    assert GREGORIAN.point("AD 5", end=True) > GREGORIAN.point("AD 5-12-31")


@pytest.mark.parametrize("bad", ["AD", "XY 5", "AD 5-13", "AD 5-02-30", "AD 5.5"])
def test_what_is_not_a_date_is_refused(bad):
    with pytest.raises(ValueError):
        GREGORIAN.parse(bad)


def test_years_with_fractions_and_days():
    assert GREGORIAN.years("AD 10.5") == 10.5
    assert GREGORIAN.years("ad 10, day 1") == pytest.approx(10 + 0.5 / 365.25)
    assert GREGORIAN.years("AD 10-01-01") == 10
    with pytest.raises(ValueError, match="like AD 523.5"):
        GREGORIAN.years("soon")


def test_text_writes_the_era_a_year_is_written_in():
    assert GREGORIAN.text(2000.0) == "AD 2000, day 1"
    assert GREGORIAN.text(0.0) == "BC 0, day 1"
    assert GREGORIAN.text(GREGORIAN.years("AD 7, day 120")) == "AD 7, day 120"


def test_a_definition_is_checked():
    with pytest.raises(ValueError, match="no era"):
        calendar.from_dict({"eras": {"AD": {"zero": 0, "direction": 1}}, "written": [{"era": "CE"}], "epoch": "AD 1"})
    with pytest.raises(ValueError, match="takes the rest"):
        calendar.from_dict({"eras": {"AD": {"zero": 0, "direction": 1}},
                            "written": [{"era": "AD", "from": 1}], "epoch": "AD 1"})
    assert calendar.from_dict(GREGORIAN.as_dict()) == GREGORIAN


def test_a_system_record_carries_the_projects_calendar():
    from galaxy import systemmap
    definition = calendar.current().as_dict()
    assert systemmap._calendar() == {"eras": definition["eras"], "written": definition["written"]}
