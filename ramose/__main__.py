# SPDX-FileCopyrightText: 2018-2021 Silvio Peroni <silvio.peroni@unibo.it>
# SPDX-FileCopyrightText: 2020-2021 Marilena Daquino <marilena.daquino2@unibo.it>
# SPDX-FileCopyrightText: 2022 Davide Brembilla
# SPDX-FileCopyrightText: 2024 Ivan Heibi <ivan.heibi2@unibo.it>
# SPDX-FileCopyrightText: 2025 Sergei Slinkin
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from argparse import ArgumentParser
from csv import writer
from http import HTTPStatus
from io import StringIO
from json import dumps
from os import path as pt
from pathlib import Path
from urllib.parse import unquote

from flask import Flask, make_response, request

from ramose.api_manager import APIManager
from ramose.html_documentation import HTMLDocumentationHandler
from ramose.openapi_documentation import OpenAPIDocumentationHandler
from ramose.operation import Operation


def _parse_args():  # pragma: no cover
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
        required=True,
        nargs="+",
        help="The file(s) in hash format containing the specification of the API(s).",
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
        help="Export the API specification to OpenAPI 3.0 YAML.",
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

    return arg_parser.parse_args()


def _handle_openapi_export(api_url, api_manager, openapi_handler, fallback_page):  # pragma: no cover
    base = api_url.rsplit("/", 1)[0]
    if "/" + base in api_manager.all_conf:
        status, yaml_content = openapi_handler.get_documentation(base_url=base)
        response = make_response(yaml_content, status)
        response.headers.set("Content-Type", "application/yaml")
        response.headers.set("Access-Control-Allow-Origin", "*")
        response.headers.set("Access-Control-Allow-Credentials", "true")
        return response
    return fallback_page, 404


def _build_error_response(status_code, error_message, content_type):  # pragma: no cover
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


def _handle_api_call(api_url, api_manager, content_type):  # pragma: no cover
    full_call = "/" + api_url
    operation = api_manager.get_op(full_call + "?" + unquote(request.query_string.decode("utf8")))
    if isinstance(operation, Operation):
        status_code, body, response_content_type, headers = operation.exec(content_type=content_type)
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


def _run_webserver(api_manager, html_handler, openapi_handler, css_path, args):  # pragma: no cover
    try:
        html_handler.logger_ramose()

        host_name = args.webserver.rsplit(":", 1)[0] if ":" in args.webserver else "127.0.0.1"
        port = args.webserver.rsplit(":", 1)[1] if ":" in args.webserver else "8080"

        app = Flask(__name__)

        if args.call:
            args.call = args.call[1:]

        @app.route("/")
        def home():
            return html_handler.get_index(css_path)

        @app.route("/<path:api_url>")
        def doc(api_url):
            if api_url.endswith(("openapi.yaml", "openapi.yml")):
                return _handle_openapi_export(api_url, api_manager, openapi_handler, html_handler.get_index(css_path))

            if not any(api_base in "/" + api_url for api_base in api_manager.all_conf):
                return html_handler.get_index(css_path), 404

            if any(api_base == "/" + api_url for api_base in api_manager.all_conf):
                status, page = html_handler.get_documentation(css_path, api_url)
                return page, status

            fmt = request.args.get("format")
            content_type = "text/csv" if fmt is not None and "csv" in fmt else "application/json"
            return _handle_api_call(api_url, api_manager, content_type)

        app.run(host=str(host_name), debug=True, port=int(port))  # noqa: S201

    except Exception as exc:  # noqa: BLE001
        traceback = exc.__traceback__
        filename = pt.split(traceback.tb_frame.f_code.co_filename)[1] if traceback else "?"
        line_number = traceback.tb_lineno if traceback else "?"
        print(f"[ERROR] {type(exc).__name__} {filename} {line_number}")


def _run_cli(api_manager, html_handler, openapi_handler, css_path, args):  # pragma: no cover
    if args.openapi:
        status, body = openapi_handler.get_documentation(base_url=args.api_base)
        content_type = "application/yaml"
    elif args.doc:
        status, body = html_handler.get_documentation(css_path)
        content_type = "text/html"
    else:
        operation = api_manager.get_op(args.call)
        if isinstance(operation, Operation):
            status, body, content_type, _ = operation.exec(args.method, args.format)
        else:
            status, body, content_type = operation

    if args.output is None:
        print(f"# Response HTTP code: {status}\n# Body:\n{body}\n# Content-type: {content_type}")
    else:
        with Path(args.output).open("w") as output_file:
            output_file.write(body)


def main():  # pragma: no cover
    args = _parse_args()
    cache_dir = None if args.no_cache else args.cache_dir
    api_manager = APIManager(args.spec, cache_dir=cache_dir, cache_ttl=args.cache_ttl)
    html_handler = HTMLDocumentationHandler(api_manager)
    openapi_handler = OpenAPIDocumentationHandler(api_manager)
    css_path = args.css or None

    if args.webserver:
        _run_webserver(api_manager, html_handler, openapi_handler, css_path, args)
    else:
        _run_cli(api_manager, html_handler, openapi_handler, css_path, args)


if __name__ == "__main__":  # pragma: no cover
    main()
