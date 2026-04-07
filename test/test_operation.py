# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import json

import pytest

from ramose import Operation


class TestGetContentType:
    def test_csv(self):
        assert Operation.get_content_type("csv") == "text/csv"

    def test_json(self):
        assert Operation.get_content_type("json") == "application/json"

    def test_passthrough(self):
        assert Operation.get_content_type("text/plain") == "text/plain"


class TestConv:
    @pytest.fixture
    def op(self):
        op_item = {
            "url": "/test/{id}",
            "sparql": "SELECT ?x WHERE { ?x ?y ?z }",
            "method": "get",
            "field_type": "str(name) int(age)",
        }
        return Operation(
            "/api/v1/test/value", "/api/v1/test/(.+)", op_item, "http://localhost:9999/sparql", "get", None
        )

    def test_csv_output(self, op):
        csv_str = "name,age\nJohn,30\n"
        result, ct = op.conv(csv_str, {}, "text/csv")
        assert result == csv_str
        assert ct == "text/csv"

    def test_json_output(self, op):
        csv_str = "name,age\nJohn,30\n"
        result, ct = op.conv(csv_str, {}, "application/json")
        parsed = json.loads(result)
        assert parsed == [{"name": "John", "age": "30"}]
        assert ct == "application/json"

    def test_format_override_via_query_string(self, op):
        csv_str = "name,age\nJohn,30\n"
        result, ct = op.conv(csv_str, {"format": ["json"]}, "text/csv")
        parsed = json.loads(result)
        assert parsed == [{"name": "John", "age": "30"}]
        assert ct == "application/json"

    def test_format_override_csv(self, op):
        csv_str = "name,age\nJohn,30\n"
        result, ct = op.conv(csv_str, {"format": ["csv"]}, "application/json")
        assert result == csv_str
        assert ct == "text/csv"


class TestPvTv:
    """``pv`` and ``tv`` extract the plain or typed value from a result item.
    When called with a single item (a tuple), they return the respective
    element directly. When called with an index and a row (a list of tuples),
    they look up the item by index first."""

    def test_pv_without_row(self):
        item = ("typed_val", "plain_val")
        assert Operation.pv(item) == "plain_val"

    def test_pv_with_row(self):
        row = [("typed_0", "plain_0"), ("typed_1", "plain_1")]
        assert Operation.pv(1, row) == "plain_1"

    def test_tv_without_row(self):
        item = ("typed_val", "plain_val")
        assert Operation.tv(item) == "typed_val"

    def test_tv_with_row(self):
        row = [("typed_0", "plain_0"), ("typed_1", "plain_1")]
        assert Operation.tv(0, row) == "typed_0"


class TestDoOverlap:
    """``do_overlap`` checks whether two integer ranges overlap. Ranges are
    inclusive on both ends, so touching at a single point (e.g. (1, 5) and
    (5, 7)) counts as overlapping."""

    def test_overlapping_ranges(self):
        assert Operation.do_overlap((1, 5), (3, 7)) is True

    def test_non_overlapping_ranges(self):
        assert Operation.do_overlap((1, 3), (5, 7)) is False

    def test_touching_ranges(self):
        assert Operation.do_overlap((1, 5), (5, 7)) is True

    def test_contained_range(self):
        assert Operation.do_overlap((1, 10), (3, 5)) is True

    def test_reversed_contained(self):
        assert Operation.do_overlap((3, 5), (1, 10)) is True


class TestGetItemInDict:
    """``get_item_in_dict`` traverses a dictionary (or a list of dictionaries)
    following a chain of keys and collects all matching leaf values. Previously
    accumulated results can be carried over via the ``prev`` parameter."""

    def test_single_key(self):
        d = {"a": 1}
        assert Operation.get_item_in_dict(d, ["a"]) == [1]

    def test_nested_keys(self):
        d = {"a": {"b": 2}}
        assert Operation.get_item_in_dict(d, ["a", "b"]) == [2]

    def test_list_of_dicts(self):
        d_list = [{"a": 1}, {"a": 2}]
        assert Operation.get_item_in_dict(d_list, ["a"]) == [1, 2]

    def test_missing_key(self):
        d = {"a": 1}
        assert Operation.get_item_in_dict(d, ["b"]) == []

    def test_with_prev(self):
        d = {"a": 1}
        assert Operation.get_item_in_dict(d, ["a"], prev=[0]) == [0, 1]


class TestAddItemInDict:
    def test_single_key_dict(self):
        d = {"a": 1}
        Operation.add_item_in_dict(d, ["a"], 99, 0)
        assert d["a"] == 99

    def test_nested_key_dict(self):
        d = {"a": {"b": 1}}
        Operation.add_item_in_dict(d, ["a", "b"], 99, 0)
        assert d["a"]["b"] == 99

    def test_list_of_dicts(self):
        d_list = [{"a": 1}, {"a": 2}]
        Operation.add_item_in_dict(d_list, ["a"], 99, 0)
        assert d_list[0]["a"] == 99
        assert d_list[1]["a"] == 2

    def test_nested_in_list(self):
        d_list = [{"a": {"b": 1}}, {"a": {"b": 2}}]
        Operation.add_item_in_dict(d_list, ["a", "b"], 99, 0)
        assert d_list[0]["a"]["b"] == 99


