---
title: Addon modules
description: Custom preprocessing, postprocessing, and format converters.
---

<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: ISC
-->

Addons are Python modules referenced by the `#addon` field in the API section. The path is relative to the spec file.

```
#addon metaapi
```

This loads `metaapi.py` from the same directory as the spec file.

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

## Custom parameters

The `#custom_params` field defines query string parameters handled by addon functions instead of the built-in RAMOSE pipeline. Each entry specifies the parameter name, handler function, processing phase, and description:

```
#custom_params filter,handle_title_filter,preprocess,Filter products by title substring
```

Multiple parameters are separated by `;`:

```
#custom_params filter,handle_title_filter,preprocess,Filter by title;limit,handle_limit,postprocess,Limit results
```

### Preprocessing parameters

A preprocessing handler generates a SPARQL fragment that replaces a `[[param_name]]` placeholder in the query before execution. The function receives the list of values from the query string and returns a SPARQL string:

```python
def handle_title_filter(values: list[str]) -> str:
    clauses = [
        f'FILTER(CONTAINS(LCASE(?title), LCASE("{v}")))'
        for v in values
    ]
    return "\n".join(clauses)
```

The SPARQL query uses a placeholder where the generated fragment should go:

```
#sparql PREFIX dcterm: <http://purl.org/dc/terms/>

SELECT ?uri ?title WHERE {
  ?uri dcterm:title ?title .
  [[filter]]
}
```

A request to `?filter=semantics` calls the handler, which returns a `FILTER(CONTAINS(...))` clause. The clause replaces `[[filter]]` in the query. When the parameter is absent, `[[filter]]` is replaced with an empty string, so the query runs without constraints.

### Postprocessing parameters

A postprocessing handler transforms the result table after built-in filters have run. The function receives the table (header followed by data rows, all plain strings) and the list of values from the query string:

```python
def handle_limit(table: list[list], values: list[str]) -> list[list]:
    limit = int(values[0])
    return [table[0], *table[1:limit + 1]]
```

### Overriding built-in parameters

If a custom parameter has the same name as a built-in query parameter (`filter`, `sort`, `require`), the built-in behavior is disabled for that operation.

## Format converters

The `#format` field in an operation registers custom output formats. Each entry maps a format name to a function in the addon module.

```
#format xml,to_xml;turtle,to_turtle
```

The function receives the result as a CSV string and returns the converted output:

```python
def to_xml(csv_string: str) -> str:
    # parse csv_string, convert to XML
    return xml_output
```

These formats become available via `?format=` in the query string and `-f` on the CLI.

### Default format

By default, operations return CSV when no `?format=` parameter is provided. The `#default_format` field overrides this for a specific operation:

```
#format skgif,to_skgif
#default_format skgif
```

With this configuration, requests without `?format=` use the `to_skgif` converter. Clients can still request other formats explicitly (e.g., `?format=csv` or `?format=json`).

The value must be a format name registered in `#format` or one of the built-in formats (`csv`, `json`).

Content types are inferred from the format name:

| Format name | Content type |
|-------------|-------------|
| `xml`, `rdfxml`, `rdf+xml` | `application/rdf+xml` |
| `ttl`, `turtle` | `text/turtle` |
| `nt`, `ntriples`, `n-triples` | `application/n-triples` |
| `nq`, `n-quads` | `application/n-quads` |
| `trig` | `application/trig` |

Unrecognized names default to `text/plain`.
