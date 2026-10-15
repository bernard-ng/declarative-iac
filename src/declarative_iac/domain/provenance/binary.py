"""The release binary of the system under study."""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path

from declarative_iac.core.hashing import sha256_file
from declarative_iac.core.paths import cache_dir
from declarative_iac.core.shell import run, which
from declarative_iac.domain.provenance.snapshot import Snapshot


class BinaryError(RuntimeError):
    """No usable binary of the pinned snapshot."""


def platform_key() -> str:
    """`darwin-arm64`, `linux-x86_64`, ...: the key of the per-platform expected hashes."""

    machine = platform.machine().lower().replace("aarch64", "arm64").replace("amd64", "x86_64")
    return f"{platform.system().lower()}-{machine}"


@dataclass(frozen=True)
class ResolvedBinary:
    path: Path
    sha256: str
    platform: str
    origin: str  # "pinned" (hash matches the recorded one) or "rebuilt" (hash recorded here)
    version: str

    def describe(self) -> dict[str, str]:
        return {
            "path": self.path.as_posix(),
            "sha256": self.sha256,
            "platform": self.platform,
            "origin": self.origin,
            "version": self.version,
        }


class BinaryProvider:
    """Supplies the `dokploy` binary built from the pinned commit.

    Resolution order: `DIAC_SUT_BINARY`, then `.cache/bin/<platform>/dokploy`. A binary whose
    hash equals the recorded one for this platform is `pinned`. Any other binary is accepted only
    when it reports the snapshot's version, and is marked `rebuilt` with its own hash, which every
    manifest records. `build()` produces one from the pinned commit with the pinned toolchain.
    """

    def __init__(self, snapshot: Snapshot) -> None:
        self.snapshot = snapshot

    def _candidates(self) -> list[Path]:
        paths: list[Path] = []
        override = os.environ.get("DIAC_SUT_BINARY")
        if override:
            paths.append(Path(override).expanduser())
        paths.append(cache_dir() / "bin" / platform_key() / "dokploy")
        return paths

    def resolve(self) -> ResolvedBinary:
        for path in self._candidates():
            if path.is_file():
                return self.inspect(path)
        raise BinaryError(
            "no dokploy binary: set DIAC_SUT_BINARY to a binary built at "
            f"{self.snapshot.commit[:7]}, or run `declarative-iac provenance build-binary`"
        )

    def inspect(self, path: Path) -> ResolvedBinary:
        digest = sha256_file(path)
        version = run([str(path), "--version"], timeout=30).stdout.strip()
        expected_version = f"dokploy {self.snapshot.config.version}"
        if version != expected_version:
            raise BinaryError(f"{path} reports {version!r}, expected {expected_version!r}")
        key = platform_key()
        expected = self.snapshot.config.binary_sha256.get(key)
        origin = "pinned" if expected == digest else "rebuilt"
        if expected is not None and origin == "rebuilt":
            # Same platform, different bytes: still usable, but it must be visible.
            origin = "rebuilt-differs-from-recorded"
        return ResolvedBinary(path.resolve(), digest, key, origin, version)

    def build(self, *, use_container: bool | None = None) -> ResolvedBinary:
        """Build the binary from a clean export of the pinned commit.

        On Linux the build runs in the pinned Rust container, so the binary runs on the host. On
        other systems a container would produce a Linux binary the host cannot run, so the build
        uses the local `cargo`, which `rust-toolchain.toml` pins to the same channel.
        """

        if use_container is None:
            use_container = platform.system() == "Linux"

        source = self.snapshot.export(cache_dir() / "build" / self.snapshot.commit)
        target = cache_dir() / "bin" / platform_key()
        target.mkdir(parents=True, exist_ok=True)
        if use_container:
            if which("docker") is None:
                raise BinaryError("docker is required for a containerised build")
            image = self.snapshot.config.toolchain_image
            if self.snapshot.config.toolchain_digest:
                image = f"{image.split(':')[0]}@{self.snapshot.config.toolchain_digest}"
            run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{source}:/src",
                    "-w",
                    "/src",
                    "-e",
                    "RUSTFLAGS=--remap-path-prefix=/src=.",
                    image,
                    "sh",
                    "-c",
                    self.snapshot.config.binary_build,
                ]
            )
        else:
            if which("cargo") is None:
                raise BinaryError("cargo is required for a local build")
            run(
                ["sh", "-c", self.snapshot.config.binary_build],
                cwd=source,
                env={"RUSTFLAGS": f"--remap-path-prefix={source}=."},
            )
        built = source / self.snapshot.config.binary_path
        shutil.copy2(built, target / "dokploy")
        return self.inspect(target / "dokploy")
