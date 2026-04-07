# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

from ramose import APIManager, Operation


TESTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests")

# Realistic mock data captured from real endpoints (Wikidata, OpenCitations, Crossref)

WIKIDATA_DOI_QID = [
    {"doi": "10.1108/jd-12-2013-0166", "qid": "Q24260641"},
    {"doi": "10.1038/nature12373", "qid": "Q34460861"},
]

OC_META_BR = [
    {"doi": "10.1108/jd-12-2013-0166", "br": "https://w3id.org/oc/meta/br/06180334099"},
    {"doi": "10.1038/nature12373", "br": "https://w3id.org/oc/meta/br/06120344846"},
]

OC_INDEX_CITATIONS_BR1 = [
    {"br": "https://w3id.org/oc/meta/br/06180334099", "oc_citation_count": "39"},
]

OC_INDEX_CITATIONS_BR2 = [
    {"br": "https://w3id.org/oc/meta/br/06120344846", "oc_citation_count": "1515"},
]

CROSSREF_TITLE_YEAR = [
    {"doi": "10.1108/jd-12-2013-0166", "title": "Setting our bibliographic references free: towards open citation data", "year": "2015"},
    {"doi": "10.1038/nature12373", "title": "Nanometre-scale thermometry in a living cell", "year": "2013"},
]

WIKIDATA_FULL_SCHOLARLY = [
    {
        "author": "",
        "year": "2015",
        "title": "Setting our bibliographic references free: towards open citation data",
        "source_title": "",
        "volume": "71",
        "issue": "2",
        "page": "253-277",
        "doi": "10.1108/jd-12-2013-0166",
        "reference": "10.1136/BMJ.B2680; 10.1145/1816123.1816198",
        "citation_count": "23",
        "qid": "Q24260641",
    },
    {
        "author": "",
        "year": "2013",
        "title": "Nanometre-scale thermometry in a living cell",
        "source_title": "",
        "volume": "500",
        "issue": "7460",
        "page": "54-58",
        "doi": "10.1038/nature12373",
        "reference": "10.1021/NN201142F; 10.1021/NL300389Y",
        "citation_count": "196",
        "qid": "Q34460861",
    },
]


def _load_api_manager(hf_file):
    return APIManager(
        [os.path.join(TESTS_DIR, hf_file)],
        endpoint_override="http://mock-endpoint/sparql",
    )


def _get_operation(am, dois_param):
    base = am.base_url[0]
    op = am.get_op(f"{base}/metadata/{dois_param}")
    assert isinstance(op, Operation)
    return op


class TestMultiSourceJoinEndpointForeachRemove:
    """Full pipeline test for test_scholarly_multi-sources.hf:
    Wikidata -> @@join OC Meta -> @@values + @@foreach OC Index -> @@remove @@join -> result."""

    def test_full_multi_source_pipeline_json(self):
        am = _load_api_manager("test_scholarly_multi-sources.hf")
        op = _get_operation(am, "10.1108/jd-12-2013-0166__10.1038/nature12373")
        assert isinstance(op, Operation)

        def mock_run_sparql(endpoint_url, query_text):
            if "query-scholarly.wikidata.org" in endpoint_url or endpoint_url == "http://mock-endpoint/sparql":
                return list(WIKIDATA_FULL_SCHOLARLY)
            if "opencitations.net/meta" in endpoint_url:
                return list(OC_META_BR)
            if "opencitations.net/index" in endpoint_url:
                if "06180334099" in query_text:
                    return list(OC_INDEX_CITATIONS_BR1)
                if "06120344846" in query_text:
                    return list(OC_INDEX_CITATIONS_BR2)
                return []
            return []

        with patch.object(op, "_run_sparql_dicts", side_effect=mock_run_sparql):
            sc, body, ctype = op.exec(method="get", content_type="application/json")

        assert sc == 200
        assert ctype == "application/json"

        rows = json.loads(body)
        assert len(rows) == 2

        dois = {r["doi"] for r in rows}
        assert dois == {"10.1108/jd-12-2013-0166", "10.1038/nature12373"}

        row_peroni = next(r for r in rows if "jd-12" in r["doi"])
        assert row_peroni["qid"] == "Q24260641"
        assert row_peroni["oc_citation_count"] == "39"
        assert row_peroni["citation_count"] == "23"
        assert "br" not in row_peroni  # @@remove ?br should have dropped it

        row_nature = next(r for r in rows if "nature" in r["doi"])
        assert row_nature["qid"] == "Q34460861"
        assert row_nature["oc_citation_count"] == "1515"


