# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import csv
import json
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from io import StringIO
from math import ceil
from re import sub
from typing import NoReturn
from urllib.parse import parse_qs, urlencode, urlsplit

from ramose import HttpError

_YEAR_MONTH_PART_COUNT = 2
_UNPROCESSABLE_CONTENT = 422

_PRODUCT_COLUMNS: dict[str, str] = dict.fromkeys(
    (
        "local_identifier",
        "identifier_scheme",
        "identifier_value",
        "title",
        "title_lang",
        "abstract",
        "abstract_lang",
        "product_type",
        "affiliation_name",
        "affiliation_short_name",
        "affiliation_country",
        "affiliation_local_identifier",
        "affiliation_identifier_scheme",
        "affiliation_identifier_value",
        "affiliation_type",
        "affiliation_website",
        "affiliation_other_name",
        "affiliation_role",
        "affiliation_period_start",
        "affiliation_period_end",
        "_affiliation_key",
        "topic_term",
        "topic_identifier_scheme",
        "topic_identifier_value",
        "topic_label",
        "topic_label_lang",
        "topic_provenance_associated_with",
        "topic_provenance_trust",
        "contribution_by_family_name",
        "contribution_by_given_name",
        "contribution_by_name",
        "contribution_by_identifier_scheme",
        "contribution_by_identifier_value",
        "contribution_by_local_identifier",
        "contribution_role",
        "contribution_type",
        "_contribution_key",
        "_contribution_next_key",
        "contribution_declared_affiliation_name",
        "contribution_declared_affiliation_short_name",
        "contribution_declared_affiliation_country",
        "contribution_declared_affiliation_local_identifier",
        "contribution_declared_affiliation_identifier_scheme",
        "contribution_declared_affiliation_identifier_value",
        "contribution_declared_affiliation_type",
        "contribution_declared_affiliation_website",
        "contribution_declared_affiliation_other_name",
        "manifestation_type_class",
        "manifestation_type_label",
        "manifestation_type_label_lang",
        "manifestation_type_defined_in",
        "_manifestation_key",
        "manifestation_identifier_scheme",
        "manifestation_identifier_value",
        "manifestation_dates_type",
        "manifestation_dates_value",
        "manifestation_peer_review_status",
        "manifestation_peer_review_description",
        "manifestation_access_rights_status",
        "manifestation_access_rights_description",
        "manifestation_licence",
        "manifestation_version",
        "manifestation_biblio_volume",
        "manifestation_biblio_issue",
        "manifestation_biblio_edition",
        "manifestation_biblio_number",
        "manifestation_biblio_pages_first",
        "manifestation_biblio_pages_last",
        "manifestation_biblio_in_name",
        "manifestation_biblio_in_local_identifier",
        "manifestation_biblio_in_identifier_scheme",
        "manifestation_biblio_in_identifier_value",
        "manifestation_biblio_in_acronym",
        "manifestation_biblio_hosting_data_source_local_identifier",
        "manifestation_biblio_hosting_data_source_name",
        "manifestation_biblio_hosting_data_source_identifier_scheme",
        "manifestation_biblio_hosting_data_source_identifier_value",
        "related_products_cites",
        "related_products_is_supplemented_by",
        "related_products_is_documented_by",
        "related_products_is_new_version_of",
        "related_products_is_part_of",
        "funding_local_identifier",
        "funding_grant_number",
        "funding_title",
        "funding_title_lang",
        "funding_abstract",
        "funding_abstract_lang",
        "funding_acronym",
        "funding_identifier_scheme",
        "funding_identifier_value",
        "funding_stream",
        "funding_agency_name",
        "funding_agency_short_name",
        "funding_agency_country",
        "funding_agency_local_identifier",
        "funding_agency_identifier_scheme",
        "funding_agency_identifier_value",
        "funding_agency_type",
        "funding_agency_website",
        "beneficiaries_name",
        "beneficiaries_short_name",
        "beneficiaries_country",
        "beneficiaries_local_identifier",
        "beneficiaries_identifier_scheme",
        "beneficiaries_identifier_value",
        "beneficiaries_type",
        "beneficiaries_website",
        "relevant_organisation_name",
        "relevant_organisation_short_name",
        "relevant_organisation_country",
        "relevant_organisation_local_identifier",
        "relevant_organisation_identifier_scheme",
        "relevant_organisation_identifier_value",
        "relevant_organisation_type",
        "relevant_organisation_website",
        "relevant_organisation_other_name",
        "research_product_types",
        "persistent_identity_system_for",
        "persistent_identity_system_pid_scheme",
        "_persistent_identity_system_key",
        "audience_type",
        "disciplines",
        "policy_about",
        "policy_target",
        "policy_documented_at",
        "policy_description",
        "_policy_key",
    ),
    "",
)

