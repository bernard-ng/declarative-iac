from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from declarative_iac.core.canonical import write_json
from declarative_iac.domain.live import evaluate
from declarative_iac.domain.live.experiment import merge_steps, mutation_ordinals
from declarative_iac.domain.live.summary import summarise
from declarative_iac.domain.live.writer import ForbiddenWrite, Writer, fill
from declarative_iac.domain.scenarios.model import Change, Step
from declarative_iac.workflow import live


def plan_output(*changes: tuple[str, str], lineage: str = "l-1") -> str:
    plan = {
        "formatVersion": 1,
        "lineage": lineage,
        "stateSerial": 3,
        "configDigest": "d",
        "changes": [
            {"address": a, "kind": k, "origin": "config", "fields": [], "metadata": []}
            for k, a in changes
        ],
        "drift": [],
        "complete": True,
        "applyable": True,
        "diagnostics": [],
    }
    return json.dumps([{"document": ".dokploy/settings.yaml", "plan": plan}])


def test_plans_are_parsed_and_no_op_is_not_a_change():
    plans = evaluate.parse_plans(plan_output(("update", "tag.probe"), ("no_op", "tag.other")))
    assert evaluate.planned_changes(plans) == [("update", "tag.probe")]
    assert evaluate.applyable(plans)
    with pytest.raises(evaluate.PlanParseError):
        evaluate.parse_plans("error: no")
    with pytest.raises(evaluate.PlanParseError):
        evaluate.parse_plans("{}")


def test_change_comparison_is_a_multiset_match():
    actual = [("update", "project.p/tag.a"), ("create", "tag.b")]
    same = evaluate.compare_changes(
        actual, [Change.parse("create tag.b"), Change.parse("update tag.a")]
    )
    assert same.equal
    short = evaluate.compare_changes(actual, [Change.parse("create tag.b")])
    assert not short.equal and short.unexpected == ("update project.p/tag.a",)
    twice = evaluate.compare_changes(actual, [Change.parse("create tag.b")] * 2)
    assert twice.missing == ("create tag.b",)
    assert evaluate.compare_changes([], []).equal


def test_normalisation_removes_only_volatile_fields():
    a = evaluate.parse_plans(plan_output(("create", "tag.a"), lineage="one"))
    b = evaluate.parse_plans(plan_output(("create", "tag.a"), lineage="two"))
    c = evaluate.parse_plans(plan_output(("update", "tag.a")))
    assert evaluate.normalised_plan(a) == evaluate.normalised_plan(b)
    assert evaluate.normalised_plan(a) != evaluate.normalised_plan(c)


VIEW = {
    "tag": [
        {"id": "1", "parent": None, "name": "a", "color": "#1"},
        {"id": "2", "parent": None, "name": "b", "color": "#2"},
    ]
}


def test_duplicates_extras_and_foreign_changes():
    doubled = {"tag": [*VIEW["tag"], {"id": "3", "parent": None, "name": "a", "color": "#1"}]}
    assert evaluate.duplicated(VIEW) == []
    assert evaluate.duplicated(doubled) == [("tag", "a")]
    assert evaluate.extra_objects(doubled, VIEW) == [("tag", "a")]
    changed = {"tag": [VIEW["tag"][0], {**VIEW["tag"][1], "color": "#9"}]}
    assert evaluate.foreign_changes(VIEW, changed, {"1"}) == []
    assert evaluate.foreign_changes(VIEW, changed, {"2"})[0]["id"] == "2"
    deleted = {"tag": [VIEW["tag"][0]]}
    assert evaluate.foreign_changes(VIEW, deleted, {"2"})[0]["after"] is None


@pytest.mark.parametrize(
    ("evidence", "outcome"),
    [
        ({"converged": True}, "C1"),
        ({"converged": False}, "C2"),
        ({"converged": True, "observations_hold": False}, "U4"),
        ({"converged": False, "observations_hold": False}, "C2"),
        ({"converged": True, "duplicates": [("tag", "a")], "leaks": ["x"]}, "U5"),
        ({"converged": True, "duplicates": [("tag", "a")], "extra_objects": [1]}, "U1"),
        ({"converged": True, "extra_objects": [1]}, "U2"),
        ({"converged": True, "foreign_changes": [1]}, "U3"),
        ({"converged": False, "crash": True}, "U6"),
    ],
)
def test_fault_outcomes_follow_the_registered_precedence(evidence, outcome):
    assert evaluate.classify_fault_run(evidence) == outcome


