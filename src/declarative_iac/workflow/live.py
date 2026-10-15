"""`declarative-iac live`: the pre-registered live experiments L1-L4 (paper Section 9).

Each run starts a fresh Dokploy with the system's own integration stack, puts the fault proxy in
front of it, and drives the pinned binary through the procedure of PREREGISTRATION.md §4.1.
`plan` lists the runs without starting anything; `summarise` turns results into the hypothesis
table. Runs need Docker with Swarm and are never executed in CI.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

import typer

from declarative_iac.core.canonical import read_json, read_yaml, write_json
from declarative_iac.core.hashing import sha256_bytes
from declarative_iac.core.manifest import RunManifest
from declarative_iac.core.paths import config_dir, relative, results_dir
from declarative_iac.domain.live import experiment
from declarative_iac.domain.live.instance import (
    DEFAULT_PORT,
    DockerUnavailable,
    Instance,
    InstanceFailed,
    InstanceProvider,
    external_instance,
)
from declarative_iac.domain.live.proxy import FaultPlan
from declarative_iac.domain.live.summary import CHECKS, summarise
from declarative_iac.domain.provenance import BinaryProvider, Snapshot
from declarative_iac.domain.scenarios import load_families
from declarative_iac.domain.scenarios.model import Scenario

app = typer.Typer(help="Run the pre-registered live experiments.", no_args_is_help=True)

EXPERIMENTS = ("L1", "L2", "L3", "L4")
REPETITIONS = {"L1": 5, "L2": 5, "L3": 3, "L4": 5}
L4_SEED = ("realistic-webapp", "realistic-compose", "unit-application-children")
FROZEN = ("scenarios", "observer.yaml", "drift.yaml", "faults.yaml")


@dataclass(frozen=True)
class Cell:
    experiment: str
    name: str
    scenario: str
    operator: str | None = None
    fault: tuple[str, str] | None = None


def scenarios() -> dict[str, Scenario]:
    families = load_families(config_dir() / "scenarios")
    return {s.id: s for f in families.values() for s in f.scenarios.values()}


def cells(name: str) -> list[Cell]:
    if name == "L1":
        return [Cell("L1", s, s) for s in scenarios()]
    if name == "L2":
        operators = read_yaml(config_dir() / "drift.yaml")["operators"]
        return [
            Cell("L2", o, body["start"]["scenario"], operator=o) for o, body in operators.items()
        ]
    if name == "L3":
        plan = read_yaml(config_dir() / "faults.yaml")
        return [
            Cell("L3", f"{s}--{k}--{o}", s, fault=(k, o))
            for s in plan["scenarios"]
            for k in plan["kinds"]
            for o in plan["ordinals"]
        ]
    if name == "L4":
        return [Cell("L4", "seed", "+".join(L4_SEED))]
    raise typer.BadParameter(f"unknown experiment {name}; choose from {', '.join(EXPERIMENTS)}")


def frozen_inputs() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in FROZEN:
        path = config_dir() / name
        files = sorted(path.glob("*.yaml")) if path.is_dir() else [path]
        for file in files:
            out[relative(file)] = sha256_bytes(file.read_bytes())
    prereg = results_dir().parent / "evaluation" / "PREREGISTRATION.md"
    out[relative(prereg)] = sha256_bytes(prereg.read_bytes())
    return out


def run_directory(base: Path, cell: Cell, version: str, repetition: int) -> Path:
    return base / cell.experiment / "B1" / version / cell.name / f"r{repetition}"


def execute(
    cell: Cell,
    instance: Instance,
    binary: Path,
    directory: Path,
    catalog: dict[str, Scenario],
    restart: Callable[[], Instance] | None = None,
) -> dict[str, Any]:
    drift = read_yaml(config_dir() / "drift.yaml")["operators"]
    writes = {d["write"]["operation"] for d in drift.values()}
    writes |= {seed.operation for s in catalog.values() for st in s.steps for seed in st.seed}
    if cell.experiment == "L1":
        with experiment.open_run(directory, instance, binary, writes) as run:
            result = experiment.run_l1(run, catalog[cell.scenario])
            run.finish(result)
            return result
    if cell.experiment == "L2":
        if cell.operator is None:
            raise RuntimeError("cell.operator is required here")
        operator = {"id": cell.operator, **drift[cell.operator]}
        with experiment.open_run(directory, instance, binary, writes) as run:
            result = experiment.run_l2(run, catalog[cell.scenario], operator)
            run.finish(result)
            return result
    if cell.experiment == "L3":
        if cell.fault is None:
            raise RuntimeError("cell.fault is required here")
        reference_path = directory.parent.parent / f"reference--{cell.scenario}" / "reference.json"
        reference = read_json(reference_path)
        ordinal = reference["ordinals"][cell.fault[1]]
        fault = FaultPlan(cell.fault[0], ordinal)
        with experiment.open_run(directory, instance, binary, writes, fault) as run:
            result = experiment.run_l3(run, catalog[cell.scenario], reference["final"])
            result["ordinal"] = ordinal
            run.finish(result)
            return result
    seed = experiment.merge_steps([catalog[s].steps[0] for s in L4_SEED])
    with experiment.open_run(directory, instance, binary, writes) as run:
        result = experiment.run_l4_import(run, seed)
        secrets = dict(run.secrets)
        run.finish(result)
    if restart is None:
        raise RuntimeError("L4 needs a second fresh instance")
    fresh = restart()
    with experiment.open_run(directory / "rebuild", fresh, binary, writes) as run:
        rebuild = experiment.run_l4_rebuild(run, directory / "import-1", secrets)
        run.finish(rebuild)
    result["rebuild"] = rebuild
    write_json(directory / "result.json", result)
    return result


def l3_reference(
    scenario: Scenario, instance: Instance, binary: Path, directory: Path
) -> dict[str, Any]:
    with experiment.open_run(directory, instance, binary, set()) as run:
        reference = experiment.run_l3_reference(run, scenario)
        reference["ordinals"] = experiment.mutation_ordinals(reference["mutations"])
        run.finish({k: v for k, v in reference.items() if k != "final"})
    write_json(directory / "reference.json", reference)
    return reference


class Instances:
    """A fresh instance per run, or the one external instance (marked as such)."""

    def __init__(self, snapshot: Snapshot) -> None:
        self.external = external_instance()
        self.provider = None if self.external else InstanceProvider(snapshot)

    def start(self, version: Any) -> Instance:
        if self.external:
            return self.external
        if self.provider is None:
            raise RuntimeError("self.provider is required here")
        return self.provider.start(version)

    def stop(self, version: Any) -> None:
        if self.provider:
            self.provider.stop(version)

    def restart(self, version: Any) -> Instance:
        if self.external:
            raise RuntimeError("L4 needs two fresh instances; unset DIAC_DOKPLOY_URL")
        self.stop(version)
        return self.start(version)


@app.command("plan")
def plan_command(
    experiments: list[str] = typer.Argument(None, help="L1 L2 L3 L4 (default: all)."),
) -> None:
    """List the cells and run counts without starting anything."""

    snapshot = Snapshot.pinned()
    versions = [v.version for v in snapshot.dokploy_versions()]
    total = 0
    for name in experiments or EXPERIMENTS:
        selected = cells(name)
        runs = len(selected) * len(versions) * REPETITIONS[name]
        total += runs
        typer.echo(
            f"{name}: {len(selected)} cells x {len(versions)} versions x "
            f"{REPETITIONS[name]} repetitions = {runs} runs"
        )
    typer.echo(f"total: {total} runs")


@app.command("run")
def run_command(
    name: str = typer.Argument(..., help="L1, L2, L3 or L4."),
    version: list[str] = typer.Option(None, "--version", help="Dokploy versions (default: all)."),
    cell: list[str] = typer.Option(None, "--cell", help="Cells (default: all)."),
    repetitions: int = typer.Option(0, help="Override the pre-registered count (pilot only)."),
    pilot: bool = typer.Option(False, help="Write under results/live/pilot; never confirmatory."),
    dry_run: bool = typer.Option(False, help="Print the runs without executing them."),
) -> None:
    """Execute runs; each writes result.json, raw/ and manifest.json."""

    if repetitions and not pilot:
        raise typer.BadParameter("--repetitions changes the design; use it only with --pilot")
    snapshot = Snapshot.pinned()
    problems = snapshot.verify()
    if problems:
        raise typer.BadParameter("the snapshot does not match its pin: " + "; ".join(problems))
    selected = [c for c in cells(name) if not cell or c.name in cell]
    known = {v.version: v for v in snapshot.dokploy_versions()}
    chosen = [known[v] for v in (version or list(known))]
    reps = repetitions or REPETITIONS[name]
    base = results_dir() / "live" / ("pilot" if pilot else "")
    plan = [(c, v, r) for v in chosen for c in selected for r in range(1, reps + 1)]
    if dry_run:
        for c, v, r in plan:
            typer.echo(relative(run_directory(base, c, v.version, r)))
        typer.echo(f"{len(plan)} runs")
        return
    binary = BinaryProvider(snapshot).resolve()
    instances = Instances(snapshot)
    catalog = scenarios()
    inputs = frozen_inputs()
    if name == "L3":
        for v in chosen:
            for scenario_id in sorted({c.scenario for c in selected}):
                directory = base / "L3" / "B1" / v.version / f"reference--{scenario_id}"
                if (directory / "reference.json").exists():
                    continue
                instance = instances.start(v)
                try:
                    l3_reference(catalog[scenario_id], instance, binary.path, directory)
                finally:
                    instances.stop(v)
    for c, v, r in plan:
        directory = run_directory(base, c, v.version, r)
        if (directory / "manifest.json").exists():
            typer.echo(f"done     {relative(directory)}")
            continue
        manifest = RunManifest(
            f"{name}/{c.name}",
            directory,
            snapshot.config.snapshot,
            parameters={
                "cell": c.name,
                "version": v.version,
                "repetition": r,
                "pilot": pilot,
                "external_instance": instances.external is not None,
            },
        )
        manifest.add_input("binary", binary.describe())
        manifest.add_input("frozen", inputs)
        instance = instances.start(v)
        try:
            manifest.add_input("instance", instance.describe())
            execute(c, instance, binary.path, directory, catalog, partial(instances.restart, v))
        finally:
            instances.stop(v)
        # raw/ is archived, not committed: its checksums are committed instead (raw-index.json).
        index = {
            p.relative_to(directory).as_posix(): sha256_bytes(p.read_bytes())
            for raw in sorted(directory.rglob("raw"))
            for p in sorted(raw.rglob("*"))
            if p.is_file()
        }
        write_json(directory / "raw-index.json", index)
        manifest.finish([directory / "result.json", directory / "raw-index.json"])
        typer.echo(f"wrote    {relative(directory)}")


def _version(snapshot: Snapshot, requested: str | None) -> Any:
    known = {v.version: v for v in snapshot.dokploy_versions()}
    if requested is None:
        return next(iter(known.values()))
    if requested not in known:
        raise typer.BadParameter(f"{requested} is not a supported version: {', '.join(known)}")
    return known[requested]


def _start(provider: InstanceProvider, version: Any) -> Instance:
    try:
        return provider.start(version)
    except (DockerUnavailable, InstanceFailed) as error:
        typer.echo(f"error: {error}", err=True)
        if isinstance(error, DockerUnavailable):
            typer.echo(
                "Live instances need a local Docker daemon with Swarm (REPRODUCING.md).", err=True
            )
        else:
            typer.echo("The stack was removed again; nothing is left running.", err=True)
        raise typer.Exit(2) from error


@app.command("up")
def up_command(
    version: str = typer.Option(None, help="Dokploy version (default: the first supported)."),
    port: int = typer.Option(DEFAULT_PORT, help="Local port of the instance."),
) -> None:
    """Start a fresh local Dokploy from compose.yaml and leave it running."""

    snapshot = Snapshot.pinned()
    chosen = _version(snapshot, version)
    provider = InstanceProvider(snapshot, port)
    instance = _start(provider, chosen)
    typer.echo(f"Dokploy {instance.version} is ready at {instance.base_url}")
    typer.echo(f"API key: {relative(provider.runtime / 'state' / 'api-key')}")
    typer.echo("Stop it with `declarative-iac live down`.")


@app.command("down")
def down_command(port: int = typer.Option(DEFAULT_PORT)) -> None:
    """Remove the local instance, its containers and its volumes."""

    InstanceProvider(Snapshot.pinned(), port).stop()
    typer.echo("removed  the declarative-iac-eval stack and its volumes")


@app.command("smoke")
def smoke_command(
    version: str = typer.Option(None, help="Dokploy version (default: the first supported)."),
    scenario: str = typer.Option("unit-tag", help="The L1 scenario to run once."),
    keep: bool = typer.Option(False, help="Leave the instance running afterwards."),
) -> None:
    """One L1 run of one scenario on a fresh instance, to check the whole chain end to end.

    Written under results/live/pilot/smoke/; never part of the confirmatory results.
    """

    snapshot = Snapshot.pinned()
    chosen = _version(snapshot, version)
    binary = BinaryProvider(snapshot).resolve()
    catalog = scenarios()
    if scenario not in catalog:
        raise typer.BadParameter(f"unknown scenario {scenario}")
    provider = InstanceProvider(snapshot)
    directory = results_dir() / "live" / "pilot" / "smoke" / chosen.version / scenario
    instance = _start(provider, chosen)
    try:
        result = execute(Cell("L1", scenario, scenario), instance, binary.path, directory, catalog)
    finally:
        if not keep:
            provider.stop(chosen)
    verdicts = {name: check(result) for name, check in CHECKS.items()}
    for name, verdict in verdicts.items():
        if verdict is not None:
            typer.echo(f"{name:13s} {'holds' if verdict else 'VIOLATED'}")
    typer.echo(f"evidence {relative(directory)}")
    if not all(v for v in verdicts.values() if v is not None):
        raise typer.Exit(1)


@app.command("summarise")
def summarise_command(
    name: str = typer.Argument(..., help="L1, L2, L3 or L4."),
    pilot: bool = typer.Option(False),
) -> None:
    """Aggregate the runs of one experiment into summary.json (the hypothesis table)."""

    root = results_dir() / "live" / ("pilot" if pilot else "") / name / "B1"
    if not root.exists():
        raise typer.BadParameter(f"no runs under {relative(root)}")
    path = write_json(root / "summary.json", summarise(root))
    typer.echo(f"wrote    {relative(path)}")
