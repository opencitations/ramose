# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import os
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ramose import APIManager
from test.start_qlever import DATA_DIR, start_qlever_server, stop_qlever_server

if TYPE_CHECKING:
    from collections.abc import Generator

QLEVER_CONTAINER = "ramose-test-qlever"
QLEVER_PORT = 0
QLEVER_SECURED_CONTAINER = "ramose-test-qlever-secured"
QLEVER_SECURED_PORT = 0
QLEVER_ACCESS_TOKEN = "test-access-token"  # noqa: S105
DOCKER_USER = f"{os.getuid()}:{os.getgid()}"

TEST_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TEST_DIR / "fixtures"


@pytest.fixture(scope="session")
def qlever_endpoint() -> Generator[str, None, None]:
    url = start_qlever_server(QLEVER_CONTAINER, QLEVER_PORT, "-n", read_only=True, user=DOCKER_USER)
    yield url
    stop_qlever_server(QLEVER_CONTAINER)


@pytest.fixture(scope="session")
def qlever_secured_endpoint() -> Generator[tuple[str, str], None, None]:
    url = start_qlever_server(
        QLEVER_SECURED_CONTAINER,
        QLEVER_SECURED_PORT,
        f"-a {QLEVER_ACCESS_TOKEN}",
        read_only=True,
        user=DOCKER_USER,
    )
    yield url, QLEVER_ACCESS_TOKEN
    stop_qlever_server(QLEVER_SECURED_CONTAINER)


@pytest.fixture(scope="session")
def api_manager(qlever_endpoint: str) -> APIManager:
    return APIManager(
        [str(DATA_DIR / "meta_v1.hf")],
        endpoint_override=qlever_endpoint,
    )


@pytest.fixture(scope="session")
def skgif_api_manager(qlever_endpoint: str) -> APIManager:
    manager = APIManager(
        [str(DATA_DIR / "skgif_products.hf")],
        endpoint_override=qlever_endpoint,
    )
    for config in manager.all_conf.values():
        config["sources_map"] = dict.fromkeys(config["sources_map"], qlever_endpoint)
    return manager


@pytest.fixture(scope="session")
def skgif_edge_api_manager(qlever_endpoint: str) -> APIManager:
    return APIManager(
        [str(FIXTURES_DIR / "skgif_edge_cases.hf")],
        endpoint_override=qlever_endpoint,
    )


def execute_operation(api_manager: APIManager, operation_url: str) -> str:
    op = api_manager.get_op(operation_url)
    if isinstance(op, tuple):
        msg = f"Operation not found: {operation_url}"
        raise TypeError(msg)
    status, result, _, _ = op.exec(method="get", content_type="application/json")
    if status != HTTPStatus.OK:
        msg = f"API returned status {status}: {result}"
        raise RuntimeError(msg)
    return result
