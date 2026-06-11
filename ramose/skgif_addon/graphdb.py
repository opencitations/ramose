# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from ramose.skgif_addon import _base


def _graphdb_text_search_filter(target: _base.TextSearchTarget, value: str) -> list[str]:
    return [f"{target.variable} <http://www.ontotext.com/fts> {_base.sparql_string(value)} ."]


handle_skgif_datasource_filter = _base.handle_skgif_datasource_filter
handle_skgif_grant_filter = _base.handle_skgif_grant_filter
handle_skgif_product_filter = _base.make_product_filter_handler(_graphdb_text_search_filter)
handle_skgif_topic_filter = _base.handle_skgif_topic_filter
to_skgif = _base.to_skgif
