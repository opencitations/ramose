---
title: Python API
description: Using RAMOSE programmatically with APIManager and Operation.
---

<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: ISC
-->

## APIManager

`APIManager` loads one or more spec files and routes API calls to the matching operation.

```python
from ramose import APIManager

am = APIManager(["meta_v1.hf", "index_v2.hf"])
```

To override the SPARQL endpoint defined in the spec files (useful for staging or testing):

```python
am = APIManager(["meta_v1.hf"], endpoint_override="http://localhost:9999/sparql")
```

### Caching

Result caching is enabled by passing `cache_dir`:

```python
am = APIManager(["meta_v1.hf"], cache_dir=".cache", cache_ttl=86400)
```

`cache_dir` sets the directory for the SQLite-backed cache store. `cache_ttl` sets the default TTL in seconds (default: 86400). Pass `cache_dir=None` to disable caching.

### get_op(url)

Returns an `Operation` for the given call URL, or a `(status_code, message, content_type)` tuple if no operation matches.

```python
from ramose import Operation

op = am.get_op("/v1/metadata/doi:10.1162/qss_a_00292")

if isinstance(op, Operation):
    status, body, content_type, headers = op.exec()
else:
    status, message, content_type = op
```

## Operation

Represents a single API operation ready to execute.

### exec(method, content_type)

Runs the full pipeline and returns `(http_status_code, response_body, content_type, headers)`.

```python
status, body, content_type, headers = op.exec(
    method="get",
    content_type="text/csv",
)
```

Both arguments are optional. Defaults: `method="get"`, `content_type="application/json"`.

The `headers` dict contains HTTP headers that should be forwarded to the client. When pagination is active (the request URL includes `page` and `page_size` parameters), it includes a `Link` header with `rel="next"`, `rel="prev"`, `rel="first"`, and `rel="last"` URLs following [RFC 8288](https://www.rfc-editor.org/rfc/rfc8288).

```python
op = am.get_op("/v1/author/orcid:0000-0002-8420-0696?page=2&page_size=10")
status, body, content_type, headers = op.exec()
print(headers.get("Link"))
```

### Pipeline

The execution follows these steps in order:

1. Extract parameters from the URL path
2. Run `#preprocess` functions on parameters
3. Check the result cache; on hit, skip to step 8
4. Execute the SPARQL query (single or [multi-source](/ramose/multi_source/))
5. Run `#postprocess` functions on results
6. Apply [query string filters](/ramose/parameters/) (require, filter, sort)
7. Cache the processed result (if caching is enabled)
8. Apply pagination slicing (if `page_size` is present)
9. Convert to the requested output format

### Error codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Invalid parameter or malformed multi-source query |
| 404 | No matching operation |
| 405 | HTTP method not allowed |
| 408 | SPARQL endpoint timeout |
| 500 | Unexpected error |
| 502 | SPARQL endpoint returned an error |
