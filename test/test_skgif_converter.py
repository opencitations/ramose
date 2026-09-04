# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import copy
import csv
import json
from io import StringIO
from typing import TYPE_CHECKING, overload

import pyshacl
import pytest
import requests
import yaml
from jsonschema import validate
from rdflib import Graph

from ramose.skg_if import to_skg_if

if TYPE_CHECKING:
    from ramose import APIManager

SKGIF_OPENAPI_URL = "https://raw.githubusercontent.com/skg-if/api/main/openapi/ver/current/skg-if-openapi.yaml"


@overload
def _resolve_refs(node: dict, components: dict) -> dict: ...
@overload
def _resolve_refs(node: list, components: dict) -> list: ...


def _resolve_refs(node: dict | list | object, components: dict) -> dict | list | object:
    if isinstance(node, dict):
        if "$ref" in node:
            ref_path = node["$ref"]
            if ref_path.startswith("#/components/schemas/"):
                schema_name = ref_path.split("/")[-1]
                return _resolve_refs(copy.deepcopy(components[schema_name]), components)
            return node
        return {key: _resolve_refs(value, components) for key, value in node.items()}
    if isinstance(node, list):
        return [_resolve_refs(item, components) for item in node]
    return node


def _load_openapi_spec() -> dict:
    response = requests.get(SKGIF_OPENAPI_URL, timeout=30)
    response.raise_for_status()
    return yaml.safe_load(response.text)


_OPENAPI_SPEC = _load_openapi_spec()
_OPENAPI_COMPONENTS = _OPENAPI_SPEC["components"]["schemas"]


def _response_schema(endpoint_path: str) -> dict:
    response_schema = _OPENAPI_SPEC["paths"][endpoint_path]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    return _resolve_refs(copy.deepcopy(response_schema), _OPENAPI_COMPONENTS)


SKGIF_PRODUCT_RESPONSE_SCHEMA = _response_schema("/products/{local_identifier}")


def _load_response_schema(endpoint: str) -> dict:
    return _response_schema(f"/{endpoint}/{{local_identifier}}")


SKGIF_SHACL_URL = "https://raw.githubusercontent.com/skg-if/shacl-extractor/main/shapes.ttl"


def _load_shacl_shapes() -> Graph:
    response = requests.get(SKGIF_SHACL_URL, timeout=30)
    response.raise_for_status()
    shapes_graph = Graph()
    shapes_graph.parse(data=response.text, format="turtle")
    return shapes_graph


SKGIF_SHACL_SHAPES = _load_shacl_shapes()


def _execute_skgif(skgif_api_manager: APIManager, local_identifier: str, endpoint: str) -> dict:
    operation = skgif_api_manager.get_op(f"/skgif/v1/{endpoint}/{local_identifier}")
    if isinstance(operation, tuple):
        msg = f"Operation not found: {local_identifier}"
        raise TypeError(msg)
    status, result, _, _ = operation.exec(method="get", content_type="application/json")
    if status != 200:
        msg = f"API returned status {status}: {result}"
        raise RuntimeError(msg)
    return json.loads(result)


def _validate_skgif_response(response: dict, endpoint: str) -> None:
    schema = _load_response_schema(endpoint)
    validate(instance=response, schema=schema)


def _validate_skgif_shacl(response: dict) -> None:
    data_graph = Graph()
    data_graph.parse(data=json.dumps(response), format="json-ld")
    conforms, _, results_text = pyshacl.validate(data_graph, shacl_graph=SKGIF_SHACL_SHAPES)
    assert conforms, f"SHACL validation failed:\n{results_text}"


SKGIF_CONTEXT = [
    "https://w3id.org/skg-if/context/1.1.0/skg-if.json",
    "https://w3id.org/skg-if/context/1.0.0/skg-if-api.json",
    {"@base": "https://w3id.org/skg-if/sandbox/opencitations/"},
]


def test_converter_context_uses_specification_base() -> None:
    result = json.loads(to_skg_if("local_identifier\n", base_url="https://example.org/skg"))
    assert result["@context"] == [*SKGIF_CONTEXT[:2], {"@base": "https://example.org/skg/"}]


