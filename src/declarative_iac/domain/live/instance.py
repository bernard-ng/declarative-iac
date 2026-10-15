"""Disposable Dokploy instances, started from this repository's `compose.yaml`.

The stack mirrors the system's own `compose.integration.yaml` at the pinned commit (checked by
`compare_with_system`), and the image of each Dokploy version is read from the pinned system.
The bootstrap (administrator, organisation, API key) is the sequence of the system's
`scripts/integration/bootstrap.sh`, made here over HTTP so the harness needs no shell tools.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml

from declarative_iac.core.paths import cache_dir, repository_root
from declarative_iac.core.shell import CommandError, Completed, run, which
from declarative_iac.domain.provenance import DokployVersion, Snapshot

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
PROJECT = "declarative-iac-eval"
SYSTEM_COMPOSE = "compose.integration.yaml"
DEFAULT_PORT = 33000
ADMIN_EMAIL = "evaluation@dokploy.test"


class UnsafeTarget(RuntimeError):
    """A URL that is not a local disposable instance."""


class DockerUnavailable(RuntimeError):
    """No Docker client, Compose or daemon is reachable."""


class InstanceFailed(RuntimeError):
    """The stack did not start, or the fresh instance could not be bootstrapped."""


def require_local(url: str) -> str:
    host = urlparse(url).hostname or ""
    if host not in LOCAL_HOSTS:
        raise UnsafeTarget(f"refusing {url}: live experiments only run against local instances")
    return url


@dataclass(frozen=True)
class Instance:
    version: str
    image: str
    base_url: str
    api_key: str = ""

    def describe(self) -> dict[str, str]:
        return {"version": self.version, "image": self.image, "base_url": self.base_url}


def compose_command() -> list[str]:
    """`docker compose` when the plugin is installed, otherwise the standalone `docker-compose`."""

    if which("docker") is None:
        raise DockerUnavailable("docker is required for live experiments")
    if run(["docker", "compose", "version"], check=False, timeout=30).ok:
        return ["docker", "compose"]
    if which("docker-compose") is not None:
        return ["docker-compose"]
    raise DockerUnavailable("Docker Compose v2 is required (`docker compose` or `docker-compose`)")


def bootstrap(base_url: str, password: str, transport: httpx.BaseTransport | None = None) -> str:
    """Create the administrator and an API key on a fresh instance; return the key."""

    headers = {"Origin": base_url}
    with httpx.Client(
        base_url=base_url, headers=headers, timeout=60, transport=transport
    ) as client:
        signup = client.post(
            "/api/auth/sign-up/email",
            json={
                "email": ADMIN_EMAIL,
                "password": password,
                "name": "Evaluation",
                "lastName": "Harness",
            },
        )
        if signup.status_code >= 400:
            raise RuntimeError(
                f"could not create the administrator ({signup.status_code}); "
                "the instance is not fresh: run `declarative-iac live down` first"
            )
        organizations = client.get("/api/organization.all")
        organizations.raise_for_status()
        organization_id = organizations.json()[0]["id"]
        created = client.post(
            "/api/user.createApiKey",
            json={
                "name": "declarative-iac-eval",
                "metadata": {"organizationId": organization_id},
                "rateLimitEnabled": False,
            },
        )
        created.raise_for_status()
        return str(created.json()["key"])


def wait_for_api(base_url: str, api_key: str, attempts: int = 30) -> None:
    import time

    for _ in range(attempts):
        try:
            response = httpx.get(
                f"{base_url}/api/project.all", headers={"x-api-key": api_key}, timeout=10
            )
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise RuntimeError("the API key was created but the API does not accept it")


class InstanceProvider:
    """Starts and always tears down a fresh Dokploy of one supported version."""

    def __init__(self, snapshot: Snapshot, port: int = DEFAULT_PORT) -> None:
        self.snapshot = snapshot
        self.port = port
        self.root = repository_root()
        self.compose_file = self.root / "compose.yaml"
        self.runtime = cache_dir() / "instance"

    @property
    def base_url(self) -> str:
        return require_local(f"http://127.0.0.1:{self.port}")

    def _env(self, version: DokployVersion | None) -> dict[str, str]:
        # The caller's Docker configuration is used as is: on Docker Desktop it holds the active
        # context and the `compose` plugin (~/.docker/cli-plugins), so it must not be redirected.
        env = {"DIAC_DOKPLOY_PORT": str(self.port)}
        # `down` needs a value for the required image variable even though it pulls nothing.
        env["DOKPLOY_IMAGE"] = version.image if version else "unused-for-down"
        return env

    def _docker(self, *args: str, timeout: float = 120, check: bool = True) -> Completed:
        return run(["docker", *args], env=self._env(None), timeout=timeout, check=check)

    def _compose(
        self, version: DokployVersion | None, *args: str, timeout: float = 600, check: bool = True
    ) -> Completed:
        return run(
            [
                *compose_command(),
                "--project-name",
                PROJECT,
                "--file",
                str(self.compose_file),
                *args,
            ],
            cwd=self.root,
            env=self._env(version),
            timeout=timeout,
            check=check,
        )

    def _write_secret(self, name: str) -> str:
        directory = self.runtime / "secrets"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        value = secrets.token_hex(32)
        path.write_text(value + "\n")
        path.chmod(0o600)
        return value

    def ensure_swarm(self) -> None:
        """Dokploy deploys services through Swarm: make the host a single-node manager and
        create the attachable overlay network Dokploy expects (as the system's scripts do)."""

        info = self._docker(
            "info",
            "--format",
            "{{.Swarm.LocalNodeState}} {{.Swarm.ControlAvailable}}",
            check=False,
        )
        if not info.ok:
            reason = (info.stderr.strip().splitlines() or ["no output"])[0]
            raise DockerUnavailable(f"cannot reach the Docker daemon: {reason}")
        state = info.stdout.split()
        if state and state[0] == "inactive":
            self._docker("swarm", "init", "--advertise-addr", "127.0.0.1")
            state = self._docker(
                "info", "--format", "{{.Swarm.LocalNodeState}} {{.Swarm.ControlAvailable}}"
            ).stdout.split()
        if state != ["active", "true"]:
            raise DockerUnavailable("the Docker host must be a Swarm manager")
        network = self._docker(
            "network",
            "inspect",
            "--format",
            "{{.Driver}} {{.Scope}} {{.Attachable}}",
            "dokploy-network",
            check=False,
        )
        if not network.ok:
            self._docker(
                "network", "create", "--driver", "overlay", "--attachable", "dokploy-network"
            )
        elif network.stdout.strip() != "overlay swarm true":
            raise DockerUnavailable("the existing dokploy-network must be an attachable overlay")

    def start(self, version: DokployVersion) -> Instance:
        """A fresh, bootstrapped instance; on any failure the stack is removed again."""

        try:
            return self._start(version)
        except CommandError as error:
            self.stop(version, check=False)
            detail = (error.completed.stderr.strip() or error.completed.stdout.strip()).splitlines()
            raise InstanceFailed(
                f"`{' '.join(error.completed.args[:3])} …` exited {error.completed.returncode}: "
                + (detail[0] if detail else "no output")
            ) from error
        except Exception:
            self.stop(version, check=False)
            raise

    def _start(self, version: DokployVersion) -> Instance:
        self.ensure_swarm()
        self.stop(version)  # a fresh instance every time: no data survives from a previous run
        self._write_secret("postgres_password")
        self._write_secret("auth_secret")
        self._compose(version, "up", "--detach", "--wait", "--wait-timeout", "300", timeout=900)
        password = self._write_secret("admin_password")
        key = bootstrap(self.base_url, password)
        wait_for_api(self.base_url, key)
        state = self.runtime / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / "api-key").write_text(key + "\n")
        (state / "api-key").chmod(0o600)
        (state / "version").write_text(version.version + "\n")
        return Instance(version.version, version.image, self.base_url, key)

    def stop(self, version: DokployVersion | None = None, check: bool = True) -> None:
        """Remove the containers and volumes of this project only; Swarm stays initialised."""

        self._compose(version, "down", "--remove-orphans", "--volumes", timeout=600, check=check)
        # The key and version belonged to the removed instance; keeping them would make
        # `running()` report an instance that no longer exists.
        for name in ("api-key", "version"):
            (self.runtime / "state" / name).unlink(missing_ok=True)

    def running(self) -> Instance | None:
        state = self.runtime / "state"
        try:
            key = (state / "api-key").read_text().strip()
            version = (state / "version").read_text().strip()
        except FileNotFoundError:
            return None
        return Instance(version, "running", self.base_url, key)


