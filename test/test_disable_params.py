# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import json
from pathlib import Path

import pytest
import yaml

from ramose import APIManager, HTMLDocumentationHandler, OpenAPIDocumentationHandler
from ramose.hash_format import BUILTIN_PARAMS, parse_disable_params
from ramose.operation import Operation

DATA_DIR = Path(__file__).parent / "data"


class TestParseDisableParams:
    def test_single_param(self):
        assert parse_disable_params("filter") == {"filter"}

    def test_multiple_params(self):
        assert parse_disable_params("require,filter,sort") == {"require", "filter", "sort"}

    def test_wildcard(self):
        assert parse_disable_params("*") == {"require", "filter", "sort", "format", "json"}

    def test_wildcard_matches_builtin(self):
        assert parse_disable_params("*") == set(BUILTIN_PARAMS)

    def test_whitespace_handling(self):
        assert parse_disable_params(" filter , sort ") == {"filter", "sort"}

    def test_empty_string(self):
        assert parse_disable_params("") == set()

    def test_trailing_comma(self):
        assert parse_disable_params("filter,sort,") == {"filter", "sort"}


def _make_op(disabled_params=None, format_map=None, addon=None, op_item_extra=None):
    op_item = {
        "url": "/test/{id}",
        "sparql": "SELECT ?x WHERE { ?x ?y ?z }",
        "method": "get",
        "field_type": "str(name) int(age)",
    }
    if op_item_extra:
        op_item.update(op_item_extra)
    return Operation(
        "/api/v1/test/value",
        "/api/v1/test/(.+)",
        op_item,
        "http://localhost:9999/sparql",
        "get",
        addon,
        format_map=format_map or {},
        disabled_params=disabled_params,
    )


class TestHandlingParamsDisabled:
    @staticmethod
    def _typed_table(rows):
        header = rows[0]
        return [header, *[[(v, v) for v in row] for row in rows[1:]]]

    def test_require_disabled(self):
        op = _make_op(disabled_params={"require"})
        table = self._typed_table([["name", "age"], ["John", "30"], ["", "25"]])
        result = op.handling_params({"require": ["name"]}, table)
        assert len(result) == 3

    def test_require_active(self):
        op = _make_op()
        table = self._typed_table([["name", "age"], ["John", "30"], ["", "25"]])
        result = op.handling_params({"require": ["name"]}, table)
        assert len(result) == 2

    def test_filter_disabled(self):
        op = _make_op(disabled_params={"filter"})
        table = self._typed_table([["name", "age"], ["John", "30"], ["Jane", "25"]])
        result = op.handling_params({"filter": ["name:John"]}, table)
        assert len(result) == 3

    def test_sort_disabled(self):
        op = _make_op(disabled_params={"sort"})
        table = self._typed_table([["name", "age"], ["John", "30"], ["Alice", "20"]])
        result = op.handling_params({"sort": ["asc(name)"]}, table)
        assert result[1][0] == ("John", "John")

    def test_all_disabled(self):
        op = _make_op(disabled_params=set(BUILTIN_PARAMS))
        table = self._typed_table([["name", "age"], ["", "30"], ["John", "25"]])
        result = op.handling_params({"require": ["name"], "filter": ["age:30"], "sort": ["asc(name)"]}, table)
        assert len(result) == 3
        assert result[1][0] == ("", "")
        assert result[2][0] == ("John", "John")


class TestConvFormatDisabled:
    def test_format_param_ignored_when_disabled(self):
        op = _make_op(disabled_params={"format"})
        csv_str = "name,age\nJohn,30\n"
        result, ct = op.conv(csv_str, {"format": ["json"]}, "text/csv")
        assert ct == "text/csv"
        assert result == csv_str

    def test_format_param_works_when_not_disabled(self):
        op = _make_op()
        csv_str = "name,age\nJohn,30\n"
        result, ct = op.conv(csv_str, {"format": ["json"]}, "text/csv")
        assert ct == "application/json"
        parsed = json.loads(result)
        assert parsed == [{"name": "John", "age": "30"}]

    def test_default_format_still_works_when_format_disabled(self):
        class FakeAddon:
            @staticmethod
            def to_custom(s):
                return '{"custom": true}'

        op = _make_op(
            disabled_params={"format"},
            format_map={"custom": "to_custom"},
            addon=FakeAddon,
            op_item_extra={"default_format": "custom"},
        )
        csv_str = "name,age\nJohn,30\n"
        result, _ct = op.conv(csv_str, {}, "text/csv")
        assert result == '{"custom": true}'