class TestSkgifJournalArticle:
    def test_context(self, skgif_api_manager: APIManager) -> None:
        result = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601", "products")
        assert result["@context"] == SKGIF_CONTEXT

    def test_product_metadata(self, skgif_api_manager: APIManager) -> None:
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601", "products")["@graph"][0]
        assert product["local_identifier"] == "https://w3id.org/oc/meta/br/0601"
        assert product["entity_type"] == "product"
        assert product["product_type"] == "literature"
        assert product["titles"] == {
            "none": [
                "Response To The Letter Of Hanley Et Al. "
                "([1999] Teratology 59:323-324), Concerning The Article By Roy Et Al. "
                "([1998] Teratology 58:62-68)",
            ],
        }
        assert "abstracts" not in product
        assert "funding" not in product
        assert "relevant_organisations" not in product

    def test_identifiers(self, skgif_api_manager: APIManager) -> None:
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601", "products")["@graph"][0]
        assert product["identifiers"] == [
            {"value": "10.1002/(sici)1096-9926(199910)60:4<177::aid-tera1>3.0.co;2-z", "scheme": "doi"},
        ]

    def test_author_contributions(self, skgif_api_manager: APIManager) -> None:
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601", "products")["@graph"][0]
        authors = [contribution for contribution in product["contributions"] if contribution["role"] == "author"]
        assert len(authors) == 2

        assert authors[0]["rank"] == 1
        assert authors[0]["by"]["name"] == "Slotkin, Theodore A."
        assert authors[0]["by"]["family_name"] == "Slotkin"
        assert authors[0]["by"]["given_name"] == "Theodore A."
        assert authors[0]["by"]["local_identifier"] == "https://w3id.org/oc/meta/ra/0601"
        assert authors[0]["by"]["entity_type"] == "person"

        assert authors[1]["rank"] == 2
        assert authors[1]["by"]["name"] == "Andrews, James E."
        assert authors[1]["by"]["family_name"] == "Andrews"
        assert authors[1]["by"]["given_name"] == "James E."

    def test_publisher_contribution(self, skgif_api_manager: APIManager) -> None:
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601", "products")["@graph"][0]
        publishers = [contribution for contribution in product["contributions"] if contribution["role"] == "publisher"]
        assert len(publishers) == 1
        assert publishers[0]["rank"] == 1
        assert publishers[0]["by"]["name"] == "Wiley"
        assert publishers[0]["by"]["entity_type"] == "organisation"
        assert publishers[0]["by"]["local_identifier"] == "https://w3id.org/oc/meta/ra/0610116001"
        assert "family_name" not in publishers[0]["by"]
        assert "given_name" not in publishers[0]["by"]

    def test_manifestation_type(self, skgif_api_manager: APIManager) -> None:
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601", "products")["@graph"][0]
        manifestation_type = product["manifestations"][0]["type"]
        assert manifestation_type == {
            "class": "http://purl.org/spar/fabio/JournalArticle",
            "defined_in": "http://purl.org/spar/fabio",
            "labels": {"en": "journal article"},
        }

    def test_biblio_volume_issue_pages(self, skgif_api_manager: APIManager) -> None:
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601", "products")["@graph"][0]
        biblio = product["manifestations"][0]["biblio"]
        assert biblio["volume"] == "60"
        assert biblio["issue"] == "4"
        assert biblio["pages"] == {"first": "177", "last": "178"}

    def test_venue(self, skgif_api_manager: APIManager) -> None:
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601", "products")["@graph"][0]
        venue = product["manifestations"][0]["biblio"]["in"]
        assert venue["name"] == "Teratology"
        assert venue["entity_type"] == "venue"
        assert venue["local_identifier"] == "https://w3id.org/oc/meta/br/06101018"
        venue_schemes = {(identifier["scheme"], identifier["value"]) for identifier in venue["identifiers"]}
        assert venue_schemes == {
            ("issn", "1096-9926"),
            ("issn", "0040-3709"),
            ("doi", "10.1002/(issn)1096-9926"),
        }

    def test_publication_date(self, skgif_api_manager: APIManager) -> None:
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601", "products")["@graph"][0]
        assert product["manifestations"][0]["dates"]["publication"] == ["1999-10-01T00:00:00"]

    def test_citations(self, skgif_api_manager: APIManager) -> None:
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601", "products")["@graph"][0]
        assert product["related_products"] == {"cites": ["https://w3id.org/oc/meta/br/06035"]}


