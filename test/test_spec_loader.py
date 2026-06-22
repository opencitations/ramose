# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
import yaml

from ramose import (
    APIManager,
    HTMLDocumentationHandler,
    OpenAPIDocumentationHandler,
    Operation,
    YAMLSpecHandler,
    read_spec_file,
)

if TYPE_CHECKING:
    from pathlib import Path


HF_SPEC = """#url /api
#type api
#base http://localhost:5000
#endpoint http://localhost:9999/sparql
#method get
#title YAML mirror API
#description API defined in two formats.
#version 0.0.1
#license ISC
#contacts test@example.org

#url /items/{id}
#type operation
#id str([A-Z]+)
#method get
#description Returns one item.
#call /items/ABC
#field_type str(id) str(title)
#output_json [
  {"id": "ABC", "title": "Example"}
]
#sparql SELECT ?id ?title WHERE {
  BIND("[[id]]" AS ?id)
  BIND("Example" AS ?title)
}
"""

YAML_SPEC = """- url: /api
  type: api
  base: http://localhost:5000
  endpoint: http://localhost:9999/sparql
  method: get
  title: YAML mirror API
  description: API defined in two formats.
  version: "0.0.1"
  license: ISC
  contacts: test@example.org

- url: /items/{id}
  type: operation
  id: 'str([A-Z]+)'
  method: get
  description: Returns one item.
  call: /items/ABC
  field_type: str(id) str(title)
  output_json: |
    [
      {"id": "ABC", "title": "Example"}
    ]
  sparql: |
    SELECT ?id ?title WHERE {
      BIND("[[id]]" AS ?id)
      BIND("Example" AS ?title)
    }
"""

EXPECTED_SPEC = [
    {
        "url": "/api",
        "type": "api",
        "base": "http://localhost:5000",
        "endpoint": "http://localhost:9999/sparql",
        "method": "get",
        "title": "YAML mirror API",
        "description": "API defined in two formats.",
        "version": "0.0.1",
        "license": "ISC",
        "contacts": "test@example.org",
    },
    {
        "url": "/items/{id}",
        "type": "operation",
        "id": "str([A-Z]+)",
        "method": "get",
        "description": "Returns one item.",
        "call": "/items/ABC",
        "field_type": "str(id) str(title)",
        "output_json": '[\n  {"id": "ABC", "title": "Example"}\n]',
        "sparql": 'SELECT ?id ?title WHERE {\n  BIND("[[id]]" AS ?id)\n  BIND("Example" AS ?title)\n}',
    },
]


def write_spec_pair(tmp_path: Path) -> tuple[Path, Path]:
    hf_path = tmp_path / "spec.hf"
    yaml_path = tmp_path / "spec.yaml"
    hf_path.write_text(HF_SPEC, encoding="utf-8")
    yaml_path.write_text(YAML_SPEC, encoding="utf-8")
    return hf_path, yaml_path


def test_yaml_loader_reads_mirror_spec(tmp_path: Path) -> None:
    yaml_path = tmp_path / "spec.yaml"
    yaml_path.write_text(YAML_SPEC, encoding="utf-8")

    assert YAMLSpecHandler().read(str(yaml_path)) == EXPECTED_SPEC


def test_spec_loader_keeps_hf_and_yaml_equal(tmp_path: Path) -> None:
    hf_path, yaml_path = write_spec_pair(tmp_path)

    assert read_spec_file(str(hf_path)) == EXPECTED_SPEC
    assert read_spec_file(str(yaml_path)) == EXPECTED_SPEC


def test_yaml_loader_returns_empty_list_for_empty_file(tmp_path: Path) -> None:
    yaml_path = tmp_path / "empty.yaml"
    yaml_path.write_text("", encoding="utf-8")

    assert YAMLSpecHandler().read(str(yaml_path)) == []


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("url: /api\n", "YAML spec must be a list of sections"),
        ("- plain\n", "YAML spec section 1 must be a mapping"),
        ("- 1: value\n", "YAML spec section 1 has a non-string key: 1"),
        ("- version: 1.0\n", "YAML spec field 'version' in section 1 must be a string"),
    ],
)
def test_yaml_loader_rejects_non_mirror_shapes(tmp_path: Path, content: str, message: str) -> None:
    yaml_path = tmp_path / "invalid.yaml"
    yaml_path.write_text(content, encoding="utf-8")

    with pytest.raises(TypeError, match=f"^{re.escape(message)}$") as exc_info:
        YAMLSpecHandler().read(str(yaml_path))

    assert str(exc_info.value) == message


