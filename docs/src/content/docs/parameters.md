---
title: Query parameters
description: Filtering, sorting, and formatting API responses.
---

<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: ISC
-->

Query parameters are passed as standard HTTP query string arguments. They are applied after the SPARQL query returns and after postprocessing, in this fixed order: require, filter, sort, format/json. Pagination (`page`, `page_size`) is applied last, after all filtering and sorting.

Operations can override any of these built-in parameters with a [custom parameter handler](/ramose/addons/#custom-parameters) via the `#custom_params` field. When overridden, the built-in behavior is replaced by the addon function.

## require

Remove rows where a field is empty.

```
?require=author
?require=author&require=venue
```

## filter

Keep only rows matching a condition. Three modes:

**Regex** (no operator): the value is treated as a regular expression.

```
?filter=title:opencitations
```

**Comparison** (`=`, `<`, `>`): compared using the field's declared type from `#field_type`.

```
?filter=pub_date:>2020
?filter=volume:=5
?filter=pub_date:<2024
```

Multiple filters stack:

```
?filter=pub_date:>2020&filter=type:journal article
```

## sort

Sort rows by a field in ascending or descending order.

```
?sort=asc(pub_date)
?sort=desc(pub_date)
```

Multiple sort parameters are applied in sequence:

```
?sort=asc(pub_date)&sort=desc(title)
```

## format

Override the response format. Takes priority over the `Accept` header.

```
?format=csv
?format=json
```

Custom formats registered via [`#format`](/ramose/addons/#format-converters) are also available (e.g., `?format=xml`).

## json

Transform fields in JSON responses. Only applies when the output format is JSON.

**array**: split a string into an array by separator.

```
?json=array("; ", author)
```

`"Massari, Arcangelo [orcid:0000-0002-8420-0696 omid:ra/06250110138]; Mariani, Fabio [orcid:0000-0002-7382-0187 omid:ra/0621012370562]"` becomes `["Massari, Arcangelo [orcid:0000-0002-8420-0696 omid:ra/06250110138]", "Mariani, Fabio [orcid:0000-0002-7382-0187 omid:ra/0621012370562]"]`.

**dict**: split a string into an object with named keys.

```
?json=dict(", ", author, family, given)
```

`"Massari, Arcangelo"` becomes `{"family": "Massari", "given": "Arcangelo"}`.

Both transformations work on nested paths using dot notation:

```
?json=array(";", person.names)
```

Multiple transformations can be chained. Each one operates on the result of the previous:

```
?json=array("; ", author)&json=dict(", ", author, family, given)
```

## page and page_size

Paginate results by specifying the page size and the page number. Without these parameters, all results are returned.

```
?page_size=10
?page=2&page_size=10
```

`page_size` sets the number of items per page. `page` selects which page to return (1-indexed, defaults to 1 when only `page_size` is provided).

When pagination is active, the response includes a `Link` HTTP header with navigation URLs using relation types from the [IANA Link Relations registry](https://www.iana.org/assignments/link-relations/), serialized following [RFC 8288](https://www.rfc-editor.org/rfc/rfc8288).

Example `Link` header for a request to `?page=2&page_size=10` on a 42-item result set:

```
Link: </v1/metadata/doi:10.1162/qss_a_00292?page=3&page_size=10>; rel="next",
      </v1/metadata/doi:10.1162/qss_a_00292?page=1&page_size=10>; rel="prev",
      </v1/metadata/doi:10.1162/qss_a_00292?page=1&page_size=10>; rel="first",
      </v1/metadata/doi:10.1162/qss_a_00292?page=5&page_size=10>; rel="last"
```

Each comma-separated entry is a separate link. `rel="first"` and `rel="last"` are always present. `rel="next"` is omitted on the last page; `rel="prev"` is omitted on the first page.

The response body contains only the sliced results for the requested page, in the same format as a non-paginated response (JSON array or CSV rows).

Invalid values (`page_size=0`, `page=-1`, non-integer values, `page` exceeding total pages) return HTTP 400.

## Combined example

```
/v1/metadata/doi:10.1162/qss_a_00292?require=author&filter=pub_date:>2020&sort=desc(pub_date)&format=csv
```

This removes rows without an author, keeps only those published after 2020, sorts by date descending, and returns CSV.

## Disabling built-in parameters

Operations or entire APIs can suppress built-in parameters with `#disable_params` in the spec file. When disabled, the parameter has no effect at runtime and does not appear in generated documentation.

```
#disable_params require,sort,format,json,page,page_size
```

Use `*` to disable all built-in parameters at once:

```
#disable_params *
```

See the [spec file reference](/ramose/spec_file/) for placement and syntax.
