#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2022, Arcangelo Massari <arcangelo.massari@unibo.it>
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

__author__ = 'Arcangelo Massari'

from typing import Tuple

URI_TYPE_DICT = {
    'http://purl.org/spar/doco/Abstract': 'abstract',
    'http://purl.org/spar/fabio/ArchivalDocument': 'archival document',
    'http://purl.org/spar/fabio/AudioDocument': 'audio document',
    'http://purl.org/spar/fabio/Book': 'book',
    'http://purl.org/spar/fabio/BookChapter': 'book chapter',
    'http://purl.org/spar/fabio/ExpressionCollection': 'book section',
    'http://purl.org/spar/fabio/BookSeries': 'book series',
    'http://purl.org/spar/fabio/BookSet': 'book set',
    'http://purl.org/spar/fabio/ComputerProgram': 'computer program',
    'http://purl.org/spar/doco/Part': 'book part',
    'http://purl.org/spar/fabio/Expression': '',
    'http://purl.org/spar/fabio/DataFile': 'dataset',
    'http://purl.org/spar/fabio/DataManagementPlan': 'data management plan',
    'http://purl.org/spar/fabio/Thesis': 'dissertation',
    'http://purl.org/spar/fabio/Editorial': 'editorial',
    'http://purl.org/spar/fabio/Journal': 'journal',
    'http://purl.org/spar/fabio/JournalArticle': 'journal article',
    'http://purl.org/spar/fabio/JournalEditorial': 'journal editorial',
    'http://purl.org/spar/fabio/JournalIssue': 'journal issue',
    'http://purl.org/spar/fabio/JournalVolume': 'journal volume',
    'http://purl.org/spar/fabio/Newspaper': 'newspaper',
    'http://purl.org/spar/fabio/NewspaperArticle': 'newspaper article',
    'http://purl.org/spar/fabio/NewspaperIssue': 'newspaper issue',
    'http://purl.org/spar/fr/ReviewVersion': 'peer review',
    'http://purl.org/spar/fabio/AcademicProceedings': 'proceedings',
    'http://purl.org/spar/fabio/Preprint': 'preprint',
    'http://purl.org/spar/fabio/Presentation': 'presentation',
    'http://purl.org/spar/fabio/ProceedingsPaper': 'proceedings article',
    'http://purl.org/spar/fabio/ReferenceBook': 'reference book',
    'http://purl.org/spar/fabio/ReferenceEntry': 'reference entry',
    'http://purl.org/spar/fabio/ReportDocument': 'report',
    'http://purl.org/spar/fabio/RetractionNotice': 'retraction notice',
    'http://purl.org/spar/fabio/Series': 'series',
    'http://purl.org/spar/fabio/SpecificationDocument': 'standard',
    'http://purl.org/spar/fabio/WebContent': 'web content'
}


def generate_id_search(ids: str) -> Tuple[str]:
    id_searches = list()
    omid_values = []
    other_values = []

    for identifier in ids.split('__'):
        scheme_literal_value = identifier.split(':', maxsplit=1)
        scheme = scheme_literal_value[0].lower()
        literal_value = scheme_literal_value[1]
        literal_value = literal_value.lower() if scheme == 'doi' else literal_value
        if scheme == 'omid':
            omid_values.append("<https://w3id.org/oc/meta/"+literal_value+">")
        elif scheme in {'doi', 'issn', 'isbn', 'openalex', 'pmid', 'pmcid', 'url', 'wikidata', 'wikipedia'}:
            other_values.append('''
                {{
                    {
                      ?identifier literal:hasLiteralValue "'''+literal_value+'''"
                    }
                    UNION
                    {
                      ?identifier literal:hasLiteralValue "'''+literal_value+'''"^^<http://www.w3.org/2001/XMLSchema#string>
                    }
                    ?identifier datacite:usesIdentifierScheme datacite:'''+scheme+''';
                        ^datacite:hasIdentifier ?res.
                    ?res a fabio:Expression.
                }}
            ''')

    if omid_values:
        id_searches.append("VALUES ?res { " + " ".join(omid_values) + " } ?res a fabio:Expression.")

    if other_values:
        id_searches.append(" UNION ".join(other_values))

    ids_search = " UNION ".join(id_searches)
    return ids_search,

def generate_ra_search(identifier:str) -> Tuple[str]:
    scheme_literal_value = identifier.split(':')
    if len(scheme_literal_value) == 2:
        scheme = scheme_literal_value[0]
        literal_value = scheme_literal_value[1]
    else:
        scheme = 'orcid'
        literal_value = scheme_literal_value[0]
    if scheme == 'omid':
        return '<https://w3id.org/oc/meta/{0}> ^pro:isHeldBy ?knownRole.'.format(literal_value),
    else:
        return '''
            {
                ?knownPersonIdentifier literal:hasLiteralValue "'''+literal_value+'''"
            }
            UNION
            {
                ?knownPersonIdentifier literal:hasLiteralValue "'''+literal_value+'''"^^<http://www.w3.org/2001/XMLSchema#string>
            }
            ?knownPersonIdentifier datacite:usesIdentifierScheme datacite:'''+scheme+''';
                                ^datacite:hasIdentifier ?knownPerson.
            ?knownPerson ^pro:isHeldBy ?knownRole.
        ''',

def create_metadata_output(results):
    header = results[0]
    output_results = [header]
    for result in results[1:]:
        output_result = list()
        for i, data in enumerate(result):
            if i == header.index('type'):
                beautiful_type = __postprocess_type(data[1])
                output_result.append((data[0], beautiful_type))
            elif i == header.index('author') or i == header.index('editor') or i == header.index('publisher'):
                ordered_list = process_ordered_list(data[1])
                output_result.append((data[0], ordered_list))
            else:
                output_result.append(data)
        output_results.append(output_result)
    return output_results, True

def __postprocess_type(type_uri:str) -> str:
    if type_uri:
        type_string = URI_TYPE_DICT[type_uri]
    else:
        type_string = ''
    return type_string

def process_ordered_list(items):
    if not items:
        return items
    items_dict = {}
    role_to_name = {}
    l_author = [item for item in items.split('|') if item is not None and item != ""]
    if len(l_author) == 0:
        return ""
    for item in l_author:
        parts = item.split(':')
        name = ':'.join(parts[:-2])
        current_role = parts[-2]
        next_role = parts[-1] if parts[-1] != '' else None
        items_dict[current_role] = next_role
        role_to_name[current_role] = name

    ordered_items = []
    start_role = next(iter(role for role, next_role in items_dict.items() if not role in items_dict.values()))

    current_role = start_role
    while current_role:
        ordered_items.append(role_to_name[current_role])
        current_role = items_dict[current_role]

    return "; ".join(ordered_items)
