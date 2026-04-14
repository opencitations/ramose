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

## Directive syntax

All directives follow the same grammar:

```
@@name <arg>... [param=value]...
```

Parameters can be passed positionally or by name using `key=value` syntax, like Python function arguments. Once a keyword argument appears, all subsequent arguments must also be keyword. Optional parameters (those with defaults) use `key=value` syntax.

A token with `=` is treated as a keyword argument only if the key matches a known parameter name. This allows values containing `=` (such as URLs with query strings) to be passed positionally without ambiguity.

```
@@foreach ?br item wait=0.5
@@foreach ?br placeholder=item wait=0.5
@@foreach variable=?br placeholder=item wait=0.5
```

These three forms are equivalent.

## Directives

### @@with

Switch to a named source for subsequent queries. The name must be declared in `#sources`.

Syntax: `@@with <source>`

```
@@with index
SELECT ?citing ?cited WHERE { ... }
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `source` | yes | Name declared in `#sources` |

### @@endpoint

Override the endpoint with an explicit URL.

Syntax: `@@endpoint <target>`

```
@@endpoint https://opencitations.net/index/sparql
SELECT ?citing ?cited WHERE { ... }
```

The special value `sparql-anything` routes the query through the SPARQL Anything engine instead:

```
@@endpoint target=sparql-anything
SELECT * WHERE { SERVICE <x-sparql-anything:location=data.csv> { ... } }
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `target` | yes | Endpoint URL or `sparql-anything` |

### @@join

Join the next query's results with the current accumulator.

Syntax: `@@join <left_var> <right_var> [type=<inner|left>]`

```
@@join ?doi ?doi type=left
SELECT ?doi ?citation_count WHERE { ... }
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `left_var` | yes | | Join key from the accumulator |
| `right_var` | yes | | Join key from the next query |
| `type` | no | `inner` | `inner` keeps only matches; `left` preserves all accumulator rows |

Join keys are normalized (http/https unification, trailing slash removal) to handle minor URL differences between endpoints.

When a right-side column name collides with an existing column, it gets a `_r` suffix.

### @@values

Inject accumulated values into the next query as a SPARQL `VALUES` clause.

Syntax: `@@values <var>...`

```
@@values ?doi
SELECT ?doi ?abstract WHERE { ... }
```

Takes one or more `?variable` names. RAMOSE collects distinct values for the listed variables from the accumulator and inserts a `VALUES` block into the next query's `WHERE` clause. Literal values are quoted; IRIs (starting with `http://` or `https://`) are wrapped in angle brackets.

### @@foreach

Iterate the next query once per distinct value of a variable from the accumulator.

Syntax: `@@foreach <variable> <placeholder> [wait=<seconds>]`

```
@@foreach ?br item wait=0.5
SELECT ?result WHERE {
  BIND(<[[item]]> as ?br)
  ...
}
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `variable` | yes | | Column from the accumulator to iterate over (must start with `?`) |
| `placeholder` | yes | | Name used as `[[placeholder]]` in the query text |
| `wait` | no | `0` | Pause in seconds (float) between iterations |

Results from all iterations are concatenated.

### @@remove

Drop columns from the accumulator.

Syntax: `@@remove <var>...`

```
@@remove ?batch_id ?temp_var
```

Takes one or more `?variable` names. Useful for cleaning up intermediate columns before the final output.

## Full example

A query that fetches metadata from OpenCitations Meta and joins citation counts from the OpenCitations Index:

```
#sources meta=https://opencitations.net/meta/sparql; index=https://opencitations.net/index/sparql
```

```
#sparql
SELECT ?doi ?title WHERE {
  ?identifier literal:hasLiteralValue "[[doi]]"^^xsd:string ;
    datacite:usesIdentifierScheme datacite:doi ;
    ^datacite:hasIdentifier ?res .
  ?res dcterm:title ?title .
  BIND("[[doi]]"^^xsd:string as ?doi)
}
@@with index
@@join ?doi ?doi type=left
SELECT ?doi ?citation_count WHERE {
  BIND("[[doi]]" as ?doi)
  {
    SELECT (COUNT(?citing) as ?citation_count) WHERE {
      ?citing cito:cites ?cited .
      ?cited datacite:hasIdentifier/literal:hasLiteralValue "[[doi]]"^^xsd:string
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