def test_crash_detection():
    assert not evaluate.crashed(0, "")
    assert not evaluate.crashed(1, "error: the journal has an unfinished step")
    assert evaluate.crashed(1, "   ")
    assert evaluate.crashed(101, "")
    assert evaluate.crashed(1, "thread 'main' panicked at src/x.rs")


def test_wilson_interval_matches_reference_values():
    # Reference values from the closed form (Wilson 1927), z = 1.96.
    assert evaluate.wilson(10, 10) == (0.7225, 1.0)
    assert evaluate.wilson(0, 10) == (0.0, 0.2775)
    low, high = evaluate.wilson(5, 10)
    assert (low, high) == (0.2366, 0.7634)
    assert evaluate.wilson(0, 0) == (0.0, 1.0)


def test_mutation_ordinals():
    assert mutation_ordinals(1) == {"first": 1, "middle": 1, "last": 1}
    assert mutation_ordinals(7) == {"first": 1, "middle": 4, "last": 7}
    with pytest.raises(ValueError):
        mutation_ordinals(0)


def test_writer_refuses_unregistered_operations_and_fills_templates():
    seen: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"ok": True})

    writer = Writer(
        "http://127.0.0.1:1", "k", {"tag.update"}, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ForbiddenWrite):
        writer.write("tag.remove", {})
    writer.write("tag.update", fill({"tagId": "{id}", "color": "#0"}, "t-1"))
    assert seen == [("/api/tag.update", {"tagId": "t-1", "color": "#0"})]
    with pytest.raises(ValueError):
        fill({"tagId": "{id}"}, None)


def test_the_l4_seed_merges_sections_and_refuses_shared_projects():
    a = Step.parse({"settings": {"tags": {"x": {}}}, "projects": {"p": {}}, "secrets": ["A"]})
    b = Step.parse(
        {
            "settings": {"tags": {"y": {}}},
            "projects": {"q": {}},
            "secrets": ["A", "B"],
            "observe": [{"collection": "tag", "name": "y"}],
        }
    )
    seed = merge_steps([a, b])
    assert seed.settings == {"tags": {"x": {}, "y": {}}}
    assert set(seed.projects) == {"p", "q"} and seed.secrets == ("A", "B")
    assert len(seed.observe) == 1
    with pytest.raises(ValueError):
        merge_steps([a, a])


def test_the_registered_design_has_the_registered_size():
    assert len(live.cells("L1")) == 28
    assert len(live.cells("L2")) == 7
    assert len(live.cells("L3")) == 36
    assert len(live.cells("L4")) == 1
    assert {c.scenario for c in live.cells("L2")} <= set(live.scenarios())


def _result(root: Path, version: str, cell: str, run: str, value: dict) -> None:
    write_json(root / version / cell / run / "result.json", value)


def test_summary_reports_verdicts_intervals_and_violations(tmp_path: Path):
    good = {
        "steps": [
            {
                "step": 1,
                "converge": {"k": 1, "converged": True},
                "a0_posts": 0,
                "settled": True,
                "observations": [{"holds": True}],
                "h7a_identical": True,
                "first_plan_digest": "d1",
            }
        ],
        "plan_posts": 0,
        "leaks": [],
    }
    slow = json.loads(json.dumps(good))
    slow["steps"][0]["converge"]["k"] = 3
    slow["steps"][0]["first_plan_digest"] = "d2"
    _result(tmp_path, "0.30.6", "unit-tag", "r1", good)
    _result(tmp_path, "0.30.6", "unit-tag", "r2", slow)
    _result(tmp_path, "0.30.7", "unit-tag", "r1", good)
    _result(tmp_path, "0.30.7", "reference--x", "r1", {"converge": {"k": 9, "converged": False}})
    summary = summarise(tmp_path)
    assert summary["runs"] == 3
    h1 = summary["hypotheses"]["H1"]
    assert h1["verdict"] == "refuted" and h1["pooled"]["satisfied"] == 2
    assert summary["violations"]["H1"] == ["0.30.6/unit-tag/r2"]
    assert summary["hypotheses"]["H2"]["verdict"] == "supported"
    assert summary["hypotheses"]["H7b"]["differing"] == ["0.30.6/unit-tag/step1"]
    assert "H5" not in summary["hypotheses"]
