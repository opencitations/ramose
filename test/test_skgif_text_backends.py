# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

from importlib import import_module
from re import escape

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


def test_identifier_filter_escapes_literal_value() -> None:
    module = import_module("ramose.skg_if")
    result = module.handle_skg_if_product_filter(['identifiers.id:10.0000/"quoted"'])
    assert result == {
        "filter_preamble": "",
        "filter": (
            "?local_identifier datacite:hasIdentifier"
            ' [ literal:hasLiteralValue "10.0000/\\"quoted\\""^^<http://www.w3.org/2001/XMLSchema#string> ] .'
        ),
    }


def test_agent_literal_filter_escapes_value() -> None:
    module = import_module("ramose.skg_if")
    result = module.handle_skg_if_product_filter(['contributions.by.name:Zenodo "community"'])
    assert result == {
        "filter_preamble": "",
        "filter": (
            "?local_identifier pro:isDocumentContextFor [ pro:isHeldBy ?_filter_agent ] .\n"
            '?_filter_agent foaf:name "Zenodo \\"community\\"" .'
        ),
    }


def test_cites_doi_filter_escapes_literal_value() -> None:
    module = import_module("ramose.skg_if")
    result = module.handle_skg_if_product_filter(['cf.cites_doi:10.0000/"quoted"'])
    assert result == {
        "filter_preamble": (
            "PREFIX datacite: <http://purl.org/spar/datacite/>\n"
            "PREFIX literal: <http://www.essepuntato.it/2010/06/literalreification/>\n"
            "SELECT ?_target WHERE {\n"
            "  ?_target datacite:hasIdentifier ?_id_node .\n"
            "  ?_id_node datacite:usesIdentifierScheme datacite:doi ;\n"
            '            literal:hasLiteralValue "10.0000/\\"quoted\\""'
            "^^<http://www.w3.org/2001/XMLSchema#string> .\n"
            "}\n"
            "@@values ?_target\n"
            "@@join ?_target ?_target type=inner\n"
            "@@with source=index\n"
            "PREFIX cito: <http://purl.org/spar/cito/>\n"
            "SELECT ?_target ?local_identifier WHERE {\n"
            "  ?_ci cito:hasCitingEntity ?_citing ;\n"
            "       cito:hasCitedEntity ?_target .\n"
            "  BIND(STR(?_citing) AS ?local_identifier)\n"
            "}\n"
            "@@remove ?_target\n"
            "@@join ?local_identifier ?local_identifier type=inner"
        ),
        "filter": "",
    }


def test_citation_iri_filter_rejects_unsafe_value() -> None:
    module = import_module("ramose.skg_if")
    unsafe_uri = "https://example.org/resource> . ?x ?y ?z ."
    expected_message = f"invalid IRI value: {unsafe_uri!r}"
    with pytest.raises(ValueError, match=f"^{escape(expected_message)}$") as exc_info:
        module.handle_skg_if_product_filter([f"cf.cites:{unsafe_uri}"])

    assert str(exc_info.value) == expected_message