# Keys that may differ between this repository's compose.yaml and the system's, by design.
ALLOWED_DIFFERENCES = {
    ("name",),
    ("x-dokploy-image",),
    ("services", "dokploy", "image"),
    ("services", "dokploy", "ports"),
    ("secrets", "auth_secret", "file"),
    ("secrets", "postgres_password", "file"),
}


def _differences(a: Any, b: Any, path: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[tuple[str, ...]] = []
        for key in sorted(set(a) | set(b)):
            out += _differences(a.get(key), b.get(key), (*path, str(key)))
        return out
    return [] if a == b else [path]


def compare_with_system(snapshot: Snapshot, compose_file: Path | None = None) -> list[str]:
    """Differences between `compose.yaml` and the system's integration stack, other than the
    documented ones; empty when the two stacks are the same."""

    ours = yaml.safe_load((compose_file or repository_root() / "compose.yaml").read_text())
    theirs = yaml.safe_load(snapshot.show(SYSTEM_COMPOSE))
    found = [d for d in _differences(ours, theirs) if d not in ALLOWED_DIFFERENCES]
    return [".".join(d) for d in found]


def external_instance() -> Instance | None:
    """An already running local instance given by `DIAC_DOKPLOY_URL` and `DIAC_DOKPLOY_API_KEY`
    (for debugging one cell); still refused unless it is local."""

    url = os.environ.get("DIAC_DOKPLOY_URL")
    if not url:
        return None
    return Instance(
        os.environ.get("DIAC_DOKPLOY_VERSION", "unknown"),
        "external",
        require_local(url),
        os.environ.get("DIAC_DOKPLOY_API_KEY", ""),
    )


def workspace_root(run_dir: Path) -> Path:
    path = run_dir / "workspace"
    path.mkdir(parents=True, exist_ok=True)
    return path
