# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from openapi_spec_validator import validate

from ramose import APIManager, OpenAPIDocumentationHandler

TESTS_DIR = Path(__file__).resolve().parent / "fixtures"


def _build_handler(*hf_files: str) -> OpenAPIDocumentationHandler:
    paths = [str(TESTS_DIR / f) for f in hf_files]
    am = APIManager(paths, endpoint_override="http://localhost:9999/sparql")
    return OpenAPIDocumentationHandler(am)


class TestOpenAPISpecIsValid:
    @pytest.mark.parametrize(
        "hf_file",
        [
            "mixed_scholarly_crossref.hf",
            "test_scholarly.hf",
            "test_openapi_edge.hf",
            "test_openapi_skgif_like.hf",
        ],
    )
    def test_generated_spec_validates_as_openapi_31(self, hf_file: str) -> None:
        handler = _build_handler(hf_file)
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        validate(spec)


class TestOpenAPIFromMixedScholarlyCrossref:
    def test_generated_yaml_matches_reference(self) -> None:
        handler = _build_handler("mixed_scholarly_crossref.hf")
        status, yml = handler.get_documentation()
        assert status == 200

        generated = yaml.safe_load(yml)
        ref_path = TESTS_DIR / "mixed_scholarly_crossref_openapi.yaml"
        with ref_path.open() as f:
            reference = yaml.safe_load(f.read())

        assert generated == reference


