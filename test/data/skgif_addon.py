# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import csv
import json
from io import StringIO

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
        manifestation["dates"] = {"publication": [pub_date]}

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


def to_skgif(csv_str: str) -> str:
    rows = list(csv.DictReader(StringIO(csv_str)))
    if not rows:
        return json.dumps({"@context": SKGIF_CONTEXT, "@graph": []}, ensure_ascii=False, indent=4)

    first_row = rows[0]
    br_uri = first_row["br_uri"]
    title = first_row["title"]
    fabio_type = first_row["fabio_type"]

    product_type = FABIO_TO_SKGIF_PRODUCT_TYPE.get(fabio_type, "literature")

    product: dict = {
        "local_identifier": br_uri,
        "entity_type": "product",
        "product_type": product_type,
    }

    if title:
        product["titles"] = {"none": [title]}

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

    result = {"@context": SKGIF_CONTEXT, "@graph": [product]}
    return json.dumps(result, ensure_ascii=False, indent=4)
