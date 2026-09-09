# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import unquote

PREFIXES = """PREFIX cito: <http://purl.org/spar/cito/>
PREFIX datacite: <http://purl.org/spar/datacite/>
PREFIX literal: <http://www.essepuntato.it/2010/06/literalreification/>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX prism: <http://prismstandard.org/namespaces/basic/2.0/>
PREFIX pro: <http://purl.org/spar/pro/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX frbr: <http://purl.org/vocab/frbr/core#>
PREFIX fabio: <http://purl.org/spar/fabio/>
PREFIX oco: <https://w3id.org/oc/ontology/>
"""
META_GRAPHS = "\n".join(f"FROM <https://w3id.org/oc/meta/{kind}/>" for kind in ("br", "id", "ar", "ra"))
RESOLUTION = """VALUES ?doi { "[[doi]]" "[[doi]]"^^<http://www.w3.org/2001/XMLSchema#string> }
?identifier datacite:usesIdentifierScheme datacite:doi ; literal:hasLiteralValue ?doi .
?omid datacite:hasIdentifier ?identifier ."""
RELATIONS = """?citation a cito:Citation ; cito:hasCitedEntity ?omid ; cito:hasCitingEntity ?citing ."""


def decode_doi(doi: str) -> tuple[str]:
    return (unquote(doi),)


def fact_expression(kind: str, variables: tuple[str, ...]) -> str:
    parts = [f'"{kind}"']
    for variable in variables:
        parts.extend(['";"', f'ENCODE_FOR_URI(COALESCE(STR(?{variable}), ""))'])
    condition = f"BOUND(?{variables[0]})"
    if kind == "venue":
        condition += " && !BOUND(?excluded_type)"
    return f'BIND(IF({condition}, CONCAT({", ".join(parts)}), "") AS ?fact)'


def metadata_pattern() -> str:
    branches = (
        ("title", ("title",), "?citing dcterms:title ?title ."),
        ("date", ("date",), "?citing prism:publicationDate ?date ."),
        (
            "identifier",
            ("scheme", "identifier_value"),
            """?citing datacite:hasIdentifier ?id .
?id datacite:usesIdentifierScheme ?scheme ; literal:hasLiteralValue ?identifier_value .""",
        ),
        (
            "author",
            ("role", "agent", "given", "family", "name", "next"),
            """?citing pro:isDocumentContextFor ?role .
?role pro:withRole pro:author ; pro:isHeldBy ?agent .
OPTIONAL { ?role oco:hasNext ?next }
OPTIONAL { ?agent foaf:givenName ?given }
OPTIONAL { ?agent foaf:familyName ?family }
OPTIONAL { ?agent foaf:name ?name }""",
        ),
        (
            "venue",
            ("venue", "venue_title", "venue_scheme", "venue_id"),
            """{ ?citing frbr:partOf ?venue }
UNION { ?citing frbr:partOf ?venue_start . ?venue_start frbr:partOf+ ?venue }
BIND(IRI(STR(?venue)) AS ?venue_resource)
OPTIONAL {
  ?venue_resource a ?excluded_type .
  FILTER(?excluded_type IN (fabio:JournalIssue, fabio:JournalVolume))
}
OPTIONAL { ?venue_resource dcterms:title ?venue_title }
OPTIONAL {
  ?venue datacite:hasIdentifier ?venue_identifier .
  ?venue_identifier datacite:usesIdentifierScheme ?venue_scheme ; literal:hasLiteralValue ?venue_id .
}""",
        ),
    )
    return "\nUNION\n".join(
        "{\n" + pattern + "\n" + fact_expression(kind, variables) + "\n}" for kind, variables, pattern in branches
    )


def metadata_query() -> str:
    return f"""{PREFIXES}
SELECT DISTINCT ?citing (GROUP_CONCAT(DISTINCT ?fact; SEPARATOR="|") AS ?metadata)
{META_GRAPHS}
WHERE {{
OPTIONAL {{ {metadata_pattern()} }}
}}
GROUP BY ?citing
"""


def specification() -> str:
    service = f"""{PREFIXES}
SELECT ?omid ?citation ?citing (GROUP_CONCAT(DISTINCT ?fact; SEPARATOR="|") AS ?metadata)
{META_GRAPHS}
WHERE {{
{{ SELECT ?omid ?citation (COALESCE(?source_citing, "") AS ?citing) WHERE {{
{{ SELECT DISTINCT ?omid WHERE {{ {RESOLUTION} }} }}
SERVICE <http://index:7001/> {{ OPTIONAL {{ {RELATIONS.replace("?citing", "?source_citing")} }} }}
}} }}
OPTIONAL {{ {metadata_pattern()} }}
}}
GROUP BY ?omid ?citation ?citing
"""
    orchestration = f"""{PREFIXES}
SELECT DISTINCT ?omid
{META_GRAPHS}
WHERE {{ {RESOLUTION} }}

@@with index
@@join ?omid ?omid type=left
@@values ?omid
{PREFIXES}
SELECT DISTINCT ?omid ?citation ?citing WHERE {{ {RELATIONS} }}

@@with meta
@@join ?citing ?citing type=left
@@values ?citing
{metadata_query()}"""
    header = """#url /benchmark
#type api
#base http://localhost:8080
#method post
#addon queries
#title Enriched incoming citations
#description Compare SERVICE and RAMOSE for incoming citations and citing work metadata.
#version 1.0.0
#contacts contact@opencitations.net
#license ISC
#endpoint http://meta:8890/sparql
#sources meta=http://meta:8890/sparql; index=http://index:7001
"""
    return header + "".join(
        f"""
#url /{strategy}/{{doi}}
#type operation
#doi str(.+)
#method get
#preprocess decode_doi(doi)
#cache_disable true
#field_type str(omid) str(citation) str(citing) str(metadata)
#sparql {query}
"""
        for strategy, query in (("service", service), ("orchestration", orchestration))
    )


@dataclass(frozen=True)
class Response:
    omids: tuple[str, ...]
    relations: tuple[tuple[str, str, str], ...]
    works: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...]

    @property
    def enriched_work_count(self) -> int:
        return sum(bool(facts) for _, facts in self.works)


def normalize(content: bytes) -> Response:
    rows = json.loads(content)
    if not isinstance(rows, list) or not rows:
        message = "Expected resolved DOI rows, including when no citations exist"
        raise ValueError(message)
    omids = set()
    relations = set()
    works: dict[str, set[tuple[str, ...]]] = {}
    for row in rows:
        if not row["omid"] or bool(row["citation"]) != bool(row["citing"]):
            message = "Each citation must have both a cited and a citing resource"
            raise ValueError(message)
        if not row["citation"] and row["metadata"]:
            message = "A row without a citation cannot contain citing work metadata"
            raise ValueError(message)
        omids.add(row["omid"])
        if row["citation"]:
            relations.add((row["citation"], row["omid"], row["citing"]))
            facts = works.setdefault(row["citing"], set())
            facts.update(
                tuple(unquote(part) for part in fact.split(";")) for fact in row["metadata"].split("|") if fact
            )
    return Response(
        tuple(sorted(omids)),
        tuple(sorted(relations)),
        tuple((work, tuple(sorted(facts))) for work, facts in sorted(works.items())),
    )
