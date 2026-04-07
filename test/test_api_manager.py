# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import pytest

from ramose import APIManager, Operation


@pytest.fixture
def api_mgr():
    conf_file = "test/data/meta_v1.hf"
    return APIManager([conf_file], endpoint_override="http://localhost:9999/sparql")


class TestNorApiUrl:
    def test_with_typed_param(self):
        item = {"url": "/metadata/{id}", "id": "str(.+)"}
        result = APIManager.nor_api_url(item, "/v1")
        assert result == "/v1/metadata/(.+)"

    def test_without_param_type_falls_back(self):
        item = {"url": "/metadata/{id}"}
        result = APIManager.nor_api_url(item, "/v1")
        assert result == "/v1/metadata/(.+)"

    def test_no_base_url(self):
        item = {"url": "/metadata/{id}", "id": "str([0-9]+)"}
        result = APIManager.nor_api_url(item)
        assert result == "/metadata/([0-9]+)"


class TestBestMatch:
    def test_valid_url(self, api_mgr):
        conf, pat = api_mgr.best_match(api_mgr.base_url[0] + "/metadata/doi:10.1234")
        assert (
            pat
            == "/v1/metadata/((doi|issn|isbn|omid|openalex|pmid|pmcid):.+?(__(doi|issn|isbn|omid|openalex|pmid|pmcid):.+?)*$)"
        )
        assert set(conf) == {
            "conf",
            "tp",
            "conf_json",
            "base_url",
            "website",
            "addon",
            "sparql_http_method",
            "sources_map",
            "engine",
        }

    def test_invalid_url(self, api_mgr):
        conf, pat = api_mgr.best_match("/nonexistent/path")
        assert conf is None
        assert pat is None


class TestGetOp:
    def test_valid_operation(self, api_mgr):
        op = api_mgr.get_op(api_mgr.base_url[0] + "/metadata/doi:10.1234")
        assert isinstance(op, Operation)

    def test_invalid_operation_returns_404(self, api_mgr):
        result = api_mgr.get_op("/nonexistent/operation")
        assert result == (404, "HTTP status code 404: the operation requested does not exist", "text/plain")


class TestSourcesParsing:
    def test_sources_map_populated(self):
        am = APIManager(
            ["tests/test_with_sources.hf"],
            endpoint_override="http://localhost:9999/sparql",
        )
        base = am.base_url[0]
        sources = am.all_conf[base]["sources_map"]
        assert sources["oc_meta"] == "https://sparql.opencitations.net/meta"
        assert sources["oc_index"] == "https://sparql.opencitations.net/index"

    def test_empty_sources_pairs_skipped(self):
        am = APIManager(
            ["tests/test_with_sources.hf"],
            endpoint_override="http://localhost:9999/sparql",
        )
        base = am.base_url[0]
        sources = am.all_conf[base]["sources_map"]
        assert "" not in sources


class TestPerOperationEngine:
    def test_operation_level_engine_override(self):
        am = APIManager(
            ["tests/test_with_sources.hf"],
            endpoint_override="http://localhost:9999/sparql",
        )
        op = am.get_op("/api/v2/data/test")
        assert isinstance(op, Operation)
        assert op.engine == "sparql"

    def test_api_level_engine(self):
        am = APIManager(
            ["tests/mixed_scholarly_crossref.hf"],
            endpoint_override="http://localhost:9999/sparql",
        )
        base = am.base_url[0]
        assert am.all_conf[base]["engine"] == "sparql"


class TestFormatParsingEmptyPart:
    def test_trailing_semicolon_ignored(self):
        am = APIManager(
            ["tests/test_openapi_edge.hf"],
            endpoint_override="http://localhost:9999/sparql",
        )
        op = am.get_op("/edge/lookup/wikidata/Q42")
        assert isinstance(op, Operation)
        assert "" not in op.format
        assert "xml" in op.format
