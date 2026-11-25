"""A project's calendar: its eras on one axis of years, and dates as they are
written, `ERA YEAR[-MM[-DD]]`.

The axis is the Gregorian year (year 0 is 1 BC as astronomers count), so the
real sky's positions (J2000) and a story's dates share it. Each era places
its year 0 on the axis and counts forward (1) or back (-1). Months and days
run forward in every era, as in the Gregorian calendar.

calendar.json:

    {"eras": {"BC": {"zero": 0, "direction": -1}, "AD": {"zero": 0, "direction": 1}},
     "written": [{"era": "AD", "from": 1}, {"era": "BC"}],
     "epoch": "AD 2000"}

`written` says which era a date on the axis is written in: the first whose
`from` (a year on the axis) it has reached; one without `from` takes the
rest. `epoch` is the date the orbits' phases are given for.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from galaxy import project

Point = tuple[int, int, int]  # absolute year, month, day

# The most days each month has, 29 February included: a date is read without
# asking whether its year is a leap year.
DAYS = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
# A year's days by month, for a date as a fraction of its year.
MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
YEAR_DAYS = 365.25


@dataclass(frozen=True)
class Calendar:
    eras: dict[str, tuple[int, int]]                 # era → (its year 0 on the axis, direction)
    written: tuple[tuple[str, Optional[int]], ...]   # (era, from), in order
    epoch: str

    @property
    def _date(self) -> re.Pattern:
        names = "|".join(re.escape(e) for e in self.eras)
        return re.compile(rf"^({names}) (\d+)(?:-(\d{{1,2}}))?(?:-(\d{{1,2}}))?$")

    @property
    def _years(self) -> re.Pattern:
        names = "|".join(re.escape(e) for e in self.eras)
        return re.compile(rf"^({names})\s+(\d+(?:\.\d+)?)(?:-(\d{{1,2}}))?(?:-(\d{{1,2}}))?"
                          rf"(?:\s*,\s*day\s+(\d+))?$", re.IGNORECASE)

    def to_absolute(self, era: str, year: float) -> float:
        """Year `year` of `era` as a year on the axis."""
        zero, direction = self.eras[era]
        return zero + direction * year

    def parse(self, date: str) -> tuple[str, int, Optional[int], Optional[int]]:
        """(era, year in era, month, day); month and day None when not given.
        Refused (ValueError) for anything that is not `ERA YEAR[-MM[-DD]]`,
        and for a month or day no calendar has."""
        m = self._date.match(date.strip())
        if not m:
            raise ValueError(f"not an 'ERA YEAR[-MM[-DD]]' date: {date!r}")
        era, year, month, day = m.groups()
        month, day = int(month) if month else None, int(day) if day else None
        if month is not None and not 1 <= month <= 12:
            raise ValueError(f"no month {month} in {date!r}")
        if day is not None and not 1 <= day <= DAYS[month - 1]:
            raise ValueError(f"no day {day} of month {month} in {date!r}")
        return era, int(year), month, day

    def absolute_year(self, date: str) -> int:
        """The year of `date` on the axis, for ordering dates across eras."""
        era, year, _, _ = self.parse(date)
        return int(self.to_absolute(era, year))

    def point(self, date: str, end: bool = False) -> Point:
        """`date` on the axis with its month and day, so two dates in one year
        order too. A missing part is the start of its year or month, or with
        `end` past its end."""
        era, year, month, day = self.parse(date)
        missing = 99 if end else 0
        return (int(self.to_absolute(era, year)),
                month if month is not None else missing,
                day if day is not None else missing)

    def years(self, text: str) -> float:
        """A date on the axis in years, with its fraction: "AD 523.5", as a
        timeline writes it ("AD 523-04-12", the start of the day) or as the
        maps show it ("AD 523, day 120", its noon). Refused (ValueError) for
        text that is none of these, or a month or day out of range."""
        m = self._years.match(text.strip())
        if not m:
            example = self.parse(self.epoch)[0]
            raise ValueError(f"{text!r} is not a date like {example} 523.5, {example} 523-04-12 "
                             f"or {example} 523, day 120")
        era, year, month, day, of_year = m.groups()
        era = next(e for e in self.eras if e.upper() == era.upper())
        value = float(year)
        if (month or of_year) and "." in year:
            raise ValueError(f"{text!r}: a year with a fraction has no month or day")
        if month and not 1 <= int(month) <= 12:
            raise ValueError(f"{text!r}: the month is 1–12")
        if day and not 1 <= int(day) <= MONTH_DAYS[int(month) - 1]:
            raise ValueError(f"{text!r}: day {int(day)} is not in month {int(month)} "
                             f"(1–{MONTH_DAYS[int(month) - 1]})")
        if of_year and not 1 <= int(of_year) <= 366:
            raise ValueError(f"{text!r}: the day of the year is 1–366")
        within = 0.0
        if month:
            days = sum(MONTH_DAYS[:int(month) - 1]) + (int(day) - 1 if day else 0)
            within = days / YEAR_DAYS
        elif of_year:
            within = (int(of_year) - 0.5) / YEAR_DAYS
        # The era's direction counts the years; a year's months and days run
        # forward in every era.
        return self.to_absolute(era, value) + within

    def era_of(self, whole: int) -> tuple[str, int]:
        """The era a year on the axis is written in, and its year there."""
        for era, start in self.written:
            if start is None or whole >= start:
                zero, direction = self.eras[era]
                return era, (whole - zero) * direction
        raise ValueError(f"no era is written for the year {whole}")

    def text(self, absolute: float) -> str:
        """A date on the axis (years) as the maps show it: "AD 523, day 120"."""
        whole = math.floor(absolute)
        day = int((absolute - whole) * YEAR_DAYS + 1e-6) + 1      # a day's start is that day, not a hair before
        era, year = self.era_of(whole)
        return f"{era} {year}, day {day}"

    @property
    def epoch_year(self) -> int:
        """The epoch as a year on the axis."""
        return self.absolute_year(self.epoch)

    def as_dict(self) -> dict:
        """The definition as calendar.json holds it."""
        return {"eras": {e: {"zero": z, "direction": d} for e, (z, d) in self.eras.items()},
                "written": [{"era": e, **({"from": f} if f is not None else {})} for e, f in self.written],
                "epoch": self.epoch}


def from_dict(doc: dict) -> Calendar:
    """The calendar a calendar.json document defines."""
    eras = {name: (int(e["zero"]), int(e["direction"])) for name, e in doc["eras"].items()}
    for name, (_, direction) in eras.items():
        if direction not in (1, -1):
            raise ValueError(f"era {name}: direction is 1 or -1")
    written = tuple((w["era"], w.get("from")) for w in doc["written"])
    for era, _ in written:
        if era not in eras:
            raise ValueError(f"written: no era {era}")
    if written[-1][1] is not None:
        raise ValueError("written: the last era takes the rest (no `from`)")
    return Calendar(eras, written, doc["epoch"])


@lru_cache(maxsize=4)
def load(path: Path) -> Calendar:
    """The calendar the calendar.json at `path` defines."""
    return from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def current() -> Calendar:
    """The current project's calendar."""
    return load(project.current().calendar)
