# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from ramose.skgif_addon import (
    _build_agent,
    _build_grant,
    _build_org,
    _build_venue,
    normalize_local_identifier_url,
)

if TYPE_CHECKING:
    from ramose import APIManager


def _execute(manager: APIManager, local_identifier: str) -> dict:
    operation = manager.get_op(f"/skgif-edge/v1/products/{local_identifier}")
    if isinstance(operation, tuple):
        msg = f"Operation not found: {local_identifier}"
        raise TypeError(msg)
    status, result, _, _ = operation.exec(method="get", content_type="application/json")
    if status != 200:
        msg = f"API returned status {status}: {result}"
        raise RuntimeError(msg)
    return json.loads(result)


class TestMissingLangColumns:
    def test_title_without_title_lang_uses_structured_format(self, skgif_edge_api_manager: APIManager) -> None:
        response = _execute(skgif_edge_api_manager, "https://w3id.org/oc/meta/br/0601")
        product = response["@graph"][0]
        assert "titles" in product, "Expected structured 'titles' field, got flat 'title' instead"
        assert product["titles"] == {
            "none": [
                "Response To The Letter Of Hanley Et Al. "
                "([1999] Teratology 59:323-324), Concerning The Article By Roy Et Al. "
                "([1998] Teratology 58:62-68)",
            ],
        }
        assert "title" not in product, "'title' should not appear as a flat scalar field"


class TestNormalizeLocalIdentifierUrl:
    def test_merged_scheme_slash_is_restored(self) -> None:
        assert normalize_local_identifier_url("https:/w3id.org/oc/meta/br/0601") == (
            "https://w3id.org/oc/meta/br/0601",
        )

    def test_http_scheme_is_restored(self) -> None:
        assert normalize_local_identifier_url("http:/example.org/entity/1") == ("http://example.org/entity/1",)

    def test_canonical_url_is_unchanged(self) -> None:
        assert normalize_local_identifier_url("https://w3id.org/oc/meta/br/0601") == (
            "https://w3id.org/oc/meta/br/0601",
        )

    def test_call_with_merged_slash_returns_same_product(self, skgif_edge_api_manager: APIManager) -> None:
        canonical = _execute(skgif_edge_api_manager, "https://w3id.org/oc/meta/br/0601")
        merged = _execute(skgif_edge_api_manager, "https:/w3id.org/oc/meta/br/0601")
        assert merged["@graph"] == canonical["@graph"]


class TestMissingLocalIdentifier:
    def test_agent_without_local_identifier_raises(self) -> None:
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

    def test_organisation_without_local_identifier_raises(self) -> None:
        row = {
            "relevant_organisation_name": "CERN",
            "relevant_organisation_short_name": "",
            "relevant_organisation_country": "",
            "relevant_organisation_website": "",
            "relevant_organisation_local_identifier": "",
        }
        with pytest.raises(ValueError, match="Missing required local_identifier for organisation 'CERN'"):
            _build_org(row, "relevant_organisation")

    def test_venue_without_local_identifier_raises(self) -> None:
        row = {"manifestation_biblio_in_acronym": ""}
        with pytest.raises(ValueError, match="Missing required local_identifier for venue 'Nature'"):
            _build_venue([row], "Nature", "")

    def test_grant_without_local_identifier_raises(self) -> None:
        row = {"funding_local_identifier": ""}
        with pytest.raises(ValueError, match="Missing required local_identifier for grant"):
            _build_grant(row)
