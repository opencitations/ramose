# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from ramose import APIManager, Operation
from ramose.hash_format import parse_custom_params

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
        module = APIManager._load_addon("ramose.skg_if", "test/data/meta_v1.hf")
        assert module.__name__ == "ramose.skg_if"


class TestApiBaseValidation:
    @pytest.mark.parametrize("base", ["/relative/base", "example.org/base"])
    def test_base_must_be_absolute_url(self, tmp_path: Path, base: str) -> None:
        spec = tmp_path / "spec.hf"
        spec.write_text(
            f"#url /api\n#type api\n#base {base}\n#endpoint http://localhost:9999/sparql\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match=r"^API #base must be an absolute URL$") as exc_info:
            APIManager([str(spec)])
        assert str(exc_info.value) == "API #base must be an absolute URL"


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
            "disable_params",
            "auth_required",
            "conf_file",
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


class TestRetryConfig:
    def test_default_retry_config(self, api_mgr: APIManager) -> None:
        op = api_mgr.get_op(api_mgr.base_url[0] + "/metadata/doi:10.1234")
        assert isinstance(op, Operation)
        assert (op.retry_attempts, op.retry_wait, op.retry_backoff) == (3, 0.5, 2.0)

    def test_api_manager_retry_config_override(self) -> None:
        am = APIManager(
            ["test/data/meta_v1.hf"],
            endpoint_override="http://localhost:9999/sparql",
            retry_attempts=5,
            retry_wait=0.25,
            retry_backoff=1.5,
        )
        op = am.get_op(am.base_url[0] + "/metadata/doi:10.1234")
        assert isinstance(op, Operation)
        assert (op.retry_attempts, op.retry_wait, op.retry_backoff) == (5, 0.25, 1.5)

    @pytest.mark.parametrize("suffix", [".hf", ".yaml"])
    def test_operation_retry_config_override(self, tmp_path: Path, suffix: str) -> None:
        spec = tmp_path / f"spec{suffix}"
        if suffix == ".hf":
            spec.write_text(
                "#url /api\n"
                "#type api\n"
                "#base http://localhost:5000\n"
                "#endpoint http://localhost:9999/sparql\n"
                "#title Retry config API\n"
                "#description Retry config API.\n"
                "#version 0.0.1\n"
                "\n"
                "#url /items/{id}\n"
                "#type operation\n"
                "#id str(.+)\n"
                "#method get\n"
                "#description Retry config operation.\n"
                "#field_type str(id)\n"
                "#retry_attempts 4\n"
                "#retry_wait 0.1\n"
                "#retry_backoff 3.0\n"
                '#sparql SELECT ?id WHERE { BIND("[[id]]" AS ?id) }\n',
                encoding="utf-8",
            )
        else:
            spec.write_text(
                """- url: /api
  type: api
  base: http://localhost:5000
  endpoint: http://localhost:9999/sparql
  title: Retry config API
  description: Retry config API.
  version: "0.0.1"

- url: /items/{id}
  type: operation
  id: 'str(.+)'
  method: get
  description: Retry config operation.
  field_type: str(id)
  retry_attempts: "4"
  retry_wait: "0.1"
  retry_backoff: "3.0"
  sparql: |
    SELECT ?id WHERE { BIND("[[id]]" AS ?id) }
""",
                encoding="utf-8",
            )

        am = APIManager([str(spec)], retry_attempts=7, retry_wait=0.7, retry_backoff=1.7)
        op = am.get_op("/api/items/ABC")
        assert isinstance(op, Operation)
        assert (op.retry_attempts, op.retry_wait, op.retry_backoff) == (4, 0.1, 3.0)


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


class TestParseCustomParams:
    def test_yaml_handler_phase_is_implicit(self) -> None:
        result = parse_custom_params("filter,filters.yaml,Search filter")
        assert result == {
            "filter": {
                "handler": "filters.yaml",
                "phase": "preprocess",
                "description": "Search filter",
            }
        }

    def test_yaml_handler_description_can_contain_commas(self) -> None:
        result = parse_custom_params("filter,filters.yml,Search filter, with commas")
        assert result == {
            "filter": {
                "handler": "filters.yml",
                "phase": "preprocess",
                "description": "Search filter, with commas",
            }
        }

    def test_yaml_handler_accepts_explicit_preprocess(self) -> None:
        result = parse_custom_params("filter,filters.yaml,preprocess,Search filter")
        assert result == {
            "filter": {
                "handler": "filters.yaml",
                "phase": "preprocess",
                "description": "Search filter",
            }
        }

    def test_yaml_handler_rejects_postprocess(self) -> None:
        with pytest.raises(
            ValueError,
            match=r"YAML custom parameter handler 'filters\.yaml' cannot be used for postprocess",
        ):
            parse_custom_params("filter,filters.yaml,postprocess,Search filter")

    def test_python_handler_keeps_explicit_phase(self) -> None:
        result = parse_custom_params("limit,handle_limit,postprocess,Limit results")
        assert result == {
            "limit": {
                "handler": "handle_limit",
                "phase": "postprocess",
                "description": "Limit results",
            }
        }


class TestCustomParamConfigs:
    def test_each_param_binds_to_its_own_config(self, tmp_path: Path) -> None:
        (tmp_path / "a.yaml").write_text("identifiers.id:\n  slot_a: '?x ex:a \"{{value}}\" .'\n", encoding="utf-8")
        (tmp_path / "b.yaml").write_text("cf.cites:\n  slot_b: '?x ex:b <{{value}}> .'\n", encoding="utf-8")
        spec = tmp_path / "spec.hf"
        spec.write_text(
            "#url /api/v2\n"
            "#type api\n"
            "#base http://localhost:5000\n"
            "#endpoint http://localhost:9999/sparql\n"
            "#title Two config-driven params\n"
            "#version 0.0.1\n"
            "\n"
            "#url /data/{id}\n"
            "#type operation\n"
            "#id str(.+)\n"
            "#method get\n"
            "#description Operation with two config-driven params\n"
            "#field_type str(x)\n"
            "#custom_params filter,a.yaml,A;extra,b.yaml,preprocess,B\n"
            '#sparql SELECT ?x WHERE { BIND("test" AS ?x) [[slot_a]] [[slot_b]] }\n',
            encoding="utf-8",
        )
        am = APIManager([str(spec)], endpoint_override="http://localhost:9999/sparql")
        op = am.get_op("/api/v2/data/123")
        assert isinstance(op, Operation)
        assert op.custom_params == {
            "filter": {"handler": "a.yaml", "phase": "preprocess", "description": "A"},
            "extra": {"handler": "b.yaml", "phase": "preprocess", "description": "B"},
        }
        assert op.custom_param_configs == {
            "filter": {"identifiers.id": {"slot_a": '?x ex:a "{{value}}" .'}},
            "extra": {"cf.cites": {"slot_b": "?x ex:b <{{value}}> ."}},
        }
