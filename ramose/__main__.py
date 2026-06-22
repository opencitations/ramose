# SPDX-FileCopyrightText: 2018-2021 Silvio Peroni <silvio.peroni@unibo.it>
# SPDX-FileCopyrightText: 2020-2021 Marilena Daquino <marilena.daquino2@unibo.it>
# SPDX-FileCopyrightText: 2022 Davide Brembilla
# SPDX-FileCopyrightText: 2024 Ivan Heibi <ivan.heibi2@unibo.it>
# SPDX-FileCopyrightText: 2025 Sergei Slinkin
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import importlib.resources
import os
from argparse import ArgumentParser, Namespace
from csv import writer
from http import HTTPStatus
from io import StringIO
from json import dumps
from pathlib import Path
from urllib.parse import unquote

from flask import Flask, Response, make_response, request
from flask_swagger_ui import get_swaggerui_blueprint

from ramose._constants import _backend_auth
from ramose.api_manager import APIManager
from ramose.auth import TokenStore
from ramose.html_documentation import HTMLDocumentationHandler
from ramose.openapi_documentation import SWAGGER_MARKDOWN_CSS_FIX, OpenAPIDocumentationHandler
from ramose.operation import Operation


def _parse_args() -> Namespace:  # pragma: no cover
    arg_parser = ArgumentParser(
        "ramose",
        description="The 'Restful API Manager Over SPARQL Endpoints' (a.k.a. "
        "'RAMOSE') is an application that allows one to expose a "
        "Restful API interface, according to a particular "
        "specification document, to interact with a SPARQL endpoint.",
    )

    arg_parser.add_argument(
        "-s",
        "--spec",
        dest="spec",
        nargs="+",
        help="The RAMOSE spec file(s) containing the API definition(s): .hf, .yaml, or .yml.",
    )
    arg_parser.add_argument(
        "-m",
        "--method",
        dest="method",
        default="get",
        help="The method to use to make a request to the API.",
    )
    arg_parser.add_argument("-c", "--call", dest="call", help="The URL to call for querying the API.")
    arg_parser.add_argument(
        "-f",
        "--format",
        dest="format",
        default="application/json",
        help="The format in which to get the response.",
    )
    arg_parser.add_argument(
        "-d",
        "--doc",
        dest="doc",
        default=False,
        action="store_true",
        help="Say to generate the HTML documentation of the API (if it is specified, all "
        "the arguments '-m', '-c', and '-f' won't be considered).",
    )
    arg_parser.add_argument(
        "--openapi",
        dest="openapi",
        default=False,
        action="store_true",
        help="Export the API specification to OpenAPI 3.2 YAML.",
    )
    arg_parser.add_argument(
        "--api-base",
        dest="api_base",
        default=None,
        help="When exporting docs/OpenAPI with multiple specs loaded, choose which API base URL to export.",
    )
    arg_parser.add_argument("-o", "--output", dest="output", help="A file where to store the response.")
    arg_parser.add_argument(
        "-w",
        "--webserver",
        dest="webserver",
        default=False,
        help="The host:port where to deploy a Flask webserver for testing the API.",
    )
    arg_parser.add_argument(
        "-css",
        "--css",
        dest="css",
        help=(
            "The path of a .css file for styling the API documentation "
            "(to be specified either with '-w' or with '-d' and '-o' arguments)."
        ),
    )
    arg_parser.add_argument(
        "--debug",
        dest="debug",
        default=False,
        action="store_true",
        help="Enable Flask debug mode (auto-reload, interactive debugger).",
    )
    arg_parser.add_argument(
        "--cache-dir",
        dest="cache_dir",
        default=".cache",
        help="Directory for result caching (default: .cache). Use --no-cache to disable.",
    )
    arg_parser.add_argument(
        "--no-cache",
        dest="no_cache",
        default=False,
        action="store_true",
        help="Disable result caching.",
    )
    arg_parser.add_argument(
        "--cache-ttl",
        dest="cache_ttl",
        type=int,
        default=86400,
        help="Cache TTL in seconds (default: 86400 = 1 day).",
    )
    arg_parser.add_argument(
        "--retry-attempts",
        dest="retry_attempts",
        type=int,
        default=3,
        help="Total SPARQL read attempts, including the first one (default: 3). Use 1 to disable retries.",
    )
    arg_parser.add_argument(
        "--retry-wait",
        dest="retry_wait",
        type=float,
        default=0.5,
        help="Seconds to wait before the first SPARQL read retry (default: 0.5).",
    )
    arg_parser.add_argument(
        "--retry-backoff",
        dest="retry_backoff",
        type=float,
        default=2.0,
        help="Multiplier applied between SPARQL read retry waits (default: 2.0).",
    )
    arg_parser.add_argument(
        "--auth-db",
        dest="auth_db",
        default=".auth",
        help="Directory for the bearer token store (default: .auth).",
    )
    arg_parser.add_argument(
        "--token-create",
        dest="token_create",
        metavar="LABEL",
        help="Create a bearer token with the given label, print it once, and exit.",
    )
    arg_parser.add_argument(
        "--token-ttl",
        dest="token_ttl",
        type=int,
        default=None,
        help="TTL in seconds for the token created with --token-create (default: no expiry).",
    )
    arg_parser.add_argument(
        "--token-list",
        dest="token_list",
        default=False,
        action="store_true",
        help="List the stored bearer tokens and exit.",
    )
    arg_parser.add_argument(
        "--token-revoke",
        dest="token_revoke",
        metavar="TOKEN",
        help="Revoke the given bearer token and exit.",
    )
    arg_parser.add_argument(
        "--backend-auth",
        dest="backend_auth",
        action="append",
        metavar="ENDPOINT=HEADER",
        help="Per-endpoint credential sent to a SPARQL backend, as 'endpoint_url=header', e.g. "
        "'https://host/sparql=Bearer <token>' or 'https://host/sparql=Basic <base64>'. The header is the "
        "full Authorization value, whatever scheme the backend expects. Repeatable for several backends. "
        "Merged with the RAMOSE_BACKEND_AUTH environment variable (newline-separated entries), which is "
        "preferred for secrets since CLI arguments are visible in the process list. The credential is sent "
        "only to its endpoint, never to any other.",
    )

    return arg_parser.parse_args()


