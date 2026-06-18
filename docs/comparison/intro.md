# Comparing REST-API-over-SPARQL generators

This site runs nine server-side tools that build REST APIs over SPARQL endpoints, RAMOSE, grlc, BASIL, R4R, CRAFTS, RDFProxy, OBA, Elda, and Walder, and runs each on the same OpenCitations lookup.

## The test case

One bibliographic resource, looked up by DOI, with data that lives in two independent OpenCitations endpoints:

| | value |
|---|---|
| DOI | `10.1007/s11192-022-04367-w` |
| OMID | `https://w3id.org/oc/meta/br/061202127149` |
| Title (from OpenCitations Meta) | Identifying And Correcting Invalid Citations Due To DOI Errors In Crossref Data |
| References (from OpenCitations Index) | 30 |

Endpoints:

- Meta: `https://sparql.opencitations.net/meta`
- Index: `https://sparql.opencitations.net/index`

All tools are tested across six dimensions: join, output, pagination, versioning, API description, and authentication.

## The comparison map

Functional comparison of the generators. `✓` supported, `✗` not supported, `∼` partial.

| Dimension | RAMOSE | grlc | BASIL | OBA | R4R | CRAFTS | RDFProxy | Elda | Walder |
|---|---|---|---|---|---|---|---|---|---|
| Interface description language | OpenAPI 3.1, HTML | OpenAPI 2.0 | Swagger 1.2 | OpenAPI 3.0 | --- | OpenAPI 3.0 | OpenAPI 3.1 | LDA spec | OpenAPI 3.0 |
| Input | SPARQL | SPARQL | SPARQL | OWL ontology | SPARQL, templates | JSON config | SPARQL, model | RDF spec | GraphQL-LD, SPARQL |
| Output | Any | endpoint-dependent | XML, JSON, CSV, RDF | JSON | JSON | JSON | JSON | Any | HTML, JSON-LD, RDF |
| Operations | CRUD | GET, POST | GET, POST | CRUD | GET | CRUD, PATCH | GET | GET | GET |
| Configuration format | .hf/.yaml | .rq, YAML | REST API | YAML | .sparql, .vm | JSON | Pydantic model | RDF/Turtle | YAML |
| Configurable queries | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Authentication | Bearer | ✗ | Basic | Bearer | Basic | Basic, Bearer | ✗ | ✗ | ✗ |
| Resources | S, M, N | S, M, N | S, M | S, M, N | S, M, N | S, M, N | S, M, N | S, M, N | S, M, N |
| Versioning | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Control over JSON | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Multiple endpoints | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✓ |
| Non-RDF sources | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Join across queries | ✓ | ✗ | ✗ | ✗ | ✗ | ∼ | ✗ | ✗ | ∼ |
| Pagination | ✓ | ✓ | ✗ | ∼ | ∼ | ✗ | ✓ | ✓ | ∼ |
| Caching | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ |

Resources: `S` single resource, `M` flat collection, `N` nested resources. Pagination counts as supported only when all three are present: a request parameter for a bounded window, navigation to adjacent pages, and a termination signal. OBA, R4R, and Walder offer only windowing, hence `∼`.

## Reproduce locally

The notebooks on the following pages ship with their committed outputs, so the
documentation builds without running anything. To re-run the calls yourself, bring
up the nine-service stack with Docker from the repository root:

```sh
docker compose -f docs/comparison/docker-compose.yml up -d --build
```

With the stack up, execute the notebooks from their directory:

```sh
uv run jupyter execute --inplace docs/comparison/*.ipynb
```

Stop the stack with `docker compose -f docs/comparison/docker-compose.yml down`.
