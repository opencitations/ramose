# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import csv
import json
from collections.abc import Callable
from io import StringIO
from math import ceil
from urllib.parse import parse_qs, urlencode, urlsplit

from oc_constants import FABIO_TYPE_LABELS

SKGIF_CONTEXT = [
    "https://w3id.org/skg-if/context/1.1.0/skg-if.json",
    "https://w3id.org/skg-if/context/1.0.0/skg-if-api.json",
    {"@base": "https://w3id.org/skg-if/sandbox/opencitations/"},
]

FABIO_TO_SKGIF_PRODUCT_TYPE = {
    "http://purl.org/spar/fabio/DataFile": "research data",
    "http://purl.org/spar/fabio/DataManagementPlan": "research data",
    "http://purl.org/spar/fabio/ComputerProgram": "research software",
}

NON_LITERATURE_FABIO_CLASSES = frozenset(FABIO_TO_SKGIF_PRODUCT_TYPE.keys())

SKGIF_TO_FABIO_PRODUCT_TYPE: dict[str, list[str]] = {}
for _fabio_uri, _skgif_type in FABIO_TO_SKGIF_PRODUCT_TYPE.items():
    SKGIF_TO_FABIO_PRODUCT_TYPE.setdefault(_skgif_type, []).append(_fabio_uri)


def _collect_identifiers(rows: list[dict]) -> list[dict]:
    seen = set()
    identifiers = []
    for row in rows:
        scheme = row["id_scheme"]
        value = row["id_value"]
        if scheme and value and (scheme, value) not in seen:
            seen.add((scheme, value))
            identifiers.append({"value": value, "scheme": scheme})
    return identifiers


def _order_linked_list(items: dict[str, dict], next_map: dict[str, str | None]) -> list[dict]:
    if not items:
        return []

    next_values = set(next_map.values()) - {None}
    start_candidates = [role_uri for role_uri in items if role_uri not in next_values]
    if not start_candidates:
        return list(items.values())

    ordered = []
    current = start_candidates[0]
    visited = set()
    while current and current in items and current not in visited:
        visited.add(current)
        ordered.append(items[current])
        current = next_map.get(current)

    for role_uri, contributor in items.items():
        if role_uri not in visited:
            ordered.append(contributor)

    return ordered


def _build_agent(row: dict) -> dict | None:
    family_name = row["contributor_family_name"]
    given_name = row["contributor_given_name"]
    full_name = row["contributor_name"]
    orcid = row["contributor_orcid"]
    ra_id = row["contributor_ra_id"]
    role = row["contributor_role"]

    is_person = bool(family_name or given_name)

    if is_person:
        display_name = f"{family_name}, {given_name}" if family_name and given_name else (family_name or given_name)
        entity_type = "person"
    elif full_name:
        display_name = full_name
        entity_type = "organisation" if role == "publisher" else "agent"
    else:
        return None

    agent: dict = {"name": display_name, "entity_type": entity_type}
    if is_person:
        if family_name:
            agent["family_name"] = family_name
        if given_name:
            agent["given_name"] = given_name
    if orcid:
        agent["identifiers"] = [{"value": orcid, "scheme": "orcid"}]
    if ra_id:
        agent["local_identifier"] = f"{entity_type}s/ra/{ra_id}"
    return agent


def _collect_contributors(rows: list[dict]) -> list[dict]:
    contributors_by_role_type: dict[str, dict[str, dict]] = {}
    next_map_by_role_type: dict[str, dict[str, str | None]] = {}

    for row in rows:
        role = row["contributor_role"]
        role_uri = row["contributor_role_uri"]
        if not role or not role_uri:
            continue

        if role not in contributors_by_role_type:
            contributors_by_role_type[role] = {}
            next_map_by_role_type[role] = {}

        if role_uri in contributors_by_role_type[role]:
            existing = contributors_by_role_type[role][role_uri]
            orcid = row["contributor_orcid"]
            if orcid and not existing["by"].get("identifiers"):
                existing["by"]["identifiers"] = [{"value": orcid, "scheme": "orcid"}]
            continue

        agent = _build_agent(row)
        if not agent:
            continue

        contributors_by_role_type[role][role_uri] = {"role": role, "by": agent}
        next_map_by_role_type[role][role_uri] = row["contributor_next_role_uri"] or None

    result = []
    for role_type in ["author", "editor", "publisher"]:
        if role_type not in contributors_by_role_type:
            continue
        ordered = _order_linked_list(contributors_by_role_type[role_type], next_map_by_role_type[role_type])
        for rank, contributor in enumerate(ordered, start=1):
            contributor["rank"] = rank
            result.append(contributor)

    return result


