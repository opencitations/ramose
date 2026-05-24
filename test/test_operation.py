# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from ramose import Operation, OperationConfig

if TYPE_CHECKING:
    from collections.abc import Callable

TypedTable = list[list[str] | list[tuple[object, str]]]


class TestGetContentType:
    def test_csv(self) -> None:
        assert Operation.get_content_type("csv") == "text/csv"

    def test_json(self) -> None:
        assert Operation.get_content_type("json") == "application/json"

    def test_passthrough(self) -> None:
        assert Operation.get_content_type("text/plain") == "text/plain"


class TestConv:
    @pytest.fixture
    def op(self) -> Operation:
        op_item = {
            "url": "/test/{id}",
            "sparql": "SELECT ?x WHERE { ?x ?y ?z }",
            "method": "get",
            "field_type": "str(name) int(age)",
        }
        return Operation(
            "/api/v1/test/value",
            "/api/v1/test/(.+)",
            op_item,
            OperationConfig(sparql_endpoint="http://localhost:9999/sparql"),
        )

    def test_csv_output(self, op: Operation) -> None:
        csv_str = "name,age\nJohn,30\n"
        result, ct = op.conv(csv_str, {}, "text/csv")
        assert result == csv_str
        assert ct == "text/csv"

    def test_json_output(self, op: Operation) -> None:
        csv_str = "name,age\nJohn,30\n"
        result, ct = op.conv(csv_str, {}, "application/json")
        parsed = json.loads(result)
        assert parsed == [{"name": "John", "age": "30"}]
        assert ct == "application/json"

    def test_format_override_via_query_string(self, op: Operation) -> None:
        csv_str = "name,age\nJohn,30\n"
        result, ct = op.conv(csv_str, {"format": ["json"]}, "text/csv")
        parsed = json.loads(result)
        assert parsed == [{"name": "John", "age": "30"}]
        assert ct == "application/json"

    def test_format_override_csv(self, op: Operation) -> None:
        csv_str = "name,age\nJohn,30\n"
        result, ct = op.conv(csv_str, {"format": ["csv"]}, "application/json")
        assert result == csv_str
        assert ct == "text/csv"


class TestPvTv:
    """``pv`` and ``tv`` extract the plain or typed value from a result item.
    When called with a single item (a tuple), they return the respective
    element directly. When called with an index and a row (a list of tuples),
    they look up the item by index first."""

    def test_pv_without_row(self) -> None:
        item = ("typed_val", "plain_val")
        assert Operation.pv(item) == "plain_val"

    def test_pv_with_row(self) -> None:
        row = [("typed_0", "plain_0"), ("typed_1", "plain_1")]
        assert Operation.pv(1, row) == "plain_1"  # type: ignore[arg-type]

    def test_tv_without_row(self) -> None:
        item = ("typed_val", "plain_val")
        assert Operation.tv(item) == "typed_val"

    def test_tv_with_row(self) -> None:
        row = [("typed_0", "plain_0"), ("typed_1", "plain_1")]
        assert Operation.tv(0, row) == "typed_0"  # type: ignore[arg-type]


class TestDoOverlap:
    """``do_overlap`` checks whether two integer ranges overlap. Ranges are
    inclusive on both ends, so touching at a single point (e.g. (1, 5) and
    (5, 7)) counts as overlapping."""

    def test_overlapping_ranges(self) -> None:
        assert Operation.do_overlap((1, 5), (3, 7)) is True

    def test_non_overlapping_ranges(self) -> None:
        assert Operation.do_overlap((1, 3), (5, 7)) is False

    def test_touching_ranges(self) -> None:
        assert Operation.do_overlap((1, 5), (5, 7)) is True

    def test_contained_range(self) -> None:
        assert Operation.do_overlap((1, 10), (3, 5)) is True

    def test_reversed_contained(self) -> None:
        assert Operation.do_overlap((3, 5), (1, 10)) is True


class TestGetItemInDict:
    """``get_item_in_dict`` traverses a dictionary (or a list of dictionaries)
    following a chain of keys and collects all matching leaf values. Previously
    accumulated results can be carried over via the ``prev`` parameter."""

    def test_single_key(self) -> None:
        d = {"a": 1}
        assert Operation.get_item_in_dict(d, ["a"]) == [1]  # type: ignore[arg-type]

    def test_nested_keys(self) -> None:
        d = {"a": {"b": 2}}
        assert Operation.get_item_in_dict(d, ["a", "b"]) == [2]  # type: ignore[arg-type]

    def test_list_of_dicts(self) -> None:
        d_list = [{"a": 1}, {"a": 2}]
        assert Operation.get_item_in_dict(d_list, ["a"]) == [1, 2]  # type: ignore[arg-type]

    def test_missing_key(self) -> None:
        d = {"a": 1}
        assert Operation.get_item_in_dict(d, ["b"]) == []  # type: ignore[arg-type]

    def test_with_prev(self) -> None:
        d = {"a": 1}
        assert Operation.get_item_in_dict(d, ["a"], prev=[0]) == [0, 1]  # type: ignore[arg-type]


