# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from ramose import APIManager, Operation, OperationConfig

if "pysparql_anything" not in sys.modules:
    _mock_module = ModuleType("pysparql_anything")
    _mock_module.SparqlAnything = MagicMock()  # type: ignore[attr-defined]
    sys.modules["pysparql_anything"] = _mock_module

TESTS_DIR = str(Path(__file__).resolve().parent / "fixtures")


class TestCustomFormatConversion:
    """Test pluggable format converters via the conv() method.
    Uses test_scholarly.hf which declares: #format upper,to_upper;dummyxml,to_dummyxml;xml,to_xml"""

    def _make_op_with_formats(self) -> Operation:
        am = APIManager(
            [str(Path(TESTS_DIR) / "test_scholarly.hf")],
            endpoint_override="http://mock/sparql",
        )
        op = am.get_op("/api/v1/metadata/10.1108/jd-12-2013-0166")
        assert isinstance(op, Operation)
        return op

    def test_xml_format_via_query_string(self) -> None:
        op = self._make_op_with_formats()
        csv_str = "qid,doi\nQ24260641,10.1108/JD-12-2013-0166\n"
        result, ct = op.conv(csv_str, {"format": ["xml"]})
        assert ct == "xml"
        assert '<?xml version="1.0"' in result
        assert "<records>" in result
        assert "<qid>Q24260641</qid>" in result

    def test_upper_format_via_query_string(self) -> None:
        op = self._make_op_with_formats()
        csv_str = "name,age\nvergine,30\n"
        result, _ = op.conv(csv_str, {"format": ["upper"]})
        assert result == "NAME,AGE\nVERGINE,30\n"

    def test_dummyxml_format_via_query_string(self) -> None:
        op = self._make_op_with_formats()
        csv_str = "name,age\nvergine,30\n"
        result, _ = op.conv(csv_str, {"format": ["dummyxml"]})
        assert "<xml>" in result
        assert "vergine" in result

    def test_unknown_format_falls_back_to_csv(self) -> None:
        op = self._make_op_with_formats()
        csv_str = "name,age\nvergine,30\n"
        result, ct = op.conv(csv_str, {"format": ["nonexistent"]})
        assert ct == "text/csv"
        assert result == csv_str


class TestDefaultFormat:
    def test_default_format_used_when_no_query_param(self) -> None:
        op_item = {
            "url": "/test/{id}",
            "id": "str(.+)",
            "sparql": "SELECT ?name WHERE { }",
            "method": "get",
            "field_type": "str(name)",
            "default_format": "upper",
        }

        class FakeAddon:
            @staticmethod
            def to_upper(csv_str: str, request_url: str = "") -> str:
                return csv_str.upper()

        op = Operation(
            "/api/test/hello",
            r"/api/test/(.+)",
            op_item,
            OperationConfig(
                sparql_endpoint="http://unused/sparql",
                addon=FakeAddon,  # type: ignore[arg-type]
                format_map={"upper": "to_upper"},
            ),
        )
        csv_str = "name,age\narcangelo,30\n"
        result, _ = op.conv(csv_str, {})
        assert result == "NAME,AGE\nARCANGELO,30\n"

    def test_explicit_format_overrides_default(self) -> None:
        op_item = {
            "url": "/test/{id}",
            "id": "str(.+)",
            "sparql": "SELECT ?name WHERE { }",
            "method": "get",
            "field_type": "str(name)",
            "default_format": "upper",
        }

        class FakeAddon:
            @staticmethod
            def to_upper(csv_str: str, request_url: str = "") -> str:
                return csv_str.upper()

            @staticmethod
            def to_dummyxml(csv_str: str, request_url: str = "") -> str:
                return f"<xml>\n{csv_str}\n</xml>"

        op = Operation(
            "/api/test/hello",
            r"/api/test/(.+)",
            op_item,
            OperationConfig(
                sparql_endpoint="http://unused/sparql",
                addon=FakeAddon,  # type: ignore[arg-type]
                format_map={"upper": "to_upper", "dummyxml": "to_dummyxml"},
            ),
        )
        csv_str = "name,age\narcangelo,30\n"
        result, _ = op.conv(csv_str, {"format": ["dummyxml"]})
        assert "<xml>" in result
        assert "arcangelo" in result

    def test_default_format_json(self) -> None:
        op_item = {
            "url": "/test/{id}",
            "id": "str(.+)",
            "sparql": "SELECT ?name WHERE { }",
            "method": "get",
            "field_type": "str(name)",
            "default_format": "json",
        }
        op = Operation(
            "/api/test/hello",
            r"/api/test/(.+)",
            op_item,
            OperationConfig(sparql_endpoint="http://unused/sparql"),
        )
        csv_str = "name\narcangelo\n"
        result, ct = op.conv(csv_str, {})
        assert ct == "application/json"
        assert json.loads(result) == [{"name": "arcangelo"}]

    def test_no_default_format_falls_back_to_csv(self) -> None:
        op_item = {
            "url": "/test/{id}",
            "id": "str(.+)",
            "sparql": "SELECT ?name WHERE { }",
            "method": "get",
            "field_type": "str(name)",
        }
        op = Operation(
            "/api/test/hello",
            r"/api/test/(.+)",
            op_item,
            OperationConfig(sparql_endpoint="http://unused/sparql"),
        )
        csv_str = "name\narcangelo\n"
        result, ct = op.conv(csv_str, {})
        assert ct == "text/csv"
        assert result == csv_str