def _build_venue(rows: list[dict], venue_name: str, venue_br_id: str) -> dict:
    venue: dict = {"name": venue_name, "entity_type": "venue"}
    if venue_br_id:
        venue["local_identifier"] = f"venues/br/{venue_br_id}"

    venue_ids_seen = set()
    venue_identifiers = []
    for row in rows:
        venue_scheme = row["venue_id_scheme"]
        venue_value = row["venue_id_value"]
        if venue_scheme and venue_value and (venue_scheme, venue_value) not in venue_ids_seen:
            venue_ids_seen.add((venue_scheme, venue_value))
            venue_identifiers.append({"value": venue_value, "scheme": venue_scheme})
    if venue_identifiers:
        venue["identifiers"] = venue_identifiers
    return venue


def _normalize_datetime(date_str: str) -> str:
    parts = date_str.split("-")
    if len(parts) == 1:
        return f"{parts[0]}-01-01T00:00:00"
    if len(parts) == 2:
        return f"{parts[0]}-{parts[1]}-01T00:00:00"
    if "T" not in date_str:
        return f"{date_str}T00:00:00"
    return date_str


def _build_manifestation(rows: list[dict]) -> dict | None:
    first_row = rows[0]
    fabio_type = first_row["fabio_type"]
    pub_date = first_row["pub_date"]
    volume = first_row["volume"]
    issue = first_row["issue"]
    start_page = first_row["start_page"]
    end_page = first_row["end_page"]
    venue_name = first_row["venue_name"]
    venue_br_id = first_row["venue_br_id"]

    manifestation: dict = {}

    if fabio_type:
        manifestation_type: dict = {
            "class": fabio_type,
            "defined_in": "http://purl.org/spar/fabio",
        }
        label = FABIO_TYPE_LABELS.get(fabio_type)
        if label:
            manifestation_type["labels"] = {"en": label}
        manifestation["type"] = manifestation_type

    biblio: dict = {}
    if volume:
        biblio["volume"] = volume
    if issue:
        biblio["issue"] = issue
    if start_page and end_page:
        biblio["pages"] = {"first": start_page, "last": end_page}
    if venue_name:
        biblio["in"] = _build_venue(rows, venue_name, venue_br_id)
    if biblio:
        manifestation["biblio"] = biblio

    if pub_date:
        manifestation["dates"] = {"publication": [_normalize_datetime(pub_date)]}

    return manifestation or None


def _collect_citations(rows: list[dict]) -> list[str]:
    seen = set()
    citations = []
    for row in rows:
        cited = row["cited_br"]
        if cited and cited not in seen:
            seen.add(cited)
            citations.append(cited)
    return citations


SUPPORTED_PRODUCT_FILTERS = {
    "cf.cited_by",
    "cf.cited_by_doi",
    "cf.cites",
    "cf.cites_doi",
    "cf.contributions_orcid",
    "cf.search.title",
    "contributions.by.family_name",
    "contributions.by.given_name",
    "contributions.by.identifiers.id",
    "contributions.by.identifiers.scheme",
    "contributions.by.local_identifier",
    "contributions.by.name",
    "identifiers.id",
    "identifiers.scheme",
    "product_type",
}

UNSUPPORTED_PRODUCT_FILTERS = {
    "cf.contributions_aff_country",
    "cf.contributions_aff_ror",
    "cf.search.title_abstract",
    "contributions.declared_affiliations.identifiers.id",
    "contributions.declared_affiliations.identifiers.scheme",
    "contributions.declared_affiliations.local_identifier",
    "contributions.declared_affiliations.name",
    "contributions.declared_affiliations.short_name",
    "funding.grant_number",
    "funding.identifiers.id",
    "funding.identifiers.scheme",
    "funding.local_identifier",
}

ALL_VALID_PRODUCT_FILTERS = SUPPORTED_PRODUCT_FILTERS | UNSUPPORTED_PRODUCT_FILTERS


VALID_PRODUCT_TYPES = {"literature", "research data", "research software", "other"}


