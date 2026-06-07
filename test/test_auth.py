# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import yaml

from ramose import APIManager
from ramose.__main__ import _build_app, parse_backend_auth
from ramose.auth import TokenStore
from ramose.html_documentation import HTMLDocumentationHandler
from ramose.openapi_documentation import OpenAPIDocumentationHandler

if "pysparql_anything" not in sys.modules:
    _mock_module = ModuleType("pysparql_anything")
    _mock_module.SparqlAnything = MagicMock()  # type: ignore[attr-defined]
    sys.modules["pysparql_anything"] = _mock_module

if TYPE_CHECKING:
    from flask.testing import FlaskClient

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
RESOURCES_URL = "/bibliography/v1/resources"
RESOURCE_BODY = {
    "resource": "https://w3id.org/oc/meta/br/062104388184",
    "title": "OpenCitations Meta",
    "identifier": "https://w3id.org/oc/meta/id/062106312420",
    "scheme": "http://purl.org/spar/datacite/doi",
    "value": "10.1162/qss_a_00292",
}


class TestTokenStore:
    def test_create_and_validate(self, tmp_path: Path) -> None:
        store = TokenStore(str(tmp_path))
        token = store.create("demo")
        assert store.validate(token) is True

    def test_unknown_token_is_invalid(self, tmp_path: Path) -> None:
        store = TokenStore(str(tmp_path))
        store.create("demo")
        assert store.validate("not-a-real-token") is False

    def test_revoke_invalidates(self, tmp_path: Path) -> None:
        store = TokenStore(str(tmp_path))
        token = store.create("demo")
        assert store.revoke(token) is True
        assert store.validate(token) is False

    def test_revoke_unknown_returns_false(self, tmp_path: Path) -> None:
        store = TokenStore(str(tmp_path))
        assert store.revoke("nope") is False

    def test_expired_token_is_invalid(self, tmp_path: Path) -> None:
        store = TokenStore(str(tmp_path))
        token = store.create("demo", ttl=-1)
        assert store.validate(token) is False

    def test_unexpired_token_is_valid(self, tmp_path: Path) -> None:
        store = TokenStore(str(tmp_path))
        token = store.create("demo", ttl=3600)
        assert store.validate(token) is True

    def test_list_tokens(self, tmp_path: Path) -> None:
        store = TokenStore(str(tmp_path))
        store.create("first")
        store.create("second", ttl=3600)
        rows = store.list_tokens()
        assert [row[0] for row in rows] == ["first", "second"]
        assert [row[3] for row in rows] == [0, 0]

    def test_token_not_stored_in_plaintext(self, tmp_path: Path) -> None:
        store = TokenStore(str(tmp_path))
        token = store.create("demo")
        db_bytes = (tmp_path / "auth.db").read_bytes()
        assert token.encode("utf-8") not in db_bytes


class TestParseBackendAuth:
    def test_single_cli_entry(self) -> None:
        assert parse_backend_auth(["https://host/sparql=Bearer xyz"], None) == {"https://host/sparql": "Bearer xyz"}

    def test_env_and_cli_merge_with_cli_override(self) -> None:
        env = "https://host/sparql=Bearer env\nhttps://other/sparql=Basic abc"
        result = parse_backend_auth(["https://host/sparql=Bearer cli"], env)
        assert result == {"https://host/sparql": "Bearer cli", "https://other/sparql": "Basic abc"}

    def test_header_with_equals_is_preserved(self) -> None:
        assert parse_backend_auth(["https://host/sparql=Basic dXNlcjpwYXNz=="], None) == {
            "https://host/sparql": "Basic dXNlcjpwYXNz==",
        }

    def test_no_input_gives_empty_map(self) -> None:
        assert parse_backend_auth(None, None) == {}

    def test_entry_without_separator_raises(self) -> None:
        with pytest.raises(ValueError, match="expected 'endpoint=header'"):
            parse_backend_auth(["no-separator-here"], None)