def parse_backend_auth(cli_entries: list[str] | None, env_value: str | None) -> dict[str, str]:
    entries: list[str] = []
    if env_value:
        entries.extend(env_value.splitlines())
    if cli_entries:
        entries.extend(cli_entries)
    mapping: dict[str, str] = {}
    for entry in entries:
        stripped = entry.strip()
        if not stripped:
            continue
        endpoint, separator, header = stripped.partition("=")
        if not separator or not endpoint.strip() or not header.strip():
            message = f"invalid backend auth entry (expected 'endpoint=header'): {entry!r}"
            raise ValueError(message)
        mapping[endpoint.strip()] = header.strip()
    return mapping


def _handle_openapi_export(  # pragma: no cover
    api_url: str,
    api_manager: APIManager,
    openapi_handler: OpenAPIDocumentationHandler,
    fallback_page: str,
) -> Response | tuple[str, int]:
    base = api_url.rsplit("/", 1)[0]
    if "/" + base in api_manager.all_conf:
        status, yaml_content = openapi_handler.get_documentation(base_url=base)
        response = make_response(yaml_content, status)
        response.headers.set("Content-Type", "application/yaml")
        response.headers.set("Access-Control-Allow-Origin", "*")
        response.headers.set("Access-Control-Allow-Credentials", "true")
        return response
    return fallback_page, 404


