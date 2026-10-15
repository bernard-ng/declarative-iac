# 6 Engine algorithms

This section gives the algorithms of the engine. None of them contains knowledge of a particular
kind: every decision that depends on the kind is taken from its specification. The engine has four
entry points. *Plan* compiles a document, discovers the remote state and computes the changes.
*Apply* executes an approved plan. *Recover* settles an apply that was interrupted. *Deploy* runs
deployments, and *import* writes a document from a live instance. Section 6.1 defines the data the
algorithms work on, and Sections 6.2 to 6.4 describe them in pipeline order. The descriptions follow
the reference implementation at `eval-B1`.

## 6.1 Data model

**Three states.** Planning compares three views of each resource. The *desired* state D is compiled
from the document. The *recorded* state S is what the tool last applied and checkpointed. The
*observed* state R is what Dokploy holds now. A resource is identified by its *address*, a path of
`kind.key` segments, and its configuration is a map from *property paths* to values. A property path
is a field at planning granularity: a scalar field, one member of a union arm, one variable of an
environment block, or one member of a set of selectors (Section 5.3).

**Values.** A recorded or desired value is a public value, an explicit `null`, an empty collection, or
a *receipt*: a keyed fingerprint that stands for a secret or a file content without revealing it. The
fingerprint is an HMAC-SHA-256 over the instance, the address, the property path and the value, with
a key held per instance outside the repository.

**Observations.** A projected property is *known* (with a value), *known absent* (`null`), a *receipt*
(for content and environment variables, fingerprinted from what Dokploy returns), or *unknown*, with a
reason such as an invalid response or a secret that cannot be read back. A resource is *present* (with
its remote identifier and properties), *missing*, or *unavailable* (with the reason).

**Durable state.** The recorded state is one file per document. It carries a lineage identifier and a
serial number that protect against stale writes, the identity of the Dokploy instance and of the
document it belongs to, and, for each managed resource, its remote identifier, its containment and
dependencies, its protection flag, its property values or receipts, and the digest of its last
successful deployment. The file is replaced atomically, with a backup, under an exclusive writer lock
that fails immediately when another process holds it. Next to it, an *operation journal* records each
apply as a sequence of steps (Section 6.3).

## 6.2 From document to plan

### Compilation

Compilation turns a parsed and validated document into the desired state.

1. Give every resource its address and its containment parent, following the nesting of the document.
2. Turn every field value into a canonical, comparable value: numbers canonicalised, sets sorted,
   unions reduced to their active arm, environment blocks split into one property per variable, and
   `default: key` applied.
3. For every secret and content value, read its source once, compute its receipt and keep the value
   only in memory that is erased after use; the desired state holds the receipt.
4. Resolve `depends_on` and `ref` to addresses, which become dependency edges.

When a plan is made against a recorded state, one step is added: for every environment variable and
every member of a set of selectors that the recorded state owns and the document no longer names, the
desired state receives an explicit clear, so that the planner removes it (Table 6).

### Discovery and projection

Discovery decides, for every address that the document or the recorded state mentions, whether the
resource is present, missing or unavailable, with as few reads as possible (Algorithm 1).

**Algorithm 1.** Discovery.

```text
input:  desired state D, recorded state S, specifications
output: an observation for every address in D ∪ S

subjects ← addresses of D ∪ S, grouped by kind; each subject carries its recorded remote
           identifier (from S) or its natural key (from D)
load the collections of every kind a selector in D refers to          -- selector index
for each kind k, parents before children:
    if k has a top-level collection:  items ← one read of the collection
    if k is read per parent:          items ← one read per parent present in the outcomes
    if k is embedded in its parent:   items ← the pointer into the parent's direct read (no request)
    if k is a singleton:              items ← the singleton read, with merged reads and fallbacks
    if the read failed:               every subject of the group ← unavailable
    if items repeat an identifier, exceed 10 000 entries, or name another parent:
                                      every subject of the group ← unavailable
    for each subject:
        match ← the item with the recorded identifier, or else
                the unique item whose collision fields equal the subject's natural key
        if no match:     subject ← missing, or unavailable if the collection is partial
        if several:      subject ← unavailable
        if one:          read it directly when the kind has a direct read;
                         if `agree` and the direct read differs on a shared field: unavailable
                         else: present, with the projected properties
a child of a missing parent is missing; a child of an unavailable parent is unavailable
```

