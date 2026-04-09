# SPDX-FileCopyrightText: 2018-2021 Silvio Peroni <silvio.peroni@unibo.it>
# SPDX-FileCopyrightText: 2020-2021 Marilena Daquino <marilena.daquino2@unibo.it>
# SPDX-FileCopyrightText: 2022 Davide Brembilla
# SPDX-FileCopyrightText: 2024 Ivan Heibi <ivan.heibi2@unibo.it>
# SPDX-FileCopyrightText: 2025 Sergei Slinkin
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from calendar import monthrange
from datetime import datetime, timedelta, timezone
from re import compile as re_compile
from sys import maxsize
from typing import NamedTuple

# ISO 8601 duration format: PnYnMnDTnHnMnS
# Python's stdlib has no parser for this format, so we handle it manually.
# Each component is optional. The T separator marks the transition from date to time components.
# Examples: "P1Y", "P2M3D", "PT4H5M6S", "P1Y2M3DT4H5M6.5S"
_DURATION_PATTERN = re_compile(
    r"P"
    r"(?:(?P<years>\d+)Y)?"
    r"(?:(?P<months>\d+)M)?"
    r"(?:(?P<days>\d+)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?"
    r")?"
)


class _ISODuration(NamedTuple):
    """Parsed ISO 8601 duration with calendar components kept separate.

    Years and months cannot be converted to a fixed number of days (a month is 28-31 days,
    a year is 365 or 366). Following the same approach as isodate, they are stored as
    integers and resolved only when added to a concrete reference date via calendar arithmetic.
    """

    years: int
    months: int
    remainder: timedelta


def _parse_datetime(date_str: str) -> datetime:
    """Parse ISO 8601 date strings, including partial formats not supported by fromisoformat.

    fromisoformat does not accept year-only ("2015") or year-month ("2015-06") strings,
    so those are handled explicitly. The trailing "Z" suffix is also normalized for Python 3.10
    compatibility, where fromisoformat does not recognize it.
    """
    date_str = date_str.strip()
    if len(date_str) == 4 and date_str.isdigit():
        return datetime(int(date_str), 1, 1, tzinfo=timezone.utc)
    if len(date_str) in (6, 7) and date_str[4] == "-":
        year, month = date_str.split("-")
        return datetime(int(year), int(month), 1, tzinfo=timezone.utc)
    if date_str.endswith("Z"):
        date_str = date_str[:-1] + "+00:00"
    parsed = datetime.fromisoformat(date_str)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_duration(duration_str: str) -> _ISODuration:
    """Parse an ISO 8601 duration string into an _ISODuration."""
    duration_match = _DURATION_PATTERN.fullmatch(duration_str)
    if not duration_match:
        msg = f"Invalid ISO 8601 duration: {duration_str}"
        raise ValueError(msg)
    parts = {key: value or "0" for key, value in duration_match.groupdict().items()}
    return _ISODuration(
        years=int(parts["years"]),
        months=int(parts["months"]),
        remainder=timedelta(
            days=int(parts["days"]),
            hours=int(parts["hours"]),
            minutes=int(parts["minutes"]),
            seconds=float(parts["seconds"]),
        ),
    )


def _add_duration(base: datetime, duration: _ISODuration) -> datetime:
    """Add an ISO 8601 duration to a datetime using calendar arithmetic.

    Years and months are added by adjusting the calendar fields directly,
    clamping the day to the maximum valid day for the resulting month
    (e.g. Jan 31 + 1 month = Feb 28). Days and smaller units are then
    added as a timedelta.
    """
    total_months = base.month + duration.years * 12 + duration.months
    year_carry, new_month = divmod(total_months - 1, 12)
    new_month += 1
    new_year = base.year + year_carry
    max_day = monthrange(new_year, new_month)[1]
    new_day = min(base.day, max_day)
    shifted = base.replace(year=new_year, month=new_month, day=new_day)
    return shifted + duration.remainder


class DataType:
    def __init__(self):
        """This class implements all the possible data types that can be used within
        the configuration file of RAMOSE. In particular, it provides methods for converting
        a string into the related Python data type representation."""
        self.func = {
            "str": DataType.str,
            "int": DataType.int,
            "float": DataType.float,
            "duration": DataType.duration,
            "datetime": DataType.datetime,
        }

    def get_func(self, name_str: str):
        """This method returns the method for handling a given data type expressed as a string name."""
        return self.func[name_str]

    @staticmethod
    def duration(s):
        """This method returns the data type for durations according to the XML Schema
        Recommendation (https://www.w3.org/TR/xmlschema11-2/#duration) from the input string.
        In case the input string is None or it is empty, an high duration value
        (i.e. 2000 years) is returned."""
        duration = _parse_duration("P2000Y") if s is None or s == "" else _parse_duration(s)
        reference_date = datetime(1983, 1, 15, tzinfo=timezone.utc)

        return _add_duration(reference_date, duration)

    @staticmethod
    def datetime(s):
        """This method returns the data type for datetime according to the ISO 8601
        (https://en.wikipedia.org/wiki/ISO_8601) from the input string. In case the input string is None or
        it is empty, a low date value (i.e. 0001-01-01) is returned."""
        return datetime(1, 1, 1, tzinfo=timezone.utc) if s is None or s == "" else _parse_datetime(s)

    @staticmethod
    def str(s):
        """This method returns the data type for strings. In case the input string is None, an empty string
        is returned."""
        return "" if s is None else str(s).lower()

    @staticmethod
    def int(s):
        """This method returns the data type for integer numbers from the input string. In case the input string is
        None or it is empty, a low integer value is returned."""
        return -maxsize if s is None or s == "" else int(s)

    @staticmethod
    def float(s):
        """This method returns the data type for float numbers from the input string. In case the input string is
        None or it is empty, a low float value is returned."""
        return float(-maxsize) if s is None or s == "" else float(s)
