from typing import Annotated

from fastapi import FastAPI, Query
from pydantic import BaseModel

from rdfproxy import (
    ConfigDict,
    Page,
    QueryParameters,
    SPARQLBinding,
    SPARQLModelAdapter,
)

META = "https://sparql.opencitations.net/meta"
CLIENT: dict = {"timeout": 60.0}

app = FastAPI(title="OpenCitations Meta (RDFProxy demo)", version="1.0.0")


def sparql_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


ARTICLE_QUERY = """\
PREFIX datacite: <http://purl.org/spar/datacite/>
PREFIX literal: <http://www.essepuntato.it/2010/06/literalreification/>
PREFIX dcterms: <http://purl.org/dc/terms/>
SELECT ?doi ?title ?br WHERE {{
  ?id datacite:usesIdentifierScheme datacite:doi ;
      literal:hasLiteralValue "{doi}" .
  ?br datacite:hasIdentifier ?id ;
      dcterms:title ?title .
  BIND("{doi}" AS ?doi)
}}"""

AUTHORS_QUERY = """\
PREFIX datacite: <http://purl.org/spar/datacite/>
PREFIX literal: <http://www.essepuntato.it/2010/06/literalreification/>
PREFIX pro: <http://purl.org/spar/pro/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
SELECT ?author ?family ?given WHERE {{
  ?id datacite:usesIdentifierScheme datacite:doi ;
      literal:hasLiteralValue "{doi}" .
  ?br datacite:hasIdentifier ?id ;
      pro:isDocumentContextFor ?ar .
  ?ar pro:withRole pro:author ;
      pro:isHeldBy ?author .
  OPTIONAL {{ ?author foaf:familyName ?family }}
  OPTIONAL {{ ?author foaf:givenName ?given }}
}}"""


class Article(BaseModel):
    doi: str
    title: str
    br: str


class Author(BaseModel):
    model_config = ConfigDict(group_by="author")

    author: str
    family: Annotated[list[str], SPARQLBinding("family")]
    given: Annotated[list[str], SPARQLBinding("given")]


@app.get("/articles/{doi:path}/authors")
def authors(doi: str, params: Annotated[QueryParameters, Query()]) -> Page[Author]:
    query = AUTHORS_QUERY.format(doi=sparql_string(doi))
    adapter = SPARQLModelAdapter(
        target=META, query=query, model=Author, aclient_config=CLIENT
    )
    return adapter.get_page(params)


@app.get("/articles/{doi:path}")
def article(doi: str, params: Annotated[QueryParameters, Query()]) -> Page[Article]:
    query = ARTICLE_QUERY.format(doi=sparql_string(doi))
    adapter = SPARQLModelAdapter(
        target=META, query=query, model=Article, aclient_config=CLIENT
    )
    return adapter.get_page(params)
