# Comparing REST-API-over-SPARQL generators

This site runs ten server-side tools that build REST APIs over SPARQL endpoints, RAMOSE, grlc, BASIL, R4R, CRAFTS, RDFProxy, OBA, Elda, Walder, and ShExpose, and runs each on the same OpenCitations lookup.

## The test case

One bibliographic resource, looked up by DOI, with data that lives in two independent OpenCitations endpoints:

| | value |
|---|---|
| DOI | `10.1007/s11192-022-04367-w` |
| OMID | `https://w3id.org/oc/meta/br/061202127149` |
| Title (from OpenCitations Meta) | Identifying And Correcting Invalid Citations Due To DOI Errors In Crossref Data |
| References (from OpenCitations Index) | 30 |

The data comes from two local snapshots in `data/`. `meta.nt` holds the OpenCitations Meta subgraph of this resource (identifiers, authors, venue) plus two more journal articles, while `index.nt` holds its 30 references from OpenCitations Index. The Docker stack loads each file into its own Fuseki endpoint, `http://meta:3030/sparql` and `http://index:3030/sparql`, so every tool queries the same fixed data. Two more endpoints, `http://meta-basic:3030/sparql` and `http://meta-digest:3030/sparql`, load the Meta file again and ask for HTTP Basic and HTTP Digest credentials. A last copy, `http://meta-write:3030/sparql`, accepts SPARQL Update. It lives in memory, so the first data come back when the stack restarts.

One more service helps the tests. A proxy stands between the tools and Meta and records every request that passes through it. In this way the caching tests can count the SPARQL requests behind two calls that are the same.

All tools are tested across ten dimensions: join, output, pagination, versioning, API description, consumer authentication, endpoint authentication, operations, caching, and control over JSON. The RAMOSE notebook also reads a non-RDF CSV source; for the other tools, the lack of this feature comes from their documentation.

## The comparison map

Functional comparison of the generators. `✓` supported, `✗` not supported, `∼` partial.

| Dimension | RAMOSE | grlc | BASIL | OBA | R4R | CRAFTS | RDFProxy | Elda | Walder | ShExpose |
|---|---|---|---|---|---|---|---|---|---|---|
| Interface description language | OpenAPI 3.2, HTML | OpenAPI 2.0 | Swagger 1.2 | OpenAPI 3.0 | --- | OpenAPI 3.0 | OpenAPI 3.1 | LDA spec | OpenAPI 3.0 | OpenAPI 3.0 |
| Input | SPARQL | SPARQL | SPARQL | OWL ontology | SPARQL, templates | JSON config | SPARQL, model | RDF spec | GraphQL-LD, SPARQL | ShEx |
| Output | Any | endpoint-dependent | XML, JSON, CSV, RDF | JSON | JSON | JSON | JSON | Any | HTML, JSON-LD, RDF | JSON |
| Operations | CRUD | GET, POST | GET, POST | CRUD | GET | CRUD, PATCH | GET | GET | GET | CRUD |
| Configuration format | .hf/.yaml | .rq, YAML | REST API | YAML | .sparql, .vm | JSON | Pydantic model | RDF/Turtle | YAML | LinkML YAML |
| Configurable queries | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| Consumer auth. | Bearer | ✗ | ✗ | Bearer | Basic | Basic, Bearer | ✗ | ✗ | ✗ | ✗ |
| Endpoint auth. | Basic, Bearer, Digest | Basic | Basic | Basic | ✗ | Basic, Digest | Basic, Digest | Basic | ✗ | Basic, token |
| Resources | S, M, N | S, M, N | S, M | S, M, N | S, M, N | S, M, N | S, M, N | S, M, N | S, M, N | S, N |
| Versioning | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Control over JSON | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ∼ |
| Multiple endpoints | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✓ | ✗ |
| Non-RDF sources | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Join across queries | ✓ | ✗ | ✗ | ✗ | ✗ | ∼ | ✗ | ✗ | ∼ | ✗ |
| Pagination | ✓ | ✓ | ✗ | ∼ | ∼ | ✗ | ✓ | ✓ | ∼ | ✗ |
| Caching | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ | ✗ | ✗ |

Resources: `S` single resource, `M` flat collection, `N` nested resources. Authentication splits in two: consumer auth. is whether the generated API challenges its own clients for credentials; endpoint auth. is whether the tool can authenticate to the upstream SPARQL endpoint. Pagination counts as supported only when all three are present: a request parameter for a bounded window, navigation to adjacent pages, and a termination signal. OBA, R4R, and Walder offer only windowing, hence `∼`.

## Reproduce locally

The notebooks on the following pages ship with their committed outputs, so the
documentation builds without running anything. To re-run the calls yourself, bring
up the stack with Docker from the repository root:

```sh
docker compose -f docs/comparison/docker-compose.yml up -d --build
```

With the stack up, execute the notebooks from their directory:

```sh
uv run jupyter execute --inplace docs/comparison/*.ipynb
```

Stop the stack with `docker compose -f docs/comparison/docker-compose.yml down`.