class TestOpenAPIFromScholarlyHf:
    def test_multiple_formats_discovered(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        fmt_enum = spec["components"]["parameters"]["format"]["schema"]["enum"]
        assert "upper" in fmt_enum
        assert "dummyxml" in fmt_enum
        assert "xml" in fmt_enum

    def test_datetime_field_type(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        props = spec["paths"]["/metadata/{dois}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"][
            "items"
        ]["properties"]
        assert props["year"] == {"type": "string", "format": "date-time"}

    def test_output_json_example_included(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        examples = spec["paths"]["/metadata/{dois}"]["get"]["responses"]["200"]["content"]["application/json"].get(
            "examples",
        )
        assert examples is not None
        example_value = examples["example"]["value"]
        assert isinstance(example_value, list)
        assert any(row.get("doi") == "10.1108/JD-12-2013-0166" for row in example_value)


class TestOpenAPIStoreDocumentation:
    def test_store_writes_file(self, tmp_path: Path) -> None:
        handler = _build_handler("mixed_scholarly_crossref.hf")
        out = tmp_path / "out.yaml"
        handler.store_documentation(str(out))
        assert out.exists()
        spec = yaml.safe_load(out.read_text())
        assert spec["openapi"] == "3.1.0"


class TestOpenAPIGetIndex:
    def test_returns_placeholder_string(self) -> None:
        handler = _build_handler("mixed_scholarly_crossref.hf")
        result = handler.get_index()
        assert isinstance(result, str)


class TestOpenAPIWithBaseUrl:
    def test_explicit_base_url(self) -> None:
        handler = _build_handler("mixed_scholarly_crossref.hf")
        status, yml = handler.get_documentation(base_url="mixed")
        assert status == 200
        spec = yaml.safe_load(yml)
        assert spec["servers"][0]["url"] == "http://localhost:5000/mixed"

    def test_base_url_with_leading_slash(self) -> None:
        handler = _build_handler("mixed_scholarly_crossref.hf")
        status, _ = handler.get_documentation(base_url="/mixed")
        assert status == 200


class TestSchemaForRamoseType:
    def test_int_type(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        assert handler._schema_for_ramose_type("int") == {"type": "integer"}

    def test_float_type(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        assert handler._schema_for_ramose_type("float") == {"type": "number"}

    def test_duration_type(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        assert handler._schema_for_ramose_type("duration") == {"type": "string", "format": "duration"}

    def test_unknown_defaults_to_string(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        assert handler._schema_for_ramose_type("xyz") == {"type": "string"}


class TestParseParamTypeShape:
    def test_valid_type_shape(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        t, shape = handler._parse_param_type_shape("str(.+)")
        assert t == "str"
        assert shape == ".+"

    def test_malformed_falls_back(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        t, shape = handler._parse_param_type_shape("garbage")
        assert t == "str"
        assert shape == ".+"


class TestGuessContact:
    def test_empty_returns_none(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        assert handler._guess_contact("") is None
        assert handler._guess_contact(None) is None

    def test_email_detected(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        result = handler._guess_contact("user@example.com")
        assert result == {"email": "user@example.com"}

    def test_non_email_returns_name(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        result = handler._guess_contact("John Doe")
        assert result == {"name": "John Doe"}

    def test_mailto_markdown_link_yields_bare_email(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        result = handler._guess_contact("[contact@opencitations.net](mailto:contact@opencitations.net)")
        assert result == {"email": "contact@opencitations.net"}

    def test_http_markdown_link_yields_name_and_url(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        result = handler._guess_contact("[OpenCitations](https://opencitations.net)")
        assert result == {"name": "OpenCitations", "url": "https://opencitations.net"}

    def test_html_mailto_anchor_yields_bare_email(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        anchor = '<a href="mailto:contact@opencitations.net" target="_blank">contact@opencitations.net</a>'
        assert handler._guess_contact(anchor) == {"email": "contact@opencitations.net"}

    def test_html_anchor_yields_name_and_url(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        anchor = '<a href="https://opencitations.net" target="_blank">OpenCitations</a>'
        assert handler._guess_contact(anchor) == {"name": "OpenCitations", "url": "https://opencitations.net"}


class TestCleanText:
    def test_strips_wrapping_quotes(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        assert handler._clean_text('"hello"') == "hello"
        assert handler._clean_text("'hello'") == "hello"

    def test_none_returns_none(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        assert handler._clean_text(None) is None

    def test_literal_backslash_n(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        assert handler._clean_text("line1\\nline2") == "line1\nline2"


class TestParamHintFromPreprocess:
    def test_empty_preprocess(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        assert handler._param_hint_from_preprocess("", "doi") == ""
        assert handler._param_hint_from_preprocess(None, "doi") == ""

    def test_param_not_mentioned(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        assert handler._param_hint_from_preprocess("lower(other)", "doi") == ""

    def test_param_mentioned(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        result = handler._param_hint_from_preprocess("lower(doi)", "doi")
        assert result == "Note: input is pre-processed by RAMOSE: lower(doi)"


class TestTryParseOutputJson:
    def test_valid_json(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        result = handler._try_parse_output_json('[{"a": 1}]')
        assert result == [{"a": 1}]

    def test_invalid_json(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        assert handler._try_parse_output_json("not json{") is None

    def test_none_input(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        assert handler._try_parse_output_json(None) is None


class TestMediaTypeForFormat:
    def test_known_formats(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        assert handler._media_type_for_format("xml") == "application/xml"
        assert handler._media_type_for_format("ttl") == "text/turtle"
        assert handler._media_type_for_format("nt") == "application/n-triples"

    def test_unknown_format(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        assert handler._media_type_for_format("nonexistent") is None


class TestBuildResponseContent:
    def test_without_error_schema(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        result = handler._build_response_content({"type": "array"}, ["csv", "json"], None, None)
        assert isinstance(result, dict)
        assert set(result.keys()) == {"application/json", "text/csv"}

    def test_extra_format_added(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        ok_and_err = handler._build_response_content(
            {"type": "array"},
            ["csv", "json", "xml"],
            None,
            err_schema_ref="#/components/schemas/Error",
        )
        assert isinstance(ok_and_err, tuple)
        assert set(ok_and_err[1].keys()) == {"application/json", "text/csv", "application/xml"}


class TestExtractParamExamples:
    def test_no_call_value(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        assert handler._extract_param_examples_from_call("/test/{id}", None) == {}

    def test_no_match(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        assert handler._extract_param_examples_from_call("/test/{id}", "/other/path") == {}


class TestOpenAPIFromMixedHf:
    def test_xml_format_in_response_content(self) -> None:
        handler = _build_handler("mixed_scholarly_crossref.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        path = spec["paths"]["/metadata/{dois}"]["get"]
        ok_content = path["responses"]["200"]["content"]
        assert set(ok_content.keys()) == {"application/json", "text/csv", "application/xml"}

    def test_double_underscore_param_description(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        params = spec["paths"]["/metadata/{dois}"]["get"]["parameters"]
        dois_param = next(p for p in params if p.get("name") == "dois")
        assert dois_param["description"] == "Note: input is pre-processed by RAMOSE: lower(dois) --> split_dois(dois)"


class TestOpenAPIEdgeCases:
    def test_trailing_semicolon_in_format(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        fmt_enum = spec["components"]["parameters"]["format"]["schema"]["enum"]
        assert fmt_enum == ["csv", "dummyxml", "json", "xml"]

    def test_multi_param_with_double_underscore(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        params = spec["paths"]["/lookup/{source}/{id}"]["get"]["parameters"]
        id_param = next(p for p in params if p.get("name") == "id")
        assert id_param["description"] == "Multiple values can be provided separated by '__'."

    def test_middle_param_example_extracted(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        result = handler._extract_param_examples_from_call("/lookup/{source}/{id}", "/lookup/wikidata/Q42")
        assert result["source"] == "wikidata"
        assert result["id"] == "Q42"


class TestOpenAPIDisableParams:
    def test_disabled_params_absent_from_components(self) -> None:
        handler = _build_handler("test_openapi_skgif_like.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        assert "parameters" not in spec["components"]

    def test_error_schema_still_present(self) -> None:
        handler = _build_handler("test_openapi_skgif_like.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        assert "Error" in spec["components"]["schemas"]

    def test_operation_has_no_common_param_refs(self) -> None:
        handler = _build_handler("test_openapi_skgif_like.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        params = spec["paths"]["/products/{local_id}"]["get"]["parameters"]
        ref_names = {p["$ref"].rsplit("/", 1)[-1] for p in params if "$ref" in p}
        assert ref_names == set()


class TestSingleFormatResponseWhenFormatDisabled:
    def test_only_declared_media_type_advertised(self) -> None:
        handler = _build_handler("test_openapi_skgif_like.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        content = spec["paths"]["/products/{local_id}"]["get"]["responses"]["200"]["content"]
        assert set(content.keys()) == {"application/ld+json"}

    def test_error_response_is_single_application_json(self) -> None:
        handler = _build_handler("test_openapi_skgif_like.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        error_content = spec["paths"]["/products/{local_id}"]["get"]["responses"]["default"]["content"]
        assert set(error_content.keys()) == {"application/json"}
        assert error_content["application/json"]["schema"] == {"$ref": "#/components/schemas/Error"}

    def test_jsonld_example_attached(self) -> None:
        handler = _build_handler("test_openapi_skgif_like.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        content = spec["paths"]["/products/{local_id}"]["get"]["responses"]["200"]["content"]
        example_value = content["application/ld+json"]["examples"]["example"]["value"]
        assert example_value["meta"] == {"total_items": 1}
        assert example_value["@graph"][0]["local_identifier"] == "R42"


class TestFormatMediaTypeDeclaration:
    def test_declared_mime_parsed(self) -> None:
        handler = _build_handler("test_openapi_skgif_like.hf")
        assert handler._format_media_type_map({"format": "skgif,to_skgif,application/ld+json"}) == {
            "skgif": "application/ld+json",
        }

    def test_format_without_mime_is_ignored(self) -> None:
        handler = _build_handler("test_openapi_skgif_like.hf")
        assert handler._format_media_type_map({"format": "xml,to_xml"}) == {}

    def test_single_response_media_type_uses_declared_mime(self) -> None:
        handler = _build_handler("test_openapi_skgif_like.hf")
        op = {"default_format": "skgif", "format": "skgif,to_skgif,application/ld+json"}
        assert handler._single_response_media_type(op) == "application/ld+json"

    def test_single_response_media_type_defaults_to_csv(self) -> None:
        handler = _build_handler("test_openapi_skgif_like.hf")
        assert handler._single_response_media_type({}) == "text/csv"


class TestSwaggerUI:
    def test_returns_self_contained_html(self) -> None:
        handler = _build_handler("test_openapi_skgif_like.hf")
        status, html = handler.get_swagger_ui()
        assert status == 200
        assert html.startswith("<!DOCTYPE html>")
        assert "SwaggerUIBundle({spec:" in html

    def test_inlines_spec_with_declared_media_type(self) -> None:
        handler = _build_handler("test_openapi_skgif_like.hf")
        _, html = handler.get_swagger_ui()
        assert "application/ld+json" in html

    def test_inlined_bundle_does_not_break_script_tags(self) -> None:
        handler = _build_handler("test_openapi_skgif_like.hf")
        _, html = handler.get_swagger_ui()
        assert html.count("</script>") == 2


class TestOpenAPIInferSchemaFromOutputJson:
    def test_inferred_schema_is_object(self) -> None:
        handler = _build_handler("test_openapi_skgif_like.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        schema = spec["paths"]["/products/{local_id}"]["get"]["responses"]["200"]["content"]["application/ld+json"][
            "schema"
        ]
        assert schema["type"] == "object"
        assert "@context" in schema["properties"]
        assert "meta" in schema["properties"]
        assert "@graph" in schema["properties"]

    def test_nested_properties_inferred(self) -> None:
        handler = _build_handler("test_openapi_skgif_like.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        schema = spec["paths"]["/products/{local_id}"]["get"]["responses"]["200"]["content"]["application/ld+json"][
            "schema"
        ]
        meta_props = schema["properties"]["meta"]["properties"]
        assert meta_props["total_items"] == {"type": "integer"}

    def test_graph_items_have_properties(self) -> None:
        handler = _build_handler("test_openapi_skgif_like.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        schema = spec["paths"]["/products/{local_id}"]["get"]["responses"]["200"]["content"]["application/ld+json"][
            "schema"
        ]
        graph_item = schema["properties"]["@graph"]["items"]
        assert graph_item["properties"]["local_identifier"] == {"type": "string"}
        assert graph_item["properties"]["score"] == {"type": "number"}
        assert graph_item["properties"]["published"] == {"type": "boolean"}

    def test_heterogeneous_array_has_no_items(self) -> None:
        handler = _build_handler("test_openapi_skgif_like.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        schema = spec["paths"]["/products/{local_id}"]["get"]["responses"]["200"]["content"]["application/ld+json"][
            "schema"
        ]
        context_schema = schema["properties"]["@context"]
        assert context_schema["type"] == "array"
        assert "items" not in context_schema

    def test_field_type_takes_priority_over_inference(self) -> None:
        handler = _build_handler("test_scholarly.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        schema = spec["paths"]["/metadata/{dois}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert schema["type"] == "array"
        assert "properties" in schema["items"]
        assert "doi" in schema["items"]["properties"]


class TestInferSchemaFromValue:
    def test_string(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        assert handler._infer_schema_from_value("hello") == {"type": "string"}

    def test_integer(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        assert handler._infer_schema_from_value(42) == {"type": "integer"}

    def test_float(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        assert handler._infer_schema_from_value(3.14) == {"type": "number"}

    def test_boolean_true(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        true_val = True
        assert handler._infer_schema_from_value(true_val) == {"type": "boolean"}

    def test_boolean_false_not_integer(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        false_val = False
        assert handler._infer_schema_from_value(false_val) == {"type": "boolean"}

    def test_none(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        assert handler._infer_schema_from_value(None) == {}

    def test_empty_list(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        assert handler._infer_schema_from_value([]) == {"type": "array"}

    def test_homogeneous_list(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        assert handler._infer_schema_from_value(["a", "b"]) == {"type": "array", "items": {"type": "string"}}

    def test_heterogeneous_list(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        assert handler._infer_schema_from_value(["a", 1]) == {"type": "array"}

    def test_empty_dict(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        assert handler._infer_schema_from_value({}) == {"type": "object"}

    def test_nested_dict(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        result = handler._infer_schema_from_value({"name": "test", "count": 5})
        assert result == {
            "type": "object",
            "properties": {"name": {"type": "string"}, "count": {"type": "integer"}},
        }


class TestBuildInfoMetadataNormalization:
    LICENSE = (
        "This document is licensed with a "
        "[Creative Commons Attribution 4.0 International License]"
        "(https://creativecommons.org/licenses/by/4.0/legalcode), while the REST API itself "
        "has been created using [RAMOSE](https://github.com/opencitations/ramose)."
    )

    def test_version_strips_leading_word(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        info = handler._build_info({"version": "Version 1.1.1 (2022-12-22)"})
        assert info["version"] == "1.1.1 (2022-12-22)"

    def test_title_markup_is_stripped(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        info = handler._build_info({"title": '<a href="https://x.org">My *cool* API</a>'})
        assert info["title"] == "My cool API"

    def test_license_is_plain_text_with_url(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        info = handler._build_info({"license": self.LICENSE})
        license_obj = info["license"]
        assert isinstance(license_obj, dict)
        assert "[" not in license_obj["name"]
        assert "*" not in license_obj["name"]
        assert license_obj["name"].startswith("This document is licensed with a Creative Commons")
        assert license_obj["url"] == "https://creativecommons.org/licenses/by/4.0/legalcode"

    def test_contact_email_is_normalized(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        info = handler._build_info({"contacts": "[x@opencitations.net](mailto:x@opencitations.net)"})
        assert info["contact"] == {"email": "x@opencitations.net"}

    def test_html_license_is_plain_text_with_url(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        anchor = '<a href="https://opensource.org/licenses/ISC" target="_blank">ISC</a>'
        info = handler._build_info({"license": anchor})
        assert info["license"] == {"name": "ISC", "url": "https://opensource.org/licenses/ISC"}

    def test_html_contact_email_is_normalized(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        anchor = '<a href="mailto:dev@opencitations.net" target="_blank">dev@opencitations.net</a>'
        info = handler._build_info({"contacts": anchor})
        assert info["contact"] == {"email": "dev@opencitations.net"}


class TestCsvExample:
    def test_tabular_rows_become_csv(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        result = handler._csv_example([{"id": "x", "title": "A"}, {"id": "y", "title": "B"}])
        assert result == "id,title\r\nx,A\r\ny,B\r\n"

    def test_missing_keys_are_filled(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        result = handler._csv_example([{"a": "1"}, {"b": "2"}])
        assert result == "a,b\r\n1,\r\n,2\r\n"

    def test_nested_rows_return_none(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        assert handler._csv_example([{"id": "x", "authors": ["A", "B"]}]) is None

    def test_empty_or_non_list_return_none(self) -> None:
        handler = _build_handler("test_openapi_edge.hf")
        assert handler._csv_example([]) is None
        assert handler._csv_example({"id": "x"}) is None
