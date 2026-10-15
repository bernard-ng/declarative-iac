from __future__ import annotations

from pathlib import Path

import pytest

from declarative_iac.core.canonical import write_json
from declarative_iac.core.manifest import RunManifest
from declarative_iac.domain.claims import registry, verifier

REGISTRY = """
format: 1
claims:
  - id: total
    statement: There are 604 operations.
    value: 604
    source: {result: static/S1/B1/summary.json, pointer: /ops}
    paper: [{file: 03.md, text: "has 604\\n operations"}]
  - id: range
    statement: Between 2 and 5.
    value: [2, 5]
    source: {result: static/S1/B1/summary.json, pointers: [/a, /b, /c], aggregate: range}
  - id: later
    statement: Measured later.
    rule: pending
"""


@pytest.fixture
def results(tmp_path: Path) -> Path:
    out = tmp_path / "results" / "static" / "S1" / "B1"
    summary = write_json(out / "summary.json", {"ops": 604, "a": 5, "b": 2, "c": 3})
    RunManifest(experiment="S1", output_dir=out, snapshot="B1", command=["t"]).finish([summary])
    return tmp_path / "results"


def load(tmp_path: Path) -> list[registry.Claim]:
    path = tmp_path / "claims.yaml"
    path.write_text(REGISTRY)
    return registry.load(path)


def test_claims_pass_aggregate_and_stay_pending(tmp_path: Path, results: Path):
    statuses = {c.id: verifier.verify(c, results).status for c in load(tmp_path)}
    assert statuses == {"total": "pass", "range": "pass", "later": "pending"}


def test_a_changed_result_fails_through_its_manifest(tmp_path: Path, results: Path):
    claim = load(tmp_path)[0]
    (results / "static/S1/B1/summary.json").write_text('{"ops": 604, "a": 5, "b": 2, "c": 3}\n')
    verdict = verifier.verify(claim, results)
    assert verdict.status == "fail" and "differs from its manifest" in verdict.detail


def test_a_wrong_value_fails(tmp_path: Path, results: Path):
    claim = load(tmp_path)[0]
    wrong = registry.Claim(**{**claim.__dict__, "value": 605})
    assert verifier.verify(wrong, results).status == "fail"


def test_paper_text_is_matched_whitespace_insensitively(tmp_path: Path):
    claim = load(tmp_path)[0]
    sections = tmp_path / "sections"
    sections.mkdir()
    (sections / "03.md").write_text("The API has 604\noperations in total.\n")
    assert verifier.check_paper(claim, sections) == []
    (sections / "03.md").write_text("The API has 605 operations.\n")
    assert verifier.check_paper(claim, sections) != []


def test_duplicate_ids_are_rejected(tmp_path: Path):
    path = tmp_path / "claims.yaml"
    path.write_text(
        "claims:\n  - {id: a, statement: x, rule: pending}\n"
        "  - {id: a, statement: y, rule: pending}\n"
    )
    with pytest.raises(registry.RegistryError):
        registry.load(path)
