"""`claims/claims.yaml`: the registry of the paper's quantitative claims."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from declarative_iac.core.canonical import read_yaml

RULES = ("exact", "approx", "pending")
AGGREGATES = (None, "min", "max", "range", "sum", "count")


@dataclass(frozen=True)
class Location:
    """Where the claim appears: a section file and a literal fragment of its text."""

    file: str
    text: str


@dataclass(frozen=True)
class Source:
    """The result that supports a claim: a file below `results/` and one or more JSON pointers."""

    result: str
    pointers: tuple[str, ...]
    aggregate: str | None = None


@dataclass(frozen=True)
class Claim:
    id: str
    statement: str
    value: Any
    rule: str
    locations: tuple[Location, ...]
    source: Source | None
    tolerance: float = 0.0
    evidence: str = "independent"
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


class RegistryError(ValueError):
    pass


def _source(data: dict[str, Any] | None) -> Source | None:
    if not data:
        return None
    pointers = data.get("pointers") or [data["pointer"]]
    aggregate = data.get("aggregate")
    if aggregate not in AGGREGATES:
        raise RegistryError(f"unknown aggregate {aggregate!r}")
    return Source(str(data["result"]), tuple(str(p) for p in pointers), aggregate)


def load(path: Path) -> list[Claim]:
    data = read_yaml(path)
    claims: list[Claim] = []
    seen: set[str] = set()
    for entry in data["claims"]:
        claim = Claim(
            id=str(entry["id"]),
            statement=str(entry["statement"]),
            value=entry.get("value"),
            rule=str(entry.get("rule", "exact")),
            locations=tuple(
                Location(str(loc["file"]), str(loc["text"])) for loc in entry.get("paper", [])
            ),
            source=_source(entry.get("source")),
            tolerance=float(entry.get("tolerance", 0.0)),
            evidence=str(entry.get("evidence", "independent")),
            notes=str(entry.get("notes", "")),
            tags=tuple(entry.get("tags", [])),
        )
        if claim.id in seen:
            raise RegistryError(f"duplicate claim id {claim.id}")
        if claim.rule not in RULES:
            raise RegistryError(f"{claim.id}: unknown rule {claim.rule!r}")
        if claim.rule != "pending" and claim.source is None:
            raise RegistryError(f"{claim.id}: a checkable claim needs a source")
        seen.add(claim.id)
        claims.append(claim)
    return claims
