# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from ramose import APIManager, Operation, OperationConfig
from ramose.__main__ import _build_app
from ramose.auth import TokenStore
from ramose.html_documentation import HTMLDocumentationHandler
from ramose.openapi_documentation import OpenAPIDocumentationHandler

if "pysparql_anything" not in sys.modules:
    _mock_module = ModuleType("pysparql_anything")
    _mock_module.SparqlAnything = MagicMock()  # type: ignore[attr-defined]
    sys.modules["pysparql_anything"] = _mock_module

if TYPE_CHECKING:
    from flask.testing import FlaskClient

TESTS_DIR = str(Path(__file__).resolve().parent / "fixtures")

SCHOLARLY_CSV = (
    "qid,author,year,title,source_title,source_id,volume,issue,page,doi,reference,citation_count\n"
    "Q24260641,,2015,Setting our bibliographic references free,,,,,,10.1108/JD-12-2013-0166,,1\n"
)

OP_URL = "/api/v1/metadata/10.1108/jd-12-2013-0166"


class TestMediaTypeToFormat:
    def _op(self, op_item: dict[str, str], config: OperationConfig | None = None) -> Operation:
        return Operation("/api/test/hello", r"/api/test/(.+)", op_item, config or OperationConfig())

    def test_custom_format_without_media_type_excluded(self) -> None:
        op = self._op({"default_format": "json"}, OperationConfig(format_map={"xml": "to_xml"}))
        assert op.media_type_to_format() == {"application/json": "json", "text/csv": "csv"}
        assert next(iter(op.media_type_to_format())) == "application/json"

    def test_no_default_format_leads_with_json(self) -> None:
        op = self._op({})
        assert op.media_type_to_format() == {"application/json": "json", "text/csv": "csv"}
        assert next(iter(op.media_type_to_format())) == "application/json"

    def test_declared_media_type_leads_when_default(self) -> None:
        op = self._op(
            {"default_format": "skg_if"},
            OperationConfig(format_map={"skg_if": "to_skg_if"}, format_media_types={"skg_if": "application/ld+json"}),
        )
        assert op.media_type_to_format() == {
            "application/ld+json": "skg_if",
            "application/json": "json",
            "text/csv": "csv",
        }
        assert next(iter(op.media_type_to_format())) == "application/ld+json"

    def test_format_disabled_returns_empty(self) -> None:
        op = self._op({"default_format": "json"}, OperationConfig(disabled_params={"format"}))
        assert op.media_type_to_format() == {}


class TestContentNegotiationWeb:
    def _client(self, tmp_path: Path) -> FlaskClient:
        api_manager = APIManager(
            [str(Path(TESTS_DIR) / "test_scholarly.hf")],
            endpoint_override="http://mock/sparql",
        )
        app = _build_app(
            api_manager,
            HTMLDocumentationHandler(api_manager),
            OpenAPIDocumentationHandler(api_manager),
            None,
            TokenStore(str(tmp_path)),
        )
        return app.test_client()

    def _get(self, tmp_path: Path, path: str, headers: dict[str, str]) -> tuple[int, str, str]:
        sparql_response = SimpleNamespace(status_code=200, text=SCHOLARLY_CSV, reason="OK", encoding=None)
        with patch("ramose.operation._http_session") as mock_session:
            mock_session.post.return_value = sparql_response
            response = self._client(tmp_path).get(path, headers=headers)
        return response.status_code, response.headers["Content-Type"], response.get_data(as_text=True)

    def test_accept_csv(self, tmp_path: Path) -> None:
        status, content_type, body = self._get(tmp_path, OP_URL, {"Accept": "text/csv"})
        assert status == 200
        assert content_type == "text/csv"
        assert body == SCHOLARLY_CSV.replace("\n", "\r\n")

    def test_accept_json(self, tmp_path: Path) -> None:
        status, content_type, body = self._get(tmp_path, OP_URL, {"Accept": "application/json"})
        assert status == 200
        assert content_type == "application/json"
        assert body.lstrip().startswith("[")

    def test_custom_format_without_media_type_not_negotiated(self, tmp_path: Path) -> None:
        status, content_type, body = self._get(tmp_path, OP_URL, {"Accept": "application/xml"})
        assert status == 200
        assert content_type == "application/json"
        assert body.lstrip().startswith("[")

    def test_query_format_wins_over_accept(self, tmp_path: Path) -> None:
        status, content_type, body = self._get(tmp_path, f"{OP_URL}?format=json", {"Accept": "text/csv"})
        assert status == 200
        assert content_type == "application/json"
        assert body.lstrip().startswith("[")

    def test_accept_wildcard_uses_default(self, tmp_path: Path) -> None:
        status, content_type, body = self._get(tmp_path, OP_URL, {"Accept": "*/*"})
        assert status == 200
        assert content_type == "application/json"
        assert body.lstrip().startswith("[")

    def test_unsupported_accept_uses_default(self, tmp_path: Path) -> None:
        status, content_type, body = self._get(tmp_path, OP_URL, {"Accept": "text/html"})
        assert status == 200
        assert content_type == "application/json"
        assert body.lstrip().startswith("[")
