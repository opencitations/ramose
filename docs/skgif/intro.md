<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: CC-BY-4.0
-->

# SKG-IF integration

RAMOSE can expose any SPARQL endpoint as a REST API compliant with [SKG-IF](https://skg-if.github.io/interoperability-framework/).

(getting-started)=
## Getting started

### 1. Create the spec file

A RAMOSE spec contains one API section, which applies to the entire spec, followed by an operation section for every route. To expose an SKG-IF entity type, define two operations: one to retrieve a single entity and another to search for entities. See [Entity types](#entity-types) for the full list supported by RAMOSE. The walkthrough below shows how to define these two operations for research products. Use the same structure for any other entity type.

In the API section, set `#addon` to `ramose.skg_if`. This loads the SKG-IF JSON-LD converter.

Disable RAMOSE's built-in [query parameters](../04-parameters.md) that are not part of the SKG-IF interface with `#disable_params require,filter,sort,format,json`. `filter` is disabled because the search operation uses an SKG-IF-specific, config-driven parameter instead.

In each operation, register the SKG-IF output with `#format skg_if,to_skg_if,application/json` and make it the default with `#default_format skg_if`.

The search operation also defines the SKG-IF `filter` query parameter via `#custom_params filter,skgif_filters.ocdm.yaml,Search filter`. The `#custom_params` field points `filter` to a YAML file whose SPARQL fragments fill the `[[filter]]` placeholder in the query below. See the {ref}`config-driven parameters <config-driven-parameters>` section for a detailed explanation of how to configure this mapping.

```
#url /skg-if/v1
#type api
#base https://w3id.org/skg-if/sandbox/my-source
#title SKG-IF API for My Source
#description SKG-IF compliant API for My Source.
#version 1.0.0
#endpoint https://my-triplestore.example.org/sparql
#method get
#addon ramose.skg_if
#disable_params require,filter,sort,format,json

#url /products/{local_identifier}
#type operation
#method get
#description Returns a single research product.
#call /products/https://example.org/product/1
#format skg_if,to_skg_if,application/json
#default_format skg_if
#sparql PREFIX dcterm: <http://purl.org/dc/terms/>

SELECT ?local_identifier ?product_type ?title ?title_lang
WHERE {
  BIND(<[[local_identifier]]> AS ?local_identifier)
  ?local_identifier dcterm:title ?title .
  # ... your triplestore-specific patterns here
}

#url /products
#type operation
#method get
#description Returns a list of research products matching the given filters.
#custom_params filter,skgif_filters.ocdm.yaml,Search filter.
#format skg_if,to_skg_if,application/json
#default_format skg_if
#call /products?filter=cf.search.title:OpenCitations
#sparql [[filter_preamble]]
PREFIX dcterm: <http://purl.org/dc/terms/>

SELECT ?local_identifier ?product_type ?title ?title_lang
WHERE {
  ?local_identifier dcterm:title ?title .
  [[filter]]
  # ... your triplestore-specific patterns here
}
```

For a complete example, see the [OpenCitations spec](https://github.com/opencitations/ramose/blob/master/test/data/skgif.hf).

### 2. Run

Start the built-in dev server:

```bash
ramose -s my_source.hf -w 127.0.0.1:8080
```

The API is served at `http://127.0.0.1:8080/skg-if/v1`.

For a runnable example querying ORKG and Wikidata, see the [live demo notebook](demo.ipynb).

### API responses

An operation returns `404` with its JSON-LD envelope when the result graph is empty. An unsupported or invalid filter returns `422`. A request also returns `422` when `page` has no `page_size`, a pagination value is not a positive integer, or the requested page exceeds the result range.

(entity-types)=
## Entity types

RAMOSE determines the SKG-IF entity type from the request URL. The SPARQL query must return variables whose names match the columns defined for that entity type. RAMOSE reads the query result as a table, groups rows with the same `local_identifier`, and converts the columns into SKG-IF JSON-LD. The links in the **Columns** column below describe the supported names and how their values are mapped.

| URL segment | `entity_type` | Columns |
|---|---|---|
| `products` | `product` | [Product](product.md) |
| `persons` | `person` | [Person](person.md) |
| `organisations` | `organisation` | [Organisation](organisation.md) |
| `venues` | `venue` | [Venue](venue.md) |
| `grants` | `grant` | [Grant](grant.md) |
| `datasources` | `datasource` | [Data source](data-source.md) |
| `topics` | `topic` | [Topic](topic.md) |
