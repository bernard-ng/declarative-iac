"""Pure functions that turn the evidence of a run into measures (PREREGISTRATION.md, §5-§6).

Nothing here talks to Dokploy or runs the system, so every decision rule is unit-tested offline.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from declarative_iac.domain.scenarios.model import Change

VOLATILE_PLAN_FIELDS = ("lineage", "stateSerial", "configDigest")
UNSAFE_ORDER = ("U5", "U1", "U2", "U3", "U4", "U6")


class PlanParseError(ValueError):
    """The plan output is not the JSON document the system documents."""


def parse_plans(stdout: str) -> list[dict[str, Any]]:
    """The `[{document, plan}]` list printed by `plan --json`."""

    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise PlanParseError(f"plan output is not JSON: {error}") from error
    if not isinstance(value, list) or not all(
        isinstance(item, dict) and "document" in item and "plan" in item for item in value
    ):
        raise PlanParseError("plan output is not a list of {document, plan}")
    return value


def planned_changes(plans: Iterable[Mapping[str, Any]]) -> list[tuple[str, str]]:
    """Every (kind, address) the plans would act on; `no_op` checkpoints are not changes."""

    return sorted(
        (str(change["kind"]), str(change["address"]))
        for item in plans
        for change in item["plan"].get("changes", [])
        if change.get("kind") != "no_op"
    )


def applyable(plans: Iterable[Mapping[str, Any]]) -> bool:
    return all(item["plan"].get("complete") and item["plan"].get("applyable") for item in plans)


@dataclass(frozen=True)
class ChangeComparison:
    equal: bool
    missing: tuple[str, ...]
    unexpected: tuple[str, ...]

    def record(self) -> dict[str, Any]:
        return {"equal": self.equal, "missing": self.missing, "unexpected": self.unexpected}


def compare_changes(actual: list[tuple[str, str]], expected: Iterable[Change]) -> ChangeComparison:
    """Multiset equality, each expected change matching one planned change by address suffix."""

    remaining = list(actual)
    missing: list[str] = []
    for change in expected:
        hit = next((a for a in remaining if change.matches(*a)), None)
        if hit is None:
            missing.append(f"{change.kind} {change.address}")
        else:
            remaining.remove(hit)
    unexpected = tuple(f"{kind} {address}" for kind, address in remaining)
    return ChangeComparison(not missing and not unexpected, tuple(missing), unexpected)


def normalised_plan(plans: list[dict[str, Any]]) -> str:
    """The plans without the fields that legitimately differ between runs (H7b)."""

    reduced = [
        {
            "document": item["document"],
            "plan": {k: v for k, v in item["plan"].items() if k not in VOLATILE_PLAN_FIELDS},
        }
        for item in plans
    ]
    return json.dumps(reduced, sort_keys=True, separators=(",", ":"))


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def names(view: Mapping[str, list[dict[str, Any]]]) -> Counter[tuple[str, str]]:
    return Counter(
        (kind, str(row.get("name")))
        for kind, rows in view.items()
        for row in rows
        if row.get("name") is not None
    )


def duplicated(view: Mapping[str, list[dict[str, Any]]]) -> list[tuple[str, str]]:
    """Objects that occur more than once under one name and parent (U1 evidence)."""

    counts = Counter(
        (kind, str(row.get("parent")), str(row.get("name")))
        for kind, rows in view.items()
        for row in rows
        if row.get("name") is not None
    )
    return sorted((kind, name) for (kind, _, name), n in counts.items() if n > 1)


def extra_objects(
    final: Mapping[str, list[dict[str, Any]]], reference: Mapping[str, list[dict[str, Any]]]
) -> list[tuple[str, str]]:
    """Named objects present after a faulted run but not after the fault-free reference (U2)."""

    surplus = names(final) - names(reference)
    return sorted(surplus.elements())


def foreign_changes(
    baseline: Mapping[str, list[dict[str, Any]]],
    final: Mapping[str, list[dict[str, Any]]],
    foreign_ids: set[str],
) -> list[dict[str, Any]]:
    """Changes to objects the system does not own: present before it ran, or made by the
    harness as drift (H4)."""

    out: list[dict[str, Any]] = []
    for kind in sorted(set(baseline) | set(final)):
        old = {str(r["id"]): r for r in baseline.get(kind, []) if str(r["id"]) in foreign_ids}
        new = {str(r["id"]): r for r in final.get(kind, []) if str(r["id"]) in foreign_ids}
        for identity in sorted(set(old) | set(new)):
            if old.get(identity) != new.get(identity):
                out.append(
                    {
                        "kind": kind,
                        "id": identity,
                        "before": old.get(identity),
                        "after": new.get(identity),
                    }
                )
    return out


def ids(view: Mapping[str, list[dict[str, Any]]]) -> set[str]:
    return {str(row["id"]) for rows in view.values() for row in rows}


def classify_fault_run(evidence: Mapping[str, Any]) -> str:
    """The outcome class of an L3 run, in the pre-registered precedence order."""

    flags = {
        "U5": bool(evidence.get("leaks")),
        "U1": bool(evidence.get("duplicates")),
        "U2": bool(evidence.get("extra_objects")),
        "U3": bool(evidence.get("foreign_changes")),
        "U4": bool(evidence.get("converged")) and not evidence.get("observations_hold", True),
        "U6": bool(evidence.get("crash")),
    }
    for code in UNSAFE_ORDER:
        if flags[code]:
            return code
    return "C1" if evidence.get("converged") else "C2"


def crashed(exit_code: int, stderr: str) -> bool:
    """U6: an exit code outside the documented set, a panic, or a silent failure."""

    if exit_code not in (0, 1, 2):
        return True
    if "panicked at" in stderr:
        return True
    return exit_code == 1 and not stderr.strip()


def wilson(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """The Wilson score interval for a proportion (95% by default)."""

    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))
