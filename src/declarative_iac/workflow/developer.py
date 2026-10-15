"""`declarative-iac developer`: run the system's own verification at the pinned commit."""

from __future__ import annotations

import typer

from declarative_iac.core.canonical import write_json
from declarative_iac.core.manifest import RunManifest
from declarative_iac.core.paths import cache_dir, results_dir
from declarative_iac.core.shell import version_of, which
from declarative_iac.domain.developer import runner
from declarative_iac.domain.provenance import Snapshot

app = typer.Typer(
    help="Developer evidence: the system's own tests at the snapshot.", no_args_is_help=True
)


@app.command("run")
def run_command(
    live: bool = typer.Option(True, help="Also run the live suites (needs Docker with Swarm)."),
    version: list[str] = typer.Option(None, help="Dokploy versions for the live suites."),
) -> None:
    """Run the workspace tests, the conformance suite, the ledger check and the live suites."""

    if which("cargo") is None:
        raise typer.BadParameter("cargo is required (rustup selects the pinned toolchain)")
    snapshot = Snapshot.pinned()
    source = snapshot.export(cache_dir() / "build" / snapshot.commit)
    versions = [v for v in snapshot.dokploy_versions() if not version or v.version in version]
    steps = runner.cargo_steps([(v.version, v.openapi) for v in snapshot.dokploy_versions()])
    if live:
        if which("docker") is None:
            raise typer.BadParameter("docker is required for the live suites; use --no-live")
        for v in versions:
            steps += runner.live_steps(v.version, v.image)
    out = results_dir() / "developer" / snapshot.config.snapshot
    out.mkdir(parents=True, exist_ok=True)
    manifest = RunManifest(
        experiment="developer",
        output_dir=out,
        snapshot=snapshot.config.snapshot,
        evidence="developer",
    )
    manifest.add_input("system_under_study", snapshot.describe())
    manifest.add_input(
        "toolchain",
        {"cargo": version_of(["cargo", "--version"]), "rustc": version_of(["rustc", "--version"])},
    )
    extra = {"DOKPLOY_FINGERPRINT_KEY": runner.fingerprint_key()}
    records = {}
    for step in steps:
        typer.echo(f"running  {step.id}")
        records[step.id] = runner.execute(step, source, out / "raw", extra)
        typer.echo(
            f"         exit {records[step.id]['exit_code']} "
            f"in {records[step.id]['duration_seconds']} s"
        )
    summary = write_json(
        out / "summary.json",
        {"steps": records, "all_passed": all(r["passed"] for r in records.values())},
    )
    manifest.finish([summary])
    typer.echo(f"wrote    {out}")
