# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from ramose.paging import build_link_header, build_pagination_info


class TestBuildPaginationInfo:
    def test_first_page_of_multiple(self) -> None:
        info = build_pagination_info("/api/v1/test", {"filter": ["year:2024"]}, 1, 10, 25)
        assert info.page == 1
        assert info.page_size == 10
        assert info.total_items == 25
        assert info.self_url == "/api/v1/test?filter=year:2024&page=1&page_size=10&total_items=25"
        assert info.next_url == "/api/v1/test?filter=year:2024&page=2&page_size=10&total_items=25"
        assert info.prev_url == ""
        assert info.first_url == "/api/v1/test?filter=year:2024&page=1&page_size=10&total_items=25"
        assert info.last_url == "/api/v1/test?filter=year:2024&page=3&page_size=10&total_items=25"

    def test_middle_page(self) -> None:
        info = build_pagination_info("/api/v1/test", {}, 2, 10, 30)
        assert info.self_url == "/api/v1/test?page=2&page_size=10&total_items=30"
        assert info.next_url == "/api/v1/test?page=3&page_size=10&total_items=30"
        assert info.prev_url == "/api/v1/test?page=1&page_size=10&total_items=30"
        assert info.first_url == "/api/v1/test?page=1&page_size=10&total_items=30"
        assert info.last_url == "/api/v1/test?page=3&page_size=10&total_items=30"

    def test_last_page(self) -> None:
        info = build_pagination_info("/api/v1/test", {}, 3, 10, 30)
        assert info.self_url == "/api/v1/test?page=3&page_size=10&total_items=30"
        assert info.next_url == ""
        assert info.prev_url == "/api/v1/test?page=2&page_size=10&total_items=30"
        assert info.first_url == "/api/v1/test?page=1&page_size=10&total_items=30"
        assert info.last_url == "/api/v1/test?page=3&page_size=10&total_items=30"

    def test_single_page(self) -> None:
        info = build_pagination_info("/api/v1/test", {}, 1, 50, 10)
        assert info.self_url == "/api/v1/test?page=1&page_size=50&total_items=10"
        assert info.next_url == ""
        assert info.prev_url == ""
        assert info.total_items == 10
        assert info.first_url == "/api/v1/test?page=1&page_size=50&total_items=10"
        assert info.last_url == "/api/v1/test?page=1&page_size=50&total_items=10"

    def test_exact_page_boundary(self) -> None:
        info = build_pagination_info("/api/v1/test", {}, 2, 10, 20)
        assert info.self_url == "/api/v1/test?page=2&page_size=10&total_items=20"
        assert info.next_url == ""
        assert info.prev_url == "/api/v1/test?page=1&page_size=10&total_items=20"
        assert info.first_url == "/api/v1/test?page=1&page_size=10&total_items=20"
        assert info.last_url == "/api/v1/test?page=2&page_size=10&total_items=20"

    def test_page_and_page_size_stripped_from_urls(self) -> None:
        info = build_pagination_info("/api/v1/test", {"page": ["2"], "page_size": ["10"], "filter": ["x"]}, 2, 10, 30)
        assert "filter=x" in info.self_url
        assert "filter=x" in info.next_url
        assert "filter=x" in info.prev_url
        assert "filter=x" in info.first_url
        assert "filter=x" in info.last_url


class TestBuildLinkHeader:
    def test_with_next_and_prev(self) -> None:
        info = build_pagination_info("/api/v1/test", {}, 2, 10, 30)
        header = build_link_header(info)
        assert header == (
            '</api/v1/test?page=3&page_size=10&total_items=30>; rel="next", '
            '</api/v1/test?page=1&page_size=10&total_items=30>; rel="prev", '
            '</api/v1/test?page=1&page_size=10&total_items=30>; rel="first", '
            '</api/v1/test?page=3&page_size=10&total_items=30>; rel="last"'
        )

    def test_first_page_next_only(self) -> None:
        info = build_pagination_info("/api/v1/test", {}, 1, 10, 30)
        header = build_link_header(info)
        assert header == (
            '</api/v1/test?page=2&page_size=10&total_items=30>; rel="next", '
            '</api/v1/test?page=1&page_size=10&total_items=30>; rel="first", '
            '</api/v1/test?page=3&page_size=10&total_items=30>; rel="last"'
        )

    def test_last_page_prev_only(self) -> None:
        info = build_pagination_info("/api/v1/test", {}, 3, 10, 30)
        header = build_link_header(info)
        assert header == (
            '</api/v1/test?page=2&page_size=10&total_items=30>; rel="prev", '
            '</api/v1/test?page=1&page_size=10&total_items=30>; rel="first", '
            '</api/v1/test?page=3&page_size=10&total_items=30>; rel="last"'
        )

    def test_single_page(self) -> None:
        info = build_pagination_info("/api/v1/test", {}, 1, 50, 10)
        header = build_link_header(info)
        assert header == (
            '</api/v1/test?page=1&page_size=50&total_items=10>; rel="first", '
            '</api/v1/test?page=1&page_size=50&total_items=10>; rel="last"'
        )
