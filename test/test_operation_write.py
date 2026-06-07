# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

from json import dumps
from types import SimpleNamespace
from unittest.mock import patch

from ramose import Operation, OperationConfig

DCTERMS_TITLE = "<http://purl.org/dc/terms/title>"
RESOURCE_IRI = "https://w3id.org/oc/meta/br/062104388184"
SUCCESS_BODY = dumps({"status": 200, "message": "operation completed"})


def _mock_response(status_code: int = 200, reason: str = "OK") -> SimpleNamespace:
    return SimpleNamespace(status_code=status_code, reason=reason, text="", encoding=None)


def _make_write_op(
    method: str = "post",
    sparql: str = f'INSERT DATA {{ <[[resource]]> {DCTERMS_TITLE} "[[title]]" . }}',
    config: OperationConfig | None = None,
) -> Operation:
    op_item = {
        "url": "/resources",
        "method": method,
        "sparql": sparql,
        "resource": "iri(.+)",
        "title": "literal(.+)",
    }
    if config is None:
        config = OperationConfig(sparql_endpoint="http://localhost/sparql")
    return Operation("/bibliography/v1/resources", r"/bibliography/v1/resources", op_item, config)


class TestWriteRequest:
    @patch("ramose.operation._http_session")
    def test_post_sends_update_form_param(self, mock_session: object) -> None:
        mock_session.post.return_value = _mock_response()  # type: ignore[attr-defined]
        op = _make_write_op()
        status, body, content_type, _ = op.exec(
            method="post",
            content_type="application/json",
            body_params={"resource": RESOURCE_IRI, "title": "OpenCitations Meta"},
        )
        assert status == 200
        assert body == SUCCESS_BODY
        assert content_type == "application/json"
        call = mock_session.post.call_args  # type: ignore[attr-defined]
        assert call.args[0] == "http://localhost/sparql"
        assert call.kwargs["data"] == {
            "update": f'INSERT DATA {{ <{RESOURCE_IRI}> {DCTERMS_TITLE} "OpenCitations Meta" . }}',
        }

    @patch("ramose.operation._http_session")
    def test_csv_success_body(self, mock_session: object) -> None:
        mock_session.post.return_value = _mock_response()  # type: ignore[attr-defined]
        op = _make_write_op()
        status, body, content_type, _ = op.exec(
            method="post",
            content_type="text/csv",
            body_params={"resource": RESOURCE_IRI, "title": "OpenCitations Meta"},
        )
        assert status == 200
        assert body == "status,message\r\n200,operation completed\r\n"
        assert content_type == "text/csv"

    @patch("ramose.operation._http_session")
    def test_update_endpoint_used_when_set(self, mock_session: object) -> None:
        mock_session.post.return_value = _mock_response()  # type: ignore[attr-defined]
        config = OperationConfig(
            sparql_endpoint="http://localhost/query",
            update_endpoint="http://localhost/update",
        )
        op = _make_write_op(config=config)
        op.exec(method="post", body_params={"resource": RESOURCE_IRI, "title": "OpenCitations Meta"})
        assert mock_session.post.call_args.args[0] == "http://localhost/update"  # type: ignore[attr-defined]

    @patch("ramose.operation._http_session")
    def test_non_2xx_from_store_propagates(self, mock_session: object) -> None:
        mock_session.post.return_value = _mock_response(status_code=400, reason="Bad Request")  # type: ignore[attr-defined]
        op = _make_write_op()
        status, body, content_type, _ = op.exec(
            method="post",
            body_params={"resource": RESOURCE_IRI, "title": "OpenCitations Meta"},
        )
        assert status == 400
        assert body == "HTTP status code 400: Bad Request"
        assert content_type == "text/plain"


class TestWriteMethodNotAllowed:
    def test_get_on_write_only_op_returns_405(self) -> None:
        op = _make_write_op()
        status, message, content_type, _ = op.exec(method="get")
        assert status == 405
        assert message == "HTTP status code 405: 'get' method not allowed"
        assert content_type == "text/plain"

    @patch("ramose.operation._http_session")
    def test_put_and_delete_are_writes(self, mock_session: object) -> None:
        mock_session.post.return_value = _mock_response()  # type: ignore[attr-defined]
        for method in ("put", "delete"):
            op = _make_write_op(method=method, sparql="DELETE WHERE { <[[resource]]> ?p ?o }")
            status, _, _, _ = op.exec(method=method, body_params={"resource": RESOURCE_IRI})
            assert status == 200


class TestWriteValueBinding:
    @patch("ramose.operation._http_session")
    def test_literal_special_chars_escaped(self, mock_session: object) -> None:
        mock_session.post.return_value = _mock_response()  # type: ignore[attr-defined]
        op = _make_write_op()
        op.exec(method="post", body_params={"resource": RESOURCE_IRI, "title": 'a"b\\c\nd'})
        assert mock_session.post.call_args.kwargs["data"]["update"] == (  # type: ignore[attr-defined]
            f'INSERT DATA {{ <{RESOURCE_IRI}> {DCTERMS_TITLE} "a\\"b\\\\c\\nd" . }}'
        )

    @patch("ramose.operation._http_session")
    def test_missing_param_rejected_with_400(self, mock_session: object) -> None:
        op = _make_write_op()
        status, body, content_type, _ = op.exec(method="post", body_params={"resource": RESOURCE_IRI})
        assert status == 400
        assert body == "HTTP status code 400: missing required parameter(s): title"
        assert content_type == "text/plain"
        mock_session.post.assert_not_called()  # type: ignore[attr-defined]

    @patch("ramose.operation._http_session")
    def test_iri_injection_rejected_with_400(self, mock_session: object) -> None:
        op = _make_write_op()
        status, _, content_type, _ = op.exec(
            method="post",
            body_params={"resource": "http://x/} ; DROP ALL ; INSERT DATA {", "title": "Title"},
        )
        assert status == 400
        assert content_type == "text/plain"
        mock_session.post.assert_not_called()  # type: ignore[attr-defined]


class TestWriteCacheInvalidation:
    @patch("ramose.operation._http_session")
    def test_write_clears_cache_and_skips_read(self, mock_session: object) -> None:
        mock_session.post.return_value = _mock_response()  # type: ignore[attr-defined]

        class FakeCache:
            def __init__(self) -> None:
                self.cleared = False
                self.get_calls = 0

            def get(self, key: str) -> object:
                self.get_calls += 1
                return None

            def clear(self) -> None:
                self.cleared = True

        cache = FakeCache()
        config = OperationConfig(sparql_endpoint="http://localhost/sparql", cache=cache)  # type: ignore[arg-type]
        op = _make_write_op(config=config)
        op.exec(method="post", body_params={"resource": RESOURCE_IRI, "title": "OpenCitations Meta"})
        assert cache.cleared is True
        assert cache.get_calls == 0
