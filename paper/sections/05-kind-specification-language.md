# 5 The kind specification language

A kind specification is one YAML file that describes one resource kind. It states everything the
engine needs to know about the kind and that the API does not say (P1). The specifications are embedded
in the binary when the tool is built, validated when they are loaded, and checked against the API by
the coverage ledger in continuous integration (Section 7). This section presents the language construct by construct. For each
construct it names the mismatch class of Section 3 that the construct closes, and Section 5.5 counts
how often each is used in the 36 Dokploy specifications. The examples are taken from those
specifications, with documentation strings removed.

## 5.1 A complete specification

Listing 1 is the complete specification of the `registry` kind, which describes the credentials of a
container registry. It is one of the simplest kinds and shows the five blocks that every
specification has.

**Listing 1.** The specification of the `registry` kind.

```yaml
kind: registry
scope: settings
section: registries
title: Container registry
class: managed
identity:
  key: name
  collision: [name]
  address: "registry.{key}"
api:
  id: registryId
  create: { op: registry.create }
  update: { op: registry.update }
  remove: { op: registry.remove }
  read:
    list: { op: registry.all, authority: authoritative }
    one: { op: registry.one, id_param: registryId, agree: true }
  create_identity:
    from_response: /registryId
fields:
  name:         { api: registryName, type: text, min_len: 1, default: key }
  type:         { api: registryType, type: "enum[cloud]" }
  url:          { api: registryUrl, type: text }
  username:     { type: text, min_len: 1 }
  password:     { type: text, min_len: 1, class: secret, mutability: write_only }
  image_prefix: { api: imagePrefix, type: text, nullable: true }
write:
  - op: registry.update
    fields: [name, type, url, username, password, image_prefix]
    shape: partial
ledger:
  readonly: [createdAt, organizationId]
  ignored:
    - { field: serverId, reason: "neither stored nor returned by Dokploy 0.30.6 and 0.30.7" }
```

The header places the kind: a settings kind, written under `registries` in the settings document.
`identity` states how a registry is named. `api` names the procedures by their OpenAPI operation
identifiers and states how a new identifier is learned. `fields` lists the configurable fields with
their API names, types, mutability and value class. `write` assigns every changeable field to the
procedure that writes it. `ledger` classifies the response fields that are not configuration. From
this file alone the engine can parse, plan, create, update, delete, verify, recover and import
registries. The rest of this section describes each block in turn.

## 5.2 Kinds, procedures and reads

### Containment and identity

**Containment.** `scope` is `project` or `settings` and selects the document in which the kind
appears. `parent` names the kind that contains it, and `section` the key under which its resources are
written inside the parent; the parent lists the kind under `children`. A resource is written inside
the resource that contains it, so the nesting of a document follows the containment of the instance.

A kind with several possible parents lists them all (M5). What differs by parent is stated beside the
create procedure: `attach` gives the request fields filled from context for every parent, and
`attach_by_parent` adds those that depend on the parent's kind. `parent_field` names, for each parent
kind, the response field that holds the parent's identifier, so that a read can tell which parent a
resource belongs to. Listing 2 shows the declarations for `mount`, which can belong to eight parent
kinds.

**Listing 2.** A kind with several parents (`mount`, excerpt).

```yaml
parent: [application, compose, postgres, mysql, mariadb, mongo, redis, libsql]
api:
  create:
    op: mounts.create
    attach: { serviceId: parent_id }
    attach_by_parent:
      application: { serviceType: application }
      postgres: { serviceType: postgres }
      # ... one entry per parent kind
  parent_field:
    application: applicationId
    postgres: postgresId
    # ... one entry per parent kind
  read:
    list: { embedded_in: { pointer: /mounts }, authority: authoritative }
```

**Identity.** `identity.key` names the field that is the natural key of a resource, usually its name.
It is `null` for a kind whose resources have no name, such as a redirect or a port; the document key is
then purely logical. `collision` lists the fields whose values must be unique among siblings at
Dokploy, which is what a create that learns its identifier by comparison relies on (M6).
`address` is the template for the resource's segment in a hierarchical address, such as
`registry.{key}`.