SKGIF_CONTEXT_URLS = [
    "https://w3id.org/skg-if/context/1.1.0/skg-if.json",
    "https://w3id.org/skg-if/context/1.0.0/skg-if-api.json",
]


def _build_context(base_url: str) -> list:
    return [*SKGIF_CONTEXT_URLS, {"@base": f"{base_url.rstrip('/')}/"}]


def _collect_identifiers(
    rows: list[dict],
    scheme_col: str = "identifier_scheme",
    value_col: str = "identifier_value",
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


def _merge_agent_identifier(agent: dict, row: dict) -> None:
    scheme = row["contribution_by_identifier_scheme"]
    value = row["contribution_by_identifier_value"]
    if not scheme or not value:
        return
    identifier = {"value": value, "scheme": scheme}
    identifiers = agent.setdefault("identifiers", [])
    if identifier not in identifiers:
        identifiers.append(identifier)


def _build_agent(row: dict, non_person_entity_type: str) -> dict | None:
    family_name = row["contribution_by_family_name"]
    given_name = row["contribution_by_given_name"]
    full_name = row["contribution_by_name"]
    agent_local_id = row["contribution_by_local_identifier"]

    is_person = bool(family_name or given_name)

    if is_person:
        display_name = f"{family_name}, {given_name}" if family_name and given_name else (family_name or given_name)
        entity_type = "person"
    elif full_name:
        display_name = full_name
        entity_type = non_person_entity_type
    else:
        return None

    agent: dict = {"name": display_name, "entity_type": entity_type}
    if is_person:
        if family_name:
            agent["family_name"] = family_name
        if given_name:
            agent["given_name"] = given_name
    _merge_agent_identifier(agent, row)
    if not agent_local_id:
        msg = f"Missing required local_identifier for {entity_type} '{display_name}'"
        raise ValueError(msg)
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
        msg = f"Missing required local_identifier for organisation '{row[f'{prefix}_name']}'"
        raise ValueError(msg)
    org["local_identifier"] = local_id
    return org


def _org_entry(row: dict, prefix: str) -> dict:
    return {"obj": _build_org(row, prefix), "seen_ids": set(), "seen_types": set(), "seen_other_names": set()}


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


_DECLARED_AFFILIATION_PREFIX = "contribution_declared_affiliation"


def _merge_declared_affiliation(store: dict, row: dict) -> None:
    prefix = _DECLARED_AFFILIATION_PREFIX
    aff_name = row[f"{prefix}_name"]
    aff_local_id = row[f"{prefix}_local_identifier"]
    if not aff_name and not aff_local_id:
        return
    if aff_local_id not in store:
        store[aff_local_id] = _org_entry(row, prefix)
    _merge_org_multivalued(store[aff_local_id], row, prefix)


def _collect_declared_affiliations(rows: list[dict], role: str, key: str, store: dict) -> None:
    role_store = store.setdefault(role, {}).setdefault(key, {})
    for row in rows:
        if row["contribution_role"] == role and row["_contribution_key"] == key:
            _merge_declared_affiliation(role_store, row)


def _enrich_contributor(
    contributor: dict,
    key: str,
    role_type: str,
    contribution_types: dict,
    affiliations: dict,
) -> None:
    types = contribution_types.get(role_type, {}).get(key)
    if types:
        contributor["contribution_types"] = types
    affs = affiliations.get(role_type, {}).get(key)
    if affs:
        contributor["declared_affiliations"] = [entry["obj"] for entry in affs.values()]


@dataclass
class _ContributorAccumulator:
    by_role_type: dict[str, dict[str, dict]] = dataclass_field(default_factory=dict)
    next_map: dict[str, dict[str, str | None]] = dataclass_field(default_factory=dict)
    types: dict[str, dict[str, list[str]]] = dataclass_field(default_factory=dict)
    affiliations: dict[str, dict[str, dict]] = dataclass_field(default_factory=dict)


def _process_contributor_row(
    row: dict,
    rows: list[dict],
    acc: _ContributorAccumulator,
) -> None:
    role = row["contribution_role"]
    key = row["_contribution_key"]
    if not role or not key:
        return

    if role not in acc.by_role_type:
        acc.by_role_type[role] = {}
        acc.next_map[role] = {}
        acc.types[role] = {}

    contribution_type = row["contribution_type"]
    if contribution_type:
        type_list = acc.types[role].setdefault(key, [])
        if contribution_type not in type_list:
            type_list.append(contribution_type)

    if key in acc.by_role_type[role]:
        existing = acc.by_role_type[role][key]
        _merge_agent_identifier(existing["by"], row)
        return

    _collect_declared_affiliations(rows, role, key, acc.affiliations)
    agent = _build_agent(row, "organisation" if role == "publisher" else "agent")
    if not agent:
        return
    acc.by_role_type[role][key] = {"role": role, "by": agent}
    acc.next_map[role][key] = row["_contribution_next_key"] or None


def _collect_contributors(rows: list[dict]) -> list[dict]:
    acc = _ContributorAccumulator()

    for row in rows:
        _process_contributor_row(row, rows, acc)

    result = []
    for role_type in ["author", "editor", "publisher"]:
        if role_type not in acc.by_role_type:
            continue
        ordered = _order_linked_list(acc.by_role_type[role_type], acc.next_map[role_type])
        for rank, contributor in enumerate(ordered, start=1):
            contributor["rank"] = rank
            key = next(k for k, v in acc.by_role_type[role_type].items() if v is contributor)
            _enrich_contributor(contributor, key, role_type, acc.types, acc.affiliations)
            result.append(contributor)

    return result


def _collect_grouped_contributors(rows: list[dict]) -> list[dict]:
    contributions: dict[str, dict] = {}
    affiliations: dict[str, dict] = {}

    for row in rows:
        key = row["_contribution_key"]
        if not key:
            continue
        if key not in contributions:
            agent = _build_agent(row, "organisation")
            if not agent:
                continue
            contributions[key] = {"by": agent, "roles": []}
            affiliations[key] = {}
        role = row["contribution_role"]
        if role and role not in contributions[key]["roles"]:
            contributions[key]["roles"].append(role)
        _merge_agent_identifier(contributions[key]["by"], row)
        _merge_declared_affiliation(affiliations[key], row)

    for key, contribution in contributions.items():
        if not contribution["roles"]:
            del contribution["roles"]
        if affiliations[key]:
            contribution["declared_affiliations"] = [entry["obj"] for entry in affiliations[key].values()]
    return list(contributions.values())


def _build_venue(rows: list[dict], venue_name: str, venue_local_id: str) -> dict:
    venue: dict = {"name": venue_name, "entity_type": "venue"}
    if not venue_local_id:
        msg = f"Missing required local_identifier for venue '{venue_name}'"
        raise ValueError(msg)
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
    if len(parts) == _YEAR_MONTH_PART_COUNT:
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


_BIBLIO_SIMPLE_FIELDS: tuple[tuple[str, str], ...] = (
    ("manifestation_biblio_volume", "volume"),
    ("manifestation_biblio_issue", "issue"),
    ("manifestation_biblio_edition", "edition"),
    ("manifestation_biblio_number", "number"),
)


def _build_biblio_venue(rows: list[dict], first_row: dict) -> dict | None:
    venue_name = first_row["manifestation_biblio_in_name"]
    if not venue_name:
        return None
    venue_local_id = first_row["manifestation_biblio_in_local_identifier"]
    return _build_venue(rows, venue_name, venue_local_id)


def _build_biblio_hosting(rows: list[dict], first_row: dict) -> dict | None:
    hosting_local_id = first_row["manifestation_biblio_hosting_data_source_local_identifier"]
    if not hosting_local_id:
        return None
    hosting: dict = {"local_identifier": hosting_local_id, "entity_type": "datasource"}
    hosting_name = first_row["manifestation_biblio_hosting_data_source_name"]
    if hosting_name:
        hosting["name"] = hosting_name
    hosting_identifiers = _collect_identifiers(
        rows,
        "manifestation_biblio_hosting_data_source_identifier_scheme",
        "manifestation_biblio_hosting_data_source_identifier_value",
    )
    if hosting_identifiers:
        hosting["identifiers"] = hosting_identifiers
    return hosting


def _build_biblio(rows: list[dict]) -> dict:
    first_row = rows[0]
    biblio: dict = {}
    for sparql_var, json_key in _BIBLIO_SIMPLE_FIELDS:
        value = first_row[sparql_var]
        if value:
            biblio[json_key] = value
    first_page = first_row["manifestation_biblio_pages_first"]
    last_page = first_row["manifestation_biblio_pages_last"]
    if first_page and last_page:
        biblio["pages"] = {"first": first_page, "last": last_page}
    venue = _build_biblio_venue(rows, first_row)
    if venue:
        biblio["in"] = venue
    hosting = _build_biblio_hosting(rows, first_row)
    if hosting:
        biblio["hosting_data_source"] = hosting
    return biblio


def _build_manifestation_type(first_row: dict) -> dict | None:
    type_class = first_row["manifestation_type_class"]
    type_label = first_row["manifestation_type_label"]
    defined_in = first_row["manifestation_type_defined_in"]
    if not type_class and not type_label and not defined_in:
        return None
    manifestation_type: dict = {}
    if type_class:
        manifestation_type["class"] = type_class
    if type_label:
        label_lang = first_row["manifestation_type_label_lang"] or "none"
        manifestation_type["labels"] = {label_lang: type_label}
    if defined_in:
        manifestation_type["defined_in"] = defined_in
    return manifestation_type


def _build_status_with_description(first_row: dict, status_field: str, desc_field: str) -> dict | None:
    status = first_row[status_field]
    if not status:
        return None
    result: dict = {"status": status}
    desc = first_row[desc_field]
    if desc:
        result["description"] = desc
    return result


def _build_manifestation(rows: list[dict]) -> dict | None:
    first_row = rows[0]
    manifestation: dict = {}

    manifestation_type = _build_manifestation_type(first_row)
    if manifestation_type:
        manifestation["type"] = manifestation_type

    dates = _collect_manifestation_dates(rows)
    if dates:
        manifestation["dates"] = dates

    identifiers = _collect_identifiers(rows, "manifestation_identifier_scheme", "manifestation_identifier_value")
    if identifiers:
        manifestation["identifiers"] = identifiers

    peer_review = _build_status_with_description(
        first_row, "manifestation_peer_review_status", "manifestation_peer_review_description"
    )
    if peer_review:
        manifestation["peer_review"] = peer_review

    access_rights = _build_status_with_description(
        first_row, "manifestation_access_rights_status", "manifestation_access_rights_description"
    )
    if access_rights:
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


def _collect_manifestations(rows: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        if not any(
            value
            for column, value in row.items()
            if column.startswith("manifestation_") and column != "_manifestation_key"
        ):
            continue
        groups.setdefault(row["_manifestation_key"], []).append(row)
    return [manifestation for group in groups.values() if (manifestation := _build_manifestation(group))]


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
            entries[local_id] = _org_entry(row, prefix)
        _merge_org_multivalued(entries[local_id], row, prefix)
    return [entry["obj"] for entry in entries.values()]


def _collect_single_organisation(rows: list[dict], prefix: str) -> dict | None:
    base_row = next((row for row in rows if row[f"{prefix}_name"]), None)
    if base_row is None:
        return None
    entry = _org_entry(base_row, prefix)
    for row in rows:
        _merge_org_multivalued(entry, row, prefix)
    return entry["obj"]


def _build_person_affiliation(rows: list[dict]) -> dict:
    affiliation = {"affiliation": _collect_organisation(rows, "affiliation")[0]}
    first_row = rows[0]
    if role := first_row["affiliation_role"]:
        affiliation["role"] = role
    period = {
        key: first_row[column]
        for key, column in (("start", "affiliation_period_start"), ("end", "affiliation_period_end"))
        if first_row[column]
    }
    if period:
        affiliation["period"] = period
    return affiliation


def _collect_person_affiliations(rows: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        local_identifier = row["affiliation_local_identifier"]
        if not local_identifier:
            continue
        key = row["_affiliation_key"] or local_identifier
        groups.setdefault(key, []).append(row)
    return [_build_person_affiliation(group) for group in groups.values()]


def _build_grant(row: dict) -> dict:
    funding_local_id = row["funding_local_identifier"]
    if not funding_local_id:
        msg = "Missing required local_identifier for grant"
        raise ValueError(msg)
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


def normalize_local_identifier_url(local_identifier: str) -> tuple[str]:
    # Reverse proxies (e.g. Traefik) merge duplicate slashes in request paths,
    # turning "https://example.org/..." into "https:/example.org/...": restore the scheme separator.
    return (sub(r"^(https?):/+", r"\1://", local_identifier),)


def _canonical_path(path: str) -> str:
    segments = [segment for segment in path.split("/") if segment]
    for index, segment in enumerate(segments):
        if segment in ENTITY_TYPES and index + 1 < len(segments):
            identifier = normalize_local_identifier_url("/".join(segments[index + 1 :]))[0]
            return "/" + "/".join(segments[: index + 1]) + "/" + identifier
    return path


def _build_search_result_page(url: str) -> dict:
    return {"local_identifier": url, "entity_type": "search_result_page"}


def _meta_base_url(request_url: str) -> str:
    parsed = urlsplit(request_url)
    path = _canonical_path(parsed.path)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}{path}"
    return path


def _page_url(base_path: str, params: dict[str, list[str]], page: int) -> str:
    page_params = {**params, "page": [str(page)]}
    return f"{base_path}?{urlencode(page_params, doseq=True, safe=':,')}"


def _raise_unprocessable(message: str) -> NoReturn:
    raise HttpError(_UNPROCESSABLE_CONTENT, f"HTTP status code {_UNPROCESSABLE_CONTENT}: {message}")


def _parse_positive_int_param(params: dict[str, list[str]], name: str) -> int:
    raw_value = params[name][0]
    try:
        value = int(raw_value)
    except ValueError:
        _raise_unprocessable(f"{name} must be an integer, got {raw_value!r}")
    if value < 1:
        _raise_unprocessable(f"{name} must be >= 1, got {value}")
    return value


def _validate_page_range(page: int, total_items: int, total_pages: int) -> None:
    if total_items and page > total_pages:
        _raise_unprocessable(f"page {page} exceeds total pages {total_pages}")


def _build_meta(request_url: str, graph_size: int) -> dict:
    parsed = urlsplit(request_url)
    base_url = _meta_base_url(request_url)
    if _is_single_entity_request(request_url):
        return {"local_identifier": base_url, "entity_type": "single_entity"}
    params = parse_qs(parsed.query)
    if "total_items" in params:
        total_items = int(params["total_items"][0])
        page = _parse_positive_int_param(params, "page")
        page_size = _parse_positive_int_param(params, "page_size")
    elif "page_size" in params:
        total_items = graph_size
        page = _parse_positive_int_param(params, "page") if "page" in params else 1
        page_size = _parse_positive_int_param(params, "page_size")
    elif "page" in params:
        _raise_unprocessable("page requires page_size")
    else:
        total_items = graph_size
        page = 1
        page_size = max(graph_size, 1)
    total_pages = ceil(total_items / page_size) if page_size > 0 else 0
    non_pagination_params = {k: v for k, v in params.items() if k not in ("page", "page_size", "total_items")}
    clean_params = {**non_pagination_params, "page": [str(page)], "page_size": [str(page_size)]}
    self_url = f"{base_url}?{urlencode(clean_params, doseq=True, safe=':,')}"
    meta = _build_search_result_page(self_url)
    if page < total_pages:
        meta["next_page"] = _build_search_result_page(_page_url(base_url, clean_params, page + 1))
    if page > 1:
        meta["prev_page"] = _build_search_result_page(_page_url(base_url, clean_params, page - 1))
    base_params = {k: v for k, v in clean_params.items() if k not in ("page", "page_size")}
    search_result_url = f"{base_url}?{urlencode(base_params, doseq=True, safe=':,')}" if base_params else base_url
    meta["part_of"] = {
        "local_identifier": search_result_url,
        "entity_type": "search_result",
        "total_items": total_items,
        "first_page": _build_search_result_page(_page_url(base_url, clean_params, 1)),
        "last_page": _build_search_result_page(_page_url(base_url, clean_params, max(total_pages, 1))),
    }
    return meta


_BUILDER_COLUMN_PREFIXES = (
    "identifier_",
    "affiliation_",
    "contribution_",
    "manifestation_",
    "related_products_",
    "topic_",
    "funding_",
    "relevant_organisation_",
    "beneficiaries_",
    "access_rights_",
    "duration_",
    "persistent_identity_system_",
    "audience_",
    "policy_",
)


_MULTI_VALUED_COLUMNS: tuple[str, ...] = (
    "types",
    "other_names",
    "keywords",
    "research_product_types",
    "disciplines",
)


def _collect_passthrough_fields(first_row: dict, excluded: set[str]) -> dict:
    entity: dict = {}
    for col, val in first_row.items():
        if col.startswith("_") or col in excluded:
            continue
        if any(col.startswith(prefix) for prefix in _BUILDER_COLUMN_PREFIXES):
            continue
        if val:
            entity[col] = val
    return entity


def _add_formatted_text(entity: dict, rows: list[dict], text_field: tuple[str, str, str], *, as_list: bool) -> None:
    field, lang_field, output_key = text_field
    if as_list:
        values: dict[str, list[str]] = {}
        for row in rows:
            value = row.get(field)
            if value:
                language_values = values.setdefault(row.get(lang_field) or "none", [])
                if value not in language_values:
                    language_values.append(value)
        if values:
            entity[output_key] = values
        return
    first_row = rows[0]
    if first_row.get(field):
        entity[output_key] = {first_row.get(lang_field) or "none": first_row[field]}


_SECTION_BUILDERS: tuple[tuple[str, str, Callable], ...] = (
    ("identifier_scheme", "identifiers", _collect_identifiers),
    ("topic_term", "topics", _collect_topics),
    ("funding_local_identifier", "funding", _collect_funding),
)


def _collect_contributions(rows: list[dict], entity_type: str | None) -> list[dict]:
    if entity_type in {"grant", "venue"}:
        return _collect_grouped_contributors(rows)
    return _collect_contributors(rows)


def _parse_number(value: str) -> int | float:
    number = float(value)
    return int(number) if number.is_integer() else number


def _apply_grant_fields(entity: dict, rows: list[dict], first_row: dict, columns: set[str]) -> None:
    if "funded_amount" in entity:
        if "currency" not in entity:
            msg = "Missing required currency for funded_amount"
            raise ValueError(msg)
        entity["funded_amount"] = _parse_number(entity["funded_amount"])
    if "duration_start" in columns and (start := first_row["duration_start"]):
        duration = {"start": start}
        if "duration_end" in columns and (end := first_row["duration_end"]):
            duration["end"] = end
        entity["duration"] = duration
    if "funding_stream" in columns and (funding_stream := first_row["funding_stream"]):
        entity["funding_stream"] = funding_stream
    if "funding_agency_name" in columns and (agency := _collect_single_organisation(rows, "funding_agency")):
        entity["funding_agency"] = agency


_FORMATTED_TEXT_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("title", "title_lang", "titles"),
    ("abstract", "abstract_lang", "abstracts"),
    ("label", "label_lang", "labels"),
)

# Research products hold a list of values per language; every other entity holds a single string.
_MULTI_VALUED_TEXT_ENTITY_TYPE = "product"


def _active_formatted_columns(columns: set[str]) -> set[str]:
    active: set[str] = set()
    for field, lang_field, _ in _FORMATTED_TEXT_FIELDS:
        if field in columns:
            active.update((field, lang_field))
    return active


def _attach_multi_valued_columns(entity: dict, rows: list[dict], columns: set[str]) -> None:
    for column in _MULTI_VALUED_COLUMNS:
        if column not in columns:
            continue
        values = list(dict.fromkeys(row[column] for row in rows if row[column]))
        if values:
            entity[column] = values


def _attach_organisation_lists(entity: dict, rows: list[dict], columns: set[str]) -> None:
    if "relevant_organisation_name" in columns and (
        organisations := _collect_organisation(rows, "relevant_organisation")
    ):
        entity["relevant_organisations"] = organisations
    if "beneficiaries_name" in columns and (beneficiaries := _collect_organisation(rows, "beneficiaries")):
        entity["beneficiaries"] = beneficiaries


def _collect_persistent_identity_systems(rows: list[dict]) -> list[dict]:
    systems: dict[str, dict] = {}
    for row in rows:
        product_type = row["persistent_identity_system_for"]
        pid_scheme = row["persistent_identity_system_pid_scheme"]
        if not product_type or not pid_scheme:
            continue
        key = row["_persistent_identity_system_key"] or product_type
        system = systems.setdefault(key, {"for": product_type, "pid_schemes": []})
        if pid_scheme not in system["pid_schemes"]:
            system["pid_schemes"].append(pid_scheme)
    return list(systems.values())


def _collect_audience(rows: list[dict]) -> list[dict]:
    audience_types = list(dict.fromkeys(row["audience_type"] for row in rows if row["audience_type"]))
    return [{"audience_type": audience_type} for audience_type in audience_types]


def _collect_policies(rows: list[dict]) -> list[dict]:
    policies: dict[str, dict] = {}
    for row in rows:
        about = row["policy_about"]
        if not about:
            continue
        key = row["_policy_key"] or about
        policy = policies.setdefault(key, {"about": about})
        target = row["policy_target"]
        if target:
            targets = policy.setdefault("targets", [])
            if target not in targets:
                targets.append(target)
        if row["policy_documented_at"]:
            policy["documented_at"] = row["policy_documented_at"]
        if row["policy_description"]:
            policy["description"] = row["policy_description"]
    return list(policies.values())


def _apply_data_source_fields(entity: dict, rows: list[dict], columns: set[str]) -> None:
    if "persistent_identity_system_for" in columns and (systems := _collect_persistent_identity_systems(rows)):
        entity["persistent_identity_systems"] = systems
    if "audience_type" in columns and (audience := _collect_audience(rows)):
        entity["audience"] = audience
    if "policy_about" in columns and (policies := _collect_policies(rows)):
        entity["policies"] = policies


def _apply_entity_type(
    entity: dict, rows: list[dict], first_row: dict, columns: set[str], entity_type: str | None
) -> None:
    if entity_type == "grant":
        _apply_grant_fields(entity, rows, first_row, columns)
    if entity_type == "venue" and "access_rights_status" in columns:
        access_rights = _build_status_with_description(first_row, "access_rights_status", "access_rights_description")
        if access_rights:
            entity["access_rights"] = access_rights
    if (
        entity_type == "person"
        and "affiliation_local_identifier" in columns
        and (affiliations := _collect_person_affiliations(rows))
    ):
        entity["affiliations"] = affiliations
    if entity_type == "datasource":
        _apply_data_source_fields(entity, rows, columns)
    if entity_type is not None:
        entity["entity_type"] = entity_type


def _build_entity(rows: list[dict], entity_type: str | None) -> dict:
    first_row = rows[0]
    columns = set(first_row)

    entity = _collect_passthrough_fields(first_row, _active_formatted_columns(columns) | set(_MULTI_VALUED_COLUMNS))
    as_list = entity_type == _MULTI_VALUED_TEXT_ENTITY_TYPE
    for text_field in _FORMATTED_TEXT_FIELDS:
        _add_formatted_text(entity, rows, text_field, as_list=as_list)

    _attach_multi_valued_columns(entity, rows, columns)

    for anchor, key, builder in _SECTION_BUILDERS:
        if anchor in columns and (section := builder(rows)):
            entity[key] = section
    if "contribution_role" in columns and (contributions := _collect_contributions(rows, entity_type)):
        entity["contributions"] = contributions
    if any(column.startswith("manifestation_") for column in columns) and (
        manifestations := _collect_manifestations(rows)
    ):
        entity["manifestations"] = manifestations
    if columns & set(_RELATED_PRODUCT_COLUMNS) and (related := _collect_related_products(rows)):
        entity["related_products"] = related
    _attach_organisation_lists(entity, rows, columns)
    _apply_entity_type(entity, rows, first_row, columns, entity_type)

    return entity


def _build_entities(rows: list[dict], entity_type: str | None) -> list[dict]:
    if not rows:
        return []
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["local_identifier"], []).append(row)
    return [_build_entity(group, entity_type) for group in groups.values()]


