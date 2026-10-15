"""A recording reverse proxy that injects one planned fault (paper Section 9, L3).

The proxy sits between the CLI and Dokploy. It logs every request (operation, query or mutation,
status, timing) and, when a fault is planned, applies it to the n-th request that matches:

- `drop_before`: close the connection without forwarding (nothing applied, outcome unknown);
- `drop_after`: forward, then close the connection without replying (applied, outcome unknown);
- `reject`: answer HTTP 500 without forwarding (a definitive failure, nothing applied);
- `unavailable`: answer HTTP 503 without forwarding (meant for reads);
- `delay`: forward after waiting `seconds`.

Only the standard library is used, so the proxy's behaviour does not depend on a web framework.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import socket
import threading
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

ERROR_BODY_LIMIT = 2000
FAULT_KINDS = ("drop_before", "drop_after", "reject", "unavailable", "delay")
HOP_HEADERS = {
    "connection",
    "keep-alive",
    "transfer-encoding",
    "te",
    "trailer",
    "upgrade",
    "proxy-authorization",
    "proxy-authenticate",
    "host",
    "content-length",
}


@dataclass(frozen=True)
class FaultPlan:
    """Inject `kind` at the `ordinal`-th (1-based) request matching `target`.

    `target` is `mutation` (any POST), `query` (any GET), or an operation such as `tag.create`.
    """

    kind: str
    ordinal: int
    target: str = "mutation"
    seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in FAULT_KINDS:
            raise ValueError(f"unknown fault {self.kind!r}")
        if self.ordinal < 1:
            raise ValueError("ordinal is 1-based")


@dataclass
class Exchange:
    sequence: int
    method: str
    operation: str
    kind: str  # query or mutation
    status: int | None
    seconds: float
    fault: str | None = None
    match_index: int | None = None
    # The first ERROR_BODY_LIMIT bytes of a response with status >= 400, for diagnosis. Secret
    # values are removed when the log is written (`ProxyLog.to_jsonl(redact=...)`).
    error_body: str | None = None


@dataclass
class ProxyLog:
    exchanges: list[Exchange] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def mutations(self) -> list[Exchange]:
        return [e for e in self.exchanges if e.kind == "mutation"]

    def to_jsonl(self, redact: Iterable[str] = ()) -> str:
        secrets = [value for value in redact if value]
        lines: list[str] = []
        for exchange in self.exchanges:
            record = asdict(exchange)
            body = record.get("error_body")
            if body:
                for value in secrets:
                    body = body.replace(value, "[redacted]")
                record["error_body"] = body
            lines.append(json.dumps(record, sort_keys=True) + "\n")
        return "".join(lines)


def _operation(path: str) -> str:
    return urlparse(path).path.rsplit("/", 1)[-1]


class FaultProxy:
    def __init__(self, upstream: str, plan: FaultPlan | None = None, port: int = 0) -> None:
        self.upstream = urlparse(upstream)
        self.plan = plan
        self.log = ProxyLog()
        self._matches = 0
        self._fired = False
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

            def do_GET(self) -> None:  # noqa: N802
                proxy._handle(self, "GET")

            def do_POST(self) -> None:  # noqa: N802
                proxy._handle(self, "POST")

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> FaultProxy:
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()

    @property
    def fired(self) -> bool:
        return self._fired

    def _decide(self, method: str, operation: str) -> tuple[str | None, int | None]:
        if self.plan is None or self._fired:
            return None, None
        kind = "mutation" if method == "POST" else "query"
        if self.plan.target not in (kind, operation):
            return None, None
        self._matches += 1
        if self._matches == self.plan.ordinal:
            self._fired = True
            return self.plan.kind, self._matches
        return None, self._matches

    def _handle(self, handler: BaseHTTPRequestHandler, method: str) -> None:
        started = time.monotonic()
        length = int(handler.headers.get("Content-Length") or 0)
        body = handler.rfile.read(length) if length else b""
        operation = _operation(handler.path)
        with self.log.lock:
            fault, index = self._decide(method, operation)
            exchange = Exchange(
                len(self.log.exchanges) + 1,
                method,
                operation,
                "mutation" if method == "POST" else "query",
                None,
                0.0,
                fault,
                index,
            )
            self.log.exchanges.append(exchange)
        status: int | None = None
        try:
            if fault == "drop_before":
                self._drop(handler)
                return
            if fault in ("reject", "unavailable"):
                status = 500 if fault == "reject" else 503
                self._reply(
                    handler,
                    status,
                    b'{"message":"injected fault"}',
                    {"Content-Type": "application/json"},
                )
                return
            if fault == "delay" and self.plan is not None:
                time.sleep(self.plan.seconds)
            status, headers, payload = self._forward(handler, method, body)
            if status >= 400:
                exchange.error_body = payload[:ERROR_BODY_LIMIT].decode("utf-8", "replace")
            if fault == "drop_after":
                self._drop(handler)
                return
            self._reply(handler, status, payload, headers)
        finally:
            exchange.status = status
            exchange.seconds = round(time.monotonic() - started, 4)

    def _forward(
        self, handler: BaseHTTPRequestHandler, method: str, body: bytes
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection(
            self.upstream.hostname or "127.0.0.1", self.upstream.port or 80, timeout=600
        )
        headers = {k: v for k, v in handler.headers.items() if k.lower() not in HOP_HEADERS}
        connection.request(method, handler.path, body=body or None, headers=headers)
        response = connection.getresponse()
        payload = response.read()
        out = {k: v for k, v in response.getheaders() if k.lower() not in HOP_HEADERS}
        connection.close()
        return response.status, out, payload

    @staticmethod
    def _reply(
        handler: BaseHTTPRequestHandler, status: int, payload: bytes, headers: dict[str, str]
    ) -> None:
        handler.send_response(status)
        for key, value in headers.items():
            handler.send_header(key, value)
        handler.send_header("Content-Length", str(len(payload)))
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.wfile.write(payload)
        handler.close_connection = True

    @staticmethod
    def _drop(handler: BaseHTTPRequestHandler) -> None:
        handler.close_connection = True
        with contextlib.suppress(OSError):
            handler.connection.shutdown(socket.SHUT_RDWR)