def _build_error_response(status_code: int, error_message: str, content_type: str) -> Response:  # pragma: no cover
    if content_type == "text/csv":
        csv_buffer = StringIO()
        csv_writer = writer(csv_buffer)
        csv_writer.writerows([["error", "message"], [str(status_code), str(error_message)]])
        response = make_response(csv_buffer.getvalue(), status_code)
        response.headers.set("Content-Disposition", "attachment", filename="error.csv")
    else:
        response = make_response(dumps({"error": status_code, "message": error_message}), status_code)
    response.headers.set("Content-Type", content_type)
    return response


def _is_authorized(token_store: TokenStore) -> bool:  # pragma: no cover
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        return False
    return token_store.validate(header[len("Bearer ") :])


def _read_body_params(method: str) -> dict[str, str] | None:  # pragma: no cover
    if method not in ("post", "put", "delete"):
        return None
    params = request.args.to_dict()
    if request.is_json:
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            params.update(payload)
    else:
        params.update(request.form.to_dict())
    return params


def _handle_api_call(api_url: str, api_manager: APIManager, token_store: TokenStore) -> Response:  # pragma: no cover
    method = request.method.lower()
    query = unquote(request.query_string.decode("utf8"))
    full_call = "/" + api_url + ("?" + query if query else "")
    operation = api_manager.get_op(full_call, method)
    content_type = "application/json"
    if isinstance(operation, Operation):
        if operation.requires_auth and not _is_authorized(token_store):
            return _build_error_response(401, "HTTP status code 401: missing or invalid bearer token", content_type)
        body_params = _read_body_params(method)
        fmt = request.args.get("format")
        if fmt is not None:
            if "csv" in fmt:
                content_type = "text/csv"
        else:
            candidates = operation.media_type_to_format()
            best = request.accept_mimetypes.best_match(list(candidates))
            if best is not None:
                content_type = "text/csv" if best == "text/csv" else "application/json"
                negotiated = api_manager.get_op(
                    full_call + ("&" if query else "?") + "format=" + candidates[best],
                    method,
                )
                if isinstance(negotiated, Operation):
                    operation = negotiated
        status_code, body, response_content_type, headers = operation.exec(
            method=method,
            content_type=content_type,
            body_params=body_params,
        )
    else:
        status_code, body, response_content_type = operation
        headers = {}

    if status_code == HTTPStatus.OK:
        response = make_response(body, status_code)
        response.headers.set("Content-Type", response_content_type)
        for header_name, header_value in headers.items():
            response.headers.set(header_name, header_value)
    else:
        response = _build_error_response(status_code, body, content_type)

    response.headers.set("Access-Control-Allow-Origin", "*")
    response.headers.set("Access-Control-Allow-Credentials", "true")
    return response


def _build_app(  # pragma: no cover
    api_manager: APIManager,
    html_handler: HTMLDocumentationHandler,
    openapi_handler: OpenAPIDocumentationHandler,
    css_path: str | None,
    token_store: TokenStore,
) -> Flask:
    app = Flask(__name__)

    swagger_url = "/docs"
    spec_urls = [{"name": base.lstrip("/"), "url": f"{base}/openapi.yaml"} for base in api_manager.all_conf]
    swagger_bp = get_swaggerui_blueprint(swagger_url, "", config={"urls": spec_urls})
    app.register_blueprint(swagger_bp, url_prefix=swagger_url)

    @app.route(f"{swagger_url}/index.css")
    def swagger_index_css() -> Response:
        base_css = importlib.resources.files("flask_swagger_ui").joinpath("dist/index.css").read_text(encoding="utf-8")
        response = make_response(base_css + SWAGGER_MARKDOWN_CSS_FIX)
        response.headers.set("Content-Type", "text/css")
        return response

    @app.route("/")
    def home() -> str:
        return html_handler.get_index(css_path)

    @app.route("/<path:api_url>", methods=["GET", "POST", "PUT", "DELETE"])
    def doc(api_url: str) -> Response | tuple[str, int] | str:
        if api_url.endswith(("openapi.yaml", "openapi.yml")):
            return _handle_openapi_export(api_url, api_manager, openapi_handler, html_handler.get_index(css_path))

        if not any(api_base in "/" + api_url for api_base in api_manager.all_conf):
            return html_handler.get_index(css_path), 404

        if any(api_base == "/" + api_url for api_base in api_manager.all_conf):
            status, page = html_handler.get_documentation(css_path, api_url)
            return page, status

        return _handle_api_call(api_url, api_manager, token_store)

    return app


