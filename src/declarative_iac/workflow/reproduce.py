"""`declarative-iac reproduce --level N`: the reproduction levels of REPRODUCING.md.

A level is nothing more than the listed commands, run in order; `--dry-run` prints them. Each
command is the same one a reviewer could type, so the level adds no hidden step.
"""

from __future__ import annotations

import subprocess  # nosec B404 - runs this package's own CLI
import sys

import typer

from declarative_iac.core.paths import repository_root

app = typer.Typer(help="Run a reproduction level.", invoke_without_command=True)

LIVE = ("L1", "L2", "L3", "L4")

LEVELS: dict[int, list[list[str]]] = {
    # Level 0: check the committed (or archived) results against the paper. No Docker, minutes.
    0: [["claims", "verify"], ["claims", "check-paper"]],
    # Level 1: recompute every static result and the developer evidence that needs no instance.
    1: [
        ["provenance", "verify"],
        ["static", "run", "--all"],
        ["developer", "run", "--no-live"],
        ["report"],
        ["claims", "verify"],
        ["claims", "check-paper"],
    ],
    # Level 2: everything, including the live experiments (Docker with Swarm, hours).
    2: [
        ["provenance", "verify"],
        ["static", "run", "--all"],
        ["developer", "run"],
        *[["live", "run", name] for name in LIVE],
        *[["live", "summarise", name] for name in LIVE],
        ["report"],
        ["claims", "verify", "--strict"],
        ["claims", "check-paper"],
    ],
}


def commands(level: int) -> list[list[str]]:
    if level not in LEVELS:
        raise typer.BadParameter(f"level is one of {sorted(LEVELS)}")
    return LEVELS[level]


@app.callback()
def reproduce(
    level: int = typer.Option(0, "--level", help="0: verify, 1: static, 2: live."),
    dry_run: bool = typer.Option(False, help="Print the commands without running them."),
) -> None:
    for args in commands(level):
        typer.echo("$ declarative-iac " + " ".join(args))
        if dry_run:
            continue
        completed = subprocess.run(  # nosec B603 - fixed argument lists, no shell
            [sys.executable, "-m", "declarative_iac", *args], cwd=repository_root(), check=False
        )
        if completed.returncode != 0:
            typer.echo(f"level {level} stopped: `{' '.join(args)}` exited {completed.returncode}")
            raise typer.Exit(completed.returncode)
    typer.echo(f"level {level} complete")
