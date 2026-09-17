# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import os
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ramose import APIManager, Operation
from test.start_qlever import (
    DATA_DIR,
    _docker,
    get_available_port,
    start_qlever_server,
    stop_qlever_server,
    wait_for_qlever,
)

if TYPE_CHECKING:
    from collections.abc import Generator

QLEVER_CONTAINER = "ramose-test-qlever"
QLEVER_PORT = 0
QLEVER_SECURED_CONTAINER = "ramose-test-qlever-secured"
QLEVER_SECURED_PORT = 0
QLEVER_ACCESS_TOKEN = "test-access-token"  # noqa: S105
FUSEKI_DIGEST_CONTAINER = "ramose-test-fuseki-digest"
FUSEKI_IMAGE = "ramose-test-fuseki"
FUSEKI_USER = "demo"
FUSEKI_PASSWORD = "demo"  # noqa: S105
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
def fuseki_digest_endpoint(tmp_path_factory: pytest.TempPathFactory) -> Generator[tuple[str, str, str], None, None]:
    passwd_dir = tmp_path_factory.mktemp("fuseki")
    passwd_dir.chmod(0o755)
    (passwd_dir / "passwd").write_text(f"{FUSEKI_USER}: {FUSEKI_PASSWORD}\n")
    port = get_available_port()
    _docker("build", "-t", FUSEKI_IMAGE, str(TEST_DIR.parent / "docs" / "comparison" / "fuseki"))
    _docker("rm", "-f", FUSEKI_DIGEST_CONTAINER, check=False)
    _docker(
        "run",
        "-d",
        "--name",
        FUSEKI_DIGEST_CONTAINER,
        "-v",
        f"{passwd_dir}:/auth:ro",
        "-p",
        f"{port}:3030",
        FUSEKI_IMAGE,
        "--passwd=/auth/passwd",
        "--auth=digest",
        "--mem",
        "--update",
        "/sparql",
    )
    wait_for_qlever(port)
    yield f"http://127.0.0.1:{port}/sparql", FUSEKI_USER, FUSEKI_PASSWORD
    _docker("rm", "-f", FUSEKI_DIGEST_CONTAINER, check=False)


@pytest.fixture(scope="session")
def api_manager(qlever_endpoint: str) -> APIManager:
    return APIManager(
        [str(DATA_DIR / "meta_v1.hf")],
        endpoint_override=qlever_endpoint,
    )


@pytest.fixture(scope="session")
def skgif_api_manager(qlever_endpoint: str) -> APIManager:
    manager = APIManager(
        [str(DATA_DIR / "skgif.hf")],
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
    if not isinstance(op, Operation):
        msg = f"Operation not found: {operation_url}"
        raise TypeError(msg)
    _response = op.exec(method="get", content_type="application/json")
    status = _response.status_code
    result = _response.body
    if status != HTTPStatus.OK:
        msg = f"API returned status {status}: {result}"
        raise RuntimeError(msg)
    return result
