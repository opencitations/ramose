# SPDX-FileCopyrightText: 2018-2021 Silvio Peroni <silvio.peroni@unibo.it>
# SPDX-FileCopyrightText: 2020-2021 Marilena Daquino <marilena.daquino2@unibo.it>
# SPDX-FileCopyrightText: 2022 Davide Brembilla
# SPDX-FileCopyrightText: 2024 Ivan Heibi <ivan.heibi2@unibo.it>
# SPDX-FileCopyrightText: 2025 Sergei Slinkin
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from functools import cache

from requests import PreparedRequest
from requests import Session as _RequestsSession
from requests.adapters import HTTPAdapter
from requests.auth import AuthBase, HTTPDigestAuth

FIELD_TYPE_RE = r"([^\(\s]+)\(([^\)]+)\)"
PARAM_NAME = r"{([^{}\(\)]+)}"
DEFAULT_HTTP_TIMEOUT = 60
HTTP_POOL_SIZE = 100
FORMAT_PARTS_WITH_MEDIA_TYPE = 3

FORMAT_MEDIA_TYPES = {
    "json": "application/json",
    "csv": "text/csv",
}


def media_type_for_format(fmt: str) -> str | None:
    return FORMAT_MEDIA_TYPES.get((fmt or "").strip().lower())


_http_session = _RequestsSession()
for _scheme in ("http://", "https://"):
    _http_session.mount(_scheme, HTTPAdapter(pool_connections=HTTP_POOL_SIZE, pool_maxsize=HTTP_POOL_SIZE))

_backend_auth: dict[str, str] = {}


class _FixedAuthorization(AuthBase):
    def __init__(self, value: str) -> None:
        self.value = value

    def __call__(self, r: PreparedRequest) -> PreparedRequest:
        r.headers["Authorization"] = self.value
        return r


@cache
def _auth_for(value: str) -> AuthBase:
    scheme, _, credentials = value.partition(" ")
    if scheme.lower() == "digest":
        username, _, password = credentials.partition(":")
        return HTTPDigestAuth(username, password)
    return _FixedAuthorization(value)


def backend_auth(endpoint_url: str) -> AuthBase | None:
    """Return the credential configured for a specific SPARQL endpoint, or None."""
    value = _backend_auth.get(endpoint_url)
    return _auth_for(value) if value else None
