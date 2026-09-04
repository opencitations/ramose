<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: CC-BY-4.0
-->

# Person CSV columns

To create SKG-IF person records from SPARQL results, name each result variable after a column in the table below. The table follows the official [Agent properties](https://skg-if.github.io/interoperability-framework/docs/agent.html#properties).

| Column | Description | Example |
|---|---|---|
| `local_identifier` | Primary key; groups all rows for one person | `https://w3id.org/oc/meta/ra/0614010840729` |
| `name` | Full name | `Peroni Silvio` |
| `family_name` | Family name | `Peroni` |
| `given_name` | Given name | `Silvio` |
| `identifier_scheme` | Identifier scheme for persons: `omid`, `openalex`, `orcid`, `url`, `urn`, `viaf`, `w3id` | `orcid` |
| `identifier_value` | The external identifier | `0000-0003-0530-4305` |

Both `identifier_scheme` and `identifier_value` must be non-empty for an identifier to be included; rows where either is empty are skipped.

## Affiliations

RAMOSE groups affiliations by `_affiliation_key`, while it uses `affiliation_local_identifier` when that key is empty. Use distinct keys when the same person has more than one work period at an organisation; rows without `affiliation_local_identifier` do not create an affiliation.

| Column | Description | Example |
|---|---|---|
| `affiliation_local_identifier` | Local identifier of the affiliated organisation | `https://example.org/organisations/unibo` |
| `_affiliation_key` | Groups rows that describe one affiliation | `affiliation_0` |
| `affiliation_name` | Organisation name | `University of Bologna` |
| `affiliation_short_name` | Short name or acronym | `UNIBO` |
| `affiliation_country` | ISO 3166-1 alpha-2 country code | `IT` |
| `affiliation_website` | Website URL | `https://www.unibo.it` |
| `affiliation_type` | Organisation type: `archive`, `company`, `education`, `facility`, `government`, `healthcare`, `nonprofit`, `funder`, `research`, or `unspecified` | `education` |
| `affiliation_other_name` | Alternative organisation name | `Alma Mater Studiorum - Università di Bologna` |
| `affiliation_identifier_scheme` | Organisation identifier scheme | `ror` |
| `affiliation_identifier_value` | Organisation external identifier | `01111rn36` |
| `affiliation_role` | Person's role in the organisation; SKG-IF recommends `affiliate` | `affiliate` |
| `affiliation_period_start` | Affiliation start date or datetime in ISO 8601 format | `2017-04-13T00:00:00Z` |
| `affiliation_period_end` | Affiliation end date or datetime in ISO 8601 format | `2019-02-11T23:59:59Z` |
