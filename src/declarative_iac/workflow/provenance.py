"""`declarative-iac provenance`: the pinned snapshot, its binary and its Dokploy versions."""

from __future__ import annotations

import json

import typer

from declarative_iac.core.manifest import harness_revision, host_environment
from declarative_iac.domain.live.instance import SYSTEM_COMPOSE, compare_with_system
from declarative_iac.domain.provenance import BinaryProvider, Snapshot
from declarative_iac.domain.provenance.binary import BinaryError

app = typer.Typer(help="Show and verify the pinned inputs.", no_args_is_help=True)


@app.command("show")
def show() -> None:
    """Print the snapshot, the binary, the harness revision and the host."""

    snapshot = Snapshot.pinned()
    record: dict[str, object] = {
        "snapshot": snapshot.describe(),
        "harness": harness_revision(),
        "host": host_environment(),
    }
    try:
        record["binary"] = BinaryProvider(snapshot).resolve().describe()
    except BinaryError as error:
        record["binary"] = {"error": str(error)}
    typer.echo(json.dumps(record, indent=2, sort_keys=True))


@app.command("verify")
def verify(
    require_binary: bool = typer.Option(True, help="Fail when no binary of the snapshot is found."),
) -> None:
    """Check the checkout, the tag, the toolchain pin and the binary; exit 1 on any problem."""

    snapshot = Snapshot.pinned()
    problems = snapshot.verify()
    problems += [
        f"compose.yaml differs from the system's {SYSTEM_COMPOSE} at {path}"
        for path in compare_with_system(snapshot)
    ]
    if require_binary:
        try:
            binary = BinaryProvider(snapshot).resolve()
            typer.echo(f"binary  {binary.origin}  {binary.sha256}  {binary.path}")
        except BinaryError as error:
            problems.append(str(error))
    for problem in problems:
        typer.echo(f"problem: {problem}", err=True)
    if problems:
        raise typer.Exit(1)
    typer.echo(f"snapshot {snapshot.config.snapshot} at {snapshot.commit} verified")


@app.command("build-binary")
def build_binary(
    container: bool | None = typer.Option(
        None, help="Build in the pinned Rust container (default on Linux only)."
    ),
) -> None:
    """Build `dokploy` from a clean export of the pinned commit and print its hash."""

    snapshot = Snapshot.pinned()
    binary = BinaryProvider(snapshot).build(use_container=container)
    typer.echo(json.dumps(binary.describe(), indent=2, sort_keys=True))
