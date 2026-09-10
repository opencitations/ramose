# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import json
import os
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from threading import Lock, Thread

import requests

DATA_PORT = 7001
CONTROL_PORT = 7002
UPSTREAM_TIMEOUT_SECONDS = 600
MAX_REQUEST_LINE_BYTES = 64 * 1024 * 1024
HOP_BY_HOP_HEADERS = {"connection", "keep-alive", "transfer-encoding", "content-length", "content-encoding", "host"}


class State:
    def __init__(self) -> None:
        self.lock = Lock()
        self.upstream = ""
        self.label = ""
        self.backend = ""
        self.active = 0
        self.records: list[dict[str, object]] = []

    def begin(self) -> str:
        with self.lock:
            self.active += 1
            return self.label

    def finish(self, label: str, values: dict[str, object]) -> None:
        with self.lock:
            self.active -= 1
            self.records.append({"backend": self.backend, "label": label, **values})

    def drain(self) -> list[dict[str, object]]:
        with self.lock:
            records, self.records = self.records, []
            return records

    def status(self) -> dict[str, int]:
        with self.lock:
            return {"active": self.active}


STATE = State()


class Server(ThreadingHTTPServer):
    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        self.server_name = str(self.server_address[0])
        self.server_port = int(self.server_address[1])


class QuietHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002, ARG002
        return


class DataHandler(QuietHandler):
    def handle_one_request(self) -> None:
        self.raw_requestline = self.rfile.readline(MAX_REQUEST_LINE_BYTES + 1)
        if not self.raw_requestline:
            self.close_connection = True
            return
        if not self.parse_request():
            return
        self.forward()
        self.wfile.flush()

    def forward(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"])) if "Content-Length" in self.headers else b""
        started = time.perf_counter_ns()
        label = STATE.begin()
        headers = {name: value for name, value in self.headers.items() if name.lower() not in HOP_BY_HOP_HEADERS}
        headers["Accept-Encoding"] = "identity"
        try:
            upstream = requests.request(
                self.command,
                STATE.upstream + self.path,
                data=body,
                headers=headers,
                timeout=UPSTREAM_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            self.record(label, started, len(body), HTTPStatus.BAD_GATEWAY, 0, str(exc))
            self.respond(HTTPStatus.BAD_GATEWAY, {"Content-Type": "text/plain"}, str(exc).encode())
            return
        response_headers = {
            name: value for name, value in upstream.headers.items() if name.lower() not in HOP_BY_HOP_HEADERS
        }
        error = upstream.text if upstream.status_code >= HTTPStatus.BAD_REQUEST else ""
        self.record(label, started, len(body), upstream.status_code, len(upstream.content), error)
        try:
            self.respond(upstream.status_code, response_headers, upstream.content)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def respond(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def record(  # noqa: PLR0913
        self, label: str, started_ns: int, request_bytes: int, status: int, response_bytes: int, error: str
    ) -> None:
        STATE.finish(
            label,
            {
                "method": self.command,
                "request_bytes": request_bytes + len(self.raw_requestline),
                "status": status,
                "response_bytes": response_bytes,
                "latency_ms": (time.perf_counter_ns() - started_ns) / 1_000_000,
                "started_ns": started_ns,
                "error": error,
            },
        )


class ControlHandler(QuietHandler):
    def do_GET(self) -> None:
        if self.path == "/records":
            self.reply(STATE.drain())
        elif self.path == "/status":
            self.reply(STATE.status())
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/label":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with STATE.lock:
            STATE.label = payload["label"]
        self.reply({})

    def reply(self, value: object) -> None:
        body = json.dumps(value).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    STATE.upstream = os.environ["PROXY_UPSTREAM"]
    STATE.backend = os.environ["PROXY_BACKEND"]
    control = Server(("0.0.0.0", CONTROL_PORT), ControlHandler)  # noqa: S104
    Thread(target=control.serve_forever, daemon=True).start()
    Server(("0.0.0.0", DATA_PORT), DataHandler).serve_forever()  # noqa: S104


if __name__ == "__main__":
    main()