class TestMultiSourceWithSparqlAnything:
    """Full pipeline test for mixed_scholarly_crossref.hf:
    Wikidata SPARQL -> OC Meta -> OC Index (foreach) -> Crossref via SPARQL Anything -> merged result."""

    def test_mixed_sparql_and_sparql_anything(self):
        am = _load_api_manager("mixed_scholarly_crossref.hf")
        op = _get_operation(am, "10.1108/jd-12-2013-0166__10.1038/nature12373")
        assert isinstance(op, Operation)

        def mock_run_sparql(endpoint_url, query_text):
            if "opencitations.net/meta" in endpoint_url:
                return list(OC_META_BR)
            if "opencitations.net/index" in endpoint_url:
                if "06180334099" in query_text:
                    return list(OC_INDEX_CITATIONS_BR1)
                if "06120344846" in query_text:
                    return list(OC_INDEX_CITATIONS_BR2)
                return []
            return list(WIKIDATA_DOI_QID)

        def mock_run_sa(query_text, values=None):
            return list(CROSSREF_TITLE_YEAR)

        with patch.object(op, "_run_sparql_dicts", side_effect=mock_run_sparql), \
             patch.object(op, "_run_sparql_anything_dicts", side_effect=mock_run_sa):
            sc, body, ctype = op.exec(method="get", content_type="application/json")

        assert sc == 200
        rows = json.loads(body)
        assert len(rows) == 2

        row_peroni = next(r for r in rows if "jd-12" in r["doi"].lower())
        assert row_peroni["qid"] == "Q24260641"
        assert row_peroni["oc_citation_count"] == "39"
        assert row_peroni["title"] == "Setting our bibliographic references free: towards open citation data"
        assert row_peroni["year"] == "2015"

        row_nature = next(r for r in rows if "nature" in r["doi"].lower())
        assert row_nature["oc_citation_count"] == "1515"
        assert row_nature["title"] == "Nanometre-scale thermometry in a living cell"
        assert row_nature["year"] == "2013"


class TestMultiSourceErrorHandling:
    def test_sparql_endpoint_failure_returns_502(self):
        am = _load_api_manager("test_scholarly_multi-sources.hf")
        op = _get_operation(am, "10.1108/jd-12-2013-0166")

        def mock_run_sparql(endpoint_url, query_text):
            raise RuntimeError("SPARQL 500: Internal Server Error")

        with patch.object(op, "_run_sparql_dicts", side_effect=mock_run_sparql):
            sc, msg, ct = op.exec(method="get", content_type="application/json")

        assert sc == 502
        assert "502" in msg
        assert ct == "text/plain"


