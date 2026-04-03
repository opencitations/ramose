# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from pathlib import Path

import pytest

from ramose import APIManager, HTMLDocumentationHandler

DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture
def doc_handler():
    mgr = APIManager(
        [str(DATA_DIR / "meta_v1.hf")],
        endpoint_override="http://localhost:9999/sparql",
    )
    return HTMLDocumentationHandler(mgr)


def _read_expected(filename: str) -> str:
    return (DATA_DIR / filename).read_text()


class TestGetDocumentation:
    def test_returns_200_and_expected_html(self, doc_handler):
        status, html = doc_handler.get_documentation()
        assert status == 200
        assert html == _read_expected("meta_v1_doc.html")

    def test_with_base_url(self, doc_handler):
        status, html = doc_handler.get_documentation(base_url="v1")
        assert status == 200
        assert html == _read_expected("meta_v1_doc.html")

    def test_with_css_path(self, doc_handler):
        _, html = doc_handler.get_documentation(css_path="/static/custom.css")
        assert html == _read_expected("meta_v1_doc_css.html")


class TestGetIndex:
    def test_returns_expected_html(self, doc_handler):
        html = doc_handler.get_index()
        assert html == _read_expected("meta_v1_index.html")


class TestStoreDocumentation:
    def test_writes_file(self, doc_handler, tmp_path):
        file_path = tmp_path / "docs.html"
        doc_handler.store_documentation(str(file_path))
        assert file_path.read_text() == _read_expected("meta_v1_doc.html")


class TestCleanLog:
    def test_valid_log_line(self, doc_handler):
        log_line = '192.168.1.1 - - [01/Jan/2026:12:00:00] "GET /v1/metadata/doi:10.1234 HTTP/1.1" 200 1234'
        result = doc_handler.clean_log(log_line, "/v1")
        assert result == (
            "<span class='group_log'>"
            "<span class='status_log code_2001234'>2001234</span>"
            "<span class='date_log'>01/Jan/2026:12:00:00</span>"
            "<span class='method_log'>GET</span>"
            "</span>"
            "<span class='group_log'>"
            "<span class='call_log'>"
            "<a href='/v1/metadata/doi:10.1234' target='_blank'>/v1/metadata/doi:10.1234</a>"
            "</span>"
            "</span>"
        )

    def test_log_line_without_separator(self, doc_handler):
        assert doc_handler.clean_log("some random log line", "/v1") == ""

    def test_root_url_returns_empty(self, doc_handler):
        log_line = '192.168.1.1 - - [01/Jan/2026:12:00:00] "GET /v1/ HTTP/1.1" 200 512'
        assert doc_handler.clean_log(log_line, "/v1") == ""


class TestGetIndexNoLogFile:
    def test_missing_ramose_log(self, doc_handler, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        html = doc_handler.get_index()
        assert "RAMOSE" in html
