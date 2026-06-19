<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: CC-BY-4.0
-->

# Addon modules

Addons are Python modules referenced by the `#addon` field in the API section. The path is relative to the spec file.

```
#addon metaapi
```

This loads `metaapi.py` from the same directory as the spec file. Relative paths such as `../shared/metaapi` are also supported. If no matching `.py` file exists relative to the spec file, the name is resolved as a standard Python package import (e.g. `ramose.skg_if`).

## Preprocessing

Functions listed in `#preprocess` transform URL parameters before the SPARQL query runs. Each function receives parameter values and returns a tuple of modified values.

```
#preprocess generate_id_search(ids)
```

In the OpenCitations Meta API, `generate_id_search` converts identifier strings like `doi:10.1162/qss_a_00292` into SPARQL graph patterns for querying the triplestore:

```python
def generate_id_search(ids: str) -> tuple[str]:
    id_searches = []
    for identifier in ids.split("__"):
        scheme, value = identifier.split(":", maxsplit=1)
        if scheme == "doi":
            value = value.lower()
        id_searches.append(
            f'?identifier literal:hasLiteralValue "{value}" ; '
            f"datacite:usesIdentifierScheme datacite:{scheme} ; "
            f"^datacite:hasIdentifier ?res ."
        )
    return (" UNION ".join(f"{{ {s} }}" for s in id_searches),)
```

Functions are chained with `-->`. The output of one becomes the input for the next:

```
#preprocess lower(ids) --> generate_id_search(ids)
```

A function can accept multiple parameters. The tuple returned must have one value per parameter, in the same order:

```
#preprocess combine(param_a, param_b)
```

```python
def combine(a: str, b: str) -> tuple[str, str]:
    return (a.strip(), b.strip())
```

If a function returns a list instead of a single value for a parameter, RAMOSE runs the query once for each combination and merges the results. For example, if `param_a` produces `["x", "y"]` and `param_b` produces `["1", "2"]`, the query runs four times: `(x,1)`, `(x,2)`, `(y,1)`, `(y,2)`.

## Postprocessing

Functions listed in `#postprocess` transform the result table after the query returns. The first argument is always the result table. Additional arguments can be passed from the spec.

```
#postprocess create_metadata_output()
```

The result table is a list where the first element is a header tuple and each subsequent element is a data row. Each cell in a data row is a `(typed_value, plain_string_value)` tuple:

```python
[
    ("id", "title", "author", "pub_date", "type"),
    (
        ("doi:10.1162/qss_a_00292 omid:br/062104388184", "doi:10.1162/qss_a_00292 omid:br/062104388184"),
        ("opencitations meta", "OpenCitations Meta"),
        ("massari, arcangelo ...", "Massari, Arcangelo ..."),
        (datetime(2024, 1, 1), "2024"),
        ("journal article", "journal article"),
    ),
    ...
]
```

The function must return `(modified_table, should_retype)`. Set `should_retype` to `True` to re-run type casting after your modifications.

```python
def create_metadata_output(results):
    header = results[0]
    output = [header]
    type_idx = header.index("type")
    for row in results[1:]:
        new_row = list(row)
        type_uri = row[type_idx][1]
        new_row[type_idx] = (row[type_idx][0], URI_TYPE_DICT.get(type_uri, ""))
        output.append(new_row)
    return (output, True)
```

Functions are chained with `-->`:

```
#postprocess create_metadata_output() --> distinct()
```

(custom-parameters)=
## Custom parameters

The `#custom_params` field defines query string parameters handled by addon functions or YAML config files instead of the built-in RAMOSE pipeline. Python handlers specify the parameter name, handler function, processing phase, and description:

```
#custom_params filter,handle_title_filter,preprocess,Filter products by title substring
```

Multiple parameters are separated by `;`:

```
#custom_params filter,handle_title_filter,preprocess,Filter by title;limit,handle_limit,postprocess,Limit results
```

### Preprocessing parameters

A preprocessing handler returns a `dict[str, str]` mapping placeholder names to SPARQL fragments. The function receives the list of values from the query string. Each key in the returned dict corresponds to a `[[placeholder]]` in the `#sparql` block:

```python
def handle_title_filter(values: list[str]) -> dict[str, str]:
    clauses = [
        f'FILTER(CONTAINS(LCASE(?title), LCASE("{v}")))'
        for v in values
    ]
    return {"filter": "\n".join(clauses)}
```

The SPARQL query uses a placeholder where the generated fragment should go:

```
#sparql PREFIX dcterm: <http://purl.org/dc/terms/>

SELECT ?uri ?title WHERE {
  ?uri dcterm:title ?title .
  [[filter]]
}
```

A request to `?filter=semantics` calls the handler, which returns `{"filter": "FILTER(CONTAINS(...))"}`. The fragment replaces `[[filter]]` in the query. When the parameter is absent, all `[[...]]` placeholders in the template are replaced with empty strings, so the query runs without constraints.

### Multiple placeholders

A handler can populate more than one placeholder. Placeholders can appear anywhere in the `#sparql` block: before the first PREFIX, inside the WHERE clause, or after the closing brace. Position is determined entirely by where you place the `[[placeholder]]` in the template.

