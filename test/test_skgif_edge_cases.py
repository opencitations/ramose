# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import json

import pytest

from ramose import APIManager
from ramose.skgif_addon import _build_agent, _build_grant, _build_org, _build_venue


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
        assert product["titles"] == {
            "none": [
                "Response To The Letter Of Hanley Et Al. "
                "([1999] Teratology 59:323-324), Concerning The Article By Roy Et Al. "
                "([1998] Teratology 58:62-68)"
            ]
        }
        assert "title" not in product, "'title' should not appear as a flat scalar field"


class TestMissingLocalIdentifier:
    def test_agent_without_local_identifier_raises(self):
        row = {
            "contribution_by_family_name": "Doe",
            "contribution_by_given_name": "Jane",
            "contribution_by_name": "",
            "contribution_by_identifier_scheme": "",
            "contribution_by_identifier_value": "",
            "contribution_by_local_identifier": "",
            "contribution_role": "author",
        }
        with pytest.raises(ValueError, match="Missing required local_identifier for person 'Doe, Jane'"):
            _build_agent(row)

    def test_organisation_without_local_identifier_raises(self):
        row = {
            "relevant_organisation_name": "CERN",
            "relevant_organisation_short_name": "",
            "relevant_organisation_country": "",
            "relevant_organisation_website": "",
            "relevant_organisation_local_identifier": "",
        }
        with pytest.raises(ValueError, match="Missing required local_identifier for organisation 'CERN'"):
            _build_org(row, "relevant_organisation")

    def test_venue_without_local_identifier_raises(self):
        row = {"manifestation_biblio_in_acronym": ""}
        with pytest.raises(ValueError, match="Missing required local_identifier for venue 'Nature'"):
            _build_venue([row], "Nature", "")

    def test_grant_without_local_identifier_raises(self):
        row = {"funding_local_identifier": ""}
        with pytest.raises(ValueError, match="Missing required local_identifier for grant"):
            _build_grant(row)