Matching by natural key is used only for addresses that the recorded state does not know. A match is
then a candidate for adoption or a collision with an unmanaged resource, which the planner decides.
An item that Dokploy made together with its parent (`made_with_parent`) is excluded from this match,
and so is the resource a `moves` directive is moving.

**Projection** maps the raw response of a present resource onto property paths through the pointers
of the specification. It is tolerant and presence-aware: a field that is not returned is *not
returned*, `null` is a value, a value outside its type or enumeration makes that one property unknown,
and secret and write-only values are dropped at the boundary. Selector fields are translated from the
identifier Dokploy holds into the name the document uses, through the selector index. Content
properties and the variables of environment blocks are then replaced by receipts computed from the
text Dokploy holds, so that an edit made outside the tool is visible as a changed receipt. A response
that cannot be projected makes its resource unavailable and leaves the others unaffected.

### Planning

The planner is a pure function of D, S and the observations R. It returns a set of changes, a set of
drift reports and a set of diagnostics. It first validates the directives (`moves`, `adopt`,
`removed`), checks the dependency graphs for cycles and checks that every selector in D resolves to
exactly one resource; each failure is a diagnostic. It then plans every address of D ∪ S
(Algorithm 2).

**Algorithm 2.** Planning one address.

```text
input:  address a, desired resource d (or none), recorded resource s (or none), observation r
if r is unavailable:                    diagnostic RemoteUnavailable at a; stop
if r is missing:
    d and not s:   adopt-only kind → diagnostic (target missing); else create
    d and s:       adopt-only kind → forget; else create again (drift: deleted outside the tool)
    s only:        forget (deleted outside the tool)
if r is present:
    not s:         d declares adoption or the kind is adopt-only → adopt;
                   otherwise → diagnostic UnmanagedAddressCollision
    s, remote identifier ≠ the recorded one → diagnostic RemoteIdentityMismatch
    s only:        adopt-only kind → forget; protected → diagnostic; else delete
    d and s:       compare properties (Algorithm 3) and classify the mutation
```

**Algorithm 3.** Three-way comparison of the properties of a present resource.

```text
for each property path p in keys(d) ∪ keys(s), except paths in lifecycle.ignore_changes:
    if p ∉ d and p ∈ s:   the document stopped managing p → record it as relinquished
    else:
        require an observation of p (unknown blocks the resource, except for a secret)
        config_changed  ← s[p] ≠ d[p]
        drifted         ← s[p] exists and r[p] ≠ s[p]          (when r[p] is known)
        must_converge   ← r[p] ≠ d[p]   if r[p] is known,  else config_changed
if no property must converge:          a state-only checkpoint (or nothing)
else, for each property that must converge, ask the kind's mutation contract:
    in_place or write_only  → update
    create_only             → replace   (refused for adopt-only or protected resources)
    computed, or a clear of a non-nullable field → diagnostic UnsupportedMutation
```

Two features of Algorithm 3 carry the presence semantics of Section 5.3. A property that the
document omits is in neither `d` nor, after the first apply, `s`, so it is never compared. And a
change made outside the tool is reported as drift but planned only if it moves the resource away
from the document: a remote change that happens to match the document needs a state checkpoint, not
a request. Secrets cannot be observed, so for a write-only property convergence is decided by the
receipts in D and S: the property is written when its source has changed.

**Ordering.** The changes are ordered in three phases. Creates, updates, adoptions, moves and
replacements come first, in topological order of the desired dependency graph, whose edges are
containment and declared dependencies. Deletions and forgets come second, in reverse topological
order of the graph of recorded resources that are being removed, so that children go before their
parents. Changes that touch a `disruptive` property come last. Within a phase, ties are broken by
address, so the order is deterministic.

**Plan outcome.** A plan is *complete* when no address is unobserved or unavailable, and *applyable*
when it has no diagnostic at all. Diagnostics block only the addresses they concern, so the plan for
every other address is still computed and shown. Applying, however, requires an applyable plan; a
single diagnostic prevents the whole apply, and nothing is sent.

## 6.3 Changing the remote state

### Execution

