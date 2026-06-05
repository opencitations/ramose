<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: CC-BY-4.0
-->

# SKG-IF integration

RAMOSE can expose any SPARQL triplestore as a [SKG-IF](https://skg-if.github.io/interoperability-framework/) compliant REST API.

## Getting started

### 1. Create the spec file

Start with the API section. Set `#addon` to `ramose.skgif_addon` and disable the built-in query parameters that SKG-IF does not use.

```
#url /skgif/v1
#type api
#base https://w3id.org/skg-if/sandbox/my-source
#title SKG-IF API for My Source
#description SKG-IF compliant API for My Source.
#version 1.0.0
#endpoint https://my-triplestore.example.org/sparql
#method get
#addon ramose.skgif_addon
#disable_params require,filter,sort,format,json
```

### 2. Add an operation

Each operation maps a URL pattern to a SPARQL query. The query must return the columns listed in the reference tables below. Multiple rows per product are expected (one per combination of identifier, contributor, topic, etc.); the converter deduplicates and aggregates them.

```
#url /products/{local_identifier}
#type operation
#method get
#description Returns a single research product.
#call /products/https://example.org/product/1
#format skgif,to_skgif
#default_format skgif
#sparql PREFIX dcterm: <http://purl.org/dc/terms/>

SELECT ?local_identifier ?product_type ?title ?title_lang
WHERE {
  BIND(<[[local_identifier]]> AS ?local_identifier)
  ?local_identifier dcterm:title ?title .
  # ... your triplestore-specific patterns here
}
```

`#format skgif,to_skgif` registers the converter; `#default_format skgif` makes JSON-LD the default output instead of CSV.

For a complete example, see the [OpenCitations spec](https://github.com/opencitations/ramose/blob/master/test/data/skgif_products.hf).

### 3. Run

Start the built-in dev server:

```bash
ramose -s my_source.hf -w 127.0.0.1:8080
```

The API serves JSON-LD at `http://127.0.0.1:8080/skgif/v1/products/{local_identifier}`.

For a runnable example querying ORKG and Wikidata, see the [live demo notebook](09-demo-skgif.ipynb).

## Product CSV columns

The `products/{local_identifier}` operation uses the columns listed below. Every SPARQL source must produce rows conforming to this schema. Multiple rows per product are expected (one per combination of identifier, contributor, citation, topic); the converter deduplicates and aggregates them.

Column names mirror JSON-LD output paths with dots replaced by underscores (SPARQL variable constraint). Columns prefixed with `_` are internal to the converter and do not appear in the output.

Optional fields with no data are omitted from the output.

Only `local_identifier` and `product_type` are required at the product level.

### Core metadata

Official reference: [Research product properties](https://skg-if.github.io/interoperability-framework/docs/research-product.html#properties).

| Column | Description | Example |
|---|---|---|
| `local_identifier` | Primary key; groups all rows for one product | `https://w3id.org/oc/meta/br/062104388184` |
| `product_type` | SKG-IF product type: `"literature"`, `"research data"`, `"research software"`, or `"other"` | `literature` |
| `title` | Product title | `OpenCitations Meta` |
| `title_lang` | ISO 639-1 language code for the title. Falls back to `"none"` if empty | `en` |
| `abstract` | Product abstract | `OpenCitations Meta is a new database for open bibliographic metadata...` |
| `abstract_lang` | ISO 639-1 language code for the abstract. Falls back to `"none"` if empty | `en` |

### Product identifiers

Official reference: [identifiers](https://skg-if.github.io/interoperability-framework/docs/research-product.html#identifiers).

Both `identifier_scheme` and `identifier_value` must be non-empty for an identifier to be included; rows where either is empty are skipped.

| Column | Description | Example |
|---|---|---|
| `identifier_scheme` | Identifier scheme for research products: `arxiv`, `bibcode`, `crossref`, `doi`, `handle`, `isbn`, `ivoid`, `omid`, `openalex`, `pmcid`, `pmid`, `spase`, `url`, `urn`, `w3id` | `doi` |
| `identifier_value` | The external identifier | `10.1162/qss_a_00292` |

### Contributions

Official reference: [contributions](https://skg-if.github.io/interoperability-framework/docs/research-product.html#contributions).

A contributor row is processed only when both `contribution_role` and `_contribution_key` are non-empty. The agent needs at least a family name, given name, or full name. Identifier `scheme`/`value` pairs and declared affiliation `scheme`/`value` pairs are co-dependent: both must be non-empty to be included.

| Column | Description | Example |
|---|---|---|
| `contribution_role` | The role of the contributing agent: `"author"`, `"editor"`, or `"publisher"` | `author` |
| `contribution_type` | CRediT contribution type: `"conceptualization"`, `"data curation"`, `"formal analysis"`, `"funding acquisition"`, `"investigation"`, `"methodology"`, `"project administration"`, `"resources"`, `"software"`, `"supervision"`, `"validation"`, `"visualization"`, `"writing – original draft"`, `"writing – review & editing"` | `writing – original draft` |
| `contribution_by_family_name` | Family name. Its presence marks the contributor as a person | `Massari` |
| `contribution_by_given_name` | Given name | `Arcangelo` |
| `contribution_by_name` | Full name (for organisations or agents without split names) | `Arcangelo Massari` |
| `contribution_by_identifier_scheme` | Identifier scheme for the contributor: `crossref`, `openalex`, `orcid`, `ror`, `url`, `urn`, `viaf`, `w3id` | `orcid` |
| `contribution_by_identifier_value` | The external identifier of the contributor | `0000-0002-8420-0696` |
| `contribution_by_local_identifier` | Contributor local identifier | `https://w3id.org/oc/meta/ra/06250110138` |
| `contribution_declared_affiliation_name` | Name of the declared affiliation organisation | `University of Bologna` |
| `contribution_declared_affiliation_short_name` | Short name or acronym of the affiliation | `UNIBO` |
| `contribution_declared_affiliation_country` | ISO 3166-1 alpha-2 country code of the affiliation (e.g., IT) | `IT` |
| `contribution_declared_affiliation_local_identifier` | Affiliation local identifier | `https://example.org/organisations/unibo` |
| `contribution_declared_affiliation_identifier_scheme` | Identifier scheme for the affiliation: `ror`, `url`, `urn`, `w3id` | `ror` |
| `contribution_declared_affiliation_identifier_value` | The external identifier of the affiliation | `01111rn36` |
| `contribution_declared_affiliation_type` | Organisation type: `"archive"`, `"company"`, `"education"`, `"facility"`, `"government"`, `"healthcare"`, `"nonprofit"`, `"funder"`, `"research"`, `"unspecified"` | `education` |
| `contribution_declared_affiliation_website` | Website URL of the affiliation | `https://www.unibo.it` |
| `contribution_declared_affiliation_other_name` | Alternative name of the affiliation | `Alma Mater Studiorum - Università di Bologna` |

See also [Internal columns](#internal) for contributor deduplication and ordering.

(internal)=
#### Internal

These columns are consumed by the converter for deduplication and ordering. They do not appear in the JSON-LD output.

| Column | Description | Example |
|---|---|---|
| `_contribution_key` | Deduplication key for contributors; also serves as the node identifier in the linked list that determines ordering within each role | `author_0` |
| `_contribution_next_key` | Points to the `_contribution_key` of the next contributor in sequence; empty for the last one. Sources that rely on SPARQL `ORDER BY` for ordering can leave this empty | `author_1` |

Contributors are ordered by role (author, then editor, then publisher) and within each role by the linked list formed by `_contribution_key` / `_contribution_next_key`.

### Topics

Official reference: [topics](https://skg-if.github.io/interoperability-framework/docs/research-product.html#topics).

`topic_term` anchors each topic entry; rows without it are skipped. Identifier and provenance fields are pairwise co-dependent: `topic_identifier_scheme`/`topic_identifier_value` and `topic_provenance_associated_with`/`topic_provenance_trust` must both be non-empty.

| Column | Description | Example |
|---|---|---|
| `topic_term` | `local_identifier` of a Topic relevant for the Research product | `topic_10102` |
| `topic_identifier_scheme` | Identifier scheme for the topic: `openalex`, `url`, `urn`, `w3id` | `openalex` |
| `topic_identifier_value` | The external identifier of the topic | `T10102` |
| `topic_label` | Label describing the topic | `Scientometrics and Bibliometrics Research` |
| `topic_label_lang` | ISO 639-1 language code for the topic label. Falls back to `"none"` if empty | `en` |
| `topic_provenance_associated_with` | `local_identifier` of the Agent responsible for the topic relation | `openalex-infra` |
| `topic_provenance_trust` | Trust value for the relation, normalized to [0,1]. Provenance entries without trust are skipped | `1` |

### Manifestations

Official reference: [manifestations](https://skg-if.github.io/interoperability-framework/docs/research-product.html#manifestations).

All fields are individually optional. Co-dependent pairs: `manifestation_identifier_scheme`/`manifestation_identifier_value`, `manifestation_dates_type`/`manifestation_dates_value`, `manifestation_biblio_pages_first`/`manifestation_biblio_pages_last`. Venue and hosting data source identifier pairs follow the same pattern.

| Column | Description | Example |
|---|---|---|
| `manifestation_type_class` | The URL of the class identifying the manifestation type (e.g. `http://purl.org/spar/fabio/JournalArticle`) | `http://purl.org/spar/fabio/JournalArticle` |
| `manifestation_type_label` | Label describing the manifestation type (e.g. `"journal article"`) | `journal article` |
| `manifestation_type_label_lang` | ISO 639-1 language code for the type label. Falls back to `"none"` if empty | `en` |
| `manifestation_identifier_scheme` | Identifier scheme for the manifestation (distinct from product-level identifiers): `arxiv`, `bibcode`, `crossref`, `doi`, `handle`, `isbn`, `ivoid`, `omid`, `openalex`, `pmcid`, `pmid`, `spase`, `url`, `urn`, `w3id` | `doi` |
| `manifestation_identifier_value` | The external identifier of the manifestation | `10.1162/qss_a_00292` |
| `manifestation_dates_type` | The type of date: `"acceptance"`, `"access"`, `"collected"`, `"copyright"`, `"correction"`, `"creation"`, `"decision"`, `"deposit"`, `"distribution"`, `"embargo"`, `"modified"`, `"publication"`, `"received"`, `"request"`, `"retraction"`, `"validity"` | `publication` |
| `manifestation_dates_value` | ISO 8601 date string; partial values like `"2024"` or `"2024-03"` are normalized to full datetime (e.g. `"2024-01-01T00:00:00"`) | `2024-03-01T00:00:00` |
| `manifestation_peer_review_status` | Peer review status: `"peer reviewed"` or `"under review"` | `peer reviewed` |
| `manifestation_peer_review_description` | Peer review type: `"single-blind peer review"`, `"double-blind peer review"`, or `"open peer review"` | `single-blind peer review` |
| `manifestation_access_rights_status` | Access status: `"open"`, `"closed"`, `"embargoed"`, `"restricted"`, or `"unavailable"` | `open` |
| `manifestation_access_rights_description` | Qualification of the access status | `Freely available` |
| `manifestation_licence` | The URL of the licence for the manifestation | `https://creativecommons.org/licenses/by/4.0/legalcode` |
| `manifestation_version` | Version identifier (for software or research data manifestations) | `1.0.0` |
| `manifestation_biblio_volume` | Volume number | `5` |
| `manifestation_biblio_issue` | Issue number | `1` |
| `manifestation_biblio_edition` | The edition (for journals and books) | `1` |
| `manifestation_biblio_number` | Manifestation number within the venue (e.g., chapter number) | `3` |
| `manifestation_biblio_pages_first` | The starting page. Both `manifestation_biblio_pages_first` and `manifestation_biblio_pages_last` must be present; if there is only one page, use the same value for both | `50` |
| `manifestation_biblio_pages_last` | The ending page | `75` |
| `manifestation_biblio_in_name` | Venue name. Its presence triggers the venue sub-object | `Quantitative Science Studies` |
| `manifestation_biblio_in_local_identifier` | Venue local identifier | `https://w3id.org/oc/meta/br/062501778099` |
| `manifestation_biblio_in_identifier_scheme` | Identifier scheme for the venue: `doi`, `eissn`, `isbn`, `issn`, `lissn`, `openalex`, `opendoar`, `url`, `urn`, `w3id` | `issn` |
| `manifestation_biblio_in_identifier_value` | Venue identifier value | `2641-3337` |
| `manifestation_biblio_in_acronym` | Venue acronym or short name | `QSS` |
| `manifestation_biblio_hosting_data_source_local_identifier` | Local identifier of the data source hosting the manifestation. Its presence triggers the hosting data source sub-object | `https://example.org/datasources/mitpress` |
| `manifestation_biblio_hosting_data_source_name` | Name of the hosting data source | `MIT Press` |
| `manifestation_biblio_hosting_data_source_identifier_scheme` | Identifier scheme for the hosting data source | `crossref` |
| `manifestation_biblio_hosting_data_source_identifier_value` | Identifier value for the hosting data source | `281` |

### Related products

Official reference: [related_products](https://skg-if.github.io/interoperability-framework/docs/research-product.html#related_products).

| Column | Description | Example |
|---|---|---|
| `related_products_cites` | Identifier of a Research product cited by the given product | `https://w3id.org/oc/meta/br/062501777134` |
| `related_products_is_supplemented_by` | Identifier of a Research product that supplements the given product | `https://example.org/products/1` |
| `related_products_is_documented_by` | Identifier of a Research product that documents the given product | `https://example.org/products/2` |
| `related_products_is_new_version_of` | Identifier of a Research product that is an older version of the given product | `https://example.org/products/3` |
| `related_products_is_part_of` | Identifier of a Research product that contains the given product | `https://example.org/products/4` |

### Funding

Official reference: [funding](https://skg-if.github.io/interoperability-framework/docs/research-product.html#funding).

`funding_local_identifier` anchors each grant entry; rows without it are skipped. `funding_agency_name` must be non-empty for the agency sub-object to be built. Identifier pairs (`funding_identifier_scheme`/`funding_identifier_value` and `funding_agency_identifier_scheme`/`funding_agency_identifier_value`) are co-dependent.

| Column | Description | Example |
|---|---|---|
| `funding_local_identifier` | Grant local identifier | `https://example.org/grants/101017452` |
| `funding_grant_number` | Grant number | `101017452` |
| `funding_title` | Grant title | `OpenAIRE-Nexus Scholarly Communication Services for EOSC users` |
| `funding_title_lang` | ISO 639-1 language code for the grant title. Falls back to `"none"` if empty | `en` |
| `funding_abstract` | Grant abstract | `A framework of services to assist in publishing research...` |
| `funding_abstract_lang` | ISO 639-1 language code for the grant abstract. Falls back to `"none"` if empty | `en` |
| `funding_acronym` | Grant acronym | `OpenAIRE-Nexus` |
| `funding_identifier_scheme` | Identifier scheme for the grant | `doi` |
| `funding_identifier_value` | The external identifier of the grant | `10.3030/101017452` |
| `funding_stream` | Funding stream (e.g. "Horizon Europe") | `Horizon 2020` |
| `funding_agency_name` | Name of the funding agency | `European Commission` |
| `funding_agency_short_name` | Short name of the funding agency | `EC` |
| `funding_agency_country` | ISO 3166-1 alpha-2 country code of the funding agency | `BE` |
| `funding_agency_local_identifier` | Funding agency local identifier | `https://example.org/organisations/789` |
| `funding_agency_identifier_scheme` | Identifier scheme for the funding agency | `ror` |
| `funding_agency_identifier_value` | The external identifier of the funding agency | `00k4n6c32` |
| `funding_agency_type` | Organisation type of the funding agency: `"archive"`, `"company"`, `"education"`, `"facility"`, `"government"`, `"healthcare"`, `"nonprofit"`, `"funder"`, `"research"`, `"unspecified"` | `funder` |
| `funding_agency_website` | Website URL of the funding agency | `https://ec.europa.eu` |

### Relevant organisations

Official reference: [relevant_organisations](https://skg-if.github.io/interoperability-framework/docs/research-product.html#relevant_organisations).

A row is included when it has at least a `relevant_organisation_name` or `relevant_organisation_local_identifier`. Identifier `scheme`/`value` pairs are co-dependent.

| Column | Description | Example |
|---|---|---|
| `relevant_organisation_name` | Organisation name | `University of Bologna` |
| `relevant_organisation_short_name` | Short name or acronym | `UNIBO` |
| `relevant_organisation_country` | ISO 3166-1 alpha-2 country code | `IT` |
| `relevant_organisation_local_identifier` | Organisation local identifier | `https://example.org/organisations/unibo` |
| `relevant_organisation_identifier_scheme` | Identifier scheme for the organisation | `ror` |
| `relevant_organisation_identifier_value` | The external identifier of the organisation | `01111rn36` |
| `relevant_organisation_type` | Organisation type: `"archive"`, `"company"`, `"education"`, `"facility"`, `"government"`, `"healthcare"`, `"nonprofit"`, `"funder"`, `"research"`, `"unspecified"` | `education` |
| `relevant_organisation_website` | Website URL of the organisation | `https://www.unibo.it` |
| `relevant_organisation_other_name` | Alternative name of the organisation | `Alma Mater Studiorum - Università di Bologna` |
