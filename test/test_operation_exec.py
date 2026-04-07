# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from types import SimpleNamespace
from unittest.mock import patch

from ramose import Operation


def _mock_response(status_code=200, text="name,age\nAlice,30\n", reason="OK"):
    resp = SimpleNamespace()
    resp.status_code = status_code
    resp.text = text
    resp.reason = reason
    resp.encoding = None
    return resp


def _make_op(
    op_url="/api/v1/test/val",
    op_key=r"/api/v1/test/(.+)",
    op_item=None,
    tp="http://localhost/sparql",
    sparql_http_method="get",
    addon=None,
):
    if op_item is None:
        op_item = {
            "url": "/test/{id}",
            "id": "str(.+)",
            "sparql": "SELECT ?name ?age WHERE { BIND([[id]] AS ?name) BIND('30' AS ?age) }",
            "method": "get",
            "field_type": "str(name) int(age)",
        }
    return Operation(op_url, op_key, op_item, tp, sparql_http_method, addon)


class TestExecMethodNotAllowed:
    def test_returns_405_for_wrong_method(self):
        op = _make_op()
        sc, msg, ct = op.exec(method="delete")
        assert sc == 405
        assert msg == "HTTP status code 405: 'delete' method not allowed"
        assert ct == "text/plain"


class TestExecGetRequest:
    @patch("ramose.operation._http_session")
    def test_successful_get(self, mock_session):
        mock_session.get.return_value = _mock_response()
        op = _make_op()
        result = op.exec(method="get", content_type="text/csv")
        assert result[0] == 200
        assert result[1] == "name,age\r\nAlice,30\r\n"

    @patch("ramose.operation._http_session")
    def test_successful_post(self, mock_session):
        mock_session.post.return_value = _mock_response()
        op = _make_op(sparql_http_method="post")
        result = op.exec(method="get", content_type="text/csv")
        assert result[0] == 200
        mock_session.post.assert_called_once()


class TestExecNon200:
    @patch("ramose.operation._http_session")
    def test_sparql_endpoint_error(self, mock_session):
        mock_session.get.return_value = _mock_response(status_code=500, reason="Internal Server Error")
        op = _make_op()
        sc, msg, ct = op.exec(method="get")
        assert sc == 500
        assert msg == "HTTP status code 500: Internal Server Error"
        assert ct == "text/plain"


class TestExecTimeout:
    @patch("ramose.operation._http_session")
    def test_timeout_returns_408(self, mock_session):
        mock_session.get.side_effect = TimeoutError("timed out")
        op = _make_op()
        sc, msg, ct = op.exec(method="get")
        assert sc == 408
        assert msg.startswith("HTTP status code 408: request timeout - TimeoutError: timed out (line ")
        assert ct == "text/plain"


class TestExecTypeError:
    @patch("ramose.operation._http_session")
    def test_type_error_returns_400(self, mock_session):
        mock_session.get.side_effect = TypeError("bad type")
        op = _make_op()
        sc, msg, ct = op.exec(method="get")
        assert sc == 400
        assert msg.startswith(
            "HTTP status code 400: parameter in the request not compliant with the type specified - TypeError: bad type (line "
        )
        assert ct == "text/plain"


class TestExecGenericError:
    @patch("ramose.operation._http_session")
    def test_generic_error_returns_500(self, mock_session):
        mock_session.get.side_effect = RuntimeError("unexpected")
        op = _make_op()
        sc, msg, ct = op.exec(method="get")
        assert sc == 500
        assert msg.startswith("HTTP status code 500: something unexpected happened - RuntimeError: unexpected (line ")
        assert ct == "text/plain"


class TestExecJsonOutput:
    @patch("ramose.operation._http_session")
    def test_json_content_type(self, mock_session):
        mock_session.get.return_value = _mock_response()
        op = _make_op()
        result = op.exec(method="get", content_type="application/json")
        assert result[0] == 200
        assert result[2] == "application/json"


class TestExecMultipleParameterCombinations:
    """When a preprocess function expands a parameter into a list of values,
    exec() generates the cartesian product of all parameter combinations and
    issues one SPARQL query per combination. The CSV header row is included
    only in the first result to avoid duplication."""

    @patch("ramose.operation._http_session")
    def test_header_included_once(self, mock_session):
        mock_session.get.return_value = _mock_response()

        class FakeAddon:
            @staticmethod
            def expand(val):
                return (["a", "b"],)

        op_item = {
            "url": "/test/{id}",
            "id": "str(.+)",
            "sparql": "SELECT ?name ?age WHERE { BIND('[[id]]' AS ?name) BIND('30' AS ?age) }",
            "method": "get",
            "field_type": "str(name) int(age)",
            "preprocess": "expand(id)",
        }
        op = _make_op(op_item=op_item, addon=FakeAddon)
        result = op.exec(method="get", content_type="text/csv")
        assert result[0] == 200
        assert mock_session.get.call_count == 2


class TestExecNonStrTypedParam:
    @patch("ramose.operation._http_session")
    def test_int_param_type_conversion(self, mock_session):
        mock_session.get.return_value = _mock_response()
        op_item = {
            "url": "/test/{count}",
            "count": "int([0-9]+)",
            "sparql": "SELECT ?name WHERE { BIND('x' AS ?name) } LIMIT [[count]]",
            "method": "get",
            "field_type": "str(name)",
        }
        op = _make_op(op_url="/api/v1/test/5", op_item=op_item)
        result = op.exec(method="get", content_type="text/csv")
        assert result[0] == 200


class TestExecKeyErrorFallback:
    """When an operation item does not declare a type for a URL parameter
    (e.g. missing ``"id": "str(.+)"``), exec() falls back to using the raw
    matched value from the URL without any type conversion."""

    @patch("ramose.operation._http_session")
    def test_param_without_type_definition(self, mock_session):
        mock_session.get.return_value = _mock_response()
        op_item = {
            "url": "/test/{id}",
            "sparql": "SELECT ?name WHERE { BIND('[[id]]' AS ?name) }",
            "method": "get",
            "field_type": "str(name)",
        }
        op = _make_op(op_item=op_item)
        result = op.exec(method="get", content_type="text/csv")
        assert result[0] == 200
