<!--
SPDX-FileCopyrightText: 2018-2021 Silvio Peroni <silvio.peroni@unibo.it>
SPDX-FileCopyrightText: 2020 Marilena Daquino <marilena.daquino2@unibo.it>
SPDX-FileCopyrightText: 2022 Davide Brembilla
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: ISC
-->

[![PyPI](https://img.shields.io/pypi/v/ramose)](https://pypi.org/project/ramose/)
[![Python versions](https://img.shields.io/pypi/pyversions/ramose)](https://pypi.org/project/ramose/)
[![Tests](https://github.com/opencitations/ramose/actions/workflows/test.yml/badge.svg)](https://github.com/opencitations/ramose/actions/workflows/test.yml)
[![Coverage](https://opencitations.github.io/ramose/coverage/coverage-badge.svg)](https://opencitations.github.io/ramose/coverage/)
[![Lint](https://github.com/opencitations/ramose/actions/workflows/lint.yml/badge.svg)](https://github.com/opencitations/ramose/actions/workflows/lint.yml)
[![REUSE status](https://api.reuse.software/badge/github.com/opencitations/ramose)](https://api.reuse.software/info/github.com/opencitations/ramose)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

# RAMOSE

Restful API Manager Over SPARQL Endpoints. Turns SPARQL endpoints into documented REST APIs.

**[Documentation](https://opencitations.github.io/ramose/)**

## Quick start

```sh
pip install ramose
```

Requires Python 3.10 or later.

Create a spec file `meta_v1.hf`:

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
#sparql PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX datacite: <http://purl.org/spar/datacite/>
PREFIX dcterm: <http://purl.org/dc/terms/>
PREFIX fabio: <http://purl.org/spar/fabio/>
PREFIX frbr: <http://purl.org/vocab/frbr/core#>
PREFIX literal: <http://www.essepuntato.it/2010/06/literalreification/>
PREFIX prism: <http://prismstandard.org/namespaces/basic/2.0/>
SELECT ?title ?pub_date ?venue ?type WHERE {
  ?identifier literal:hasLiteralValue "[[doi]]"^^xsd:string ;
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

Run locally:

```sh
python -m ramose -s meta_v1.hf -c '/v1/metadata/10.1162/qss_a_00292'
```

Or start the web server:

```sh
python -m ramose -s meta_v1.hf -w 127.0.0.1:8080
```

Visit `http://localhost:8080/v1` for auto-generated docs.

## How to cite

If you use RAMOSE, please cite both the article and the software:

> Daquino, M., Heibi, I., Peroni, S., Shotton, D. (2022). Creating RESTful APIs over SPARQL endpoints using RAMOSE. *Semantic Web*, 13(2), 195-213. https://doi.org/10.3233/SW-210439

> Brembilla, D., Peroni, S., Daquino, M., Massari, A., Heibi, I. (2026). opencitations/ramose (v2.0.0). Zenodo. https://doi.org/10.5281/zenodo.19399602

## License

ISC
