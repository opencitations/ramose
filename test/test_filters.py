# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

from re import escape
from typing import TYPE_CHECKING

import pytest

from ramose.filters import apply_filters, load_filters_config, render

if TYPE_CHECKING:
    from pathlib import Path

# Two providers, SAME filter vocabulary, DIFFERENT data topology.
# Provider A keeps metadata and citations in two stores: the cf.cites filter
# injects a federated step into a [[citation_step]] slot.
CONFIG_A = {
    "identifiers.id": {
        "constraints": '?product datacite:hasIdentifier [ literal:hasLiteralValue "{{value}}" ] .',
    },
    "contributions.by.family_name": {
        "constraints": (
            '?product pro:isDocumentContextFor [ pro:isHeldBy ?_agent ] .\n?_agent foaf:familyName "{{value}}" .'
        ),
    },
    "cf.cites": {
        "citation_step": (
            "@@with source=index\n"
            "SELECT ?product WHERE { ?_ci cito:hasCitingEntity ?product ; cito:hasCitedEntity <{{value}}> . }\n"
            "@@join ?product ?product type=inner"
        ),
    },
}

# Provider B keeps everything in one store: the SAME cf.cites filter is just an
# inline triple in the SAME [[constraints]] slot. The engine never knows the difference.
CONFIG_B = {
    "identifiers.id": {"constraints": '?product ex:doi "{{value}}" .'},
    "cf.cites": {"constraints": "?product cito:cites <{{value}}> ."},
}

# A slot may dispatch on the value itself (which also validates it).
CONFIG_VALUE_DISPATCH = {
    "product_type": {
        "filter": {
            "literature": "FILTER NOT EXISTS { ?product a fabio:DataFile }",
            "research software": "?product a fabio:ComputerProgram .",
            "other": "FILTER(false)",
        },
    },
}

CONFIG_ALWAYS_EMPTY = {
    "cf.cites": {
        "citation_step": (
            "@@with source=index\n"
            "SELECT ?product WHERE { ?_ci cito:hasCitingEntity ?product ; cito:hasCitedEntity <{{value}}> . }\n"
            "@@join ?product ?product type=inner"
        ),
    },
    "funding.local_identifier": {"filter": "FILTER(false)"},
}


def test_render_replaces_value_raw() -> None:
    assert render("name {{value}} .", 'Zenodo "community"') == 'name Zenodo "community" .'


def test_apply_filters_inline_constraint() -> None:
    assert apply_filters(CONFIG_A, ["identifiers.id:10.1162/qss_a_00292"]) == {
        "constraints": '?product datacite:hasIdentifier [ literal:hasLiteralValue "10.1162/qss_a_00292" ] .',
        "citation_step": "",
    }


def test_apply_filters_federated_topology() -> None:
    assert apply_filters(CONFIG_A, ["cf.cites:https://w3id.org/oc/meta/br/06035"]) == {
        "constraints": "",
        "citation_step": (
            "@@with source=index\n"
            "SELECT ?product WHERE { ?_ci cito:hasCitingEntity ?product ; "
            "cito:hasCitedEntity <https://w3id.org/oc/meta/br/06035> . }\n"
            "@@join ?product ?product type=inner"
        ),
    }


def test_apply_filters_same_filter_single_store_topology() -> None:
    # Same filter key and value as the federated case, but provider B's config makes it
    # an inline triple in one store. The engine output follows the config, nothing else.
    assert apply_filters(CONFIG_B, ["cf.cites:https://w3id.org/oc/meta/br/06035"]) == {
        "constraints": "?product cito:cites <https://w3id.org/oc/meta/br/06035> .",
    }


def test_apply_filters_concatenates_same_slot_as_and() -> None:
    assert apply_filters(CONFIG_B, ["identifiers.id:10.1/x,cf.cites:https://example.org/1"]) == {
        "constraints": '?product ex:doi "10.1/x" .\n?product cito:cites <https://example.org/1> .',
    }


def test_apply_filters_splits_repeated_param_values() -> None:
    assert apply_filters(CONFIG_A, ["identifiers.id:10.1/x", "contributions.by.family_name:Peroni"]) == {
        "constraints": (
            '?product datacite:hasIdentifier [ literal:hasLiteralValue "10.1/x" ] .\n'
            "?product pro:isDocumentContextFor [ pro:isHeldBy ?_agent ] .\n"
            '?_agent foaf:familyName "Peroni" .'
        ),
        "citation_step": "",
    }


def test_apply_filters_rejects_unconfigured_filter() -> None:
    expected = "The filter 'funding.grant_number' is not configured, configured filters are cf.cites, identifiers.id"
    with pytest.raises(ValueError, match=f"^{escape(expected)}$"):
        apply_filters(CONFIG_B, ["funding.grant_number:123"])


def test_apply_filters_always_empty_skips_other_slots() -> None:
    assert apply_filters(CONFIG_ALWAYS_EMPTY, ["cf.cites:https://example.org/1,funding.local_identifier:123"]) == {
        "citation_step": "",
        "filter": "FILTER(false)",
    }


def test_apply_filters_always_empty_skips_other_slots_when_first() -> None:
    assert apply_filters(CONFIG_ALWAYS_EMPTY, ["funding.local_identifier:123,cf.cites:https://example.org/1"]) == {
        "citation_step": "",
        "filter": "FILTER(false)",
    }


def test_apply_filters_always_empty_still_rejects_unconfigured_filter() -> None:
    expected = "The filter 'unknown' is not configured, configured filters are cf.cites, funding.local_identifier"
    with pytest.raises(ValueError, match=f"^{escape(expected)}$"):
        apply_filters(CONFIG_ALWAYS_EMPTY, ["funding.local_identifier:123,unknown:x"])


def test_apply_filters_value_dispatch_selects_template() -> None:
    assert apply_filters(CONFIG_VALUE_DISPATCH, ["product_type:research software"]) == {
        "filter": "?product a fabio:ComputerProgram .",
    }


def test_apply_filters_value_dispatch_rejects_invalid_value() -> None:
    expected = (
        "The value 'nonexistent' is not valid for filter 'product_type', "
        "valid values are literature, other, research software"
    )
    with pytest.raises(ValueError, match=f"^{escape(expected)}$"):
        apply_filters(CONFIG_VALUE_DISPATCH, ["product_type:nonexistent"])


def test_load_filters_config_reads_yaml(tmp_path: Path) -> None:
    config_file = tmp_path / "filters.yaml"
    config_file.write_text(
        "identifiers.id:\n  constraints: '?product ex:doi \"{{value}}\" .'\n",
        encoding="utf-8",
    )
    assert load_filters_config(str(config_file)) == {"identifiers.id": {"constraints": '?product ex:doi "{{value}}" .'}}
