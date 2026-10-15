from __future__ import annotations

import pytest

from declarative_iac.domain.static import references

RULES = {
    "simulator": ["sim"],
    "exclusions": [{"kind": "project", "files": ["crates/model/src/read.rs"], "reason": "keyword"}],
    "concerns": {
        "local-server": {"title": "t", "kinds": ["server"], "binding": True},
        "deploy": {
            "title": "d",
            "kinds": ["application"],
            "files": ["crates/sim/src/lib.rs"],
            "binding": True,
        },
    },
}

FILES = {
    "crates/engine/src/a.rs": 'let x = "server";\n// "application" in a comment\n'
    '#[cfg(test)]\nmod tests { "server" }\n',
    "crates/model/src/read.rs": '"project" => project,\n',
    "crates/sim/src/lib.rs": '"application" => "application",\n',
    "crates/engine/tests/it.rs": '"server"\n',
}


def test_references_skip_tests_and_comments_and_count_a_line_once():
    found = references.find(FILES, ["server", "project", "application"])
    assert [(r.file, r.line, r.kind) for r in found] == [
        ("crates/engine/src/a.rs", 1, "server"),
        ("crates/model/src/read.rs", 1, "project"),
        ("crates/sim/src/lib.rs", 1, "application"),
    ]


def test_every_reference_is_classified_and_the_simulator_is_reported_apart():
    rows, unclassified = references.classify(
        references.find(FILES, ["server", "project", "application"]), RULES
    )
    assert unclassified == []
    summary = references.summarise(rows, RULES)
    assert summary["references"] == 1 and summary["excluded"] == 1
    assert summary["simulator"]["references"] == 1


def test_an_unknown_reference_is_reported():
    _, unclassified = references.classify(
        references.find({"crates/engine/src/b.rs": '"tag"\n'}, ["tag"]), RULES
    )
    assert [r.kind for r in unclassified] == ["tag"]


@pytest.mark.parametrize("line", ["#[cfg(test)]"])
def test_production_lines_stop_at_the_test_module(line):
    assert list(references.production_lines(f"a\n{line}\nb")) == [(1, "a")]
