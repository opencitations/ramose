# SPDX-FileCopyrightText: 2018-2021 Silvio Peroni <silvio.peroni@unibo.it>
# SPDX-FileCopyrightText: 2020-2021 Marilena Daquino <marilena.daquino2@unibo.it>
# SPDX-FileCopyrightText: 2022 Davide Brembilla
# SPDX-FileCopyrightText: 2024 Ivan Heibi <ivan.heibi2@unibo.it>
# SPDX-FileCopyrightText: 2025 Sergei Slinkin
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import csv
import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from re import findall, split
from typing import TYPE_CHECKING, overload
from urllib.parse import quote

import yaml
from markdown import markdown

from ramose._constants import FIELD_TYPE_RE, PARAM_NAME
from ramose.documentation import DocumentationHandler
from ramose.hash_format import parse_custom_params, parse_disable_params

if TYPE_CHECKING:
    from ramose.api_manager import APIConfig

_MIN_QUOTED_LENGTH = 2
_FORMAT_PARTS_WITH_MEDIA_TYPE = 3


@dataclass
class _OpenAPIBuildContext:
    tag_name: str
    common_param_refs: list[dict[str, str]]
    formats_enum: list[str]
    api_disabled: set[str]


class _MarkupParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._text_fragments: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._current_link_href: str | None = None
        self._current_link_label_fragments: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._current_link_href = dict(attrs).get("href")
            self._current_link_label_fragments = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_link_href is not None:
            label = "".join(self._current_link_label_fragments).strip()
            self.links.append((self._current_link_href, label))
            self._current_link_href = None

    def handle_data(self, data: str) -> None:
        self._text_fragments.append(data)
        if self._current_link_href is not None:
            self._current_link_label_fragments.append(data)

    @property
    def text(self) -> str:
        return "".join(self._text_fragments).strip()


