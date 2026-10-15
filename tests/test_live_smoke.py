"""End-to-end smoke test of an L1 run against a fake Dokploy and a fake system binary.

It exercises the orchestration (proxy, isolated CLI, observer, settling, evidence) without
Docker. The fakes implement only tags; they say nothing about the real system.
"""

from __future__ import annotations

import json
import socket
import stat
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from declarative_iac.domain.live import experiment
from declarative_iac.domain.live.instance import Instance
from declarative_iac.domain.scenarios.model import Scenario, Step


def _can_bind() -> bool:
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _can_bind(), reason="binding local sockets is forbidden")

FAKE_BINARY = """#!{python}
import json, os, sys, urllib.request, yaml
base = os.environ["DOKPLOY_URL"].rstrip("/") + "/api"
headers = {{"x-api-key": os.environ["DOKPLOY_API_KEY"], "Content-Type": "application/json"}}
def call(method, op, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"{{base}}/{{op}}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read() or b"null")
desired = (yaml.safe_load(open(".dokploy/settings.yaml"))["settings"] or {{}}).get("tags", {{}})
remote = {{t["name"]: t for t in call("GET", "tag.all")}}
changes = []
for name, body in sorted(desired.items()):
    if name not in remote:
        changes.append(("create", name, body))
    elif body.get("color") and remote[name]["color"] != body["color"]:
        changes.append(("update", name, body))
if sys.argv[1] == "plan":
    plan = {{"formatVersion": 1, "lineage": "fake", "stateSerial": 0, "configDigest": "x",
            "changes": [{{"address": f"tag.{{n}}", "kind": k}} for k, n, _ in changes],
            "drift": [], "complete": True, "applyable": True, "diagnostics": []}}
    print(json.dumps([{{"document": ".dokploy/settings.yaml", "plan": plan}}]))
    sys.exit(2 if changes else 0)
for kind, name, body in changes:
    if kind == "create":
        call("POST", "tag.create", {{"name": name, "color": body.get("color")}})
    else:
        call("POST", "tag.update", {{"tagId": remote[name]["tagId"], "color": body["color"]}})
"""


class FakeDokploy:
    def __init__(self) -> None:
        self.tags: dict[str, dict] = {}
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                return

            def _send(self, value: object) -> None:
                body = json.dumps(value).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                operation = self.path.split("?")[0].rsplit("/", 1)[-1]
                self._send(list(fake.tags.values()) if operation == "tag.all" else [])

            def do_POST(self) -> None:  # noqa: N802
                operation = self.path.rsplit("/", 1)[-1]
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if operation == "tag.create":
                    tag = {
                        "tagId": f"t{len(fake.tags) + 1}",
                        "name": body["name"],
                        "color": body.get("color"),
                    }
                    fake.tags[body["name"]] = tag
                elif operation == "tag.update":
                    tag = next(t for t in fake.tags.values() if t["tagId"] == body["tagId"])
                    tag["color"] = body["color"]
                self._send({"ok": True})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"


@pytest.fixture
def dokploy() -> Iterator[FakeDokploy]:
    fake = FakeDokploy()
    yield fake
    fake.server.shutdown()


def test_an_l1_run_records_every_measure(dokploy: FakeDokploy, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(experiment, "SETTLE_INTERVAL", 0.05)
    binary = tmp_path / "dokploy"
    binary.write_text(FAKE_BINARY.format(python=sys.executable))
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    scenario = Scenario(
        "unit-tag",
        "unit",
        ("tag",),
        (
            Step.parse({"settings": {"tags": {"probe": {}}}}),
            Step.parse(
                {
                    "settings": {"tags": {"probe": {"color": "#336699"}}},
                    "observe": [
                        {
                            "collection": "tag",
                            "name": "probe",
                            "field": "color",
                            "equals": "#336699",
                        }
                    ],
                    "expect": {"changes": ["update tag.probe"]},
                }
            ),
        ),
    )
    instance = Instance("fake", "fake", dokploy.url, "key")
    run_dir = tmp_path / "run"
    with experiment.open_run(run_dir, instance, binary, set()) as run:
        result = experiment.run_l1(run, scenario)
        run.finish(result)
    first, second = result["steps"]
    assert first["converge"] == {"k": 1, "converged": True, "final_exit": 0}
    assert first["a0_posts"] == 0 and first["h7a_identical"]
    assert second["expected_changes"]["equal"]
    assert second["observations"][0]["holds"] and second["settled"]
    assert second["foreign_changes"] == [] and second["duplicates"] == []
    stored = json.loads((run_dir / "result.json").read_text())
    assert stored["plan_posts"] == 0 and stored["leaks"] == []
    assert (run_dir / "raw" / "proxy.jsonl").read_text().count("tag.create") == 1
