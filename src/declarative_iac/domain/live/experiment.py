"""Running one live repetition: instance, proxy, CLI, observer and the evidence they leave.

The procedures follow PREREGISTRATION.md §4.1 step by step; the decision rules are in
`evaluate.py`. Everything a run observes is written under its directory, in `raw/` (command
output, proxy log, snapshots) and `result.json` (the measures).
"""

from __future__ import annotations

import json
import math
import secrets as random_secrets
import shutil
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from declarative_iac.core.canonical import write_json
from declarative_iac.core.paths import config_dir
from declarative_iac.domain.live import evaluate
from declarative_iac.domain.live.canary import make_canary, scan
from declarative_iac.domain.live.cli import CliResult, CliRunner
from declarative_iac.domain.live.instance import Instance
from declarative_iac.domain.live.observer import (
    Collection,
    Observer,
    load_collections,
    read_operations,
)
from declarative_iac.domain.live.proxy import FaultPlan, FaultProxy
from declarative_iac.domain.live.writer import Writer, fill
from declarative_iac.domain.scenarios.model import Observation, Scenario, Step, materialise

K_MAX = 3
L4_EXCLUDE = (".dokploy/state/",)
SETTLE_INTERVAL = 2.0
SETTLE_LIMIT = 60.0

View = dict[str, list[dict[str, Any]]]


def fingerprint_key() -> str:
    """A fresh key in the form the CLI requires: `<uuid>:<64 lowercase hex>`.

    Setting it explicitly keeps the CLI away from the operating system's credential store, so a
    run neither reads nor writes the user's keychain.
    """

    return f"{uuid.uuid4()}:{random_secrets.token_hex(32)}"


@dataclass
class Command:
    index: int
    args: list[str]
    exit_code: int
    seconds: float
    posts: int
    gets: int


@dataclass
class Run:
    """One repetition: the CLI goes through the proxy; observer and writer go direct."""

    directory: Path
    instance: Instance
    binary: Path
    proxy: FaultProxy
    collections: list[Collection]
    writes: set[str]
    commands: list[Command] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    secrets: dict[str, str] = field(default_factory=dict)
    fingerprint_key: str = field(default_factory=lambda: fingerprint_key())

    def __post_init__(self) -> None:
        self.raw = self.directory / "raw"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.workspace = self.directory / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.observer = Observer(
            self.instance.base_url, self.instance.api_key, read_operations(self.collections)
        )
        self.writer = Writer(self.instance.base_url, self.instance.api_key, self.writes)
        self.cli = self.runner(self.workspace)

    def runner(self, workspace: Path) -> CliRunner:
        return CliRunner(
            self.binary,
            workspace,
            self.proxy.url,
            self.instance.api_key,
            self.fingerprint_key,
            self.directory / "home",
            dict(self.secrets),
        )

    # --- commands -------------------------------------------------------------------------

    def command(self, *args: str, cli: CliRunner | None = None) -> CliResult:
        runner = cli or self.cli
        runner.env.update(self.secrets)
        start = len(self.proxy.log.exchanges)
        result = runner(*args)
        window = self.proxy.log.exchanges[start:]
        index = len(self.commands) + 1
        verb = args[0]
        (self.raw / f"{index:03d}-{verb}.out").write_text(result.stdout)
        (self.raw / f"{index:03d}-{verb}.err").write_text(result.stderr)
        self.outputs += [result.stdout, result.stderr]
        self.commands.append(
            Command(
                index,
                list(args),
                result.exit_code,
                result.seconds,
                sum(1 for e in window if e.kind == "mutation"),
                sum(1 for e in window if e.kind == "query"),
            )
        )
        return result

    @property
    def last(self) -> Command:
        return self.commands[-1]

    def plan(self) -> tuple[CliResult, list[dict[str, Any]] | None]:
        result = self.command("plan", "--detailed-exitcode", "--json")
        try:
            return result, evaluate.parse_plans(result.stdout)
        except evaluate.PlanParseError:
            return result, None

    def converge(self, flags: tuple[str, ...] = ()) -> dict[str, Any]:
        """Apply until the plan reports no changes (exit 0) or K_MAX applies have run.

        PREREGISTRATION.md §4.1 step 5. A plan that exits 1 is not a reason to stop: in a
        workspace whose project documents select resources that its settings document creates,
        the plan cannot resolve those selectors until the settings document has been applied,
        while apply handles the documents in order.
        """

        k = 0
        exits: list[int] = []
        result, plans = self.plan()
        exits.append(result.exit_code)
        while result.exit_code != 0 and k < K_MAX:
            self.command("apply", "--auto-approve", *flags)
            k += 1
            result, plans = self.plan()
            exits.append(result.exit_code)
        return {
            "k": k,
            "converged": result.exit_code == 0,
            "final_exit": result.exit_code,
            "plan_exits": exits,
            "apply_exits": [c.exit_code for c in self.commands if c.args[0] == "apply"][-k:]
            if k
            else [],
        }

    # --- observation ----------------------------------------------------------------------

    def snapshot(self, label: str) -> View:
        view = self.observer.snapshot(self.collections)
        write_json(self.raw / "snapshots" / f"{label}.json", view)
        return view

    def settle(self, label: str) -> tuple[View, bool]:
        deadline = time.monotonic() + SETTLE_LIMIT
        previous = self.observer.snapshot(self.collections)
        while time.monotonic() < deadline:
            time.sleep(SETTLE_INTERVAL)
            current = self.observer.snapshot(self.collections)
            if current == previous:
                write_json(self.raw / "snapshots" / f"{label}.json", current)
                return current, True
            previous = current
        write_json(self.raw / "snapshots" / f"{label}.json", previous)
        return previous, False

    def observe(self, view: View, observations: tuple[Observation, ...]) -> list[dict[str, Any]]:
        return [
            {"observation": _observation_data(o), "holds": o.holds(view, self.secrets)}
            for o in observations
        ]

    # --- secrets ------------------------------------------------------------------------------

    def provide_secrets(self, step: Step) -> None:
        for name in step.secrets:
            if name not in self.secrets or name in step.rotate:
                self.secrets[name] = make_canary(name.lower())

    def leaks(self) -> list[str]:
        roots = [self.workspace] + [p for p in self.directory.glob("import-*") if p.is_dir()]
        return scan(roots, self.outputs, list(self.secrets.values()))

    # --- record ---------------------------------------------------------------------------------

    def finish(self, result: dict[str, Any]) -> Path:
        (self.raw / "proxy.jsonl").write_text(self.proxy.log.to_jsonl(self.secrets.values()))
        write_json(self.raw / "commands.json", [c.__dict__ for c in self.commands])
        write_json(self.raw / "writes.json", self.writer.log)
        result["leaks"] = self.leaks()
        result["plan_posts"] = sum(c.posts for c in self.commands if c.args[0] == "plan")
        return write_json(self.directory / "result.json", result)


