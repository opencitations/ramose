# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import json
from pathlib import Path

import yaml

from ramose import APIManager, HTMLDocumentationHandler, OpenAPIDocumentationHandler, Operation
from ramose.hash_format import BUILTIN_PARAMS

with (Path(__file__).parent / "data" / "expected_search_products.json").open(encoding="utf8") as expected_search_file:
    EXPECTED_SEARCH: dict[str, list[dict]] = json.load(expected_search_file)

SKGIF_PUBLIC_BASE_URL = "https://w3id.org/skg-if/sandbox/opencitations"
# COMING_SOON_MOCK_ENDPOINTS = ("venues")
EMPTY_DATA_MOCK_ENDPOINTS = ("grants", "datasources", "topics")
MOCK_ENDPOINTS = (EMPTY_DATA_MOCK_ENDPOINTS)
MOCK_FILTER_EXAMPLES = {
    # "persons": "cf.search.given_name:Silvio,cf.search.family_name:Peroni",
    "organisations": "cf.search.name:Mit Press",
    "venues": "cf.search.name:Quantitative Science Studies",
    "grants": "grant_number:12345",
    "datasources": "research_product_type:literature",
    "topics": "cf.search.labels:biology",
}
OPERATION_PATH_ORDER = [
    "/products/{local_identifier}",
    "/products",
    "/persons/{local_identifier}",
    "/persons",
    "/organisations/{local_identifier}",
    "/organisations",
    "/venues/{local_identifier}",
    "/venues",
    "/grants/{local_identifier}",
    "/grants",
    "/datasources/{local_identifier}",
    "/datasources",
    "/topics/{local_identifier}",
    "/topics",
]
FILTER_DESCRIPTION_ORDER = {
    "products": (
        "product_type",
        "identifiers.id",
        "identifiers.scheme",
        "contributions.by.local_identifier",
        "contributions.by.identifiers.id",
        "contributions.by.identifiers.scheme",
        "contributions.by.family_name",
        "contributions.by.given_name",
        "contributions.by.name",
        "contributions.declared_affiliations.local_identifier",
        "contributions.declared_affiliations.identifiers.id",
        "contributions.declared_affiliations.identifiers.scheme",
        "contributions.declared_affiliations.name",
        "contributions.declared_affiliations.short_name",
        "funding.local_identifier",
        "funding.grant_number",
        "funding.identifiers.id",
        "funding.identifiers.scheme",
        "cf.search.title",
        "cf.search.title_abstract",
        "cf.contributions_orcid",
        "cf.contributions_aff_ror",
        "cf.contributions_aff_country",
        "cf.cites",
        "cf.cited_by",
        "cf.cites_doi",
        "cf.cited_by_doi",
    ),
    "persons": (
        "identifiers.id",
        "identifiers.scheme",
        "given_name",
        "family_name",
        "name",
        "affiliations.affiliation.local_identifier",
        "affiliations.affiliation.name",
        "affiliations.affiliation.short_name",
        "affiliations.role",
        "cf.search.family_name",
        "cf.search.given_name",
        "cf.search.name",
    ),
    "organisations": (
        "identifiers.id",
        "identifiers.scheme",
        "name",
        "short_name",
        "website",
        "country",
        "cf.search.name",
    ),
    "venues": (
        "acronym",
        "type",
        "identifiers.scheme",
        "identifiers.value",
        "name",
        "cf.search.name",
    ),
    "grants": (
        "identifiers.scheme",
        "identifiers.value",
        "acronym",
        "currency",
        "website",
        "beneficiaries.identifiers.scheme",
        "beneficiaries.identifiers.value",
        "beneficiaries.name",
        "beneficiaries.short_name",
        "beneficiaries.website",
        "beneficiaries.country",
        "contributions.by.local_identifier",
        "contributions.by.identifiers.scheme",
        "contributions.by.identifiers.value",
        "contributions.by.given_name",
        "contributions.by.family_name",
        "contributions.by.name",
        "contributions.declared_affiliations.local_identifier",
        "contributions.declared_affiliations.identifiers.scheme",
        "contributions.declared_affiliations.identifiers.value",
        "contributions.declared_affiliations.name",
        "contributions.declared_affiliations.short_name",
        "contributions.declared_affiliations.website",
        "contributions.declared_affiliations.country",
        "contributions.role",
        "grant_number",
        "funding_agency.identifiers.scheme",
        "funding_agency.identifiers.value",
        "funding_agency.name",
        "funding_agency.short_name",
        "funding_agency.website",
        "funding_agency.country",
        "funding_stream",
        "cf.search.title",
        "cf.search.title_abstract",
        "cf.funded_amount.from",
        "cf.funded_amount.to",
        "cf.duration.start.from",
        "cf.duration.start.to",
        "cf.duration.end.from",
    ),
    "datasources": (
        "data_source_classification",
        "research_product_type",
        "identifiers.scheme",
        "identifiers.value",
        "acronym",
        "cf.search.name",
    ),
    "topics": (
        "identifiers.scheme",
        "identifiers.value",
        "cf.search.labels",
        "cf.search.language",
    ),
}


