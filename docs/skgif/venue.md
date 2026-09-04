<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: CC-BY-4.0
-->

# Venue CSV columns

To create SKG-IF venues, name each query result after a column listed below, as defined by the official [Venue properties](https://skg-if.github.io/interoperability-framework/docs/venue.html#properties).

| Column | Description | Example |
|---|---|---|
| `local_identifier` | Primary key; groups all rows for one venue | `https://w3id.org/oc/meta/br/062501778099` |
| `name` | Venue name | `Quantitative Science Studies` |
| `type` | Venue type: `journal`, `conference`, `book`, `repository`, `other`, or `unknown` | `journal` |
| `acronym` | Venue acronym or short name | `QSS` |
| `series` | Name of the conference or book series | `Lecture Notes in Computer Science (LNCS)` |
| `creation_date` | Venue creation date or datetime in ISO 8601 format | `2019-09-13T00:00:00+00:00` |
| `identifier_scheme` | Identifier scheme for venues: `doi`, `eissn`, `isbn`, `issn`, `lissn`, `omid`, `openalex`, `opendoar`, `url`, `urn`, `w3id` | `issn` |
| `identifier_value` | The external identifier | `2641-3337` |

Both identifier fields must have a value for the pair to be used, so rows with an empty field are skipped.

## Access rights

A status is required to create the access rights object, so a description without a status is skipped.

| Column | Description | Example |
|---|---|---|
| `access_rights_status` | Access status: `open`, `closed`, or `hybrid` | `open` |
| `access_rights_description` | Qualification of the access status | `Diamond Open Access journal` |

## Contributions

RAMOSE groups rows for the same contributor through the internal key, while rows without that key or an agent name are skipped. A named contributor must have a local identifier; roles are collected without duplicates, and an external identifier is included only when both `contribution_by_identifier_scheme` and `contribution_by_identifier_value` have a value.

| Column | Description | Example |
|---|---|---|
| `contribution_by_local_identifier` | Contributor local identifier | `https://example.org/organisations/mit-press` |
| `_contribution_key` | Groups rows that describe one contributor | `publisher_0` |
| `contribution_role` | Contributor role: `publisher` or `editor` | `publisher` |
| `contribution_by_family_name` | Family name. Its presence marks the contributor as a person | `Peroni` |
| `contribution_by_given_name` | Given name | `Silvio` |
| `contribution_by_name` | Full name for organisations or agents without split names | `MIT Press` |
| `contribution_by_identifier_scheme` | Identifier scheme for the contributor | `ror` |
| `contribution_by_identifier_value` | External identifier of the contributor | `042nb2s44` |

The converter also accepts the declared-affiliation columns documented for {ref}`contributions`.
