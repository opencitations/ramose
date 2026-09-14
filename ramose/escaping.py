# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

from re import fullmatch, search

_IRI_FORBIDDEN = r'[<>"{}|^`\\\x00-\x20]'
_LOCAL_NAME = r"[\w.\-:%]+"


class InvalidParameterValueError(ValueError):
    pass


def escape_literal(value: str) -> str:
    value = value.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")
    return value.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def escape_iri(value: str) -> str:
    if search(_IRI_FORBIDDEN, value):
        msg = f"invalid IRI value: {value!r}"
        raise InvalidParameterValueError(msg)
    return value


def escape_local_name(value: str) -> str:
    if not fullmatch(_LOCAL_NAME, value):
        msg = f"invalid prefixed name value: {value!r}"
        raise InvalidParameterValueError(msg)
    return value