Apply takes the writer lock, reads the recorded state, makes a fresh plan and asks the caller to
approve it (Algorithm 4).

**Algorithm 4.** Apply.

```text
take the writer lock; S ← recorded state; plan ← Plan(D, S, discover(D, S))
if the caller declines:            stop; nothing changed
if plan is not applyable:          stop with its diagnostics; nothing changed
preflight: build every request of every change without sending it; any error → stop
begin a journal operation (plan digest, Dokploy version)
re-read the collections that selectors refer to, so that the identifiers sent are current
for each change, in plan order:
    execute it as one or two journaled steps (below)
    on a definitive rejection:    record the step as failed; stop
    on an unknown outcome:        leave the step open; stop (recovery is required)
    on a verification mismatch:   keep the checkpoint; close the operation; stop
close the journal operation
```

Every step follows the same protocol. Its journal entry, written before any request is sent, records
the action, the address and the exact state the step is expected to produce. The requests are sent.
On success the recorded state is updated to the expected state and checkpointed, and the journal entry
is marked as succeeded. A request whose outcome the transport cannot establish, such as a lost
connection after the request was sent, leaves the entry open and stops the run; the request is never
retried. A definitive error response marks the entry as failed and stops the run. Nothing is rolled
back. The steps differ by change:

- **Create.** If the kind is made with its parent and the parent already holds the row, that row is
  taken over and the remaining properties are written as an update. Otherwise, for `diff_collection`,
  the collection is read before the request. One create request carries every managed property the
  create procedure accepts, together with the attachment to the parent. The new identifier is read from
  the response, or found as the one new item of the collection whose key fields match; if it cannot
  be learned, the step stays open as an unknown outcome. The properties that the create procedure
  does not accept are then written by an update, as a second step, so that an interruption between
  the two leaves a resource that the recorded state describes exactly.
- **Update.** The changed properties are grouped by write group. A `full` group first reads the
  resource and overlays the changes on what Dokploy holds; a `partial` group sends only the changes;
  a `by_variant` group selects the procedure of the arm the document names. Relations add and remove
  one member per request, and per-entry collections write one entry per request. All requests of one
  update are built before the step begins and sent within one step, ordinary groups before disruptive
  ones.
- **Delete.** One remove request is sent, and an HTTP 404 counts as removed. The resource is then read
  again: if it can still be read, the step fails and the resource stays recorded, so the next plan
  removes it again. A resource that Dokploy made with its parent is forgotten instead.
- **Replace.** A delete followed by a create. The executor supports only this order; a replacement
  that would require creating first is refused by the preflight.
- **Adopt, move, forget.** Adoption records the identifier of an existing resource and writes any
  differences with the write groups. A move changes only the address in the recorded state, and is
  followed by an update when the properties also change. A forget removes the resource from the
  recorded state without a request.

**Verification.** After a create or update step succeeds, the resource is read again through the same
projection, and every public property the step wrote must read as written. Secrets are excluded
because they cannot be read back. A mismatch is reported after the step has been checkpointed, so the
next plan shows it as drift, and the run stops.

The executor runs one step at a time. The plan order guarantees that a parent exists before its
children are created and that children are removed before their parents; running steps sequentially
and stopping at the first failure keeps the journal of an interrupted apply to at most one open step.

### Recovery

Recovery settles the one interrupted operation of a document. It never repeats a mutation: it
discovers the resource of the open step again, compares it with the state the step was meant to
produce and with the state before it, and decides (Table 8). A step that had succeeded but whose state
was not yet checkpointed is simply checkpointed. The caller sees the decision, which contains no
value, before anything is recorded.

**Table 8.** Recovery decisions for an open step.

| Open step | Fresh observation | Decision |
|---|---|---|
| create | missing | nothing changed |
| create | present, matching the expected state (secrets excepted) | record the identifier and checkpoint |
| update | matching the expected state | checkpoint the success |
| update | matching the previous state | nothing changed |
| update | matching except for secrets, and the step changed no secret | as above |
| delete | missing | checkpoint the removal |
| delete | present with the recorded identifier | nothing changed |
| move, forget | (state only) | checkpoint |
| deploy | the uniquely titled deployment record is running or done | checkpoint the deployment |
| deploy | that record ended in error or was cancelled | nothing changed |
| any | anything else, unavailable, or a rotated secret | a person decides; nothing is recorded |

