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
    status, body, content_type = op.exec()
else:
    status, message, content_type = op
```

## Operation

Represents a single API operation ready to execute.

### exec(method, content_type)

Runs the full pipeline and returns `(http_status_code, response_body, content_type)`.

```python
status, body, content_type = op.exec(
    method="get",
    content_type="text/csv",
)
```

Both arguments are optional. Defaults: `method="get"`, `content_type="application/json"`.

### pagination_info

After calling `exec()` with `page`/`page_size` query parameters, `op.pagination_info` holds a `PaginationInfo` named tuple with `page`, `page_size`, `total_items`, `next_url`, and `prev_url` fields. When pagination is not active, this attribute is `None`.

```python
from ramose.paging import build_link_header

status, body, content_type = op.exec()
if op.pagination_info is not None:
    print(op.pagination_info.total_items)
    print(build_link_header(op.pagination_info))
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
