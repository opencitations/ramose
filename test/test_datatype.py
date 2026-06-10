# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

from datetime import datetime, timezone
from sys import maxsize

import pytest

from ramose import DataType


@pytest.fixture
def dt() -> DataType:
    return DataType()


class TestGetFunc:
    def test_returns_correct_function_for_each_type(self, dt: DataType) -> None:
        assert dt.get_func("str") == DataType.str
        assert dt.get_func("int") == DataType.int
        assert dt.get_func("float") == DataType.float
        assert dt.get_func("duration") == DataType.duration
        assert dt.get_func("datetime") == DataType.datetime

    def test_raises_for_unknown_type(self, dt: DataType) -> None:
        with pytest.raises(KeyError):
            dt.get_func("unknown")


class TestDuration:
    def test_valid_duration(self) -> None:
        result = DataType.duration("P1Y")
        assert result == datetime(1984, 1, 15, tzinfo=timezone.utc)

    def test_negative_duration(self) -> None:
        result = DataType.duration("-P1Y")
        assert result == datetime(1982, 1, 15, tzinfo=timezone.utc)

    def test_negative_duration_days(self) -> None:
        result = DataType.duration("-P0Y0M1D")
        assert result == datetime(1983, 1, 14, tzinfo=timezone.utc)

    def test_none_returns_high_duration(self) -> None:
        result = DataType.duration(None)
        assert result == datetime(3983, 1, 15, tzinfo=timezone.utc)

    def test_empty_string_returns_high_duration(self) -> None:
        result = DataType.duration("")
        assert result == datetime(3983, 1, 15, tzinfo=timezone.utc)


class TestDatetime:
    def test_valid_date(self) -> None:
        result = DataType.datetime("2023-06-15")
        assert result == datetime(2023, 6, 15, 0, 0, tzinfo=timezone.utc)

    def test_none_returns_low_date(self) -> None:
        result = DataType.datetime(None)
        assert result == datetime(1, 1, 1, 0, 0, tzinfo=timezone.utc)

    def test_empty_string_returns_low_date(self) -> None:
        result = DataType.datetime("")
        assert result == datetime(1, 1, 1, 0, 0, tzinfo=timezone.utc)


class TestStr:
    def test_valid_string(self) -> None:
        assert DataType.str("Hello") == "hello"

    def test_none_returns_empty(self) -> None:
        assert DataType.str(None) == ""

    def test_numeric_input(self) -> None:
        assert DataType.str(42) == "42"  # type: ignore[arg-type]


class TestInt:
    def test_valid_int(self) -> None:
        assert DataType.int("42") == 42

    def test_none_returns_negative_maxsize(self) -> None:
        assert DataType.int(None) == -maxsize

    def test_empty_string_returns_negative_maxsize(self) -> None:
        assert DataType.int("") == -maxsize


class TestFloat:
    def test_valid_float(self) -> None:
        assert DataType.float("3.14") == 3.14

    def test_none_returns_negative_maxsize(self) -> None:
        assert DataType.float(None) == float(-maxsize)

    def test_empty_string_returns_negative_maxsize(self) -> None:
        assert DataType.float("") == float(-maxsize)
