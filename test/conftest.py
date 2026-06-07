# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import os
import subprocess
import time
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import requests

from ramose import APIManager

if TYPE_CHECKING:
    from collections.abc import Generator

# v0.5.45
QLEVER_IMAGE = "adfreiburg/qlever@sha256:4672a53f0ff4e55ac921d25832a21ec0bb3ca08f54d7c1950d04ebf6af7b8c21"
QLEVER_CONTAINER = "ramose-test-qlever"
QLEVER_PORT = 7019
QLEVER_SECURED_CONTAINER = "ramose-test-qlever-secured"
QLEVER_SECURED_PORT = 7020
QLEVER_ACCESS_TOKEN = "test-access-token"  # noqa: S105
INDEX_NAME = "ramose-test"
DOCKER_USER = f"{os.getuid()}:{os.getgid()}"

TEST_DIR = Path(__file__).resolve().parent
DATA_DIR = TEST_DIR / "data"


def _wait_for_qlever(port: int, timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = requests.get(f"http://127.0.0.1:{port}", timeout=2)
            if r.status_code in range(200, 500):
                return
        except requests.ConnectionError:
            pass
        time.sleep(1)
    msg = f"QLever did not become ready on port {port} within {timeout}s"
    raise TimeoutError(msg)


def _start_qlever(container: str, port: int, server_flags: str) -> None:
    subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container,
            "--entrypoint",
            "bash",
            "-u",
            DOCKER_USER,
            "-v",
            f"{DATA_DIR!s}:/index:ro",
            "-w",
            "/index",
            "-p",
            f"{port}:{port}",
            "--init",
            QLEVER_IMAGE,
            "-c",
            f"qlever-server -i {INDEX_NAME} -j 4 -p {port} -m 1G -c 500M -e 500M -k 50 -s 30s {server_flags}",
        ],
        check=True,
        capture_output=True,
    )
    _wait_for_qlever(port)


def _stop_qlever(container: str) -> None:
    subprocess.run(["docker", "stop", container], capture_output=True, check=False)
    subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)


@pytest.fixture(scope="session")
def qlever_endpoint() -> Generator[str, None, None]:
    _start_qlever(QLEVER_CONTAINER, QLEVER_PORT, "-n")
    yield f"http://127.0.0.1:{QLEVER_PORT}"
    _stop_qlever(QLEVER_CONTAINER)


@pytest.fixture(scope="session")
def qlever_secured_endpoint() -> Generator[tuple[str, str], None, None]:
    _start_qlever(QLEVER_SECURED_CONTAINER, QLEVER_SECURED_PORT, f"-a {QLEVER_ACCESS_TOKEN}")
    yield f"http://127.0.0.1:{QLEVER_SECURED_PORT}", QLEVER_ACCESS_TOKEN
    _stop_qlever(QLEVER_SECURED_CONTAINER)


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


FIXTURES_DIR = TEST_DIR / "fixtures"


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
