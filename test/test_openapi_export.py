# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from pathlib import Path

import yaml

from ramose import APIManager, OpenAPIDocumentationHandler

TESTS_DIR = Path(__file__).resolve().parent.parent / "tests"


def _build_handler(*hf_files):
    paths = [str(TESTS_DIR / f) for f in hf_files]
    am = APIManager(paths, endpoint_override="http://localhost:9999/sparql")
    return OpenAPIDocumentationHandler(am)


class TestOpenAPIFromMixedScholarlyCrossref:
    def test_generated_yaml_matches_reference(self):
        handler = _build_handler("mixed_scholarly_crossref.hf")
        status, yml = handler.get_documentation()
        assert status == 200

        generated = yaml.safe_load(yml)
        ref_path = TESTS_DIR / "mixed_scholarly_crossref_openapi.yaml"
        with ref_path.open() as f:
            reference = yaml.safe_load(f.read())

        assert generated == reference


class TestOpenAPIFromScholarlyHf:
    def test_post_method_preserved(self):
        handler = _build_handler("test_scholarly.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        assert spec["x-ramose-sparql-method"] == "post"

    def test_multiple_formats_discovered(self):
        handler = _build_handler("test_scholarly.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        fmt_enum = spec["components"]["parameters"]["format"]["schema"]["enum"]
        assert "upper" in fmt_enum
        assert "dummyxml" in fmt_enum
        assert "xml" in fmt_enum

    def test_datetime_field_type(self):
        handler = _build_handler("test_scholarly.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        props = spec["paths"]["/metadata/{dois}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["items"]["properties"]
        assert props["year"] == {"type": "string", "format": "date-time"}

    def test_output_json_example_included(self):
        handler = _build_handler("test_scholarly.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        examples = spec["paths"]["/metadata/{dois}"]["get"]["responses"]["200"]["content"]["application/json"].get("examples")
        assert examples is not None
        example_value = examples["example"]["value"]
        assert isinstance(example_value, list)
        assert any(row.get("doi") == "10.1108/JD-12-2013-0166" for row in example_value)


class TestOpenAPIStoreDocumentation:
    def test_store_writes_file(self, tmp_path):
        handler = _build_handler("mixed_scholarly_crossref.hf")
        out = tmp_path / "out.yaml"
        handler.store_documentation(str(out))
        assert out.exists()
        spec = yaml.safe_load(out.read_text())
        assert spec["openapi"] == "3.0.3"


class TestOpenAPIGetIndex:
    def test_returns_placeholder_string(self):
        handler = _build_handler("mixed_scholarly_crossref.hf")
        result = handler.get_index()
        assert isinstance(result, str)


class TestOpenAPIWithBaseUrl:
    def test_explicit_base_url(self):
        handler = _build_handler("mixed_scholarly_crossref.hf")
        status, yml = handler.get_documentation(base_url="mixed")
        assert status == 200
        spec = yaml.safe_load(yml)
        assert spec["servers"][0]["url"] == "http://localhost:5000/mixed"

    def test_base_url_with_leading_slash(self):
        handler = _build_handler("mixed_scholarly_crossref.hf")
        status, _ = handler.get_documentation(base_url="/mixed")
        assert status == 200


class TestSchemaForRamoseType:
    def test_int_type(self):
        handler = _build_handler("test_scholarly.hf")
        assert handler._schema_for_ramose_type("int") == {"type": "integer"}

    def test_float_type(self):
        handler = _build_handler("test_scholarly.hf")
        assert handler._schema_for_ramose_type("float") == {"type": "number"}

    def test_duration_type(self):
        handler = _build_handler("test_scholarly.hf")
        assert handler._schema_for_ramose_type("duration") == {"type": "string", "format": "duration"}

    def test_unknown_defaults_to_string(self):
        handler = _build_handler("test_scholarly.hf")
        assert handler._schema_for_ramose_type("xyz") == {"type": "string"}


class TestParseParamTypeShape:
    def test_valid_type_shape(self):
        handler = _build_handler("test_scholarly.hf")
        t, shape = handler._parse_param_type_shape("str(.+)")
        assert t == "str"
        assert shape == ".+"

    def test_malformed_falls_back(self):
        handler = _build_handler("test_scholarly.hf")
        t, shape = handler._parse_param_type_shape("garbage")
        assert t == "str"
        assert shape == ".+"


class TestGuessContact:
    def test_empty_returns_none(self):
        handler = _build_handler("test_scholarly.hf")
        assert handler._guess_contact("") is None
        assert handler._guess_contact(None) is None

    def test_email_detected(self):
        handler = _build_handler("test_scholarly.hf")
        result = handler._guess_contact("user@example.com")
        assert result == {"email": "user@example.com"}

    def test_non_email_returns_name(self):
        handler = _build_handler("test_scholarly.hf")
        result = handler._guess_contact("John Doe")
        assert result == {"name": "John Doe"}


class TestCleanText:
    def test_strips_wrapping_quotes(self):
        handler = _build_handler("test_scholarly.hf")
        assert handler._clean_text('"hello"') == "hello"
        assert handler._clean_text("'hello'") == "hello"

    def test_none_returns_none(self):
        handler = _build_handler("test_scholarly.hf")
        assert handler._clean_text(None) is None

    def test_literal_backslash_n(self):
        handler = _build_handler("test_scholarly.hf")
        assert handler._clean_text("line1\\nline2") == "line1\nline2"


class TestParamHintFromPreprocess:
    def test_empty_preprocess(self):
        handler = _build_handler("test_scholarly.hf")
        assert handler._param_hint_from_preprocess("", "doi") == ""
        assert handler._param_hint_from_preprocess(None, "doi") == ""

    def test_param_not_mentioned(self):
        handler = _build_handler("test_scholarly.hf")
        assert handler._param_hint_from_preprocess("lower(other)", "doi") == ""

    def test_param_mentioned(self):
        handler = _build_handler("test_scholarly.hf")
        result = handler._param_hint_from_preprocess("lower(doi)", "doi")
        assert result == "Note: input is pre-processed by RAMOSE: lower(doi)"


class TestTryParseOutputJson:
    def test_valid_json(self):
        handler = _build_handler("test_scholarly.hf")
        result = handler._try_parse_output_json('[{"a": 1}]')
        assert result == [{"a": 1}]

    def test_invalid_json(self):
        handler = _build_handler("test_scholarly.hf")
        assert handler._try_parse_output_json("not json{") is None

    def test_none_input(self):
        handler = _build_handler("test_scholarly.hf")
        assert handler._try_parse_output_json(None) is None


class TestMediaTypeForFormat:
    def test_known_formats(self):
        handler = _build_handler("test_scholarly.hf")
        assert handler._media_type_for_format("xml") == "application/xml"
        assert handler._media_type_for_format("ttl") == "text/turtle"
        assert handler._media_type_for_format("nt") == "application/n-triples"

    def test_unknown_format(self):
        handler = _build_handler("test_scholarly.hf")
        assert handler._media_type_for_format("nonexistent") is None


class TestBuildResponseContent:
    def test_without_error_schema(self):
        handler = _build_handler("test_scholarly.hf")
        result = handler._build_response_content(
            {"type": "array"}, ["csv", "json"], None, None
        )
        assert isinstance(result, dict)
        assert set(result.keys()) == {"application/json", "text/csv"}

    def test_extra_format_added(self):
        handler = _build_handler("test_scholarly.hf")
        ok_and_err = handler._build_response_content(
            {"type": "array"}, ["csv", "json", "xml"],
            None, "#/components/schemas/Error"
        )
        assert isinstance(ok_and_err, tuple)
        assert set(ok_and_err[1].keys()) == {"application/json", "text/csv", "application/xml"}


class TestExtractParamExamples:
    def test_no_call_value(self):
        handler = _build_handler("test_scholarly.hf")
        assert handler._extract_param_examples_from_call("/test/{id}", None) == {}

    def test_no_match(self):
        handler = _build_handler("test_scholarly.hf")
        assert handler._extract_param_examples_from_call("/test/{id}", "/other/path") == {}

class TestOpenAPIFromMixedHf:
    def test_xml_format_in_response_content(self):
        handler = _build_handler("mixed_scholarly_crossref.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        path = spec["paths"]["/metadata/{dois}"]["get"]
        ok_content = path["responses"]["200"]["content"]
        assert set(ok_content.keys()) == {"application/json", "text/csv", "application/xml"}

    def test_vendor_extension_keys(self):
        handler = _build_handler("test_scholarly.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        path = spec["paths"]["/metadata/{dois}"]["get"]
        ramose_ext = path["x-ramose"]
        assert set(ramose_ext.keys()) == {"preprocess", "call", "sparql_in_description"}

    def test_double_underscore_param_description(self):
        handler = _build_handler("test_scholarly.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        params = spec["paths"]["/metadata/{dois}"]["get"]["parameters"]
        dois_param = next(p for p in params if p.get("name") == "dois")
        assert dois_param["description"] == "Note: input is pre-processed by RAMOSE: lower(dois) --> split_dois(dois)"


class TestOpenAPIEdgeCases:
    def test_trailing_semicolon_in_format(self):
        handler = _build_handler("test_openapi_edge.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        fmt_enum = spec["components"]["parameters"]["format"]["schema"]["enum"]
        assert fmt_enum == ["csv", "dummyxml", "json", "xml"]

    def test_postprocess_vendor_extension(self):
        handler = _build_handler("test_openapi_edge.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        path = spec["paths"]["/lookup/{source}/{id}"]["get"]
        ramose_ext = path["x-ramose"]
        assert ramose_ext["postprocess"] == "my_post()"

    def test_multi_param_with_double_underscore(self):
        handler = _build_handler("test_openapi_edge.hf")
        _, yml = handler.get_documentation()
        spec = yaml.safe_load(yml)
        params = spec["paths"]["/lookup/{source}/{id}"]["get"]["parameters"]
        id_param = next(p for p in params if p.get("name") == "id")
        assert id_param["description"] == "Multiple values can be provided separated by '__'."

    def test_middle_param_example_extracted(self):
        handler = _build_handler("test_openapi_edge.hf")
        result = handler._extract_param_examples_from_call(
            "/lookup/{source}/{id}", "/lookup/wikidata/Q42"
        )
        assert result["source"] == "wikidata"
        assert result["id"] == "Q42"