def _filter_product_type(value: str) -> list[str]:
    if value not in VALID_PRODUCT_TYPES:
        msg = f"The product type '{value}' is not valid, valid types are {', '.join(sorted(VALID_PRODUCT_TYPES))}"
        raise ValueError(msg)
    if value == "literature":
        return [f"FILTER NOT EXISTS {{ ?br_uri a <{fc}> }}" for fc in NON_LITERATURE_FABIO_CLASSES]
    if value in SKGIF_TO_FABIO_PRODUCT_TYPE:
        values_list = " ".join(f"<{fc}>" for fc in SKGIF_TO_FABIO_PRODUCT_TYPE[value])
        return [f"VALUES ?_filter_type {{ {values_list} }}\n?br_uri a ?_filter_type ."]
    return ["FILTER(false)"]


_AGENT_FILTER_TEMPLATES: dict[str, str] = {
    "contributions.by.identifiers.id": '?_filter_agent datacite:hasIdentifier [ literal:hasLiteralValue "{value}" ] .',
    "contributions.by.identifiers.scheme": "?_filter_agent datacite:hasIdentifier [ datacite:usesIdentifierScheme datacite:{value} ] .",
    "contributions.by.family_name": '?_filter_agent foaf:familyName "{value}" .',
    "contributions.by.given_name": '?_filter_agent foaf:givenName "{value}" .',
    "contributions.by.name": '?_filter_agent foaf:name "{value}" .',
    "cf.contributions_orcid": '?_filter_agent datacite:hasIdentifier [ literal:hasLiteralValue "{value}" ; datacite:usesIdentifierScheme datacite:orcid ] .',
}


_CITATION_CITO_PREFIX = "PREFIX cito: <http://purl.org/spar/cito/>"

_DOI_RESOLVE_PREFIX = (
    "PREFIX datacite: <http://purl.org/spar/datacite/>\n"
    "PREFIX literal: <http://www.essepuntato.it/2010/06/literalreification/>"
)


def _build_cites_preamble(target_uri: str) -> str:
    return (
        f"@@with source=index\n"
        f"{_CITATION_CITO_PREFIX}\n"
        f"SELECT ?br_uri WHERE {{\n"
        f"  ?_ci cito:hasCitingEntity ?_citing ;\n"
        f"       cito:hasCitedEntity <{target_uri}> .\n"
        f"  BIND(STR(?_citing) AS ?br_uri)\n"
        f"}}\n"
        f"@@join ?br_uri ?br_uri type=inner"
    )


def _build_cited_by_preamble(target_uri: str) -> str:
    return (
        f"@@with source=index\n"
        f"{_CITATION_CITO_PREFIX}\n"
        f"SELECT ?br_uri WHERE {{\n"
        f"  ?_ci cito:hasCitingEntity <{target_uri}> ;\n"
        f"       cito:hasCitedEntity ?_cited .\n"
        f"  BIND(STR(?_cited) AS ?br_uri)\n"
        f"}}\n"
        f"@@join ?br_uri ?br_uri type=inner"
    )


def _build_cites_doi_preamble(doi: str) -> str:
    return (
        f"{_DOI_RESOLVE_PREFIX}\n"
        f"SELECT ?_target WHERE {{\n"
        f"  ?_target datacite:hasIdentifier ?_id_node .\n"
        f"  ?_id_node datacite:usesIdentifierScheme datacite:doi ;\n"
        f'            literal:hasLiteralValue "{doi}" .\n'
        f"}}\n"
        f"@@values ?_target\n"
        f"@@join ?_target ?_target type=inner\n"
        f"@@with source=index\n"
        f"{_CITATION_CITO_PREFIX}\n"
        f"SELECT ?_target ?br_uri WHERE {{\n"
        f"  ?_ci cito:hasCitingEntity ?_citing ;\n"
        f"       cito:hasCitedEntity ?_target .\n"
        f"  BIND(STR(?_citing) AS ?br_uri)\n"
        f"}}\n"
        f"@@remove ?_target\n"
        f"@@join ?br_uri ?br_uri type=inner"
    )


