---
title: Multi-source queries
description: Querying multiple SPARQL endpoints and using SPARQL Anything.
---

<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: ISC
-->

RAMOSE can combine results from multiple SPARQL endpoints in a single operation. This is driven by directives: lines starting with `@@` inside the `#sparql` block.

When no directives are present, the query runs against the default endpoint as usual. When directives appear, RAMOSE splits the block into steps and executes them in sequence, building up an accumulator of rows.

## Setup

Register named endpoints in the API section:

```
#sources meta=https://opencitations.net/meta/sparql; index=https://opencitations.net/index/sparql
```

To allow overriding endpoints inline (rather than by name only):

```
#allow_inline_endpoints true
```

## Directives

### @@with

Switch to a named source for subsequent queries. The name must be declared in `#sources`.

```
@@with index
SELECT ?citing ?cited WHERE { ... }
```

### @@endpoint

Override the endpoint with an explicit URL. Requires `#allow_inline_endpoints true`.

```
@@endpoint https://opencitations.net/index/sparql
SELECT ?citing ?cited WHERE { ... }
```

The special value `sparql-anything` routes the query through the SPARQL Anything engine instead:

```
@@endpoint sparql-anything
SELECT * WHERE { SERVICE <x-sparql-anything:location=data.csv> { ... } }
```

### @@join

Join the next query's results with the current accumulator.

```
@@join ?doi ?doi
SELECT ?doi ?citation_count WHERE { ... }
```

Syntax: `@@join <left_var> <right_var> [type=<inner|left>]`

- `inner` (default): only rows with matches on both sides are kept.
- `left`: all rows from the accumulator are preserved. Unmatched rows get empty values for the right-side columns.

Join keys are normalized (http/https unification, trailing slash removal) to handle minor URL differences between endpoints.

When a right-side column name collides with an existing column, it gets a `_r` suffix.

### @@values

Inject accumulated values into the next query as a SPARQL `VALUES` clause.

```
@@values ?doi
SELECT ?doi ?abstract WHERE { ... }
```

RAMOSE collects distinct values for the listed variables from the accumulator and inserts a `VALUES` block into the next query's `WHERE` clause. Literal values are quoted; IRIs (starting with `http://` or `https://`) are wrapped in angle brackets.

### @@values with alias (foreach setup)

Prepare a column for iteration with `@@foreach`:

```
@@values ?br:batch_id
```

This creates an alias `batch_id` for the `?br` column, collecting its distinct values for the subsequent `@@foreach`.

### @@foreach

Iterate the next query once per value from the aliased column.

```
@@foreach batch_id 0.5
SELECT ?result WHERE {
  BIND([[batch_id]] as ?item)
  ...
}
```

Syntax: `@@foreach <alias> [delay_seconds]`

For each distinct value, `[[alias]]` is replaced in the query text. The optional delay (in seconds, float) adds a pause between iterations to avoid overwhelming the endpoint. Results from all iterations are concatenated.

### @@remove

Drop columns from the accumulator.

```
@@remove ?batch_id ?temp_var
```

Useful for cleaning up intermediate columns before the final output.

## Full example

A query that fetches metadata from OpenCitations Meta and joins citation counts from the OpenCitations Index:

```
#sources meta=https://opencitations.net/meta/sparql; index=https://opencitations.net/index/sparql
```

```
#sparql
SELECT ?doi ?title WHERE {
  ?identifier literal:hasLiteralValue "[[doi]]" ;
    datacite:usesIdentifierScheme datacite:doi ;
    ^datacite:hasIdentifier ?res .
  ?res dcterm:title ?title .
  BIND("[[doi]]" as ?doi)
}
@@with index
@@join ?doi ?doi type=left
SELECT ?doi ?citation_count WHERE {
  BIND("[[doi]]" as ?doi)
  {
    SELECT (COUNT(?citing) as ?citation_count) WHERE {
      ?citing cito:cites ?cited .
      ?cited datacite:hasIdentifier/literal:hasLiteralValue "[[doi]]"
    }
  }
}
```

This fetches the title from Meta, then joins the citation count from Index. The `left` join keeps the row even if the Index has no citation data for that DOI.

## SPARQL Anything

[SPARQL Anything](https://sparql-anything.cc/) lets you query non-RDF data sources (CSV, JSON, XML, etc.) using SPARQL. RAMOSE integrates it via [PySPARQL-Anything](https://pypi.org/project/pysparql-anything/).

Set the engine in the API section (applies to all operations) or in a single operation section (overrides the API-level setting):

```
#engine sparql-anything
```

Or per query in a multi-source block:

```
@@endpoint sparql-anything
SELECT * WHERE {
  SERVICE <x-sparql-anything:location=https://example.org/data.csv> {
    ?s ?p ?o
  }
}
```