class TestSkgifBook:
    def test_product_metadata(self, skgif_api_manager: APIManager) -> None:
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0612058700", "products")["@graph"][0]
        assert product["local_identifier"] == "https://w3id.org/oc/meta/br/0612058700"
        assert product["product_type"] == "literature"
        assert product["titles"] == {"none": ["Adaptive Environmental Management"]}
        assert "abstracts" not in product
        assert "funding" not in product
        assert "relevant_organisations" not in product

    def test_multiple_identifiers(self, skgif_api_manager: APIManager) -> None:
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0612058700", "products")["@graph"][0]
        identifier_pairs = {(identifier["scheme"], identifier["value"]) for identifier in product["identifiers"]}
        assert identifier_pairs == {
            ("isbn", "9789048127108"),
            ("isbn", "9781402096327"),
            ("doi", "10.1007/978-1-4020-9632-7"),
            ("openalex", "W4249829199"),
        }

    def test_editor_ordering(self, skgif_api_manager: APIManager) -> None:
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0612058700", "products")["@graph"][0]
        editors = [contribution for contribution in product["contributions"] if contribution["role"] == "editor"]
        assert len(editors) == 2
        assert editors[0]["rank"] == 1
        assert editors[0]["by"]["family_name"] == "Allan"
        assert editors[0]["by"]["given_name"] == "Catherine"
        assert editors[0]["by"]["identifiers"] == [{"value": "0000-0003-2098-4759", "scheme": "orcid"}]
        assert editors[1]["rank"] == 2
        assert editors[1]["by"]["family_name"] == "Stankey"
        assert editors[1]["by"]["given_name"] == "George H."
        assert "identifiers" not in editors[1]["by"]

    def test_no_venue_no_pages(self, skgif_api_manager: APIManager) -> None:
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0612058700", "products")["@graph"][0]
        manifestation = product["manifestations"][0]
        assert manifestation["type"] == {
            "class": "http://purl.org/spar/fabio/Book",
            "defined_in": "http://purl.org/spar/fabio",
            "labels": {"en": "book"},
        }
        assert "biblio" not in manifestation
        assert manifestation["dates"]["publication"] == ["2009-01-01T00:00:00"]


class TestSkgifSchemaConformance:
    def test_schema_context_min_items_matches_upstream(self) -> None:
        assert SKGIF_PRODUCT_RESPONSE_SCHEMA["properties"]["@context"]["minItems"] == 3

    def test_journal_article_conforms(self, skgif_api_manager: APIManager) -> None:
        response = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601", "products")
        _validate_skgif_response(response, "products")

    def test_book_conforms(self, skgif_api_manager: APIManager) -> None:
        response = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0612058700", "products")
        _validate_skgif_response(response, "products")

    def test_person_conforms(self, skgif_api_manager: APIManager) -> None:
        response = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/ra/0614010840729", "persons")
        _validate_skgif_response(response, "persons")

    def test_org_conforms(self, skgif_api_manager: APIManager) -> None:
        response = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/ra/0670114921", "organisations")
        _validate_skgif_response(response, "organisations")

    def test_venue_conforms(self, skgif_api_manager: APIManager) -> None:
        response = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/062501778099", "venues")
        _validate_skgif_response(response, "venues")

    def test_journal_article_shacl(self, skgif_api_manager: APIManager) -> None:
        response = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601", "products")
        _validate_skgif_shacl(response)

    def test_book_shacl(self, skgif_api_manager: APIManager) -> None:
        response = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0612058700", "products")
        _validate_skgif_shacl(response)

    def test_person_shacl(self, skgif_api_manager: APIManager) -> None:
        response = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/ra/0614010840729", "persons")
        _validate_skgif_shacl(response)

    def test_org_shacl(self, skgif_api_manager: APIManager) -> None:
        response = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/ra/0670114921", "organisations")
        _validate_skgif_shacl(response)

    def test_venue_shacl(self, skgif_api_manager: APIManager) -> None:
        response = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/062501778099", "venues")
        _validate_skgif_shacl(response)


