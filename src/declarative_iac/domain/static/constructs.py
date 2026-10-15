"""How often each construct of the specification language is used (paper Table 7)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from declarative_iac.domain.static.specs import KindSpec, SpecCatalog


def _op(spec: KindSpec, name: str) -> dict:
    value = spec.api.get(name)
    return value if isinstance(value, dict) else {}


def _type_is(spec: KindSpec, wanted: str) -> bool:
    return any(str(d.get("type", "")) == wanted for _, d in spec.fields)


@dataclass(frozen=True)
class Construct:
    id: str
    mismatch: str
    label: str
    predicate: Callable[[KindSpec], bool]


CONSTRUCTS: tuple[Construct, ...] = (
    Construct("field.api", "M1", "`api` pointer", lambda s: s.field_has("api")),
    Construct("field.request", "M1", "`request`", lambda s: s.field_has("request")),
    Construct("field.list_api", "M1", "`list_api`", lambda s: s.field_has("list_api")),
    Construct(
        "read.one.id_from",
        "M1",
        "`read.one.id_from`",
        lambda s: "id_from" in (s.reads.get("one") or {}),
    ),
    Construct(
        "update.from_read", "M1", "`update.from_read`", lambda s: "from_read" in _op(s, "update")
    ),
    Construct(
        "field.read_nullable", "M2", "`read_nullable`", lambda s: s.field_has("read_nullable", True)
    ),
    Construct(
        "field.read_normalization",
        "M3",
        "`read_normalization`",
        lambda s: s.field_has("read_normalization"),
    ),
    Construct("field.trim", "M3", "`trim`", lambda s: s.field_has("trim", True)),
    Construct(
        "read.list.embedded_in",
        "M4",
        "`read.list.embedded_in`",
        lambda s: "embedded_in" in s.list_read,
    ),
    Construct("read.list.scope", "M4", "`read.list.scope`", lambda s: "scope" in s.list_read),
    Construct(
        "read.one.agree",
        "M4",
        "`read.one.agree`",
        lambda s: (s.reads.get("one") or {}).get("agree") is True,
    ),
    Construct(
        "parent.list",
        "M5",
        "list-valued `parent`",
        lambda s: isinstance(s.data.get("parent"), list),
    ),
    Construct(
        "attach_by_parent",
        "M5",
        "`attach_by_parent`",
        lambda s: any("attach_by_parent" in _op(s, o) for o in ("create", "update", "remove")),
    ),
    Construct("parent_field", "M5", "`parent_field`", lambda s: bool(s.api.get("parent_field"))),
    Construct(
        "scope.query_by_parent",
        "M5",
        "`scope.query_by_parent`",
        lambda s: "query_by_parent" in (s.list_read.get("scope") or {}),
    ),
    Construct(
        "create_identity.from_response",
        "M6",
        "`create_identity: from_response`",
        lambda s: s.create_identity() == "from_response",
    ),
    Construct(
        "create_identity.diff_collection",
        "M6",
        "`create_identity: diff_collection`",
        lambda s: s.create_identity() == "diff_collection",
    ),
    Construct(
        "identity.collision",
        "M6",
        "`identity.collision`",
        lambda s: bool((s.data.get("identity") or {}).get("collision")),
    ),
    Construct(
        "class.adopt_only",
        "M7",
        "`class: adopt_only`",
        lambda s: s.data.get("class") == "adopt_only",
    ),
    Construct(
        "made_with_parent",
        "M7",
        "`made_with_parent`",
        lambda s: bool(s.data.get("made_with_parent")),
    ),
    Construct("singleton", "M8", "`singleton`", lambda s: bool(s.data.get("singleton"))),
    Construct(
        "read.singleton.merge",
        "M8",
        "`read.singleton.merge`",
        lambda s: "merge" in (s.reads.get("singleton") or {}),
    ),
    Construct(
        "update_id.false", "M8", "`update_id: false`", lambda s: s.api.get("update_id") is False
    ),
    Construct(
        "write.partial",
        "M9",
        "write groups `partial`",
        lambda s: any(g.get("shape") == "partial" for g in s.write_groups),
    ),
    Construct(
        "write.full",
        "M9",
        "write groups `full`",
        lambda s: any(g.get("shape") == "full" for g in s.write_groups),
    ),
    Construct(
        "field.resend_on_update",
        "M9",
        "`resend_on_update`",
        lambda s: s.field_has("resend_on_update", True),
    ),
    Construct("type.union", "M10", "`union`", lambda s: s.field_type_starts("union")),
    Construct(
        "write.by_variant",
        "M10",
        "`by_variant` on write groups",
        lambda s: any("by_variant" in g for g in s.write_groups),
    ),
    Construct(
        "create.by_variant",
        "M10",
        "`by_variant` on create",
        lambda s: "by_variant" in _op(s, "create"),
    ),
    Construct("field.nest", "M10", "`nest`", lambda s: s.field_has("nest")),
    Construct("field.fallback", "M10", "`fallback`", lambda s: s.field_has("fallback")),
    Construct(
        "granularity.key", "M11", "`granularity: key`", lambda s: s.field_has("granularity", "key")
    ),
    Construct("field.membership", "M11", "`membership`", lambda s: s.field_has("membership")),
    Construct("field.entry", "M11", "`entry`", lambda s: s.field_has("entry")),
    Construct("field.key_selector", "M11", "`key_selector`", lambda s: s.field_has("key_selector")),
    Construct("class.secret", "M12", "`class: secret`", lambda s: s.field_has("class", "secret")),
    Construct(
        "class.content", "M12", "`class: content`", lambda s: s.field_has("class", "content")
    ),
    Construct(
        "mutability.write_only",
        "M12",
        "`write_only`",
        lambda s: s.field_has("mutability", "write_only"),
    ),
    Construct("type.env", "M12", "`env`", lambda s: _type_is(s, "env")),
    Construct("field.file_key", "M12", "`file_key`", lambda s: s.field_has("file_key")),
    Construct("field.json", "M12", "`json`", lambda s: s.field_has("json", True)),
    Construct("api.deploy", "M12", "`deploy`", lambda s: bool(s.api.get("deploy"))),
    Construct(
        "field.needs_deploy", "M12", "`needs_deploy`", lambda s: s.field_has("needs_deploy", True)
    ),
    Construct("disruptive", "M12", "`disruptive`", lambda s: s.has_key("disruptive", True)),
    Construct("hook", "-", "`hook`", lambda s: bool(s.data.get("hook"))),
)


def construct_counts(catalog: SpecCatalog) -> list[dict[str, object]]:
    rows = []
    for construct in CONSTRUCTS:
        kinds = catalog.kinds(construct.predicate)
        rows.append(
            {
                "construct": construct.id,
                "mismatch": construct.mismatch,
                "label": construct.label,
                "count": len(kinds),
                "kinds": kinds,
            }
        )
    return rows
