# 8 Applying the approach to another API

This section turns Sections 3 to 7 into a procedure for building a declarative control plane over
another procedure-oriented API. It is derived from one implementation, so it states what was needed
for Dokploy and how to decide each point for a different platform; it does not claim that every API
needs every step. The procedure has seven steps (Table 12). Steps 1 to 3 establish what the API does,
steps 4 and 5 produce and check the specifications, and steps 6 and 7 bind and maintain the result.

**Table 12.** The procedure at a glance.

| Step | Input | Output | Main decisions |
|---|---|---|---|
| 1 Fix scope and versions | the platform and its users | list of kinds, non-goals, supported versions | what is configuration, what stays manual |
| 2 Survey the contract | pinned API descriptions | operation census, contract gaps | which roles names do not reveal |
| 3 Record behaviour | disposable pinned instances | recorded responses, contract facts per kind | which probes each kind needs |
| 4 Model the kinds | contract facts | containment tree, document scopes, lifecycle classes | managed, adopt-only, singleton, made with parent |
| 5 Write and check specifications | facts, models | one specification per kind, a clean ledger, passing scenarios | construct per mismatch; extend the language or not |
| 6 Bind the engine | the API's transport and encodings | transport, version check, value encodings | what is platform-specific |
| 7 Maintain | new releases | updated ledger, captures, supported set | when to support a version |

## 8.1 Establishing what the API does

**Step 1: fix the scope and the versions.** List the resource kinds a user configures, and decide for
each operation whether it is configuration or an action. Configuration is state the tool reconciles;
an action, such as starting, stopping, restarting or reading logs, is not modelled and remains an
imperative command. Write down the steps that must stay manual, because the API cannot perform them
or because they establish the tool's own access. For Dokploy these are installing the platform,
creating the first administrator and API key, installing a GitHub App through the dashboard, and
preparing new servers. Choose a small set of supported versions and pin each to an immutable image,
because every later step records behaviour that is specific to a version.

**Step 2: survey the contract.** Pin the machine-readable description of each supported version and
build an operation census as in Section 3.2: operations per module, the role suggested by each name,
and, for each operation, the request fields and the declared response. Three results of the census
decide how much of the later work is necessary. If responses are typed, response shapes can be
taken from the contract and step 3 shrinks; for Dokploy every response is declared empty. If most
operations have standard names and a single write procedure per resource, a name-based mapping is a
reasonable first draft; for Dokploy a third of the operations the specifications need do not. And if
the description declares identifiers, version tags or idempotency keys, the identity and recovery
constructs of Sections 5 and 6 have more to work with.

**Step 3: record behaviour.** Because the contract leaves the essentials unsaid, each kind needs a
small set of probes run against a disposable instance of each supported version. A probe is a script
that creates resources through the API, exercises one question, records the requests and responses,
and deletes what it created. Its results are of two kinds: recorded responses, sanitised and checked
for leaked secrets before review (Section 7.1), and a short file of *contract facts* stating what the
probe proved, such as whether an update is a patch or whether two resources may share a name. Table 13
lists the questions, the probe that answers each, and the specification attribute that records the
answer.

**Table 13.** Probe questions, how to answer them, and where the answer is recorded.

| Question | Probe | Recorded as | Class |
|---|---|---|---|
| Where does a field appear in the collection read, the direct read and each request? | create a resource with every field set; read the collection and the direct read | `api`, `request`, `list_api`, `id_from` | M1 |
| Does a field read back as written? | write a value, read it back, compare | `trim`, `read_normalization`, or a finding for Section 3 | M3 |
| Can a field be cleared? Can it read as `null`? | write `null`; read a fresh resource | `nullable`, `read_nullable` | M2 |
| Which procedure writes a field, and what does it do with absent fields? | send an update with one field; read back the others | write groups, `shape: partial` or `full` | M9 |
| Does a full update require a secret to be resent? | send a full update without the secret | `resend_on_update` | M9, M12 |
| Does the write procedure depend on a variant? | write each variant through each candidate procedure | `union`, `by_variant`, `nest`, `fallback` | M10 |
| Is a field changeable after creation at all? | update it; read back | `mutability: create_only` | — |
| What does a create return? | create; inspect the response | `create_identity` | M6 |
| Are natural keys unique? | create two resources with the same name | `identity.collision`, and a finding | M6 |
| Where are the children of a parent listed? | create a child; read the parent's direct read and every candidate list | `read.list` form, `parent_field`, `query_by_parent` | M4, M5 |
| Can a collection hide items from the caller? | read it with a less privileged key | `authority` | M4 |
| Does the platform create or forbid some resources itself? | create a parent; try to create and delete each child | `class: adopt_only`, `made_with_parent` | M7 |
| Is a setting read and written through several procedures? | call every candidate getter and setter; note 404 or 500 for absent configuration | `singleton`, `merge`, `fallback`, `update_id` | M8 |
| Is a collection changed one member at a time? | add and remove members; look for a delete procedure | `membership`, `entry`, `granularity: key` | M11 |
| Are secrets returned, masked or omitted? | create with a canary secret; read every response | `class: secret`, `mutability: write_only` | M12 |
| Does a write need a deployment, or restart something? | change a field; observe the running service | `needs_deploy`, `deploy`, `disruptive` | M12 |
| What does a remove return, and does a repeated remove fail? | remove; read again; remove again | the delete step of Section 6.3 | — |