class TestSkgifPerson:
    def test_context(self, skgif_api_manager: APIManager) -> None:
        result = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/ra/0614010840729", "persons")
        assert result["@context"] == SKGIF_CONTEXT

    def test_person_metadata(self, skgif_api_manager: APIManager) -> None:
        person = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/ra/0614010840729", "persons")["@graph"][0]
        assert person["local_identifier"] == "https://w3id.org/oc/meta/ra/0614010840729"
        assert person["entity_type"] == "person"
        assert person["given_name"] == "Silvio"
        assert person["family_name"] == "Peroni"
        assert person["name"] == "Peroni Silvio"

    def test_identifiers(self, skgif_api_manager: APIManager) -> None:
        person = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/ra/0614010840729", "persons")["@graph"][0]
        assert person["identifiers"] == [{"scheme": "orcid", "value": "0000-0003-0530-4305"}]

    def test_affiliations(self) -> None:
        person_id = "https://example.org/persons/sp"
        base_row = {
            "local_identifier": person_id,
            "name": "Silvio Peroni",
            "affiliation_local_identifier": "https://example.org/organisations/unibo",
            "affiliation_name": "University of Bologna",
            "affiliation_short_name": "UNIBO",
            "affiliation_country": "IT",
            "affiliation_website": "https://www.unibo.it",
            "affiliation_type": "education",
            "affiliation_other_name": "Alma Mater Studiorum",
            "affiliation_identifier_scheme": "ror",
            "affiliation_identifier_value": "01111rn36",
            "affiliation_role": "affiliate",
            "affiliation_period_start": "2017-04-13T00:00:00Z",
            "affiliation_period_end": "2019-02-11T23:59:59Z",
        }
        second_row = {
            **base_row,
            "affiliation_type": "research",
            "affiliation_other_name": "Università di Bologna",
            "affiliation_identifier_scheme": "w3id",
            "affiliation_identifier_value": "unibo",
        }

        response = _convert([base_row, second_row], "persons", person_id)
        _validate_skgif_response(response, "persons")
        person = response["@graph"][0]

        assert person == {
            "local_identifier": person_id,
            "name": "Silvio Peroni",
            "affiliations": [
                {
                    "affiliation": {
                        "entity_type": "organisation",
                        "name": "University of Bologna",
                        "short_name": "UNIBO",
                        "country": "IT",
                        "website": "https://www.unibo.it",
                        "local_identifier": "https://example.org/organisations/unibo",
                        "identifiers": [
                            {"value": "01111rn36", "scheme": "ror"},
                            {"value": "unibo", "scheme": "w3id"},
                        ],
                        "types": ["education", "research"],
                        "other_names": ["Alma Mater Studiorum", "Università di Bologna"],
                    },
                    "role": "affiliate",
                    "period": {"start": "2017-04-13T00:00:00Z", "end": "2019-02-11T23:59:59Z"},
                }
            ],
            "entity_type": "person",
        }


class TestSkgifOrganisation:
    def test_context(self, skgif_api_manager: APIManager) -> None:
        result = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/ra/0670114921", "organisations")
        assert result["@context"] == SKGIF_CONTEXT

    def test_org_metadata(self, skgif_api_manager: APIManager) -> None:
        org = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/ra/0670114921", "organisations")["@graph"][0]
        assert org["local_identifier"] == "https://w3id.org/oc/meta/ra/0670114921"
        assert org["entity_type"] == "organisation"
        assert org["name"] == "Korean Council Of Science Editors"

    def test_identifiers(self, skgif_api_manager: APIManager) -> None:
        org = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/ra/0670114921", "organisations")["@graph"][0]
        assert org["identifiers"] == [{"scheme": "crossref", "value": "4099"}]