def _run_webserver(  # pragma: no cover
    api_manager: APIManager,
    html_handler: HTMLDocumentationHandler,
    openapi_handler: OpenAPIDocumentationHandler,
    css_path: str | None,
    args: Namespace,
) -> None:
    html_handler.logger_ramose()

    host_name = args.webserver.rsplit(":", 1)[0] if ":" in args.webserver else "127.0.0.1"
    port = args.webserver.rsplit(":", 1)[1] if ":" in args.webserver else "8080"

    token_store = TokenStore(args.auth_db)
    app = _build_app(api_manager, html_handler, openapi_handler, css_path, token_store)
    app.run(host=str(host_name), debug=args.debug, port=int(port))


def _run_cli(  # pragma: no cover
    api_manager: APIManager,
    html_handler: HTMLDocumentationHandler,
    openapi_handler: OpenAPIDocumentationHandler,
    css_path: str | None,
    args: Namespace,
) -> None:
    if args.openapi:
        status, body = openapi_handler.get_documentation(base_url=args.api_base)
        content_type = "application/yaml"
    elif args.doc:
        status, body = html_handler.get_documentation(css_path)
        content_type = "text/html"
    else:
        operation = api_manager.get_op(args.call, args.method)
        if isinstance(operation, Operation):
            status, body, content_type, _ = operation.exec(args.method, args.format)
        else:
            status, body, content_type = operation

    if args.output is None:
        print(f"# Response HTTP code: {status}\n# Body:\n{body}\n# Content-type: {content_type}")
    else:
        with Path(args.output).open("w") as output_file:
            output_file.write(body)


def _handle_token_management(args: Namespace) -> None:  # pragma: no cover
    token_store = TokenStore(args.auth_db)
    if args.token_create:
        token = token_store.create(args.token_create, args.token_ttl)
        print(f"Token created for '{args.token_create}':\n{token}")
    elif args.token_revoke:
        print("Token revoked." if token_store.revoke(args.token_revoke) else "Token not found.")
    elif args.token_list:
        for label, created_at, expires_at, revoked in token_store.list_tokens():
            print(f"{label}\tcreated={created_at}\texpires={expires_at}\trevoked={bool(revoked)}")


def main() -> None:  # pragma: no cover
    args = _parse_args()

    if args.token_create or args.token_list or args.token_revoke:
        _handle_token_management(args)
        return

    if not args.spec:
        message = "the following arguments are required: -s/--spec"
        raise SystemExit(message)

    _backend_auth.update(parse_backend_auth(args.backend_auth, os.environ.get("RAMOSE_BACKEND_AUTH")))

    cache_dir = None if args.no_cache else args.cache_dir
    api_manager = APIManager(
        args.spec,
        cache_dir=cache_dir,
        cache_ttl=args.cache_ttl,
        retry_attempts=args.retry_attempts,
        retry_wait=args.retry_wait,
        retry_backoff=args.retry_backoff,
    )
    html_handler = HTMLDocumentationHandler(api_manager)
    openapi_handler = OpenAPIDocumentationHandler(api_manager)
    css_path = args.css or None

    if args.webserver:
        _run_webserver(api_manager, html_handler, openapi_handler, css_path, args)
    else:
        _run_cli(api_manager, html_handler, openapi_handler, css_path, args)


if __name__ == "__main__":  # pragma: no cover
    main()
