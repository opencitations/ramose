# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from urllib.parse import unquote


def decode_issn(issn: str) -> tuple[str]:
    return (unquote(issn),)
