# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC


def aggregate_references(results: list[list[tuple[object, str]]]) -> tuple[list[list[tuple[object, str]]], bool]:
    header = results[0]
    references_index = header.index("references")  # type: ignore[arg-type]
    count_index = header.index("reference_count")  # type: ignore[arg-type]
    references = sorted({row[references_index][1] for row in results[1:] if row[references_index][1]})
    serialized = "|".join(references)
    row = list(results[1])
    row[references_index] = (serialized, serialized)
    row[count_index] = (len(references), str(len(references)))
    return [header, row], True


def fill_reference_counts(results: list[list[tuple[object, str]]]) -> tuple[list[list[tuple[object, str]]], bool]:
    count_index = results[0].index("reference_count")  # type: ignore[arg-type]
    for row in results[1:]:
        if row[count_index][1] == "":
            row[count_index] = (0, "0")
    return results, True