class TestSkgifVenue:
    def test_context(self, skgif_api_manager: APIManager) -> None:
        result = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/062501778099", "venues")
        assert result["@context"] == SKGIF_CONTEXT

    def test_venue_metadata(self, skgif_api_manager: APIManager) -> None:
        venue = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/062501778099", "venues")["@graph"][0]
        assert venue["local_identifier"] == "https://w3id.org/oc/meta/br/062501778099"
        assert venue["entity_type"] == "venue"
        assert venue["name"] == "Quantitative Science Studies"
        assert venue["type"] == "journal"

    def test_identifiers(self, skgif_api_manager: APIManager) -> None:
        venue = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/062501778099", "venues")["@graph"][0]
        assert venue["identifiers"] == [
            {"scheme": "openalex", "value": "S4210195326"},
            {"scheme": "issn", "value": "2641-3337"},
        ]

    def test_optional_metadata_and_contributions(self) -> None:
        venue_id = "https://example.org/venues/1"
        base_row = {
            "local_identifier": venue_id,
            "name": "Example Conference",
            "series": "Example Series",
            "creation_date": "2026-09-04T00:00:00+00:00",
            "access_rights_status": "open",
            "access_rights_description": "Open access venue",
            "_contribution_key": "editor-1",
            "contribution_role": "editor",
            "contribution_by_family_name": "Peroni",
            "contribution_by_given_name": "Silvio",
            "contribution_by_local_identifier": "https://example.org/persons/1",
        }

        response = _convert([base_row], "venues", venue_id)
        _validate_skgif_response(response, "venues")
        venue = response["@graph"][0]

        assert venue["series"] == "Example Series"
        assert venue["creation_date"] == "2026-09-04T00:00:00+00:00"
        assert venue["access_rights"] == {"status": "open", "description": "Open access venue"}
        assert venue["contributions"] == [
            {
                "by": {
                    "name": "Peroni, Silvio",
                    "entity_type": "person",
                    "family_name": "Peroni",
                    "given_name": "Silvio",
                    "local_identifier": "https://example.org/persons/1",
                },
                "roles": ["editor"],
            }
        ]

    def test_contribution_collects_identifier_from_later_row(self) -> None:
        venue_id = "https://example.org/venues/1"
        base_row = {
            "local_identifier": venue_id,
            "_contribution_key": "publisher-1",
            "contribution_role": "publisher",
            "contribution_by_name": "Example Publisher",
            "contribution_by_local_identifier": "https://example.org/organisations/1",
            "contribution_by_identifier_scheme": "",
            "contribution_by_identifier_value": "",
        }
        rows = [
            base_row,
            {
                **base_row,
                "contribution_by_identifier_scheme": "ror",
                "contribution_by_identifier_value": "012345678",
            },
        ]

        response = _convert(rows, "venues", venue_id)
        _validate_skgif_response(response, "venues")

        assert response["@graph"][0]["contributions"] == [
            {
                "by": {
                    "name": "Example Publisher",
                    "entity_type": "organisation",
                    "local_identifier": "https://example.org/organisations/1",
                    "identifiers": [{"value": "012345678", "scheme": "ror"}],
                },
                "roles": ["publisher"],
            }
        ]


CONVERTER_BASE_URL = "https://w3id.org/skg-if/sandbox/oc"
API_ROOT = "https://w3id.org/skg-if/sandbox/opencitations/skgif/v1"


def _convert(rows: list[dict[str, str]], endpoint: str, local_identifier: str) -> dict:
    buffer = StringIO()
    dict_writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    dict_writer.writeheader()
    dict_writer.writerows(rows)
    request_url = f"{API_ROOT}/{endpoint}/{local_identifier}"
    return json.loads(to_skg_if(buffer.getvalue(), request_url=request_url, base_url=CONVERTER_BASE_URL))


class TestProductRowsConversion:
    def test_collects_multilingual_titles_and_abstracts(self) -> None:
        product_id = "https://example.org/products/1"
        rows = [
            {
                "local_identifier": product_id,
                "product_type": "literature",
                "title": "Title",
                "title_lang": "en",
                "abstract": "Abstract",
                "abstract_lang": "en",
            },
            {
                "local_identifier": product_id,
                "product_type": "literature",
                "title": "Titolo",
                "title_lang": "it",
                "abstract": "Abstract",
                "abstract_lang": "en",
            },
        ]

        response = _convert(rows, "products", product_id)
        _validate_skgif_response(response, "products")
        product = response["@graph"][0]

        assert product["titles"] == {"en": ["Title"], "it": ["Titolo"]}
        assert product["abstracts"] == {"en": ["Abstract"]}

    def test_groups_independent_manifestations_without_requiring_a_type_class(self) -> None:
        product_id = "https://example.org/products/1"
        base_row = {
            "local_identifier": product_id,
            "product_type": "research software",
            "manifestation_type_label": "",
            "manifestation_type_label_lang": "",
            "manifestation_type_defined_in": "",
            "manifestation_version": "",
            "manifestation_identifier_scheme": "",
            "manifestation_identifier_value": "",
        }
        rows = [
            {
                **base_row,
                "_manifestation_key": "source",
                "manifestation_type_label": "source code",
                "manifestation_type_label_lang": "en",
                "manifestation_type_defined_in": "https://example.org/manifestation-types",
                "manifestation_version": "1.0.0",
            },
            {
                **base_row,
                "_manifestation_key": "package",
                "manifestation_identifier_scheme": "doi",
                "manifestation_identifier_value": "10.1234/package",
            },
        ]

        response = _convert(rows, "products", product_id)
        _validate_skgif_response(response, "products")
        product = response["@graph"][0]

        assert product["manifestations"] == [
            {
                "type": {
                    "labels": {"en": "source code"},
                    "defined_in": "https://example.org/manifestation-types",
                },
                "version": "1.0.0",
            },
            {"identifiers": [{"value": "10.1234/package", "scheme": "doi"}]},
        ]