class TestAddItemInDict:
    def test_single_key_dict(self) -> None:
        d = {"a": 1}
        Operation.add_item_in_dict(d, ["a"], 99, 0)  # type: ignore[arg-type]
        assert d["a"] == 99

    def test_nested_key_dict(self) -> None:
        d = {"a": {"b": 1}}
        Operation.add_item_in_dict(d, ["a", "b"], 99, 0)  # type: ignore[arg-type]
        assert d["a"]["b"] == 99

    def test_list_of_dicts(self) -> None:
        d_list = [{"a": 1}, {"a": 2}]
        Operation.add_item_in_dict(d_list, ["a"], 99, 0)  # type: ignore[arg-type]
        assert d_list[0]["a"] == 99
        assert d_list[1]["a"] == 2

    def test_nested_in_list(self) -> None:
        d_list = [{"a": {"b": 1}}, {"a": {"b": 2}}]
        Operation.add_item_in_dict(d_list, ["a", "b"], 99, 0)  # type: ignore[arg-type]
        assert d_list[0]["a"]["b"] == 99


class TestStructured:
    def test_no_json_param(self) -> None:
        table = [{"name": "John"}]
        assert Operation.structured({}, table) == [{"name": "John"}]  # type: ignore[arg-type]

    def test_array_operation(self) -> None:
        table = [{"names": "Doe, John; Doe, Jane"}]
        params = {"json": ['array("; ",names)']}
        result = Operation.structured(params, table)  # type: ignore[arg-type]
        assert result[0]["names"] == ["Doe, John", "Doe, Jane"]

    def test_array_empty_value(self) -> None:
        table = [{"names": ""}]
        params = {"json": ['array("; ",names)']}
        result = Operation.structured(params, table)  # type: ignore[arg-type]
        assert result[0]["names"] == []

    def test_dict_operation(self) -> None:
        table = [{"name": "Doe, John"}]
        params = {"json": ['dict(", ",name,fname,gname)']}
        result = Operation.structured(params, table)  # type: ignore[arg-type]
        assert result[0]["name"] == {"fname": "Doe", "gname": "John"}

    def test_dict_empty_value(self) -> None:
        table = [{"name": ""}]
        params = {"json": ['dict(", ",name,fname,gname)']}
        result = Operation.structured(params, table)  # type: ignore[arg-type]
        assert result[0]["name"] == {}

    def test_dict_on_list_value(self) -> None:
        table = [{"name": ["Doe, John", "Smith, Jane"]}]
        params = {"json": ['dict(", ",name,fname,gname)']}
        result = Operation.structured(params, table)  # type: ignore[arg-type]
        assert result[0]["name"] == [
            {"fname": "Doe", "gname": "John"},
            {"fname": "Smith", "gname": "Jane"},
        ]


@pytest.fixture
def make_operation() -> Callable[..., Operation]:
    def _make(
        op_url: str = "/api/v1/test/value",
        op_key: str = "/api/v1/test/(.+)",
        op_item: dict[str, str] | None = None,
        config: OperationConfig | None = None,
    ) -> Operation:
        if op_item is None:
            op_item = {
                "url": "/test/{id}",
                "sparql": "SELECT ?x WHERE { ?x ?y ?z }",
                "method": "get",
                "field_type": "str(name) int(age)",
            }
        if config is None:
            config = OperationConfig(sparql_endpoint="http://localhost:9999/sparql")
        return Operation(op_url, op_key, op_item, config)

    return _make


