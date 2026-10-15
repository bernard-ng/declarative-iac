"""Where the engine names a kind (S7): literal kind names in non-test engine source."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

TEST_START = re.compile(r"^#\[cfg\(test\)\]")


@dataclass(frozen=True)
class Reference:
    file: str
    line: int
    kind: str
    text: str


def production_lines(source: str) -> Iterable[tuple[int, str]]:
    """Lines before the first top-level `#[cfg(test)]`."""

    for number, line in enumerate(source.splitlines(), start=1):
        if TEST_START.match(line):
            return
        yield number, line


def find(files: Mapping[str, str], kinds: Iterable[str]) -> list[Reference]:
    names = sorted(set(kinds), key=len, reverse=True)
    pattern = re.compile(r'"(' + "|".join(map(re.escape, names)) + r')"')
    out: list[Reference] = []
    for path, source in sorted(files.items()):
        if "/tests/" in path:
            continue
        for number, line in production_lines(source):
            if line.lstrip().startswith("//"):
                continue
            # One reference per line and kind: `"application" => "application"` maps the kind
            # to Dokploy's deployment type of the same spelling, which is one place, not two.
            for kind in dict.fromkeys(m.group(1) for m in pattern.finditer(line)):
                out.append(Reference(path, number, kind, line.strip()))
    return out


def _applies(rule: Mapping[str, Any], reference: Reference) -> bool:
    return reference.kind in rule["kinds" if "kinds" in rule else "kind"] and (
        "files" not in rule or reference.file in rule["files"]
    )


def classify(
    references: list[Reference], rules: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[Reference]]:
    rows: list[dict[str, Any]] = []
    unclassified: list[Reference] = []
    for reference in references:
        exclusion = next(
            (
                r
                for r in rules["exclusions"]
                if reference.kind == r["kind"] and reference.file in r["files"]
            ),
            None,
        )
        concern = (
            None
            if exclusion
            else next(
                (name for name, rule in rules["concerns"].items() if _applies(rule, reference)),
                None,
            )
        )
        if exclusion is None and concern is None:
            unclassified.append(reference)
            continue
        rows.append(
            {
                "file": reference.file,
                "line": reference.line,
                "kind": reference.kind,
                "classification": concern or "excluded",
                "reason": exclusion["reason"] if exclusion else "",
                "text": reference.text,
            }
        )
    return rows, unclassified


def summarise(rows: list[dict[str, Any]], rules: Mapping[str, Any]) -> dict[str, Any]:
    """Counts for the engine (all scanned crates but the simulator), plus the simulator apart."""

    simulator = tuple(f"crates/{crate}/" for crate in rules.get("simulator", []))
    in_simulator = [r for r in rows if r["file"].startswith(simulator) and simulator]
    rows = [r for r in rows if r not in in_simulator]
    summary = _summarise(rows, rules)
    summary["simulator"] = _summarise(in_simulator, rules)
    return summary


def _summarise(rows: list[dict[str, Any]], rules: Mapping[str, Any]) -> dict[str, Any]:
    kept = [r for r in rows if r["classification"] != "excluded"]
    concerns = {}
    for name, rule in rules["concerns"].items():
        mine = [r for r in kept if r["classification"] == name]
        concerns[name] = {
            "title": rule["title"],
            "binding": bool(rule["binding"]),
            "references": len(mine),
            "files": len({r["file"] for r in mine}),
            "kinds": sorted({r["kind"] for r in mine}),
        }
    return {
        "references": len(kept),
        "files": len({r["file"] for r in kept}),
        "concerns": len([c for c in concerns.values() if c["references"]]),
        "binding_concerns": len([c for c in concerns.values() if c["references"] and c["binding"]]),
        "kinds_named": sorted({r["kind"] for r in kept}),
        "excluded": len(rows) - len(kept),
        "by_concern": concerns,
    }
