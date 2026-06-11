# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

from importlib import import_module

import pytest


@pytest.mark.parametrize(
    ("module_name", "expected_filter"),
    [
        (
            "ramose.skgif_addon",
            'FILTER(CONTAINS(LCASE(?title), LCASE("adaptive")))',
        ),
        (
            "ramose.skgif_addon.blazegraph",
            '?title <http://www.bigdata.com/rdf/search#search> "adaptive" .',
        ),
        (
            "ramose.skgif_addon.fuseki",
            '?local_identifier <http://jena.apache.org/text#query> (<http://purl.org/dc/terms/title> "adaptive") .',
        ),
        (
            "ramose.skgif_addon.graphdb",
            '?title <http://www.ontotext.com/fts> "adaptive" .',
        ),
        (
            "ramose.skgif_addon.qlever",
            '?title <http://qlever.cs.uni-freiburg.de/builtin-functions/contains-word> "adaptive" .',
        ),
        (
            "ramose.skgif_addon.virtuoso",
            """?title bif:contains "'adaptive'" .""",
        ),
    ],
)
def test_product_title_search_backend_filter(module_name: str, expected_filter: str) -> None:
    module = import_module(module_name)
    result = module.handle_skgif_product_filter(["cf.search.title:adaptive"])
    assert result == {"filter_preamble": "", "filter": expected_filter}


@pytest.mark.parametrize(
    "module_name",
    [
        "ramose.skgif_addon.blazegraph",
        "ramose.skgif_addon.fuseki",
        "ramose.skgif_addon.graphdb",
        "ramose.skgif_addon.qlever",
        "ramose.skgif_addon.virtuoso",
    ],
)
def test_backend_keeps_non_text_product_filters(module_name: str) -> None:
    module = import_module(module_name)
    result = module.handle_skgif_product_filter(["identifiers.scheme:isbn"])
    assert result == {
        "filter_preamble": "",
        "filter": "?local_identifier datacite:hasIdentifier [ datacite:usesIdentifierScheme datacite:isbn ] .",
    }
