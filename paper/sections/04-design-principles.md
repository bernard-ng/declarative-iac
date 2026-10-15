# 4 Design principles

The mismatches of Section 3 can be closed in more than one way. This section states the eleven
principles that fix the approach taken here, each with the reason for it. Sections 5 to 7 describe the
mechanisms that implement them. The principles fall into three groups: where knowledge about the API
is kept (P1 to P3), how the remote state is observed and owned (P4 to P7), and how it is changed
(P8 to P11). The reference implementation documents them as 29 invariants; the principles give the reasons
for those invariants.

## 4.1 Knowledge about the API

**P1 Semantics as data, an engine without kinds.** Everything a declarative tool must know about a
kind and that the API does not say is written once, as data, in the kind's specification. The engine
reads specifications and contains no knowledge of any kind: parsing, discovery, projection, planning,
execution, verification, recovery and import are each one algorithm for all kinds.

*Reason.* Section 3 showed that the missing information is per kind and per field, and that rare
mismatches are as costly to handle as common ones. If that information were spread through engine
code, every new kind or field would require changes in several components, and the components
could disagree with each other. As data, it exists in one place, a new field is one entry, and the
information can be checked against the API (P2) and turned into tests (Section 7). Behaviour that a
specification cannot express may be added as a hook registered for a kind, but only with a written
justification in the specification and tests of its own. None of the 36 specifications declares a
hook.

**P2 The specification is checked against the API, field by field.** Every request and response field
of every procedure that a specification uses must be classified: mapped to a field of the
specification, read-only, an action input, derived, or ignored with a written reason. The check fails
on any unclassified field, on any procedure the API does not have, and on any specified field the
API no longer has. Request fields are checked mechanically against the OpenAPI document; response fields, which the
document does not describe, are taken from responses recorded on live instances, and a mechanical
check of them is not yet implemented (Section 7.1).

*Reason.* Since the contract says nothing about responses (M1), the specifications are the only
typed description of the API that the tool has. An unchecked specification would be as untrustworthy
as the contract it replaces. Classifying every field turns "the specifications cover the API" from a
claim into a test, and a new Dokploy release that adds or removes a field appears as a precise list of
failures rather than as a silent misreading.

**P3 One mapping, used in both directions.** Import, which writes a document from a live instance,
uses the same field table as apply, which writes a live instance from a document. There is no importer
per kind. The two directions are tied together by a *round-trip contract*: importing an instance,
applying the result to a fresh instance of the same version and importing again yields the same
document, up to a fixed list of values that Dokploy generates.

*Reason.* Separate forward and reverse mappings drift, and a field that is applied but not imported is
lost the next time an instance is exported. Requiring that both directions use one table makes such a
loss a defect of one specification, not of two programs. The round-trip contract also gives a testable
meaning to "this document describes that instance", which is the goal of managing an instance from a
repository.

## 4.2 Observation and ownership

**P4 Observe fresh, project tolerantly.** Every plan reads the current state of Dokploy; there is no
persistent cache of the API. Responses are projected onto the properties of a kind through the
pointers in its specification. A field that is not returned is *not returned*, which differs from
`null`; a value outside its declared type or enumeration is *invalid* for that one property; and
unknown response fields are ignored. Unknown fields in a document, by contrast, are rejected.

*Reason.* The responses are untyped and can change between releases (M1), and some values are
returned in a different form than they were written (M2, M3). A projection that fails on the first
unexpected field would make the tool unusable after any Dokploy update. A projection that guesses
would plan wrong changes. Projecting only what the specification names, and marking everything else
explicitly, keeps a reading error local to the property it concerns. The asymmetry between responses
and documents is deliberate: Dokploy may add fields, but a user's misspelt field must not be silently
ignored.

**P5 Absence must be proven, and uncertainty blocks only what it concerns.** A resource is *missing*
only when a read that the specification declares authoritative for its kind, in its scope, does not
contain it. A read that fails, or that contradicts itself or another read, makes exactly the addresses
it covers *unavailable*. Planning for an unavailable address is blocked; the rest of the plan is
still computed and reported, but an apply requires a plan without diagnostics.

*Reason.* Many collections are nested in a parent or read per parent (M4, M5), so an absent child can
be mistaken for a deleted one when the parent was not read correctly. A tool that inferred absence
from a failed or partial read would plan to create a resource that exists or would forget one it
manages. Blocking only the affected addresses keeps the plan informative: it shows exactly which
resources could not be observed and what would change elsewhere. Refusing to apply a plan with any
diagnostic keeps an apply from running on a view of the instance that the tool knows to be partial.

**P6 Ownership is explicit, and presence has three values.** In a document, an omitted field is
*unmanaged*: it is never compared and never written. A field written as `null` is *cleared*, which is
allowed only where the API accepts a clear. A field with a value is *managed*. The same rule applies to
resources: only resources that the state records as managed can be deleted, and a remote resource
that the tool does not manage is never changed. When a resource to be created has the natural key of
an existing unmanaged one, the plan reports a collision and stops instead of adopting it implicitly.