def test_api_manager_loads_yaml_like_hf(tmp_path: Path) -> None:
    hf_path, yaml_path = write_spec_pair(tmp_path)
    hf_manager = APIManager([str(hf_path)], endpoint_override="http://mock/sparql")
    yaml_manager = APIManager([str(yaml_path)], endpoint_override="http://mock/sparql")

    assert yaml_manager.all_conf["/api"]["conf_json"] == hf_manager.all_conf["/api"]["conf_json"]
    assert yaml_manager.all_conf["/api"]["conf_json"] == EXPECTED_SPEC

    hf_conf, hf_pattern, hf_item = hf_manager.best_match("/api/items/ABC")
    yaml_conf, yaml_pattern, yaml_item = yaml_manager.best_match("/api/items/ABC")

    assert hf_conf is not None
    assert yaml_conf is not None
    assert hf_pattern == "/api/items/([A-Z]+)"
    assert yaml_pattern == "/api/items/([A-Z]+)"
    assert hf_item == EXPECTED_SPEC[1]
    assert yaml_item == EXPECTED_SPEC[1]

    operation = yaml_manager.get_op("/api/items/ABC")
    assert isinstance(operation, Operation)
    assert operation.i == EXPECTED_SPEC[1]


def test_yaml_and_hf_generate_same_documentation(tmp_path: Path) -> None:
    hf_path, yaml_path = write_spec_pair(tmp_path)
    hf_manager = APIManager([str(hf_path)], endpoint_override="http://mock/sparql")
    yaml_manager = APIManager([str(yaml_path)], endpoint_override="http://mock/sparql")

    hf_html_status, hf_html = HTMLDocumentationHandler(hf_manager).get_documentation()
    yaml_html_status, yaml_html = HTMLDocumentationHandler(yaml_manager).get_documentation()
    hf_openapi_status, hf_openapi = OpenAPIDocumentationHandler(hf_manager).get_documentation()
    yaml_openapi_status, yaml_openapi = OpenAPIDocumentationHandler(yaml_manager).get_documentation()

    assert yaml_html_status == 200
    assert hf_html_status == 200
    assert yaml_html == hf_html
    assert yaml_openapi_status == 200
    assert hf_openapi_status == 200
    assert yaml.safe_load(yaml_openapi) == yaml.safe_load(hf_openapi)


def test_yaml_spec_resolves_relative_custom_param_config(tmp_path: Path) -> None:
    (tmp_path / "filters.yaml").write_text(
        "identifiers.id:\n  slot: '?x <http://example.org/id> \"{{value}}\" .'\n",
        encoding="utf-8",
    )
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        """- url: /api
  type: api
  base: http://localhost:5000
  endpoint: http://localhost:9999/sparql
  title: YAML custom param API
  description: API with config-driven params.
  version: "0.0.1"
  license: ISC
  contacts: test@example.org

- url: /items/{id}
  type: operation
  id: 'str([A-Z]+)'
  method: get
  description: Operation with one config-driven param.
  call: /items/ABC
  field_type: str(x)
  custom_params: filter,filters.yaml,Search filter.
  sparql: |
    SELECT ?x WHERE {
      BIND("[[id]]" AS ?x)
      [[slot]]
    }
""",
        encoding="utf-8",
    )

    manager = APIManager([str(spec)], endpoint_override="http://mock/sparql")
    operation = manager.get_op("/api/items/ABC")

    assert isinstance(operation, Operation)
    assert operation.custom_param_configs == {
        "filter": {"identifiers.id": {"slot": '?x <http://example.org/id> "{{value}}" .'}},
    }
