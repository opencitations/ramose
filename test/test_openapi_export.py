# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import os

import yaml

from ramose import APIManager, OpenAPIDocumentationHandler


TESTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests")


def _build_handler(*hf_files):
    paths = [os.path.join(TESTS_DIR, f) for f in hf_files]
    am = APIManager(paths, endpoint_override="http://localhost:9999/sparql")
    return OpenAPIDocumentationHandler(am)


class TestOpenAPIFromMixedScholarlyCrossref:
    def test_generated_yaml_matches_reference(self):
        handler = _build_handler("mixed_scholarly_crossref.hf")
        status, yml = handler.get_documentation()
        assert status == 200

        generated = yaml.safe_load(yml)
        ref_path = os.path.join(TESTS_DIR, "mixed_scholarly_crossref_openapi.yaml")
        with open(ref_path) as f:
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
        assert "mixed" in spec["servers"][0]["url"]

    def test_base_url_with_leading_slash(self):
        handler = _build_handler("mixed_scholarly_crossref.hf")
        status, _ = handler.get_documentation(base_url="/mixed")
        assert status == 200
