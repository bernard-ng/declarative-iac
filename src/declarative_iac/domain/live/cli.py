"""The system's CLI as a black box: an isolated environment, captured output, timed runs."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from declarative_iac.core.shell import run

EXIT_NO_CHANGES, EXIT_ERROR, EXIT_CHANGES = 0, 1, 2


@dataclass(frozen=True)
class CliResult:
    args: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    seconds: float

    def record(self) -> dict[str, object]:
        return {"args": list(self.args), "exit_code": self.exit_code, "seconds": self.seconds}


class CliRunner:
    """Runs `dokploy` in one workspace with a minimal, explicit environment.

    The process sees only PATH, a private HOME, the target URL and key, and a fingerprint key fixed
    for the run; nothing from the caller's environment or credential store leaks in.
    """

    def __init__(
        self,
        binary: Path,
        workspace: Path,
        url: str,
        api_key: str,
        fingerprint_key: str,
        home: Path,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self.binary = binary
        self.workspace = workspace
        home.mkdir(parents=True, exist_ok=True)
        self.env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(home),
            "DOKPLOY_URL": url,
            "DOKPLOY_API_KEY": api_key,
            "DOKPLOY_FINGERPRINT_KEY": fingerprint_key,
            "NO_COLOR": "1",
            **(extra_env or {}),
        }
        self.history: list[CliResult] = []

    def __call__(self, *args: str, timeout: float = 1800) -> CliResult:
        started = time.monotonic()
        completed = run(
            [str(self.binary), *args],
            cwd=self.workspace,
            env=self.env,
            inherit_env=False,
            check=False,
            timeout=timeout,
        )
        result = CliResult(
            tuple(args),
            completed.returncode,
            completed.stdout,
            completed.stderr,
            round(time.monotonic() - started, 3),
        )
        self.history.append(result)
        return result

    def plan(self) -> CliResult:
        return self("plan", "--detailed-exitcode", "--json")

    def apply(self, *extra: str) -> CliResult:
        return self("apply", "--auto-approve", *extra)

    def recover(self, document: str) -> CliResult:
        return self("recover", "--file", document, "--auto-approve")