*Reason.* A Dokploy instance is also edited through its dashboard, and some objects exist whether or
not the user declares them (M7). Partial management must therefore be safe: a document that declares
only some fields, or only some resources, must not erase the rest. Distinguishing "not mentioned"
from "cleared" is what makes that possible, and refusing implicit adoption prevents a document from
taking over a resource that someone else created with the same name.

**P7 Remote identifiers are identity; addresses are labels.** The identity of a managed resource is
the identifier Dokploy assigned, recorded in the state. The address of a resource is a hierarchical
path of document keys, such as `project.shop/environment.staging/application.api`, and serves only to
name it in documents, plans and commands. Renaming an address changes only the state, never the remote
resource. Each kind's specification states how the identifier of a new resource is learned and which
fields form its natural key.

*Reason.* Dokploy does not always return the identifier of what it creates, and it does not enforce
unique names (M6). A tool that identified resources by name would confuse two resources with the same
name and would lose track of a resource whose name changed. Recording the remote identifier once it is
known, and stating per kind how it becomes known, makes identity independent of display names.

## 4.3 Changing the remote state

**P8 Planning is pure; execution follows the plan.** The planner is a deterministic function of the
desired state, the observed state and the recorded state. It has no access to the network and produces
the same plan for the same inputs. The executor performs only the changes in an approved plan. Before
the first request is sent, every request is built once without being sent, so that a change the
executor cannot make is reported before anything changes.

*Reason.* A plan is what a user reviews and approves, so it must describe exactly what will happen.
A pure planner can be tested exhaustively without a Dokploy instance, and building every request in
advance turns errors that would otherwise appear halfway through an apply into errors before it.

**P9 Every mutation is sent once; uncertainty is settled by observation.** Each change is recorded in a
journal, with the state it is expected to produce, before its request is sent, and the state is
updated when the request succeeds. A request whose outcome is unknown, such as one interrupted by a
lost connection or a create whose identifier cannot be learned, is never retried. The step stays
open, and a separate recovery reads the resource again and decides whether the change happened. When
the evidence does not decide it, nothing is recorded and a person decides. A definitive rejection by
Dokploy stops the run, and nothing is rolled back automatically.

*Reason.* Dokploy's procedures are not idempotent, and the contract declares no idempotency keys, version
tags or conditional requests. A
create sent twice can produce two resources with the same name (M6), and the second cannot be told
from the first by name. Retrying is therefore unsafe, and so is guessing. Journaling every step before
it is sent ensures that an interruption leaves a record of what may have happened, and stopping at the
first rejection keeps that record short and the state consistent with it.

**P10 Every write is verified by reading it back.** After each step, the resource is read again through
the same projection, and every public property that the step wrote must read as written. A mismatch is
recorded and reported, so the next plan shows it as drift. A deletion that Dokploy acknowledges while
the resource can still be read fails the step.

*Reason.* One resource is written through several procedures with different rules for absent fields
(M9, M10), and some values are altered by the server (M3). An acknowledgement from a procedure is
therefore weak evidence that the intended state was reached. Reading back turns the property "apply
followed by plan yields no changes" into a check made after every step rather than an assumption
tested only later.

**P11 Secrets and side effects are explicit.** Every field has a value class: *public*, *secret* or
*content*. A secret is given in a document as a source, such as an environment variable or a file, never
as a literal. It is read only when a request needs it, and the state keeps only a keyed fingerprint.
Plans name the property that changes, never its value. Effects beyond storing a value are explicit
too: apply never deploys on its own, deployment follows a per-resource policy or an explicit command,
and changes that may restart Traefik or the server require explicit approval and run after all
other changes.

*Reason.* Many kinds hold secrets that Dokploy masks or omits, file contents, environment blocks or
writes with side effects (M12). The state and the documents are kept in a repository, so a secret
stored there would be published. Since secrets cannot be read back, they are compared through
fingerprints, which detect a change without revealing the value. Making deployments and restarts
explicit separates changing the configuration of a service from running it, which a user may want to
schedule separately.

## 4.4 Principles and mismatches

Table 4 relates the principles to the classes of Section 3. Each class is addressed by at least one
principle, and the specification constructs that implement them are presented in Section 5.

**Table 4.** Principles and the mismatch classes that motivate them.

| Principle | Main classes addressed | Section |
|---|---|---|
| P1 Semantics as data, an engine without kinds | all | 5, 6 |
| P2 The specification is checked against the API | M1 | 7 |
| P3 One mapping, used in both directions | M1, M3, M12 | 6, 7 |
| P4 Observe fresh, project tolerantly | M1, M2, M3 | 6 |
| P5 Absence must be proven | M4, M5, M8 | 5, 6 |
| P6 Ownership is explicit, presence has three values | M7, M11 | 5, 6 |
| P7 Remote identifiers are identity | M6, M7 | 5, 6 |
| P8 Planning is pure | M9, M10 | 6 |
| P9 Every mutation is sent once | M6, M9 | 6 |
| P10 Every write is verified by reading it back | M3, M9, M10 | 6 |
| P11 Secrets and side effects are explicit | M12 | 5, 6 |
