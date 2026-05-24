# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import json

from ramose import APIManager


def _execute(manager: APIManager, local_identifier: str) -> dict:
    operation = manager.get_op(f"/skgif-edge/v1/products/{local_identifier}")
    if isinstance(operation, tuple):
        raise TypeError(f"Operation not found: {local_identifier}")
    status, result, _, _ = operation.exec(method="get", content_type="application/json")
    if status != 200:
        raise RuntimeError(f"API returned status {status}: {result}")
    return json.loads(result)


class TestMissingLangColumns:
    def test_title_without_title_lang_uses_structured_format(self, skgif_edge_api_manager):
        response = _execute(skgif_edge_api_manager, "https://w3id.org/oc/meta/br/0601")
        product = response["@graph"][0]
        assert "titles" in product, "Expected structured 'titles' field, got flat 'title' instead"
        assert product["titles"] == {"none": [
            "Response To The Letter Of Hanley Et Al. "
            "([1999] Teratology 59:323-324), Concerning The Article By Roy Et Al. "
            "([1998] Teratology 58:62-68)"
        ]}
        assert "title" not in product, "'title' should not appear as a flat scalar field"
