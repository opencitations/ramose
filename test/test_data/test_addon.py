#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2018, Silvio Peroni <essepuntato@gmail.com>
#
# Permission to use, copy, modify, and/or distribute this software for any purpose
# with or without fee is hereby granted, provided that the above copyright notice
# and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
# REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT,
# OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE,
# DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS
# ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS
# SOFTWARE.

__author__ = 'essepuntato'
from urllib.parse import quote, unquote
from requests import get
# from rdflib import Graph, URIRef
# from rdflib.namespace import RDF, OWL, Namespace
from json import loads


def upper(s):
    return s.upper(),


def split_dois(s):
    return "\"%s\"" % "\" \"".join(s.split("__")),


def distinct(res):
    header = res[0]
    doi_field = header.index("doi")
    result = [header]

    dois = set()
    for row in res[1:]:
        cur_doi = row[doi_field]
        if cur_doi not in dois:
            dois.add(cur_doi)
            result.append(row)

    return result, True
