<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: CC-BY-4.0
-->

# Data source CSV columns

To convert SPARQL results into SKG-IF data sources, write the operation's query so that its result variables match the column names listed below.

Official reference: [Data source properties](https://skg-if.github.io/interoperability-framework/docs/data-source.html#properties).

| Column | Description | Example |
|---|---|---|
| `local_identifier` | Primary key; groups all rows for one data source | `https://example.org/datasources/mitpress` |
| `name` | Data source name | `MIT Press` |
| `data_source_classification` | Data source classification: `repository`, `aggregator`, `scientific database`, `journal archive`, `publisher archive`, or `cris system` | `journal archive` |
| `research_product_types` | Managed research product type: `metadata`, `research data`, `literature`, `software`, or `any` | `literature` |
| `identifier_scheme` | Identifier scheme for data sources: `doi`, `handle`, `ivoid`, `openalex`, `opendoar`, `url`, `urn`, or `w3id` | `opendoar` |
| `identifier_value` | The external identifier | `2659` |

Both `identifier_scheme` and `identifier_value` must be non-empty for an identifier to be included; rows where either is empty are skipped.

Use one row per type, and RAMOSE collects the values without duplicates in the order in which they first appear.

## Persistent identity systems

Both `persistent_identity_system_for` and `persistent_identity_system_pid_scheme` must have a value for the object to be included. RAMOSE groups rows by `_persistent_identity_system_key`, while it uses the research product type when that key is empty.

| Column | Description | Example |
|---|---|---|
| `_persistent_identity_system_key` | Groups rows that describe one persistent identity system | `literature_pids` |
| `persistent_identity_system_for` | Research product type: `literature`, `research data`, `software`, `metadata`, or `any` | `literature` |
| `persistent_identity_system_pid_scheme` | Persistent identifier scheme: `doi`, `handle`, `ror`, `orcid`, `isni`, `arxiv`, `pmcid`, or `ark` | `doi` |

## Audience

Use one row per audience type.

| Column | Description | Example |
|---|---|---|
| `audience_type` | Audience type: `Global`, `National`, `Regional`, `Institution`, `Research Infrastructure`, or `e-Infrastructure` | `Global` |

## Disciplines

Use one row per Library of Congress Classification code or `all` when the data source is not dedicated to a discipline; RAMOSE collects the values without duplicates in the order in which they first appear.

| Column | Description | Example |
|---|---|---|
| `disciplines` | Library of Congress Classification code, or `all` | `QC790.95-QC791.8` |

## Policies

`policy_about` is required to create a policy object. RAMOSE groups rows by `_policy_key` and uses `policy_about` when that key is empty, so use one row per target.

| Column | Description | Example |
|---|---|---|
| `_policy_key` | Groups rows that describe one policy | `open_access_policy` |
| `policy_about` | Policy type: `submission`, `preservation`, `embargoed access`, `metadata only access`, `open access`, or `restricted access` | `open access` |
| `policy_target` | Target research product type: `metadata`, `research data`, `literature`, `software`, or `any` | `literature` |
| `policy_documented_at` | URL of the document that describes the policy | `https://example.org/open-access` |
| `policy_description` | Policy description | `Open-access policy` |
