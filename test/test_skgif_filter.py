# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import json

import yaml

from ramose import APIManager, HTMLDocumentationHandler, OpenAPIDocumentationHandler
from ramose.hash_format import BUILTIN_PARAMS


def _exec(skgif_api_manager: APIManager, url: str) -> list[dict]:
    op = skgif_api_manager.get_op(url)
    if isinstance(op, tuple):
        raise TypeError(f"Operation not found: {url}")
    status, result, _ = op.exec(method="get", content_type="application/json")
    if status != 200:
        raise RuntimeError(f"API returned status {status}: {result}")
    return json.loads(result)


def _exec_raw(skgif_api_manager: APIManager, url: str) -> tuple[int, str]:
    op = skgif_api_manager.get_op(url)
    if isinstance(op, tuple):
        raise TypeError(f"Operation not found: {url}")
    status, result, _ = op.exec(method="get", content_type="application/json")
    return status, result


class TestNoFilter:
    def test_returns_all_products(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products")
        assert len(results) == 1098


class TestTitleFilter:
    def test_title_search_matches_content(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.search.title:adaptive")
        assert results == [
            {"br_uri": "https://w3id.org/oc/meta/br/0612058700", "title": "Adaptive Environmental Management"},
            {
                "br_uri": "https://w3id.org/oc/meta/br/0615065546",
                "title": "Adaptive System: The Study Of Information, Pattern, And Behavior",
            },
            {
                "br_uri": "https://w3id.org/oc/meta/br/0615066104",
                "title": "Boon Or Bust? Access To Electronic Publishing By Individuals Using Adaptive Computer Technology",
            },
        ]

    def test_title_search_no_match(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.search.title:xyznonexistent999")
        assert results == []


class TestIdentifierFilter:
    def test_filter_by_identifier_scheme(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=identifiers.scheme:isbn")
        assert results == [
            {"br_uri": "https://w3id.org/oc/meta/br/0612058700", "title": "Adaptive Environmental Management"},
            {
                "br_uri": "https://w3id.org/oc/meta/br/061702785338",
                "title": "Advances In Intelligent Systems And Computing",
            },
            {
                "br_uri": "https://w3id.org/oc/meta/br/06302611905",
                "title": "Communications In Computer And Information Science",
            },
            {"br_uri": "https://w3id.org/oc/meta/br/06402611083", "title": "Lecture Notes In Computer Science"},
            {"br_uri": "https://w3id.org/oc/meta/br/06603870331", "title": "OECD Economic Surveys: China 2022"},
            {"br_uri": "https://w3id.org/oc/meta/br/0611064823", "title": "The Semantic Web"},
            {"br_uri": "https://w3id.org/oc/meta/br/06401297735", "title": "The Semantic Web"},
            {"br_uri": "https://w3id.org/oc/meta/br/0611064985", "title": "The Semantic Web"},
            {
                "br_uri": "https://w3id.org/oc/meta/br/0612056541",
                "title": "The Semantic Web: ESWC 2014 Satellite Events",
            },
        ]

    def test_filter_by_identifier_value(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=identifiers.id:9781402096327")
        assert results == [
            {"br_uri": "https://w3id.org/oc/meta/br/0612058700", "title": "Adaptive Environmental Management"},
        ]


class TestCombinedFilters:
    def test_title_and_scheme_combined(self, skgif_api_manager):
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=cf.search.title:adaptive,identifiers.scheme:isbn",
        )
        assert results == [
            {"br_uri": "https://w3id.org/oc/meta/br/0612058700", "title": "Adaptive Environmental Management"},
        ]


class TestProductTypeFilter:
    def test_literature_returns_all(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=product_type:literature")
        assert len(results) == 1098

    def test_research_data_returns_empty(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=product_type:research data")
        assert results == []

    def test_research_software_returns_empty(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=product_type:research software")
        assert results == []

    def test_other_returns_empty(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=product_type:other")
        assert results == []

    def test_invalid_type_returns_error(self, skgif_api_manager):
        status, result = _exec_raw(skgif_api_manager, "/skgif/v1/products?filter=product_type:nonexistent")
        assert status == 500
        assert "The product type 'nonexistent' is not valid" in result


class TestContributorFamilyNameFilter:
    def test_family_name_match(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=contributions.by.family_name:Slotkin")
        assert results == [
            {
                "br_uri": "https://w3id.org/oc/meta/br/0601",
                "title": "Response To The Letter Of Hanley Et Al. "
                "([1999] Teratology 59:323-324), Concerning The Article By Roy Et Al. "
                "([1998] Teratology 58:62-68)",
            },
        ]


class TestContributorGivenNameFilter:
    def test_given_name_match(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=contributions.by.given_name:Theodore A.")
        assert results == [
            {
                "br_uri": "https://w3id.org/oc/meta/br/0601",
                "title": "Response To The Letter Of Hanley Et Al. "
                "([1999] Teratology 59:323-324), Concerning The Article By Roy Et Al. "
                "([1998] Teratology 58:62-68)",
            },
        ]


class TestContributorNameFilter:
    def test_org_name_match(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=contributions.by.name:Zenodo")
        assert results == [
            {
                "br_uri": "https://w3id.org/oc/meta/br/060504627",
                "title": "Classes Of Errors In DOI Names (Data Management Plan)",
            },
            {
                "br_uri": "https://w3id.org/oc/meta/br/060504628",
                "title": "Classes Of Errors In DOI Names (Data Management Plan)",
            },
            {
                "br_uri": "https://w3id.org/oc/meta/br/060504675",
                "title": "Cleaning Different Types Of DOI Errors Found In Cited References On Crossref Using Automated Methods",
            },
        ]


class TestContributorLocalIdentifierFilter:
    def test_local_identifier_match(self, skgif_api_manager):
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=contributions.by.local_identifier:https://w3id.org/oc/meta/ra/0601",
        )
        assert results == [
            {
                "br_uri": "https://w3id.org/oc/meta/br/0601",
                "title": "Response To The Letter Of Hanley Et Al. "
                "([1999] Teratology 59:323-324), Concerning The Article By Roy Et Al. "
                "([1998] Teratology 58:62-68)",
            },
        ]


class TestContributorIdentifierSchemeFilter:
    def test_orcid_scheme_match(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=contributions.by.identifiers.scheme:orcid")
        assert len(results) == 73


class TestContributionsOrcidFilter:
    def test_specific_orcid_match(self, skgif_api_manager):
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=cf.contributions_orcid:0000-0003-4747-4708",
        )
        assert results == [
            {
                "br_uri": "https://w3id.org/oc/meta/br/06035",
                "title": "H-ras, But Not N-ras, Induces An Invasive Phenotype In Human Breast Epithelial Cells: "
                "A Role For MMP-2 In The H-Ras-Induced Invasive Phenotype",
            },
        ]


class TestCombinedContributorFilters:
    def test_family_and_given_name_same_agent(self, skgif_api_manager):
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=contributions.by.family_name:Slotkin,contributions.by.given_name:Theodore A.",
        )
        assert results == [
            {
                "br_uri": "https://w3id.org/oc/meta/br/0601",
                "title": "Response To The Letter Of Hanley Et Al. "
                "([1999] Teratology 59:323-324), Concerning The Article By Roy Et Al. "
                "([1998] Teratology 58:62-68)",
            },
        ]


class TestUnsupportedFilter:
    def test_unknown_filter_returns_error(self, skgif_api_manager):
        status, result = _exec_raw(
            skgif_api_manager,
            "/skgif/v1/products?filter=unsupported_field:value",
        )
        assert status == 500
        expected_prefix = (
            "HTTP status code 500: something unexpected happened - ValueError: "
            "The filter unsupported_field is not supported, "
            "valid filters are cf.cited_by, cf.cited_by_doi, cf.cites, cf.cites_doi, "
            "cf.contributions_orcid, cf.search.title, "
            "contributions.by.family_name, contributions.by.given_name, "
            "contributions.by.identifiers.id, contributions.by.identifiers.scheme, "
            "contributions.by.local_identifier, contributions.by.name, "
            "identifiers.id, identifiers.scheme, product_type (line "
        )
        assert result.startswith(expected_prefix)

    def test_known_unsupported_filter_returns_same_error(self, skgif_api_manager):
        status, result = _exec_raw(
            skgif_api_manager,
            "/skgif/v1/products?filter=contributions.declared_affiliations.name:MIT",
        )
        assert status == 500
        expected_prefix = (
            "HTTP status code 500: something unexpected happened - ValueError: "
            "The filter contributions.declared_affiliations.name is not supported, "
            "valid filters are cf.cited_by, cf.cited_by_doi, cf.cites, cf.cites_doi, "
            "cf.contributions_orcid, cf.search.title, "
            "contributions.by.family_name, contributions.by.given_name, "
            "contributions.by.identifiers.id, contributions.by.identifiers.scheme, "
            "contributions.by.local_identifier, contributions.by.name, "
            "identifiers.id, identifiers.scheme, product_type (line "
        )
        assert result.startswith(expected_prefix)

    def test_title_abstract_not_supported(self, skgif_api_manager):
        status, result = _exec_raw(
            skgif_api_manager,
            "/skgif/v1/products?filter=cf.search.title_abstract:adaptive",
        )
        assert status == 500
        assert "The filter cf.search.title_abstract is not supported" in result


class TestCitesFilter:
    def test_cites_returns_citing_products(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.cites:https://w3id.org/oc/meta/br/06035")
        br_uris = [r["br_uri"] for r in results]
        assert br_uris == ["https://w3id.org/oc/meta/br/0601"]

    def test_cites_no_match(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.cites:https://w3id.org/oc/meta/br/9999999")
        assert results == []


class TestCitedByFilter:
    def test_cited_by_returns_cited_products(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.cited_by:https://w3id.org/oc/meta/br/0601")
        br_uris = [r["br_uri"] for r in results]
        assert br_uris == ["https://w3id.org/oc/meta/br/06035"]

    def test_cited_by_no_match(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.cited_by:https://w3id.org/oc/meta/br/9999999")
        assert results == []


class TestCitesDoiFilter:
    def test_cites_doi_resolves_and_returns(self, skgif_api_manager):
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=cf.cites_doi:10.1002/(sici)1097-0215(20000115)85:2<176::aid-ijc5>3.0.co;2-e",
        )
        br_uris = [r["br_uri"] for r in results]
        assert br_uris == ["https://w3id.org/oc/meta/br/0601"]

    def test_cites_doi_no_match(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.cites_doi:10.9999/nonexistent")
        assert results == []


class TestCitedByDoiFilter:
    def test_cited_by_doi_resolves_and_returns(self, skgif_api_manager):
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=cf.cited_by_doi:10.1002/(sici)1096-9926(199910)60:4<177::aid-tera1>3.0.co;2-z",
        )
        br_uris = [r["br_uri"] for r in results]
        assert br_uris == ["https://w3id.org/oc/meta/br/06035"]

    def test_cited_by_doi_no_match(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.cited_by_doi:10.9999/nonexistent")
        assert results == []


class TestMixedCitationAndRegularFilter:
    def test_cites_with_title_filter(self, skgif_api_manager):
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=cf.cites:https://w3id.org/oc/meta/br/06035,cf.search.title:Response",
        )
        br_uris = [r["br_uri"] for r in results]
        assert br_uris == ["https://w3id.org/oc/meta/br/0601"]

    def test_cites_with_nonmatching_title(self, skgif_api_manager):
        results = _exec(
            skgif_api_manager,
            "/skgif/v1/products?filter=cf.cites:https://w3id.org/oc/meta/br/06035,cf.search.title:xyznonexistent",
        )
        assert results == []


class TestBuiltinFilterOverride:
    def test_skgif_filter_overrides_builtin(self, skgif_api_manager):
        results = _exec(skgif_api_manager, "/skgif/v1/products?filter=cf.search.title:adaptive")
        assert results == [
            {"br_uri": "https://w3id.org/oc/meta/br/0612058700", "title": "Adaptive Environmental Management"},
            {
                "br_uri": "https://w3id.org/oc/meta/br/0615065546",
                "title": "Adaptive System: The Study Of Information, Pattern, And Behavior",
            },
            {
                "br_uri": "https://w3id.org/oc/meta/br/0615066104",
                "title": "Boon Or Bust? Access To Electronic Publishing By Individuals Using Adaptive Computer Technology",
            },
        ]


class TestCustomParamsInDocumentation:
    def test_filter_in_openapi(self, skgif_api_manager):
        handler = OpenAPIDocumentationHandler(skgif_api_manager)
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        products_op = spec["paths"]["/products"]["get"]
        inline_params = [p for p in products_op["parameters"] if isinstance(p, dict) and "name" in p]
        filter_param = next(p for p in inline_params if p["name"] == "filter")
        assert filter_param["in"] == "query"
        assert filter_param["required"] is False
        assert "cf.search.title" in filter_param["description"]

    def test_builtin_params_absent_from_openapi(self, skgif_api_manager):
        handler = OpenAPIDocumentationHandler(skgif_api_manager)
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        for path_ops in spec["paths"].values():
            for op in path_ops.values():
                ref_names = {p["$ref"].rsplit("/", 1)[-1] for p in op["parameters"] if "$ref" in p}
                for builtin in BUILTIN_PARAMS:
                    assert builtin not in ref_names

    def test_builtin_params_absent_from_html(self, skgif_api_manager):
        handler = HTMLDocumentationHandler(skgif_api_manager)
        _, html = handler.get_documentation()
        assert "require=" not in html
        assert "sort=" not in html
        assert 'id="parameters"' not in html
