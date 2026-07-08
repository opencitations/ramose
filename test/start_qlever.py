# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import contextlib
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

QLEVER_IMAGE = "adfreiburg/qlever@sha256:4672a53f0ff4e55ac921d25832a21ec0bb3ca08f54d7c1950d04ebf6af7b8c21"
INDEX_NAME = "ramose-test"
DATA_DIR = Path(__file__).resolve().parent / "data"
QLEVER_PORT = 7019
UI_IMAGE = "docker.io/adfreiburg/qlever-ui"
UI_PORT = 8176
UI_DB_DIR = Path(tempfile.gettempdir()) / "qlever-ui-db"


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], check=check, capture_output=True, text=True)


def wait_for_qlever(port: int, timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with contextlib.suppress(requests.RequestException):
            response = requests.get(f"http://127.0.0.1:{port}", timeout=2)
            if response.status_code in range(200, 500):
                return
        time.sleep(1)
    msg = f"QLever did not become ready on port {port} within {timeout}s"
    raise RuntimeError(msg)


def get_available_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_qlever_server(
    container: str = "qlever",
    port: int = QLEVER_PORT,
    server_flags: str = "",
    *,
    read_only: bool = False,
    user: str | None = None,
) -> str:
    if port == 0:
        port = get_available_port()
    _docker("rm", "-f", container, check=False)
    run_args = ["run", "-d", "--name", container, "--entrypoint", "bash", "--init"]
    if user:
        run_args += ["-u", user]
    mount = f"{DATA_DIR}:/index{':ro' if read_only else ''}"
    cmd = f"qlever-server -i {INDEX_NAME} -j 4 -p {port} -m 1G -c 500M -e 500M -k 50 -s 30s {server_flags}".strip()
    run_args += ["-v", mount, "-w", "/index", "-p", f"{port}:{port}", QLEVER_IMAGE, "-c", cmd]
    _docker(*run_args)
    wait_for_qlever(port)
    return f"http://127.0.0.1:{port}"


def stop_qlever_server(container: str) -> None:
    _docker("rm", "-f", container, check=False)


def start_ui() -> None:
    _docker("rm", "-f", "qlever-ui", check=False)
    UI_DB_DIR.mkdir(parents=True, exist_ok=True)
    db_file = UI_DB_DIR / "qleverui.sqlite3"
    if not db_file.exists():
        _docker("rm", "-f", "qlever-ui-tmp", check=False)
        _docker("create", "--name", "qlever-ui-tmp", UI_IMAGE)
        _docker("cp", "qlever-ui-tmp:/app/db/qleverui.sqlite3", str(db_file))
        _docker("rm", "-f", "qlever-ui-tmp", check=False)
    _docker(
        "run",
        "-d",
        "--name",
        "qlever-ui",
        "-v",
        f"{UI_DB_DIR}:/app/db",
        "-e",
        "QLEVERUI_DATABASE_URL=sqlite:////app/db/qleverui.sqlite3",
        "--add-host",
        "host.docker.internal:host-gateway",
        "-p",
        f"{UI_PORT}:7000",
        UI_IMAGE,
    )
    time.sleep(3)
    _docker(
        "exec",
        "qlever-ui",
        "python",
        "manage.py",
        "shell",
        "-c",
        f"from backend.models import Backend\n"
        f"b = Backend.objects.get(slug='default')\n"
        f"b.baseUrl = 'http://127.0.0.1:{QLEVER_PORT}'\n"
        f"b.isDefault = True\n"
        f"b.sortKey = 'A.0'\n"
        f"b.name = 'RAMOSE Test'\n"
        f"b.save()\n"
        f"Backend.objects.filter(slug='wikidata').update(isDefault=False)\n",
    )
    print(f"QLever UI: http://127.0.0.1:{UI_PORT}")


if __name__ == "__main__":  # pragma: no cover
    url = start_qlever_server()
    print(f"QLever SPARQL endpoint: {url}")
    if "--no-ui" not in sys.argv:
        start_ui()
    print("Stop with: docker rm -f qlever qlever-ui")
