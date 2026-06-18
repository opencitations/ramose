<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: CC-BY-4.0
-->

# CLI

## Arguments

```sh
python -m ramose -s <spec.hf|spec.yaml> [options]
```

| Argument | Description |
|----------|-------------|
| `-s`, `--spec` | RAMOSE spec file(s). Required. Accepts `.hf`, `.yaml`, and `.yml`; accepts multiple files. |
| `-c`, `--call` | API call URL, e.g. `/v1/metadata/doi:10.1162/qss_a_00292`. |
| `-m`, `--method` | HTTP method for the call. Default: `get`. |
| `-f`, `--format` | Response format: `application/json` (default) or `text/csv`. |
| `-d`, `--doc` | Generate HTML documentation. Ignores `-m`, `-c`, `-f`. |
| `--openapi` | Export OpenAPI 3.1 YAML specification. |
| `--api-base` | Select which API base to export when multiple specs are loaded. |
| `-o`, `--output` | Write response to file instead of stdout. |
| `-w`, `--webserver` | Start Flask server at `host:port`. |
| `-css`, `--css` | Custom CSS file path for documentation styling. |
| `--debug` | Enable Flask debug mode (auto-reload, interactive debugger). |
| `--cache-dir` | Directory for result caching. Default: `.cache`. |
| `--no-cache` | Disable result caching entirely. |
| `--cache-ttl` | Cache TTL in seconds. Default: `86400` (1 day). |
| `--auth-db` | Directory for the bearer token store. Default: `.auth`. |
| `--token-create` | Create a bearer token with the given label, print it once, and exit. |
| `--token-ttl` | Token lifetime in seconds for `--token-create`. Default: no expiry. |
| `--token-list` | List stored tokens (labels, timestamps, revoked flag) and exit. |
| `--token-revoke` | Revoke the given token and exit. |
| `--backend-auth` | Per-endpoint backend credential as `endpoint_url=header` (e.g. `https://host/sparql=Bearer <token>`). Repeatable. Merged with `RAMOSE_BACKEND_AUTH`. |

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
python -m ramose -s meta_v1.hf index_v2.yaml -w 127.0.0.1:8080
```

Apply custom CSS to the documentation:

```sh
python -m ramose -s meta_v1.hf -w 127.0.0.1:8080 -css style.css
```

## Caching

RAMOSE caches processed query results in a local SQLite-backed store. Subsequent requests for the same query hit the cache instead of re-querying the SPARQL endpoint.

By default, the cache lives in `.cache/` in the working directory with a 1-day TTL. Override with:

```sh
python -m ramose -s meta_v1.hf -w 127.0.0.1:8080 --cache-dir /tmp/ramose-cache --cache-ttl 3600
```

To disable caching:

```sh
python -m ramose -s meta_v1.hf -w 127.0.0.1:8080 --no-cache
```

Per-operation cache control is available via `#cache_duration` and `#cache_disable` in the [spec file](01-spec-file.md).

## Authentication

Operations marked `#auth required` in the [spec file](01-spec-file.md) need a bearer token. Tokens are kept in a local SQLite store (default `.auth/`, configurable with `--auth-db`); RAMOSE stores only their SHA-256 hash, never the token itself. Write operations (`POST`/`PUT`/`DELETE`) should always be protected this way.

Create a token (printed once):

```sh
python -m ramose --token-create my-client
```

Optionally give it a lifetime in seconds:

```sh
python -m ramose --token-create my-client --token-ttl 3600
```

List or revoke tokens:

```sh
python -m ramose --token-list
python -m ramose --token-revoke <token>
```

Call a protected operation by sending the token in the `Authorization` header:

```sh
curl -X POST -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"resource": "https://w3id.org/oc/meta/br/062104388184", "title": "OpenCitations Meta", "identifier": "https://w3id.org/oc/meta/id/062106312420", "scheme": "http://purl.org/spar/datacite/doi", "value": "10.1162/qss_a_00292"}' \
  "http://localhost:8080/bibliography/v1/resources"
```

Requests with a missing, invalid, or revoked token receive HTTP 401. Operations without `#auth` stay open.

## Backend authentication

The bearer token above protects the client→RAMOSE boundary. It is unrelated to any credential the SPARQL backend itself requires on the RAMOSE→backend boundary. 

QLever, for example, can require an access token for SPARQL Updates. Apache Jena Fuseki and Ontotext GraphDB expose several schemes: HTTP Basic and bearer tokens, plus GraphDB's own GDB token.

Configure RAMOSE with its own backend credentials, **keyed by endpoint URL**. The credential applies to both reads and writes.

Each entry is `endpoint_url=header`, where the header is the full `Authorization` value RAMOSE sends. RAMOSE does not interpret the scheme, so the value matches whatever the backend expects (`Bearer <token>`, `Basic <base64(user:pass)>`, `GDB <token>`, and so on):

```sh
export RAMOSE_BACKEND_AUTH='https://localhost:7019/sparql=Bearer <qlever-access-token>'
python -m ramose -s write_api.hf -w 127.0.0.1:8080
```

Set several backends with newline-separated entries in the environment variable, or with a repeatable `--backend-auth` flag:

```sh
python -m ramose -s apis.hf -w 127.0.0.1:8080 \
  --backend-auth 'https://qlever.example/sparql=Bearer <token>' \
  --backend-auth 'https://fuseki.example/ds/update=Basic <base64>'
```