class TestCustomFormatThroughExec:
    def test_xml_output_through_exec(self) -> None:
        am = APIManager(
            [str(Path(TESTS_DIR) / "test_scholarly.hf")],
            endpoint_override="http://mock/sparql",
        )
        op = am.get_op("/api/v1/metadata/10.1108/jd-12-2013-0166?format=xml")
        assert isinstance(op, Operation)

        resp = SimpleNamespace(
            status_code=200,
            text=(
                "qid,author,year,title,source_title,source_id,volume,issue,page,doi,reference,citation_count\n"
                "Q24260641,,2015,Setting our bibliographic references free,,,,,,10.1108/JD-12-2013-0166,,1\n"
            ),
            reason="OK",
            encoding=None,
        )
        with patch("ramose.operation._http_session") as mock_session:
            mock_session.post.return_value = resp
            sc, body, ctype, _ = op.exec(method="get", content_type="text/csv")

        assert sc == 200
        assert ctype == "xml"
        assert '<?xml version="1.0"' in body
        assert "<record>" in body
        assert "Q24260641" in body


class TestAPIManagerConfigParsing:
    def test_addon_loaded(self) -> None:
        am = APIManager(
            [str(Path(TESTS_DIR) / "test_scholarly.hf")],
            endpoint_override="http://mock/sparql",
        )
        base = am.base_url[0]
        addon = am.all_conf[base]["addon"]
        assert addon is not None
        assert hasattr(addon, "to_xml")
        assert hasattr(addon, "to_upper")
        assert hasattr(addon, "to_dummyxml")

    def test_format_map_built_correctly(self) -> None:
        am = APIManager(
            [str(Path(TESTS_DIR) / "test_scholarly.hf")],
            endpoint_override="http://mock/sparql",
        )
        op = am.get_op("/api/v1/metadata/10.1108/jd-12-2013-0166")
        assert isinstance(op, Operation)
        assert op.format == {"upper": "to_upper", "dummyxml": "to_dummyxml", "xml": "to_xml"}


class TestSparqlAnythingSingleQueryExec:
    def test_sparql_anything_engine_exec(self) -> None:
        op_item = {
            "url": "/test/{id}",
            "id": "str(.+)",
            "sparql": "SELECT ?title WHERE { SERVICE <x-sparql-anything:...> { ?r ?p ?title } }",
            "method": "get",
            "field_type": "str(title)",
        }
        op = Operation(
            "/api/test/hello",
            r"/api/test/(.+)",
            op_item,
            OperationConfig(
                sparql_endpoint="http://unused/sparql",
                format_map={},
                sources_map={},
                engine="sparql-anything",
            ),
        )

        with patch.object(op, "_run_sparql_anything_dicts", return_value=[{"title": "Test Paper"}]):
            sc, body, ctype, _ = op.exec(method="get", content_type="application/json")

        assert sc == 200
        assert ctype == "application/json"
        rows = json.loads(body)
        assert len(rows) == 1
        assert rows[0]["title"] == "Test Paper"


