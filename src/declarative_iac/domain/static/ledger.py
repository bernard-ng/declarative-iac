"""The coverage ledger as the pinned binary reports it (paper Section 7.1)."""

from __future__ import annotations

from typing import Any

COLUMNS = ("mapped", "readonly", "action", "ignored", "derived", "unclassified")


def parse_coverage(text: str) -> list[dict[str, Any]]:
    """Parse `dokploy coverage`: a tab-separated table with one row per kind."""

    lines = [line for line in text.splitlines() if line.strip()]
    header = lines[0].split("\t")
    if header[:2] != ["kind", "coverage"]:
        raise ValueError(f"unexpected coverage header: {header}")
    rows = []
    for line in lines[1:]:
        cells = dict(zip(header, line.split("\t"), strict=True))
        row: dict[str, Any] = {"kind": cells["kind"], "coverage": cells["coverage"].lower()}
        row.update({column: int(cells[column]) for column in COLUMNS})
        rows.append(row)
    return rows


def totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "kinds": len(rows),
        "kinds_partial": sorted(row["kind"] for row in rows if row["coverage"] == "partial"),
        **{column: sum(row[column] for row in rows) for column in COLUMNS},
    }
