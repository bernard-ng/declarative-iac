"""The system under study, read only at its pinned commit."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from declarative_iac.core.canonical import load_yaml_text, read_yaml
from declarative_iac.core.paths import cache_dir, config_dir
from declarative_iac.core.shell import run


class SnapshotError(RuntimeError):
    """The checkout does not hold the pinned snapshot."""


@dataclass(frozen=True)
class DokployVersion:
    version: str
    status: str
    image: str
    openapi: str

    @property
    def digest(self) -> str:
        return self.image.split("@", 1)[1] if "@" in self.image else ""


@dataclass(frozen=True)
class SnapshotConfig:
    """`config/snapshot.yaml`."""

    snapshot: str
    name: str
    version: str
    repository: str
    tag: str
    commit: str
    binary_sha256: dict[str, str]
    binary_path: str
    binary_build: str
    rust: str
    toolchain_image: str
    toolchain_digest: str | None
    versions_path: str
    specs_path: str
    fixtures_path: str

    @classmethod
    def load(cls, path: Path | None = None) -> SnapshotConfig:
        data: dict[str, Any] = read_yaml(path or config_dir() / "snapshot.yaml")
        sut = data["system_under_study"]
        binary = sut["release_binary"]
        toolchain = data["toolchain"]
        paths = data["paths"]
        return cls(
            snapshot=data["snapshot"],
            name=sut["name"],
            version=sut["version"],
            repository=sut["repository"],
            tag=sut["tag"],
            commit=sut["commit"],
            binary_sha256=dict(binary.get("sha256") or {}),
            binary_path=binary["path_in_checkout"],
            binary_build=binary["build"],
            rust=str(toolchain["rust"]),
            toolchain_image=toolchain["image"],
            toolchain_digest=toolchain.get("image_digest"),
            versions_path=paths["versions"],
            specs_path=paths["specs"],
            fixtures_path=paths["fixtures"],
        )


class Snapshot:
    """Reads the system under study at one commit, through git only.

    The checkout is `DIAC_SUT_PATH` when set (an existing clone, never written to), otherwise a
    clone under `.cache/sut`. Nothing is read from a working tree: every file comes from
    `git show <commit>:<path>`, so local edits cannot leak into results.
    """

    def __init__(self, config: SnapshotConfig, checkout: Path | None = None) -> None:
        self.config = config
        self.checkout = checkout or self._default_checkout()

    @classmethod
    def pinned(cls) -> Snapshot:
        snapshot = cls(SnapshotConfig.load())
        snapshot.ensure()
        return snapshot

    @property
    def commit(self) -> str:
        return self.config.commit

    def _default_checkout(self) -> Path:
        override = os.environ.get("DIAC_SUT_PATH")
        return Path(override).expanduser().resolve() if override else cache_dir() / "sut"

    def _git(self, *args: str, check: bool = True) -> str:
        return run(["git", "-C", str(self.checkout), *args], check=check).stdout

    def ensure(self) -> None:
        """Clone when needed and check that the pinned commit and tag are present."""

        if not (self.checkout / ".git").exists() and not (self.checkout / "HEAD").exists():
            if os.environ.get("DIAC_SUT_PATH"):
                raise SnapshotError(f"DIAC_SUT_PATH is not a git repository: {self.checkout}")
            self.checkout.parent.mkdir(parents=True, exist_ok=True)
            run(["git", "clone", "--quiet", self.config.repository, str(self.checkout)])
        exists = run(
            ["git", "-C", str(self.checkout), "cat-file", "-e", f"{self.commit}^{{commit}}"],
            check=False,
        )
        if not exists.ok:
            raise SnapshotError(f"commit {self.commit} is not in {self.checkout}")

    def tag_commit(self) -> str | None:
        """The commit the configured tag points to, or None when the tag is absent."""

        resolved = run(
            [
                "git",
                "-C",
                str(self.checkout),
                "rev-parse",
                "--verify",
                "--quiet",
                f"refs/tags/{self.config.tag}^{{commit}}",
            ],
            check=False,
        )
        return resolved.stdout.strip() if resolved.ok else None

    def verify(self) -> list[str]:
        """Problems with the checkout; empty when it holds the pinned snapshot."""

        problems: list[str] = []
        tag = self.tag_commit()
        if tag is None:
            problems.append(f"tag {self.config.tag} is not present in {self.checkout}")
        elif tag != self.commit:
            problems.append(f"tag {self.config.tag} points to {tag}, not {self.commit}")
        text = self.show_text("rust-toolchain.toml")
        if f'channel = "{self.config.rust}"' not in text:
            problems.append(f"rust-toolchain.toml at the commit does not pin {self.config.rust}")
        return problems

    def show(self, path: str) -> bytes:
        """The bytes of `path` at the pinned commit."""

        process = subprocess.run(  # nosec B607
            ["git", "-C", str(self.checkout), "show", f"{self.commit}:{path}"],
            capture_output=True,
            check=False,
        )
        if process.returncode != 0:
            raise SnapshotError(f"{path} does not exist at {self.commit[:7]}")
        return process.stdout

    def show_text(self, path: str) -> str:
        return self.show(path).decode("utf-8")

    def show_yaml(self, path: str) -> Any:
        return load_yaml_text(self.show(path))

    def list_files(self, prefix: str) -> list[str]:
        """Every file below `prefix` at the pinned commit, sorted."""

        out = self._git("ls-tree", "-r", "--name-only", self.commit, "--", prefix)
        return sorted(line for line in out.splitlines() if line)

    def dokploy_versions(self) -> list[DokployVersion]:
        data = self.show_yaml(self.config.versions_path)
        return [
            DokployVersion(
                version=str(entry["version"]),
                status=str(entry["status"]),
                image=str(entry["image"]),
                openapi=str(entry["openapi"]),
            )
            for entry in data["versions"]
        ]

    def export(self, destination: Path) -> Path:
        """A clean copy of the tree at the commit (no `.git`, no local files), for builds and the
        system's own scripts. An existing export is reused only if it carries the commit marker."""

        marker = destination / ".diac-export-commit"
        if marker.is_file() and marker.read_text().strip() == self.commit:
            return destination
        if destination.exists():
            raise SnapshotError(f"{destination} exists and is not an export of {self.commit[:7]}")
        destination.mkdir(parents=True)
        run(
            [
                "sh",
                "-c",
                f"git -C '{self.checkout}' archive {self.commit} | tar -x -C '{destination}'",
            ]
        )
        marker.write_text(self.commit + "\n")
        return destination

    def describe(self) -> dict[str, Any]:
        """The identity of the snapshot, for manifests."""

        return {
            "snapshot": self.config.snapshot,
            "system": self.config.name,
            "version": self.config.version,
            "commit": self.commit,
            "tag": self.config.tag,
            "tag_verified": self.tag_commit() == self.commit,
            "dokploy": [
                {"version": item.version, "image": item.image} for item in self.dokploy_versions()
            ],
        }