class TestHandlingParams:
    """``handling_params`` applies query-string directives (``require``,
    ``filter``, ``sort``) to a typed result table. Filters support comparison
    operators (``>``, ``<``, ``=``) and regex matching. Sort accepts
    ``asc()``, ``desc()``, or bare field names (defaults to ascending).
    Invalid field names are silently ignored."""

    @pytest.fixture
    def typed_table(self, make_operation: Callable[..., Operation]) -> TypedTable:
        op = make_operation()
        raw = [
            ["name", "age", "city"],
            ["alice", "30", "rome"],
            ["bob", "25", "milan"],
            ["charlie", "", "rome"],
        ]
        return op.type_fields(raw, {"field_type": "str(name) int(age) str(city)"})  # type: ignore[arg-type]

    def test_require(self, make_operation: Callable[..., Operation], typed_table: TypedTable) -> None:
        op = make_operation()
        result = op.handling_params({"require": ["age"]}, typed_table)
        names = [Operation.pv(0, row) for row in result[1:]]  # type: ignore[arg-type]
        assert names == ["alice", "bob"]

    def test_filter_gt(self, make_operation: Callable[..., Operation], typed_table: TypedTable) -> None:
        op = make_operation()
        result = op.handling_params({"filter": ["age:>26"]}, typed_table)
        names = [Operation.pv(0, row) for row in result[1:]]  # type: ignore[arg-type]
        assert names == ["alice"]

    def test_filter_eq(self, make_operation: Callable[..., Operation], typed_table: TypedTable) -> None:
        op = make_operation()
        result = op.handling_params({"filter": ["age:=25"]}, typed_table)
        names = [Operation.pv(0, row) for row in result[1:]]  # type: ignore[arg-type]
        assert names == ["bob"]

    def test_filter_lt(self, make_operation: Callable[..., Operation], typed_table: TypedTable) -> None:
        op = make_operation()
        result = op.handling_params({"filter": ["age:<30"]}, typed_table)
        names = [Operation.pv(0, row) for row in result[1:]]  # type: ignore[arg-type]
        assert names == ["bob", "charlie"]

    def test_filter_regex(self, make_operation: Callable[..., Operation], typed_table: TypedTable) -> None:
        op = make_operation()
        result = op.handling_params({"filter": ["name:ali.*"]}, typed_table)
        names = [Operation.pv(0, row) for row in result[1:]]  # type: ignore[arg-type]
        assert names == ["alice"]

    def test_filter_invalid_field(self, make_operation: Callable[..., Operation], typed_table: TypedTable) -> None:
        op = make_operation()
        result = op.handling_params({"filter": ["nonexistent:>5"]}, typed_table)
        assert len(result) == len(typed_table)

    def test_sort_asc(self, make_operation: Callable[..., Operation], typed_table: TypedTable) -> None:
        op = make_operation()
        result = op.handling_params({"sort": ["asc(name)"]}, typed_table)
        names = [Operation.pv(0, row) for row in result[1:]]  # type: ignore[arg-type]
        assert names == ["alice", "bob", "charlie"]

    def test_sort_desc(self, make_operation: Callable[..., Operation], typed_table: TypedTable) -> None:
        op = make_operation()
        result = op.handling_params({"sort": ["desc(name)"]}, typed_table)
        names = [Operation.pv(0, row) for row in result[1:]]  # type: ignore[arg-type]
        assert names == ["charlie", "bob", "alice"]

    def test_sort_without_order(self, make_operation: Callable[..., Operation], typed_table: TypedTable) -> None:
        op = make_operation()
        result = op.handling_params({"sort": ["name"]}, typed_table)
        names = [Operation.pv(0, row) for row in result[1:]]  # type: ignore[arg-type]
        assert names == ["alice", "bob", "charlie"]

    def test_sort_invalid_field(self, make_operation: Callable[..., Operation], typed_table: TypedTable) -> None:
        op = make_operation()
        result = op.handling_params({"sort": ["asc(nonexistent)"]}, typed_table)
        assert len(result) == len(typed_table)


class TestPostprocess:
    def test_norm_join_key_none(self, make_operation: Callable[..., Operation]) -> None:
        op = make_operation()
        assert op._norm_join_key(None) is None

    def test_postprocess_with_params(self, make_operation: Callable[..., Operation]) -> None:
        class FakeAddon:
            @staticmethod
            def filter_by(result: TypedTable, col: str, val: str) -> tuple[TypedTable, bool]:
                header = result[0]
                col_idx = header.index(col)  # type: ignore[arg-type]
                filtered = [row for row in result[1:] if Operation.pv(col_idx, row) == val]  # type: ignore[arg-type]
                return [header, *filtered], False

        op_item = {
            "url": "/test/{id}",
            "sparql": "SELECT ?x WHERE { ?x ?y ?z }",
            "method": "get",
            "field_type": "str(name) str(city)",
            "postprocess": "filter_by(name, alice)",
        }
        config = OperationConfig(sparql_endpoint="http://localhost:9999/sparql", addon=FakeAddon)  # type: ignore[arg-type]
        op = make_operation(op_item=op_item, config=config)
        raw = [
            ["name", "city"],
            ["alice", "rome"],
            ["bob", "milan"],
        ]
        typed = op.type_fields(raw, op_item)  # type: ignore[arg-type]
        result = op.postprocess(typed, op_item, FakeAddon)  # type: ignore[arg-type]
        names = [Operation.pv(0, row) for row in result[1:]]  # type: ignore[arg-type]
        assert names == ["alice"]
