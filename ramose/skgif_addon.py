# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import csv
import json
from collections.abc import Callable
from io import StringIO
from math import ceil
from urllib.parse import parse_qs, urlencode, urlsplit

from ramose import HttpError

SKGIF_CONTEXT = [
    "https://w3id.org/skg-if/context/1.1.0/skg-if.json",
    "https://w3id.org/skg-if/context/1.0.0/skg-if-api.json",
    {"@base": "https://w3id.org/skg-if/sandbox/"},
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


def _collect_identifiers(
    rows: list[dict], scheme_col: str = "identifier_scheme", value_col: str = "identifier_value"
) -> list[dict]:
    seen = set()
    identifiers = []
    for row in rows:
        scheme = row[scheme_col]
        value = row[value_col]
        if scheme and value and (scheme, value) not in seen:
            seen.add((scheme, value))
            identifiers.append({"value": value, "scheme": scheme})
    return identifiers


def _order_linked_list(items: dict[str, dict], next_map: dict[str, str | None]) -> list[dict]:
    if not items:
        return []

    next_values = set(next_map.values()) - {None}
    start_candidates = [key for key in items if key not in next_values]
    if not start_candidates:
        return list(items.values())

    ordered = []
    current = start_candidates[0]
    visited = set()
    while current and current in items and current not in visited:
        visited.add(current)
        ordered.append(items[current])
        current = next_map.get(current)

    for key, contributor in items.items():
        if key not in visited:
            ordered.append(contributor)

    return ordered


def _build_agent(row: dict) -> dict | None:
    family_name = row["contribution_by_family_name"]
    given_name = row["contribution_by_given_name"]
    full_name = row["contribution_by_name"]
    id_scheme = row["contribution_by_identifier_scheme"]
    id_value = row["contribution_by_identifier_value"]
    agent_local_id = row["contribution_by_local_identifier"]
    role = row["contribution_role"]

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
    if id_scheme and id_value:
        agent["identifiers"] = [{"value": id_value, "scheme": id_scheme}]
    if not agent_local_id:
        raise ValueError(f"Missing required local_identifier for {entity_type} '{display_name}'")
    agent["local_identifier"] = agent_local_id
    return agent


def _build_org(row: dict, prefix: str) -> dict:
    org: dict = {"entity_type": "organisation"}
    name = row[f"{prefix}_name"]
    if name:
        org["name"] = name
    for field in ("short_name", "country", "website"):
        val = row[f"{prefix}_{field}"]
        if val:
            org[field] = val
    local_id = row[f"{prefix}_local_identifier"]
    if not local_id:
        raise ValueError(f"Missing required local_identifier for organisation '{row[f'{prefix}_name']}'")
    org["local_identifier"] = local_id
    return org


def _merge_org_multivalued(entry: dict, row: dict, prefix: str) -> None:
    id_scheme = row[f"{prefix}_identifier_scheme"]
    id_value = row[f"{prefix}_identifier_value"]
    if id_scheme and id_value and (id_scheme, id_value) not in entry["seen_ids"]:
        entry["seen_ids"].add((id_scheme, id_value))
        entry["obj"].setdefault("identifiers", []).append({"value": id_value, "scheme": id_scheme})
    org_type = row[f"{prefix}_type"]
    if org_type and org_type not in entry["seen_types"]:
        entry["seen_types"].add(org_type)
        entry["obj"].setdefault("types", []).append(org_type)
    if f"{prefix}_other_name" in row:
        other_name = row[f"{prefix}_other_name"]
        if other_name and other_name not in entry["seen_other_names"]:
            entry["seen_other_names"].add(other_name)
            entry["obj"].setdefault("other_names", []).append(other_name)


def _collect_declared_affiliations(rows: list[dict], role: str, key: str, store: dict) -> None:
    prefix = "contribution_declared_affiliation"
    role_store = store.setdefault(role, {}).setdefault(key, {})
    for row in rows:
        if row["contribution_role"] != role or row["_contribution_key"] != key:
            continue
        aff_name = row[f"{prefix}_name"]
        aff_local_id = row[f"{prefix}_local_identifier"]
        if not aff_name and not aff_local_id:
            continue
        if aff_local_id not in role_store:
            role_store[aff_local_id] = {
                "obj": _build_org(row, prefix),
                "seen_ids": set(),
                "seen_types": set(),
                "seen_other_names": set(),
            }
        _merge_org_multivalued(role_store[aff_local_id], row, prefix)


def _enrich_contributor(
    contributor: dict, key: str, role_type: str, contribution_types: dict, affiliations: dict
) -> None:
    types = contribution_types.get(role_type, {}).get(key)
    if types:
        contributor["contribution_types"] = types
    affs = affiliations.get(role_type, {}).get(key)
    if affs:
        contributor["declared_affiliations"] = [entry["obj"] for entry in affs.values()]


def _collect_contributors(rows: list[dict]) -> list[dict]:
    contributors_by_role_type: dict[str, dict[str, dict]] = {}
    next_map_by_role_type: dict[str, dict[str, str | None]] = {}
    contribution_types: dict[str, dict[str, list[str]]] = {}
    affiliations_store: dict = {}

    for row in rows:
        role = row["contribution_role"]
        key = row["_contribution_key"]
        if not role or not key:
            continue

        if role not in contributors_by_role_type:
            contributors_by_role_type[role] = {}
            next_map_by_role_type[role] = {}
            contribution_types[role] = {}

        contribution_type = row["contribution_type"]
        if contribution_type:
            type_list = contribution_types[role].setdefault(key, [])
            if contribution_type not in type_list:
                type_list.append(contribution_type)

        if key in contributors_by_role_type[role]:
            existing = contributors_by_role_type[role][key]
            id_scheme = row["contribution_by_identifier_scheme"]
            id_value = row["contribution_by_identifier_value"]
            if id_scheme and id_value and not existing["by"].get("identifiers"):
                existing["by"]["identifiers"] = [{"value": id_value, "scheme": id_scheme}]
            continue

        _collect_declared_affiliations(rows, role, key, affiliations_store)
        agent = _build_agent(row)
        if not agent:
            continue
        contributors_by_role_type[role][key] = {"role": role, "by": agent}
        next_map_by_role_type[role][key] = row["_contribution_next_key"] or None

    result = []
    for role_type in ["author", "editor", "publisher"]:
        if role_type not in contributors_by_role_type:
            continue
        ordered = _order_linked_list(contributors_by_role_type[role_type], next_map_by_role_type[role_type])
        for rank, contributor in enumerate(ordered, start=1):
            contributor["rank"] = rank
            key = next(k for k, v in contributors_by_role_type[role_type].items() if v is contributor)
            _enrich_contributor(contributor, key, role_type, contribution_types, affiliations_store)
            result.append(contributor)

    return result


def _build_venue(rows: list[dict], venue_name: str, venue_local_id: str) -> dict:
    venue: dict = {"name": venue_name, "entity_type": "venue"}
    if not venue_local_id:
        raise ValueError(f"Missing required local_identifier for venue '{venue_name}'")
    venue["local_identifier"] = venue_local_id
    acronym = rows[0]["manifestation_biblio_in_acronym"]
    if acronym:
        venue["acronym"] = acronym

    venue_ids_seen = set()
    venue_identifiers = []
    for row in rows:
        venue_scheme = row["manifestation_biblio_in_identifier_scheme"]
        venue_value = row["manifestation_biblio_in_identifier_value"]
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


def _collect_manifestation_dates(rows: list[dict]) -> dict[str, list[str]]:
    dates: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        date_type = row["manifestation_dates_type"]
        date_value = row["manifestation_dates_value"]
        if date_type and date_value and (date_type, date_value) not in seen:
            seen.add((date_type, date_value))
            dates.setdefault(date_type, []).append(_normalize_datetime(date_value))
    return dates


def _build_biblio(rows: list[dict]) -> dict:
    first_row = rows[0]
    biblio: dict = {}
    volume = first_row["manifestation_biblio_volume"]
    if volume:
        biblio["volume"] = volume
    issue = first_row["manifestation_biblio_issue"]
    if issue:
        biblio["issue"] = issue
    edition = first_row["manifestation_biblio_edition"]
    if edition:
        biblio["edition"] = edition
    number = first_row["manifestation_biblio_number"]
    if number:
        biblio["number"] = number
    first_page = first_row["manifestation_biblio_pages_first"]
    last_page = first_row["manifestation_biblio_pages_last"]
    if first_page and last_page:
        biblio["pages"] = {"first": first_page, "last": last_page}
    venue_name = first_row["manifestation_biblio_in_name"]
    if venue_name:
        venue_local_id = first_row["manifestation_biblio_in_local_identifier"]
        biblio["in"] = _build_venue(rows, venue_name, venue_local_id)
    hosting_local_id = first_row["manifestation_biblio_hosting_data_source_local_identifier"]
    if hosting_local_id:
        hosting: dict = {"local_identifier": hosting_local_id, "entity_type": "datasource"}
        hosting_name = first_row["manifestation_biblio_hosting_data_source_name"]
        if hosting_name:
            hosting["name"] = hosting_name
        hosting_ids_seen: set[tuple[str, str]] = set()
        hosting_identifiers: list[dict] = []
        for row in rows:
            hosting_scheme = row["manifestation_biblio_hosting_data_source_identifier_scheme"]
            hosting_value = row["manifestation_biblio_hosting_data_source_identifier_value"]
            if hosting_scheme and hosting_value and (hosting_scheme, hosting_value) not in hosting_ids_seen:
                hosting_ids_seen.add((hosting_scheme, hosting_value))
                hosting_identifiers.append({"value": hosting_value, "scheme": hosting_scheme})
        if hosting_identifiers:
            hosting["identifiers"] = hosting_identifiers
        biblio["hosting_data_source"] = hosting
    return biblio


def _build_manifestation(rows: list[dict]) -> dict | None:
    first_row = rows[0]
    manifestation: dict = {}

    type_class = first_row["manifestation_type_class"]
    if type_class:
        separator = "#" if "#" in type_class else "/"
        defined_in = type_class.rsplit(separator, 1)[0]
        manifestation_type: dict = {"class": type_class, "defined_in": defined_in}
        type_label = first_row["manifestation_type_label"]
        if type_label:
            label_lang = first_row["manifestation_type_label_lang"] or "none"
            manifestation_type["labels"] = {label_lang: type_label}
        manifestation["type"] = manifestation_type

    dates = _collect_manifestation_dates(rows)
    if dates:
        manifestation["dates"] = dates

    identifiers = _collect_identifiers(rows, "manifestation_identifier_scheme", "manifestation_identifier_value")
    if identifiers:
        manifestation["identifiers"] = identifiers

    peer_review_status = first_row["manifestation_peer_review_status"]
    if peer_review_status:
        peer_review: dict = {"status": peer_review_status}
        peer_review_desc = first_row["manifestation_peer_review_description"]
        if peer_review_desc:
            peer_review["description"] = peer_review_desc
        manifestation["peer_review"] = peer_review

    access_status = first_row["manifestation_access_rights_status"]
    if access_status:
        access_rights: dict = {"status": access_status}
        access_desc = first_row["manifestation_access_rights_description"]
        if access_desc:
            access_rights["description"] = access_desc
        manifestation["access_rights"] = access_rights

    licence = first_row["manifestation_licence"]
    if licence:
        manifestation["licence"] = licence

    version = first_row["manifestation_version"]
    if version:
        manifestation["version"] = version

    biblio = _build_biblio(rows)
    if biblio:
        manifestation["biblio"] = biblio

    return manifestation or None


_RELATED_PRODUCT_COLUMNS = [
    "related_products_cites",
    "related_products_is_supplemented_by",
    "related_products_is_documented_by",
    "related_products_is_new_version_of",
    "related_products_is_part_of",
]


def _collect_related_products(rows: list[dict]) -> dict:
    result: dict[str, list[str]] = {}
    for column in _RELATED_PRODUCT_COLUMNS:
        key = column.replace("related_products_", "")
        seen: set[str] = set()
        values: list[str] = []
        for row in rows:
            val = row[column]
            if val and val not in seen:
                seen.add(val)
                values.append(val)
        if values:
            result[key] = values
    return result


def _collect_topics(rows: list[dict]) -> list[dict]:
    topics_by_uri: dict[str, dict] = {}
    seen_identifiers: dict[str, set] = {}
    seen_provenance: dict[str, set] = {}

    for row in rows:
        uri = row["topic_term"]
        if not uri:
            continue

        if uri not in topics_by_uri:
            topics_by_uri[uri] = {"term": {"local_identifier": uri, "entity_type": "topic"}}
            seen_identifiers[uri] = set()
            seen_provenance[uri] = set()

        topic = topics_by_uri[uri]
        term = topic["term"]

        label = row["topic_label"]
        if label:
            lang = row["topic_label_lang"] or "none"
            term.setdefault("labels", {})[lang] = label

        id_scheme = row["topic_identifier_scheme"]
        id_value = row["topic_identifier_value"]
        if id_scheme and id_value and (id_scheme, id_value) not in seen_identifiers[uri]:
            seen_identifiers[uri].add((id_scheme, id_value))
            term.setdefault("identifiers", []).append({"scheme": id_scheme, "value": id_value})

        prov_agent = row["topic_provenance_associated_with"]
        prov_trust = row["topic_provenance_trust"]
        if prov_agent and prov_trust and prov_agent not in seen_provenance[uri]:
            seen_provenance[uri].add(prov_agent)
            topic.setdefault("provenance", []).append({"associated_with": prov_agent, "trust": float(prov_trust)})

    return list(topics_by_uri.values())


def _collect_organisation(rows: list[dict], prefix: str) -> list[dict]:
    entries: dict[str, dict] = {}
    for row in rows:
        name = row[f"{prefix}_name"]
        local_id = row[f"{prefix}_local_identifier"]
        if not name and not local_id:
            continue
        if local_id not in entries:
            entries[local_id] = {
                "obj": _build_org(row, prefix),
                "seen_ids": set(),
                "seen_types": set(),
                "seen_other_names": set(),
            }
        _merge_org_multivalued(entries[local_id], row, prefix)
    return [entry["obj"] for entry in entries.values()]


def _build_grant(row: dict) -> dict:
    funding_local_id = row["funding_local_identifier"]
    if not funding_local_id:
        raise ValueError("Missing required local_identifier for grant")
    grant: dict = {"local_identifier": funding_local_id, "entity_type": "grant"}
    for field, csv_col in (
        ("grant_number", "funding_grant_number"),
        ("acronym", "funding_acronym"),
        ("funding_stream", "funding_stream"),
    ):
        val = row[csv_col]
        if val:
            grant[field] = val
    title = row["funding_title"]
    if title:
        grant["titles"] = {row["funding_title_lang"] or "none": title}
    abstract = row["funding_abstract"]
    if abstract:
        grant["abstracts"] = {row["funding_abstract_lang"] or "none": abstract}
    agency_name = row["funding_agency_name"]
    if agency_name:
        grant["funding_agency"] = _build_org(row, "funding_agency")
    return grant


def _collect_funding(rows: list[dict]) -> list[dict]:
    funding_by_key: dict[str, dict] = {}
    seen_ids: dict[str, set[tuple[str, str]]] = {}
    agency_trackers: dict[str, dict] = {}

    for row in rows:
        local_id = row["funding_local_identifier"]
        if not local_id:
            continue
        if local_id not in funding_by_key:
            funding_by_key[local_id] = _build_grant(row)
            seen_ids[local_id] = set()
            agency_trackers[local_id] = {"seen_ids": set(), "seen_types": set()}

        id_scheme = row["funding_identifier_scheme"]
        id_value = row["funding_identifier_value"]
        if id_scheme and id_value and (id_scheme, id_value) not in seen_ids[local_id]:
            seen_ids[local_id].add((id_scheme, id_value))
            funding_by_key[local_id].setdefault("identifiers", []).append({"value": id_value, "scheme": id_scheme})

        if "funding_agency" not in funding_by_key[local_id]:
            continue
        tracker = agency_trackers[local_id]
        agency = funding_by_key[local_id]["funding_agency"]
        a_scheme = row["funding_agency_identifier_scheme"]
        a_value = row["funding_agency_identifier_value"]
        if a_scheme and a_value and (a_scheme, a_value) not in tracker["seen_ids"]:
            tracker["seen_ids"].add((a_scheme, a_value))
            agency.setdefault("identifiers", []).append({"value": a_value, "scheme": a_scheme})
        a_type = row["funding_agency_type"]
        if a_type and a_type not in tracker["seen_types"]:
            tracker["seen_types"].add(a_type)
            agency.setdefault("types", []).append(a_type)

    return list(funding_by_key.values())


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
        return [f"FILTER NOT EXISTS {{ ?local_identifier a <{fc}> }}" for fc in NON_LITERATURE_FABIO_CLASSES]
    if value in SKGIF_TO_FABIO_PRODUCT_TYPE:
        values_list = " ".join(f"<{fc}>" for fc in SKGIF_TO_FABIO_PRODUCT_TYPE[value])
        return [f"VALUES ?_filter_type {{ {values_list} }}\n?local_identifier a ?_filter_type ."]
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
        f"SELECT ?local_identifier WHERE {{\n"
        f"  ?_ci cito:hasCitingEntity ?_citing ;\n"
        f"       cito:hasCitedEntity <{target_uri}> .\n"
        f"  BIND(STR(?_citing) AS ?local_identifier)\n"
        f"}}\n"
        f"@@join ?local_identifier ?local_identifier type=inner"
    )


