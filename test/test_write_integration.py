# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

from http import HTTPStatus
from json import loads
from pathlib import Path

import pytest

from ramose import APIManager, Operation
from ramose._constants import _backend_auth

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
DOI_SCHEME = "http://purl.org/spar/datacite/doi"

# The "OpenCitations Meta" journal article, already present in the test data.
META_PAPER_IRI = "https://w3id.org/oc/meta/br/062104388184"
META_PAPER_DOI = "10.1162/qss_a_00292"

# A fresh resource, absent from the test data, used for the write roundtrip.
NEW_RESOURCE_IRI = "https://w3id.org/oc/meta/br/0699999999"
NEW_IDENTIFIER_IRI = "https://w3id.org/oc/meta/id/0699999999"


def _resource_body(title: str, value: str) -> dict[str, object]:
    return {
        "resource": NEW_RESOURCE_IRI,
        "title": title,
        "identifier": NEW_IDENTIFIER_IRI,
        "scheme": DOI_SCHEME,
        "value": value,
    }


@pytest.fixture
def write_api_manager(qlever_endpoint: str) -> APIManager:
    return APIManager([str(FIXTURES_DIR / "write_api.hf")], endpoint_override=qlever_endpoint)


def _exec(
    api_manager: APIManager, url: str, method: str, body_params: dict[str, object] | None = None
) -> tuple[int, str]:
    operation = api_manager.get_op(url, method)
    assert isinstance(operation, Operation)
    status, body, _, _ = operation.exec(method=method, content_type="application/json", body_params=body_params)
    return status, body


def _read_resource(api_manager: APIManager, iri: str) -> list[dict[str, str]]:
    status, body = _exec(api_manager, f"/bibliography/v1/resources/{iri}", "get")
    assert status == HTTPStatus.OK
    return loads(body)


class TestWriteIntegration:
    def test_read_existing_meta_paper(self, write_api_manager: APIManager) -> None:
        assert _read_resource(write_api_manager, META_PAPER_IRI) == [
            {"title": "OpenCitations Meta", "scheme": DOI_SCHEME, "value": META_PAPER_DOI},
        ]

    def test_insert_read_delete_roundtrip(self, write_api_manager: APIManager) -> None:
        status, body = _exec(
            write_api_manager,
            "/bibliography/v1/resources",
            "post",
            _resource_body("A Newly Minted Article", "10.0000/new"),
        )
        assert status == HTTPStatus.OK
        assert loads(body) == {"status": 200, "message": "operation completed"}

        assert _read_resource(write_api_manager, NEW_RESOURCE_IRI) == [
            {"title": "A Newly Minted Article", "scheme": DOI_SCHEME, "value": "10.0000/new"},
        ]

        status, _ = _exec(write_api_manager, f"/bibliography/v1/resources/{NEW_RESOURCE_IRI}", "delete")
        assert status == HTTPStatus.OK

        assert _read_resource(write_api_manager, NEW_RESOURCE_IRI) == []

    def test_write_needs_backend_credential(self, qlever_secured_endpoint: tuple[str, str]) -> None:
        endpoint, access_token = qlever_secured_endpoint
        api_manager = APIManager([str(FIXTURES_DIR / "write_api.hf")], endpoint_override=endpoint)
        body = _resource_body("A Secured Article", "10.0000/secured")

        # QLever rejects an update with no access token; RAMOSE propagates its 500.
        status, _ = _exec(api_manager, "/bibliography/v1/resources", "post", body)
        assert status == HTTPStatus.INTERNAL_SERVER_ERROR

        _backend_auth[endpoint] = f"Bearer {access_token}"
        try:
            status, response_body = _exec(api_manager, "/bibliography/v1/resources", "post", body)
            assert status == HTTPStatus.OK
            assert loads(response_body) == {"status": 200, "message": "operation completed"}
        finally:
            _backend_auth.pop(endpoint, None)

    def test_literal_with_quote_roundtrips(self, write_api_manager: APIManager) -> None:
        title = 'A title with a "quoted" word'
        status, _ = _exec(
            write_api_manager,
            "/bibliography/v1/resources",
            "post",
            _resource_body(title, "10.0000/quote"),
        )
        assert status == HTTPStatus.OK
        assert _read_resource(write_api_manager, NEW_RESOURCE_IRI) == [
            {"title": title, "scheme": DOI_SCHEME, "value": "10.0000/quote"},
        ]
        _exec(write_api_manager, f"/bibliography/v1/resources/{NEW_RESOURCE_IRI}", "delete")
