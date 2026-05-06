# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import json
import tempfile
from pathlib import Path

import pytest

from ramose import APIManager
from ramose.paging import build_link_header

DATA_DIR = Path(__file__).resolve().parent / "data"
AUTHOR_ORCID = "/v1/author/orcid:0000-0002-8420-0696"
TOTAL_AUTHOR_WORKS = 7


def _page_url(page, page_size=3):
    return f"{AUTHOR_ORCID}?page={page}&page_size={page_size}"


@pytest.fixture
def cached_api_manager(qlever_endpoint):
    with tempfile.TemporaryDirectory() as tmpdir:
        yield APIManager(
            [str(DATA_DIR / "meta_v1.hf")],
            endpoint_override=qlever_endpoint,
            cache_dir=tmpdir,
        )


class TestPagination:
    def test_first_page(self, api_manager):
        op = api_manager.get_op(f"{AUTHOR_ORCID}?page=1&page_size=3")
        status, body, _ = op.exec(content_type="application/json")
        result = json.loads(body)
        assert status == 200
        assert len(result) == 3
        assert op.pagination_info is not None
        assert op.pagination_info.total_items == TOTAL_AUTHOR_WORKS
        assert op.pagination_info.page == 1
        assert op.pagination_info.page_size == 3
        assert op.pagination_info.next_url == _page_url(2)
        assert op.pagination_info.prev_url == ""
        assert op.pagination_info.first_url == _page_url(1)
        assert op.pagination_info.last_url == _page_url(3)

    def test_middle_page(self, api_manager):
        op = api_manager.get_op(f"{AUTHOR_ORCID}?page=2&page_size=3")
        status, body, _ = op.exec(content_type="application/json")
        result = json.loads(body)
        assert status == 200
        assert len(result) == 3
        assert op.pagination_info is not None
        assert op.pagination_info.next_url == _page_url(3)
        assert op.pagination_info.prev_url == _page_url(1)
        assert op.pagination_info.first_url == _page_url(1)
        assert op.pagination_info.last_url == _page_url(3)

    def test_last_page_partial(self, api_manager):
        op = api_manager.get_op(f"{AUTHOR_ORCID}?page=3&page_size=3")
        status, body, _ = op.exec(content_type="application/json")
        result = json.loads(body)
        assert status == 200
        assert len(result) == 1
        assert op.pagination_info is not None
        assert op.pagination_info.next_url == ""
        assert op.pagination_info.prev_url == _page_url(2)
        assert op.pagination_info.first_url == _page_url(1)
        assert op.pagination_info.last_url == _page_url(3)

    def test_no_pagination_returns_all(self, api_manager):
        op = api_manager.get_op(AUTHOR_ORCID)
        status, body, _ = op.exec(content_type="application/json")
        result = json.loads(body)
        assert status == 200
        assert len(result) == TOTAL_AUTHOR_WORKS
        assert op.pagination_info is None

    def test_page_beyond_total_returns_400(self, api_manager):
        op = api_manager.get_op(f"{AUTHOR_ORCID}?page=10&page_size=3")
        status, _, ctype = op.exec(content_type="application/json")
        assert status == 400
        assert ctype == "text/plain"

    def test_all_pages_cover_full_result(self, api_manager):
        all_ids = set()
        for page_num in range(1, 4):
            op = api_manager.get_op(f"{AUTHOR_ORCID}?page={page_num}&page_size=3")
            status, body, _ = op.exec(content_type="application/json")
            assert status == 200
            for item in json.loads(body):
                all_ids.add(item["id"])
        assert len(all_ids) == TOTAL_AUTHOR_WORKS

    def test_csv_pagination(self, api_manager):
        op = api_manager.get_op(f"{AUTHOR_ORCID}?page=1&page_size=3")
        status, body, ctype = op.exec(content_type="text/csv")
        assert status == 200
        assert ctype == "text/csv"
        lines = [line for line in body.strip().split("\r\n") if line]
        assert len(lines) == 4

    def test_invalid_page_size_returns_400(self, api_manager):
        op = api_manager.get_op(f"{AUTHOR_ORCID}?page_size=0")
        status, _, ctype = op.exec(content_type="application/json")
        assert status == 400
        assert ctype == "text/plain"

    def test_negative_page_returns_400(self, api_manager):
        op = api_manager.get_op(f"{AUTHOR_ORCID}?page=-1&page_size=3")
        status, _, ctype = op.exec(content_type="application/json")
        assert status == 400
        assert ctype == "text/plain"

    def test_non_integer_page_size_returns_400(self, api_manager):
        op = api_manager.get_op(f"{AUTHOR_ORCID}?page_size=abc")
        status, _, ctype = op.exec(content_type="application/json")
        assert status == 400
        assert ctype == "text/plain"

    def test_link_header_middle_page(self, api_manager):
        op = api_manager.get_op(f"{AUTHOR_ORCID}?page=2&page_size=3")
        op.exec(content_type="application/json")
        header = build_link_header(op.pagination_info)
        assert header == (
            f'<{_page_url(3)}>; rel="next", '
            f'<{_page_url(1)}>; rel="prev", '
            f'<{_page_url(1)}>; rel="first", '
            f'<{_page_url(3)}>; rel="last"'
        )


def _cache_entry_count(api_manager):
    return api_manager._cache._conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]


class TestCaching:
    def test_result_is_cached(self, cached_api_manager):
        op = cached_api_manager.get_op(AUTHOR_ORCID)
        status, _, _ = op.exec(content_type="application/json")
        assert status == 200
        assert _cache_entry_count(cached_api_manager) == 1

    def test_cache_hit_returns_same_result(self, cached_api_manager):
        op1 = cached_api_manager.get_op(AUTHOR_ORCID)
        _, body1, _ = op1.exec(content_type="application/json")

        op2 = cached_api_manager.get_op(AUTHOR_ORCID)
        _, body2, _ = op2.exec(content_type="application/json")

        assert json.loads(body1) == json.loads(body2)
        assert _cache_entry_count(cached_api_manager) == 1

    def test_pagination_shares_cache_entry(self, cached_api_manager):
        op1 = cached_api_manager.get_op(f"{AUTHOR_ORCID}?page=1&page_size=3")
        op1.exec(content_type="application/json")

        op2 = cached_api_manager.get_op(f"{AUTHOR_ORCID}?page=2&page_size=3")
        op2.exec(content_type="application/json")

        assert _cache_entry_count(cached_api_manager) == 1

    def test_different_filters_create_different_entries(self, cached_api_manager):
        op1 = cached_api_manager.get_op(f"{AUTHOR_ORCID}?filter=pub_date:>2023")
        op1.exec(content_type="application/json")

        op2 = cached_api_manager.get_op(f"{AUTHOR_ORCID}?filter=pub_date:<2022")
        op2.exec(content_type="application/json")

        assert _cache_entry_count(cached_api_manager) == 2

    def test_pages_from_cache_dont_overlap(self, cached_api_manager):
        op1 = cached_api_manager.get_op(f"{AUTHOR_ORCID}?page=1&page_size=3")
        _, body1, _ = op1.exec(content_type="application/json")

        op2 = cached_api_manager.get_op(f"{AUTHOR_ORCID}?page=2&page_size=3")
        _, body2, _ = op2.exec(content_type="application/json")

        ids1 = {item["id"] for item in json.loads(body1)}
        ids2 = {item["id"] for item in json.loads(body2)}
        assert len(ids1) == 3
        assert len(ids2) == 3
        assert len(ids1 & ids2) == 0
