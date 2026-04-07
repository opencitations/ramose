# SPDX-FileCopyrightText: 2018-2021 Silvio Peroni <silvio.peroni@unibo.it>
# SPDX-FileCopyrightText: 2020-2021 Marilena Daquino <marilena.daquino2@unibo.it>
# SPDX-FileCopyrightText: 2022 Davide Brembilla
# SPDX-FileCopyrightText: 2024 Ivan Heibi <ivan.heibi2@unibo.it>
# SPDX-FileCopyrightText: 2025 Sergei Slinkin
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import json
import re
from collections import OrderedDict
from pathlib import Path
from re import findall, split
from urllib.parse import quote

import yaml

from ramose._constants import FIELD_TYPE_RE, PARAM_NAME
from ramose.documentation import DocumentationHandler


class OpenAPIDocumentationHandler(DocumentationHandler):
    """
    Export RAMOSE .hf configuration(s) to an OpenAPI 3.0 YAML specification.

    Notes:
    - OpenAPI is a surface contract. RAMOSE implementation details are preserved as vendor extensions.
    - Extra RAMOSE config fields from Tables 1-2 are kept as x-ramose-* where OpenAPI has no native field.
    """

    # -------------------------
    # Small utilities
    # -------------------------
    def _normalize_base_url(self, base_url: str) -> str:
        return base_url.removeprefix("/")

    def _get_conf(self, base_url: str | None = None):
        if base_url is None:
            first_key = next(iter(self.conf_doc))
            return self.conf_doc[first_key]
        normalized = self._normalize_base_url(base_url)
        return self.conf_doc["/" + normalized]

    def _schema_for_ramose_type(self, t):
        t = (t or "str").strip().lower()
        if t == "int":
            return {"type": "integer"}
        if t == "float":
            return {"type": "number"}
        if t == "datetime":
            return {"type": "string", "format": "date-time"}
        if t == "duration":
            # OpenAPI doesn't standardize duration; still useful as hint.
            return {"type": "string", "format": "duration"}
        return {"type": "string"}

    def _parse_param_type_shape(self, s):
        # expected "type(regex)"
        try:
            t, shape = findall(r"^\s*([^\(]+)\((.+)\)\s*$", s)[0]
            return t.strip(), shape.strip()
        except (IndexError, ValueError):
            return "str", ".+"

    def _guess_contact(self, contacts_value):
        """
        Table 1: '#contacts <contact_url>' but in practice it's often an email.
        Prefer OpenAPI contact.email when it looks like an email.
        """
        if not contacts_value:
            return None
        c = str(contacts_value).strip()
        if "@" in c and " " not in c and "/" not in c:
            return {"email": c}
        return {"name": c}

    def _clean_text(self, v):
        """
        Normalize text coming from .hf parsing so Swagger/ YAML render nicely:
        - remove wrapping quotes if they were included as part of the value
        - turn literal '\\n' into real newlines
        - trim whitespace
        """
        if v is None:
            return None
        s = str(v).strip()
        # Strip wrapping quotes if parser stored them as part of the value
        if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
            s = s[1:-1].strip()
        # Convert literal backslash-n sequences to actual newlines
        return s.replace("\\n", "\n")

    def _param_hint_from_preprocess(self, preprocess_str, param_name):
        """
        Table 2: preprocess functions like 'lower(doi) --> split_dois(dois)'.
        Not formalizable in OpenAPI, but helpful as a hint.
        """
        if not preprocess_str:
            return ""
        s = str(preprocess_str)
        # Any function call mentioning the param inside (...)?
        if re.search(r"\([^)]*\b" + re.escape(param_name) + r"\b[^)]*\)", s):
            return f"Note: input is pre-processed by RAMOSE: {s}"
        return ""

    def _try_parse_output_json(self, output_json_value):
        """
        Table 2: '#output_json <ex_response>' (JSON example).
        """
        if not output_json_value:
            return None
        try:
            return json.loads(output_json_value)
        except (ValueError, TypeError):
            return None

    # -------------------------
    # Formats / media-types
    # -------------------------
    def _collect_format_tokens(self, conf):
        # always supported by RAMOSE docs
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
                        # expected "fmt,func"
                        fmt = part.split(",", 1)[0].strip()
                        if fmt:
                            formats.add(fmt)
        return sorted(formats)

    def _media_type_for_format(self, fmt):
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

    def _build_response_content(self, ok_schema, formats_enum, ok_example=None, err_schema_ref=None):
        """
        Build OpenAPI 'content' dict for responses based on supported formats.
        JSON gets structured schema. Others are represented as string payloads.
        If err_schema_ref is provided, also returns an error-content dict.
        """
        content = OrderedDict()

        content["application/json"] = {"schema": ok_schema}
        if ok_example is not None:
            content["application/json"]["examples"] = {"example": {"value": ok_example}}

        content["text/csv"] = {"schema": {"type": "string"}}

        # Other formats discovered in .hf (#format)
        for fmt in formats_enum or []:
            mt = self._media_type_for_format(fmt)
            if mt is None or mt in content:
                continue
            content[mt] = {"schema": {"type": "string"}}

        if err_schema_ref:
            err_content = OrderedDict()
            err_content["application/json"] = {"schema": {"$ref": err_schema_ref}}
            err_content["text/csv"] = {"schema": {"type": "string"}}
            for fmt in formats_enum or []:
                mt = self._media_type_for_format(fmt)
                if mt is None or mt in err_content:
                    continue
                err_content[mt] = {"schema": {"type": "string"}}
            return content, err_content

        return content

    # -------------------------
    # Examples from #call
    # -------------------------
    def _extract_param_examples_from_call(self, path_template, call_value):
        """
        Given a template like '/metadata/{dois}' and a call like
        '/metadata/10.1/abc__10.2/xyz', return {'dois': '10.1/abc__10.2/xyz'}.

        IMPORTANT: RAMOSE allows slashes inside the last param because it routes
        everything via <path:api_url>. OpenAPI tooling typically expects these
        slashes to be URL-encoded in examples.
        """
        if not call_value:
            return {}

        call_path = str(call_value).split("?", 1)[0].strip()

        parts = path_template.split("/")
        re_parts = []

        # Allow '/' inside the LAST parameter segment (captures the rest of the path)
        last_index = len(parts) - 1

        for i, part in enumerate(parts):
            if part.startswith("{") and part.endswith("}"):
                name = part[1:-1]
                if i == last_index:
                    # last param: capture everything to end, including slashes
                    re_parts.append(rf"(?P<{name}>.+)")
                else:
                    # middle params: standard segment (no slash)
                    re_parts.append(rf"(?P<{name}>[^/]+)")
            else:
                re_parts.append(re.escape(part))

        pat = "^" + "/".join(re_parts) + "$"
        m = re.match(pat, call_path)
        if not m:
            return {}
        return {k: v for k, v in m.groupdict().items() if v is not None}

    # -------------------------
    # Schema from field_type
    # -------------------------
    def _build_row_schema_from_field_type(self, field_type_str):
        props = OrderedDict()
        for t, f in findall(FIELD_TYPE_RE, field_type_str or ""):
            props[f] = self._schema_for_ramose_type(t)
        return {"type": "object", "properties": props}

    # -------------------------
    # Main builder
    # -------------------------
    def _build_info(self, api_meta):
        """Build the OpenAPI info object from API metadata."""
        info: OrderedDict[str, object] = OrderedDict()
        info["title"] = api_meta.get("title", "RAMOSE API")
        info["version"] = api_meta.get("version", "0.0.0")
        if "description" in api_meta:
            info["description"] = api_meta["description"]
        if "license" in api_meta:
            info["license"] = {"name": api_meta["license"]}
        if "contacts" in api_meta:
            contact_obj = self._guess_contact(api_meta.get("contacts"))
            if contact_obj:
                info["contact"] = contact_obj
        return info

    @staticmethod
    def _build_common_parameters(formats_enum):
        """Build the shared query parameter definitions."""
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

    def _build_path_params(self, op, raw_path):
        """Build path parameter objects for an operation, including examples from #call."""
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

    def _build_operation_object(self, op, tag_name, path_params, common_param_refs, formats_enum):
        """Build an OpenAPI operation object for a single HTTP method."""
        summary = op["description"].split("\n")[0].strip() if op.get("description") else ""
        desc = self._clean_text(op.get("description")) or ""
        spr = self._clean_text(op.get("sparql"))
        if spr:
            desc += f"\n\n---\n\n### RAMOSE SPARQL\n\n```sparql\n{spr}\n```"

        row_schema = self._build_row_schema_from_field_type(op.get("field_type", ""))
        ok_schema = {"type": "array", "items": row_schema}
        ok_example = self._try_parse_output_json(op.get("output_json"))
        ok_content, err_content = self._build_response_content(
            ok_schema=ok_schema,
            formats_enum=formats_enum,
            ok_example=ok_example,
            err_schema_ref="#/components/schemas/Error",
        )

        op_obj: OrderedDict[str, object] = OrderedDict()
        op_obj["tags"] = [tag_name]
        op_obj["summary"] = summary
        op_obj["description"] = desc
        op_obj["parameters"] = path_params + common_param_refs
        op_obj["responses"] = OrderedDict(
            [
                ("200", {"description": "Successful response", "content": ok_content}),
                ("default", {"description": "Error", "content": err_content}),
            ]
        )

        ramose_ext = OrderedDict()
        for key, src_key in [("preprocess", "preprocess"), ("postprocess", "postprocess"), ("call", "call")]:
            val = self._clean_text(op.get(src_key))
            if val:
                ramose_ext[key] = val
        if spr:
            ramose_ext["sparql_in_description"] = True
        if ramose_ext:
            op_obj["x-ramose"] = ramose_ext

        return op_obj

    def _build_openapi(self, base_url=None):
        conf = self._get_conf(base_url)
        api_meta = conf["conf_json"][0]
        formats_enum = self._collect_format_tokens(conf)

        spec = OrderedDict()
        spec["openapi"] = "3.0.3"
        spec["info"] = self._build_info(api_meta)

        base = api_meta.get("base", "")
        root = api_meta.get("url", "")
        spec["servers"] = [{"url": f"{base}{root}"}]

        for ext_key, meta_key in [
            ("x-ramose-endpoint", "endpoint"),
            ("x-ramose-addon", "addon"),
            ("x-ramose-sparql-method", "method"),
        ]:
            if meta_key in api_meta:
                spec[ext_key] = api_meta[meta_key]

        spec["components"] = {
            "schemas": {
                "Error": {
                    "type": "object",
                    "properties": {"error": {"type": "integer"}, "message": {"type": "string"}},
                    "required": ["error", "message"],
                },
            },
            "parameters": self._build_common_parameters(formats_enum),
        }

        common_param_refs = [{"$ref": f"#/components/parameters/{name}"} for name in spec["components"]["parameters"]]

        spec["paths"] = OrderedDict()
        tag_name = api_meta.get("title", "RAMOSE API")

        for op in conf["conf_json"][1:]:
            raw_path = op.get("url", "")
            if raw_path not in spec["paths"]:
                spec["paths"][raw_path] = OrderedDict()

            path_params = self._build_path_params(op, raw_path)

            methods = [mm.lower() for mm in split(r"\s+", op.get("method", "get").strip()) if mm]
            for m in methods:
                spec["paths"][raw_path][m] = self._build_operation_object(
                    op,
                    tag_name,
                    path_params,
                    common_param_refs,
                    formats_enum,
                )

        return spec

    # -------------------------
    # PyYAML compatibility
    # -------------------------
    def _to_builtin(self, obj):
        """Recursively convert OrderedDict (and other non-builtin containers)
        to plain Python builtins so that yaml.safe_dump can serialize it."""
        if isinstance(obj, OrderedDict):
            obj = dict(obj)
        if isinstance(obj, dict):
            return {k: self._to_builtin(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [self._to_builtin(v) for v in obj]
        return obj

    def _dump_yaml(self, spec):
        """
        Dump OpenAPI spec to YAML with nice formatting:
        - multiline strings become block scalars (|)
        - keys keep insertion order (sort_keys=False)
        """

        class _RamoseYamlDumper(yaml.SafeDumper):
            pass

        def _str_presenter(dumper, data):
            if "\n" in data:
                return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
            return dumper.represent_scalar("tag:yaml.org,2002:str", data)

        _RamoseYamlDumper.add_representer(str, _str_presenter)
        return yaml.dump(spec, Dumper=_RamoseYamlDumper, sort_keys=False, allow_unicode=True)

    def get_documentation(self, base_url=None):
        spec = self._build_openapi(base_url=base_url)
        spec = self._to_builtin(spec)
        yml = self._dump_yaml(spec)
        return 200, yml

    def store_documentation(self, file_path, base_url=None):
        yml = self.get_documentation(base_url=base_url)[1]
        with Path(file_path).open("w", encoding="utf8") as f:
            f.write(yml)

    def get_index(self, *_args, **_dargs):
        # Not used by the current UI. Keep a minimal placeholder.
        return "OpenAPI exporter available."
