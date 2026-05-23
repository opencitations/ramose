---
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: CC-BY-4.0

title: SKG-IF integration
description: Using RAMOSE to serve SKG-IF compliant APIs from SPARQL endpoints.
---

RAMOSE can expose any SPARQL triplestore as a [SKG-IF](https://skg-if.github.io/interoperability-framework/) compliant REST API. The architecture has three layers:

1. **Source-specific SPARQL queries** in `.hf` spec files map each triplestore's data model to a standardized CSV schema
2. **A shared converter** (`to_skgif` format function in the addon module) transforms the CSV into JSON-LD following the SKG-IF data model
3. **RAMOSE** handles routing, pagination, caching, and documentation

Each triplestore only needs its own `.hf` file with the appropriate SPARQL queries. The converter is reused without modification.

## Product CSV columns

The `products/{local_identifier}` operation uses the columns listed below. Every SPARQL source must produce rows conforming to this schema. Multiple rows per product are expected (one per combination of identifier, contributor, citation, topic); the converter deduplicates and aggregates them.

Column names mirror JSON-LD output paths with dots replaced by underscores (SPARQL variable constraint). For contributions, `contribution_by_*` columns map to fields nested under `contribution.by` (the agent object), while `contribution_*` columns without `by` map to contribution-level fields like `role`. Columns prefixed with `_` are internal to the converter and do not appear in the output.

All optional fields are always present in the output. Dict-typed fields default to `{}`, array-typed fields to `[]`.

The Status column indicates whether the field is required or optional within its parent sub-object. All sections except Core metadata are optional at the product level; see the official reference for each section.

### Core metadata

Official reference: [Research product properties](https://skg-if.github.io/interoperability-framework/docs/research-product.html#properties).

| Column | Description | Example | Status |
|---|---|---|---|
| `local_identifier` | Primary key; groups all rows for one product | `https://w3id.org/oc/meta/br/062104388184` | Required |
| `product_type` | SKG-IF product type: `"literature"`, `"research data"`, `"research software"`, or `"other"` | `literature` | Required |
| `title` | Product title | `OpenCitations Meta` | Optional |
| `title_lang` | ISO 639-1 language code for the title. Falls back to `"none"` if empty | `en` | Optional |
| `abstract` | Product abstract | `OpenCitations Meta is a new database for open bibliographic metadata...` | Optional |
| `abstract_lang` | ISO 639-1 language code for the abstract. Falls back to `"none"` if empty | `en` | Optional |

### Product identifiers

Official reference: [identifiers](https://skg-if.github.io/interoperability-framework/docs/research-product.html#identifiers).

| Column | Description | Example | Status |
|---|---|---|---|
| `identifier_scheme` | Identifier scheme for research products: `arxiv`, `bibcode`, `crossref`, `doi`, `handle`, `isbn`, `ivoid`, `omid`, `openalex`, `pmcid`, `pmid`, `spase`, `url`, `urn`, `w3id` | `doi` | Required |
| `identifier_value` | The external identifier | `10.1162/qss_a_00292` | Required |

### Contributions

Official reference: [contributions](https://skg-if.github.io/interoperability-framework/docs/research-product.html#contributions).

| Column | Description | Example | Status |
|---|---|---|---|
| `contribution_role` | The role of the contributing agent: `"author"`, `"editor"`, or `"publisher"` | `author` | Optional |
| `contribution_type` | CRediT contribution type: `"conceptualization"`, `"data curation"`, `"formal analysis"`, `"funding acquisition"`, `"investigation"`, `"methodology"`, `"project administration"`, `"resources"`, `"software"`, `"supervision"`, `"validation"`, `"visualization"`, `"writing – original draft"`, `"writing – review & editing"` | `writing – original draft` | Optional |
| `contribution_by_family_name` | Family name. Its presence marks the contributor as a person | `Massari` | Optional |
| `contribution_by_given_name` | Given name | `Arcangelo` | Optional |
| `contribution_by_name` | Full name (for organisations or agents without split names) | `Arcangelo Massari` | Optional |
| `contribution_by_identifier_scheme` | Identifier scheme for the contributor: `crossref`, `openalex`, `orcid`, `ror`, `url`, `urn`, `viaf`, `w3id` | `orcid` | Required |
| `contribution_by_identifier_value` | The external identifier of the contributor | `0000-0002-8420-0696` | Required |
| `contribution_by_local_identifier` | Contributor local identifier | `https://w3id.org/oc/meta/ra/06250110138` | Required |
| `contribution_declared_affiliation_name` | Name of the declared affiliation organisation | `University of Bologna` | Optional |
| `contribution_declared_affiliation_short_name` | Short name or acronym of the affiliation | `UNIBO` | Optional |
| `contribution_declared_affiliation_country` | ISO 3166-1 alpha-2 country code of the affiliation (e.g., IT) | `IT` | Optional |
| `contribution_declared_affiliation_local_identifier` | Affiliation local identifier | `https://example.org/organisations/unibo` | Required |
| `contribution_declared_affiliation_identifier_scheme` | Identifier scheme for the affiliation: `ror`, `url`, `urn`, `w3id` | `ror` | Required |
| `contribution_declared_affiliation_identifier_value` | The external identifier of the affiliation | `01111rn36` | Required |
| `contribution_declared_affiliation_type` | Organisation type: `"archive"`, `"company"`, `"education"`, `"facility"`, `"government"`, `"healthcare"`, `"nonprofit"`, `"funder"`, `"research"`, `"unspecified"` | `education` | Optional |
| `contribution_declared_affiliation_website` | Website URL of the affiliation | `https://www.unibo.it` | Optional |
| `contribution_declared_affiliation_other_name` | Alternative name of the affiliation | `Alma Mater Studiorum - Università di Bologna` | Optional |

See also [Internal columns](#internal) for contributor deduplication and ordering.

#### Internal

These columns are consumed by the converter for deduplication and ordering. They do not appear in the JSON-LD output.

| Column | Description | Example | Status |
|---|---|---|---|
| `_contribution_key` | Deduplication key for contributors; also serves as the node identifier in the linked list that determines ordering within each role | `author_0` | Optional |
| `_contribution_next_key` | Points to the `_contribution_key` of the next contributor in sequence; empty for the last one. Sources that rely on SPARQL `ORDER BY` for ordering can leave this empty | `author_1` | Optional |

Contributors are ordered by role (author, then editor, then publisher) and within each role by the linked list formed by `_contribution_key` / `_contribution_next_key`.

### Topics

Official reference: [topics](https://skg-if.github.io/interoperability-framework/docs/research-product.html#topics).

| Column | Description | Example | Status |
|---|---|---|---|
| `topic_term` | `local_identifier` of a Topic relevant for the Research product | `topic_10102` | Required |
| `topic_identifier_scheme` | Identifier scheme for the topic: `openalex`, `url`, `urn`, `w3id` | `openalex` | Required |
| `topic_identifier_value` | The external identifier of the topic | `T10102` | Required |
| `topic_label` | Label describing the topic | `Scientometrics and Bibliometrics Research` | Optional |
| `topic_label_lang` | ISO 639-1 language code for the topic label. Falls back to `"none"` if empty | `en` | Optional |
| `topic_provenance_associated_with` | `local_identifier` of the Agent responsible for the topic relation | `openalex-infra` | Required |
| `topic_provenance_trust` | Trust value for the relation, normalized to [0,1]. Required: provenance entries without trust are skipped | `1` | Required |

### Manifestations

Official reference: [manifestations](https://skg-if.github.io/interoperability-framework/docs/research-product.html#manifestations).

| Column | Description | Example | Status |
|---|---|---|---|
| `manifestation_type_class` | The URL of the class identifying the manifestation type (e.g. `http://purl.org/spar/fabio/JournalArticle`) | `http://purl.org/spar/fabio/JournalArticle` | Optional |
| `manifestation_type_label` | Label describing the manifestation type (e.g. `"journal article"`) | `journal article` | Optional |
| `manifestation_type_label_lang` | ISO 639-1 language code for the type label. Falls back to `"none"` if empty | `en` | Optional |
| `manifestation_identifier_scheme` | Identifier scheme for the manifestation (distinct from product-level identifiers): `arxiv`, `bibcode`, `crossref`, `doi`, `handle`, `isbn`, `ivoid`, `omid`, `openalex`, `pmcid`, `pmid`, `spase`, `url`, `urn`, `w3id` | `doi` | Required |
| `manifestation_identifier_value` | The external identifier of the manifestation | `10.1162/qss_a_00292` | Required |
| `manifestation_dates_type` | The type of date: `"acceptance"`, `"access"`, `"collected"`, `"copyright"`, `"correction"`, `"creation"`, `"decision"`, `"deposit"`, `"distribution"`, `"embargo"`, `"modified"`, `"publication"`, `"received"`, `"request"`, `"retraction"`, `"validity"` | `publication` | Optional |
| `manifestation_dates_value` | ISO 8601 date string; partial values like `"2024"` or `"2024-03"` are normalized to full datetime (e.g. `"2024-01-01T00:00:00"`) | `2024-03-01T00:00:00` | Optional |
| `manifestation_peer_review_status` | Peer review status: `"peer reviewed"` or `"under review"` | `peer reviewed` | Required |
| `manifestation_peer_review_description` | Peer review type: `"single-blind peer review"`, `"double-blind peer review"`, or `"open peer review"` | `single-blind peer review` | Optional |
| `manifestation_access_rights_status` | Access status: `"open"`, `"closed"`, `"embargoed"`, `"restricted"`, or `"unavailable"` | `open` | Required |
| `manifestation_access_rights_description` | Qualification of the access status | `Freely available` | Optional |
| `manifestation_licence` | The URL of the licence for the manifestation | `https://creativecommons.org/licenses/by/4.0/legalcode` | Optional |
| `manifestation_version` | Version identifier (for software or research data manifestations) | `1.0.0` | Optional |
| `manifestation_biblio_volume` | Volume number | `5` | Optional |
| `manifestation_biblio_issue` | Issue number | `1` | Optional |
| `manifestation_biblio_edition` | The edition (for journals and books) | `1` | Optional |
| `manifestation_biblio_number` | Manifestation number within the venue (e.g., chapter number) | `3` | Optional |
| `manifestation_biblio_pages_first` | The starting page. Both `manifestation_biblio_pages_first` and `manifestation_biblio_pages_last` must be present; if there is only one page, use the same value for both | `50` | Required |
| `manifestation_biblio_pages_last` | The ending page | `75` | Required |
| `manifestation_biblio_in_name` | Venue name | `Quantitative Science Studies` | Optional |
| `manifestation_biblio_in_local_identifier` | Venue local identifier | `https://w3id.org/oc/meta/br/062501778099` | Required |
| `manifestation_biblio_in_identifier_scheme` | Identifier scheme for the venue: `doi`, `eissn`, `isbn`, `issn`, `lissn`, `openalex`, `opendoar`, `url`, `urn`, `w3id` | `issn` | Required |
| `manifestation_biblio_in_identifier_value` | Venue identifier value | `2641-3337` | Required |
| `manifestation_biblio_in_acronym` | Venue acronym or short name | `QSS` | Optional |
| `manifestation_biblio_hosting_data_source_local_identifier` | Local identifier of the data source hosting the manifestation | `https://example.org/datasources/mitpress` | Required |
| `manifestation_biblio_hosting_data_source_name` | Name of the hosting data source | `MIT Press` | Optional |
| `manifestation_biblio_hosting_data_source_identifier_scheme` | Identifier scheme for the hosting data source | `crossref` | Required |
| `manifestation_biblio_hosting_data_source_identifier_value` | Identifier value for the hosting data source | `281` | Required |

### Related products

Official reference: [related_products](https://skg-if.github.io/interoperability-framework/docs/research-product.html#related_products).

| Column | Description | Example | Status |
|---|---|---|---|
| `related_products_cites` | Identifier of a Research product cited by the given product | `https://w3id.org/oc/meta/br/062501777134` | Optional |
| `related_products_is_supplemented_by` | Identifier of a Research product that supplements the given product | `https://example.org/products/1` | Optional |
| `related_products_is_documented_by` | Identifier of a Research product that documents the given product | `https://example.org/products/2` | Optional |
| `related_products_is_new_version_of` | Identifier of a Research product that is an older version of the given product | `https://example.org/products/3` | Optional |
| `related_products_is_part_of` | Identifier of a Research product that contains the given product | `https://example.org/products/4` | Optional |

### Funding

Official reference: [funding](https://skg-if.github.io/interoperability-framework/docs/research-product.html#funding).

| Column | Description | Example | Status |
|---|---|---|---|
| `funding_local_identifier` | Grant local identifier | `https://example.org/grants/101017452` | Required |
| `funding_grant_number` | Grant number | `101017452` | Optional |
| `funding_title` | Grant title | `OpenAIRE-Nexus Scholarly Communication Services for EOSC users` | Optional |
| `funding_title_lang` | ISO 639-1 language code for the grant title. Falls back to `"none"` if empty | `en` | Optional |
| `funding_abstract` | Grant abstract | `A framework of services to assist in publishing research...` | Optional |
| `funding_abstract_lang` | ISO 639-1 language code for the grant abstract. Falls back to `"none"` if empty | `en` | Optional |
| `funding_acronym` | Grant acronym | `OpenAIRE-Nexus` | Optional |
| `funding_identifier_scheme` | Identifier scheme for the grant | `doi` | Required |
| `funding_identifier_value` | The external identifier of the grant | `10.3030/101017452` | Required |
| `funding_stream` | Funding stream (e.g. "Horizon Europe") | `Horizon 2020` | Optional |
| `funding_agency_name` | Name of the funding agency | `European Commission` | Optional |
| `funding_agency_short_name` | Short name of the funding agency | `EC` | Optional |
| `funding_agency_country` | ISO 3166-1 alpha-2 country code of the funding agency | `BE` | Optional |
| `funding_agency_local_identifier` | Funding agency local identifier | `https://example.org/organisations/789` | Required |
| `funding_agency_identifier_scheme` | Identifier scheme for the funding agency | `ror` | Required |
| `funding_agency_identifier_value` | The external identifier of the funding agency | `00k4n6c32` | Required |
| `funding_agency_type` | Organisation type of the funding agency: `"archive"`, `"company"`, `"education"`, `"facility"`, `"government"`, `"healthcare"`, `"nonprofit"`, `"funder"`, `"research"`, `"unspecified"` | `funder` | Optional |
| `funding_agency_website` | Website URL of the funding agency | `https://ec.europa.eu` | Optional |

### Relevant organisations

Official reference: [relevant_organisations](https://skg-if.github.io/interoperability-framework/docs/research-product.html#relevant_organisations).

| Column | Description | Example | Status |
|---|---|---|---|
| `relevant_organisation_name` | Organisation name | `University of Bologna` | Optional |
| `relevant_organisation_short_name` | Short name or acronym | `UNIBO` | Optional |
| `relevant_organisation_country` | ISO 3166-1 alpha-2 country code | `IT` | Optional |
| `relevant_organisation_local_identifier` | Organisation local identifier | `https://example.org/organisations/unibo` | Required |
| `relevant_organisation_identifier_scheme` | Identifier scheme for the organisation | `ror` | Required |
| `relevant_organisation_identifier_value` | The external identifier of the organisation | `01111rn36` | Required |
| `relevant_organisation_type` | Organisation type: `"archive"`, `"company"`, `"education"`, `"facility"`, `"government"`, `"healthcare"`, `"nonprofit"`, `"funder"`, `"research"`, `"unspecified"` | `education` | Optional |
| `relevant_organisation_website` | Website URL of the organisation | `https://www.unibo.it` | Optional |
| `relevant_organisation_other_name` | Alternative name of the organisation | `Alma Mater Studiorum - Università di Bologna` | Optional |