ENTITY_TYPES = frozenset({"products", "persons", "organisations", "grants", "venues", "topics", "datasources"})

_ENTITY_TYPE_MAP: dict[str, str] = {
    "products": "product",
    "persons": "person",
    "organisations": "organisation",
    "grants": "grant",
    "venues": "venue",
    "topics": "topic",
    "datasources": "datasource",
}


def _extract_entity_type(request_url: str) -> str | None:
    for segment in urlsplit(request_url).path.split("/"):
        if segment in _ENTITY_TYPE_MAP:
            return _ENTITY_TYPE_MAP[segment]
    return None


def _is_single_entity_request(request_url: str) -> bool:
    segments = [s for s in urlsplit(request_url).path.split("/") if s]
    for i, segment in enumerate(segments):
        if segment in ENTITY_TYPES:
            return i + 1 < len(segments)
    return False


_COLUMN_GROUP_PREFIXES = (
    "identifier_",
    "affiliation_",
    "_affiliation_",
    "contribution_",
    "_contribution_",
    "manifestation_",
    "_manifestation_",
    "related_products_",
    "topic_",
    "funding_",
    "relevant_organisation_",
    "beneficiaries_",
    "persistent_identity_system_",
    "_persistent_identity_system_",
    "audience_",
    "policy_",
    "_policy_",
)

