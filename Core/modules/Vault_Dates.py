#!/usr/bin/env python3
"""Natural-language dates for vault tasks and events. Clock is America/Chicago.

Speech always labels the time CT, including during daylight time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


@dataclass
class When:
    day: date
    clock: Optional[time] = None

    @property
    def all_day(self) -> bool:
        return self.clock is None

    @property
    def iso_date(self) -> str:
        return self.day.isoformat()

    @property
    def hhmm(self) -> str:
        if self.clock is None:
            return ""
        return self.clock.strftime("%H:%M")


def now_ct() -> datetime:
    return datetime.now(CT)


def speak_when(moment: When) -> str:
    """Fri Oct 23 CT, or Fri Oct 23, 7:00 PM CT."""
    label = f"{moment.day.strftime('%a')} {moment.day.strftime('%b')} {moment.day.day}"
    if moment.clock is None:
        return f"{label} CT"
    hour = moment.clock.hour % 12 or 12
    suffix = "AM" if moment.clock.hour < 12 else "PM"
    return f"{label}, {hour}:{moment.clock.minute:02d} {suffix} CT"


def parse_when(text: str, now: Optional[datetime] = None) -> Optional[When]:
    """Pull one date, and a clock time if the words include one."""
    raw = (text or "").strip().lower()
    if not raw:
        return None
    moment = now or now_ct()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=CT)
    clock = _parse_clock(raw)
    cleaned = _strip_clock(raw)
    cleaned = re.sub(r"\b(by|due|on|at|for|this|coming)\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if re.search(r"\btonight\b", raw):
        return When(moment.date(), clock or time(19, 0))
    if re.search(r"\btomorrow\b", cleaned):
        return When(moment.date() + timedelta(days=1), clock)
    if re.search(r"\btoday\b", cleaned):
        return When(moment.date(), clock)
    if re.search(r"\bnext week\b", raw) and not _weekday_in(cleaned):
        return When(moment.date() + timedelta(days=7), clock)

    weekday = _weekday_in(cleaned)
    if weekday is not None:
        nxt = bool(re.search(r"\bnext\b", raw))
        delta = (weekday - moment.weekday()) % 7
        if nxt:
            delta = 7 if delta == 0 else delta + 7
        return When(moment.date() + timedelta(days=delta), clock)

    iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", raw)
    if iso:
        try:
            return When(date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))), clock)
        except ValueError:
            return None

    month = re.search(
        r"\b(" + "|".join(_MONTHS) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(20\d{2}))?\b",
        cleaned,
    )
    if month:
        year = int(month.group(3)) if month.group(3) else moment.year
        try:
            found = date(year, _MONTHS[month.group(1)], int(month.group(2)))
        except ValueError:
            return None
        if not month.group(3) and found < moment.date():
            try:
                found = date(year + 1, found.month, found.day)
            except ValueError:
                return None
        return When(found, clock)
    if clock and re.fullmatch(r"(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?", raw.strip()):
        return When(moment.date(), clock)
    return None


def end_after(start: time, hours: int = 1) -> time:
    """One hour later, staying on the same calendar day."""
    total = start.hour * 60 + start.minute + hours * 60
    if total >= 24 * 60:
        return time(23, 59)
    return time(total // 60, total % 60)


def _weekday_in(text: str) -> Optional[int]:
    for name, index in _WEEKDAYS.items():
        if re.search(rf"\b{name}\b", text):
            return index
    return None


def _parse_clock(text: str) -> Optional[time]:
    match = re.search(
        r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
        text,
    )
    if not match:
        match = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
        if not match:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2))
        if hour > 23 or minute > 59:
            return None
        return time(hour, minute)
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    suffix = match.group(3)
    if minute > 59 or hour > 12 or hour == 0:
        return None
    if suffix == "pm" and hour < 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    return time(hour, minute)


def _strip_clock(text: str) -> str:
    text = re.sub(r"\b(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", " ", text)
    text = re.sub(r"\b\d{1,2}:\d{2}\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()
