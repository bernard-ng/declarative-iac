"""Recording reverse proxy (oracle O-traffic).

Run it between the CLI and Dokploy:  DOKPLOY_URL=http://127.0.0.1:8899  while the proxy forwards to
the real instance. Each request is appended to a JSONL log with method, operation, status, and
latency; bodies are NOT logged (they may hold secrets). Fault injection for E4 hooks in here too:
a rule can drop the response after the upstream has committed it (the outcome-unknown case).
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

HOP = {"connection", "keep-alive", "transfer-encoding", "content-length", "content-encoding", "host"}


@dataclass
class FaultRule:
    operation: str                 # e.g. "application.create"
    kind: str                      # "drop_before" | "drop_after" | "status_503" | "delay"
    on_call: int = 1               # fire on the nth matching call
    delay_s: float = 0.0
    _seen: int = 0

    def matches(self, operation: str) -> bool:
        if operation != self.operation:
            return False
        self._seen += 1
        return self._seen == self.on_call


@dataclass
class CallRecorder:
    upstream: str
    log_path: Path
    port: int = 8899
    faults: list[FaultRule] = field(default_factory=list)
    _server: ThreadingHTTPServer | None = None

    def start(self) -> str:
        recorder = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silence default stderr logging
                pass

            def _forward(self):
                started = time.time()
                op = self.path.split("?", 1)[0].removeprefix("/api/")
                length = int(self.headers.get("content-length") or 0)
                body = self.rfile.read(length) if length else None
                rule = next((f for f in recorder.faults if f.matches(op)), None)
                record = {"t": started, "method": self.command, "operation": op, "fault": rule.kind if rule else None}
                if rule and rule.kind == "drop_before":
                    record["status"] = "dropped_before"
                    recorder._write(record)
                    self.close_connection = True
                    return
                if rule and rule.kind == "status_503":
                    record["status"] = 503
                    recorder._write(record)
                    self.send_response(503); self.end_headers(); return
                if rule and rule.kind == "delay":
                    time.sleep(rule.delay_s)
                headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
                r = requests.request(self.command, recorder.upstream.rstrip("/") + self.path,
                                     headers=headers, data=body, timeout=120)
                record.update(status=r.status_code, ms=round((time.time() - started) * 1000, 1))
                if rule and rule.kind == "drop_after":
                    record["status"] = f"dropped_after:{r.status_code}"
                    recorder._write(record)
                    self.close_connection = True
                    return
                recorder._write(record)
                self.send_response(r.status_code)
                for k, v in r.headers.items():
                    if k.lower() not in HOP:
                        self.send_header(k, v)
                self.send_header("content-length", str(len(r.content)))
                self.end_headers()
                self.wfile.write(r.content)

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _forward

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.port}"

    def _write(self, record: dict) -> None:
        with self._lock, self.log_path.open("a") as fh:
            fh.write(json.dumps(record) + "\n")

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()


def summarize(log_path: Path, since: float = 0.0) -> dict:
    reads = mutations = 0
    ops: dict[str, int] = {}
    for line in log_path.read_text().splitlines():
        r = json.loads(line)
        if r["t"] < since:
            continue
        ops[r["operation"]] = ops.get(r["operation"], 0) + 1
        if r["method"] == "GET":
            reads += 1
        else:
            mutations += 1
    return {"reads": reads, "mutations": mutations, "by_operation": ops}
