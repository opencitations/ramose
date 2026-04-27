# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import copy
import json
from typing import overload

import requests
import yaml
from jsonschema import validate

from ramose import APIManager

SKGIF_OPENAPI_URL = "https://raw.githubusercontent.com/skg-if/api/main/openapi/ver/current/skg-if-openapi.yaml"


@overload
def _resolve_refs(node: dict, components: dict) -> dict: ...
@overload
def _resolve_refs(node: list, components: dict) -> list: ...


def _resolve_refs(node, components):
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


def _load_product_response_schema() -> dict:
    response = requests.get(SKGIF_OPENAPI_URL, timeout=30)
    response.raise_for_status()
    openapi_spec = yaml.safe_load(response.text)
    components = openapi_spec["components"]["schemas"]
    response_schema = openapi_spec["paths"]["/products/{short_local_identifier}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    return _resolve_refs(copy.deepcopy(response_schema), components)


SKGIF_PRODUCT_RESPONSE_SCHEMA = _load_product_response_schema()


def _execute_skgif(skgif_api_manager: APIManager, local_identifier: str) -> dict:
    operation = skgif_api_manager.get_op(f"/skgif/v1/products/{local_identifier}")
    if isinstance(operation, tuple):
        raise TypeError(f"Operation not found: {local_identifier}")
    status, result, _ = operation.exec(method="get", content_type="application/json")
    if status != 200:
        raise RuntimeError(f"API returned status {status}: {result}")
    return json.loads(result)


def _validate_skgif_response(response: dict) -> None:
    validate(instance=response, schema=SKGIF_PRODUCT_RESPONSE_SCHEMA)


SKGIF_CONTEXT = [
    "https://w3id.org/skg-if/context/1.1.0/skg-if.json",
    "https://w3id.org/skg-if/context/1.0.0/skg-if-api.json",
    {"@base": "https://w3id.org/skg-if/sandbox/opencitations/"},
]


class TestSkgifJournalArticle:
    def test_context(self, skgif_api_manager):
        result = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601")
        assert result["@context"] == SKGIF_CONTEXT

    def test_product_metadata(self, skgif_api_manager):
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601")["@graph"][0]
        assert product["local_identifier"] == "https://w3id.org/oc/meta/br/0601"
        assert product["entity_type"] == "product"
        assert product["product_type"] == "literature"
        assert product["titles"] == {
            "none": [
                "Response To The Letter Of Hanley Et Al. "
                "([1999] Teratology 59:323-324), Concerning The Article By Roy Et Al. "
                "([1998] Teratology 58:62-68)"
            ]
        }

    def test_identifiers(self, skgif_api_manager):
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601")["@graph"][0]
        assert product["identifiers"] == [
            {"value": "10.1002/(sici)1096-9926(199910)60:4<177::aid-tera1>3.0.co;2-z", "scheme": "doi"}
        ]

    def test_author_contributions(self, skgif_api_manager):
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601")["@graph"][0]
        authors = [contribution for contribution in product["contributions"] if contribution["role"] == "author"]
        assert len(authors) == 2

        assert authors[0]["rank"] == 1
        assert authors[0]["by"]["name"] == "Slotkin, Theodore A."
        assert authors[0]["by"]["family_name"] == "Slotkin"
        assert authors[0]["by"]["given_name"] == "Theodore A."
        assert authors[0]["by"]["local_identifier"] == "persons/ra/0601"
        assert authors[0]["by"]["entity_type"] == "person"

        assert authors[1]["rank"] == 2
        assert authors[1]["by"]["name"] == "Andrews, James E."
        assert authors[1]["by"]["family_name"] == "Andrews"
        assert authors[1]["by"]["given_name"] == "James E."

    def test_publisher_contribution(self, skgif_api_manager):
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601")["@graph"][0]
        publishers = [contribution for contribution in product["contributions"] if contribution["role"] == "publisher"]
        assert len(publishers) == 1
        assert publishers[0]["rank"] == 1
        assert publishers[0]["by"]["name"] == "Wiley"
        assert publishers[0]["by"]["entity_type"] == "organisation"
        assert publishers[0]["by"]["local_identifier"] == "organisations/ra/0610116001"
        assert "family_name" not in publishers[0]["by"]
        assert "given_name" not in publishers[0]["by"]

    def test_manifestation_type(self, skgif_api_manager):
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601")["@graph"][0]
        manifestation_type = product["manifestations"][0]["type"]
        assert manifestation_type == {
            "class": "http://purl.org/spar/fabio/JournalArticle",
            "defined_in": "http://purl.org/spar/fabio",
            "labels": {"en": "journal article"},
        }

    def test_biblio_volume_issue_pages(self, skgif_api_manager):
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601")["@graph"][0]
        biblio = product["manifestations"][0]["biblio"]
        assert biblio["volume"] == "60"
        assert biblio["issue"] == "4"
        assert biblio["pages"] == {"first": "177", "last": "178"}

    def test_venue(self, skgif_api_manager):
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601")["@graph"][0]
        venue = product["manifestations"][0]["biblio"]["in"]
        assert venue["name"] == "Teratology"
        assert venue["entity_type"] == "venue"
        assert venue["local_identifier"] == "venues/br/06101018"
        venue_schemes = {(identifier["scheme"], identifier["value"]) for identifier in venue["identifiers"]}
        assert venue_schemes == {
            ("issn", "1096-9926"),
            ("issn", "0040-3709"),
            ("doi", "10.1002/(issn)1096-9926"),
        }

    def test_publication_date(self, skgif_api_manager):
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601")["@graph"][0]
        assert product["manifestations"][0]["dates"]["publication"] == ["1999-10"]

    def test_no_citations(self, skgif_api_manager):
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601")["@graph"][0]
        assert "related_products" not in product


class TestSkgifBook:
    def test_product_metadata(self, skgif_api_manager):
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0612058700")["@graph"][0]
        assert product["local_identifier"] == "https://w3id.org/oc/meta/br/0612058700"
        assert product["product_type"] == "literature"
        assert product["titles"] == {"none": ["Adaptive Environmental Management"]}

    def test_multiple_identifiers(self, skgif_api_manager):
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0612058700")["@graph"][0]
        identifier_pairs = {(identifier["scheme"], identifier["value"]) for identifier in product["identifiers"]}
        assert identifier_pairs == {
            ("isbn", "9789048127108"),
            ("isbn", "9781402096327"),
            ("doi", "10.1007/978-1-4020-9632-7"),
            ("openalex", "W4249829199"),
        }

    def test_editor_ordering(self, skgif_api_manager):
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0612058700")["@graph"][0]
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

    def test_no_venue_no_pages(self, skgif_api_manager):
        product = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0612058700")["@graph"][0]
        manifestation = product["manifestations"][0]
        assert manifestation["type"] == {
            "class": "http://purl.org/spar/fabio/Book",
            "defined_in": "http://purl.org/spar/fabio",
            "labels": {"en": "book"},
        }
        assert "biblio" not in manifestation
        assert manifestation["dates"]["publication"] == ["2009"]


class TestSkgifSchemaConformance:
    def test_journal_article_conforms(self, skgif_api_manager):
        response = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0601")
        _validate_skgif_response(response)

    def test_book_conforms(self, skgif_api_manager):
        response = _execute_skgif(skgif_api_manager, "https://w3id.org/oc/meta/br/0612058700")
        _validate_skgif_response(response)