class TestConvJsonDisabled:
    def test_json_structuring_ignored_when_disabled(self):
        op = _make_op(disabled_params={"json"})
        csv_str = "name,age\nDoe; John,30\n"
        result, _ct = op.conv(csv_str, {"json": ['array("; ",name)']}, "application/json")
        parsed = json.loads(result)
        assert parsed == [{"name": "Doe; John", "age": "30"}]

    def test_json_structuring_works_when_not_disabled(self):
        op = _make_op()
        csv_str = "name,age\nDoe; John,30\n"
        result, _ct = op.conv(csv_str, {"json": ['array("; ",name)']}, "application/json")
        parsed = json.loads(result)
        assert parsed == [{"name": ["Doe", "John"], "age": "30"}]


class TestApiManagerDisableParams:
    def test_api_level_disable_propagates(self):
        mgr = APIManager(
            [str(DATA_DIR / "skgif_products.hf")],
            endpoint_override="http://localhost:9999/sparql",
        )
        for conf in mgr.all_conf.values():
            assert conf["disable_params"] == set(BUILTIN_PARAMS)

    def test_operation_gets_disabled_params(self):
        mgr = APIManager(
            [str(DATA_DIR / "skgif_products.hf")],
            endpoint_override="http://localhost:9999/sparql",
        )
        op = mgr.get_op("/skgif/v1/products/https://w3id.org/oc/meta/br/0612058700")
        assert isinstance(op, Operation)
        assert op.disabled_params == set(BUILTIN_PARAMS)

    def test_no_disable_params_defaults_to_empty(self):
        mgr = APIManager(
            [str(DATA_DIR / "meta_v1.hf")],
            endpoint_override="http://localhost:9999/sparql",
        )
        for conf in mgr.all_conf.values():
            assert conf["disable_params"] == set()


class TestHtmlDocumentationDisableParams:
    def test_all_params_hidden_when_disabled(self):
        mgr = APIManager(
            [str(DATA_DIR / "skgif_products.hf")],
            endpoint_override="http://localhost:9999/sparql",
        )
        handler = HTMLDocumentationHandler(mgr)
        _, html = handler.get_documentation()
        assert "require=" not in html
        assert "sort=" not in html
        assert "format=" not in html
        for keyword in ["require", "sort", "format=", "json="]:
            assert f"<code>{keyword}" not in html

    def test_params_visible_when_not_disabled(self):
        mgr = APIManager(
            [str(DATA_DIR / "meta_v1.hf")],
            endpoint_override="http://localhost:9999/sparql",
        )
        handler = HTMLDocumentationHandler(mgr)
        _, html = handler.get_documentation()
        assert "require=" in html
        assert "filter=" in html
        assert "sort=" in html
        assert "format=" in html


class TestOpenApiDocumentationDisableParams:
    @pytest.fixture
    def skgif_spec(self):
        mgr = APIManager(
            [str(DATA_DIR / "skgif_products.hf")],
            endpoint_override="http://localhost:9999/sparql",
        )
        handler = OpenAPIDocumentationHandler(mgr)
        _, yml = handler.get_documentation()
        return yaml.safe_load(yml)

    def test_no_global_param_refs_on_products(self, skgif_spec):
        products_get = skgif_spec["paths"]["/products"]["get"]
        ref_names = {p["$ref"].rsplit("/", 1)[-1] for p in products_get["parameters"] if "$ref" in p}
        for builtin in BUILTIN_PARAMS:
            assert builtin not in ref_names

    def test_custom_filter_still_present(self, skgif_spec):
        products_get = skgif_spec["paths"]["/products"]["get"]
        inline_names = {p["name"] for p in products_get["parameters"] if "name" in p}
        assert "filter" in inline_names

    def test_single_product_has_no_global_params(self, skgif_spec):
        single_get = skgif_spec["paths"]["/products/{local_identifier}"]["get"]
        ref_names = {p["$ref"].rsplit("/", 1)[-1] for p in single_get["parameters"] if "$ref" in p}
        for builtin in BUILTIN_PARAMS:
            assert builtin not in ref_names