**Lifecycle.** `class: managed` is the default and means that the tool creates, updates and deletes
resources of the kind. `class: adopt_only` describes a kind that exists independently of the tool
(M7): a declared resource must already exist, the first apply records its identity, and dropping it
from the document forgets it without deleting it. `made_with_parent: { name, marker }` describes a
resource that Dokploy creates together with its parent: a declared resource of that name is taken
over instead of created, written with an update that never carries the key, and forgotten instead of
deleted when the document drops it. `singleton: <key>` describes a settings kind that exists once per
instance and has no collection (M8). Its document section holds the fields directly, and the state
uses the fixed key.

### Procedures

`api.id` names the identifier field used in requests and responses. The procedures of a kind are
`create`, `update`, `remove` and, for a deployable kind, `deploy`; each is given as an operation
identifier `op` with optional attributes:

- `id_param` names the request parameter that carries the identifier;
- `attach` and `attach_by_parent` give request fields filled from context, as above;
- `send` gives typed values sent as written on every call, such as `deleteVolumes: false` on a remove;
- `by_variant` on a create selects the procedure by the variant of a union field (M10), as in
  `{ by_variant: config, ops: { slack: notification.createSlack, ... } }`;
- `from_read` on an update copies request fields from a fresh direct read, for transport identifiers
  that the state does not hold, such as the subtype identifier of a git provider (M1);
- `update_id: false` states that the update procedures of a singleton take no identifier;
- `deploy: { op, wait: deployment }` names the deployment procedure and states that completion is
  observed through Dokploy's deployment records (M12).

**Learning a new identity.** `create_identity` states how the identifier of a created resource is
learned (M6). It takes one of three forms, in order of preference:

1. `from_response: <pointer>` reads it from the create response at a JSON pointer.
2. `diff_collection: { key: [fields] }` reads the collection before and after the create and takes the
   one new item whose key fields match the desired resource.
3. `none` states that the identifier cannot be learned, so the outcome of every create is unknown and
   recovery settles it by observation (Section 6).

The preference order matters because the second form costs two reads and depends on the uniqueness
of the key fields, and the third gives up the ability to finish an apply without recovery.

### Reads

The read declarations state how the current state of a kind is observed and how its absence is proven
(P5). A kind has a collection read, a direct read or both, or, for a singleton, a singleton read.

**Collection reads.** `read.list` takes one of three forms (M4):

- `{ op }` names a procedure that lists every resource of the kind in its scope;
- `{ op, scope: { param, query_by_parent } }` names a procedure that is called once per parent, with
  the parent's identifier in `param`; `query_by_parent` adds the parameters that tell the procedure
  which kind of parent the identifier names, so that one procedure serves several parent kinds (M5);
- `{ embedded_in: { parent_op, pointer } }` states that the collection is part of the parent's direct
  read, at a JSON pointer, and costs no request of its own.

`authority` states what the collection proves. `authoritative`, the default, means that a resource
absent from it does not exist. `partial` means that the collection may hide items, for example by the
caller's role, so absence from it is *unknown*. None of the Dokploy collections needs `partial`.

**Direct reads.** `read.one: { op, id_param }` reads one resource by its identifier. `agree: true`
requires the direct read and the collection item to agree on the identity and on every field they
share; a disagreement makes the observation unavailable rather than a choice between them. `id_from`
names a pointer in the collection item from which the identifier of the direct read is taken when it
differs from `api.id` (M1).

**Singleton reads.** `read.singleton: { op }` names a parameterless procedure. `merge` adds further
procedures whose responses are inserted under named keys before projection, and a `fallback` value is
used when one of them answers HTTP 404 or 500 for a configuration that does not exist yet (M8).

## 5.3 Fields and writes

### Field attributes