Probes also reveal behaviour that no construct needs but that the engine must tolerate, such as a
duplicate that is answered with HTTP 500 instead of a client error, or a rejected request that is
persisted anyway. These belong in the contract facts, because the simulator and the live tests
depend on them.

## 8.2 Producing the specifications

**Step 4: model the kinds.** From the facts, draw the containment tree: which kind is created inside
which, and which kinds can have parents of several kinds. Assign each kind to a document scope, as
Dokploy separates instance settings from projects, and order the scopes so that a kind referenced by
selector is applied first. Classify each kind's lifecycle: *managed* if the tool creates and deletes
it, *adopt-only* if it exists independently of the tool, *made with its parent* if the platform
creates it implicitly, and *singleton* if it exists once per instance. Choose a natural key for each
kind and decide whether the tool must enforce its uniqueness among siblings; this is required
wherever a new identity is learned by comparing collections.

**Step 5: write and check the specifications, one kind at a time.** Begin with the kinds that the
fewest classes of Section 3 affect, so that the engine binding of step 6 is exercised on simple cases
first; for Dokploy that is a flat settings kind such as `tag` or `registry`. For each kind:

1. Write the specification from the facts of step 3, using Table 13 for the attributes.
2. Run the coverage ledger until no request field is unclassified. Classify each remaining field
   explicitly: read-only for identifiers, timestamps and status; derived when another field implies
   it; ignored only with a written reason. An unclassified field is a question to answer with a probe,
   not a field to ignore.
3. Run the generated conformance scenarios against the simulator. A failure points either to the
   specification, when it misstates the API, or to the engine, when the specification is right and
   the generic behaviour is not.
4. Run the kind's live tests on every supported version, and add it to the round-trip seed once its
   import is supported.

**Extend the language, not the engine.** A kind will eventually show a behaviour that no construct
expresses. The rule followed for Dokploy is to add a construct to the language rather than code for
the kind to the engine. A new construct should name the property of the API that makes it necessary,
not the kind that first showed it; it should be validated when specifications are loaded, enforced by
the ledger where it introduces new request fields, and exercised by the generated scenarios. Hooks
remain available as a last resort, with a written reason, but the Dokploy specifications need none.
The twelve classes of Section 3 can serve as a checklist: a new API is likely to exhibit the common
classes (nested collections, hidden identities, several write procedures, secrets and side effects),
and each rare class it exhibits will require its own construct.

## 8.3 Binding and maintaining the engine

**Step 6: bind the engine to the API.** The language, the planner, the state and journal, and the
algorithms of Section 6 contain no knowledge of Dokploy. Six parts are specific to the platform and
must be rewritten for another API:

1. the **transport**, which turns an operation identifier and its fields into a request (for Dokploy,
   a query as an HTTP `GET` with query parameters and a mutation as a `POST` with a JSON body), and
   classifies failures as definitive rejections or unknown outcomes;
2. the **version check**, which reads the server's version and applies the support policy of
   Section 7.1;
3. the **value encodings** that the language exposes as types, such as the `KEY=VALUE` text in which
   Dokploy stores an environment block and the syntax of its vault references;
4. **context values** that requests need but documents do not hold, such as the organization an API
   key acts in;
5. the **observation of deployments**, which for Dokploy relies on titled deployment records;
6. **platform conventions** that the language exposes, such as the server on which Dokploy itself
   runs, which has no identifier and is written as `{ local: true }` in a server selector.

The classification of transport failures deserves particular care, because the recovery guarantees of
Section 6.3 depend on it. A response that proves the request was not applied, such as a validation
error, is a definitive rejection. A connection lost after the request was sent, a timeout, or a
response that cannot be parsed is an unknown outcome and must leave the journal step open.

**Step 7: maintain the specifications.** Run the coverage ledger regularly against the description of
the newest release and treat every new or changed field as work to classify, never as something to
update automatically. Support a new version only after its probes have been run, its responses
recorded and reviewed, and the live tests and the round-trip gate pass on it. Mark a field or
procedure with the versions in which it exists only when behaviour actually differs between supported
versions.

## 8.4 Expected effort

The work is concentrated in steps 3 and 5, and the Dokploy specifications suggest that it depends more
on the mismatch classes a kind exhibits than on the number of its fields. A kind affected by no class
beyond untyped responses, such as `tag`, needs a short specification and its recorded responses. The
most complex kinds, `application` and `web_server`, declare up to 106 fields across several write
groups and procedures, and still need no hook. The few places where the engine still names a kind are
discussed in Section 10.
