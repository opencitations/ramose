from datetime import datetime
from sys import maxsize

import pytest
from isodate import parse_duration

from ramose import DataType


@pytest.fixture
def dt():
    return DataType()


class TestGetFunc:
    def test_returns_correct_function_for_each_type(self, dt):
        assert dt.get_func("str") == DataType.str
        assert dt.get_func("int") == DataType.int
        assert dt.get_func("float") == DataType.float
        assert dt.get_func("duration") == DataType.duration
        assert dt.get_func("datetime") == DataType.datetime

    def test_returns_none_for_unknown_type(self, dt):
        assert dt.get_func("unknown") is None


class TestDuration:
    def test_valid_duration(self):
        result = DataType.duration("P1Y")
        expected = datetime(1983, 1, 15) + parse_duration("P1Y")
        assert result == expected

    def test_none_returns_high_duration(self):
        result = DataType.duration(None)
        expected = datetime(1983, 1, 15) + parse_duration("P2000Y")
        assert result == expected

    def test_empty_string_returns_high_duration(self):
        result = DataType.duration("")
        expected = datetime(1983, 1, 15) + parse_duration("P2000Y")
        assert result == expected


class TestDatetime:
    def test_valid_date(self):
        result = DataType.datetime("2023-06-15")
        assert result == datetime(2023, 6, 15, 0, 0)

    def test_none_returns_low_date(self):
        result = DataType.datetime(None)
        assert result == datetime(1, 1, 1, 0, 0)

    def test_empty_string_returns_low_date(self):
        result = DataType.datetime("")
        assert result == datetime(1, 1, 1, 0, 0)


class TestStr:
    def test_valid_string(self):
        assert DataType.str("Hello") == "hello"

    def test_none_returns_empty(self):
        assert DataType.str(None) == ""

    def test_numeric_input(self):
        assert DataType.str(42) == "42"


class TestInt:
    def test_valid_int(self):
        assert DataType.int("42") == 42

    def test_none_returns_negative_maxsize(self):
        assert DataType.int(None) == -maxsize

    def test_empty_string_returns_negative_maxsize(self):
        assert DataType.int("") == -maxsize


class TestFloat:
    def test_valid_float(self):
        assert DataType.float("3.14") == 3.14

    def test_none_returns_negative_maxsize(self):
        assert DataType.float(None) == float(-maxsize)

    def test_empty_string_returns_negative_maxsize(self):
        assert DataType.float("") == float(-maxsize)
