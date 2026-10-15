"""Running external programs with captured, bounded output."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Completed:
    """The outcome of one external command."""

    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class CommandError(RuntimeError):
    def __init__(self, completed: Completed) -> None:
        super().__init__(
            f"command failed ({completed.returncode}): {' '.join(completed.args)}\n"
            f"{completed.stderr.strip()[-2000:]}"
        )
        self.completed = completed


def run(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    inherit_env: bool = True,
    timeout: float | None = None,
    check: bool = True,
    stdin: str | None = None,
) -> Completed:
    """Run a program without a shell; `env` is added to (or, with `inherit_env=False`,
    replaces) the environment."""

    environment = dict(os.environ) if inherit_env else {"PATH": os.environ.get("PATH", "")}
    if env:
        environment.update(env)
    process = subprocess.run(
        list(args),
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
        input=stdin,
        check=False,
    )
    completed = Completed(tuple(args), process.returncode, process.stdout, process.stderr)
    if check and not completed.ok:
        raise CommandError(completed)
    return completed


def which(program: str) -> str | None:
    return shutil.which(program)


def version_of(args: Sequence[str]) -> str | None:
    """The first line a version command prints, or None when the program is absent."""

    if which(args[0]) is None:
        return None
    try:
        completed = run(args, check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (completed.stdout or completed.stderr).strip()
    return text.splitlines()[0] if text else None