def _build_cited_by_preamble(target_uri: str) -> str:
    return (
        f"@@with source=index\n"
        f"{_CITATION_CITO_PREFIX}\n"
        f"SELECT ?local_identifier WHERE {{\n"
        f"  ?_ci cito:hasCitingEntity <{target_uri}> ;\n"
        f"       cito:hasCitedEntity ?_cited .\n"
        f"  BIND(STR(?_cited) AS ?local_identifier)\n"
        f"}}\n"
        f"@@join ?local_identifier ?local_identifier type=inner"
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
        f"SELECT ?_target ?local_identifier WHERE {{\n"
        f"  ?_ci cito:hasCitingEntity ?_citing ;\n"
        f"       cito:hasCitedEntity ?_target .\n"
        f"  BIND(STR(?_citing) AS ?local_identifier)\n"
        f"}}\n"
        f"@@remove ?_target\n"
        f"@@join ?local_identifier ?local_identifier type=inner"
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
        f"SELECT ?_target ?local_identifier WHERE {{\n"
        f"  ?_ci cito:hasCitingEntity ?_target ;\n"
        f"       cito:hasCitedEntity ?_cited .\n"
        f"  BIND(STR(?_cited) AS ?local_identifier)\n"
        f"}}\n"
        f"@@remove ?_target\n"
        f"@@join ?local_identifier ?local_identifier type=inner"
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
            clauses.append(f'?local_identifier datacite:hasIdentifier [ literal:hasLiteralValue "{value}" ] .')
        elif key == "identifiers.scheme":
            clauses.append(
                f"?local_identifier datacite:hasIdentifier [ datacite:usesIdentifierScheme datacite:{value} ] ."
            )
        elif key == "product_type":
            clauses.extend(_filter_product_type(value))
        elif key == "contributions.by.local_identifier":
            clauses.append(f"?local_identifier pro:isDocumentContextFor [ pro:isHeldBy <{value}> ] .")
        elif key in _AGENT_FILTER_TEMPLATES:
            agent_clauses.append(_AGENT_FILTER_TEMPLATES[key].format(value=value))

    if agent_clauses:
        clauses.insert(0, "?local_identifier pro:isDocumentContextFor [ pro:isHeldBy ?_filter_agent ] .")
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


def _build_meta(request_url, graph_size):
    parsed = urlsplit(request_url)
    params = parse_qs(parsed.query)
    if "total_items" in params:
        total_items = int(params["total_items"][0])
        page = int(params["page"][0])
        page_size = int(params["page_size"][0])
    elif "page_size" in params:
        total_items = graph_size
        page = int(params.get("page", ["1"])[0])
        page_size = int(params["page_size"][0])
    else:
        total_items = graph_size
        page = 1
        page_size = max(graph_size, 1)
    total_pages = ceil(total_items / page_size) if page_size > 0 else 0
    non_pagination_params = {k: v for k, v in params.items() if k not in ("page", "page_size", "total_items")}
    clean_params = {**non_pagination_params, "page": [str(page)], "page_size": [str(page_size)]}
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


_BUILDER_COLUMN_PREFIXES = (
    "identifier_",
    "contribution_",
    "manifestation_",
    "related_products_",
    "topic_",
    "funding_",
    "relevant_organisation_",
)


def _collect_passthrough_fields(first_row: dict, active_formatted: set[str]) -> dict:
    entity: dict = {}
    for col, val in first_row.items():
        if col.startswith("_") or col in active_formatted:
            continue
        if any(col.startswith(prefix) for prefix in _BUILDER_COLUMN_PREFIXES):
            continue
        if val:
            entity[col] = val
    return entity


def _add_formatted_text(entity: dict, first_row: dict, field: str, lang_field: str, output_key: str) -> None:
    if field not in first_row:
        return
    if first_row[field]:
        lang = first_row.get(lang_field) or "none"
        entity[output_key] = {lang: [first_row[field]]}
    else:
        entity[output_key] = {}


def _build_entity(rows: list[dict]) -> dict:
    first_row = rows[0]
    columns = set(first_row)

    active_formatted: set[str] = set()
    if "title" in columns:
        active_formatted.update(("title", "title_lang"))
    if "abstract" in columns:
        active_formatted.update(("abstract", "abstract_lang"))

    entity = _collect_passthrough_fields(first_row, active_formatted)
    _add_formatted_text(entity, first_row, "title", "title_lang", "titles")
    _add_formatted_text(entity, first_row, "abstract", "abstract_lang", "abstracts")

    if "identifier_scheme" in columns:
        entity["identifiers"] = _collect_identifiers(rows)
    if "contribution_role" in columns:
        entity["contributions"] = _collect_contributors(rows)
    if "manifestation_type_class" in columns:
        manifestation = _build_manifestation(rows)
        entity["manifestations"] = [manifestation] if manifestation else []
    if columns & set(_RELATED_PRODUCT_COLUMNS):
        entity["related_products"] = _collect_related_products(rows)
    if "topic_term" in columns:
        entity["topics"] = _collect_topics(rows)
    if "funding_local_identifier" in columns:
        entity["funding"] = _collect_funding(rows)
    if "relevant_organisation_name" in columns:
        entity["relevant_organisations"] = _collect_organisation(rows, "relevant_organisation")

    return entity


def _build_entities(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["local_identifier"], []).append(row)
    return [_build_entity(group) for group in groups.values()]


ENTITY_TYPES = frozenset({"products", "persons", "organisations", "grants", "venues", "topics", "datasources"})


def _is_single_entity_request(request_url):
    segments = [s for s in urlsplit(request_url).path.split("/") if s]
    for i, segment in enumerate(segments):
        if segment in ENTITY_TYPES:
            return i + 1 < len(segments)
    return False


def to_skgif(csv_str, request_url=""):
    rows = list(csv.DictReader(StringIO(csv_str)))
    if not rows and _is_single_entity_request(request_url):
        raise HttpError(404, "HTTP status code 404: entity not found")
    graph = _build_entities(rows)

    total_entities = len(graph)

    parsed = urlsplit(request_url)
    params = parse_qs(parsed.query)
    if "page_size" in params:
        page_size = int(params["page_size"][0])
        page = int(params.get("page", ["1"])[0])
        total_pages = ceil(total_entities / page_size) if page_size > 0 else 0
        if total_pages > 0 and page > total_pages:
            msg = f"page {page} exceeds total pages {total_pages}"
            raise ValueError(msg)
        start = (page - 1) * page_size
        graph = graph[start : start + page_size]

    result = {
        "@context": SKGIF_CONTEXT,
        "meta": _build_meta(request_url, total_entities),
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
