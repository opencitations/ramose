# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from ramose.skg_if import _base


def _qlever_text_search_filter(target: _base.TextSearchTarget, value: str) -> list[str]:
    return [
        f"{target.variable} "
        f"<http://qlever.cs.uni-freiburg.de/builtin-functions/contains-word> {_base.sparql_string(value)} .",
    ]


handle_skg_if_datasource_filter = _base.handle_skg_if_datasource_filter
handle_skg_if_grant_filter = _base.handle_skg_if_grant_filter
handle_skg_if_product_filter = _base.make_product_filter_handler(_qlever_text_search_filter)
handle_skg_if_topic_filter = _base.handle_skg_if_topic_filter
to_skg_if = _base.to_skg_if
