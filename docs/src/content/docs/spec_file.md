---
title: Spec file format
description: Reference for the .hf hash format configuration file.
---

<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: ISC
-->

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
| `#endpoint` | yes | Default SPARQL endpoint URL. |
| `#method` | no | HTTP method for SPARQL requests: `get` or `post`. Default: `post`. |
| `#addon` | no | Python module name for custom functions. Path relative to the spec file. |
| `#engine` | no | Execution backend: `sparql` (default) or `sparql-anything`. See [multi-source queries](/ramose/multi_source/). |
| `#sources` | no | Named endpoints for multi-source queries: `name1=url1; name2=url2`. |
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
| `#method` | yes | HTTP method(s). Space-separated for multiple (e.g., `get post`). |
| `#description` | yes | Markdown-formatted description. |
| `#call` | yes | Example call URL with real parameter values. Shown in documentation. |
| `#field_type` | yes | Space-separated `type(field_name)` pairs defining output columns and their types. |
| `#output_json` | no | Example JSON response for documentation. |
| `#preprocess` | no | Preprocessing chain: `func1(param) --> func2(param)`. See [addon modules](/ramose/addons/). |
| `#postprocess` | no | Postprocessing chain: `func1() --> func2("arg")`. See [addon modules](/ramose/addons/). |
| `#sparql` | yes | SPARQL query. Parameters injected via `[[param_name]]` placeholders. |
| `#format` | no | Custom output format converters: `name,function;...`. See [addon modules](/ramose/addons/#format-converters). |
| `#engine` | no | Override the API-level engine for this operation only. |

## Supported types

Used in `#field_type` declarations and `#<param>` definitions:

| Type | Cast behavior | Default for missing values |
|------|--------------|---------------------------|
| `str` | Lowercase string | Empty string |
| `int` | Integer | Minimum integer |
| `float` | Float | Minimum float |
| `datetime` | ISO 8601 date | `0001-01-01` |
| `duration` | XML Schema duration | `P2000Y` |

## Parameter substitution

In `#sparql` blocks, `[[param_name]]` placeholders are replaced with the URL parameter value before query execution. The parameter name matches the `{param}` in the operation URL.
