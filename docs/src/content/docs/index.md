---
title: Quick start
description: Install RAMOSE and run your first API in under five minutes.
template: doc
---

<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: ISC
-->

RAMOSE turns SPARQL endpoints into documented REST APIs. You write a spec file describing your queries, and RAMOSE handles routing, type casting, filtering, and documentation generation.

## Install

```sh
pip install ramose
```

Requires Python 3.10 or later.

## Create a spec file

Save this as `meta_v1.hf`:

```
#url /v1
#type api
#base https://api.opencitations.net/meta
#title OpenCitations Meta REST API
#description REST API for bibliographic metadata from OpenCitations Meta
#version 1.0.0
#license ISC
#contacts [contact@opencitations.net](mailto:contact@opencitations.net)
#endpoint https://opencitations.net/meta/sparql
#method post

#url /metadata/{doi}
#type operation
#doi str(10\..+)
#method get
#description Returns bibliographic metadata for the given DOI.
#call /metadata/10.1162/qss_a_00292
#field_type str(title) datetime(pub_date) str(venue) str(type)
#sparql PREFIX datacite: <http://purl.org/spar/datacite/>
PREFIX dcterm: <http://purl.org/dc/terms/>
PREFIX fabio: <http://purl.org/spar/fabio/>
PREFIX frbr: <http://purl.org/vocab/frbr/core#>
PREFIX literal: <http://www.essepuntato.it/2010/06/literalreification/>
PREFIX prism: <http://prismstandard.org/namespaces/basic/2.0/>
SELECT ?title ?pub_date ?venue ?type WHERE {
  ?identifier literal:hasLiteralValue "[[doi]]" ;
    datacite:usesIdentifierScheme datacite:doi ;
    ^datacite:hasIdentifier ?res .
  OPTIONAL { ?res dcterm:title ?title }
  OPTIONAL { ?res prism:publicationDate ?pub_date }
  OPTIONAL {
    ?res frbr:partOf+ ?journal .
    ?journal a fabio:Journal ; dcterm:title ?venue
  }
  OPTIONAL { ?res a ?type . FILTER(?type != fabio:Expression) }
}
```

The first section declares the API (endpoint, metadata). The second defines an operation: a URL pattern with a `{doi}` parameter, mapped to a SPARQL query where `[[doi]]` gets replaced at runtime.

## Run locally

```sh
python -m ramose -s meta_v1.hf -c '/v1/metadata/10.1162/qss_a_00292'
```

Output:

```
# Response HTTP code: 200
# Body:
[{"title": "OpenCitations Meta", "pub_date": "2024", "venue": "Quantitative Science Studies", "type": "journal article"}]
# Content-type: application/json
```

## Start the web server

```sh
python -m ramose -s meta_v1.hf -w 127.0.0.1:8080
```

Open `http://localhost:8080/v1` for auto-generated documentation, or query `http://localhost:8080/v1/metadata/10.1162/qss_a_00292` directly.

## What's next

- [Spec file format](/ramose/spec_file/) for the full `.hf` reference
- [CLI](/ramose/cli/) for all command-line options
- [Python API](/ramose/python_api/) for programmatic usage
- [Query parameters](/ramose/parameters/) for filtering and sorting results
