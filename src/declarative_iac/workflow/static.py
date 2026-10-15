"""`declarative-iac static`: the deterministic experiments over the pinned snapshot.

- S1-census (Section 3.2, Table 2): operations, roles by name, operations the specs use.
- S2-specifications (Sections 3.2, 3.3, 5.5, Tables 3 and 7): field, kind, class and
  construct counts.
- S3-ledger (Section 7.1): the coverage ledger reported by the pinned binary.
- S4-fixtures (Section 7.1): recorded responses per Dokploy version.
- S5-invariants (Section 4): the invariants the system documents in ARCHITECTURE.md.
- S7-kind-references (Section 10): the places where the engine names a kind.
- S6-scenarios (Section 9.1): every pre-registered scenario document, validated offline by the
  pinned binary, and the kinds and mismatch classes the scenario set exercises.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import typer

from declarative_iac.core.canonical import read_yaml, write_csv, write_json
from declarative_iac.core.hashing import sha256_bytes
from declarative_iac.core.manifest import RunManifest
from declarative_iac.core.paths import config_dir, results_dir
from declarative_iac.core.shell import run
from declarative_iac.domain.live.observer import load_collections
from declarative_iac.domain.provenance import BinaryProvider, Snapshot
from declarative_iac.domain.scenarios import load_families, materialise
from declarative_iac.domain.scenarios.coverage import declared_kinds
from declarative_iac.domain.static import (
    census,
    classes,
    constructs,
    fixtures,
    inventory,
    ledger,
    references,
)
from declarative_iac.domain.static.specs import SpecCatalog
from declarative_iac.workflow.live import EXPERIMENTS as LIVE_EXPERIMENTS
from declarative_iac.workflow.live import L4_SEED, REPETITIONS, cells

app = typer.Typer(
    help="Recompute the structural results from the pinned snapshot.", no_args_is_help=True
)


def load_catalog(snapshot: Snapshot) -> tuple[SpecCatalog, dict[str, str]]:
    root = snapshot.config.specs_path
    paths = [p for p in snapshot.list_files(root) if p.endswith(".yaml") and p.count("/") == 2]
    files = {path: snapshot.show(path) for path in paths}
    digests = {path: sha256_bytes(data) for path, data in files.items()}
    return SpecCatalog.from_files(files), digests


def known_operations(snapshot: Snapshot) -> tuple[dict[str, list[census.Operation]], dict]:
    by_version: dict[str, list[census.Operation]] = {}
    digests: dict[str, str] = {}
    for version in snapshot.dokploy_versions():
        data = snapshot.show(version.openapi)
        digests[version.openapi] = sha256_bytes(data)
        by_version[version.version] = census.operations(json.loads(data))
    return by_version, digests


def s1_census(snapshot: Snapshot, out: Path, manifest: RunManifest) -> list[Path]:
    by_version, digests = known_operations(snapshot)
    catalog, spec_digests = load_catalog(snapshot)
    manifest.add_input("openapi_sha256", digests)
    manifest.add_input(
        "specs_sha256", sha256_bytes(json.dumps(spec_digests, sort_keys=True).encode())
    )
    outputs: list[Path] = []
    summary: dict[str, object] = {}
    for version, ops in by_version.items():
        names = {op.name for op in ops}
        used = set().union(*(spec.operations_named(names) for spec in catalog))
        summary[version] = census.summarise(ops, used)
        outputs.append(
            write_csv(
                out / f"operations-{version}.csv",
                (
                    {
                        "operation": op.name,
                        "router": op.router,
                        "procedure": op.procedure,
                        "method": op.method,
                        "role": op.role,
                        "response_empty_object": op.response_empty,
                        "used_by_specs": op.name in used,
                    }
                    for op in ops
                ),
                [
                    "operation",
                    "router",
                    "procedure",
                    "method",
                    "role",
                    "response_empty_object",
                    "used_by_specs",
                ],
            )
        )
    names_per_version = {v: sorted(op.name for op in ops) for v, ops in by_version.items()}
    first = next(iter(names_per_version.values()))
    summary["versions_have_identical_operations"] = all(
        names == first for names in names_per_version.values()
    )
    outputs.append(write_json(out / "summary.json", summary))
    return outputs


def s2_specifications(snapshot: Snapshot, out: Path, manifest: RunManifest) -> list[Path]:
    catalog, spec_digests = load_catalog(snapshot)
    manifest.add_input("specs_sha256", spec_digests)
    by_version, _ = known_operations(snapshot)
    names = {op.name for op in next(iter(by_version.values()))}
    kinds = inventory.kind_rows(catalog, names)
    construct_rows = constructs.construct_counts(catalog)
    return [
        write_json(out / "summary.json", inventory.summarise(catalog, names)),
        write_json(out / "classes.json", classes.class_counts(catalog)),
        write_json(out / "constructs.json", {row["construct"]: row for row in construct_rows}),
        write_csv(out / "kinds.csv", kinds, list(kinds[0].keys())),
        write_csv(
            out / "fields.csv",
            inventory.field_rows(catalog),
            [
                "kind",
                "path",
                "top_level",
                "type",
                "mutability",
                "class",
                "nullable",
                "needs_deploy",
            ],
        ),
        write_csv(
            out / "constructs.csv",
            construct_rows,
            ["construct", "mismatch", "label", "count", "kinds"],
        ),
    ]


def s3_ledger(snapshot: Snapshot, out: Path, manifest: RunManifest) -> list[Path]:
    binary = BinaryProvider(snapshot).resolve()
    manifest.add_input("binary", binary.describe())
    report = run([str(binary.path), "coverage"], cwd=out, timeout=120).stdout
    rows = ledger.parse_coverage(report)
    (out / "coverage.tsv").write_text(report)
    return [
        out / "coverage.tsv",
        write_csv(out / "ledger.csv", rows, ["kind", "coverage", *ledger.COLUMNS]),
        write_json(out / "summary.json", ledger.totals(rows)),
    ]


def s4_fixtures(snapshot: Snapshot, out: Path, manifest: RunManifest) -> list[Path]:
    root = snapshot.config.fixtures_path
    files = snapshot.list_files(root)
    return [
        write_json(
            out / "summary.json",
            {
                "files_per_version": fixtures.count_by_version(files, root),
                "files": len(files),
            },
        )
    ]


def s5_invariants(snapshot: Snapshot, out: Path, manifest: RunManifest) -> list[Path]:
    text = snapshot.show_text("ARCHITECTURE.md")
    manifest.add_input("ARCHITECTURE.md_sha256", sha256_bytes(text.encode()))
    section = text.split("## Invariants", 1)[1]
    numbers = [int(m.group(1)) for m in re.finditer(r"^(\d+)\. ", section, re.MULTILINE)]
    return [
        write_json(
            out / "summary.json",
            {
                "invariants": len(numbers),
                "numbered_consecutively": numbers == list(range(1, len(numbers) + 1)),
            },
        )
    ]


# Documents the validator must reject, so a run where every scenario "passes" cannot be explained
# by a validator that accepts anything (for example, one that never found the file).
NEGATIVE_CONTROLS: dict[str, tuple[str, str]] = {
    "unknown-field": (
        'version: 2\nsettings:\n  tags:\n    probe: { colour: "#336699" }\n',
        "DOKDOC004",
    ),
    "literal-secret": (
        "version: 2\nsettings:\n  registries:\n    r: { type: cloud, url: x, username: u,"
        " password: plain }\n",
        "DOKDOC008",
    ),
}


def _validate(binary: Path, workspace: Path, document: str) -> tuple[bool, list[str]]:
    result = run(
        [str(binary), "validate", "--file", document],
        cwd=workspace,
        env={"PATH": "/usr/bin:/bin", "HOME": str(workspace), "NO_COLOR": "1"},
        inherit_env=False,
        check=False,
        timeout=60,
    )
    if "cannot read" in result.stderr:
        raise RuntimeError(f"validate could not read {document}: {result.stderr.strip()}")
    return result.returncode == 0, sorted(set(re.findall(r"DOKDOC\d{3}", result.stderr)))


def live_design(versions: int) -> dict[str, dict[str, int]]:
    """Cells, repetitions and runs of each pre-registered live experiment."""

    design = {}
    for name in LIVE_EXPERIMENTS:
        count = len(cells(name))
        design[name] = {
            "cells_per_version": count,
            "repetitions": REPETITIONS[name],
            "runs": count * versions * REPETITIONS[name],
        }
    design["total"] = {"runs": sum(d["runs"] for d in design.values())}
    return design


def _recorded_names(snapshot: Snapshot) -> set[str]:
    """Every object key in every recorded response of the first Dokploy version."""

    names: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            names.update(str(k) for k in node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    version = snapshot.dokploy_versions()[0]
    root = f"{snapshot.config.fixtures_path}/v{version.version}"
    for path in snapshot.list_files(root):
        if not path.endswith(".json"):
            continue
        data = snapshot.show(path)
        if not data.strip():
            continue  # a recorded empty body
        try:
            walk(json.loads(data))
        except json.JSONDecodeError:
            continue  # a recorded non-JSON body (for example, plain text)
    return names


def s6_scenarios(snapshot: Snapshot, out: Path, manifest: RunManifest) -> list[Path]:
    import tempfile

    import yaml

    binary = BinaryProvider(snapshot).resolve()
    manifest.add_input("binary", binary.describe())
    directory = config_dir() / "scenarios"
    manifest.add_input(
        "scenarios_sha256",
        {p.name: sha256_bytes(p.read_bytes()) for p in sorted(directory.glob("*.yaml"))},
    )
    catalog, _ = load_catalog(snapshot)
    by_kind = classes.classify(catalog)
    families = load_families(directory)
    rows: list[dict[str, object]] = []
    exercised: dict[str, set[str]] = {}
    for family in families.values():
        for scenario in family.scenarios.values():
            declared: set[str] = set()
            for index, step in enumerate(scenario.steps, start=1):
                with tempfile.TemporaryDirectory() as tmp:
                    workspace = Path(tmp)
                    for document in materialise(step, workspace):
                        valid, codes = _validate(binary.path, workspace, document)
                        text = (workspace / document).read_text()
                        kinds = declared_kinds(yaml.safe_load(text), catalog)
                        declared |= kinds
                        rows.append(
                            {
                                "family": family.name,
                                "scenario": scenario.id,
                                "step": index,
                                "document": document,
                                "valid": valid,
                                "diagnostics": " ".join(codes),
                                "kinds": " ".join(sorted(kinds)),
                                "sha256": sha256_bytes(text.encode()),
                            }
                        )
            for kind in declared:
                exercised.setdefault(kind, set()).add(scenario.id)
            undeclared = sorted(set(scenario.covers) - declared)
            if undeclared:
                raise typer.BadParameter(f"{scenario.id}: covers {undeclared} but declares none")
    kinds_rows = [
        {
            "kind": spec.kind,
            "scope": spec.scope,
            "classes": " ".join(by_kind[spec.kind]),
            "scenarios": len(exercised.get(spec.kind, ())),
        }
        for spec in catalog
    ]
    class_rows = []
    for mismatch in classes.CLASSES:
        members = [k for k, ids in by_kind.items() if mismatch.id in ids]
        covered = [k for k in members if k in exercised]
        class_rows.append(
            {
                "class": mismatch.id,
                "kinds": len(members),
                "exercised": len(covered),
                "missing": " ".join(sorted(set(members) - set(covered))),
            }
        )
    controls: dict[str, dict[str, object]] = {}
    failed: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, (text, code) in NEGATIVE_CONTROLS.items():
            (Path(tmp) / f"{name}.yaml").write_text(text)
            valid, codes = _validate(binary.path, Path(tmp), f"{name}.yaml")
            controls[name] = {"rejected": not valid, "expected": code, "codes": codes}
            if valid or code not in codes:
                failed.append(name)
    if failed:
        raise RuntimeError(f"a negative control was not rejected as expected: {controls}")
    recorded = _recorded_names(snapshot)
    observed = load_collections(config_dir() / "observer.yaml")
    manifest.add_input(
        "observer_sha256", sha256_bytes((config_dir() / "observer.yaml").read_bytes())
    )
    unrecorded = {
        c.kind: missing
        for c in observed
        if (
            missing := [
                n for n in (c.id_field, c.name_field, *c.fields, *c.path) if n and n not in recorded
            ]
        )
    }
    if unrecorded:
        raise RuntimeError(f"observer names absent from every recorded response: {unrecorded}")
    by_collection = {c.kind: c for c in observed}
    observations = 0
    for family in families.values():
        for scenario in family.scenarios.values():
            for step in scenario.steps:
                references = [(o.collection, o.field) for o in step.observe]
                if step.expect:
                    references += [
                        (address.split(".", 1)[0], None)
                        for address in (*step.expect.remote_present, *step.expect.remote_absent)
                    ]
                for collection, name in references:
                    known = by_collection.get(collection)
                    if known is None or (name is not None and name not in known.fields):
                        raise RuntimeError(f"{scenario.id}: observes {collection}.{name}")
                observations += len(step.observe)
    drift = read_yaml(config_dir() / "drift.yaml")["operators"]
    faults = read_yaml(config_dir() / "faults.yaml")
    manifest.add_input("drift_sha256", sha256_bytes((config_dir() / "drift.yaml").read_bytes()))
    manifest.add_input("faults_sha256", sha256_bytes((config_dir() / "faults.yaml").read_bytes()))
    contract = json.loads(snapshot.show(snapshot.dokploy_versions()[0].openapi))["paths"]
    scenarios = {s.id: s for f in families.values() for s in f.scenarios.values()}
    for name, operator in drift.items():
        start = operator["start"]
        if start["scenario"] not in scenarios or start["step"] > len(
            scenarios[start["scenario"]].steps
        ):
            raise RuntimeError(f"{name}: unknown start {start}")
        write = operator["write"]
        post = contract.get(f"/{write['operation']}", {}).get("post")
        if post is None:
            raise RuntimeError(f"{name}: {write['operation']} is not a POST of the contract")
        schema = post["requestBody"]["content"]["application/json"]["schema"]
        extra = set(write["body"]) - set(schema.get("properties", {}))
        if extra:
            raise RuntimeError(f"{name}: {write['operation']} has no fields {sorted(extra)}")
        target = operator.get("target")
        if target and target["collection"] not in by_collection:
            raise RuntimeError(f"{name}: unobserved collection {target['collection']}")
    for scenario_id in faults["scenarios"]:
        if scenario_id not in scenarios:
            raise RuntimeError(f"faults.yaml names unknown scenario {scenario_id}")
    invalid = [r for r in rows if not r["valid"]]
    summary = {
        "families": {f.name: len(f.scenarios) for f in families.values()},
        "scenarios": sum(len(f.scenarios) for f in families.values()),
        "steps": sum(len(s.steps) for f in families.values() for s in f.scenarios.values()),
        "documents_checked": len(rows),
        "documents_invalid": len(invalid),
        "kinds_exercised": len(exercised),
        "kinds_total": len(catalog),
        "kinds_not_exercised": sorted({s.kind for s in catalog} - set(exercised)),
        "classes_exercised": sum(1 for r in class_rows if r["exercised"]),
        "classes_exercised_by_class": {str(r["class"]): r["exercised"] for r in class_rows},
        "live_design": live_design(len(snapshot.dokploy_versions())),
        "classes_total": len(class_rows),
        "negative_controls": controls,
        "observer_collections": sorted(c.kind for c in observed),
        "observations": observations,
        "l4_seed": {
            "scenarios": list(L4_SEED),
            "kinds": sorted(
                seed_kinds := {
                    k for r in rows if r["scenario"] in L4_SEED for k in str(r["kinds"]).split()
                }
            ),
            "kind_count": len(seed_kinds),
        },
        "drift_operators": len(drift),
        "fault_cells_per_version": len(faults["scenarios"])
        * len(faults["kinds"])
        * len(faults["ordinals"]),
        "observer_kinds_not_observed": sorted(set(exercised) - {c.kind for c in observed}),
        "observer_kinds_observed": len(set(exercised) & {c.kind for c in observed}),
    }
    return [
        write_json(out / "summary.json", summary),
        write_csv(out / "documents.csv", rows, list(rows[0])),
        write_csv(out / "kinds.csv", kinds_rows, list(kinds_rows[0])),
        write_csv(out / "classes.csv", class_rows, list(class_rows[0])),
    ]


def s7_kind_references(snapshot: Snapshot, out: Path, manifest: RunManifest) -> list[Path]:
    rules_path = config_dir() / "kind-references.yaml"
    rules = read_yaml(rules_path)
    manifest.add_input("rules_sha256", sha256_bytes(rules_path.read_bytes()))
    catalog, _ = load_catalog(snapshot)
    files = {
        path: snapshot.show(path).decode()
        for crate in rules["crates"]
        for path in snapshot.list_files(f"crates/{crate}/src")
        if path.endswith(".rs")
    }
    manifest.add_input("source_files", len(files))
    found = references.find(files, (spec.kind for spec in catalog))
    rows, unclassified = references.classify(found, rules)
    if unclassified:
        listed = "; ".join(f"{r.file}:{r.line} {r.kind}" for r in unclassified)
        raise RuntimeError(f"unclassified kind references: {listed}")
    summary = references.summarise(rows, rules)
    simulator = tuple(f"crates/{crate}/" for crate in rules.get("simulator", []))
    summary["source_files_scanned"] = sum(1 for p in files if not p.startswith(simulator))
    summary["simulator"]["source_files_scanned"] = sum(1 for p in files if p.startswith(simulator))
    return [
        write_json(out / "summary.json", summary),
        write_csv(out / "references.csv", rows, list(rows[0])),
    ]


@dataclass(frozen=True)
class StaticExperiment:
    id: str
    title: str
    run: Callable[[Snapshot, Path, RunManifest], list[Path]]
    needs_binary: bool = False


EXPERIMENTS: dict[str, StaticExperiment] = {
    e.id: e
    for e in (
        StaticExperiment("S1-census", "API census", s1_census),
        StaticExperiment("S2-specifications", "Specification inventory", s2_specifications),
        StaticExperiment("S3-ledger", "Coverage ledger", s3_ledger, needs_binary=True),
        StaticExperiment("S4-fixtures", "Recorded responses", s4_fixtures),
        StaticExperiment("S5-invariants", "Documented invariants", s5_invariants),
        StaticExperiment("S6-scenarios", "Scenario validity and coverage", s6_scenarios, True),
        StaticExperiment("S7-kind-references", "Kind names in engine code", s7_kind_references),
    )
}


def output_dir(experiment_id: str, snapshot: Snapshot) -> Path:
    return results_dir() / "static" / experiment_id / snapshot.config.snapshot


def run_experiment(experiment: StaticExperiment, snapshot: Snapshot) -> Path:
    out = output_dir(experiment.id, snapshot)
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.iterdir():
        if stale.is_file():
            stale.unlink()
    manifest = RunManifest(
        experiment=experiment.id, output_dir=out, snapshot=snapshot.config.snapshot
    )
    manifest.add_input("system_under_study", snapshot.describe())
    outputs = experiment.run(snapshot, out, manifest)
    return manifest.finish(outputs)


@app.command("list")
def list_experiments() -> None:
    """List the static experiments."""

    for experiment in EXPERIMENTS.values():
        note = "  (needs the binary)" if experiment.needs_binary else ""
        typer.echo(f"{experiment.id:20} {experiment.title}{note}")


@app.command("run")
def run_command(
    names: list[str] = typer.Argument(None, help="Experiment ids; omit with --all."),
    all_: bool = typer.Option(False, "--all", help="Run every static experiment."),
    skip_binary: bool = typer.Option(
        False, help="Skip experiments that need the release binary (for example in CI)."
    ),
) -> None:
    """Run static experiments and write results/static/<id>/<snapshot>/."""

    selected = list(EXPERIMENTS) if all_ or not names else names
    unknown = [name for name in selected if name not in EXPERIMENTS]
    if unknown:
        raise typer.BadParameter(f"unknown experiments: {', '.join(unknown)}")
    snapshot = Snapshot.pinned()
    for name in selected:
        experiment = EXPERIMENTS[name]
        if experiment.needs_binary and skip_binary:
            typer.echo(f"skip     {name} (needs the binary)")
            continue
        manifest = run_experiment(experiment, snapshot)
        typer.echo(f"wrote    {manifest.parent}")
