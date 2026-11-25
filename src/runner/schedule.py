"""When scheduled execute groups run, and how their dates and repeats read.

Times are local and naive, the way the user picks them on the dial. A repeat
counts forward from the date picked: "Mon 09:00, every 1 week" runs every
Monday at 09:00. Months are calendar months, counted from the start each time,
so a run on the 31st lands on the 30th in a 30-day month and is back on the
31st the month after.

A run that was missed, because Runner was closed or the computer was asleep,
is skipped. The scheduler only runs what falls due while it is watching.
"""

from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta

from .config import Group, ScheduleEntry

# The roller's units, left to right, and how each reads in a sentence.
UNIT_NAMES = (("months", "month"), ("weeks", "week"), ("days", "day"), ("hours", "hour"), ("minutes", "minute"))
NO_REPEAT = "Does not repeat"


def add_months(when: datetime, months: int) -> datetime:
    """Same day and time, months later. A day the month does not have becomes its last day."""
    index = when.month - 1 + months
    year, month = when.year + index // 12, index % 12 + 1
    day = min(when.day, calendar.monthrange(year, month)[1])
    return when.replace(year=year, month=month, day=day)


def _fixed_part(entry: ScheduleEntry) -> timedelta:
    return timedelta(weeks=entry.weeks, days=entry.days, hours=entry.hours, minutes=entry.minutes)


def occurrence(entry: ScheduleEntry, k: int) -> datetime:
    """The k-th run of entry: k = 0 is the date picked."""
    return add_months(entry.when, k * entry.months) + k * _fixed_part(entry)


def next_run(entry: ScheduleEntry, after: datetime) -> datetime | None:
    """The first run strictly after `after`, or None when it never runs again."""
    start = entry.when
    if start > after:
        return start
    if not entry.repeats:
        return None
    fixed = _fixed_part(entry)
    # A first guess from the average step, then walk to the exact run.
    step = fixed + timedelta(days=30.436875 * entry.months)
    k = max(0, int((after - start) / step) - 1)
    while occurrence(entry, k) <= after:
        k += 1
    while k > 0 and occurrence(entry, k - 1) > after:
        k -= 1
    return occurrence(entry, k)


def group_next_run(group: Group, after: datetime) -> datetime | None:
    """The soonest run of any of the group's dates after `after`."""
    runs = [run for run in (next_run(entry, after) for entry in group.schedule) if run is not None]
    return min(runs, default=None)


def due_between(entry: ScheduleEntry, since: datetime, now: datetime) -> datetime | None:
    """A run of entry that falls in (since, now], the most recent one if there are several."""
    run = next_run(entry, since)
    if run is None or run > now:
        return None
    latest = run
    while True:
        later = next_run(entry, latest)
        if later is None or later > now:
            return latest
        latest = later


def interval_parts(entry: ScheduleEntry) -> list[int]:
    return [entry.months, entry.weeks, entry.days, entry.hours, entry.minutes]


def describe_repeat(entry: ScheduleEntry) -> str:
    """'Every 1 week', 'Every 1 day and 12 hours', or 'Does not repeat'."""
    parts = [
        f"{value} {singular if value == 1 else plural}"
        for value, (plural, singular) in zip(interval_parts(entry), UNIT_NAMES, strict=True)
        if value
    ]
    if not parts:
        return NO_REPEAT
    if len(parts) == 1:
        return "Every " + parts[0]
    return "Every " + ", ".join(parts[:-1]) + " and " + parts[-1]


def format_when(when: datetime, *, with_year: bool = True) -> str:
    """'Mon 24 Nov 2026 · 09:00'. Built by hand: %-d is not available on Windows."""
    year = f" {when.year}" if with_year else ""
    return f"{when:%a} {when.day} {when:%b}{year} · {when:%H:%M}"