@contextmanager
def open_run(
    directory: Path,
    instance: Instance,
    binary: Path,
    writes: set[str],
    fault: FaultPlan | None = None,
) -> Iterator[Run]:
    collections = load_collections(config_dir() / "observer.yaml")
    with FaultProxy(instance.base_url, fault) as proxy:
        yield Run(directory, instance, binary, proxy, collections, writes)


# --- procedures (PREREGISTRATION.md §4.1) -------------------------------------------------------


def run_step(run: Run, step: Step, index: int, foreign: set[str]) -> dict[str, Any]:
    """L1 for one step; `foreign` collects the ids of objects the system does not own."""

    if index == 1:
        # Objects present before the system ever ran are foreign; seeded objects are not, since
        # a seeded object exists to be adopted.
        foreign |= evaluate.ids(run.snapshot("pre-run"))
    for seed in step.seed:
        run.writer.write(seed.operation, seed.body)
    baseline = run.snapshot(f"step{index}-baseline")
    run.provide_secrets(step)
    materialise(step, run.workspace)
    first, plans = run.plan()
    first_posts = run.last.posts
    second, _ = run.plan()
    record: dict[str, Any] = {
        "step": index,
        "first_plan_exit": first.exit_code,
        "first_plan_parsed": plans is not None,
        "h7a_identical": first.stdout == second.stdout,
        "first_plan_digest": evaluate.digest(evaluate.normalised_plan(plans)) if plans else None,
        "first_plan_posts": first_posts,
    }
    expect = step.expect
    if plans is not None and expect is not None and expect.changes is not None:
        record["expected_changes"] = evaluate.compare_changes(
            evaluate.planned_changes(plans), expect.changes
        ).record()
    if expect is not None and (expect.refused or expect.apply_exit is not None):
        run.command("apply", "--auto-approve", *step.apply_flags)
        record["apply_exit"] = run.last.exit_code
        record["apply_mutations"] = run.last.posts
        record["expectation_met"] = (
            (expect.apply_exit is None or run.last.exit_code == expect.apply_exit)
            and (
                not expect.refused
                or (run.last.exit_code == 1 and plans is not None and not evaluate.applyable(plans))
            )
            and (expect.mutations is None or run.last.posts == expect.mutations)
        )
        record["converge"] = None
    else:
        record["converge"] = run.converge(step.apply_flags)
        if record["converge"]["converged"]:
            # A0: one more apply on the converged workspace (H2); meaningless otherwise.
            run.command("apply", "--auto-approve", *step.apply_flags)
            record["a0_posts"] = run.last.posts
            record["a0_exit"] = run.last.exit_code
    view, settled = run.settle(f"step{index}-final")
    record["settled"] = settled
    record["observations"] = run.observe(view, step.observe)
    if expect is not None:
        present = [_located(view, a) for a in expect.remote_present]
        absent = [not _located(view, a) for a in expect.remote_absent]
        record["remote_expectations_met"] = all(present) and all(absent)
    record["foreign_changes"] = evaluate.foreign_changes(baseline, view, foreign)
    record["duplicates"] = evaluate.duplicated(view)
    return record


