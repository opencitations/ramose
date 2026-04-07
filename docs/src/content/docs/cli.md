---
title: CLI
description: Command-line interface for running RAMOSE locally or as a web server.
---

<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: ISC
-->

## Arguments

```sh
python -m ramose -s <spec.hf> [options]
```

| Argument | Description |
|----------|-------------|
| `-s`, `--spec` | Spec file(s) in hash format. Required. Accepts multiple files. |
| `-c`, `--call` | API call URL, e.g. `/v1/metadata/doi:10.1162/qss_a_00292`. |
| `-m`, `--method` | HTTP method for the call. Default: `get`. |
| `-f`, `--format` | Response format: `application/json` (default) or `text/csv`. |
| `-d`, `--doc` | Generate HTML documentation. Ignores `-m`, `-c`, `-f`. |
| `--openapi` | Export OpenAPI 3.0 YAML specification. |
| `--api-base` | Select which API base to export when multiple specs are loaded. |
| `-o`, `--output` | Write response to file instead of stdout. |
| `-w`, `--webserver` | Start Flask server at `host:port`. |
| `-css`, `--css` | Custom CSS file path for documentation styling. |

## Local mode

Query an endpoint and print the result:

```sh
python -m ramose -s meta_v1.hf -c '/v1/metadata/doi:10.1162/qss_a_00292'
```

```
# Response HTTP code: 200
# Body:
[{"id": "doi:10.1162/qss_a_00292 omid:br/062104388184", "title": "OpenCitations Meta", ...}]
# Content-type: application/json
```

Request CSV instead:

```sh
python -m ramose -s meta_v1.hf -f text/csv -c '/v1/metadata/doi:10.1162/qss_a_00292'
```

Save to file:

```sh
python -m ramose -s meta_v1.hf -c '/v1/metadata/doi:10.1162/qss_a_00292' -o result.json
```

Generate HTML documentation:

```sh
python -m ramose -s meta_v1.hf -d -o docs.html
```

Export OpenAPI spec:

```sh
python -m ramose -s meta_v1.hf --openapi -o openapi.yaml
```

## Web server

Start a Flask development server:

```sh
python -m ramose -s meta_v1.hf -w 127.0.0.1:8080
```

This serves:

- **Dashboard** at the root (`/`)
- **API documentation** at the API base path (e.g., `/v1`)
- **API endpoints** at their configured paths
- **OpenAPI spec** at `<api_base>/openapi.yaml` (e.g., `/v1/openapi.yaml`)

Query via curl:

```sh
curl -H "Accept: text/csv" "http://localhost:8080/v1/metadata/doi:10.1162/qss_a_00292"
```

Load multiple APIs at once:

```sh
python -m ramose -s meta_v1.hf index_v2.hf -w 127.0.0.1:8080
```

Apply custom CSS to the documentation:

```sh
python -m ramose -s meta_v1.hf -w 127.0.0.1:8080 -css style.css
```