def _build_cited_by_doi_preamble(doi: str) -> str:
    return (
        f"{_DOI_RESOLVE_PREFIX}\n"
        f"SELECT ?_target WHERE {{\n"
        f"  ?_target datacite:hasIdentifier ?_id_node .\n"
        f"  ?_id_node datacite:usesIdentifierScheme datacite:doi ;\n"
        f'            literal:hasLiteralValue "{doi}" .\n'
        f"}}\n"
        f"@@values ?_target\n"
        f"@@join ?_target ?_target type=inner\n"
        f"@@with source=index\n"
        f"{_CITATION_CITO_PREFIX}\n"
        f"SELECT ?_target ?br_uri WHERE {{\n"
        f"  ?_ci cito:hasCitingEntity ?_target ;\n"
        f"       cito:hasCitedEntity ?_cited .\n"
        f"  BIND(STR(?_cited) AS ?br_uri)\n"
        f"}}\n"
        f"@@remove ?_target\n"
        f"@@join ?br_uri ?br_uri type=inner"
    )


_CITATION_FILTER_BUILDERS: dict[str, Callable[[str], str]] = {
    "cf.cites": _build_cites_preamble,
    "cf.cited_by": _build_cited_by_preamble,
    "cf.cites_doi": _build_cites_doi_preamble,
    "cf.cited_by_doi": _build_cited_by_doi_preamble,
}


def _build_supported_product_filter(pairs: list[str]) -> dict[str, str]:
    clauses: list[str] = []
    agent_clauses: list[str] = []
    preamble_parts: list[str] = []

    for pair in pairs:
        key, value = pair.split(":", 1)

        if key in _CITATION_FILTER_BUILDERS:
            preamble_parts.append(_CITATION_FILTER_BUILDERS[key](value))
        elif key == "cf.search.title":
            clauses.append(f'FILTER(CONTAINS(LCASE(?title), LCASE("{value}")))')
        elif key == "identifiers.id":
            clauses.append(f'?br_uri datacite:hasIdentifier [ literal:hasLiteralValue "{value}" ] .')
        elif key == "identifiers.scheme":
            clauses.append(f"?br_uri datacite:hasIdentifier [ datacite:usesIdentifierScheme datacite:{value} ] .")
        elif key == "product_type":
            clauses.extend(_filter_product_type(value))
        elif key == "contributions.by.local_identifier":
            clauses.append(f"?br_uri pro:isDocumentContextFor [ pro:isHeldBy <{value}> ] .")
        elif key in _AGENT_FILTER_TEMPLATES:
            agent_clauses.append(_AGENT_FILTER_TEMPLATES[key].format(value=value))

    if agent_clauses:
        clauses.insert(0, "?br_uri pro:isDocumentContextFor [ pro:isHeldBy ?_filter_agent ] .")
        clauses.extend(agent_clauses)

    return {
        "filter_preamble": "\n".join(preamble_parts),
        "filter": "\n".join(clauses),
    }


def handle_skgif_product_filter(values: list[str]) -> dict[str, str]:
    raw = values[0]
    pairs = [pair.strip() for pair in raw.split(",") if pair.strip()]

    has_unsupported = False
    for pair in pairs:
        key, _ = pair.split(":", 1)
        if key not in ALL_VALID_PRODUCT_FILTERS:
            msg = f"The filter {key} is not supported, valid filters are {', '.join(sorted(ALL_VALID_PRODUCT_FILTERS))}"
            raise ValueError(msg)
        if key in UNSUPPORTED_PRODUCT_FILTERS:
            has_unsupported = True

    if has_unsupported:
        return {"filter_preamble": "", "filter": "FILTER(false)"}

    return _build_supported_product_filter(pairs)


def _build_search_result_page(url) -> dict:
    return {"local_identifier": url, "entity_type": "search_result_page"}


def _page_url(base_path, params, page):
    page_params = {**params, "page": [str(page)]}
    return f"{base_path}?{urlencode(page_params, doseq=True)}"


def _build_meta(request_url):
    parsed = urlsplit(request_url)
    params = parse_qs(parsed.query)
    if "total_items" not in params:
        return _build_search_result_page(request_url)
    total_items = int(params["total_items"][0])
    page = int(params["page"][0])
    page_size = int(params["page_size"][0])
    total_pages = ceil(total_items / page_size) if page_size > 0 else 0
    clean_params = {k: v for k, v in params.items() if k != "total_items"}
    self_url = f"{parsed.path}?{urlencode(clean_params, doseq=True)}"
    meta = _build_search_result_page(self_url)
    if page < total_pages:
        meta["next_page"] = _build_search_result_page(_page_url(parsed.path, clean_params, page + 1))
    if page > 1:
        meta["prev_page"] = _build_search_result_page(_page_url(parsed.path, clean_params, page - 1))
    base_params = {k: v for k, v in clean_params.items() if k not in ("page", "page_size")}
    base_url = f"{parsed.path}?{urlencode(base_params, doseq=True)}" if base_params else parsed.path
    meta["part_of"] = {
        "local_identifier": base_url,
        "entity_type": "search_result",
        "total_items": total_items,
        "first_page": _build_search_result_page(_page_url(parsed.path, clean_params, 1)),
        "last_page": _build_search_result_page(_page_url(parsed.path, clean_params, max(total_pages, 1))),
    }
    return meta


