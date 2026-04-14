---
title: OpenAPI export
description: Exporting RAMOSE API specs to OpenAPI 3.0 YAML.
---

<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: ISC
-->

RAMOSE can export your API definition as an [OpenAPI 3.0](https://spec.openapis.org/oas/v3.0.3) YAML document. This lets you plug into the OpenAPI ecosystem: Swagger UI, client generators, API gateways, and so on.

## From the CLI

```sh
python -m ramose -s api.hf --openapi -o openapi.yaml
```

When multiple spec files are loaded, use `--api-base` to select which one to export:

```sh
python -m ramose -s api_v1.hf api_v2.hf --openapi --api-base /api/v1 -o openapi.yaml
```

## From the web server

The OpenAPI spec is served automatically at `<api_base>/openapi.yaml`:

```
http://localhost:8080/api/v1/openapi.yaml
```

Also accessible as `openapi.yml`.

## What gets exported

The generated document includes:

- API metadata (`info.title`, `info.version`, `info.description`, `info.contact`, `info.license`)
- Server URLs derived from `#base` and `#url`
- One path per operation, with parameters extracted from the URL template
- Parameter schemas inferred from `#<param>` type declarations
- Example values extracted from `#call`
- Response schemas with field types from `#field_type`
- Available output formats from `#format` declarations and built-in `csv`/`json`

RAMOSE-specific implementation details (endpoint, addon, method, preprocess, postprocess) are intentionally omitted from the output as they are not meaningful to API consumers.