GRANT_ID = "https://example.org/grants/101017452"
GRANT_ROW = {
    "local_identifier": GRANT_ID,
    "grant_number": "101017452",
    "acronym": "OpenAIRE-Nexus",
    "currency": "EUR",
    "funded_amount": "4000000",
    "website": "https://www.openaire.eu/openaire-nexus-project",
    "title": "OpenAIRE-Nexus Scholarly Communication Services for EOSC users",
    "title_lang": "en",
    "abstract": "A framework of services to assist in publishing research.",
    "abstract_lang": "en",
    "keywords": "Open science",
    "duration_start": "2021-01-01T00:00:00",
    "duration_end": "2023-12-31T23:59:59",
    "identifier_scheme": "doi",
    "identifier_value": "10.3030/101017452",
    "funding_stream": "Horizon 2020",
    "funding_agency_name": "European Commission",
    "funding_agency_short_name": "EC",
    "funding_agency_country": "BE",
    "funding_agency_local_identifier": "https://example.org/organisations/ec",
    "funding_agency_identifier_scheme": "ror",
    "funding_agency_identifier_value": "00k4n6c32",
    "funding_agency_type": "funder",
    "funding_agency_website": "https://ec.europa.eu",
    "beneficiaries_name": "University of Bologna",
    "beneficiaries_short_name": "UNIBO",
    "beneficiaries_country": "IT",
    "beneficiaries_local_identifier": "https://example.org/organisations/unibo",
    "beneficiaries_identifier_scheme": "ror",
    "beneficiaries_identifier_value": "01111rn36",
    "beneficiaries_type": "education",
    "beneficiaries_website": "https://www.unibo.it",
    "beneficiaries_other_name": "Alma Mater Studiorum",
    "_contribution_key": "contributor_0",
    "contribution_role": "project manager",
    "contribution_by_family_name": "Peroni",
    "contribution_by_given_name": "Silvio",
    "contribution_by_name": "",
    "contribution_by_local_identifier": "https://example.org/persons/sp",
    "contribution_by_identifier_scheme": "orcid",
    "contribution_by_identifier_value": "0000-0003-0530-4305",
    "contribution_declared_affiliation_name": "University of Bologna",
    "contribution_declared_affiliation_local_identifier": "https://example.org/organisations/unibo",
}