class TestParseSteps:
    def _make_op(self, allow_inline=True, sources_map=None):
        op_item = {
            "url": "/test/{id}",
            "id": "str(.+)",
            "sparql": "SELECT ?x WHERE { ?x ?y ?z }",
            "method": "get",
            "field_type": "str(x)",
        }
        return Operation(
            "/api/test/val", r"/api/test/(.+)", op_item,
            "http://default-endpoint/sparql", "get", None,
            format={}, sources_map=sources_map or {},
            allow_inline_endpoints=allow_inline,
        )

    def test_simple_query_no_directives(self):
        op = self._make_op()
        text = "SELECT ?x WHERE { ?x ?y ?z }"
        steps = op._parse_steps(text, "http://ep/sparql", {})
        assert len(steps) == 1
        assert steps[0][0] == "QUERY"
        assert steps[0][1] == "http://ep/sparql"

    def test_join_directive(self):
        op = self._make_op()
        text = "SELECT ?a WHERE { ?a ?b ?c }\n@@join ?a ?a type=left\nSELECT ?a ?d WHERE { ?a ?d ?e }"
        steps = op._parse_steps(text, "http://ep/sparql", {})
        assert len(steps) == 3
        assert steps[0][0] == "QUERY"
        assert steps[1] == ("JOIN", "?a", "?a", "left")
        assert steps[2][0] == "QUERY"

    def test_inner_join_default(self):
        op = self._make_op()
        text = "SELECT ?a WHERE { }\n@@join ?a ?b\nSELECT ?b WHERE { }"
        steps = op._parse_steps(text, "http://ep/sparql", {})
        assert steps[1] == ("JOIN", "?a", "?b", "inner")

    def test_endpoint_directive(self):
        op = self._make_op(allow_inline=True)
        text = "SELECT ?a WHERE { }\n@@join ?a ?a\n@@endpoint https://other.endpoint/sparql\nSELECT ?a ?b WHERE { }"
        steps = op._parse_steps(text, "http://ep/sparql", {})
        assert steps[2][0] == "QUERY"
        assert steps[2][1] == "https://other.endpoint/sparql"

    def test_endpoint_not_allowed_raises(self):
        op = self._make_op(allow_inline=False)
        text = "@@endpoint https://other/sparql\nSELECT ?a WHERE { }"
        try:
            op._parse_steps(text, "http://ep/sparql", {})
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "not allowed" in str(e)

    def test_values_inject(self):
        op = self._make_op()
        text = "SELECT ?a WHERE { }\n@@values ?a ?b\nSELECT ?a ?b WHERE { }"
        steps = op._parse_steps(text, "http://ep/sparql", {})
        assert steps[1] == ("VALUES_INJECT", ["?a", "?b"])

    def test_foreach_setup_and_mark(self):
        op = self._make_op()
        text = "SELECT ?br WHERE { }\n@@values ?br:myalias\n@@join ?br ?br type=left\n@@foreach myalias 0.5\nSELECT ?br ?count WHERE { }"
        steps = op._parse_steps(text, "http://ep/sparql", {})
        tags = [s[0] for s in steps]
        assert "FOREACH_SETUP" in tags
        assert "FOREACH_MARK" in tags
        setup = next(s for s in steps if s[0] == "FOREACH_SETUP")
        assert setup == ("FOREACH_SETUP", "myalias", "?br")
        mark = next(s for s in steps if s[0] == "FOREACH_MARK")
        assert mark == ("FOREACH_MARK", "myalias", 0.5)

    def test_remove_directive(self):
        op = self._make_op()
        text = "SELECT ?a ?b WHERE { }\n@@remove ?b"
        steps = op._parse_steps(text, "http://ep/sparql", {})
        assert steps[1] == ("REMOVE", ["?b"])

    def test_param_substitution(self):
        op = self._make_op()
        text = "SELECT ?a WHERE { VALUES ?a { [[id]] } }"
        steps = op._parse_steps(text, "http://ep/sparql", {"id": "hello"})
        assert "hello" in steps[0][2]
        assert "[[id]]" not in steps[0][2]

    def test_unknown_directive_raises(self):
        op = self._make_op()
        text = "@@bogus something"
        try:
            op._parse_steps(text, "http://ep/sparql", {})
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Unknown directive" in str(e)

    def test_with_directive_known_source(self):
        op = self._make_op(sources_map={"wikidata": "https://wikidata.org/sparql"})
        text = "@@with wikidata\nSELECT ?a WHERE { }"
        steps = op._parse_steps(text, "http://ep/sparql", {})
        assert steps[0][0] == "QUERY"
        assert steps[0][1] == "https://wikidata.org/sparql"

    def test_with_directive_unknown_source_raises(self):
        op = self._make_op(sources_map={})
        text = "@@with nonexistent\nSELECT ?a WHERE { }"
        try:
            op._parse_steps(text, "http://ep/sparql", {})
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Unknown source" in str(e)