def _meta_url(path: str) -> str:
    return f"{SKGIF_PUBLIC_BASE_URL}{path}"


def _exec(skgif_api_manager: APIManager, url: str) -> list[dict]:
    sep = "&" if "?" in url else "?"
    collected: list[dict] = []
    page = 1
    while True:
        op = skgif_api_manager.get_op(f"{url}{sep}page={page}&page_size=100")
        if isinstance(op, tuple):
            msg = f"Operation not found: {url}"
            raise TypeError(msg)
        status, result, _, _ = op.exec(method="get", content_type="application/json")
        if status != 200:
            msg = f"API returned status {status}: {result}"
            raise RuntimeError(msg)
        parsed = json.loads(result)
        if not (isinstance(parsed, dict) and "@graph" in parsed):
            return list(parsed)
        collected.extend(parsed["@graph"])
        meta = parsed["meta"]
        if "next_page" not in meta:
            return collected
        page += 1


def _exec_raw(skgif_api_manager: APIManager, url: str) -> tuple[int, str]:
    op = skgif_api_manager.get_op(url)
    if isinstance(op, tuple):
        msg = f"Operation not found: {url}"
        raise TypeError(msg)
    status, result, _, _ = op.exec(method="get", content_type="application/json")
    return status, result


def _filter_param_description(spec: dict, entity: str) -> str:
    op_spec = spec["paths"][f"/{entity}"]["get"]
    inline_params = [p for p in op_spec["parameters"] if isinstance(p, dict) and p.get("name") == "filter"]
    assert len(inline_params) == 1
    return inline_params[0]["description"]


def _filter_keys_from_description(description: str) -> list[str]:
    return [line.split("`", 2)[1] for line in description.splitlines() if line.startswith("- `")]