class TestGrantConversion:
    def _grant(self, rows: list[dict[str, str]]) -> dict:
        response = _convert(rows, "grants", GRANT_ID)
        _validate_skgif_response(response, "grants")
        return response["@graph"][0]

    def test_grant_conforms_and_keeps_scalar_language_maps(self) -> None:
        grant = self._grant([GRANT_ROW])
        assert grant["entity_type"] == "grant"
        assert grant["titles"] == {"en": "OpenAIRE-Nexus Scholarly Communication Services for EOSC users"}
        assert grant["abstracts"] == {"en": "A framework of services to assist in publishing research."}
        assert grant["funded_amount"] == 4000000
        assert grant["funding_stream"] == "Horizon 2020"
        assert grant["keywords"] == ["Open science"]
        assert grant["duration"] == {
            "start": "2021-01-01T00:00:00",
            "end": "2023-12-31T23:59:59",
        }

    def test_keywords_are_deduplicated_in_row_order(self) -> None:
        second_keyword = {**GRANT_ROW, "keywords": "mutual learning"}
        grant = self._grant([GRANT_ROW, second_keyword, second_keyword])
        assert grant["keywords"] == ["Open science", "mutual learning"]

    def test_duration_requires_a_start(self) -> None:
        grant = self._grant([{**GRANT_ROW, "duration_start": "", "duration_end": "2023-12-31T23:59:59"}])
        assert "duration" not in grant

    def test_duration_end_is_optional(self) -> None:
        row = {key: value for key, value in GRANT_ROW.items() if key != "duration_end"}
        grant = self._grant([row])
        assert grant["duration"] == {"start": "2021-01-01T00:00:00"}

    def test_funded_amount_requires_currency(self) -> None:
        with pytest.raises(ValueError, match=r"^Missing required currency for funded_amount$"):
            self._grant([{**GRANT_ROW, "currency": ""}])

    def test_funding_agency_and_beneficiaries(self) -> None:
        grant = self._grant([GRANT_ROW])
        assert grant["funding_agency"] == {
            "entity_type": "organisation",
            "name": "European Commission",
            "short_name": "EC",
            "country": "BE",
            "website": "https://ec.europa.eu",
            "local_identifier": "https://example.org/organisations/ec",
            "identifiers": [{"value": "00k4n6c32", "scheme": "ror"}],
            "types": ["funder"],
        }
        assert grant["beneficiaries"] == [
            {
                "entity_type": "organisation",
                "name": "University of Bologna",
                "short_name": "UNIBO",
                "country": "IT",
                "website": "https://www.unibo.it",
                "local_identifier": "https://example.org/organisations/unibo",
                "identifiers": [{"value": "01111rn36", "scheme": "ror"}],
                "types": ["education"],
                "other_names": ["Alma Mater Studiorum"],
            }
        ]

    def test_contributions_use_scoro_roles(self) -> None:
        second_role = {**GRANT_ROW, "contribution_role": "workpackage leader"}
        organisation_contributor = {
            **GRANT_ROW,
            "_contribution_key": "contributor_1",
            "contribution_role": "lead applicant",
            "contribution_by_family_name": "",
            "contribution_by_given_name": "",
            "contribution_by_name": "European Commission",
            "contribution_by_local_identifier": "https://example.org/organisations/ec",
            "contribution_by_identifier_scheme": "",
            "contribution_by_identifier_value": "",
            "contribution_declared_affiliation_name": "",
            "contribution_declared_affiliation_local_identifier": "",
        }
        grant = self._grant([GRANT_ROW, second_role, organisation_contributor])
        assert grant["contributions"] == [
            {
                "by": {
                    "name": "Peroni, Silvio",
                    "entity_type": "person",
                    "family_name": "Peroni",
                    "given_name": "Silvio",
                    "identifiers": [{"value": "0000-0003-0530-4305", "scheme": "orcid"}],
                    "local_identifier": "https://example.org/persons/sp",
                },
                "roles": ["project manager", "workpackage leader"],
                "declared_affiliations": [
                    {
                        "entity_type": "organisation",
                        "name": "University of Bologna",
                        "local_identifier": "https://example.org/organisations/unibo",
                    }
                ],
            },
            {
                "by": {
                    "name": "European Commission",
                    "entity_type": "organisation",
                    "local_identifier": "https://example.org/organisations/ec",
                },
                "roles": ["lead applicant"],
            },
        ]

    def test_grant_without_funding_columns(self) -> None:
        grant = self._grant([{"local_identifier": GRANT_ID, "grant_number": "101017452", "acronym": "Nexus"}])
        assert grant == {
            "local_identifier": GRANT_ID,
            "grant_number": "101017452",
            "acronym": "Nexus",
            "entity_type": "grant",
        }


class TestTopicConversion:
    def test_topic_labels_are_scalar(self) -> None:
        rows = [
            {
                "local_identifier": "https://example.org/topics/T10102",
                "label": "Scientometrics and Bibliometrics Research",
                "label_lang": "en",
                "identifier_scheme": "openalex",
                "identifier_value": "T10102",
            }
        ]
        response = _convert(rows, "topics", "https://example.org/topics/T10102")
        _validate_skgif_response(response, "topics")
        assert response["@graph"][0] == {
            "local_identifier": "https://example.org/topics/T10102",
            "labels": {"en": "Scientometrics and Bibliometrics Research"},
            "identifiers": [{"value": "T10102", "scheme": "openalex"}],
            "entity_type": "topic",
        }