class OpenAPIDocumentationHandler(DocumentationHandler):
    def _normalize_base_url(self, base_url: str) -> str:
        return base_url.removeprefix("/")

    def _get_conf(self, base_url: str | None = None) -> APIConfig:
        if base_url is None:
            first_key = next(iter(self.conf_doc))
            return self.conf_doc[first_key]
        normalized = self._normalize_base_url(base_url)
        return self.conf_doc["/" + normalized]

    def _schema_for_ramose_type(self, t: str | None) -> dict[str, str]:
        t = (t or "str").strip().lower()
        if t == "int":
            return {"type": "integer"}
        if t == "float":
            return {"type": "number"}
        if t == "datetime":
            return {"type": "string", "format": "date-time"}
        if t == "duration":
            return {"type": "string", "format": "duration"}
        return {"type": "string"}

    def _parse_param_type_shape(self, s: str) -> tuple[str, str]:
        try:
            t, shape = findall(r"^\s*([^\(]+)\((.+)\)\s*$", s)[0]
            return t.strip(), shape.strip()
        except (IndexError, ValueError):
            return "str", ".+"

    def _parse_markup(self, text: str) -> _MarkupParser:
        parser = _MarkupParser()
        parser.feed(markdown(text))
        return parser

    def _guess_contact(self, contacts_value: object) -> dict[str, str] | None:
        if not contacts_value:
            return None
        parsed = self._parse_markup(str(contacts_value).strip())
        for href, label in parsed.links:
            if href.startswith("mailto:"):
                return {"email": href.removeprefix("mailto:")}
            if href.startswith(("http://", "https://")):
                return {"name": label or parsed.text, "url": href}
        plain_text = parsed.text
        looks_like_bare_email = "@" in plain_text and " " not in plain_text and "/" not in plain_text
        if looks_like_bare_email:
            return {"email": plain_text}
        return {"name": plain_text}

    def _clean_text(self, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if len(s) >= _MIN_QUOTED_LENGTH and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
            s = s[1:-1].strip()
        return s.replace("\\n", "\n")

    def _param_hint_from_preprocess(self, preprocess_str: object, param_name: str) -> str:
        if not preprocess_str:
            return ""
        s = str(preprocess_str)
        if re.search(r"\([^)]*\b" + re.escape(param_name) + r"\b[^)]*\)", s):
            return f"Note: input is pre-processed by RAMOSE: {s}"
        return ""

    def _try_parse_output_json(self, output_json_value: str | None) -> object:
        if not output_json_value:
            return None
        try:
            return json.loads(output_json_value)
        except (ValueError, TypeError):
            return None

    def _collect_format_tokens(self, conf: APIConfig) -> list[str]:
        formats = {"csv", "json"}
        for op in conf["conf_json"][1:]:
            if "format" in op:
                fm_val = op["format"]
                fm_list = fm_val if isinstance(fm_val, list) else [fm_val]
                for fm in fm_list:
                    for raw_part in str(fm).split(";"):
                        part = raw_part.strip()
                        if not part:
                            continue
                        fmt = part.split(",", 1)[0].strip()
                        if fmt:
                            formats.add(fmt)
        return sorted(formats)

    def _media_type_for_format(self, fmt: str) -> str | None:
        fmt = (fmt or "").strip().lower()
        mapping = {
            "json": "application/json",
            "csv": "text/csv",
            "xml": "application/xml",
            "rdfxml": "application/rdf+xml",
            "rdf+xml": "application/rdf+xml",
            "ttl": "text/turtle",
            "turtle": "text/turtle",
            "nt": "application/n-triples",
            "ntriples": "application/n-triples",
            "n-triples": "application/n-triples",
            "nq": "application/n-quads",
            "n-quads": "application/n-quads",
            "trig": "application/trig",
        }
        return mapping.get(fmt)

    def _format_media_type_map(self, op: dict[str, str]) -> dict[str, str]:
        if "format" not in op:
            return {}
        raw_value = op["format"]
        declarations = raw_value if isinstance(raw_value, list) else [raw_value]
        declared_media_types: dict[str, str] = {}
        for declaration in declarations:
            for part in str(declaration).split(";"):
                fields = [field.strip() for field in part.split(",")]
                if len(fields) >= _FORMAT_PARTS_WITH_MEDIA_TYPE and fields[0] and fields[2]:
                    declared_media_types[fields[0]] = fields[2]
        return declared_media_types

    def _single_response_media_type(self, op: dict[str, str]) -> str:
        default_format = op["default_format"].strip() if "default_format" in op else "csv"
        if default_format == "json":
            return "application/json"
        if default_format == "csv":
            return "text/csv"
        declared_media_types = self._format_media_type_map(op)
        if default_format in declared_media_types:
            return declared_media_types[default_format]
        return self._media_type_for_format(default_format) or "application/json"

    def _csv_example(self, example: object) -> str | None:
        if not isinstance(example, list):
            return None
        dict_rows = [row for row in example if isinstance(row, dict)]
        if not dict_rows:
            return None
        scalar_cell_types = (str, int, float, bool, type(None))
        all_cells_are_scalar = all(isinstance(value, scalar_cell_types) for row in dict_rows for value in row.values())
        if not all_cells_are_scalar:
            return None
        fieldnames = list(dict.fromkeys(key for row in dict_rows for key in row))
        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dict_rows)
        return buffer.getvalue()

    @overload
    def _build_response_content(
        self,
        ok_schema: dict[str, object],
        formats_enum: list[str],
        ok_example: object = ...,
        err_schema_ref: None = ...,
    ) -> OrderedDict[str, dict[str, object]]: ...

    @overload
    def _build_response_content(
        self,
        ok_schema: dict[str, object],
        formats_enum: list[str],
        ok_example: object = ...,
        *,
        err_schema_ref: str,
    ) -> tuple[OrderedDict[str, dict[str, object]], OrderedDict[str, dict[str, object]]]: ...

    def _build_response_content(
        self,
        ok_schema: dict[str, object],
        formats_enum: list[str],
        ok_example: object = None,
        err_schema_ref: str | None = None,
    ) -> (
        OrderedDict[str, dict[str, object]]
        | tuple[OrderedDict[str, dict[str, object]], OrderedDict[str, dict[str, object]]]
    ):
        content: OrderedDict[str, dict[str, object]] = OrderedDict()

        content["application/json"] = {"schema": ok_schema}
        if ok_example is not None:
            content["application/json"]["examples"] = {"example": {"value": ok_example}}

        content["text/csv"] = {"schema": {"type": "string"}}
        csv_example = self._csv_example(ok_example)
        if csv_example is not None:
            content["text/csv"]["examples"] = {"example": {"value": csv_example}}

        for fmt in formats_enum or []:
            mt = self._media_type_for_format(fmt)
            if mt is None or mt in content:
                continue
            content[mt] = {"schema": {"type": "string"}}

        if err_schema_ref:
            err_content: OrderedDict[str, dict[str, object]] = OrderedDict()
            err_content["application/json"] = {"schema": {"$ref": err_schema_ref}}
            err_content["text/csv"] = {"schema": {"type": "string"}}
            for fmt in formats_enum or []:
                mt = self._media_type_for_format(fmt)
                if mt is None or mt in err_content:
                    continue
                err_content[mt] = {"schema": {"type": "string"}}
            return content, err_content

        return content

    def _build_single_format_response(
        self,
        op: dict[str, str],
        ok_schema: dict[str, object],
        ok_example: object,
    ) -> tuple[OrderedDict[str, dict[str, object]], OrderedDict[str, dict[str, object]]]:
        media_type = self._single_response_media_type(op)
        is_json = media_type == "application/json" or media_type.endswith("+json")
        ok_entry: dict[str, object] = {"schema": ok_schema if is_json else {"type": "string"}}
        if is_json:
            example = ok_example
        elif media_type == "text/csv":
            example = self._csv_example(ok_example)
        else:
            example = None
        if example is not None:
            ok_entry["examples"] = {"example": {"value": example}}
        ok_content: OrderedDict[str, dict[str, object]] = OrderedDict([(media_type, ok_entry)])
        err_content: OrderedDict[str, dict[str, object]] = OrderedDict(
            [("application/json", {"schema": {"$ref": "#/components/schemas/Error"}})],
        )
        return ok_content, err_content

    def _extract_param_examples_from_call(self, path_template: str, call_value: object) -> dict[str, str]:
        if not call_value:
            return {}

        call_path = str(call_value).split("?", 1)[0].strip()

        parts = path_template.split("/")
        re_parts = []

        last_index = len(parts) - 1

        for i, part in enumerate(parts):
            if part.startswith("{") and part.endswith("}"):
                name = part[1:-1]
                # Last param captures slashes too (RAMOSE routes via <path:api_url>)
                if i == last_index:
                    re_parts.append(rf"(?P<{name}>.+)")
                else:
                    re_parts.append(rf"(?P<{name}>[^/]+)")
            else:
                re_parts.append(re.escape(part))

        pat = "^" + "/".join(re_parts) + "$"
        m = re.match(pat, call_path)
        if not m:
            return {}
        return {k: v for k, v in m.groupdict().items() if v is not None}

    def _build_row_schema_from_field_type(self, field_type_str: str) -> dict[str, object]:
        props = OrderedDict()
        for t, f in findall(FIELD_TYPE_RE, field_type_str or ""):
            props[f] = self._schema_for_ramose_type(t)
        return {"type": "object", "properties": props}

    def _infer_schema_from_value(self, value: object) -> dict[str, object]:
        primitive_type_map: dict[type, str] = {bool: "boolean", int: "integer", float: "number", str: "string"}
        for py_type, json_type in primitive_type_map.items():
            if isinstance(value, py_type):
                return {"type": json_type}
        if isinstance(value, list):
            result: dict[str, object] = {"type": "array"}
            if value:
                schemas = [self._infer_schema_from_value(item) for item in value]
                if all(schema == schemas[0] for schema in schemas):
                    result["items"] = schemas[0]
            return result
        if isinstance(value, dict):
            if value:
                return {"type": "object", "properties": {k: self._infer_schema_from_value(v) for k, v in value.items()}}
            return {"type": "object"}
        return {}

    def _build_info(self, api_meta: dict[str, str]) -> OrderedDict[str, object]:
        info: OrderedDict[str, object] = OrderedDict()
        info["title"] = self._parse_markup(api_meta.get("title", "RAMOSE API")).text
        version_text = self._parse_markup(api_meta.get("version", "0.0.0")).text
        info["version"] = re.sub(r"^version\s+", "", version_text, flags=re.IGNORECASE)
        if "description" in api_meta:
            info["description"] = api_meta["description"]
        if "license" in api_meta:
            parsed_license = self._parse_markup(api_meta["license"])
            license_url = next(
                (href for href, _ in parsed_license.links if href.startswith(("http://", "https://"))),
                None,
            )
            license_obj: dict[str, str] = {"name": parsed_license.text}
            if license_url is not None:
                license_obj["url"] = license_url
            info["license"] = license_obj
        if "contacts" in api_meta:
            contact_obj = self._guess_contact(api_meta["contacts"])
            if contact_obj:
                info["contact"] = contact_obj
        return info

    @staticmethod
    def _build_common_parameters(formats_enum: list[str]) -> dict[str, dict[str, object]]:
        return {
            "require": {
                "name": "require",
                "in": "query",
                "description": "Remove rows that have an empty value in the specified field. Repeatable.",
                "required": False,
                "style": "form",
                "explode": True,
                "schema": {"type": "array", "items": {"type": "string"}},
            },
            "filter": {
                "name": "filter",
                "in": "query",
                "description": (
                    "Filter rows. Repeatable.\n\n"
                    "Syntax: `field:opvalue` where `op` is one of `=`, `<`, `>`.\n"
                    "If `op` is omitted, `value` is treated as a regex."
                ),
                "required": False,
                "style": "form",
                "explode": True,
                "schema": {"type": "array", "items": {"type": "string"}},
            },
            "sort": {
                "name": "sort",
                "in": "query",
                "description": "Sort rows. Syntax: asc(field) or desc(field). Repeatable.",
                "required": False,
                "style": "form",
                "explode": True,
                "schema": {"type": "array", "items": {"type": "string"}},
            },
            "format": {
                "name": "format",
                "in": "query",
                "description": "Force output format (overrides Accept header).",
                "required": False,
                "schema": {"type": "string", "enum": formats_enum},
            },
            "json": {
                "name": "json",
                "in": "query",
                "description": (
                    "Transform JSON output rows. Repeatable.\n\n"
                    "Syntax:\n"
                    '- `array("<sep>", field)`\n'
                    '- `dict("<sep>", field, new_field_1, new_field_2, ...)`\n\n'
                    "Where `<sep>` is a string separator (e.g. `,` or `__`)."
                ),
                "required": False,
                "style": "form",
                "explode": True,
                "schema": {"type": "array", "items": {"type": "string"}},
            },
        }

    def _build_path_params(self, op: dict[str, str], raw_path: str) -> list[dict[str, object]]:
        path_params = []
        for p in findall(PARAM_NAME, raw_path):
            t, shape = ("str", ".+")
            if p in op:
                t, shape = self._parse_param_type_shape(op[p])

            schema = self._schema_for_ramose_type(t)
            if schema.get("type") == "string" and shape:
                schema["pattern"] = shape

            param_obj = {"name": p, "in": "path", "required": True, "schema": schema}
            hint = self._param_hint_from_preprocess(op.get("preprocess"), p)
            if hint:
                param_obj["description"] = hint
            path_params.append(param_obj)

        call_examples = self._extract_param_examples_from_call(raw_path, op.get("call"))
        for param in path_params:
            nm = param.get("name")
            if nm in call_examples:
                param["example"] = quote(call_examples[nm], safe="-._~__")
                if "__" in call_examples[nm] and "description" not in param:
                    param["description"] = "Multiple values can be provided separated by '__'."

        return path_params

    def _build_operation_object(
        self,
        op: dict[str, str],
        path_params: list[dict[str, object]],
        ctx: _OpenAPIBuildContext,
    ) -> OrderedDict[str, object]:
        summary = self._parse_markup(op["description"].split("\n")[0]).text if op.get("description") else ""
        desc = self._clean_text(op.get("description")) or ""

        row_schema = self._build_row_schema_from_field_type(op.get("field_type", ""))
        ok_example = self._try_parse_output_json(op.get("output_json"))
        if not row_schema["properties"] and ok_example is not None:
            ok_schema: dict[str, object] = self._infer_schema_from_value(ok_example)
        else:
            ok_schema = {"type": "array", "items": row_schema}

        disabled_names = set(ctx.api_disabled)
        if "disable_params" in op:
            disabled_names |= parse_disable_params(op["disable_params"])

        if "format" in disabled_names:
            ok_content, err_content = self._build_single_format_response(op, ok_schema, ok_example)
        else:
            ok_content, err_content = self._build_response_content(
                ok_schema=ok_schema,
                formats_enum=ctx.formats_enum,
                ok_example=ok_example,
                err_schema_ref="#/components/schemas/Error",
            )

        op_obj: OrderedDict[str, object] = OrderedDict()
        op_obj["tags"] = [ctx.tag_name]
        op_obj["summary"] = summary
        op_obj["description"] = desc
        custom_query_params = []
        custom_names: set[str] = set()
        if "custom_params" in op:
            for name, conf in parse_custom_params(op["custom_params"]).items():
                custom_names.add(name)
                param_obj: dict[str, object] = {
                    "name": name,
                    "in": "query",
                    "required": False,
                    "schema": {"type": "string"},
                }
                if conf["description"]:
                    param_obj["description"] = conf["description"]
                custom_query_params.append(param_obj)

        suppressed = custom_names | disabled_names
        filtered_refs = [ref for ref in ctx.common_param_refs if ref["$ref"].rsplit("/", 1)[-1] not in suppressed]
        op_obj["parameters"] = path_params + custom_query_params + filtered_refs
        op_obj["responses"] = OrderedDict(
            [
                ("200", {"description": "Successful response", "content": ok_content}),
                ("default", {"description": "Error", "content": err_content}),
            ],
        )

        return op_obj

    def _build_openapi(self, base_url: str | None = None) -> OrderedDict[str, object]:
        conf = self._get_conf(base_url)
        api_meta = conf["conf_json"][0]
        formats_enum = self._collect_format_tokens(conf)

        spec = OrderedDict()
        spec["openapi"] = "3.1.0"
        spec["info"] = self._build_info(api_meta)

        base = api_meta.get("base", "")
        root = api_meta.get("url", "")
        spec["servers"] = [{"url": f"{base}{root}"}]

        api_disabled = parse_disable_params(api_meta["disable_params"]) if "disable_params" in api_meta else set()

        all_common_params = self._build_common_parameters(formats_enum)
        active_common_params = {k: v for k, v in all_common_params.items() if k not in api_disabled}

        components: dict[str, object] = {
            "schemas": {
                "Error": {
                    "type": "object",
                    "properties": {"error": {"type": "integer"}, "message": {"type": "string"}},
                    "required": ["error", "message"],
                },
            },
        }
        if active_common_params:
            components["parameters"] = active_common_params
        spec["components"] = components

        common_param_refs = [{"$ref": f"#/components/parameters/{name}"} for name in active_common_params]

        spec["paths"] = OrderedDict()
        tag_name = api_meta.get("title", "RAMOSE API")

        ctx = _OpenAPIBuildContext(
            tag_name=tag_name,
            common_param_refs=common_param_refs,
            formats_enum=formats_enum,
            api_disabled=api_disabled,
        )

        for op in conf["conf_json"][1:]:
            raw_path = op.get("url", "")
            if raw_path not in spec["paths"]:
                spec["paths"][raw_path] = OrderedDict()

            path_params = self._build_path_params(op, raw_path)

            methods = [mm.lower() for mm in split(r"\s+", op.get("method", "get").strip()) if mm]
            for m in methods:
                spec["paths"][raw_path][m] = self._build_operation_object(op, path_params, ctx)

        return spec

    def _to_builtin(self, obj: object) -> object:
        if isinstance(obj, OrderedDict):
            obj = dict(obj)
        if isinstance(obj, dict):
            return {k: self._to_builtin(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [self._to_builtin(v) for v in obj]
        return obj

    def _dump_yaml(self, spec: object) -> str:
        class _RamoseYamlDumper(yaml.SafeDumper):
            pass

        def _str_presenter(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
            if "\n" in data:
                return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
            return dumper.represent_scalar("tag:yaml.org,2002:str", data)

        _RamoseYamlDumper.add_representer(str, _str_presenter)
        return yaml.dump(spec, Dumper=_RamoseYamlDumper, sort_keys=False, allow_unicode=True)

    def get_documentation(self, base_url: str | None = None, *_args: object, **_dargs: object) -> tuple[int, str]:
        spec = self._build_openapi(base_url=base_url)
        spec = self._to_builtin(spec)
        yml = self._dump_yaml(spec)
        return 200, yml

    def store_documentation(
        self, file_path: str, base_url: str | None = None, *_args: object, **_dargs: object
    ) -> None:
        yml = self.get_documentation(base_url=base_url)[1]
        with Path(file_path).open("w", encoding="utf8") as f:
            f.write(yml)

    def get_index(self, *_args: object, **_dargs: object) -> str:
        return "OpenAPI exporter available."
