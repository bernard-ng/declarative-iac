"""Comparing claims with results, and with the text of the paper."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from declarative_iac.core.canonical import read_json
from declarative_iac.core.manifest import MANIFEST_NAME, verify_manifest
from declarative_iac.domain.claims.registry import Claim, Source

PASS, FAIL, PENDING, MISSING = "pass", "fail", "pending", "missing"


@dataclass(frozen=True)
class Verdict:
    claim: Claim
    status: str
    observed: Any
    detail: str = ""


def resolve_pointer(document: Any, pointer: str) -> Any:
    """RFC 6901 JSON pointer."""

    if pointer in ("", "/"):
        return document
    node = document
    for raw in pointer.lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            node = node[int(token)]
        elif isinstance(node, dict):
            if token not in node:
                raise KeyError(pointer)
            node = node[token]
        else:
            raise KeyError(pointer)
    return node


def _aggregate(values: list[Any], how: str | None) -> Any:
    if how is None:
        return values[0] if len(values) == 1 else values
    numbers = [v if isinstance(v, (int, float)) else len(v) for v in values]
    if how == "min":
        return min(numbers)
    if how == "max":
        return max(numbers)
    if how == "range":
        return [min(numbers), max(numbers)]
    if how == "sum":
        return sum(numbers)
    return len(values)  # count


def observe(source: Source, results: Path) -> tuple[Any, list[str]]:
    """The value a source yields, and problems with the result's manifest."""

    path = results / source.result
    manifest = path.parent / MANIFEST_NAME
    problems = verify_manifest(manifest) if manifest.is_file() else [f"{manifest}: missing"]
    document = read_json(path)
    values = [resolve_pointer(document, pointer) for pointer in source.pointers]
    return _aggregate(values, source.aggregate), problems


def _equal(expected: Any, observed: Any, tolerance: float) -> bool:
    if isinstance(expected, (int, float)) and isinstance(observed, (int, float)):
        return abs(float(expected) - float(observed)) <= tolerance
    if isinstance(expected, list) and isinstance(observed, list):
        if all(isinstance(x, str) for x in expected + observed):
            return sorted(expected) == sorted(observed)
        return len(expected) == len(observed) and all(
            _equal(e, o, tolerance) for e, o in zip(expected, observed, strict=True)
        )
    return expected == observed


def verify(claim: Claim, results: Path) -> Verdict:
    if claim.rule == "pending":
        return Verdict(claim, PENDING, None, claim.notes or "awaiting a result")
    if claim.source is None:
        raise RuntimeError("claim.source is required here")
    try:
        observed, problems = observe(claim.source, results)
    except FileNotFoundError:
        return Verdict(claim, MISSING, None, f"{claim.source.result} does not exist")
    except (KeyError, IndexError, ValueError) as error:
        return Verdict(claim, MISSING, None, f"pointer not found: {error}")
    if problems:
        return Verdict(claim, FAIL, observed, "; ".join(problems))
    tolerance = claim.tolerance if claim.rule == "approx" else 0.0
    if _equal(claim.value, observed, tolerance):
        return Verdict(claim, PASS, observed)
    return Verdict(claim, FAIL, observed, f"claimed {claim.value!r}, result {observed!r}")


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def check_paper(claim: Claim, sections: Path) -> list[str]:
    """Locations of the claim whose fragment is not in the cited file."""

    missing: list[str] = []
    for location in claim.locations:
        path = sections / location.file
        if not path.is_file():
            missing.append(f"{location.file}: file does not exist")
        elif normalise(location.text) not in normalise(path.read_text(encoding="utf-8")):
            missing.append(f"{location.file}: {location.text!r} not found")
    return missing