def _located(view: View, address: str) -> bool:
    collection, name = address.split(".", 1)
    return any(str(r.get("name")) == name for r in view.get(collection, []))


def run_l1(run: Run, scenario: Scenario, until: int | None = None) -> dict[str, Any]:
    foreign: set[str] = set()
    steps = scenario.steps[: until or len(scenario.steps)]
    records = [run_step(run, step, i, foreign) for i, step in enumerate(steps, start=1)]
    return {"scenario": scenario.id, "steps": records, "foreign_ids": sorted(foreign)}


def run_l2(run: Run, scenario: Scenario, operator: Mapping[str, Any]) -> dict[str, Any]:
    from declarative_iac.domain.scenarios.model import Change

    prefix = run_l1(run, scenario, until=int(operator["start"]["step"]))
    foreign = set(prefix["foreign_ids"])
    before = run.snapshot("drift-before")
    target = operator.get("target")
    identity = None
    if target:
        rows = [
            r for r in before.get(target["collection"], []) if str(r.get("name")) == target["name"]
        ]
        if len(rows) != 1:
            return {**prefix, "drift": {"error": f"target found {len(rows)} times"}}
        identity = str(rows[0]["id"])
    write = operator["write"]
    run.writer.write(write["operation"], fill(write["body"], identity))
    after_write, _ = run.settle("drift-written")
    foreign |= evaluate.ids(after_write) - evaluate.ids(before)
    _, plans = run.plan()
    expected = [Change.parse(c) for c in operator["expect"]["changes"]]
    comparison = (
        evaluate.compare_changes(evaluate.planned_changes(plans), expected).record()
        if plans is not None
        else {"equal": False, "missing": [], "unexpected": ["<unparsable plan>"]}
    )
    converge = run.converge()
    final, settled = run.settle("drift-final")
    untouched = [
        _located(final, a) and _row(final, a) == _row(after_write, a)
        for a in operator["expect"].get("untouched", [])
    ]
    return {
        **prefix,
        "drift": {
            "operator": operator.get("id"),
            "changes": comparison,
            "converge": converge,
            "settled": settled,
            "untouched_ok": all(untouched),
            "foreign_changes": evaluate.foreign_changes(after_write, final, foreign),
        },
    }


def _row(view: View, address: str) -> dict[str, Any] | None:
    collection, name = address.split(".", 1)
    return next((r for r in view.get(collection, []) if str(r.get("name")) == name), None)


def mutation_ordinals(m: int) -> dict[str, int]:
    """First, middle and last mutation of a fault-free apply with m mutations."""

    if m < 1:
        raise ValueError("the reference apply made no mutation")
    return {"first": 1, "middle": max(1, math.ceil(m / 2)), "last": m}


def run_l3_reference(run: Run, scenario: Scenario) -> dict[str, Any]:
    step = scenario.steps[0]
    run.provide_secrets(step)
    materialise(step, run.workspace)
    run.command("apply", "--auto-approve", *step.apply_flags)
    mutations = run.last.posts
    converge = run.converge(step.apply_flags)
    final, _ = run.settle("reference-final")
    return {"mutations": mutations, "converge": converge, "final": final}


