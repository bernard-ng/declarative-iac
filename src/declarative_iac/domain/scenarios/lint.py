"""Plan-time requirements a scenario must meet, checked offline (S6-scenarios).

`dokploy validate` checks a document on its own. Two further rules are checked by the system only
when it plans or applies against an instance, and the first pilot round (DEVIATIONS.md) showed
that scenarios can break them:

1. **Required on create.** A field that the create procedure's request requires (OpenAPI
   `required`) and that the specification gives no `default`, `fallback` or `nullable` must be
   declared; otherwise the plan reports DOKPLAN018.
2. **Write-only members of full write groups.** A write group with shape `full` replaces every
   member, so a write-only member (for example `source.docker.password`) must be declared, as
   `null` if it is unused, whenever the group is written; otherwise apply refuses the change.

These are rules about scenario validity, read from the pinned specifications and contract; they
are not used as oracles of behaviour.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from declarative_iac.domain.static.specs import KindSpec, SpecCatalog


@dataclass(frozen=True)
class Finding:
    address: str
    rule: str
    field: str

    def __str__(self) -> str:
        return f"{self.address}: {self.rule} `{self.field}`"


def _parents(spec: KindSpec) -> list[str]:
    parent = spec.data.get("parent")
    return [] if parent is None else [parent] if isinstance(parent, str) else list(parent)


def _singleton(value: Any) -> bool:
    return isinstance(value, Mapping) and any(not isinstance(v, Mapping) for v in value.values())


def resources(document: Mapping[str, Any], catalog: SpecCatalog) -> Iterator[tuple[str, str, dict]]:
    """(kind, address, body) for every resource a version 2 document declares."""

    def children(
        parent: str, address: str, body: Mapping[str, Any]
    ) -> Iterator[tuple[str, str, dict]]:
        for spec in catalog:
            section = spec.data.get("section")
            if isinstance(section, str) and parent in _parents(spec) and section in body:
                for key, child in (body[section] or {}).items():
                    child = dict(child or {})
                    child_address = f"{address}/{spec.kind}.{key}"
                    yield spec.kind, child_address, child
                    yield from children(spec.kind, child_address, child)

    if "settings" in document:
        settings = document["settings"] or {}
        for spec in catalog:
            section = spec.data.get("section")
            if spec.scope != "settings" or section not in settings:
                continue
            value = settings[section]
            if _singleton(value):
                yield spec.kind, spec.kind, dict(value)
                continue
            for key, body in (value or {}).items():
                yield spec.kind, f"{spec.kind}.{key}", dict(body or {})
    if "project" in document:
        project = dict(document["project"] or {})
        address = f"project.{project.get('slug')}"
        yield "project", address, project
        yield from children("project", address, project)


def required_on_create(spec: KindSpec, contract: Mapping[str, Any]) -> list[str]:
    create = ((spec.api.get("create") or {}) if isinstance(spec.api, Mapping) else {}).get("op")
    if not create:
        return []
    schema = (
        contract.get(f"/{create}", {})
        .get("post", {})
        .get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )
    required = set(schema.get("required", []))
    return [
        name
        for name, field in (spec.data.get("fields") or {}).items()
        if isinstance(field, Mapping)
        and field.get("api", name) in required
        and not any(key in field for key in ("default", "fallback"))
        and not field.get("nullable")
        and field.get("mutability") != "computed"
    ]


def _write_only(field: Any) -> bool:
    return isinstance(field, Mapping) and (
        field.get("mutability") == "write_only" or field.get("class") == "secret"
    )


def full_group_members(spec: KindSpec, body: Mapping[str, Any]) -> list[str]:
    """Write-only members of full write groups that `body` writes but does not declare."""

    fields = spec.data.get("fields") or {}
    missing: list[str] = []
    for group in spec.data.get("write") or []:
        if group.get("shape") != "full":
            continue
        if "by_variant" in group:
            union = str(group["by_variant"])
            declared = body.get(union)
            if not isinstance(declared, Mapping):
                continue
            arm = declared.get("type")
            members = ((fields.get(union) or {}).get("arms") or {}).get(arm) or {}
            missing += [
                f"{union}.{name}"
                for name, field in members.items()
                if _write_only(field) and name not in declared
            ]
            continue
        group_fields = group.get("fields") or []
        if not any(name in body for name in group_fields):
            continue
        missing += [n for n in group_fields if _write_only(fields.get(n)) and n not in body]
    return missing


def lint(
    document: Mapping[str, Any], catalog: SpecCatalog, contract: Mapping[str, Any]
) -> list[Finding]:
    findings: list[Finding] = []
    for kind, address, body in resources(document, catalog):
        spec = catalog.get(kind)
        findings += [
            Finding(address, "required on create, not declared:", name)
            for name in required_on_create(spec, contract)
            if name not in body
        ]
        findings += [
            Finding(address, "write-only member of a full write group, not declared:", name)
            for name in full_group_members(spec, body)
        ]
    return findings