class TestNoFilter:
    def test_returns_all_products(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products")
        assert len(results) == 1349


class TestTitleFilter:
    def test_title_search_matches_content(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.search.title:OpenCitations")
        assert results == EXPECTED_SEARCH["cf.search.title:OpenCitations"]

    def test_title_search_no_match(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.search.title:xyznonexistent999")
        assert results == []


class TestIdentifierFilter:
    def test_filter_by_identifier_scheme(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=identifiers.scheme:isbn")
        assert results == EXPECTED_SEARCH["identifiers.scheme:isbn"]

    def test_filter_by_identifier_value(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=identifiers.id:9781402096327")
        assert results == EXPECTED_SEARCH["identifiers.id:9781402096327"]


class TestCombinedFilters:
    def test_title_and_scheme_combined(self, skgif_api_manager: APIManager) -> None:
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=cf.search.title:OpenCitations,identifiers.scheme:doi",
        )
        assert results == EXPECTED_SEARCH["cf.search.title:OpenCitations,identifiers.scheme:doi"]


class TestProductTypeFilter:
    def test_literature_returns_all(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=product_type:literature")
        assert len(results) == 1349

    def test_research_data_returns_empty(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=product_type:research data")
        assert results == []

    def test_research_software_returns_empty(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=product_type:research software")
        assert results == []

    def test_other_returns_empty(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=product_type:other")
        assert results == []

    def test_invalid_type_returns_error(self, skgif_api_manager: APIManager) -> None:
        status, result = _exec_raw(skgif_api_manager, "/skgif/v1/products?filter=product_type:nonexistent")
        assert status == 400
        assert "The value 'nonexistent' is not valid for filter 'product_type'" in result


class TestContributorFamilyNameFilter:
    def test_family_name_match(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=contributions.by.family_name:Slotkin")
        assert results == EXPECTED_SEARCH["contributions.by.family_name:Slotkin"]


class TestContributorGivenNameFilter:
    def test_given_name_match(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=contributions.by.given_name:Theodore A.")
        assert results == EXPECTED_SEARCH["contributions.by.given_name:Theodore A."]


class TestContributorNameFilter:
    def test_org_name_match(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=contributions.by.name:Zenodo")
        assert results == EXPECTED_SEARCH["contributions.by.name:Zenodo"]


class TestContributorLocalIdentifierFilter:
    def test_local_identifier_match(self, skgif_api_manager: APIManager) -> None:
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=contributions.by.local_identifier:https://w3id.org/oc/meta/ra/0601",
        )
        assert results == EXPECTED_SEARCH["contributions.by.local_identifier:https://w3id.org/oc/meta/ra/0601"]


class TestContributorIdentifierSchemeFilter:
    def test_orcid_scheme_match(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=contributions.by.identifiers.scheme:orcid")
        assert len(results) == 73


class TestContributionsOrcidFilter:
    def test_specific_orcid_match(self, skgif_api_manager: APIManager) -> None:
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=cf.contributions_orcid:0000-0003-4747-4708",
        )
        assert results == EXPECTED_SEARCH["cf.contributions_orcid:0000-0003-4747-4708"]


class TestCombinedContributorFilters:
    def test_family_and_given_name_same_agent(self, skgif_api_manager: APIManager) -> None:
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=contributions.by.family_name:Slotkin,contributions.by.given_name:Theodore A.",
        )
        assert (
            results == EXPECTED_SEARCH["contributions.by.family_name:Slotkin,contributions.by.given_name:Theodore A."]
        )


class TestUnsupportedFilter:
    def test_unknown_filter_returns_error(self, skgif_api_manager: APIManager) -> None:
        status, result = _exec_raw(
            skgif_api_manager,
            "/skgif/v1/products?filter=unsupported_field:value",
        )
        assert status == 400
        expected_prefix = (
            "HTTP status code 400: parameter in the request not compliant with the type specified - ValueError: "
            "The filter 'unsupported_field' is not configured, "
            "configured filters are "
            "cf.cited_by, cf.cited_by_doi, cf.cites, cf.cites_doi, "
            "cf.contributions_aff_country, cf.contributions_aff_ror, cf.contributions_orcid, "
            "cf.search.title, cf.search.title_abstract, "
            "contributions.by.family_name, contributions.by.given_name, "
            "contributions.by.identifiers.id, contributions.by.identifiers.scheme, "
            "contributions.by.local_identifier, contributions.by.name, "
            "contributions.declared_affiliations.identifiers.id, "
            "contributions.declared_affiliations.identifiers.scheme, "
            "contributions.declared_affiliations.local_identifier, "
            "contributions.declared_affiliations.name, "
            "contributions.declared_affiliations.short_name, "
            "funding.grant_number, funding.identifiers.id, "
            "funding.identifiers.scheme, funding.local_identifier, "
            "identifiers.id, identifiers.scheme, product_type (line "
        )
        assert result.startswith(expected_prefix)

    def test_unsupported_affiliation_filter_returns_empty(self, skgif_api_manager: APIManager) -> None:
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=contributions.declared_affiliations.name:MIT",
        )
        assert results == []

    def test_unsupported_title_abstract_returns_empty(self, skgif_api_manager: APIManager) -> None:
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=cf.search.title_abstract:OpenCitations",
        )
        assert results == []

    def test_unsupported_combined_with_supported_returns_empty(self, skgif_api_manager: APIManager) -> None:
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=cf.search.title:OpenCitations,cf.search.title_abstract:test",
        )
        assert results == []

    def test_unsupported_combined_with_federated_filter_skips_preamble(self, skgif_api_manager: APIManager) -> None:
        op = skgif_api_manager.get_op(
            "/skgif/v1/products?filter=cf.cites:https://w3id.org/oc/meta/br/06035,funding.local_identifier:grant"
        )
        assert isinstance(op, Operation)
        params = op._prepare_params()
        assert params["filter_preamble"] == ""
        assert params["filter"] == "FILTER(false)"

    def test_unsupported_funding_filter_returns_empty(self, skgif_api_manager: APIManager) -> None:
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=funding.local_identifier:some-grant",
        )
        assert results == []


class TestCitesFilter:
    def test_cites_returns_citing_products(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.cites:https://w3id.org/oc/meta/br/06035")
        local_identifiers = [r["local_identifier"] for r in results]
        assert local_identifiers == ["https://w3id.org/oc/meta/br/0601"]

    def test_cites_no_match(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.cites:https://w3id.org/oc/meta/br/9999999")
        assert results == []


class TestCitedByFilter:
    def test_cited_by_returns_cited_products(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.cited_by:https://w3id.org/oc/meta/br/0601")
        local_identifiers = [r["local_identifier"] for r in results]
        assert local_identifiers == ["https://w3id.org/oc/meta/br/06035"]

    def test_cited_by_no_match(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.cited_by:https://w3id.org/oc/meta/br/9999999")
        assert results == []


class TestCitesDoiFilter:
    def test_cites_doi_resolves_and_returns(self, skgif_api_manager: APIManager) -> None:
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=cf.cites_doi:10.1002/(sici)1097-0215(20000115)85:2<176::aid-ijc5>3.0.co;2-e",
        )
        local_identifiers = [r["local_identifier"] for r in results]
        assert local_identifiers == ["https://w3id.org/oc/meta/br/0601"]

    def test_cites_doi_no_match(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.cites_doi:10.9999/nonexistent")
        assert results == []


class TestCitedByDoiFilter:
    def test_cited_by_doi_resolves_and_returns(self, skgif_api_manager: APIManager) -> None:
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=cf.cited_by_doi:10.1002/(sici)1096-9926(199910)60:4<177::aid-tera1>3.0.co;2-z",
        )
        local_identifiers = [r["local_identifier"] for r in results]
        assert local_identifiers == ["https://w3id.org/oc/meta/br/06035"]

    def test_cited_by_doi_no_match(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.cited_by_doi:10.9999/nonexistent")
        assert results == []


class TestMixedCitationAndRegularFilter:
    def test_cites_with_title_filter(self, skgif_api_manager: APIManager) -> None:
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=cf.cites:https://w3id.org/oc/meta/br/06035,cf.search.title:Response",
        )
        local_identifiers = [r["local_identifier"] for r in results]
        assert local_identifiers == ["https://w3id.org/oc/meta/br/0601"]

    def test_cites_with_nonmatching_title(self, skgif_api_manager: APIManager) -> None:
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=cf.cites:https://w3id.org/oc/meta/br/06035,cf.search.title:xyznonexistent",
        )
        assert results == []


class TestBuiltinFilterOverride:
    def test_skgif_filter_overrides_builtin(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.search.title:OpenCitations")
        assert results == EXPECTED_SEARCH["cf.search.title:OpenCitations"]


class TestCustomParamsInDocumentation:
    def test_filter_in_openapi(self, skgif_api_manager: APIManager) -> None:
        handler = OpenAPIDocumentationHandler(skgif_api_manager)
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        products_op = spec["paths"]["/products"]["get"]
        inline_params = [p for p in products_op["parameters"] if isinstance(p, dict) and "name" in p]
        filter_param = next(p for p in inline_params if p["name"] == "filter")
        assert filter_param["in"] == "query"
        assert filter_param["required"] is False
        assert "cf.search.title" in filter_param["description"]

    def test_builtin_params_absent_from_openapi(self, skgif_api_manager: APIManager) -> None:
        handler = OpenAPIDocumentationHandler(skgif_api_manager)
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        for path_ops in spec["paths"].values():
            for op in path_ops.values():
                ref_names = {p["$ref"].rsplit("/", 1)[-1] for p in op["parameters"] if "$ref" in p}
                for builtin in BUILTIN_PARAMS:
                    assert builtin not in ref_names

    def test_builtin_params_absent_from_html(self, skgif_api_manager: APIManager) -> None:
        handler = HTMLDocumentationHandler(skgif_api_manager)
        _, html = handler.get_documentation()
        assert "require=" not in html
        assert "sort=" not in html
        assert 'id="parameters"' not in html

    def test_result_fields_type_hidden_with_custom_default_format(self, skgif_api_manager: APIManager) -> None:
        handler = HTMLDocumentationHandler(skgif_api_manager)
        _, html = handler.get_documentation()
        assert "Result fields type" not in html

    def test_operation_paths_keep_expected_order(self, skgif_api_manager: APIManager) -> None:
        handler = OpenAPIDocumentationHandler(skgif_api_manager)
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        assert list(spec["paths"]) == OPERATION_PATH_ORDER

    def test_mock_endpoints_in_openapi(self, skgif_api_manager: APIManager) -> None:
        handler = OpenAPIDocumentationHandler(skgif_api_manager)
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        for entity in MOCK_ENDPOINTS:
            assert f"/{entity}" in spec["paths"]
            assert f"/{entity}/{{local_identifier}}" in spec["paths"]

    def test_mock_list_endpoints_have_filter_param(self, skgif_api_manager: APIManager) -> None:
        handler = OpenAPIDocumentationHandler(skgif_api_manager)
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        for entity in MOCK_ENDPOINTS:
            op_spec = spec["paths"][f"/{entity}"]["get"]
            inline_params = [p for p in op_spec["parameters"] if isinstance(p, dict) and p.get("name") == "filter"]
            assert len(inline_params) == 1

    def test_filter_descriptions_keep_expected_order(self, skgif_api_manager: APIManager) -> None:
        handler = OpenAPIDocumentationHandler(skgif_api_manager)
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        for entity, expected_order in FILTER_DESCRIPTION_ORDER.items():
            description = _filter_param_description(spec, entity)
            assert _filter_keys_from_description(description) == list(expected_order)

    # def test_coming_soon_mock_endpoints_are_labelled(self, skgif_api_manager: APIManager) -> None:
    #     handler = OpenAPIDocumentationHandler(skgif_api_manager)
    #     _, yml = handler.get_documentation()
    #     spec = yaml.safe_load(yml)
    #     for entity in COMING_SOON_MOCK_ENDPOINTS:
    #         assert spec["paths"][f"/{entity}"]["get"]["summary"].startswith("Coming soon")
    #         assert spec["paths"][f"/{entity}/{{local_identifier}}"]["get"]["summary"].startswith("Coming soon")


# class TestComingSoonMockEndpoints:
#     def test_list_returns_empty(self, skgif_api_manager: APIManager) -> None:
#         for entity in COMING_SOON_MOCK_ENDPOINTS:
#             results = _exec(skgif_api_manager, f"/skgif/v1/{entity}")
#             assert results == []

#     def test_list_with_filter_returns_empty(self, skgif_api_manager: APIManager) -> None:
#         for entity in COMING_SOON_MOCK_ENDPOINTS:
#             results = _exec(skgif_api_manager, f"/skgif/v1/{entity}?filter={MOCK_FILTER_EXAMPLES[entity]}")
#             assert results == []

#     def test_list_invalid_filter_returns_error(self, skgif_api_manager: APIManager) -> None:
#         for entity in COMING_SOON_MOCK_ENDPOINTS:
#             status, _ = _exec_raw(skgif_api_manager, f"/skgif/v1/{entity}?filter=invalid_field:value")
#             assert status == 400

#     def test_single_returns_404(self, skgif_api_manager: APIManager) -> None:
#         for entity in COMING_SOON_MOCK_ENDPOINTS:
#             status, _ = _exec_raw(skgif_api_manager, f"/skgif/v1/{entity}/example-id")
#             assert status == 404


class TestGrantsEndpoints:
    def test_list_returns_empty(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/grants")
        assert results == []

    def test_list_with_filter_returns_empty(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/grants?filter=grant_number:12345")
        assert results == []

    def test_list_invalid_filter_returns_error(self, skgif_api_manager: APIManager) -> None:
        status, _ = _exec_raw(skgif_api_manager, "/skgif/v1/grants?filter=invalid_field:value")
        assert status == 400

    def test_single_returns_404(self, skgif_api_manager: APIManager) -> None:
        status, _ = _exec_raw(skgif_api_manager, "/skgif/v1/grants/example-id")
        assert status == 404


class TestTopicsEndpoints:
    def test_list_returns_empty(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/topics")
        assert results == []

    def test_list_with_filter_returns_empty(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/topics?filter=cf.search.labels:biology")
        assert results == []

    def test_list_invalid_filter_returns_error(self, skgif_api_manager: APIManager) -> None:
        status, _ = _exec_raw(skgif_api_manager, "/skgif/v1/topics?filter=invalid_field:value")
        assert status == 400

    def test_single_returns_404(self, skgif_api_manager: APIManager) -> None:
        status, _ = _exec_raw(skgif_api_manager, "/skgif/v1/topics/example-id")
        assert status == 404


class TestDatasourcesEndpoints:
    def test_list_returns_empty(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/datasources")
        assert results == []

    def test_list_with_filter_returns_empty(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/datasources?filter=research_product_type:literature")
        assert results == []

    def test_list_invalid_filter_returns_error(self, skgif_api_manager: APIManager) -> None:
        status, _ = _exec_raw(skgif_api_manager, "/skgif/v1/datasources?filter=invalid_field:value")
        assert status == 400

    def test_single_returns_404(self, skgif_api_manager: APIManager) -> None:
        status, _ = _exec_raw(skgif_api_manager, "/skgif/v1/datasources/example-id")
        assert status == 404


class TestPersonsEndpoint:
    def test_returns_all_persons(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/persons")
        assert len(results) == 1869
    def test_filter_by_identifier_scheme(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/persons?filter=identifiers.scheme:orcid")
        assert len(results) == 135
        assert results == EXPECTED_SEARCH["identifiers.scheme:orcid"]
    def test_filter_by_identifier_value(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/persons?filter=identifiers.id:0000-0002-7562-5203")
        assert results == EXPECTED_SEARCH["identifiers.id:0000-0002-7562-5203"]
    def test_filter_by_given_name(self, skgif_api_manager: APIManager) -> None:
        results_1 = _exec(skgif_api_manager, "/skgif/v1/persons?filter=given_name:Greg")
        assert results_1 == EXPECTED_SEARCH["given_name:Greg"]
        results_2 = _exec(skgif_api_manager, "/skgif/v1/persons?filter=cf.search.given_name:Greg")
        assert results_2 == EXPECTED_SEARCH["cf.search.given_name:Greg"]
    def test_filter_by_family_name(self, skgif_api_manager: APIManager) -> None:
        results_1 = _exec(skgif_api_manager, "/skgif/v1/persons?filter=family_name:Nakamura")
        assert results_1 == EXPECTED_SEARCH["family_name:Nakamura"]
        results_2 = _exec(skgif_api_manager, "/skgif/v1/persons?filter=cf.search.family_name:o'")
        assert results_2 == EXPECTED_SEARCH["cf.search.family_name:o'"]
    def test_filter_by_combined_name(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/persons?filter=cf.search.given_name:Silvio,cf.search.family_name:Peroni")
        assert results == EXPECTED_SEARCH["cf.search.given_name:Silvio,cf.search.family_name:Peroni"]


class TestOrganisationEndpoint:
    def test_returns_all_orgs(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/organisations")
        assert len(results) == 32
    def test_filter_by_identifier_scheme(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/organisations?filter=identifiers.scheme:crossref")
        assert len(results) == 21
        assert results == EXPECTED_SEARCH["identifiers.scheme:crossref"]
    def test_filter_by_identifier_value(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/organisations?filter=identifiers.id:140")
        assert results == EXPECTED_SEARCH["identifiers.id:140"]
    def test_filter_by_name(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/organisations?filter=cf.search.name:Mit Press")
        assert results == EXPECTED_SEARCH["cf.search.name:Mit Press"]

class TestVenueEndpoint:
    def test_returns_all_venues(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/venues")
        assert len(results) == 46
    def test_filter_by_type(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/venues?filter=type:conference")
        assert results == EXPECTED_SEARCH["type:conference"]
    def test_filter_by_identifier_scheme(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/venues?filter=identifiers.scheme:issn")
        assert results == EXPECTED_SEARCH["identifiers.scheme:issn"]
    def test_filter_by_identifier_value(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/venues?filter=identifiers.id:2059-481X")
        assert results == EXPECTED_SEARCH["identifiers.id:2059-481X"]
    def test_filter_by_name(self, skgif_api_manager: APIManager) -> None:
        results = _exec(skgif_api_manager, "/skgif/v1/venues?filter=cf.search.name:Digital Libraries")
        assert results == EXPECTED_SEARCH["cf.search.name:Digital Libraries"]

SKGIF_CONTEXT = [
    "https://w3id.org/skg-if/context/1.1.0/skg-if.json",
    "https://w3id.org/skg-if/context/1.0.0/skg-if-api.json",
    {"@base": "https://w3id.org/skg-if/sandbox/oc/"},
]

TOTAL_PRODUCTS = 1349


def _envelope(skgif_api_manager: APIManager, url: str) -> dict:
    op = skgif_api_manager.get_op(url)
    assert isinstance(op, Operation)
    status, result, _, _ = op.exec(method="get", content_type="application/json")
    assert status == 200
    return json.loads(result)


class TestSkgifEnvelope:
    def test_envelope_without_pagination(self, skgif_api_manager: APIManager) -> None:
        result = _envelope(skgif_api_manager, "/skgif/v1/products?filter=cf.search.title:OpenCitations")
        assert result["@context"] == SKGIF_CONTEXT
        assert result["meta"] == {
            "local_identifier": _meta_url(
                "/skgif/v1/products?filter=cf.search.title:OpenCitations&page=1&page_size=10"
            ),
            "entity_type": "search_result_page",
            "part_of": {
                "local_identifier": _meta_url("/skgif/v1/products?filter=cf.search.title:OpenCitations"),
                "entity_type": "search_result",
                "total_items": 7,
                "first_page": {
                    "local_identifier": _meta_url(
                        "/skgif/v1/products?filter=cf.search.title:OpenCitations&page=1&page_size=10"
                    ),
                    "entity_type": "search_result_page",
                },
                "last_page": {
                    "local_identifier": _meta_url(
                        "/skgif/v1/products?filter=cf.search.title:OpenCitations&page=1&page_size=10"
                    ),
                    "entity_type": "search_result_page",
                },
            },
        }
        assert len(result["@graph"]) == 7

    def test_envelope_first_page(self, skgif_api_manager: APIManager) -> None:
        result = _envelope(skgif_api_manager, "/skgif/v1/products?page_size=10")
        meta = result["meta"]
        assert meta["entity_type"] == "search_result_page"
        assert meta["local_identifier"] == _meta_url("/skgif/v1/products?page=1&page_size=10")
        assert meta["next_page"] == {
            "local_identifier": _meta_url("/skgif/v1/products?page=2&page_size=10"),
            "entity_type": "search_result_page",
        }
        assert "prev_page" not in meta
        assert meta["part_of"] == {
            "local_identifier": _meta_url("/skgif/v1/products"),
            "entity_type": "search_result",
            "total_items": TOTAL_PRODUCTS,
            "first_page": {
                "local_identifier": _meta_url("/skgif/v1/products?page=1&page_size=10"),
                "entity_type": "search_result_page",
            },
            "last_page": {
                "local_identifier": _meta_url(f"/skgif/v1/products?page={-(-TOTAL_PRODUCTS // 10)}&page_size=10"),
                "entity_type": "search_result_page",
            },
        }
        assert len(result["@graph"]) == 10

    def test_envelope_middle_page(self, skgif_api_manager: APIManager) -> None:
        result = _envelope(skgif_api_manager, "/skgif/v1/products?page=2&page_size=10")
        meta = result["meta"]
        assert meta["local_identifier"] == _meta_url("/skgif/v1/products?page=2&page_size=10")
        assert meta["next_page"]["local_identifier"] == _meta_url("/skgif/v1/products?page=3&page_size=10")
        assert meta["prev_page"]["local_identifier"] == _meta_url("/skgif/v1/products?page=1&page_size=10")
        assert len(result["@graph"]) == 10

    def test_envelope_last_page(self, skgif_api_manager: APIManager) -> None:
        last_page = -(-TOTAL_PRODUCTS // 10)
        result = _envelope(skgif_api_manager, f"/skgif/v1/products?page={last_page}&page_size=10")
        meta = result["meta"]
        assert "next_page" not in meta
        assert meta["prev_page"]["local_identifier"] == _meta_url(
            f"/skgif/v1/products?page={last_page - 1}&page_size=10"
        )
        assert meta["part_of"]["total_items"] == TOTAL_PRODUCTS

    def test_envelope_with_filter_and_pagination(self, skgif_api_manager: APIManager) -> None:
        result = _envelope(
            skgif_api_manager,
            "/skgif/v1/products?filter=identifiers.scheme:isbn&page=1&page_size=5",
        )
        meta = result["meta"]
        assert meta["local_identifier"] == _meta_url(
            "/skgif/v1/products?filter=identifiers.scheme:isbn&page=1&page_size=5"
        )
        assert meta["part_of"]["local_identifier"] == _meta_url("/skgif/v1/products?filter=identifiers.scheme:isbn")
        assert len(result["@graph"]) == 5

    def test_envelope_page_beyond_total_returns_422(self, skgif_api_manager: APIManager) -> None:
        op = skgif_api_manager.get_op("/skgif/v1/products?page=9999&page_size=10")
        assert isinstance(op, Operation)
        status, result, ctype, _ = op.exec(method="get", content_type="application/json")
        assert status == 422
        assert result == "HTTP status code 422: page 9999 exceeds total pages 135"
        assert ctype == "text/plain"

    def test_single_product_returns_single_entity_envelope(self, skgif_api_manager: APIManager) -> None:
        base_url = "/skgif/v1/products/https://w3id.org/oc/meta/br/0612058700"
        without_pagination = _envelope(skgif_api_manager, base_url)
        with_pagination = _envelope(skgif_api_manager, f"{base_url}?page_size=10&page=1")
        assert with_pagination["meta"]["entity_type"] == "single_entity"
        assert "part_of" not in with_pagination["meta"]
        assert "next_page" not in with_pagination["meta"]
        assert with_pagination["@graph"] == without_pagination["@graph"]

    def test_envelope_context_structure(self, skgif_api_manager: APIManager) -> None:
        result = _envelope(skgif_api_manager, "/skgif/v1/products?page_size=5")
        assert result["@context"] == SKGIF_CONTEXT

    def test_default_page_size_applied(self, skgif_api_manager: APIManager) -> None:
        result = _envelope(skgif_api_manager, "/skgif/v1/products")
        assert len(result["@graph"]) == 10
        meta = result["meta"]
        assert meta == {
            "local_identifier": _meta_url("/skgif/v1/products?page=1&page_size=10"),
            "entity_type": "search_result_page",
            "next_page": {
                "local_identifier": _meta_url("/skgif/v1/products?page=2&page_size=10"),
                "entity_type": "search_result_page",
            },
            "part_of": {
                "local_identifier": _meta_url("/skgif/v1/products"),
                "entity_type": "search_result",
                "total_items": TOTAL_PRODUCTS,
                "first_page": {
                    "local_identifier": _meta_url("/skgif/v1/products?page=1&page_size=10"),
                    "entity_type": "search_result_page",
                },
                "last_page": {
                    "local_identifier": _meta_url("/skgif/v1/products?page=135&page_size=10"),
                    "entity_type": "search_result_page",
                },
            },
        }

    def test_sparql_pagination_is_stable_and_disjoint(self, skgif_api_manager: APIManager) -> None:
        page1 = _envelope(skgif_api_manager, "/skgif/v1/products?page=1&page_size=5")
        page2 = _envelope(skgif_api_manager, "/skgif/v1/products?page=2&page_size=5")
        first_ten = _envelope(skgif_api_manager, "/skgif/v1/products?page=1&page_size=10")
        ids1 = [e["local_identifier"] for e in page1["@graph"]]
        ids2 = [e["local_identifier"] for e in page2["@graph"]]
        ids_ref = [e["local_identifier"] for e in first_ten["@graph"]]
        assert ids1 + ids2 == ids_ref
        assert sorted(set(ids1) & set(ids2)) == []

    def test_total_items_reflects_full_match_count_not_page(self, skgif_api_manager: APIManager) -> None:
        result = _envelope(
            skgif_api_manager, "/skgif/v1/products?filter=cf.search.title:OpenCitations&page=2&page_size=3"
        )
        assert len(result["@graph"]) == 3
        meta = result["meta"]
        assert meta["part_of"]["total_items"] == 7
        prev_id = _meta_url("/skgif/v1/products?filter=cf.search.title:OpenCitations&page=1&page_size=3")
        next_id = _meta_url("/skgif/v1/products?filter=cf.search.title:OpenCitations&page=3&page_size=3")
        assert meta["prev_page"]["local_identifier"] == prev_id
        assert meta["next_page"]["local_identifier"] == next_id

    def test_explicit_page_size_above_max_returns_422(self, skgif_api_manager: APIManager) -> None:
        op = skgif_api_manager.get_op("/skgif/v1/products?page_size=100000")
        assert isinstance(op, Operation)
        status, result, ctype, _ = op.exec(method="get", content_type="application/json")
        assert status == 422
        assert result == "HTTP status code 422: page_size must be <= 100, got 100000"
        assert ctype == "text/plain"

    def test_empty_result_set_is_paginated_with_zero_total(self, skgif_api_manager: APIManager) -> None:
        result = _envelope(skgif_api_manager, "/skgif/v1/products?filter=cf.search.title:xyznonexistent999")
        assert result["@graph"] == []
        meta = result["meta"]
        assert meta == {
            "local_identifier": _meta_url(
                "/skgif/v1/products?filter=cf.search.title:xyznonexistent999&page=1&page_size=10"
            ),
            "entity_type": "search_result_page",
            "part_of": {
                "local_identifier": _meta_url("/skgif/v1/products?filter=cf.search.title:xyznonexistent999"),
                "entity_type": "search_result",
                "total_items": 0,
                "first_page": {
                    "local_identifier": _meta_url(
                        "/skgif/v1/products?filter=cf.search.title:xyznonexistent999&page=1&page_size=10"
                    ),
                    "entity_type": "search_result_page",
                },
                "last_page": {
                    "local_identifier": _meta_url(
                        "/skgif/v1/products?filter=cf.search.title:xyznonexistent999&page=1&page_size=10"
                    ),
                    "entity_type": "search_result_page",
                },
            },
        }
