"""Which kinds a scenario document declares, read from the document and the kinds' sections.

Used only to describe the scenario set (what is exercised), never as an oracle of behaviour.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from declarative_iac.domain.static.specs import SpecCatalog


def _parents(data: Mapping[str, Any]) -> list[str]:
    parent = data.get("parent")
    if parent is None:
        return []
    return [parent] if isinstance(parent, str) else list(parent)


def _is_singleton(section_value: Any) -> bool:
    return isinstance(section_value, Mapping) and any(
        not isinstance(value, Mapping) for value in section_value.values()
    )


def declared_kinds(document: Mapping[str, Any], catalog: SpecCatalog) -> set[str]:
    """The kinds a version 2 document declares at least one resource of."""

    found: set[str] = set()

    def children(parent: str, resource: Mapping[str, Any]) -> None:
        for spec in catalog:
            if parent in _parents(spec.data) and spec.data.get("section") in resource:
                for child in (resource[spec.data["section"]] or {}).values():
                    found.add(spec.kind)
                    if isinstance(child, Mapping):
                        children(spec.kind, child)

    if "settings" in document:
        body = document["settings"] or {}
        for spec in catalog:
            section = spec.data.get("section")
            if spec.scope != "settings" or section not in body:
                continue
            value = body[section]
            if _is_singleton(value):
                found.add(spec.kind)
                continue
            for resource in (value or {}).values():
                found.add(spec.kind)
                if isinstance(resource, Mapping):
                    children(spec.kind, resource)
    if "project" in document:
        found.add("project")
        children("project", document["project"] or {})
    return found
