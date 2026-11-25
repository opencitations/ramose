# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from re import Match, findall, sub
from re import compile as compile_pattern
from re import escape as escape_pattern

import yaml

from ramose.escaping import escape_iri, escape_literal, escape_local_name

FiltersConfig = Mapping[str, Mapping[str, "str | dict[str, str]"]]

_VALUE_PATTERN = r"\{\{\s*value\s*\}\}"
_QLEVER_HAS_WORD = ("ql:has-word", "<http://qlever.cs.uni-freiburg.de/builtin-functions/has-word>")
_ALWAYS_EMPTY_FILTER = "FILTER(false)"
_HAS_WORD = "(?:" + "|".join(map(escape_pattern, _QLEVER_HAS_WORD)) + ")"
_QUOTED_VALUE = rf"""(?P<quote>["']){_VALUE_PATTERN}(?P=quote)"""
_EXACT_WORD_FORM = compile_pattern(rf"(?P<literal>\?\w+)\s+{_HAS_WORD}\s+{_QUOTED_VALUE}")
_WORD_VARIABLE_FORM = compile_pattern(rf"(\?\w+)\s+{_HAS_WORD}\s+(\?\w+)")
_WORD_START = r"(^|[^\\p{L}\\p{N}])"
_WORD_END = r"($|[^\\p{L}\\p{N}])"


def render(template: str, value: str) -> str:
    def bind(placeholder: Match[str]) -> str:
        before = template[placeholder.start() - 1 : placeholder.start()]
        after = template[placeholder.end() : placeholder.end() + 1]
        if before in ('"', "'") and after == before:
            return escape_literal(value)
        if before == "<" and after == ">":
            return escape_iri(value)
        return escape_local_name(value)

    return sub(_VALUE_PATTERN, bind, template)


def _select_template(key: str, spec: str | dict[str, str], value: str) -> str:
    if isinstance(spec, str):
        return spec
    if value not in spec:
        msg = f"The value '{value}' is not valid for filter '{key}', valid values are {', '.join(sorted(spec))}"
        raise ValueError(msg)
    return spec[value]


def _word_filter(literal: str, word: str, *, prefix: bool) -> str:
    end = "" if prefix else _WORD_END
    return f'FILTER REGEX({literal}, "{_WORD_START}{word}{end}", "i")'


def _has_word_form(template: str) -> tuple[str, bool] | None:
    if exact := _EXACT_WORD_FORM.search(template):
        return exact["literal"], False
    for literal, word in _WORD_VARIABLE_FORM.findall(template):
        prefix_filter = rf"(?i:STRSTARTS)\s*\(\s*{escape_pattern(word)}\s*,\s*{_QUOTED_VALUE}\s*\)"
        if compile_pattern(prefix_filter).search(template):
            return literal, True
    return None


def _render_fragments(template: str, value: str) -> list[str]:
    if not any(predicate in template for predicate in _QLEVER_HAS_WORD):
        return [render(template, value)]
    words = findall(r"[^\W_]+", value.lower())
    if not words:
        return [_ALWAYS_EMPTY_FILTER]
    form = _has_word_form(template)
    if form is None:
        return [render(template, word) for word in words]
    # Only the longest word, usually the rarest, goes through the has-word index;
    # the others are checked on the few literals it leaves.
    literal, prefix = form
    anchor, *others = sorted(words, key=len, reverse=True)
    return [render(template, anchor), *(_word_filter(literal, word, prefix=prefix) for word in others)]


def _is_always_empty(fragment: str) -> bool:
    return fragment.strip().upper() == _ALWAYS_EMPTY_FILTER.upper()


def apply_filters(config: FiltersConfig, values: list[str]) -> dict[str, str]:
    slots: list[str] = []
    for slot_map in config.values():
        for slot in slot_map:
            if slot not in slots:
                slots.append(slot)
    result = dict.fromkeys(slots, "")
    fragments: list[tuple[str, str]] = []

    raw_pairs = (pair.strip() for value in values for pair in value.split(","))
    for pair in (pair for pair in raw_pairs if pair):
        key, value = pair.split(":", 1)
        if key not in config:
            msg = f"The filter '{key}' is not configured, configured filters are {', '.join(sorted(config))}"
            raise ValueError(msg)
        for slot, spec in config[key].items():
            template = _select_template(key, spec, value)
            fragments.extend((slot, fragment) for fragment in _render_fragments(template, value))

    always_empty_slots = {slot for slot, fragment in fragments if _is_always_empty(fragment)}
    if always_empty_slots:
        for slot in always_empty_slots:
            result[slot] = _ALWAYS_EMPTY_FILTER
        return result

    for slot, fragment in fragments:
        result[slot] = f"{result[slot]}\n{fragment}" if result[slot] else fragment
    return result


def load_yaml_config(path: str) -> FiltersConfig:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
