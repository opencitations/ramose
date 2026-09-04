<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: CC-BY-4.0
-->

# Topic CSV columns

To convert SPARQL results into SKG-IF topics, write the operation's query so that its result variables match the column names listed below.

Official reference: [Topic properties](https://skg-if.github.io/interoperability-framework/docs/topic.html#properties).

| Column | Description | Example |
|---|---|---|
| `local_identifier` | Primary key; groups all rows for one topic | `topic_10102` |
| `label` | Topic label | `Scientometrics and Bibliometrics Research` |
| `label_lang` | ISO 639-1 language code for the label. Falls back to `"none"` if empty | `en` |
| `identifier_scheme` | Identifier scheme for topics: `openalex`, `url`, `urn`, `w3id` | `openalex` |
| `identifier_value` | The external identifier | `T10102` |

Both `identifier_scheme` and `identifier_value` must be non-empty for an identifier to be included; rows where either is empty are skipped.
