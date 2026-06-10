# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from ramose import APIManager, Operation

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def api_mgr() -> APIManager:
    conf_file = "test/data/meta_v1.hf"
    return APIManager([conf_file], endpoint_override="http://localhost:9999/sparql")


class TestLoadAddon:
    def test_relative_path_with_parent_directory(self, tmp_path: Path) -> None:
        addon_dir = tmp_path / "src"
        addon_dir.mkdir()
        (addon_dir / "relative_path_addon.py").write_text("VALUE = 42\n")
        conf_dir = tmp_path / "conf"
        conf_dir.mkdir()
        conf_file = conf_dir / "spec.hf"
        conf_file.write_text("")
        module = APIManager._load_addon("../src/relative_path_addon", str(conf_file))
        assert module.VALUE == 42

    def test_dotted_name_resolved_as_package_import(self) -> None:
        module = APIManager._load_addon("ramose.skgif_addon", "test/data/meta_v1.hf")
        assert module.__name__ == "ramose.skgif_addon"


class TestNorApiUrl:
    def test_with_typed_param(self) -> None:
        item = {"url": "/metadata/{id}", "id": "str(.+)"}
        result = APIManager.nor_api_url(item, "/v1")
        assert result == "/v1/metadata/(.+)"

    def test_without_param_type_falls_back(self) -> None:
        item = {"url": "/metadata/{id}"}
        result = APIManager.nor_api_url(item, "/v1")
        assert result == "/v1/metadata/(.+)"

    def test_no_base_url(self) -> None:
        item = {"url": "/metadata/{id}", "id": "str([0-9]+)"}
        result = APIManager.nor_api_url(item)
        assert result == "/metadata/([0-9]+)"


class TestBestMatch:
    def test_valid_url(self, api_mgr: APIManager) -> None:
        conf, pat, op_item = api_mgr.best_match(api_mgr.base_url[0] + "/metadata/doi:10.1234")
        assert pat == (
            "/v1/metadata/"
            "((doi|issn|isbn|omid|openalex|pmid|pmcid):.+?"
            "(__(doi|issn|isbn|omid|openalex|pmid|pmcid):.+?)*$)"
        )
        assert op_item is not None
        assert "get" in op_item["method"].split()
        assert conf is not None
        assert set(conf) == {
            "conf",
            "tp",
            "update_endpoint",
            "conf_json",
            "base_url",
            "website",
            "addon",
            "sparql_http_method",
            "sources_map",
            "engine",
            "disable_params",
            "auth_required",
        }

    def test_invalid_url(self, api_mgr: APIManager) -> None:
        conf, pat, op_item = api_mgr.best_match("/nonexistent/path")
        assert conf is None
        assert pat is None
        assert op_item is None


class TestGetOp:
    def test_valid_operation(self, api_mgr: APIManager) -> None:
        op = api_mgr.get_op(api_mgr.base_url[0] + "/metadata/doi:10.1234")
        assert isinstance(op, Operation)

    def test_invalid_operation_returns_404(self, api_mgr: APIManager) -> None:
        result = api_mgr.get_op("/nonexistent/operation")
        assert result == (404, "HTTP status code 404: the operation requested does not exist", "text/plain")


class TestGetOpInvalidParam:
    def test_invalid_param_value_returns_400(self, api_mgr: APIManager) -> None:
        result = api_mgr.get_op(api_mgr.base_url[0] + "/author/orcid:10.1162/qss_a_00292")
        assert result == (
            400,
            "HTTP status code 400: the value 'orcid:10.1162/qss_a_00292' is not valid for parameter 'id'"
            " in operation '/v1/author/{id}'. Example: /v1/author/orcid:0000-0002-8420-0696",
            "text/plain",
        )

    def test_empty_param_returns_400(self, api_mgr: APIManager) -> None:
        result = api_mgr.get_op(api_mgr.base_url[0] + "/author/")
        assert result == (
            400,
            "HTTP status code 400: the operation '/v1/author/{id}' requires a value for parameter 'id'"
            ". Example: /v1/author/orcid:0000-0002-8420-0696",
            "text/plain",
        )

    def test_nonexistent_operation_still_404(self, api_mgr: APIManager) -> None:
        result = api_mgr.get_op(api_mgr.base_url[0] + "/nonexistent/something")
        assert result == (404, "HTTP status code 404: the operation requested does not exist", "text/plain")


class TestSourcesParsing:
    def test_sources_map_populated(self) -> None:
        am = APIManager(
            ["test/fixtures/test_with_sources.hf"],
            endpoint_override="http://localhost:9999/sparql",
        )
        base = am.base_url[0]
        sources = am.all_conf[base]["sources_map"]
        assert sources["oc_meta"] == "https://sparql.opencitations.net/meta"
        assert sources["oc_index"] == "https://sparql.opencitations.net/index"

    def test_empty_sources_pairs_skipped(self) -> None:
        am = APIManager(
            ["test/fixtures/test_with_sources.hf"],
            endpoint_override="http://localhost:9999/sparql",
        )
        base = am.base_url[0]
        sources = am.all_conf[base]["sources_map"]
        assert "" not in sources


class TestPerOperationEngine:
    def test_operation_level_engine_override(self) -> None:
        am = APIManager(
            ["test/fixtures/test_with_sources.hf"],
            endpoint_override="http://localhost:9999/sparql",
        )
        op = am.get_op("/api/v2/data/test")
        assert isinstance(op, Operation)
        assert op.engine == "sparql"

    def test_api_level_engine(self) -> None:
        am = APIManager(
            ["test/fixtures/mixed_scholarly_crossref.hf"],
            endpoint_override="http://localhost:9999/sparql",
        )
        base = am.base_url[0]
        assert am.all_conf[base]["engine"] == "sparql"


class TestFormatParsingEmptyPart:
    def test_trailing_semicolon_ignored(self) -> None:
        am = APIManager(
            ["test/fixtures/test_openapi_edge.hf"],
            endpoint_override="http://localhost:9999/sparql",
        )
        op = am.get_op("/edge/lookup/wikidata/Q42")
        assert isinstance(op, Operation)
        assert "" not in op.format
        assert "xml" in op.format
