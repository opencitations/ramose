# SPDX-FileCopyrightText: 2018-2021 Silvio Peroni <silvio.peroni@unibo.it>
# SPDX-FileCopyrightText: 2020-2021 Marilena Daquino <marilena.daquino2@unibo.it>
# SPDX-FileCopyrightText: 2022 Davide Brembilla
# SPDX-FileCopyrightText: 2024 Ivan Heibi <ivan.heibi2@unibo.it>
# SPDX-FileCopyrightText: 2025 Sergei Slinkin
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from requests import Session as _RequestsSession

FIELD_TYPE_RE = r"([^\(\s]+)\(([^\)]+)\)"
PARAM_NAME = r"{([^{}\(\)]+)}"
DEFAULT_HTTP_TIMEOUT = 60
FORMAT_PARTS_WITH_MEDIA_TYPE = 3

FORMAT_MEDIA_TYPES = {
    "json": "application/json",
    "csv": "text/csv",
}


def media_type_for_format(fmt: str) -> str | None:
    return FORMAT_MEDIA_TYPES.get((fmt or "").strip().lower())


_http_session = _RequestsSession()

_backend_auth: dict[str, str] = {}


def backend_auth_header(endpoint_url: str) -> dict[str, str]:
    """Return the Authorization header configured for a specific SPARQL endpoint, or an empty dict."""
    value = _backend_auth.get(endpoint_url)
    return {"Authorization": value} if value else {}
