<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: CC-BY-4.0
-->

# Grant CSV columns

To convert SPARQL results into SKG-IF grants, write the operation's query so that its result variables match the column names listed below.

The column mapping follows the official [Grant properties](https://skg-if.github.io/interoperability-framework/docs/grant.html#properties).

| Column | Description | Example |
|---|---|---|
| `local_identifier` | Primary key; groups all rows for one grant | `https://example.org/grants/101017452` |
| `grant_number` | Grant number | `101017452` |
| `acronym` | Grant acronym | `OpenAIRE-Nexus` |
| `funding_stream` | Funding stream | `Horizon 2020` |
| `currency` | Currency code of the funded amount. Required when `funded_amount` has a value | `EUR` |
| `funded_amount` | Funded amount. Emitted as a JSON number, so the value must parse as one | `4000000` |
| `website` | Grant website | `https://example.org/grants/101017452` |
| `title` | Grant title | `OpenAIRE-Nexus Scholarly Communication Services for EOSC users` |
| `title_lang` | ISO 639-1 language code for the title. Falls back to `"none"` if empty | `en` |
| `abstract` | Grant abstract | `A framework of services to assist in publishing research...` |
| `abstract_lang` | ISO 639-1 language code for the abstract. Falls back to `"none"` if empty | `en` |
| `identifier_scheme` | Identifier scheme for grants: `doi`, `openalex`, `url`, `urn`, `w3id` | `doi` |
| `identifier_value` | The external identifier | `10.3030/101017452` |

Both `identifier_scheme` and `identifier_value` must be non-empty for an identifier to be included; rows where either is empty are skipped.

## Funding agency

RAMOSE builds a single organisation from the `funding_agency_*` columns only when `funding_agency_name` has a value, and the organisation must also have a local identifier. It includes an external identifier only when both `funding_agency_identifier_scheme` and `funding_agency_identifier_value` have a value.

| Column | Description | Example |
|---|---|---|
| `funding_agency_local_identifier` | Funding agency local identifier | `https://example.org/organisations/789` |
| `funding_agency_name` | Name of the funding agency | `European Commission` |
| `funding_agency_short_name` | Short name of the funding agency | `EC` |
| `funding_agency_country` | ISO 3166-1 alpha-2 country code of the funding agency | `BE` |
| `funding_agency_identifier_scheme` | Identifier scheme for the funding agency | `ror` |
| `funding_agency_identifier_value` | The external identifier of the funding agency | `00k4n6c32` |
| `funding_agency_type` | Organisation type of the funding agency: `"archive"`, `"company"`, `"education"`, `"facility"`, `"government"`, `"healthcare"`, `"nonprofit"`, `"funder"`, `"research"`, `"unspecified"` | `funder` |
| `funding_agency_website` | Website URL of the funding agency | `https://ec.europa.eu` |

## Beneficiaries

RAMOSE includes a beneficiary only when `beneficiaries_local_identifier` has a value. The name is optional. Rows are grouped by the beneficiary's local identifier.

| Column | Description | Example |
|---|---|---|
| `beneficiaries_local_identifier` | Organisation local identifier | `https://example.org/organisations/unibo` |
| `beneficiaries_name` | Organisation name | `University of Bologna` |
| `beneficiaries_short_name` | Short name or acronym | `UNIBO` |
| `beneficiaries_country` | ISO 3166-1 alpha-2 country code | `IT` |
| `beneficiaries_identifier_scheme` | Identifier scheme for the organisation | `ror` |
| `beneficiaries_identifier_value` | The external identifier of the organisation | `01111rn36` |
| `beneficiaries_type` | Organisation type: `"archive"`, `"company"`, `"education"`, `"facility"`, `"government"`, `"healthcare"`, `"nonprofit"`, `"funder"`, `"research"`, `"unspecified"` | `education` |
| `beneficiaries_website` | Website URL of the organisation | `https://www.unibo.it` |
| `beneficiaries_other_name` | Alternative name of the organisation | `Alma Mater Studiorum - Università di Bologna` |

## Contributions

Grant contributions contain a list of roles. RAMOSE groups rows for the same contributor through the internal key, while rows without that key or an agent name are skipped. An external identifier is included only when both `contribution_by_identifier_scheme` and `contribution_by_identifier_value` have a value.

| Column | Description | Example |
|---|---|---|
| `contribution_by_local_identifier` | Contributor local identifier | `https://w3id.org/oc/meta/ra/06250110138` |
| `contribution_role` | A role the agent had in the grant, from the SCoRO project roles: `"co-applicant"`, `"lead applicant"`, `"project leader"`, `"project manager"`, `"project member"`, `"workpackage leader"` | `project manager` |
| `contribution_by_family_name` | Family name. Its presence marks the contributor as a person | `Massari` |
| `contribution_by_given_name` | Given name | `Arcangelo` |
| `contribution_by_name` | Full name (for organisations or agents without split names) | `Arcangelo Massari` |
| `contribution_by_identifier_scheme` | Identifier scheme for the contributor: `crossref`, `openalex`, `orcid`, `ror`, `url`, `urn`, `viaf`, `w3id` | `orcid` |
| `contribution_by_identifier_value` | The external identifier of the contributor | `0000-0002-8420-0696` |
| `contribution_declared_affiliation_local_identifier` | Affiliation local identifier | `https://example.org/organisations/unibo` |
| `contribution_declared_affiliation_name` | Name of the declared affiliation organisation | `University of Bologna` |
| `contribution_declared_affiliation_short_name` | Short name or acronym of the affiliation | `UNIBO` |
| `contribution_declared_affiliation_country` | ISO 3166-1 alpha-2 country code of the affiliation (e.g., IT) | `IT` |
| `contribution_declared_affiliation_identifier_scheme` | Identifier scheme for the affiliation: `ror`, `url`, `urn`, `w3id` | `ror` |
| `contribution_declared_affiliation_identifier_value` | The external identifier of the affiliation | `01111rn36` |
| `contribution_declared_affiliation_type` | Organisation type: `"archive"`, `"company"`, `"education"`, `"facility"`, `"government"`, `"healthcare"`, `"nonprofit"`, `"funder"`, `"research"`, `"unspecified"` | `education` |
| `contribution_declared_affiliation_website` | Website URL of the affiliation | `https://www.unibo.it` |
| `contribution_declared_affiliation_other_name` | Alternative name of the affiliation | `Alma Mater Studiorum - Università di Bologna` |

### Internal

The converter consumes this column for deduplication, so it does not appear in the JSON-LD output.

| Column | Description | Example |
|---|---|---|
| `_contribution_key` | Deduplication key for contributors: rows sharing a key are merged into one contribution, collecting its roles and declared affiliations | `contributor_0` |

## Duration

`duration_start` is required to create the duration object. `duration_end` is optional; when omitted, the object contains only `start`.

| Column | Description | Example |
|---|---|---|
| `duration_start` | Grant start date or datetime in ISO 8601 format | `2021-01-01T00:00:00` |
| `duration_end` | Grant end date or datetime in ISO 8601 format | `2023-12-31T23:59:59` |

## Keywords

Use one row per keyword. RAMOSE collects the values without duplicates and keeps the order in which they first appear.

| Column | Description | Example |
|---|---|---|
| `keywords` | A grant keyword | `Open science` |
