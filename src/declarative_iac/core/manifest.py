"""Run manifests: what produced a set of outputs, and checks that the outputs are unchanged.

Every experiment writes its outputs into one directory together with `manifest.json`. The
manifest records the inputs, the tools, the host, the exact command, the seed, the timings and the
SHA-256 of every output file. Timings and host details legitimately differ between reruns; the
output hashes must not, for deterministic experiments.
"""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from declarative_iac import __version__
from declarative_iac.core.canonical import read_json, write_json
from declarative_iac.core.hashing import sha256_file
from declarative_iac.core.paths import relative, repository_root
from declarative_iac.core.shell import run, version_of

MANIFEST_NAME = "manifest.json"
MANIFEST_FORMAT = 1


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _memory_bytes() -> int | None:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return None


def harness_revision() -> dict[str, Any]:
    """The research repository's commit and whether the working tree differs from it."""

    root = repository_root()
    head = run(["git", "-C", str(root), "rev-parse", "HEAD"], check=False)
    status = run(["git", "-C", str(root), "status", "--porcelain"], check=False)
    lock = root / "uv.lock"
    return {
        "commit": head.stdout.strip() if head.ok else None,
        "dirty": bool(status.stdout.strip()) if status.ok else None,
        "uv_lock_sha256": sha256_file(lock) if lock.is_file() else None,
        "harness_version": __version__,
    }


def host_environment() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "memory_bytes": _memory_bytes(),
        "git": version_of(["git", "--version"]),
        "uv": version_of(["uv", "--version"]),
        "docker": version_of(["docker", "version", "--format", "{{.Server.Version}}"]),
    }


@dataclass
class RunManifest:
    """The record of one experiment run, written next to its outputs."""

    experiment: str
    output_dir: Path
    snapshot: str
    command: list[str] = field(default_factory=lambda: list(sys.argv))
    seed: int | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    evidence: str = "independent"
    started_at: str = field(default_factory=_now)

    def add_input(self, name: str, value: Any) -> None:
        self.inputs[name] = value

    def finish(self, outputs: list[Path]) -> Path:
        """Hash every output and write the manifest; returns its path."""

        hashed: dict[str, str] = {}
        for path in sorted(outputs, key=lambda item: item.as_posix()):
            if not path.is_file():
                raise FileNotFoundError(path)
            hashed[path.resolve().relative_to(self.output_dir.resolve()).as_posix()] = sha256_file(
                path
            )
        record = {
            "format": MANIFEST_FORMAT,
            "experiment": self.experiment,
            "evidence": self.evidence,
            "snapshot": self.snapshot,
            "command": self.command,
            "seed": self.seed,
            "parameters": self.parameters,
            "inputs": self.inputs,
            "harness": harness_revision(),
            "host": host_environment(),
            "started_at": self.started_at,
            "finished_at": _now(),
            "output_dir": relative(self.output_dir),
            "outputs": hashed,
        }
        return write_json(self.output_dir / MANIFEST_NAME, record)


def verify_manifest(manifest_path: Path) -> list[str]:
    """Problems found when the outputs a manifest lists are compared with the files on disk."""

    problems: list[str] = []
    record = read_json(manifest_path)
    base = manifest_path.parent
    for name, expected in sorted(record.get("outputs", {}).items()):
        path = base / name
        if not path.is_file():
            problems.append(f"{relative(path)}: missing")
        elif sha256_file(path) != expected:
            problems.append(f"{relative(path)}: content differs from its manifest")
    return problems