The `fields` block maps each field of the document to the API. A field is declared by its document
name and a set of attributes, summarised in Table 5. Fields can be nested: the members of a struct and
the members of each arm of a union are fields in their own right.

**Table 5.** Field attributes.

| Attribute | Meaning | Class |
|---|---|---|
| `type` | the value type (below) | M1 |
| `api` | name or JSON pointer of the field in requests and responses; defaults to the field name | M1 |
| `request`, `list_api` | the request name, or the pointer in a collection item, when either differs from `api` | M1 |
| `mutability` | `in_place`, `create_only`, `write_only` or `computed` (below) | M9, M12 |
| `class` | `public`, `secret` or `content` (below) | M12 |
| `nullable` | `null` is a valid document value and clears the remote value | — |
| `read_nullable` | a remote `null` is a valid observation but cannot be written | M2 |
| `trim`, `read_normalization` | compare without surrounding whitespace; remove a server-generated suffix before comparison | M3 |
| `default: key` | the remote name defaults to the document key | — |
| `fallback` | the value sent when a write needs the field and neither the document nor Dokploy has one | M10 |
| `needs_deploy`, `disruptive` | a change takes effect only after a deployment; a write may restart Traefik or the server | M12 |
| `granularity` | plan a map or set per key, or a struct per member | M11 |
| `membership`, `entry`, `key_selector` | relations and keyed collections written one member at a time (Section 5.3) | M11 |
| `json`, `file_key` | decode a secret source as JSON; accept a dotenv file for an environment block | M12 |

**Types.** The scalar types are `text`, `int`, `number` and `bool`, with optional bounds and patterns,
and `enum[...]`, a closed set in which an unknown remote value is read as *unknown*, not coerced. The
collection types are `list<T>`, compared in order, `set<T>`, compared as a set, and `map<text, T>`. A
`struct{...}` groups named members. A `union(tag)` is a tagged union whose arms list their own members
(M10); `nest` places the arms inside one nested object when Dokploy keeps them so. A `blob(schema)` is
opaque JSON validated against a JSON Schema and compared as one value. An `env` field is an
environment block, stored by Dokploy as one text of `KEY=VALUE` lines and planned per variable. A
`file` field takes its content from a file of the workspace. `ref(kind)` refers to another resource
of the same document, and `selector(kind)` names a resource outside the document by its name; the
engine resolves the name against a fresh read and sends the identifier.

**Mutability.** Every field has exactly one mutability, which fixes how a change is planned:

- `in_place`: a change is written by an update;
- `create_only`: a change replaces the resource, which is refused for a protected resource;
- `write_only`: the value cannot be read back, so it is compared through a fingerprint, and an update
  that must resend it requires its source to be declared;
- `computed`: the value is readable but never configurable, such as a status or an automatically
  generated flag; it serves import and verification only.

A clear (`null`) is accepted only for a `nullable` field. The language also reserves `reparent` for a
field whose change would move a resource to another parent; the Dokploy specifications do not use
it, and a move is expressed instead by changing the resource's address.

**Value class.** Every field has a value class (P11, M12). A `public` value is written as a literal
and kept in the state. A `secret` value is written as a source (an environment variable, a file, or a
reference to a Dokploy vault) and the state keeps only a keyed fingerprint. A `content` value is
written as a file and compared through a fingerprint of its content. A secret field must be
`write_only` or `create_only`, because its value is never kept in the state to be compared or resent. The variables of an
environment block are classified individually, and every variable that comes from a file or an
environment variable is secret unless declared public.

### Write groups

The `write` block partitions the changeable fields of a kind among the procedures that write them
(M9). Each entry is a *write group* with an operation, the fields it carries and a *shape*:

- `partial`: the request carries the identifier and only the fields of the group that changed, for a
  procedure that leaves absent fields unchanged;
- `full`: the request carries the identifier and every field of the group, read fresh and overlaid
  with the changes, for a procedure that requires or overwrites every field.