class TestRunSparqlAnythingDictsNormalization:
    def _make_op(self) -> Operation:
        op_item = {
            "url": "/test/{id}",
            "id": "str(.+)",
            "sparql": "SELECT ?x WHERE { }",
            "method": "get",
            "field_type": "str(x)",
        }
        return Operation(
            "/api/test/v",
            r"/api/test/(.+)",
            op_item,
            OperationConfig(sparql_endpoint="http://ep/sparql", engine="sparql-anything"),
        )

    def test_list_of_dicts(self) -> None:
        op = self._make_op()
        with patch("pysparql_anything.SparqlAnything") as mock_sa:
            mock_sa.return_value.select.return_value = [{"x": "a"}, {"x": "b"}]
            rows = op._run_sparql_anything_dicts("SELECT ?x WHERE { }")
        assert rows == [{"x": "a"}, {"x": "b"}]

    def test_sparql_json_resultset(self) -> None:
        op = self._make_op()
        sparql_result = {
            "head": {"vars": ["x", "y"]},
            "results": {
                "bindings": [
                    {"x": {"type": "literal", "value": "a"}, "y": {"type": "literal", "value": "1"}},
                    {"x": {"type": "literal", "value": "b"}, "y": {"type": "literal", "value": "2"}},
                ],
            },
        }
        with patch("pysparql_anything.SparqlAnything") as mock_sa:
            mock_sa.return_value.select.return_value = sparql_result
            rows = op._run_sparql_anything_dicts("SELECT ?x ?y WHERE { }")
        assert len(rows) == 2
        assert rows[0] == {"x": "a", "y": "1"}
        assert rows[1] == {"x": "b", "y": "2"}

    def test_columnar_dict(self) -> None:
        op = self._make_op()
        with patch("pysparql_anything.SparqlAnything") as mock_sa:
            mock_sa.return_value.select.return_value = {"x": ["a", "b"], "y": ["1", "2"]}
            rows = op._run_sparql_anything_dicts("SELECT ?x ?y WHERE { }")
        assert len(rows) == 2
        assert rows[0] == {"x": "a", "y": "1"}
        assert rows[1] == {"x": "b", "y": "2"}

    def test_single_dict_fallback(self) -> None:
        op = self._make_op()
        with patch("pysparql_anything.SparqlAnything") as mock_sa:
            mock_sa.return_value.select.return_value = {"x": "a"}
            rows = op._run_sparql_anything_dicts("SELECT ?x WHERE { }")
        assert rows == [{"x": "a"}]

    def test_non_dict_result(self) -> None:
        op = self._make_op()
        with patch("pysparql_anything.SparqlAnything") as mock_sa:
            mock_sa.return_value.select.return_value = "raw_string"
            rows = op._run_sparql_anything_dicts("SELECT ?x WHERE { }")
        assert rows == [{"result": "raw_string"}]

    def test_list_of_non_dicts_coerced(self) -> None:
        op = self._make_op()
        with patch("pysparql_anything.SparqlAnything") as mock_sa:
            mock_sa.return_value.select.return_value = [[("x", "a")], [("x", "b")]]
            rows = op._run_sparql_anything_dicts("SELECT ?x WHERE { }")
        assert rows == [{"x": "a"}, {"x": "b"}]

    def test_sparql_json_non_dict_cell(self) -> None:
        op = self._make_op()
        sparql_result = {
            "head": {"vars": ["x"]},
            "results": {
                "bindings": [
                    {"x": "plain_value"},
                ],
            },
        }
        with patch("pysparql_anything.SparqlAnything") as mock_sa:
            mock_sa.return_value.select.return_value = sparql_result
            rows = op._run_sparql_anything_dicts("SELECT ?x WHERE { }")
        assert rows == [{"x": "plain_value"}]

    def test_columnar_dict_with_scalar(self) -> None:
        op = self._make_op()
        with patch("pysparql_anything.SparqlAnything") as mock_sa:
            mock_sa.return_value.select.return_value = {"x": ["a", "b"], "label": "fixed"}
            rows = op._run_sparql_anything_dicts("SELECT ?x ?label WHERE { }")
        assert len(rows) == 2
        assert rows[0] == {"x": "a", "label": "fixed"}
        assert rows[1] == {"x": "b", "label": "fixed"}

    def test_values_param_passed(self) -> None:
        op = self._make_op()
        with patch("pysparql_anything.SparqlAnything") as mock_sa:
            mock_sa.return_value.select.return_value = [{"x": "a"}]
            op._run_sparql_anything_dicts("Q", values={"doi": "10.1"})
        call_kwargs = mock_sa.return_value.select.call_args
        assert call_kwargs[1]["values"] == {"doi": "10.1"}


