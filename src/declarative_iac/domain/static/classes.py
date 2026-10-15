"""The mechanical test of each mismatch class (paper Section 3.3, Table 3).

Each class pairs a description with a predicate on one specification. The number of kinds affected
is the number of specifications for which the predicate holds, so it can be recomputed from the
specifications alone. M1 holds for every kind (no response is typed); its bracketed count is the
narrower test given here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from declarative_iac.domain.static.specs import KindSpec, SpecCatalog


@dataclass(frozen=True)
class MismatchClass:
    id: str
    title: str
    test: str
    predicate: Callable[[KindSpec], bool]


def _deploys_or_secret(spec: KindSpec) -> bool:
    return (
        spec.field_has("class", "secret")
        or spec.field_has("class", "content")
        or any(str(d.get("type", "")) == "env" for _, d in spec.fields)
        or bool(spec.api.get("deploy"))
        or spec.has_key("disruptive", True)
    )


CLASSES: tuple[MismatchClass, ...] = (
    MismatchClass(
        "M1",
        "Untyped responses and divergent names",
        "a field named differently in request, collection or direct read",
        lambda s: any(s.has_key(k) for k in ("request", "list_api", "id_from", "from_read")),
    ),
    MismatchClass(
        "M2",
        "Asymmetric value rules",
        "a field readable as null but not writable as null",
        lambda s: s.has_key("read_nullable", True),
    ),
    MismatchClass(
        "M3",
        "Server-altered values",
        "a field normalised before comparison",
        lambda s: s.has_key("read_normalization") or s.has_key("trim", True),
    ),
    MismatchClass(
        "M4",
        "Nested and per-parent collections",
        "collection embedded in the parent's read or queried per parent",
        lambda s: s.read_form() in ("embedded", "scoped"),
    ),
    MismatchClass(
        "M5",
        "One kind under several parent kinds",
        "more than one parent kind",
        lambda s: isinstance(s.data.get("parent"), list),
    ),
    MismatchClass(
        "M6",
        "Create does not return the identity",
        "identity learned by comparing the collection before and after the create",
        lambda s: s.create_identity() == "diff_collection",
    ),
    MismatchClass(
        "M7",
        "Resources the client cannot create or delete",
        "adopt-only kind, or kind made with its parent",
        lambda s: s.data.get("class") == "adopt_only" or bool(s.data.get("made_with_parent")),
    ),
    MismatchClass(
        "M8",
        "Singletons spread over several procedures",
        "kind with a single instance and no collection",
        lambda s: bool(s.data.get("singleton")),
    ),
    MismatchClass(
        "M9",
        "One resource written through several procedures",
        "more than one write procedure",
        lambda s: len(s.write_operations()) > 1,
    ),
    MismatchClass(
        "M10",
        "Per-variant procedures",
        "procedure chosen by a union variant",
        lambda s: s.has_key("by_variant"),
    ),
    MismatchClass(
        "M11",
        "Relations and keyed collections changed one member at a time",
        "membership or per-entry operations",
        lambda s: s.has_key("membership") or s.has_key("entry"),
    ),
    MismatchClass(
        "M12",
        "Secrets, content and side effects",
        "secret or content field, environment block, deployment or disruptive write",
        _deploys_or_secret,
    ),
)


def classify(catalog: SpecCatalog) -> dict[str, list[str]]:
    """For each kind, the classes whose test it passes."""

    return {spec.kind: [c.id for c in CLASSES if c.predicate(spec)] for spec in catalog}


def class_counts(catalog: SpecCatalog) -> dict[str, dict[str, object]]:
    return {
        c.id: {
            "title": c.title,
            "test": c.test,
            "kinds": catalog.kinds(c.predicate),
            "count": len(catalog.kinds(c.predicate)),
        }
        for c in CLASSES
    }