A field that a `full` procedure requires but that cannot be read back, such as a password, is marked
`resend_on_update`; an update that changes any field of its group then requires the secret's source
to be declared. A write group can be selected by the variant of a union (`by_variant`), with one
operation per arm, as for the source of an application (Listing 3). One operation can serve several
arms, as `saveBuildType` serves every build type.

**Listing 3.** Write groups of the `application` kind (field lists shortened).

```yaml
write:
  - { op: application.update, fields: [name, description, replicas, command, ...], shape: partial }
  - { op: application.saveEnvironment, fields: [environment, build_args, build_secrets, create_env_file],
      shape: full }
  - { op: application.updateTraefikConfig, fields: [traefik_config], shape: full }
  - by_variant: source
    shape: full
    ops: { github: application.saveGithubProvider, gitlab: application.saveGitlabProvider,
           bitbucket: application.saveBitbucketProvider, gitea: application.saveGiteaProvider,
           git: application.saveGitProvider, docker: application.saveDockerProvider }
  - by_variant: build
    shape: full
    ops: { dockerfile: application.saveBuildType, nixpacks: application.saveBuildType, ... }
```

The partition is checked when the specifications are loaded. Apart from the relations and keyed
collections described below, every `in_place` and `write_only` field belongs to exactly one write
group, a `create_only` or `computed` field belongs to none, and the operations of a `by_variant` group
name exactly the arms of its union. A change is written by one request per write group that contains a
changed field, in the order in which the groups are listed, except that groups containing a
`disruptive` field run after the others.

**Relations and keyed collections** belong to no write group, because Dokploy changes them one member
at a time (M11). `membership: { add: { op, member }, remove: { op, member } }` declares a relation:
each added member is one request to `add` and each removed member one request to `remove`, as for the
tags of a project (`tag.assignToProject`, `tag.removeFromProject`). `entry` declares a map whose
entries are read and written one at a time by key, with a `key_format` that maps a document key to the
remote key, as for the dynamic Traefik files of the web server. `key_selector` declares a map whose
keys are themselves names of resources, as for the projects and environments a vault provider is
assigned to.

### Presence semantics

A document says, for every field and resource, whether the tool manages it (P6). The rule is
three-valued and is the same for every kind; the specification decides only which values a field
admits. Table 6 summarises it.

**Table 6.** Presence semantics.

| Element | Omitted | `null` or empty | A value |
|---|---|---|---|
| field | unmanaged: never compared, never written | cleared, only if `nullable` | managed: made to match |
| union member | unmanaged; Dokploy's value is kept while the arm is unchanged | cleared, only if `nullable` | managed |
| environment block or keyed map | unmanaged as a whole | `null` clears every entry; `{}` declares it empty | each named entry is managed; an entry the document named before and no longer names is removed (or only forgotten where the API cannot delete it); other entries are left alone |
| set of selectors, relation | unmanaged | `[]` detaches every member | each named member is attached; a member named before and no longer named is detached; other members are left alone |
| resource | deleted if the state records it as managed (refused if it is protected), forgotten if its kind is adopt-only or made with its parent; untouched if never managed | — | managed |

Two consequences matter for a reader applying the method elsewhere. First, a document can manage a
subset of the fields of a resource, and of the entries of a collection, without erasing the rest.
This is what allows a tool to coexist with changes made through a dashboard. Second, the rule for
collections tracks what the document has *owned*, not only what it names now: an entry that the
document named once and then dropped is removed, while an entry that someone else added is left
alone. The state records which entries the document owns. A resource can also be released without
being deleted by a `removed` directive with `destroy: false`, and individual properties can be
excluded from comparison with `lifecycle.ignore_changes`.

## 5.4 Completeness, validation and derived artefacts

### Ledger declarations and hooks

The `ledger` block classifies the fields of the referenced procedures that are deliberately not
configuration: `readonly` for identifiers, timestamps and status, `derived` for request fields
implied by another field, such as a union tag that the chosen procedure implies, and `ignored` for
fields excluded with a written reason. Together with `fields`, it lets the coverage ledger require
that every field of every referenced procedure is classified (Section 7). `coverage: partial` marks a
kind whose unclassified request fields are counted instead of failing the check; one Dokploy kind,
`project`, carries it, although its ledger has no unclassified field.

