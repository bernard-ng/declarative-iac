"""Aggregating run results into the hypothesis table (PREREGISTRATION.md §5)."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from declarative_iac.core.canonical import read_json
from declarative_iac.domain.live.evaluate import wilson

Result = dict[str, Any]
Check = Callable[[Result], bool | None]  # None: the run does not bear on the hypothesis


def _steps(result: Result) -> list[Result]:
    if "steps" in result:
        return result["steps"]
    if "seed" in result:
        return [result["seed"]]
    return []


def _converged_steps(result: Result) -> Iterable[Result]:
    return (s["converge"] for s in _steps(result) if s.get("converge"))


def h1(result: Result) -> bool:
    runs = list(_converged_steps(result))
    for extra in (
        result.get("drift", {}).get("converge"),
        result.get("converge"),
        result.get("rebuild", {}).get("converge"),
    ):
        if extra:
            runs.append(extra)
    return all(c["converged"] and c["k"] <= 2 for c in runs)


def h2(result: Result) -> bool:
    return result.get("plan_posts", 0) == 0 and all(
        s.get("a0_posts", 0) == 0 for s in _steps(result)
    )


def h3(result: Result) -> bool | None:
    settled = [s for s in _steps(result) if s.get("settled") and s.get("observations")]
    if not settled:
        return None
    return all(o["holds"] for s in settled for o in s["observations"])


def h4(result: Result) -> bool:
    drift = result.get("drift", {})
    return (
        not any(s.get("foreign_changes") for s in _steps(result))
        and not drift.get("foreign_changes")
        and drift.get("untouched_ok", True)
        and not result.get("foreign_changes")
    )


def h5(result: Result) -> bool | None:
    drift = result.get("drift")
    return None if drift is None else bool(drift.get("changes", {}).get("equal"))


def expectations(result: Result) -> bool | None:
    checks = []
    for step in _steps(result):
        if "expected_changes" in step:
            checks.append(step["expected_changes"]["equal"])
        if "expectation_met" in step:
            checks.append(step["expectation_met"])
        if "remote_expectations_met" in step:
            checks.append(step["remote_expectations_met"])
    return None if not checks else all(checks)


def h6(result: Result) -> bool | None:
    outcome = result.get("outcome")
    return None if outcome is None else outcome in ("C1", "C2")


def h7a(result: Result) -> bool | None:
    steps = _steps(result)
    return None if not steps else all(s.get("h7a_identical") for s in steps)


def h8(result: Result) -> bool | None:
    if "import_plan" not in result:
        return None
    rebuild = result.get("rebuild", {})
    return (
        result["import_plan"].get("exit") == 0
        and bool(result.get("imports_identical"))
        and bool(rebuild.get("converge", {}).get("converged"))
        and bool(rebuild.get("round_trip_identical"))
    )


def no_leak(result: Result) -> bool:
    return not result.get("leaks")


CHECKS: dict[str, Check] = {
    "H1": h1,
    "H2": h2,
    "H3": h3,
    "H4": h4,
    "H5": h5,
    "H6": h6,
    "H7a": h7a,
    "H8": h8,
    "expectations": expectations,
    "no_leak": no_leak,
}


def load_results(root: Path) -> list[tuple[Path, Result]]:
    """Every run's result; L3 reference runs fix the fault ordinals and are not runs."""

    return [
        (path.parent, read_json(path))
        for path in sorted(root.rglob("result.json"))
        if not any(
            part.startswith("reference--") or part == "rebuild"
            for part in path.relative_to(root).parts
        )
    ]


def proportion(values: list[bool]) -> dict[str, Any]:
    n, k = len(values), sum(values)
    low, high = wilson(k, n)
    return {
        "n": n,
        "satisfied": k,
        "proportion": round(k / n, 4) if n else None,
        "wilson95": [low, high],
    }


def summarise(root: Path) -> dict[str, Any]:
    """`root` is results/live/<exp>/<snapshot>; runs are <version>/<cell>/<run>/result.json."""

    runs = load_results(root)
    table: dict[str, Any] = {}
    violations: dict[str, list[str]] = defaultdict(list)
    for name, check in CHECKS.items():
        by_version: dict[str, list[bool]] = defaultdict(list)
        for directory, result in runs:
            verdict = check(result)
            if verdict is None:
                continue
            version = directory.relative_to(root).parts[0]
            by_version[version].append(verdict)
            if not verdict:
                violations[name].append(directory.relative_to(root).as_posix())
        if not by_version:
            continue
        pooled = [v for values in by_version.values() for v in values]
        table[name] = {
            "verdict": "supported" if all(pooled) else "refuted",
            "pooled": proportion(pooled),
            "by_version": {v: proportion(values) for v, values in sorted(by_version.items())},
        }
    h7b = _determinism_across_runs(root, runs)
    if h7b["cells"]:
        table["H7b"] = h7b
    outcomes = Counter(r.get("outcome") for _, r in runs if r.get("outcome"))
    return {
        "runs": len(runs),
        "hypotheses": table,
        "violations": {k: sorted(v) for k, v in sorted(violations.items())},
        "outcomes": dict(sorted(outcomes.items())),
    }


def _determinism_across_runs(root: Path, runs: list[tuple[Path, Result]]) -> dict[str, Any]:
    digests: dict[tuple[str, str, int], set[str]] = defaultdict(set)
    for directory, result in runs:
        version, cell = directory.relative_to(root).parts[:2]
        for step in result.get("steps", []):
            if step.get("first_plan_digest"):
                digests[(version, cell, step["step"])].add(step["first_plan_digest"])
    differing = sorted(f"{v}/{c}/step{s}" for (v, c, s), d in digests.items() if len(d) > 1)
    return {
        "verdict": "supported" if not differing else "refuted",
        "cells": len(digests),
        "differing": differing,
    }