class TestStructured:
    def test_no_json_param(self):
        table = [{"name": "John"}]
        assert Operation.structured({}, table) == [{"name": "John"}]

    def test_array_operation(self):
        table = [{"names": "Doe, John; Doe, Jane"}]
        params = {"json": ['array("; ",names)']}
        result = Operation.structured(params, table)
        assert result[0]["names"] == ["Doe, John", "Doe, Jane"]

    def test_array_empty_value(self):
        table = [{"names": ""}]
        params = {"json": ['array("; ",names)']}
        result = Operation.structured(params, table)
        assert result[0]["names"] == []

    def test_dict_operation(self):
        table = [{"name": "Doe, John"}]
        params = {"json": ['dict(", ",name,fname,gname)']}
        result = Operation.structured(params, table)
        assert result[0]["name"] == {"fname": "Doe", "gname": "John"}

    def test_dict_empty_value(self):
        table = [{"name": ""}]
        params = {"json": ['dict(", ",name,fname,gname)']}
        result = Operation.structured(params, table)
        assert result[0]["name"] == {}

    def test_dict_on_list_value(self):
        table = [{"name": ["Doe, John", "Smith, Jane"]}]
        params = {"json": ['dict(", ",name,fname,gname)']}
        result = Operation.structured(params, table)
        assert result[0]["name"] == [
            {"fname": "Doe", "gname": "John"},
            {"fname": "Smith", "gname": "Jane"},
        ]


@pytest.fixture
def make_operation():
    def _make(
        op_url="/api/v1/test/value",
        op_key="/api/v1/test/(.+)",
        op_item=None,
        tp="http://localhost:9999/sparql",
        sparql_http_method="get",
        addon=None,
    ):
        if op_item is None:
            op_item = {
                "url": "/test/{id}",
                "sparql": "SELECT ?x WHERE { ?x ?y ?z }",
                "method": "get",
                "field_type": "str(name) int(age)",
            }
        return Operation(op_url, op_key, op_item, tp, sparql_http_method, addon)

    return _make


class TestHandlingParams:
    """``handling_params`` applies query-string directives (``require``,
    ``filter``, ``sort``) to a typed result table. Filters support comparison
    operators (``>``, ``<``, ``=``) and regex matching. Sort accepts
    ``asc()``, ``desc()``, or bare field names (defaults to ascending).
    Invalid field names are silently ignored."""

    @pytest.fixture
    def typed_table(self, make_operation):
        op = make_operation()
        raw = [
            ["name", "age", "city"],
            ["alice", "30", "rome"],
            ["bob", "25", "milan"],
            ["charlie", "", "rome"],
        ]
        return op.type_fields(raw, {"field_type": "str(name) int(age) str(city)"})

    def test_require(self, make_operation, typed_table):
        op = make_operation()
        result = op.handling_params({"require": ["age"]}, typed_table)
        names = [Operation.pv(0, row) for row in result[1:]]
        assert names == ["alice", "bob"]

    def test_filter_gt(self, make_operation, typed_table):
        op = make_operation()
        result = op.handling_params({"filter": ["age:>26"]}, typed_table)
        names = [Operation.pv(0, row) for row in result[1:]]
        assert names == ["alice"]

    def test_filter_eq(self, make_operation, typed_table):
        op = make_operation()
        result = op.handling_params({"filter": ["age:=25"]}, typed_table)
        names = [Operation.pv(0, row) for row in result[1:]]
        assert names == ["bob"]

    def test_filter_lt(self, make_operation, typed_table):
        op = make_operation()
        result = op.handling_params({"filter": ["age:<30"]}, typed_table)
        names = [Operation.pv(0, row) for row in result[1:]]
        assert names == ["bob", "charlie"]

    def test_filter_regex(self, make_operation, typed_table):
        op = make_operation()
        result = op.handling_params({"filter": ["name:ali.*"]}, typed_table)
        names = [Operation.pv(0, row) for row in result[1:]]
        assert names == ["alice"]

    def test_filter_invalid_field(self, make_operation, typed_table):
        op = make_operation()
        result = op.handling_params({"filter": ["nonexistent:>5"]}, typed_table)
        assert len(result) == len(typed_table)

    def test_sort_asc(self, make_operation, typed_table):
        op = make_operation()
        result = op.handling_params({"sort": ["asc(name)"]}, typed_table)
        names = [Operation.pv(0, row) for row in result[1:]]
        assert names == ["alice", "bob", "charlie"]

    def test_sort_desc(self, make_operation, typed_table):
        op = make_operation()
        result = op.handling_params({"sort": ["desc(name)"]}, typed_table)
        names = [Operation.pv(0, row) for row in result[1:]]
        assert names == ["charlie", "bob", "alice"]

    def test_sort_without_order(self, make_operation, typed_table):
        op = make_operation()
        result = op.handling_params({"sort": ["name"]}, typed_table)
        names = [Operation.pv(0, row) for row in result[1:]]
        assert names == ["alice", "bob", "charlie"]

    def test_sort_invalid_field(self, make_operation, typed_table):
        op = make_operation()
        result = op.handling_params({"sort": ["asc(nonexistent)"]}, typed_table)
        assert len(result) == len(typed_table)


class TestPostprocess:
    def test_norm_join_key_none(self, make_operation):
        op = make_operation()
        assert op._norm_join_key(None) is None

    def test_postprocess_with_params(self, make_operation):
        class FakeAddon:
            @staticmethod
            def filter_by(result, col, val):
                header = result[0]
                col_idx = header.index(col)
                filtered = [row for row in result[1:] if Operation.pv(col_idx, row) == val]
                return [header, *filtered], False

        op_item = {
            "url": "/test/{id}",
            "sparql": "SELECT ?x WHERE { ?x ?y ?z }",
            "method": "get",
            "field_type": "str(name) str(city)",
            "postprocess": "filter_by(name, alice)",
        }
        op = make_operation(op_item=op_item, addon=FakeAddon)
        raw = [
            ["name", "city"],
            ["alice", "rome"],
            ["bob", "milan"],
        ]
        typed = op.type_fields(raw, op_item)
        result = op.postprocess(typed, op_item, FakeAddon)
        names = [Operation.pv(0, row) for row in result[1:]]
        assert names == ["alice"]
