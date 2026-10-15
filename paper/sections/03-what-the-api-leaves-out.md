# 3 What a procedure-oriented API leaves out

This section states what a declarative tool needs from the API it manages, measures how far Dokploy's
API departs from it, and organises the departures into twelve classes of mismatch. The classes are
the requirements that the specification language of Section 5 must meet. All figures refer to the
OpenAPI documents of Dokploy 0.30.6 and 0.30.7, which give identical counts, and to the 36 kind
specifications of dokploy-iac at tag `eval-B1`.

## 3.1 What declarative management needs from an API

A declarative tool runs one loop for every resource it manages. It discovers the resource, compares
the observed state with the desired one, plans the operations that close the difference, executes them
and verifies the result by reading the resource again. Each step makes an assumption about the API.
Six assumptions, N1 to N6, follow from this loop and from the guidance for declarative-friendly APIs
([AIP-121](https://google.aip.dev/121); [AIP-128](https://google.aip.dev/128)):

- **N1 Typed observation.** A read returns the resource in a documented shape, under the field names
  that writes use, and a value reads back as it was written.
- **N2 Provable absence.** One collection read enumerates every resource of a kind in its scope, so a
  resource missing from that read is known to be absent.
- **N3 Learnable identity.** A create returns the identifier of the new resource, and the natural key
  that a user writes is unique among siblings.
- **N4 Client-controlled lifecycle.** Every managed resource is created and deleted through explicit
  requests, and only through them.
- **N5 Uniform mutation.** One standard update changes any mutable field of a resource, and its effect
  is limited to the fields it carries.
- **N6 Comparable values and known effects.** Secrets and file contents can be compared without being
  stored in plain text, and the side effects of a write, such as a redeployment or a restart, are known
  before it is issued.

Resource-oriented APIs meet most of these assumptions by construction, and a provider can then map a
resource to a fixed set of operations. A procedure-oriented API meets few of them, as the rest of this
section shows for Dokploy.

## 3.2 The Dokploy API

Dokploy's API is written with tRPC and exported as an OpenAPI 3.1 document. It contains 604 operations
in 57 routers, each named `router.procedure`. Queries are exposed as `GET` (226 operations) and
mutations as `POST` (378). Every operation declares its successful response as an empty object, so
the document describes what a client may send but not what it receives.

The role of each operation can be estimated from its name alone. An operation was given a standard
role when the last segment of its name is `create`; `one` or `get` (read one); `all`, `getAll`, `list`
or `search` (list); `update`; or `remove` or `delete`. All other names were classed as *other*. Table 2
gives the result for the whole API and for the 223 operations, in 37 routers, that the 36
specifications use.

**Table 2.** Operations of the Dokploy API by role inferred from the name.

| Role by name | Whole API | Used by the specifications |
|---|---:|---:|
| create | 34 | 32 |
| read one | 41 | 34 |
| list | 30 | 15 |
| update | 37 | 33 |
| delete | 36 | 31 |
| other | 426 | 78 |
| **Total** | **604** | **223** |

Only 178 of the 604 operations (29.5%) have a standard name. Among the operations the specifications
use, 78 of 223 (35%) do not. They fall into six groups: 24 per-provider `create*` and `update*`
procedures of the `notification` router, 23 `settings` procedures that read or write one part of the
instance configuration, 8 `saveEnvironment` procedures, 8 `deploy` procedures, 8 `application`
procedures that write its source, build type or proxy configuration, and 7 others, such as
`environment.byProjectId` and `tag.assignToProject`. A mapping derived from names would therefore miss
a third of the operations that declarative management of Dokploy requires.

A standard name does not settle an operation's behaviour either. `registry.update` changes only the
fields it receives and answers `true`. `ai.update` is an upsert and fails with HTTP 500 unless every
column is sent. `redirects.create` answers `true` rather than the new record. These differences are not visible in the contract, which declares the same empty response for all three.
The number of operations a specification names varies widely between kinds: the median is 5, but
`notification` uses 27, `web_server` 23 and `application` 15.

## 3.3 Twelve classes of mismatch

The classes were obtained from the specification language. Its constructs were first separated into
those any declarative schema needs (types, natural key, and the create, read, update and delete
operations of a kind) and the rest. Each remaining construct was then assigned to the property of the
API that makes it necessary, and constructs with the same cause were merged into one class. Each class
is paired with a test on the specifications, given in the last column of Table 3. The number of kinds
affected is the number of specifications that pass the test, so the counts can be recomputed from the
specifications alone. The classification itself is the author's, made once, and Section 10 returns to
this threat.

**Table 3.** Classes of mismatch between Dokploy's API and declarative management, with the number of
the 36 kinds affected.

| Class | Assumption broken | Dokploy example | Kinds | Test on the specification |
|---|---|---|---:|---|
| M1 Untyped responses and divergent names | N1 | the git providers' collection holds the name at `name`, their direct reads at `/gitProvider/name` | 36 (8) | all kinds; in brackets, kinds that name a field differently in request, collection or direct read |
| M2 Asymmetric value rules | N1 | `organization.logo` reads as `null` but cannot be written as `null` | 1 | a field readable as null but not writable as null |
| M3 Server-altered values | N1 | an application's `appName` is stored with a random six-character suffix | 2 | a field normalised before comparison |
| M4 Nested and per-parent collections | N2 | ports are listed only inside `application.one` | 18 | collection embedded in the parent's read or queried per parent |
| M5 One kind under several parent kinds | N2 | a mount belongs to an application, a Compose stack or one of six database kinds | 6 | more than one parent kind |
| M6 Create does not return the identity | N3 | `security.create` answers `true` | 14 | identity learned by comparing the collection before and after the create |
| M7 Resources the client cannot create or delete | N4 | `project.create` also makes a `production` environment, which cannot be deleted on its own | 4 | adopt-only kind, or kind made with its parent |
| M8 Singletons spread over several procedures | N2, N5 | the web-server settings are read through 9 procedures and written through 14 | 2 | kind with a single instance and no collection |
| M9 One resource written through several procedures | N5 | an application is written through `update`, `saveEnvironment`, `updateTraefikConfig` and others | 15 | more than one write procedure |
| M10 Per-variant procedures | N5 | each of 12 notification providers has its own create and update | 2 | procedure chosen by a union variant |
| M11 Relations and keyed collections changed one member at a time | N5 | tags are assigned to a project one at a time | 2 | membership or per-entry operations |
| M12 Secrets, content and side effects | N6 | DNS and Vault provider secrets read back as `********` | 26 | secret or content field, environment block, deployment or disruptive write |

### Observation (N1)

**M1 Untyped responses and divergent names.** Because every response is declared empty, no kind can be
read through generated types; the shape of each response is known only from recorded responses of a
live instance. Field names add a second problem in 8 kinds. The four git-provider kinds share one
collection read, `gitProvider.getAll`, which carries a name at `name` and a subtype identifier inside a
nested object, while their direct reads and updates use the subtype identifier and nest the name
under `/gitProvider`. Notifications accept `webhookUrl` in a request but return it below an object
named after the provider, such as `/slack/webhookUrl`. A tool that assumes one name per field cannot
read these kinds back after writing them.

**M2 Asymmetric value rules.** Some values can be read but not written. The organization's logo is
returned as `null` when none is set, while `organization.update` accepts an omitted logo or a string
but rejects an explicit `null`. A tool that writes back
what it read, as an import followed by an apply does, fails on such a field unless it knows the
asymmetry.

**M3 Server-altered values.** Dokploy changes some values on the way in. It appends a random
six-character suffix to the Docker-level name of an application, and it adds a trailing newline to the
content of a patch when the content has none. In both cases a read after a successful write differs
from what was sent, and a naive comparison would plan the same change on every run.

### Absence (N2)

**M4 Nested and per-parent collections.** Of the 36 kinds, 16 have a flat collection read and 2 are
singletons. The other 18 do not. For 14 of them the collection exists only inside the direct read of
the parent: ports, redirects and HTTP basic-auth entries are found only in `application.one`, and the
applications of an environment only in `environment.one`. For the other 4 the collection is a query
that takes the parent's identifier, such as `environment.byProjectId`. Proving that a resource is
absent therefore requires its parent to be read first, and the read plan depends on the kind.

**M5 One kind under several parent kinds.** Six kinds can belong to parents of different kinds. A
mount or a volume backup can belong to an application, a Compose stack or any of six database kinds;
a backup belongs to one of five database kinds; and a domain, a patch or a schedule belongs to an
application or a Compose stack. The procedures differ by parent: the create takes a different
identifier field for each parent kind, and a per-parent query such as `schedule.list` needs both the
parent's identifier and a parameter that names its kind.

### Identity and lifecycle (N3, N4)

**M6 Create does not return the identity.** Of the 36 kinds, 33 can be created through the API. The
specifications read the new identifier from the create response for 19 of them and learn it for the
other 14 by listing the collection before and after the create and taking the one new item that matches
the natural key. Comparison is necessary where the response carries no identifier:
`redirects.create` and `security.create` answer `true`, and every notification create answers an empty
body. Even where a response does carry the identifier, the contract does not promise it, because the
response is declared empty. Comparison by natural key in turn requires the key to be unique, which
Dokploy does not enforce for several kinds, among them AI providers, certificates, registries,
servers and SSH keys.

**M7 Resources the client cannot create or delete.** Four kinds do not follow a client-controlled
lifecycle. `project.create` creates a `production` environment as a side effect; a second environment
of that name is refused, and the environment cannot be deleted on its own. The organization and the
local web server are created when Dokploy is installed and cannot be created or deleted through the
API. A GitHub provider can be updated through the API but is created only through the dashboard's
GitHub App installation. A tool that treats every declared resource as creatable, and every undeclared
one as deletable, fails or does damage on these kinds.

**M8 Singletons spread over several procedures.** Two settings kinds exist exactly once per instance
and have neither a collection nor an identifier of their own. The organization is read through one
parameterless procedure. The web-server settings are read through `settings.getWebServerSettings` and
seven further procedures, some of which answer HTTP 404 or 500 when an optional file or port
configuration does not exist yet. Its dynamic Traefik files have their own read procedure (M11). The
settings are written through 13 procedures, plus one that writes a Traefik file. Together they make the
`web_server` kind the most fragmented in the API: 23 operations for one object.

### Mutation and effects (N5, N6)

**M9 One resource written through several procedures.** Fifteen kinds are written through more than one
procedure. An application is written through `update`, `saveEnvironment`, `updateTraefikConfig`,
`saveBuildType` and one procedure per source type; each database kind through `update` and
`saveEnvironment`. The procedures also differ in how they treat fields they do not receive. Across
the 36 specifications, the fields of each kind are divided into 63 *write groups*, one per procedure:
39 groups are partial: the procedure leaves absent fields unchanged, so only changed fields are sent.
The other 24 are full: the procedure requires or overwrites every field of the group, so the whole
group must be sent, read fresh and overlaid with the changes. A full update must therefore also resend
secrets the tool cannot read back, which happens in four kinds.

**M10 Per-variant procedures.** Two kinds are polymorphic, and the procedure that writes them depends
on the variant. An application's source is written through one of six `save*Provider` procedures,
selected by the source type. A notification is created and updated through one of 12 pairs of
procedures, such as `notification.createSlack` and `notification.updateSlack`, selected by the
provider. Changing the variant therefore changes which procedure is called, not only which values are
sent.

**M11 Relations and keyed collections changed one member at a time.** A project's tags are not a field
of the project: `tag.assignToProject` and `tag.removeFromProject` add and remove one tag at a time, and
the direct read returns the assigned tags as an array of link objects. The web server's dynamic
Traefik files are read and written one file at a time, by path, and the API has no procedure to delete
one. A declarative set of tags or files must therefore be planned member by member.

**M12 Secrets, content and side effects.** Twenty-six kinds have at least one value that cannot be
compared naively or a write whose effect goes beyond storing it. Twenty kinds hold secrets, 50
properties in all. Dokploy returns some secrets masked as `********` and omits others; a registry's
password, for example, appears in the collection read but not in the direct read. Seven kinds hold file contents (11 properties), and ten hold environment-variable blocks whose
entries must be treated as sensitive. Eight kinds (the application, the Compose stack and the six
database kinds) take effect only after a deployment, which is a separate procedure, and some writes
to the web-server settings may restart Traefik or the server.

## 3.4 Summary

Every kind is affected by at least one class, because no response is typed (M1). Counting only the
classes that a specification must declare explicitly, a kind is affected by a median of 3 classes
(range 0 to 6). Only `tag` is affected by none, and `web_server` is affected by six. The classes
differ in frequency. Four of them, nested collections (M4), hidden identities (M6), several write
procedures (M9) and secrets and side effects (M12), each affect between 14 and 26 kinds, so they
shape the design of the specification language and the engine. The other eight affect between 1 and
8 kinds each (M1 by its narrower test), but each still requires its own construct, because no
general mechanism covers it.

Two consequences follow for the method. First, the missing information is per kind and per field, so
it cannot be supplied once for the whole API; it must be recorded for each kind. Second, most of it
cannot be found in the contract. It comes from recorded responses and from the behaviour of a live
instance, so a specification must be checked against both. Section 5 presents the language that
records this information, and Section 7 the method that checks it.
