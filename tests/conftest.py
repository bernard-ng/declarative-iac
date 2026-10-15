from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def sut_repo(tmp_path: Path) -> tuple[Path, str]:
    """A tiny repository standing in for the system under study, with a tag."""

    repo = tmp_path / "sut"
    repo.mkdir()
    git(repo, "init", "--quiet")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "test")
    (repo / "rust-toolchain.toml").write_text('[toolchain]\nchannel = "1.97.1"\n')
    (repo / "specs").mkdir()
    (repo / "specs" / "versions.yaml").write_text(
        "versions:\n"
        '  - version: "0.30.6"\n'
        "    status: supported\n"
        "    image: dokploy/dokploy:v0.30.6@sha256:aa\n"
        "    openapi: openapi/dokploy.json\n"
    )
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "snapshot")
    git(repo, "tag", "eval-B1")
    commit = git(repo, "rev-parse", "HEAD")
    (repo / "rust-toolchain.toml").write_text("changed in the working tree\n")
    return repo, commit
