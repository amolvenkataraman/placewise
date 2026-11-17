"""Days spent per country or state, with the evidence behind every counted day."""

import datetime as dt
from collections import Counter
from dataclasses import dataclass

from ._base import Model, set_field

RULES = frozenset({"any_part", "slept", "majority"})
LEVELS = frozenset({"country", "admin1"})


@dataclass(frozen=True, slots=True)
class DayPresence(Model):
    date: dt.date  # local date
    codes: tuple[str, ...]  # countries (or admin1 codes) counted for that day
    first_fix: dt.datetime
    last_fix: dt.datetime

    def __post_init__(self):
        set_field(self, "codes", tuple(self.codes))
        if self.last_fix < self.first_fix:
            raise ValueError("last fix is before the first")


@dataclass(frozen=True, slots=True)
class PresenceDays(Model):
    by: str
    rule: str
    days: tuple[DayPresence, ...]

    def __post_init__(self):
        if self.by not in LEVELS or self.rule not in RULES:
            raise ValueError(f"by must be one of {sorted(LEVELS)} and rule one of {sorted(RULES)}")
        set_field(self, "days", tuple(self.days))

    def totals(self, year=None):
        """Days per code, optionally for one calendar year."""
        return dict(Counter(c for d in self.days if year is None or d.date.year == year for c in d.codes))

    def evidence(self, code, date):
        """The day record behind one counted day, or None if that day wasn't counted for code."""
        return next((d for d in self.days if d.date == date and code in d.codes), None)
