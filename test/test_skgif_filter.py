# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import json

import yaml

from ramose import APIManager, OpenAPIDocumentationHandler


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


class TestUnsupportedFilter:
    def test_unsupported_filter_returns_error(self, skgif_api_manager):
        status, result = _exec_raw(
            skgif_api_manager,
            "/skgif/v1/products?filter=unsupported_field:value",
        )
        assert status == 500
        expected_prefix = (
            "HTTP status code 500: something unexpected happened - ValueError: "
            "The filter unsupported_field is not supported, "
            "valid filters are cf.search.title, contributions.by.identifiers.id, "
            "identifiers.id, identifiers.scheme (line "
        )
        assert result.startswith(expected_prefix)


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
