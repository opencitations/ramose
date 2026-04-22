# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import os
import subprocess
import time
from pathlib import Path

import pytest
import requests

from ramose import APIManager

# v0.5.45
QLEVER_IMAGE = "adfreiburg/qlever@sha256:4672a53f0ff4e55ac921d25832a21ec0bb3ca08f54d7c1950d04ebf6af7b8c21"
QLEVER_CONTAINER = "ramose-test-qlever"
QLEVER_PORT = 7019
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
    raise TimeoutError(f"QLever did not become ready on port {port} within {timeout}s")


@pytest.fixture(scope="session")
def qlever_endpoint():
    subprocess.run(["docker", "rm", "-f", QLEVER_CONTAINER], capture_output=True)
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            QLEVER_CONTAINER,
            "--entrypoint",
            "bash",
            "-u",
            DOCKER_USER,
            "-v",
            f"{DATA_DIR!s}:/index:ro",
            "-w",
            "/index",
            "-p",
            f"{QLEVER_PORT}:{QLEVER_PORT}",
            "--init",
            QLEVER_IMAGE,
            "-c",
            f"qlever-server -i {INDEX_NAME} -j 4 -p {QLEVER_PORT} -m 1G -c 500M -e 500M -k 50 -s 30s",
        ],
        check=True,
        capture_output=True,
    )

    _wait_for_qlever(QLEVER_PORT)
    endpoint = f"http://127.0.0.1:{QLEVER_PORT}"

    yield endpoint

    subprocess.run(["docker", "stop", QLEVER_CONTAINER], capture_output=True)
    subprocess.run(["docker", "rm", "-f", QLEVER_CONTAINER], capture_output=True)


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


def execute_operation(api_manager: APIManager, operation_url: str) -> str:
    op = api_manager.get_op(operation_url)
    if isinstance(op, tuple):
        raise TypeError(f"Operation not found: {operation_url}")
    status, result, _ = op.exec(method="get", content_type="application/json")
    if status != 200:
        raise RuntimeError(f"API returned status {status}: {result}")
    return result