A created resource is found by its natural key, because its identifier was never recorded; this is
why the collision fields of a kind must be unique among siblings. An update that rotated a secret
cannot be proven by observation, because the secret cannot be read back, and is left to a person.

### Deployment

Deployment is a separate operation (P11). It requires a converged configuration: a plan for the
document must be complete, applyable and empty. A deployable resource is selected when the caller
names it, or when its `lifecycle.deploy` policy asks for it: `on_create` selects a resource that has
never been deployed, and `on_change` also selects a resource whose *deployment digest* differs from
the one recorded at its last successful deployment. The digest is a hash over the values of the
properties marked `needs_deploy`, so a change to a description does not cause a deployment, while a
change to the image or the environment does. The selected deployments are ordered by the dependency
graph and run up to a configurable number at a time; a deployment whose dependency failed is skipped.

Each deployment is a journaled step. The request carries a title made of the journal operation's
identifier and the step number, so the deployment record that Dokploy creates for it can be found
without ambiguity. When asked to wait, the engine polls the deployment records of the resource until
the record with that title reports `done`, `error` or `cancelled`, or until a timeout. The same title
lets recovery decide an interrupted deployment from the record (Table 8). A successful deployment
records the new digest.

## 6.4 Import and the round-trip proof

Import writes a workspace from a live instance with the same field tables that apply uses (P3).

1. **Inventory.** Read the settings or the project tree with the minimum reads, parents before
   children, combining collection and direct reads.
2. **Allocate keys.** Derive a document key for every resource from its natural key or, for a kind
   without one, from its collision fields, by lower-casing the value and replacing every run of other
   characters with `-`; among siblings of one kind, break collisions with `-2`, `-3`, in order of
   remote identifier.
3. **Map.** Map every property through the specification to a document field. Secrets and environment
   variables follow a classification policy: likely credentials go to secret files referenced by
   sources, and other values stay inline. Content goes to files. Everything that cannot be written is
   listed in an *unsupported ledger*, grouped as unmanaged by choice, unsupported, or unrepresentable.
4. **Render and recompile.** Render each document as canonical YAML, parse it again and compile it.
5. **Prove.** Build the recorded state with the observed identifiers and require that the first plan
   is complete, applyable and empty. A document that would not converge is not written.
6. **Re-read.** Inventory the instance again and require the same identities and containment, so that
   a change made during the import does not produce an inconsistent workspace.
7. **Persist.** Check every destination before the first write, refuse to overwrite an existing
   workspace, write secret files with owner-only permissions and ignore rules, and remove the files
   created by the call if a later write fails.

Step 5 is the round-trip contract of P3 applied to one instance: the document that import writes
describes the instance exactly, in the sense that applying it changes nothing. The full contract,
which rebuilds the instance on a fresh Dokploy and imports it again, is a test of the verification
method (Section 7).

## 6.5 Invariants

Table 9 relates the main invariants of the reference implementation to the algorithms that maintain
them.

**Table 9.** Invariants and the mechanisms that maintain them.

| Invariant | Maintained by |
|---|---|
| Every plan reads fresh state; there is no cache | Algorithm 1 runs for every plan, apply and recovery |
| Only resources recorded as managed can be deleted; unmanaged resources are untouched | Algorithm 2: delete requires a recorded resource; a natural-key match without a record is a collision |
| An omitted field is unmanaged; `null` differs from omission | Algorithm 3 compares only keys of D and S; clears require `nullable` |
| Remote identifiers establish identity | discovery matches by recorded identifier first; identity mismatch is a diagnostic |
| Every successful mutation is journaled and checkpointed | the step protocol of Section 6.3 |
| An uncertain mutation is never retried | unknown outcomes leave the step open; only recovery settles it |
| Protected resources are neither deleted nor replaced | Algorithm 2 and the mutation classification |
| Secrets never appear in state, plans or logs | receipts in D and S; projection drops secrets; errors carry codes, not values |
| No automatic rollback | execution stops at the first failure without compensating requests |
| Plans are deterministic | pure planner; ordering by graph rank, then address |
| Apply followed by plan yields no changes | the proof step of import and the read-back after every step |