_CORE_COLUMNS = frozenset(col for col in _PRODUCT_COLUMNS if not any(col.startswith(p) for p in _COLUMN_GROUP_PREFIXES))


def _fill_missing_columns(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if not rows:
        return rows
    present = set(rows[0])
    active_prefixes = {prefix for prefix in _COLUMN_GROUP_PREFIXES if any(col.startswith(prefix) for col in present)}
    missing = {
        col: ""
        for col in _PRODUCT_COLUMNS
        if col not in present
        and (
            (active_prefixes and col in _CORE_COLUMNS)
            or any(col.startswith(p) for p in active_prefixes)
            or (col == "_manifestation_key" and "manifestation_" in active_prefixes)
            or (col == "_affiliation_key" and "affiliation_" in active_prefixes)
            or (col == "_persistent_identity_system_key" and "persistent_identity_system_" in active_prefixes)
            or (col == "_policy_key" and "policy_" in active_prefixes)
        )
    }
    if not missing:
        return rows
    return [missing | row for row in rows]


def to_skg_if(csv_str: str, request_url: str = "", base_url: str = "") -> str:
    context = _build_context(base_url)
    rows = _fill_missing_columns(list(csv.DictReader(StringIO(csv_str))))
    if not rows and _is_single_entity_request(request_url):
        msg = "HTTP status code 404: entity not found"
        raise HttpError(404, msg)
    entity_type = _extract_entity_type(request_url)
    graph = _build_entities(rows, entity_type)

    total_entities = len(graph)

    parsed = urlsplit(request_url)
    params = parse_qs(parsed.query)
    if "page_size" in params and "total_items" not in params:
        page_size = _parse_positive_int_param(params, "page_size")
        page = _parse_positive_int_param(params, "page") if "page" in params else 1
        total_pages = ceil(total_entities / page_size) if page_size > 0 else 0
        _validate_page_range(page, total_entities, total_pages)
        start = (page - 1) * page_size
        graph = graph[start : start + page_size]
    elif "page" in params and "total_items" not in params:
        _raise_unprocessable("page requires page_size")

    result = {
        "@context": context,
        "meta": _build_meta(request_url, total_entities),
        "@graph": graph,
    }
    return json.dumps(result, ensure_ascii=False, indent=4)
