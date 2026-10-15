"""Counts over the specifications that the paper reports (Sections 3.2, 3.3 and 5.5)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from declarative_iac.domain.static.classes import classify
from declarative_iac.domain.static.specs import KindSpec, SpecCatalog, distribution


def _type_base(declaration: dict) -> str:
    match = re.match(r"[a-z_]+", str(declaration.get("type", "")))
    return match.group(0) if match else ""


def field_rows(catalog: SpecCatalog) -> list[dict[str, Any]]:
    """One row per field declaration, including struct and union-arm members."""

    rows = []
    for spec in catalog:
        for path, declaration in spec.fields:
            rows.append(
                {
                    "kind": spec.kind,
                    "path": path,
                    "top_level": "." not in path,
                    "type": _type_base(declaration),
                    "mutability": declaration.get("mutability", "in_place"),
                    "class": declaration.get("class", "public"),
                    "nullable": bool(declaration.get("nullable", False)),
                    "needs_deploy": bool(declaration.get("needs_deploy", False)),
                }
            )
    return rows


def _web_server_procedures(spec: KindSpec) -> dict[str, int]:
    singleton = spec.reads.get("singleton") or {}
    candidates = [
        singleton.get("op"),
        *((m or {}).get("op") for m in (singleton.get("merge") or {}).values()),
    ]
    writes_found: list[object] = list(spec.write_operations())
    for _, declaration in spec.fields:
        entry = declaration.get("entry") or {}
        if entry:
            candidates.append((entry.get("read") or {}).get("op"))
            writes_found.append((entry.get("write") or {}).get("op"))
    reads = {str(op) for op in candidates if op}
    writes = {str(op) for op in writes_found if op}
    return {"read_procedures": len(reads), "write_procedures": len(writes)}


def kind_rows(catalog: SpecCatalog, known_operations: set[str]) -> list[dict[str, Any]]:
    classes = classify(catalog)
    rows = []
    for spec in catalog:
        parent = spec.data.get("parent")
        rows.append(
            {
                "kind": spec.kind,
                "scope": spec.scope,
                "class": spec.data.get("class", "managed"),
                "coverage": spec.data.get("coverage", "full"),
                "parents": parent if isinstance(parent, list) else ([parent] if parent else []),
                "read_form": spec.read_form(),
                "create_identity": spec.create_identity() or "",
                "creatable": bool(spec.api.get("create")),
                "fields": len(spec.fields),
                "top_level_fields": len(spec.data.get("fields") or {}),
                "write_groups": len(spec.write_groups),
                "write_procedures": len(spec.write_operations()),
                "procedures": len(spec.operations_named(known_operations)),
                "classes": classes[spec.kind],
            }
        )
    return rows


def summarise(catalog: SpecCatalog, known_operations: set[str]) -> dict[str, Any]:
    fields = field_rows(catalog)
    kinds = kind_rows(catalog, known_operations)
    by_kind = {row["kind"]: row for row in kinds}
    groups = [group for spec in catalog for group in spec.write_groups]

    def kinds_with(column: str, value: Any) -> int:
        return len({row["kind"] for row in fields if row[column] == value})

    def props(column: str, value: Any) -> int:
        return sum(row[column] == value for row in fields)

    web = catalog.get("web_server")
    notification = catalog.get("notification")
    application = catalog.get("application")
    source_ops = next(g["ops"] for g in application.write_groups if g.get("by_variant") == "source")
    return {
        "kinds": len(catalog),
        "scopes": dict(sorted(Counter(row["scope"] for row in kinds).items())),
        "fields": {
            "declarations": len(fields),
            "top_level": sum(row["top_level"] for row in fields),
            "mutability": dict(sorted(Counter(row["mutability"] for row in fields).items())),
            "class": dict(sorted(Counter(row["class"] for row in fields).items())),
            "per_kind": distribution([row["fields"] for row in kinds]),
            "largest_kind": max(kinds, key=lambda row: row["fields"])["kind"],
            "secret_kinds": kinds_with("class", "secret"),
            "content_kinds": kinds_with("class", "content"),
            "secret_properties": props("class", "secret"),
            "content_properties": props("class", "content"),
            "env_kinds": kinds_with("type", "env"),
        },
        "write_groups": {
            "total": len(groups),
            "shapes": dict(sorted(Counter(str(g.get("shape", "partial")) for g in groups).items())),
            "by_variant": sum("by_variant" in g for g in groups),
            "kinds_with_several_write_procedures": sum(
                row["write_procedures"] > 1 for row in kinds
            ),
            "kinds_with_resend_on_update": len(
                catalog.kinds(lambda s: s.field_has("resend_on_update", True))
            ),
        },
        "create_identity": dict(
            sorted(Counter(row["create_identity"] or "not_creatable" for row in kinds).items())
        ),
        "creatable_kinds": sum(row["creatable"] for row in kinds),
        "read_forms": dict(sorted(Counter(row["read_form"] for row in kinds).items())),
        "deployable_kinds": len(catalog.kinds(lambda s: bool(s.api.get("deploy")))),
        "hooks": len(catalog.kinds(lambda s: bool(s.data.get("hook")))),
        "procedures_per_kind": {
            **distribution([row["procedures"] for row in kinds]),
            "notification": by_kind["notification"]["procedures"],
            "web_server": by_kind["web_server"]["procedures"],
            "application": by_kind["application"]["procedures"],
        },
        "parents": {row["kind"]: len(row["parents"]) for row in kinds if len(row["parents"]) > 1},
        "web_server": _web_server_procedures(web),
        "notification_providers": len((notification.api.get("create") or {}).get("ops") or {}),
        "application_source_procedures": len(set(source_ops.values())),
        "classes_per_kind": {
            **distribution([len(row["classes"]) for row in kinds]),
            "kinds_with_none": [row["kind"] for row in kinds if not row["classes"]],
            "kinds_with_most": [
                row["kind"]
                for row in kinds
                if len(row["classes"]) == max(len(r["classes"]) for r in kinds)
            ],
        },
    }
