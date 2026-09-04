<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: CC-BY-4.0
-->

# Organisation CSV columns

To convert SPARQL results into SKG-IF organisations, write the operation's query so that its result variables match the column names listed below.

Official reference: [Agent properties](https://skg-if.github.io/interoperability-framework/docs/agent.html#properties).

| Column | Description | Example |
|---|---|---|
| `local_identifier` | Primary key; groups all rows for one organisation | `https://example.org/organisations/unibo` |
| `name` | Organisation name | `University of Bologna` |
| `short_name` | Short name or acronym | `UNIBO` |
| `website` | Website URL | `https://www.unibo.it` |
| `country` | ISO 3166-1 alpha-2 country code | `IT` |
| `types` | Organisation type: `"archive"`, `"company"`, `"education"`, `"facility"`, `"government"`, `"healthcare"`, `"nonprofit"`, `"funder"`, `"research"`, `"unspecified"` | `education` |
| `other_names` | Alternative name of the organisation | `Alma Mater Studiorum - Università di Bologna` |
| `identifier_scheme` | Identifier scheme for organisations: `crossref`, `omid`, `openalex`, `ror`, `url`, `urn`, `viaf`, `w3id` | `ror` |
| `identifier_value` | The external identifier | `01111rn36` |

Both `identifier_scheme` and `identifier_value` must be non-empty for an identifier to be included; rows where either is empty are skipped.

`types` and `other_names` are lists in the output. Emit one row per value: the converter collects them across every row of the organisation and drops duplicates, keeping the order in which they first appear.
