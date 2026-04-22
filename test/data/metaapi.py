# SPDX-FileCopyrightText: 2022-2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from oc_constants import FABIO_TYPE_LABELS


def generate_id_search(ids: str) -> tuple[str]:
    id_searches = []
    omid_values = []
    other_values = []

    for identifier in ids.split("__"):
        scheme_literal_value = identifier.split(":", maxsplit=1)
        scheme = scheme_literal_value[0].lower()
        literal_value = scheme_literal_value[1]
        literal_value = literal_value.lower() if scheme == "doi" else literal_value
        if scheme == "omid":
            omid_values.append("<https://w3id.org/oc/meta/" + literal_value + ">")
        elif scheme in {"doi", "issn", "isbn", "openalex", "pmid", "pmcid", "url", "wikidata", "wikipedia"}:
            other_values.append(
                '''
                {{
                    {
                      ?identifier literal:hasLiteralValue "'''
                + literal_value
                + '''"
                    }
                    UNION
                    {
                      ?identifier literal:hasLiteralValue "'''
                + literal_value
                + """"^^<http://www.w3.org/2001/XMLSchema#string>
                    }
                    ?identifier datacite:usesIdentifierScheme datacite:"""
                + scheme
                + """;
                        ^datacite:hasIdentifier ?res.
                    ?res a fabio:Expression.
                }}
            """
            )

    if omid_values:
        id_searches.append("VALUES ?res { " + " ".join(omid_values) + " } ?res a fabio:Expression.")

    if other_values:
        id_searches.append(" UNION ".join(other_values))

    ids_search = " UNION ".join(id_searches)
    return (ids_search,)


def generate_ra_search(identifier: str) -> tuple[str]:
    scheme_literal_value = identifier.split(":")
    if len(scheme_literal_value) == 2:
        scheme = scheme_literal_value[0]
        literal_value = scheme_literal_value[1]
    else:
        scheme = "orcid"
        literal_value = scheme_literal_value[0]
    if scheme == "omid":
        return (f"<https://w3id.org/oc/meta/{literal_value}> ^pro:isHeldBy ?knownRole.",)
    return (
        '''
            {
                ?knownPersonIdentifier literal:hasLiteralValue "'''
        + literal_value
        + '''"
            }
            UNION
            {
                ?knownPersonIdentifier literal:hasLiteralValue "'''
        + literal_value
        + """"^^<http://www.w3.org/2001/XMLSchema#string>
            }
            ?knownPersonIdentifier datacite:usesIdentifierScheme datacite:"""
        + scheme
        + """;
                                ^datacite:hasIdentifier ?knownPerson.
            ?knownPerson ^pro:isHeldBy ?knownRole.
        """,
    )


def create_metadata_output(results):
    header = results[0]
    output_results = [header]
    for result in results[1:]:
        output_result = []
        for i, data in enumerate(result):
            if i == header.index("type"):
                beautiful_type = __postprocess_type(data[1])
                output_result.append((data[0], beautiful_type))
            elif i == header.index("author") or i == header.index("editor") or i == header.index("publisher"):
                ordered_list = process_ordered_list(data[1])
                output_result.append((data[0], ordered_list))
            else:
                output_result.append(data)
        output_results.append(output_result)
    return output_results, True


def __postprocess_type(type_uri: str) -> str:
    return FABIO_TYPE_LABELS[type_uri] if type_uri else ""


def process_ordered_list(items):
    if not items:
        return items
    items_dict = {}
    role_to_name = {}
    l_author = [item for item in items.split("|") if item is not None and item != ""]
    if len(l_author) == 0:
        return ""
    for item in l_author:
        parts = item.split(":")
        name = ":".join(parts[:-2])
        current_role = parts[-2]
        next_role = parts[-1] if parts[-1] != "" else None
        items_dict[current_role] = next_role
        role_to_name[current_role] = name

    ordered_items = []
    start_role = next(iter(role for role, next_role in items_dict.items() if role not in items_dict.values()))

    current_role = start_role
    while current_role:
        ordered_items.append(role_to_name[current_role])
        current_role = items_dict[current_role]

    return "; ".join(ordered_items)