def format_full(when: datetime) -> str:
    """'Tuesday 24 November 2026 · 09:30', written out in full under the dial."""
    return f"{when:%A} {when.day} {when:%B} {when.year} · {when:%H:%M}"


_MONTH_WORDS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_MONTH_WORDS |= {name.lower(): i for i, name in enumerate(calendar.month_abbr) if name}
_MONTH_WORDS["sept"] = 9
_DAY_WORDS = {name.lower() for name in (*calendar.day_name, *calendar.day_abbr)}
_DAY_WORDS |= {"tues", "thur", "thurs"}
_TIME = re.compile(r"\b(\d{1,2})(?:[:.h](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?(?![\d/-])", re.I)
_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_SLASHED = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2}|\d{4}))?\b")


def parse_when(text: str, base: datetime) -> datetime:
    """A date and time typed by hand, with anything left out taken from `base`.

    Reads what format_full writes ("Tuesday 24 November 2026 · 09:30") and
    looser forms: "24 Nov 2027 18:05", "5 March 9pm", "24/11/2026 09:30"
    (day first), "2026-11-24 9:30", or just "14:45". The weekday is ignored:
    the date decides it. Raises ValueError when it can't make sense of it.
    """
    rest = text.strip().lower().replace("·", " ").replace(",", " ")
    if not rest:
        raise ValueError("Type a date and time.")
    year, month, day = base.year, base.month, base.day
    hour, minute = base.hour, base.minute
    date_found = time_found = numeric_date = False

    match = _ISO.search(rest) or _SLASHED.search(rest)
    if match:
        if match.re is _ISO:
            year, month, day = (int(v) for v in match.groups())
        else:
            day, month = int(match.group(1)), int(match.group(2))
            if match.group(3):
                year = int(match.group(3))
                year += 2000 if year < 100 else 0
        rest = rest[: match.start()] + " " + rest[match.end() :]
        date_found = numeric_date = True

    # A time: has a colon, or am/pm. A bare number is a day or a year instead.
    for match in _TIME.finditer(rest):
        if match.group(2) is None and match.group(3) is None:
            continue
        hour, minute = int(match.group(1)), int(match.group(2) or 0)
        meridiem = (match.group(3) or "").replace(".", "")
        if meridiem:
            if not 1 <= hour <= 12:
                raise ValueError(f"{hour} {meridiem} is not a time.")
            hour = hour % 12 + (12 if meridiem == "pm" else 0)
        rest = rest[: match.start()] + " " + rest[match.end() :]
        time_found = True
        break

    for word in re.findall(r"\d+(?:st|nd|rd|th)?|[a-z]+", rest):
        if word in ("at", "of", "the", "on"):
            continue
        number = re.sub(r"(st|nd|rd|th)$", "", word)
        if number.isdigit():
            if len(number) == 4 and number == word:
                year = int(number)
            elif len(number) <= 2 and not numeric_date:
                day = int(number)
            else:
                raise ValueError(f"Not sure what {word} means here.")
        elif word in _MONTH_WORDS:
            month = _MONTH_WORDS[word]
        elif word in _DAY_WORDS:
            continue
        else:
            raise ValueError(f"Not sure what \"{word}\" means.")
        date_found = True

    if not (date_found or time_found):
        raise ValueError("Type a date and time.")
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"{hour:02d}:{minute:02d} is not a time.")
    if not 1 <= month <= 12:
        raise ValueError(f"There is no month {month}.")
    last = calendar.monthrange(year, month)[1] if 1 <= year <= 9999 else 31
    if not 1 <= day <= last:
        raise ValueError(f"{calendar.month_name[month]} {year} has no day {day}.")
    return datetime(year, month, day, hour, minute)


def scheduled_groups(groups: list[Group]) -> list[Group]:
    return [group for group in groups if group.scheduled]


def execute_groups(groups: list[Group]) -> list[Group]:
    """The groups run by hand: every group that is not scheduled."""
    return [group for group in groups if not group.scheduled]