```
#sparql [[directives]]
PREFIX dcterm: <http://purl.org/dc/terms/>

SELECT ?uri ?title WHERE {
  ?uri dcterm:title ?title .
  [[filter]]
}
```

```python
def handle_search(values: list[str]) -> dict[str, str]:
    return {
        "directives": "@@with source=index\n...\n@@join ?uri ?uri type=inner",
        "filter": 'FILTER(CONTAINS(LCASE(?title), LCASE("...")))',
    }
```

When the handler returns `@@` directives (such as `@@with`, `@@join`, `@@values`), the engine detects them after placeholder substitution and switches from single-query to [multi-source execution](06-multi-source.md). This allows a handler to dynamically activate cross-endpoint queries without changing the spec file. Directives injected this way follow the same syntax and rules as directives written directly in the `#sparql` block.

### Postprocessing parameters

A postprocessing handler transforms the result table after built-in filters have run. The function receives the table (header followed by data rows, all plain strings) and the list of values from the query string:

```python
def handle_limit(table: list[list], values: list[str]) -> list[list]:
    limit = int(values[0])
    return [table[0], *table[1:limit + 1]]
```

### Config-driven parameters

A preprocessing parameter can be backed by a config file instead of a Python function. Give the parameter a handler that ends in `.yaml` or `.yml`: the handler is read as a path to a config file, resolved relative to the spec file. YAML handlers are always preprocessing handlers, so they omit the phase. No addon is required.

```
#custom_params filter,filters.yaml,Filter products
```

The config maps each key to one or more named slots. A slot holds a SPARQL template injected into the matching `[[slot]]` placeholder:

```yaml
identifiers.id:
  constraints: '?product ex:doi "{{value}}" .'
cites:
  federation: |
    @@with source=index
    SELECT ?product WHERE { ?product ex:cites <{{value}}> . }
    @@join ?product ?product type=inner
```

A request to `?filter=identifiers.id:10.1/x,cites:https://example.org/1` fills `[[constraints]]` and `[[federation]]`. Slot names are arbitrary; they only need to match the `[[...]]` placeholders in the operation's `#sparql`. A template containing `@@` directives triggers [multi-source execution](06-multi-source.md), so a parameter can reach a second endpoint without editing the spec. A key absent from the config is rejected; a key mapped to an empty slot map is accepted and adds no constraint.

Each parameter names its own config in its own handler, so one operation can drive several parameters from different files. The `{{value}}` placeholder is replaced with the filter value as received. Write the SPARQL delimiters you need directly in the template, such as `"{{value}}"` for a string literal or `<{{value}}>` for an IRI.

A slot can also select its template from the value, which validates the value against the listed set:

```yaml
product_type:
  constraints:
    literature: "?product a ex:Article ."
    dataset: "?product a ex:Dataset ."
```

### Overriding built-in parameters

If a custom parameter has the same name as a built-in query parameter (`filter`, `sort`, `require`), the built-in behavior is disabled for that operation.

(format-converters)=
## Format converters

The `#format` field in an operation registers custom output formats. Each entry maps a format name to a function in the addon module, with an optional media type as a third comma-separated field.

```
#format xml,to_xml;turtle,to_turtle
```

The third field declares the media type for that format. It is reported in the OpenAPI document and used for [content negotiation](content-negotiation): a custom format is selectable via the `Accept` header, and listed in the OpenAPI response content, only when it declares a media type.

```
#format skg_if,to_skg_if,application/ld+json
```

Without the third field a custom format is still reachable through `?format=` and `-f`, but it has no media type, so it is not Accept-negotiable and does not appear in the OpenAPI response content.

The function receives the result as a CSV string and a `request_url` keyword argument:

```python
def to_xml(csv_string, request_url=""):
    return xml_output
```

`request_url` is the absolute request URL, built from the API's `#base` and the request path with its query string. When `page` and `page_size` are present, the URL includes them as-is (e.g., `https://example.org/products?page=1&page_size=10`).

Custom formats can change the number of entities in the output, for example by collapsing multiple CSV rows into a single object. Because of this, RAMOSE cannot determine the correct total item count or page boundaries in advance. When a custom format is configured, RAMOSE passes the full result set to the converter without slicing. The converter is responsible for counting entities, validating page bounds, slicing to the requested page, and embedding pagination metadata in the output.

These formats become available via `?format=` in the query string and `-f` on the CLI.

### Default format

By default, operations return JSON when neither a `?format=` parameter nor an `Accept` header selects a format. The `#default_format` field overrides this for a specific operation:

```
#format skg_if,to_skg_if
#default_format skg_if
```

With this configuration, requests that do not select a format use the `to_skg_if` converter. Clients can still request other formats explicitly (e.g., `?format=csv` or `?format=json`).

The value must be a format name registered in `#format` or one of the built-in formats (`csv`, `json`).

When `#default_format` is set to a custom format, the "Result fields type" section is not shown in the HTML documentation. The output structure of a custom converter typically does not match the tabular columns declared in `#field_type`, so displaying them would be misleading. The `#field_type` field is still required: it controls column selection, ordering, and type casting internally.