class TestJoin:
    def _make_op(self):
        op_item = {
            "url": "/test/{id}", "id": "str(.+)",
            "sparql": "SELECT ?x WHERE { }", "method": "get",
            "field_type": "str(x)",
        }
        return Operation("/api/test/v", r"/api/test/(.+)", op_item,
                         "http://ep/sparql", "get", None)

    def test_inner_join(self):
        op = self._make_op()
        left = [{"doi": "10.1", "title": "Paper A"}, {"doi": "10.2", "title": "Paper B"}]
        right = [{"doi": "10.1", "count": "5"}]
        result = op._join(left, right, "?doi", "?doi", "inner")
        assert len(result) == 1
        assert result[0]["doi"] == "10.1"
        assert result[0]["count"] == "5"
        assert result[0]["title"] == "Paper A"

    def test_left_join(self):
        op = self._make_op()
        left = [{"doi": "10.1", "title": "A"}, {"doi": "10.2", "title": "B"}]
        right = [{"doi": "10.1", "extra": "x"}]
        result = op._join(left, right, "?doi", "?doi", "left")
        assert len(result) == 2
        matched = next(r for r in result if r["doi"] == "10.1")
        assert matched["extra"] == "x"
        unmatched = next(r for r in result if r["doi"] == "10.2")
        assert "extra" not in unmatched

    def test_join_normalizes_http_https(self):
        op = self._make_op()
        left = [{"br": "http://example.org/br/1", "doi": "10.1"}]
        right = [{"br": "https://example.org/br/1", "count": "3"}]
        result = op._join(left, right, "?br", "?br", "inner")
        assert len(result) == 1
        assert result[0]["count"] == "3"

    def test_join_normalizes_trailing_slash(self):
        op = self._make_op()
        left = [{"uri": "http://example.org/x/"}]
        right = [{"uri": "http://example.org/x", "val": "y"}]
        result = op._join(left, right, "?uri", "?uri", "inner")
        assert len(result) == 1

    def test_join_empty_right(self):
        op = self._make_op()
        left = [{"a": "1"}, {"a": "2"}]
        result = op._join(left, [], "?a", "?a", "left")
        assert len(result) == 2

    def test_join_empty_left(self):
        op = self._make_op()
        result = op._join([], [{"a": "1"}], "?a", "?a", "inner")
        assert len(result) == 0


class TestDropColumns:
    def test_removes_specified_columns(self):
        rows = [{"a": "1", "b": "2", "c": "3"}, {"a": "4", "b": "5", "c": "6"}]
        result = Operation._drop_columns(rows, ["?b", "?c"])
        assert result == [{"a": "1"}, {"a": "4"}]

    def test_empty_rows(self):
        assert Operation._drop_columns([], ["?a"]) == []


class TestInjectValuesClause:
    def _make_op(self):
        op_item = {
            "url": "/test/{id}", "id": "str(.+)",
            "sparql": "SELECT ?x WHERE { }", "method": "get",
            "field_type": "str(x)",
        }
        return Operation("/api/test/v", r"/api/test/(.+)", op_item,
                         "http://ep/sparql", "get", None)

    def test_injects_literal_values(self):
        op = self._make_op()
        acc = [{"doi": "10.1", "title": "A"}, {"doi": "10.2", "title": "B"}]
        query = "SELECT ?doi ?extra WHERE { ?s ?p ?o }"
        result = op._inject_values_clause(query, ["?doi"], acc)
        assert 'VALUES (?doi)' in result
        assert '"10.1"' in result
        assert '"10.2"' in result

    def test_injects_iri_values(self):
        op = self._make_op()
        acc = [{"br": "https://example.org/br/1"}, {"br": "https://example.org/br/2"}]
        query = "SELECT ?br WHERE { }"
        result = op._inject_values_clause(query, ["?br"], acc)
        assert "<https://example.org/br/1>" in result
        assert "<https://example.org/br/2>" in result

    def test_skips_empty_values(self):
        op = self._make_op()
        acc = [{"doi": "10.1"}, {"doi": ""}]
        query = "SELECT ?doi WHERE { }"
        result = op._inject_values_clause(query, ["?doi"], acc)
        assert '"10.1"' in result
        assert result.count("(") - result.count("VALUES") == 1

    def test_no_rows_returns_original(self):
        op = self._make_op()
        query = "SELECT ?x WHERE { }"
        result = op._inject_values_clause(query, ["?x"], [])
        assert result == query


