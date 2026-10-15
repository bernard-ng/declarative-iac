"""Regression tests for the harness defects found by pilot round 1 (DEVIATIONS.md, D1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
import typer

from declarative_iac.domain.live import evaluate, experiment
from declarative_iac.domain.live.cli import CliResult
from declarative_iac.domain.live.observer import Collection, Observer
from declarative_iac.domain.live.proxy import Exchange, ProxyLog
from declarative_iac.domain.scenarios.lint import lint
from declarative_iac.domain.static.specs import KindSpec, SpecCatalog
from declarative_iac.workflow import live


class ScriptedRun:
    """Stands in for `experiment.Run`: plans and applies return scripted exit codes."""

    def __init__(self, plan_exits: list[int]) -> None:
        self.plan_exits = list(plan_exits)
        self.commands: list[Any] = []

    def plan(self) -> tuple[CliResult, None]:
        code = self.plan_exits.pop(0)
        self.commands.append(type("C", (), {"args": ["plan"], "exit_code": code})())
        return CliResult(("plan",), code, "", "", 0.0), None

    def command(self, *args: str) -> CliResult:
        self.commands.append(type("C", (), {"args": list(args), "exit_code": 0})())
        return CliResult(tuple(args), 0, "", "", 0.0)


def test_a_failed_plan_does_not_stop_convergence():
    # A plan exiting 1 (cross-document selectors not yet resolvable) is followed by an apply.
    run = ScriptedRun([1, 0])
    result = experiment.Run.converge(run)  # type: ignore[arg-type]
    assert result["k"] == 1 and result["converged"] and result["plan_exits"] == [1, 0]


def test_convergence_gives_up_after_k_max_applies():
    run = ScriptedRun([2, 2, 1, 2])
    result = experiment.Run.converge(run)  # type: ignore[arg-type]
    assert result["k"] == experiment.K_MAX and not result["converged"]


def test_nested_rows_record_their_parent_so_names_repeat_safely():
    projects = [
        {"projectId": "p1", "environments": [{"environmentId": "e1", "name": "production"}]},
        {"projectId": "p2", "environments": [{"environmentId": "e2", "name": "production"}]},
    ]
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=projects))
    observer = Observer("http://127.0.0.1:1", "k", {"project.all"}, transport=transport)
    collection = Collection(
        "environment",
        "project.all",
        "environmentId",
        "name",
        (),
        ("environments",),
        parent="projectId",
    )
    view = observer.snapshot([collection])
    assert [row["parent"] for row in view["environment"]] == ["p1", "p2"]
    assert evaluate.duplicated(view) == []


def test_error_bodies_are_logged_without_secret_values():
    log = ProxyLog()
    log.exchanges.append(
        Exchange(
            1,
            "POST",
            "network.create",
            "mutation",
            400,
            0.1,
            error_body='{"message":"bad","echo":"diac-canary-pw-abc"}',
        )
    )
    text = log.to_jsonl(["diac-canary-pw-abc"])
    assert "diac-canary" not in text and "[redacted]" in text and "bad" in text


def _catalog() -> SpecCatalog:
    port = KindSpec(
        "specs/project/port.yaml",
        {
            "kind": "port",
            "scope": "project",
            "parent": "application",
            "section": "ports",
            "api": {"create": {"op": "port.create"}},
            "fields": {
                "protocol": {"type": "enum[tcp, udp]"},
                "target_port": {"api": "targetPort"},
                "note": {"type": "text", "nullable": True},
            },
        },
    )
    application = KindSpec(
        "specs/project/application.yaml",
        {
            "kind": "application",
            "scope": "project",
            "parent": "environment",
            "section": "applications",
            "api": {},
            "fields": {
                "source": {
                    "type": "union(type)",
                    "arms": {
                        "docker": {
                            "image": {"type": "text"},
                            "password": {"type": "text", "mutability": "write_only"},
                        }
                    },
                }
            },
            "write": [{"by_variant": "source", "shape": "full", "ops": {"docker": "x"}}],
        },
    )
    environment = KindSpec(
        "specs/project/environment.yaml",
        {
            "kind": "environment",
            "scope": "project",
            "parent": "project",
            "section": "environments",
            "api": {},
        },
    )
    project = KindSpec("specs/project/project.yaml", {"kind": "project", "scope": "project"})
    return SpecCatalog([port, application, environment, project])


CONTRACT = {
    "/port.create": {
        "post": {
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {"required": ["protocol", "targetPort", "note", "applicationId"]}
                    }
                }
            }
        }
    }
}


def _document(port: dict, source: dict) -> dict:
    return {
        "version": 2,
        "project": {
            "slug": "p",
            "environments": {
                "production": {"applications": {"web": {"source": source, "ports": {"http": port}}}}
            },
        },
    }


def test_lint_reports_the_two_plan_time_rules_and_nothing_else():
    bad = lint(
        _document({"target_port": 80}, {"type": "docker", "image": "x"}), _catalog(), CONTRACT
    )
    assert sorted(f.field for f in bad) == ["protocol", "source.password"]
    good = lint(
        _document(
            {"target_port": 80, "protocol": "tcp"},
            {"type": "docker", "image": "x", "password": None},
        ),
        _catalog(),
        CONTRACT,
    )
    assert good == []


def test_pilot_rounds_are_kept_apart(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DIAC_ROOT", str(tmp_path))
    (tmp_path / "pyproject.toml").write_text("")
    assert live.live_base(True, 1).as_posix().endswith("results/live/pilot")
    assert live.live_base(True, 2).as_posix().endswith("results/live/pilot/round-2")
    assert live.live_base(False).as_posix().endswith("results/live")
    with pytest.raises(typer.BadParameter):
        live.live_base(False, 2)
