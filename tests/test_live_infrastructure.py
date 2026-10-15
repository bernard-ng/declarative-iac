from __future__ import annotations

import http.client
import json
import os
import stat
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from declarative_iac.domain.live import canary
from declarative_iac.domain.live.cli import CliRunner
from declarative_iac.domain.live.instance import UnsafeTarget, require_local
from declarative_iac.domain.live.observer import (
    Collection,
    ForbiddenOperation,
    Observer,
    diff_snapshots,
)
from declarative_iac.domain.live.proxy import FaultPlan, FaultProxy


class Upstream:
    """A stand-in for Dokploy that records what reached it."""

    def __init__(self) -> None:
        self.received: list[tuple[str, str]] = []
        upstream = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                return

            def _answer(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                upstream.received.append((self.command, self.path))
                body = json.dumps({"ok": True, "path": self.path}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = _answer  # noqa: N815
            do_POST = _answer  # noqa: N815

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"


def _can_bind() -> bool:
    import socket

    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
        return True
    except OSError:
        return False


needs_sockets = pytest.mark.skipif(
    not _can_bind(), reason="this environment forbids binding local sockets"
)


@pytest.fixture
def upstream() -> Iterator[Upstream]:
    server = Upstream()
    yield server
    server.server.shutdown()


def call(url: str, method: str, path: str) -> int:
    host, port = url.removeprefix("http://").split(":")
    connection = http.client.HTTPConnection(host, int(port), timeout=10)
    connection.request(
        method,
        path,
        body=b"{}" if method == "POST" else None,
        headers={"Content-Type": "application/json"},
    )
    status = connection.getresponse().status
    connection.close()
    return status


@needs_sockets
def test_the_proxy_forwards_and_logs(upstream: Upstream):
    with FaultProxy(upstream.url) as proxy:
        assert call(proxy.url, "GET", "/api/tag.all") == 200
        assert call(proxy.url, "POST", "/api/tag.create") == 200
    assert upstream.received == [("GET", "/api/tag.all"), ("POST", "/api/tag.create")]
    assert [e.kind for e in proxy.log.exchanges] == ["query", "mutation"]
    assert proxy.log.exchanges[1].operation == "tag.create"


@needs_sockets
def test_drop_before_never_reaches_dokploy(upstream: Upstream):
    with (
        FaultProxy(upstream.url, FaultPlan("drop_before", 1)) as proxy,
        pytest.raises((http.client.HTTPException, ConnectionError, OSError)),
    ):
        call(proxy.url, "POST", "/api/tag.create")
    assert upstream.received == []
    assert proxy.fired


@needs_sockets
def test_drop_after_applies_but_loses_the_answer(upstream: Upstream):
    with FaultProxy(upstream.url, FaultPlan("drop_after", 2)) as proxy:
        assert call(proxy.url, "POST", "/api/tag.create") == 200
        with pytest.raises((http.client.HTTPException, ConnectionError, OSError)):
            call(proxy.url, "POST", "/api/tag.update")
        assert call(proxy.url, "POST", "/api/tag.remove") == 200
    assert [path for _, path in upstream.received] == [
        "/api/tag.create",
        "/api/tag.update",
        "/api/tag.remove",
    ]
    assert [e.fault for e in proxy.log.mutations()] == [None, "drop_after", None]


@needs_sockets
def test_reject_and_operation_targets(upstream: Upstream):
    plan = FaultPlan("reject", 1, target="tag.update")
    with FaultProxy(upstream.url, plan) as proxy:
        assert call(proxy.url, "POST", "/api/tag.create") == 200
        assert call(proxy.url, "POST", "/api/tag.update") == 500
    assert ("POST", "/api/tag.update") not in upstream.received


def test_unknown_fault_kinds_are_refused():
    with pytest.raises(ValueError):
        FaultPlan("explode", 1)


def test_only_local_targets_are_accepted():
    assert require_local("http://127.0.0.1:33000") == "http://127.0.0.1:33000"
    with pytest.raises(UnsafeTarget):
        require_local("https://dokploy.example.com")


def test_the_observer_is_read_only_and_sorted():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.headers["x-api-key"] == "key"
        return httpx.Response(
            200,
            json=[
                {"tagId": "b", "name": "y", "color": "#2"},
                {"tagId": "a", "name": "x", "color": "#1"},
            ],
        )

    observer = Observer(
        "http://127.0.0.1:1", "key", {"tag.all"}, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ForbiddenOperation):
        observer.read("tag.create")
    view = observer.snapshot([Collection("tag", "tag.all", "tagId", "name", ("color",))])
    assert [row["id"] for row in view["tag"]] == ["a", "b"]
    after = {"tag": [{"id": "a", "name": "x", "color": "#9"}, view["tag"][1]]}
    assert diff_snapshots(view, after, managed_ids={"a"}) == []
    assert diff_snapshots(view, after, managed_ids=set())[0]["id"] == "a"


def test_the_cli_runs_in_an_isolated_environment(tmp_path: Path, monkeypatch):
    binary = tmp_path / "dokploy"
    binary.write_text('#!/bin/sh\necho "$HOME|$DOKPLOY_URL|${LEAK:-none}|$*"\nexit 2\n')
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LEAK", "from-caller")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    cli = CliRunner(binary, workspace, "http://127.0.0.1:9", "k", "f", tmp_path / "home")
    result = cli.plan()
    assert result.exit_code == 2
    home, url, leak, args = result.stdout.strip().split("|")
    assert home == str(tmp_path / "home") and url == "http://127.0.0.1:9" and leak == "none"
    assert args == "plan --detailed-exitcode --json"
    assert os.environ["LEAK"] == "from-caller"


def test_canaries_are_found_outside_secret_files(tmp_path: Path):
    value = canary.make_canary("pw")
    (tmp_path / ".dokploy" / "secrets").mkdir(parents=True)
    (tmp_path / ".dokploy" / "secrets" / "a.env").write_text(f"PW={value}\n")
    assert canary.scan([tmp_path], ["plan output"], [value]) == []
    (tmp_path / ".dokploy" / "state.json").write_text(value)
    assert len(canary.scan([tmp_path], [f"error: {value}"], [value])) == 2