class TestOrganisationConversion:
    def test_types_and_other_names_are_deduplicated_lists(self) -> None:
        base = {
            "local_identifier": "https://example.org/organisations/unibo",
            "name": "University of Bologna",
            "types": "education",
            "other_names": "Alma Mater Studiorum",
        }
        rows = [base, {**base, "types": "research", "other_names": "UNIBO"}, base]
        response = _convert(rows, "organisations", "https://example.org/organisations/unibo")
        _validate_skgif_response(response, "organisations")
        assert response["@graph"][0] == {
            "local_identifier": "https://example.org/organisations/unibo",
            "name": "University of Bologna",
            "types": ["education", "research"],
            "other_names": ["Alma Mater Studiorum", "UNIBO"],
            "entity_type": "organisation",
        }


class TestDataSourceConversion:
    def test_data_source_fields(self) -> None:
        data_source_id = "https://example.org/datasources/zenodo"
        base = {
            "local_identifier": data_source_id,
            "name": "Zenodo",
            "identifier_scheme": "doi",
            "identifier_value": "10.25495/7GXK-RD71",
            "data_source_classification": "repository",
            "research_product_types": "research data",
            "disciplines": "all",
            "_persistent_identity_system_key": "literature",
            "persistent_identity_system_for": "literature",
            "persistent_identity_system_pid_scheme": "doi",
            "audience_type": "Global",
            "_policy_key": "open-access",
            "policy_about": "open access",
            "policy_target": "metadata",
            "policy_documented_at": "https://example.org/open-access",
            "policy_description": "Open-access policy",
        }
        rows = [
            base,
            {
                **base,
                "research_product_types": "literature",
                "disciplines": "QC790.95-QC791.8",
                "persistent_identity_system_pid_scheme": "handle",
                "audience_type": "National",
                "policy_target": "literature",
            },
            base,
        ]
        response = _convert(rows, "datasources", data_source_id)
        _validate_skgif_response(response, "datasources")
        assert response["@graph"][0] == {
            "local_identifier": data_source_id,
            "name": "Zenodo",
            "data_source_classification": "repository",
            "identifiers": [{"value": "10.25495/7GXK-RD71", "scheme": "doi"}],
            "research_product_types": ["research data", "literature"],
            "disciplines": ["all", "QC790.95-QC791.8"],
            "persistent_identity_systems": [
                {"for": "literature", "pid_schemes": ["doi", "handle"]},
            ],
            "audience": [{"audience_type": "Global"}, {"audience_type": "National"}],
            "policies": [
                {
                    "about": "open access",
                    "targets": ["metadata", "literature"],
                    "documented_at": "https://example.org/open-access",
                    "description": "Open-access policy",
                }
            ],
            "entity_type": "datasource",
        }

    def test_incomplete_nested_data_is_skipped_and_fields_use_fallback_grouping(self) -> None:
        data_source_id = "https://example.org/datasources/zenodo"
        rows = [
            {
                "local_identifier": data_source_id,
                "persistent_identity_system_for": "literature",
                "persistent_identity_system_pid_scheme": "doi",
                "policy_about": "preservation",
                "policy_target": "literature",
                "policy_documented_at": "",
                "policy_description": "",
            },
            {
                "local_identifier": data_source_id,
                "persistent_identity_system_for": "literature",
                "persistent_identity_system_pid_scheme": "",
                "policy_about": "",
                "policy_target": "metadata",
                "policy_documented_at": "https://example.org/ignored",
                "policy_description": "Ignored",
            },
        ]
        response = _convert(rows, "datasources", data_source_id)
        _validate_skgif_response(response, "datasources")
        assert response["@graph"][0] == {
            "local_identifier": data_source_id,
            "persistent_identity_systems": [{"for": "literature", "pid_schemes": ["doi"]}],
            "policies": [{"about": "preservation", "targets": ["literature"]}],
            "entity_type": "datasource",
        }
