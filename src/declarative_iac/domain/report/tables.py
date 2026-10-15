"""Markdown tables generated from results (Section 3, 5, 7 and 9 sources)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from declarative_iac.core.paths import results_dir
from declarative_iac.domain.report.sources import MissingResult, Source, header
from declarative_iac.domain.static.classes import CLASSES


def markdown(columns: Sequence[str], rows: Sequence[Sequence[Any]], align: str = "") -> str:
    align = align or "l" + "r" * (len(columns) - 1)
    rule = ["---:" if a == "r" else "---" for a in align]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(rule) + " |"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def document(sources: list[Source], title: str, body: str, note: str = "") -> str:
    parts = [header(sources), "", f"**{title}**", "", body.rstrip()]
    if note:
        parts += ["", note]
    return "\n".join(parts).rstrip() + "\n"


ROLE_ORDER = ("create", "read_one", "list", "update", "delete", "other")


def census_roles() -> str:
    source = Source.static("S1-census")
    summary = source.json()
    identical = bool(summary.pop("versions_have_identical_operations"))
    first = next(iter(summary.values()))
    rows = [
        (role.replace("_", " "), first["roles"][role], first["used"]["roles"][role])
        for role in ROLE_ORDER
    ]
    rows.append(("total", first["operations"], first["used"]["operations"]))
    versions = ", ".join(summary)
    note = f"Roles are assigned by procedure name. Dokploy {versions}" + (
        " have identical operations." if identical else " differ; values are for the first."
    )
    return document(
        [source],
        "Procedures by role: whole API and used by the kind specifications",
        markdown(("Role", "Whole API", "Used by specifications"), rows),
        note,
    )


def mismatch_classes() -> str:
    source = Source.static("S2-specifications")
    counts = source.json("classes.json")
    rows = [
        (c.id, counts[c.id]["title"], counts[c.id]["test"], counts[c.id]["count"]) for c in CLASSES
    ]
    return document(
        [source],
        "Mismatch classes and the kinds each affects",
        markdown(("Class", "Mismatch", "Mechanical test", "Kinds"), rows, "lllr"),
    )


def constructs() -> str:
    source = Source.static("S2-specifications")
    rows = [(r["mismatch"], r["label"], r["count"]) for r in source.csv("constructs.csv")]
    return document(
        [source],
        "Specification constructs and the kinds that use them",
        markdown(("Class", "Construct", "Kinds"), rows, "llr"),
    )


def ledger() -> str:
    source = Source.static("S3-ledger")
    s = source.json()
    rows = [
        (k, s[k]) for k in ("mapped", "readonly", "ignored", "derived", "action", "unclassified")
    ]
    note = f"{s['kinds']} kinds; partial coverage: {', '.join(s['kinds_partial']) or 'none'}."
    return document(
        [source],
        "Request fields in the coverage ledger, by classification",
        markdown(("Classification", "Fields"), rows),
        note,
    )


def scenarios() -> str:
    source = Source.static("S6-scenarios")
    s = source.json()
    classes = source.csv("classes.csv")
    body = markdown(("Family", "Scenarios"), [(f, n) for f, n in s["families"].items()])
    body += "\n" + markdown(
        ("Class", "Kinds affected", "Kinds exercised"),
        [(r["class"], r["kinds"], r["exercised"]) for r in classes],
    )
    note = (
        f"{s['scenarios']} scenarios, {s['steps']} steps and {s['documents_checked']} documents, "
        f"of which {s['documents_invalid']} fail `dokploy validate`. "
        f"{s['kinds_exercised']} of {s['kinds_total']} kinds are exercised; not exercised: "
        + ", ".join(s["kinds_not_exercised"])
        + "."
    )
    return document(
        [source], "Pre-registered scenarios and the mismatch classes they exercise", body, note
    )


HYPOTHESES = ("H1", "H2", "H3", "H4", "H5", "H6", "H7a", "H7b", "H8", "expectations", "no_leak")


def live_hypotheses() -> str:
    rows: list[tuple[Any, ...]] = []
    sources: list[Source] = []
    for experiment in ("L1", "L2", "L3", "L4"):
        directory = results_dir() / "live" / experiment / "B1"
        if not (directory / "summary.json").is_file():
            rows.append((experiment, "—", "not run", "", ""))
            continue
        source = Source(directory)
        sources.append(source)
        summary = source.json()
        for name in HYPOTHESES:
            entry = summary["hypotheses"].get(name)
            if entry is None:
                continue
            pooled = entry.get("pooled")
            if pooled is None:
                rows.append((experiment, name, entry["verdict"], f"{entry['cells']} cells", ""))
                continue
            low, high = pooled["wilson95"]
            rows.append(
                (
                    experiment,
                    name,
                    entry["verdict"],
                    f"{pooled['satisfied']}/{pooled['n']}",
                    f"[{low:.2f}, {high:.2f}]",
                )
            )
    body = markdown(
        ("Experiment", "Hypothesis", "Verdict", "Runs satisfying", "Wilson 95%"), rows, "lllrr"
    )
    text = document(sources, "Live hypotheses (PREREGISTRATION.md §5)", body)
    if not sources:
        text = text.replace("from . Do not edit.", "from results/live (no runs yet). Do not edit.")
    return text


TABLES: dict[str, Callable[[], str]] = {
    "census-roles": census_roles,
    "mismatch-classes": mismatch_classes,
    "constructs": constructs,
    "coverage-ledger": ledger,
    "scenarios": scenarios,
    "live-hypotheses": live_hypotheses,
}


def write_tables(directory: Path) -> tuple[list[Path], list[str]]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    missing: list[str] = []
    for name, build in TABLES.items():
        try:
            text = build()
        except MissingResult as error:
            missing.append(f"{name}: {error}")
            continue
        path = directory / f"{name}.md"
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written, missing