def _build_product_graph(rows):
    first_row = rows[0]
    product: dict = {
        "local_identifier": first_row["br_uri"],
        "entity_type": "product",
        "product_type": FABIO_TO_SKGIF_PRODUCT_TYPE.get(first_row["fabio_type"], "literature"),
    }
    if first_row["title"]:
        product["titles"] = {"none": [first_row["title"]]}
    identifiers = _collect_identifiers(rows)
    if identifiers:
        product["identifiers"] = identifiers
    contributions = _collect_contributors(rows)
    if contributions:
        product["contributions"] = contributions
    manifestation = _build_manifestation(rows)
    if manifestation:
        product["manifestations"] = [manifestation]
    citations = _collect_citations(rows)
    if citations:
        product["related_products"] = {"cites": citations}
    return [product]


def to_skgif(csv_str, request_url=""):
    rows = list(csv.DictReader(StringIO(csv_str)))
    if not rows:
        graph = []
    elif "fabio_type" in rows[0]:
        graph = _build_product_graph(rows)
    else:
        graph = [dict(row) for row in rows]
    result = {
        "@context": SKGIF_CONTEXT,
        "meta": _build_meta(request_url),
        "@graph": graph,
    }
    return json.dumps(result, ensure_ascii=False, indent=4)


VALID_GRANT_FILTERS = frozenset(
    {
        "acronym",
        "beneficiaries.country",
        "beneficiaries.identifiers.scheme",
        "beneficiaries.identifiers.value",
        "beneficiaries.name",
        "beneficiaries.short_name",
        "beneficiaries.website",
        "cf.duration.end.from",
        "cf.duration.start.from",
        "cf.duration.start.to",
        "cf.funded_amount.from",
        "cf.funded_amount.to",
        "cf.search.title",
        "cf.search.title_abstract",
        "contributions.by.family_name",
        "contributions.by.given_name",
        "contributions.by.identifiers.scheme",
        "contributions.by.identifiers.value",
        "contributions.by.local_identifier",
        "contributions.by.name",
        "contributions.declared_affiliations.country",
        "contributions.declared_affiliations.identifiers.scheme",
        "contributions.declared_affiliations.identifiers.value",
        "contributions.declared_affiliations.local_identifier",
        "contributions.declared_affiliations.name",
        "contributions.declared_affiliations.short_name",
        "contributions.declared_affiliations.website",
        "contributions.role",
        "currency",
        "funding_agency.country",
        "funding_agency.identifiers.scheme",
        "funding_agency.identifiers.value",
        "funding_agency.name",
        "funding_agency.short_name",
        "funding_agency.website",
        "funding_stream",
        "grant_number",
        "identifiers.scheme",
        "identifiers.value",
        "website",
    }
)

VALID_TOPIC_FILTERS = frozenset(
    {
        "cf.search.labels",
        "cf.search.language",
        "identifiers.scheme",
        "identifiers.value",
    }
)

VALID_DATASOURCE_FILTERS = frozenset(
    {
        "acronym",
        "cf.search.name",
        "data_source_classification",
        "identifiers.scheme",
        "identifiers.value",
        "research_product_type",
    }
)


def _make_mock_filter_handler(valid_filters: frozenset[str]):
    def handler(values: list[str]) -> dict[str, str]:
        raw = values[0]
        pairs = [pair.strip() for pair in raw.split(",") if pair.strip()]
        for pair in pairs:
            key, _ = pair.split(":", 1)
            if key not in valid_filters:
                msg = f"The filter {key} is not supported, valid filters are {', '.join(sorted(valid_filters))}"
                raise ValueError(msg)
        return {}

    return handler


handle_skgif_grant_filter = _make_mock_filter_handler(VALID_GRANT_FILTERS)
handle_skgif_topic_filter = _make_mock_filter_handler(VALID_TOPIC_FILTERS)
handle_skgif_datasource_filter = _make_mock_filter_handler(VALID_DATASOURCE_FILTERS)