A `hook: { name, reason }` registers a function of the engine for a kind whose behaviour the language
cannot express. A hook may replace discovery, the construction of a create request, a step after
create, or the comparison of a property, but never the document model, and it requires a written
reason and tests of its own. No Dokploy specification declares a hook.

### Validation and derived artefacts

When the specifications are loaded, each is checked against the grammar and against the others. The
checks include the following: names are lower snake case; every pointer is a JSON pointer; an
address template contains `{key}` exactly once; every changeable field belongs to exactly one write
group and no other field belongs to one; a secret field is `write_only` or `create_only`, and a
`write_only` field is secret; a union tag is not also a field; a kind made with its parent has
exactly one parent kind; and no kind is defined twice. A specification that fails a check is rejected,
and continuous integration fails.

From the validated specifications the engine derives, without code specific to any kind: a JSON
Schema for editors, the document parser and canonical writer, the compilation of a document to
desired state, the discovery reads, the projection of responses, the mutation contract used by the
planner, the requests for create, update, replacement and removal, the journal steps, the verification
reads, the importer and its convergence proof, the generated reference documentation, and the
conformance scenarios and simulator behaviour of Section 7.

## 5.5 The Dokploy specifications

The 36 specifications describe 19 project kinds and 17 settings kinds. They declare 625 fields,
counting the members of structs and union arms, of which 308 are top-level. By mutability, 532 fields
are `in_place`, 49 `write_only`, 31 `create_only` and 13 `computed`; by value class, 564 are public,
50 secret and 11 content. The changeable fields are divided into 63 write groups, 39 partial and 24
full, of which 3 are selected by variant. The identifier of a new resource is read from the create
response for 19 kinds and learned by comparing collections for 14; the other 3 kinds are adopt-only.
The specification sizes are uneven: a kind declares a median of 8 fields, but `application` declares
106.

Table 7 relates the constructs to the mismatch classes and gives the number of kinds that use each
construct. Every class is closed by at least one construct, and most constructs serve one class.

**Table 7.** Constructs of the language, the mismatch classes they close, and the number of the 36
kinds that use them.

| Class | Constructs (kinds using) |
|---|---|
| M1 Untyped responses, divergent names | `api` pointer (33), `request` (8), `list_api` (4), `read.one.id_from` (4), `update.from_read` (4); tolerant projection for all |
| M2 Asymmetric value rules | `read_nullable` (1) |
| M3 Server-altered values | `read_normalization` (1), `trim` (1) |
| M4 Nested and per-parent collections | `read.list.embedded_in` (14), `read.list.scope` (4), `authority` (all collections), `read.one.agree` (26) |
| M5 Several parent kinds | list-valued `parent` (6), `attach_by_parent` (6), `parent_field` (5), `scope.query_by_parent` (3) |
| M6 Create does not return the identity | `create_identity` with `from_response` (19) or `diff_collection` (14); non-empty `identity.collision` (34) |
| M7 Resources not created or deleted by the client | `class: adopt_only` (3), `made_with_parent` (1) |
| M8 Singletons over several procedures | `singleton` (2), `read.singleton.merge` with `fallback` (1), `update_id: false` (1) |
| M9 Several write procedures | write groups: `partial` (22), `full` (21); `resend_on_update` (4) |
| M10 Per-variant procedures | `union` (6), `by_variant` on write groups (2) and on create (1), `nest` (2), `fallback` (10) |
| M11 Member-at-a-time changes | `granularity: key` (12), `membership` (1), `entry` (1), `key_selector` (1) |
| M12 Secrets, content, side effects | `class: secret` (20), `class: content` (7), `write_only` (19), `env` (10), `file_key` (2), `json` (1), `deploy` and `needs_deploy` (8), `disruptive` (1) |
