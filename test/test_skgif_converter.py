# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, overload

import pyshacl
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
    {"@base": "https://w3id.org/skg-if/sandbox/oc/"},
]


def test_direct_converter_uses_skgif_placeholder_base() -> None:
    result = json.loads(to_skg_if("local_identifier\n"))
    assert result["@context"] == SKGIF_CONTEXT


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