class TestHeaderFromFieldType:
    def test_extracts_field_names_in_order(self):
        op_item = {"field_type": "str(doi) str(qid) int(count)"}
        result = Operation._header_from_field_type(op_item, [])
        assert result == ["doi", "qid", "count"]

    def test_fallback_to_dict_keys(self):
        op_item = {}
        acc = [{"a": "1", "b": "2"}]
        result = Operation._header_from_field_type(op_item, acc)
        assert result == ["a", "b"]

    def test_empty_acc_no_field_type(self):
        assert Operation._header_from_field_type({}, []) == []


class TestToCsvRows:
    def test_produces_header_plus_data(self):
        header = ["x", "y"]
        acc = [{"x": "1", "y": "2"}, {"x": "3", "y": "4"}]
        result = Operation._to_csv_rows(header, acc)
        assert result == [["x", "y"], ["1", "2"], ["3", "4"]]

    def test_missing_key_becomes_empty(self):
        header = ["a", "b"]
        acc = [{"a": "1"}]
        result = Operation._to_csv_rows(header, acc)
        assert result == [["a", "b"], ["1", ""]]


class TestRunSparqlDicts:
    def _make_op(self, method="get"):
        op_item = {
            "url": "/test/{id}", "id": "str(.+)",
            "sparql": "SELECT ?x WHERE { }", "method": "get",
            "field_type": "str(x)",
        }
        return Operation("/api/test/v", r"/api/test/(.+)", op_item,
                         "http://ep/sparql", method, None)

    @patch("ramose._http_session")
    def test_get_request(self, mock_session):
        resp = SimpleNamespace(
            status_code=200,
            content=b"doi,qid\n10.1,Q1\n10.2,Q2\n",
            reason="OK",
            encoding=None,
        )
        mock_session.get.return_value = resp

        op = self._make_op("get")
        rows = op._run_sparql_dicts("http://ep/sparql", "SELECT ?doi ?qid WHERE { }")
        assert len(rows) == 2
        assert rows[0]["doi"] == "10.1"
        assert rows[1]["qid"] == "Q2"

    @patch("ramose._http_session")
    def test_post_request(self, mock_session):
        resp = SimpleNamespace(
            status_code=200,
            content=b"x\nval\n",
            reason="OK",
            encoding=None,
        )
        mock_session.post.return_value = resp

        op = self._make_op("post")
        rows = op._run_sparql_dicts("http://ep/sparql", "SELECT ?x WHERE { }")
        assert len(rows) == 1
        assert rows[0]["x"] == "val"

    @patch("ramose._http_session")
    def test_non_200_raises(self, mock_session):
        resp = SimpleNamespace(
            status_code=500,
            content=b"error",
            reason="Internal Server Error",
            encoding=None,
        )
        mock_session.get.return_value = resp

        op = self._make_op("get")
        try:
            op._run_sparql_dicts("http://ep/sparql", "SELECT ?x WHERE { }")
            assert False, "Should have raised"
        except RuntimeError as e:
            assert "500" in str(e)

    @patch("ramose._http_session")
    def test_request_exception_raises(self, mock_session):
        from requests.exceptions import ConnectionError
        mock_session.get.side_effect = ConnectionError("refused")

        op = self._make_op("get")
        try:
            op._run_sparql_dicts("http://ep/sparql", "SELECT ?x WHERE { }")
            assert False, "Should have raised"
        except RuntimeError as e:
            assert "SPARQL request failed" in str(e)
