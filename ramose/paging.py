# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

from math import ceil
from typing import NamedTuple
from urllib.parse import urlencode

_PAGINATION_KEYS = frozenset({"page", "page_size"})


class PaginationInfo(NamedTuple):
    page: int
    page_size: int
    total_items: int
    self_url: str
    next_url: str
    prev_url: str
    first_url: str
    last_url: str


def build_pagination_info(
    base_path: str,
    query_params: dict[str, list[str]],
    page: int,
    page_size: int,
    total_items: int,
) -> PaginationInfo:
    total_pages = ceil(total_items / page_size) if page_size > 0 else 0
    self_url = _page_url(base_path, query_params, page, page_size, total_items)
    next_url = _page_url(base_path, query_params, page + 1, page_size, total_items) if page < total_pages else ""
    prev_url = _page_url(base_path, query_params, page - 1, page_size, total_items) if page > 1 else ""
    first_url = _page_url(base_path, query_params, 1, page_size, total_items)
    last_url = _page_url(base_path, query_params, max(total_pages, 1), page_size, total_items)
    return PaginationInfo(page, page_size, total_items, self_url, next_url, prev_url, first_url, last_url)


def build_link_header(pagination_info: PaginationInfo) -> str:
    links = []
    if pagination_info.next_url:
        links.append(f'<{pagination_info.next_url}>; rel="next"')
    if pagination_info.prev_url:
        links.append(f'<{pagination_info.prev_url}>; rel="prev"')
    links.append(f'<{pagination_info.first_url}>; rel="first"')
    links.append(f'<{pagination_info.last_url}>; rel="last"')
    return ", ".join(links)


def _page_url(base_path: str, query_params: dict[str, list[str]], page: int, page_size: int, total_items: int) -> str:
    params = {k: v for k, v in query_params.items() if k not in _PAGINATION_KEYS}
    params["page"] = [str(page)]
    params["page_size"] = [str(page_size)]
    params["total_items"] = [str(total_items)]
    return f"{base_path}?{urlencode(params, doseq=True, safe=':,')}"
