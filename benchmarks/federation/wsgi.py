# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from ramose.__main__ import _build_app
from ramose.api_manager import APIManager
from ramose.auth import TokenStore
from ramose.html_documentation import HTMLDocumentationHandler
from ramose.openapi_documentation import OpenAPIDocumentationHandler

api_manager = APIManager(["/data/benchmark/operations.hf"])
app = _build_app(
    api_manager,
    HTMLDocumentationHandler(api_manager),
    OpenAPIDocumentationHandler(api_manager),
    None,
    TokenStore("/tmp/ramose-benchmark-auth"),  # noqa: S108
)
