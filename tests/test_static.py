from __future__ import annotations

from declarative_iac.domain.static import census, classes, constructs, fixtures, inventory, ledger
from declarative_iac.domain.static.specs import KindSpec, SpecCatalog

EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}


def _op(fields: dict | None = None, query: list[str] | None = None) -> dict:
    op: dict = {"responses": {"200": {"content": {"application/json": {"schema": EMPTY}}}}}
    if fields:
        op["requestBody"] = {"content": {"application/json": {"schema": {"properties": fields}}}}
    if query:
        op["parameters"] = [{"in": "query", "name": name} for name in query]
    return op


DOCUMENT = {
    "paths": {
        "/tag.create": {"post": _op({"name": {}})},
        "/tag.all": {"get": _op()},
        "/tag.one": {"get": _op(query=["tagId"])},
        "/tag.assignToProject": {"post": _op({"tagId": {}, "projectId": {}})},
        "/settings.getWebServerSettings": {"get": _op()},
    }
}

TAG = {
    "kind": "tag",
    "scope": "settings",
    "identity": {"key": "name", "collision": ["name"]},
    "api": {
        "id": "tagId",
        "create": {"op": "tag.create"},
        "read": {"list": {"op": "tag.all"}, "one": {"op": "tag.one", "agree": True}},
        "create_identity": {"from_response": "/tagId"},
    },
    "fields": {"name": {"type": "text"}, "color": {"type": "text", "nullable": True}},
    "write": [{"op": "tag.update", "fields": ["name", "color"], "shape": "partial"}],
}

PATCH = {
    "kind": "patch",
    "scope": "project",
    "parent": ["application", "compose"],
    "identity": {"key": None, "collision": ["file_path"]},
    "api": {
        "id": "patchId",
        "create": {"op": "patch.create", "attach_by_parent": {"application": {"type": "a"}}},
        "read": {"list": {"op": "patch.byEntityId", "scope": {"param": "id"}}},
        "create_identity": {"diff_collection": {"key": ["file_path"]}},
    },
    "fields": {
        "file_path": {"type": "text"},
        "content": {"type": "file", "class": "content", "trim": True},
        "source": {
            "type": "union(type)",
            "arms": {"git": {"url": {"type": "text"}}, "docker": {"image": {"type": "text"}}},
        },
    },
    "write": [
        {"op": "patch.update", "fields": ["file_path", "content"], "shape": "full"},
        {"by_variant": "source", "ops": {"git": "patch.saveGit", "docker": "patch.saveDocker"}},
    ],
}


def catalog() -> SpecCatalog:
    return SpecCatalog(
        [KindSpec("specs/settings/tag.yaml", TAG), KindSpec("specs/project/patch.yaml", PATCH)]
    )


def test_census_roles_follow_the_lexicon_and_flag_empty_responses():
    ops = census.operations(DOCUMENT)
    summary = census.summarise(ops, {"tag.create", "tag.assignToProject", "tag.missing"})
    assert summary["operations"] == 5
    assert summary["routers"] == 2
    assert summary["responses_empty_object"] == 5
    assert summary["roles"]["create"] == 1 and summary["roles"]["list"] == 1
    assert summary["roles"]["other"] == 2
    assert summary["used"]["other"] == 1
    assert summary["used"]["unknown_references"] == ["tag.missing"]
    one = next(op for op in ops if op.name == "tag.one")
    assert one.request_fields == ("tagId",)


def test_field_walk_includes_union_arm_members():
    paths = [path for path, _ in catalog().get("patch").fields]
    assert paths == ["file_path", "content", "source", "source.git.url", "source.docker.image"]


def test_mismatch_tests_are_mechanical():
    assigned = classes.classify(catalog())
    assert assigned["tag"] == []
    assert assigned["patch"] == ["M3", "M4", "M5", "M6", "M9", "M10", "M12"]


def test_construct_counts():
    counts = {row["construct"]: row["count"] for row in constructs.construct_counts(catalog())}
    assert counts["parent.list"] == 1
    assert counts["write.by_variant"] == 1
    assert counts["read.one.agree"] == 1
    assert counts["hook"] == 0


def test_inventory_counts_declarations_and_groups():
    rows = inventory.field_rows(catalog())
    assert len(rows) == 7
    assert sum(row["top_level"] for row in rows) == 5
    assert {row["class"] for row in rows} == {"public", "content"}


def test_ledger_parsing_and_totals():
    text = (
        "kind\tcoverage\tmapped\treadonly\taction\tignored\tderived\tunclassified\n"
        "tag\tFull\t3\t2\t0\t0\t0\t0\n"
        "project\tPartial\t5\t2\t0\t0\t0\t0\n"
    )
    totals = ledger.totals(ledger.parse_coverage(text))
    assert totals["mapped"] == 8 and totals["readonly"] == 4
    assert totals["kinds_partial"] == ["project"]


def test_fixtures_are_counted_per_version():
    files = [
        "fixtures/api/live/v0.30.6/a.json",
        "fixtures/api/live/v0.30.6/b.json",
        "fixtures/api/live/v0.30.7/a.json",
        "fixtures/other.json",
    ]
    assert fixtures.count_by_version(files, "fixtures/api/live") == {"v0.30.6": 2, "v0.30.7": 1}