class TestOpenAPISecurity:
    def _yaml(self) -> str:
        am = APIManager([str(FIXTURES_DIR / "write_api.hf")], endpoint_override="http://mock/sparql")
        _, yml = OpenAPIDocumentationHandler(am).get_documentation()
        return yml

    def test_security_scheme_declared(self) -> None:
        spec = yaml.safe_load(self._yaml())
        assert spec["components"]["securitySchemes"]["bearerAuth"] == {"type": "http", "scheme": "bearer"}

    def test_protected_post_has_security_and_401(self) -> None:
        post_op = yaml.safe_load(self._yaml())["paths"]["/resources"]["post"]
        assert post_op["security"] == [{"bearerAuth": []}]
        assert "401" in post_op["responses"]

    def test_protected_post_has_request_body(self) -> None:
        post_op = yaml.safe_load(self._yaml())["paths"]["/resources"]["post"]
        properties = post_op["requestBody"]["content"]["application/json"]["schema"]["properties"]
        assert set(properties) == {"resource", "title", "identifier", "scheme", "value"}

    def test_open_get_has_no_security(self) -> None:
        get_op = yaml.safe_load(self._yaml())["paths"]["/resources/{resource}"]["get"]
        assert "security" not in get_op
        assert "401" not in get_op["responses"]


class TestWebEnforcement:
    def _client_and_token(self, tmp_path: Path) -> tuple[FlaskClient, str]:
        store = TokenStore(str(tmp_path))
        token = store.create("demo")
        api_manager = APIManager([str(FIXTURES_DIR / "write_api.hf")], endpoint_override="http://mock/sparql")
        app = _build_app(
            api_manager,
            HTMLDocumentationHandler(api_manager),
            OpenAPIDocumentationHandler(api_manager),
            None,
            store,
        )
        return app.test_client(), token

    def test_post_without_token_is_401(self, tmp_path: Path) -> None:
        client, _ = self._client_and_token(tmp_path)
        response = client.post(RESOURCES_URL, json=RESOURCE_BODY)
        assert response.status_code == 401

    def test_post_with_invalid_token_is_401(self, tmp_path: Path) -> None:
        client, _ = self._client_and_token(tmp_path)
        response = client.post(RESOURCES_URL, json=RESOURCE_BODY, headers={"Authorization": "Bearer wrong"})
        assert response.status_code == 401

    def test_post_with_valid_token_succeeds(self, tmp_path: Path) -> None:
        client, token = self._client_and_token(tmp_path)
        update_response = SimpleNamespace(status_code=200, reason="OK", text="", encoding=None)
        with patch("ramose.operation._http_session") as mock_session:
            mock_session.post.return_value = update_response
            response = client.post(RESOURCES_URL, json=RESOURCE_BODY, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200

    def test_post_reads_params_from_query_string(self, tmp_path: Path) -> None:
        client, token = self._client_and_token(tmp_path)
        update_response = SimpleNamespace(status_code=200, reason="OK", text="", encoding=None)
        with patch("ramose.operation._http_session") as mock_session:
            mock_session.post.return_value = update_response
            response = client.post(
                RESOURCES_URL,
                query_string=RESOURCE_BODY,
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200
        update_text = mock_session.post.call_args.kwargs["data"]["update"]
        assert f"<{RESOURCE_BODY['resource']}>" in update_text
        assert f'"{RESOURCE_BODY["title"]}"' in update_text

    def test_open_get_needs_no_token(self, tmp_path: Path) -> None:
        client, _ = self._client_and_token(tmp_path)
        read_response = SimpleNamespace(status_code=200, reason="OK", text="title,scheme,value\nA,B,C\n", encoding=None)
        with patch("ramose.operation._http_session") as mock_session:
            mock_session.get.return_value = read_response
            response = client.get(f"{RESOURCES_URL}/https://w3id.org/oc/meta/br/062104388184")
        assert response.status_code == 200

    def test_revoked_token_is_rejected(self, tmp_path: Path) -> None:
        store = TokenStore(str(tmp_path))
        token = store.create("demo")
        store.revoke(token)
        api_manager = APIManager([str(FIXTURES_DIR / "write_api.hf")], endpoint_override="http://mock/sparql")
        app = _build_app(
            api_manager,
            HTMLDocumentationHandler(api_manager),
            OpenAPIDocumentationHandler(api_manager),
            None,
            store,
        )
        response = app.test_client().post(
            RESOURCES_URL,
            json=RESOURCE_BODY,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
