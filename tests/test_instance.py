from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest
import yaml

from declarative_iac.core.paths import repository_root
from declarative_iac.core.shell import CommandError, Completed
from declarative_iac.domain.live import instance
from declarative_iac.domain.live.experiment import fingerprint_key


class FakeSnapshot:
    def __init__(self, text: str) -> None:
        self.text = text

    def show(self, path: str) -> bytes:
        assert path == instance.SYSTEM_COMPOSE
        return self.text.encode()


def system_compose() -> dict:
    ours = yaml.safe_load((repository_root() / "compose.yaml").read_text())
    theirs = json.loads(json.dumps(ours))
    theirs["name"] = "dokploy-iac-integration"
    theirs["services"]["dokploy"]["image"] = "dokploy/dokploy:v0.30.6@sha256:abc"
    theirs["services"]["dokploy"]["ports"] = ["127.0.0.1:${DOKPLOY_INTEGRATION_PORT:-33000}:3000"]
    theirs["secrets"]["auth_secret"]["file"] = ".integration/secrets/auth_secret"
    return theirs


def test_documented_differences_are_allowed():
    snapshot = FakeSnapshot(yaml.safe_dump(system_compose()))
    assert instance.compare_with_system(snapshot) == []  # type: ignore[arg-type]


def test_any_other_difference_is_reported():
    theirs = system_compose()
    theirs["services"]["postgres"]["image"] = "postgres:17"
    theirs["services"]["dokploy"]["environment"]["EXTRA"] = "1"
    snapshot = FakeSnapshot(yaml.safe_dump(theirs))
    assert instance.compare_with_system(snapshot) == [  # type: ignore[arg-type]
        "services.dokploy.environment.EXTRA",
        "services.postgres.image",
    ]


def test_every_port_is_bound_to_loopback():
    document = yaml.safe_load((repository_root() / "compose.yaml").read_text())
    ports = [p for s in document["services"].values() for p in s.get("ports", [])]
    assert ports and all(str(p).startswith("127.0.0.1:") for p in ports)


def test_bootstrap_follows_the_system_sequence():
    calls: list[tuple[str, str, dict | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        assert request.headers["origin"] == "http://127.0.0.1:33000"
        if request.url.path == "/api/organization.all":
            return httpx.Response(200, json=[{"id": "org-1"}])
        if request.url.path == "/api/user.createApiKey":
            return httpx.Response(200, json={"key": "secret-key"})
        return httpx.Response(200, json={}, headers={"set-cookie": "session=1; Path=/"})

    key = instance.bootstrap("http://127.0.0.1:33000", "pw", httpx.MockTransport(handler))
    assert key == "secret-key"
    assert [path for _, path, _ in calls] == [
        "/api/auth/sign-up/email",
        "/api/organization.all",
        "/api/user.createApiKey",
    ]
    assert calls[2][2] == {
        "name": "declarative-iac-eval",
        "metadata": {"organizationId": "org-1"},
        "rateLimitEnabled": False,
    }


def test_bootstrap_refuses_an_instance_that_is_not_fresh():
    transport = httpx.MockTransport(lambda request: httpx.Response(422, json={}))
    with pytest.raises(RuntimeError, match="not fresh"):
        instance.bootstrap("http://127.0.0.1:33000", "pw", transport)


def test_the_fingerprint_key_has_the_form_the_cli_requires():
    # dokploy-cli fingerprint_key.rs: `<uuid>:<64 lowercase hexadecimal characters>`
    pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:[0-9a-f]{64}$"
    )
    keys = {fingerprint_key() for _ in range(3)}
    assert len(keys) == 3 and all(pattern.match(key) for key in keys)


class Recorder:
    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[tuple[list[str], dict]] = []
        self.fail_on = fail_on

    def __call__(self, args, **kwargs):
        self.calls.append((list(args), kwargs.get("env") or {}))
        code = 1 if self.fail_on and self.fail_on in args else 0
        stdout = (
            "active true" if "info" in args else "overlay swarm true" if "network" in args else ""
        )
        completed = Completed(tuple(args), code, stdout, "boom" if code else "")
        if code and kwargs.get("check", True):
            raise CommandError(completed)
        return completed


class Pinned:
    def __init__(self) -> None:
        self.version = "0.30.6"
        self.image = "dokploy/dokploy:v0.30.6@sha256:abc"


def _provider(monkeypatch, tmp_path: Path, recorder: Recorder) -> instance.InstanceProvider:
    monkeypatch.setenv("DIAC_ROOT", str(repository_root()))
    monkeypatch.setattr(instance, "run", recorder)
    monkeypatch.setattr(instance, "compose_command", lambda: ["docker", "compose"])
    provider = instance.InstanceProvider(object())  # type: ignore[arg-type]
    provider.runtime = tmp_path / "instance"
    return provider


def test_docker_runs_with_the_callers_configuration(monkeypatch, tmp_path: Path):
    recorder = Recorder()
    provider = _provider(monkeypatch, tmp_path, recorder)
    provider.stop(Pinned())  # type: ignore[arg-type]
    args, env = recorder.calls[-1]
    assert args[:4] == ["docker", "compose", "--project-name", instance.PROJECT]
    assert "DOCKER_CONFIG" not in env
    assert env["DOKPLOY_IMAGE"] == Pinned().image


def test_a_failed_start_removes_the_stack(monkeypatch, tmp_path: Path):
    recorder = Recorder(fail_on="up")
    provider = _provider(monkeypatch, tmp_path, recorder)
    with pytest.raises(instance.InstanceFailed, match="exited 1: boom"):
        provider.start(Pinned())  # type: ignore[arg-type]
    assert "down" in recorder.calls[-1][0]


def test_stopping_forgets_the_removed_instance(monkeypatch, tmp_path: Path):
    provider = _provider(monkeypatch, tmp_path, Recorder())
    state = provider.runtime / "state"
    state.mkdir(parents=True)
    (state / "api-key").write_text("k\n")
    (state / "version").write_text("0.30.6\n")
    assert provider.running() is not None
    provider.stop(Pinned())  # type: ignore[arg-type]
    assert provider.running() is None
