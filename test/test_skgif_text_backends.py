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
            "ramose.skg_if",
            'FILTER(CONTAINS(LCASE(?title), LCASE("adaptive")))',
        ),
        (
            "ramose.skg_if.blazegraph",
            '?title <http://www.bigdata.com/rdf/search#search> "adaptive" .',
        ),
        (
            "ramose.skg_if.fuseki",
            '?local_identifier <http://jena.apache.org/text#query> (<http://purl.org/dc/terms/title> "adaptive") .',
        ),
        (
            "ramose.skg_if.graphdb",
            '?title <http://www.ontotext.com/fts> "adaptive" .',
        ),
        (
            "ramose.skg_if.qlever",
            '?title <http://qlever.cs.uni-freiburg.de/builtin-functions/contains-word> "adaptive" .',
        ),
        (
            "ramose.skg_if.virtuoso",
            """?title bif:contains "'adaptive'" .""",
        ),
    ],
)
def test_product_title_search_backend_filter(module_name: str, expected_filter: str) -> None:
    module = import_module(module_name)
    result = module.handle_skg_if_product_filter(["cf.search.title:adaptive"])
    assert result == {"filter_preamble": "", "filter": expected_filter}


@pytest.mark.parametrize(
    "module_name",
    [
        "ramose.skg_if.blazegraph",
        "ramose.skg_if.fuseki",
        "ramose.skg_if.graphdb",
        "ramose.skg_if.qlever",
        "ramose.skg_if.virtuoso",
    ],
)
def test_backend_keeps_non_text_product_filters(module_name: str) -> None:
    module = import_module(module_name)
    result = module.handle_skg_if_product_filter(["identifiers.scheme:isbn"])
    assert result == {
        "filter_preamble": "",
        "filter": "?local_identifier datacite:hasIdentifier [ datacite:usesIdentifierScheme datacite:isbn ] .",
    }