class TestRunQueryDictsDispatch:
    def _make_op(self, engine: str = "sparql") -> Operation:
        op_item = {
            "url": "/test/{id}",
            "id": "str(.+)",
            "sparql": "SELECT ?x WHERE { }",
            "method": "get",
            "field_type": "str(x)",
        }
        return Operation(
            "/api/test/v",
            r"/api/test/(.+)",
            op_item,
            OperationConfig(sparql_endpoint="http://ep/sparql", engine=engine),
        )

    def test_op_level_sparql_anything_engine(self) -> None:
        op = self._make_op(engine="sparql-anything")
        with patch.object(op, "_run_sparql_anything_dicts", return_value=[{"x": "1"}]) as mock_sa:
            rows = op._run_query_dicts("http://some-endpoint/sparql", "SELECT ?x WHERE { }")
        mock_sa.assert_called_once_with("SELECT ?x WHERE { }")
        assert rows == [{"x": "1"}]


class TestSparqlAnythingSingleQueryWithAddon:
    def test_postprocess_called(self) -> None:
        class FakeAddon:
            @staticmethod
            def my_post(
                result: list[list[str] | list[tuple[object, str]]],
            ) -> tuple[list[list[str] | list[tuple[object, str]]], bool]:
                return result, False

        op_item = {
            "url": "/test/{id}",
            "id": "str(.+)",
            "sparql": "SELECT ?title WHERE { }",
            "method": "get",
            "field_type": "str(title)",
            "postprocess": "my_post()",
        }
        op = Operation(
            "/api/test/hello",
            r"/api/test/(.+)",
            op_item,
            OperationConfig(
                sparql_endpoint="http://unused/sparql",
                addon=FakeAddon,  # type: ignore[arg-type]
                format_map={},
                sources_map={},
                engine="sparql-anything",
            ),
        )

        with patch.object(op, "_run_sparql_anything_dicts", return_value=[{"title": "Test"}]):
            sc, _body, _ctype, _ = op.exec(method="get", content_type="application/json")

        assert sc == 200


class TestInjectValuesNoWhereBrace:
    def _make_op(self) -> Operation:
        op_item = {
            "url": "/test/{id}",
            "id": "str(.+)",
            "sparql": "SELECT ?x WHERE { }",
            "method": "get",
            "field_type": "str(x)",
        }
        return Operation("/api/test/v", r"/api/test/(.+)", op_item, OperationConfig(sparql_endpoint="http://ep/sparql"))

    def test_no_brace_puts_values_at_top(self) -> None:
        op = self._make_op()
        acc = [{"x": "val"}]
        query = "CONSTRUCT WHERE SOMETHING"
        result = op._inject_values_clause(query, ["?x"], acc)  # type: ignore[arg-type]
        assert result.startswith("VALUES (?x)")
        assert "CONSTRUCT WHERE SOMETHING" in result
