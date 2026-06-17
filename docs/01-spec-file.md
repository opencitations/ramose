<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: CC-BY-4.0
-->

# Spec file format

A spec file (`.hf`) defines your API: metadata, operations, SPARQL queries, and processing pipelines. RAMOSE parses it to route requests and generate documentation.

The file contains sections separated by blank lines. The first section defines the API. Each subsequent section defines an operation.

## API section

```
#url /v1
#type api
#base https://api.opencitations.net/meta
#title OpenCitations Meta REST API
#description REST API for bibliographic metadata from OpenCitations Meta
#version 1.1.1
#license [ISC](https://opensource.org/licenses/ISC)
#contacts [contact@opencitations.net](mailto:contact@opencitations.net)
#endpoint https://opencitations.net/meta/sparql
#method post
#addon metaapi
```

| Field | Required | Description |
|-------|----------|-------------|
| `#url` | yes | API base path (e.g., `/v1`). Must be unique when multiple APIs coexist. |
| `#type` | yes | Must be `api`. |
| `#base` | yes | Full URL prefix shared across services. |
| `#title` | yes | API name shown in documentation. |
| `#description` | yes | Supports Markdown. Use `\n` for line breaks. |
| `#version` | yes | Version string. |
| `#license` | yes | License text. Markdown links supported. |
| `#contacts` | yes | Contact info in `[text](url)` format. |
| `#endpoint` | yes | Default SPARQL query endpoint URL. |
| `#update_endpoint` | no | SPARQL Update endpoint URL for write operations. Defaults to `#endpoint` when omitted. |
| `#method` | no | HTTP method for SPARQL requests: `get` or `post`. Default: `post`. |
| `#auth` | no | Set to `required` to make every operation in this API require a bearer token. Operation-level `#auth` overrides this default. |
| `#addon` | no | Python module name for custom functions. Path relative to the spec file. |
| `#engine` | no | Execution backend: `sparql` (default) or `sparql-anything`. See [multi-source queries](06-multi-source.md). |
| `#sources` | no | Named endpoints for multi-source queries: `name1=url1; name2=url2`. |
| `#disable_params` | no | Comma-separated list of built-in query parameters to suppress (`require`, `filter`, `sort`, `format`, `json`, `page`, `page_size`). Use `*` to disable all. Applies to all operations in this API. Operation-level `#disable_params` extends this set. |
| `#html_meta_description` | no | HTML meta description for documentation pages. |

## Operation section

Each operation maps a URL pattern to a SPARQL query. Here is the `/metadata/{ids}` operation from the OpenCitations Meta API:

