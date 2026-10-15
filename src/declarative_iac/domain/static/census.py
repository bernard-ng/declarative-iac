"""The operation census of an OpenAPI document (paper Section 3.2, Table 2)."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

# A procedure gets a standard role when the last segment of its name is one of these words
# (Section 3.2). Every other name is `other`.
LEXICON: dict[str, str] = {
    "create": "create",
    "one": "read_one",
    "get": "read_one",
    "all": "list",
    "getAll": "list",
    "list": "list",
    "search": "list",
    "update": "update",
    "remove": "delete",
    "delete": "delete",
}
ROLES = ("create", "read_one", "list", "update", "delete", "other")
EMPTY_OBJECT = {"type": "object", "properties": {}, "additionalProperties": False}


@dataclass(frozen=True)
class Operation:
    router: str
    procedure: str
    method: str
    response_empty: bool
    request_fields: tuple[str, ...]

    @property
    def name(self) -> str:
        return f"{self.router}.{self.procedure}"

    @property
    def role(self) -> str:
        return LEXICON.get(self.procedure, "other")


def _request_fields(operation: dict[str, Any]) -> tuple[str, ...]:
    names = {p["name"] for p in operation.get("parameters", []) if p.get("in") == "query"}
    schema = (operation.get("requestBody", {}).get("content", {}).get("application/json", {})).get(
        "schema", {}
    )
    names.update((schema.get("properties") or {}).keys())
    return tuple(sorted(names))


def operations(document: dict[str, Any]) -> list[Operation]:
    """Every operation of a tRPC OpenAPI export, whose paths are `/<router>.<procedure>`."""

    found: list[Operation] = []
    for path, item in document["paths"].items():
        name = path.lstrip("/")
        router, _, procedure = name.rpartition(".")
        for method, operation in item.items():
            schema = (
                operation.get("responses", {})
                .get("200", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema")
            )
            found.append(
                Operation(
                    router=router,
                    procedure=procedure,
                    method=method.upper(),
                    response_empty=json.dumps(schema, sort_keys=True)
                    == json.dumps(EMPTY_OBJECT, sort_keys=True),
                    request_fields=_request_fields(operation),
                )
            )
    return sorted(found, key=lambda op: (op.name, op.method))


def non_crud_group(op: Operation) -> str:
    """The group of a used operation without a standard name (Section 3.2)."""

    if op.procedure == "deploy":
        return "deploy"
    if op.procedure == "saveEnvironment":
        return "saveEnvironment"
    if op.router == "application":
        return "application source, build and proxy"
    if op.router == "notification":
        return "notification per provider"
    if op.router == "settings":
        return "settings"
    return "other"


def summarise(ops: list[Operation], used: set[str]) -> dict[str, Any]:
    used_ops = [op for op in ops if op.name in used]
    standard = [op for op in ops if op.role != "other"]
    used_other = [op for op in used_ops if op.role == "other"]
    return {
        "operations": len(ops),
        "routers": len({op.router for op in ops}),
        "methods": dict(sorted(Counter(op.method for op in ops).items())),
        "responses_empty_object": sum(op.response_empty for op in ops),
        "roles": {role: sum(op.role == role for op in ops) for role in ROLES},
        "standard_named": len(standard),
        "standard_named_percent": round(100 * len(standard) / len(ops), 1),
        "used": {
            "operations": len(used_ops),
            "routers": len({op.router for op in used_ops}),
            "roles": {role: sum(op.role == role for op in used_ops) for role in ROLES},
            "other": len(used_other),
            "other_percent": round(100 * len(used_other) / len(used_ops)),
            "other_groups": dict(sorted(Counter(non_crud_group(op) for op in used_other).items())),
            "unknown_references": sorted(used - {op.name for op in ops}),
        },
    }