def run_l3(run: Run, scenario: Scenario, reference_final: View) -> dict[str, Any]:
    step = scenario.steps[0]
    baseline = run.snapshot("baseline")
    foreign = evaluate.ids(baseline)
    run.provide_secrets(step)
    materialise(step, run.workspace)
    faulted = run.command("apply", "--auto-approve", *step.apply_flags)
    crash = evaluate.crashed(faulted.exit_code, faulted.stderr)
    for document in step.documents():
        recovered = run.command("recover", "--file", document, "--auto-approve")
        crash = crash or evaluate.crashed(recovered.exit_code, recovered.stderr)
    converge = run.converge(step.apply_flags)
    final, settled = run.settle("final")
    observations = run.observe(final, step.observe)
    evidence = {
        "fault_fired": run.proxy.fired,
        "faulted_exit": faulted.exit_code,
        "converge": converge,
        "converged": converge["converged"],
        "settled": settled,
        "observations_hold": all(o["holds"] for o in observations),
        "duplicates": evaluate.duplicated(final),
        "extra_objects": evaluate.extra_objects(final, reference_final),
        "foreign_changes": evaluate.foreign_changes(baseline, final, foreign),
        "crash": crash,
        "leaks": run.leaks(),
    }
    evidence["outcome"] = evaluate.classify_fault_run(evidence)
    return evidence


def tree_digest(root: Path, exclude: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        if any(relative.startswith(prefix) for prefix in exclude):
            continue
        out[relative] = evaluate.digest(path.read_text(errors="replace"))
    return out


def import_into(run: Run, target: Path) -> CliResult:
    target.mkdir(parents=True, exist_ok=True)
    return run.command("import", "all", "--directory", str(target), "--env", "file")


def run_l4_import(run: Run, seed: Step) -> dict[str, Any]:
    """L4, first instance: converge the seed, import twice, plan the import."""

    seeded = run_step(run, seed, 1, set())
    first = import_into(run, run.directory / "import-1")
    again = import_into(run, run.directory / "import-1b")
    cli = run.runner(run.directory / "import-1")
    planned = run.command("plan", "--detailed-exitcode", "--json", cli=cli)
    one = tree_digest(run.directory / "import-1", L4_EXCLUDE)
    return {
        "seed": seeded,
        "import_exit": [first.exit_code, again.exit_code],
        "import_plan": {"exit": planned.exit_code, "posts": run.last.posts},
        "imports_identical": one == tree_digest(run.directory / "import-1b", L4_EXCLUDE),
        "import_files": len(one),
    }


def run_l4_rebuild(run: Run, imported: Path, secrets: Mapping[str, str]) -> dict[str, Any]:
    """L4, second (fresh) instance: apply the imported workspace without its state, then
    import again and compare with the first import."""

    shutil.copytree(
        imported, run.workspace, dirs_exist_ok=True, ignore=shutil.ignore_patterns("state")
    )
    run.secrets.update(secrets)
    converge = run.converge()
    second = import_into(run, run.directory / "import-2")
    one = tree_digest(imported, L4_EXCLUDE)
    two = tree_digest(run.directory / "import-2", L4_EXCLUDE)
    differing = sorted(k for k in set(one) | set(two) if one.get(k) != two.get(k))
    return {
        "converge": converge,
        "import_exit": second.exit_code,
        "round_trip_identical": not differing,
        "differing_files": differing,
    }


def merge_steps(steps: list[Step]) -> Step:
    """The L4 seed: the union of several scenarios' first steps."""

    settings: dict[str, Any] = {}
    for step in steps:
        for section, body in (step.settings or {}).items():
            if isinstance(body, Mapping) and all(isinstance(v, Mapping) for v in body.values()):
                settings.setdefault(section, {}).update(body)
            else:
                settings[section] = body
    projects: dict[str, Any] = {}
    files: dict[str, str] = {}
    secrets: list[str] = []
    for step in steps:
        overlap = set(projects) & set(step.projects)
        if overlap:
            raise ValueError(f"seed scenarios share project slugs {sorted(overlap)}")
        projects.update(step.projects)
        files.update(step.files)
        secrets += [s for s in step.secrets if s not in secrets]
    return Step.parse(
        {
            "settings": settings or None,
            "projects": projects,
            "files": files,
            "secrets": secrets,
            "observe": [_observation_data(o) for s in steps for o in s.observe],
        }
    )


def _observation_data(observation: Observation) -> dict[str, Any]:
    return {k: v for k, v in observation.__dict__.items() if v is not None and v is not False}


def dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")