```
#url /metadata/{ids}
#type operation
#ids str((doi|issn|isbn|omid|openalex|pmid|pmcid):.+?(__(doi|issn|isbn|omid|openalex|pmid|pmcid):.+?)*$)
#preprocess generate_id_search(ids)
#postprocess create_metadata_output()
#method get
#description Returns bibliographic metadata for the given identifiers.
#call /metadata/doi:10.1162/qss_a_00292
#field_type str(id) str(title) str(author) datetime(pub_date) str(issue) str(volume) str(venue) str(page) str(type) str(publisher) str(editor)
#format xml,to_xml;turtle,to_turtle
#engine sparql
#output_json [
    {
        "id": "doi:10.1162/qss_a_00292 omid:br/062104388184",
        "title": "OpenCitations Meta",
        "author": "Massari, Arcangelo [orcid:0000-0002-8420-0696 omid:ra/06250110138]; Mariani, Fabio [orcid:0000-0002-7382-0187 omid:ra/0621012370562]; Heibi, Ivan [orcid:0000-0001-5366-5194 omid:ra/0621012370563]; Peroni, Silvio [orcid:0000-0003-0530-4305 omid:ra/0621012370564]; Shotton, David [orcid:0000-0001-5506-523X omid:ra/0621012370565]",
        "pub_date": "2024",
        "issue": "1",
        "volume": "5",
        "venue": "Quantitative Science Studies [issn:2641-3337 openalex:S4210195326 omid:br/062501778099]",
        "type": "journal article",
        "page": "50-75",
        "publisher": "Mit Press [crossref:281 omid:ra/0610116105]",
        "editor": ""
    }
]
#sparql PREFIX datacite: <http://purl.org/spar/datacite/>
PREFIX literal: <http://www.essepuntato.it/2010/06/literalreification/>
PREFIX fabio: <http://purl.org/spar/fabio/>
...
SELECT DISTINCT ?id ?title ?author ?pub_date ... WHERE {
    [[ids]]
    ...
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `#url` | yes | Operation path with parameters in braces: `/path/{param}`. |
| `#type` | yes | Must be `operation`. |
| `#<param>` | no | Validator for a URL parameter. The field name matches the `{param}` in `#url`. Value is `type(regex)`, e.g. `#ids str(...)` validates `{ids}`. Defaults to `str(.+)` if omitted. |
| `#method` | yes | HTTP method(s). Space-separated for multiple (e.g., `get post`). `post`, `put`, `delete` are write operations (see [Write operations](#write-operations)). The same `#url` can have several operations with different methods. |
| `#description` | yes | Markdown-formatted description. |
| `#call` | yes | Example call URL with real parameter values. Shown in documentation. |
| `#field_type` | yes | Space-separated `type(field_name)` pairs defining output columns and their types. |
| `#output_json` | no | Example JSON response for documentation. |
| `#preprocess` | no | Preprocessing chain: `func1(param) --> func2(param)`. See [addon modules](05-addons.md). |
| `#postprocess` | no | Postprocessing chain: `func1() --> func2("arg")`. See [addon modules](05-addons.md). |
| `#sparql` | yes | SPARQL query. Parameters injected via `[[param_name]]` placeholders. |
| `#format` | no | Custom output format converters: `name,function;...`. See [addon modules](format-converters). |
| `#default_format` | no | Default output format when neither a `?format=` query parameter nor an `Accept` header selects one. Must match a name registered in `#format` or a built-in format (`csv`, `json`). Without this field, the default is JSON. When set to a custom format, the "Result fields type" section is hidden from the HTML documentation since the output structure does not match the tabular columns declared in `#field_type`. |
| `#custom_params` | no | Custom query parameters with addon handlers (`name,function,phase,description;...`) or YAML handlers (`name,file.yaml,description;...`). See [addon modules](custom-parameters). |
| `#engine` | no | Override the API-level engine for this operation only. |
| `#disable_params` | no | Comma-separated list of built-in query parameters to suppress for this operation. Use `*` to disable all. Merged with any API-level `#disable_params`. |
| `#cache_duration` | no | Cache TTL in seconds for this operation. Overrides the global `--cache-ttl` value. |
| `#cache_disable` | no | Set to any value (e.g., `true`) to disable caching for this operation. |
| `#auth` | no | Set to `required` to require a bearer token for this operation. Overrides the API-level `#auth`. |

## Supported types

Used in `#field_type` declarations and `#<param>` definitions:

| Type | Cast behavior | Default for missing values |
|------|--------------|---------------------------|
| `str` | Lowercase string | Empty string |
| `int` | Integer | Minimum integer |
| `float` | Float | Minimum float |
| `datetime` | ISO 8601 date | `0001-01-01` |
| `duration` | XML Schema duration | `P2000Y` |
| `iri` | String kept verbatim; in write operations the value is validated as an IRI | Empty string |
| `literal` | String kept verbatim; in write operations the value is escaped as a SPARQL string literal | Empty string |

`iri` and `literal` behave like `str` for read operations but skip the lowercasing, and they drive safe value binding for write operations (see below).

## Parameter substitution

In `#sparql` blocks, `[[param_name]]` placeholders are replaced with the URL parameter value before query execution. The parameter name matches the `{param}` in the operation URL.

(write-operations)=
## Write operations

An operation whose `#method` is `post`, `put`, or `delete` runs a SPARQL 1.1 Update (`INSERT`/`DELETE`/`UPDATE`) instead of a read query. The update is sent to `#update_endpoint` (or `#endpoint` if that is not set) and the response is a small JSON confirmation rather than a result set.

Here is an example:

```
#url /resources
#type operation
#method post
#auth required
#resource iri(.+)
#title literal(.+)
#identifier iri(.+)
#scheme iri(.+)
#value literal(.+)
#description Create a bibliographic resource with a title and an identifier
#field_type str(x)
#sparql INSERT DATA {
            <[[resource]]> a <http://purl.org/spar/fabio/Expression> ;
                <http://purl.org/dc/terms/title> "[[title]]" ;
                <http://purl.org/spar/datacite/hasIdentifier> <[[identifier]]> .
            <[[identifier]]> a <http://purl.org/spar/datacite/Identifier> ;
                <http://purl.org/spar/datacite/usesIdentifierScheme> <[[scheme]]> ;
                <http://www.essepuntato.it/2010/06/literalreification/hasLiteralValue> "[[value]]" .
        }
```

```
POST /resources
Authorization: Bearer <token>
Content-Type: application/json

{
  "resource": "https://w3id.org/oc/meta/br/062104388184",
  "title": "OpenCitations Meta",
  "identifier": "https://w3id.org/oc/meta/id/062106312420",
  "scheme": "http://purl.org/spar/datacite/doi",
  "value": "10.1162/qss_a_00292"
}
```

The same request can carry the parameters in the URL query string instead of a body. With `curl`, `--url-query` encodes each value for you:

```bash
curl -X POST http://127.0.0.1:8080/bibliography/v1/resources \
  -H "Authorization: Bearer <token>" \
  --url-query 'resource=https://w3id.org/oc/meta/br/062104388184' \
  --url-query 'title=OpenCitations Meta' \
  --url-query 'identifier=https://w3id.org/oc/meta/id/062106312420' \
  --url-query 'scheme=http://purl.org/spar/datacite/doi' \
  --url-query 'value=10.1162/qss_a_00292'
```

Or with everything inline in the URL (spaces must be percent-encoded as `%20`; `:` and `/` may stay as they are):

```bash
curl -X POST "http://127.0.0.1:8080/bibliography/v1/resources?resource=https://w3id.org/oc/meta/br/062104388184&title=OpenCitations%20Meta&identifier=https://w3id.org/oc/meta/id/062106312420&scheme=http://purl.org/spar/datacite/doi&value=10.1162/qss_a_00292" \
  -H "Authorization: Bearer <token>"
```

If any `[[placeholder]]` is left unfilled after substitution, the request is rejected with HTTP 400 and nothing is sent to the endpoint.

Protect write operations with `#auth required`; see [authentication](02-cli.md#authentication).
