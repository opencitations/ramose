# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import pytest

from ramose.filters import apply_filters

# The per-backend full-text-search syntaxes are no longer Python code: each deployment
# expresses its cf.search.title filter as a config template, rendered by the generic engine.
# The default uses portable SPARQL CONTAINS; triplestore-specific backends use their own index.
BACKEND_TEMPLATES: dict[str, tuple[str, str]] = {
    "default": (
        'FILTER(CONTAINS(LCASE(?title), LCASE("{{value}}")))',
        'FILTER(CONTAINS(LCASE(?title), LCASE("adaptive")))',
    ),
    "blazegraph": (
        '?title <http://www.bigdata.com/rdf/search#search> "{{value}}" .',
        '?title <http://www.bigdata.com/rdf/search#search> "adaptive" .',
    ),
    "fuseki": (
        '?local_identifier <http://jena.apache.org/text#query> (<http://purl.org/dc/terms/title> "{{value}}") .',
        '?local_identifier <http://jena.apache.org/text#query> (<http://purl.org/dc/terms/title> "adaptive") .',
    ),
    "graphdb": (
        '?title <http://www.ontotext.com/fts> "{{value}}" .',
        '?title <http://www.ontotext.com/fts> "adaptive" .',
    ),
    "qlever": (
        '?title <http://qlever.cs.uni-freiburg.de/builtin-functions/contains-word> "{{value}}" .',
        '?title <http://qlever.cs.uni-freiburg.de/builtin-functions/contains-word> "adaptive" .',
    ),
    "virtuoso": (
        "?title bif:contains \"'{{value}}'\" .",
        "?title bif:contains \"'adaptive'\" .",
    ),
}


@pytest.mark.parametrize(("template", "expected"), list(BACKEND_TEMPLATES.values()), ids=list(BACKEND_TEMPLATES))
def test_backend_text_search_template(template: str, expected: str) -> None:
    assert apply_filters({"cf.search.title": {"filter": template}}, ["cf.search.title:adaptive"]) == {
        "filter": expected
    }
