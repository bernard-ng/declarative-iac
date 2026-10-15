# 7 Verification method

Because the API contract describes no response, the kind specifications are the only typed
description of Dokploy that the engine has. Verification must therefore establish four things: that
the specifications agree with the API, that the engine driven by them behaves as Sections 5 and 6
state under normal and failing conditions, that the test double used for most of that work behaves
like Dokploy, and that an instance can be reproduced from its description. The method uses six
layers, summarised in Table 10 and described in this section. For each layer the section states what
it checks and what it leaves unchecked, because the two together determine what the evidence of
Section 9 can support. The descriptions refer to dokploy-iac at `eval-B1`.

**Table 10.** Layers of the verification method.

| Layer | Input | Checks | Runs |
|---|---|---|---|
| Coverage ledger | specifications, OpenAPI documents | every request field of every referenced procedure is classified | every change, both supported versions; weekly against the newest release |
| Recorded responses | captures from live instances | response files exist per kind and version, secrets are redacted | when captured, before review |
| Simulator | specifications, OpenAPI, recorded responses | requests match the contract; responses have the recorded shapes | inside the two layers below |
| Conformance scenarios | one specification | create, update, replace, drift, delete, collisions, faults and recovery, secret leaks | every change, against the simulator |
| Live engine tests | a disposable Dokploy | the engine against the real platform for selected kinds | every change, both supported versions |
| Round-trip gate | a seed workspace, two disposable instances | import, rebuild and re-import yield the same files | every change, both supported versions |

## 7.1 Checking the specifications against the API

### The coverage ledger

The coverage ledger checks that each specification accounts for the procedures it uses (P2). Its
input is the set of specifications and an OpenAPI document. It proceeds in four steps:

1. Index the OpenAPI document: for every operation, collect the names of its request-body fields and
   query parameters.
2. For each specification, collect every operation it references, in its procedures, reads, write
   groups, relations and per-entry collections. An operation that the document does not contain is a
   failure.
3. For each request field of each referenced operation, classify it as *mapped* (a field of the
   specification, including union arms and struct members), *readonly*, *action*, *ignored* (with a
   reason) or *derived*, from the `fields` and `ledger` blocks. A field that falls in none of these
   is *unclassified*; a field listed both as mapped and in the ledger is a contradiction.
4. Check that every mapped field is accepted by the operation of the write group that carries it.

A contradiction, an unknown operation, a mapped field that its operation does not accept, or an
unclassified field of a kind with `coverage: full` fails the check. For a kind with `coverage:
partial`, unclassified fields are counted and reported instead. The check runs in continuous
integration against the OpenAPI documents of both supported versions, and a weekly job runs it
against the document of the newest Dokploy release. That job never changes a specification; it
reports the operations and fields that the release added, removed or changed, as a list of failures
to be classified by a person.

At `eval-B1` the ledger classifies 614 request fields as mapped, 32 as read-only, 23 as ignored and 8
as derived, and leaves none unclassified.

**Scope.** The ledger is mechanical for requests only. The response side is covered differently,
by the recorded responses described next: the specifications name response fields through their pointers and list read-only
response fields in the `ledger` block, but no check at `eval-B1` fails when a recorded response
contains a field that no specification maps or classifies. Such a field is ignored by the projection
(P4). A response-side check, which would apply the same four steps to the field names of the recorded
responses, is a direct extension and is discussed in Section 10.

### Recorded live responses

Response shapes come from responses recorded on live instances. A manually started capture job runs
the digest-pinned Dokploy image of one supported version on a disposable host, creates resources of
each kind through the API, and records the responses of the procedures the specifications use,
including collection and direct reads before and after each create, update and delete. Every capture
passes through a fixed sanitising filter that replaces secrets and instance identifiers, and then
through a checker that requires the expected files for each kind, verifies that every secret field is
redacted, and scans the whole directory for leaked values. The job never commits: its output is
reviewed and added by hand, and recorded files are never edited afterwards. At `eval-B1` the
repository holds 366 recorded files for Dokploy 0.30.6 and 365 for 0.30.7.

The recorded responses are the evidence behind every response pointer in the specifications and
every statement about Dokploy's behaviour in Section 3, and they give the simulator its response
shapes (Section 7.2). Because Dokploy's responses are not typed, a new version is supported only once
its responses have been recorded and reviewed.

### Version compatibility

A file in the repository lists the supported Dokploy versions with their pinned images, and each has
its own OpenAPI document and recorded responses. Before any command that reads or writes through the
engine, the tool reads the server's version. A supported version proceeds. A newer patch release of
a supported minor version proceeds with a warning. Any other version allows reads, such as planning
and import, but refuses mutations unless the user overrides the check explicitly. A version enters the
supported set only once its responses have been recorded and reviewed and the live layers pass on it.

## 7.2 Testing the engine

### The simulator

Most behavioural testing runs against a simulator: an in-memory implementation of the Dokploy API
behind the same transport interface as the HTTP client, so the engine runs against it unchanged. The
simulator, like the engine, contains no knowledge of any kind. It reads the specifications and answers
exactly the operations they reference:

- every request is checked against the request contract generated from the OpenAPI document, and an
  unknown or missing field is answered with HTTP 400;
- a create stores an object under a generated identifier, fills the fields declared read-only, and
  answers HTTP 404 when the parent does not exist;
- an update merges the fields it receives, as Dokploy's recorded updates do;
- a remove deletes the object and everything attached below it;
- a collection read returns the stored objects, filtered by a parent parameter where the
  specification reads per parent, and can hide an object to model a filtered collection;
- a direct read returns the object together with the child collections the specifications declare as
  embedded in it;
- a deploy creates a titled deployment record for applications and Compose stacks.

Responses take their shape from the recorded files: a recorded object acts as a template that says
which keys a response has, each value being taken from the stored object, and literal answers such as
`true` are returned as recorded. A test can inject a fault on the next call, or the n-th call, of an
operation: the request is lost before it is applied, the response is lost after it is applied, the
request is rejected, the request is applied and then reported as rejected (as a registry whose login
fails is still saved), or a read is answered with HTTP 503.

**Scope.** The simulator agrees with Dokploy by construction, through the request contract and the
recorded shapes, not through a differential test that compares the two on the same inputs. It does not
enforce unique names, does not run background work and does not reproduce server-side alterations
such as generated suffixes unless the recorded shapes contain them. The live engine tests below and the round-trip gate (Section 7.3)
exercise what the simulator cannot.

### Specification-derived conformance scenarios

Every kind with `coverage: full` has a test suite that nobody writes by hand. The suite reads the
kind's specification and generates scenarios, each of which runs in a fresh world (simulator,
workspace and engine) and goes through the real engine: the document is parsed, compiled, planned,
applied, recovered where relevant, and read back.

**Generation.** For each field the suite derives a sample value of its type and a second value for
changes, notes the write group that carries it, and supplies secret fields from environment variables
with distinctive *canary* values. A field that defaults to the key is left out of the first document
so that the default is exercised. Selector targets, union arms, structs, keyed collections,
environment blocks and file sources are derived from the specification where the kind has them. A
kind with several parent kinds is exercised under each parent, and a nested kind runs with its
ancestors seeded in the simulator and recorded in the state.

**Scenarios.** Table 11 groups the generated scenarios.

**Table 11.** Conformance scenarios generated from a specification.

| Group | Scenarios and what they require |
|---|---|
| Normal operation | `create`: one apply creates the resource with every field as written, using the create and one write per group for the fields the create does not accept, and the next plan is empty; `create_minimal`: only required fields; `converges`: a second apply sends nothing; `update:<field>`: a change sends exactly its write group's operation with only that group's fields; `replace:<field>`: a create-only change deletes, creates and yields a new identifier; `delete` |
| Drift | `drift:<field>`: a change made behind the engine plans one change naming the field, and apply restores it; content drifts as a receipt, secrets never |
| Safety | `protected_delete`; `unmanaged_collision` and `ambiguous_collision`: one or two existing resources with the same natural key block the plan; `partial_authority`; `read_failure`: an unreadable collection blocks the apply; `foreign_collection_item` and `foreign_direct_read`: a response naming another parent blocks the plan; `selector_unmatched` and `selector_ambiguous`; `declined` |
| Failures and recovery | `rejected_create`; `removal_not_applied`: an acknowledged removal that did nothing fails and is retried by the next apply; `identity_ambiguous`: a concurrent identical create makes the outcome unknown and recovery leaves it to a person; `follow_up_*`: the write after a create is rejected or lost, recovery settles it without repeating the create, and one more apply finishes; `unknown_{create,update,delete}_{before,after}`: the request or its response is lost, the mutation is sent once, recovery takes the right decision, and one more apply converges |
| Secrets | `secrets_from_files` and `secrets_from_vault`: secrets supplied from workspace files or as vault references are written and then plan nothing |

A scenario that does not apply to a kind, such as replacement for a kind without create-only fields,
is skipped with its reason and never silently. Every scenario ends by scanning the workspace, the
state, the journal and everything the scenario printed for the canary values; any occurrence fails
the scenario. The suite requires at least ten passing scenarios for every managed kind and a stated
reason for every skipped one; for an adopt-only kind, creation scenarios are skipped with their reason.
Kinds with unions are additionally run once per arm.

**The suite is itself tested.** A separate test breaks specifications in the ways they go wrong (a
wrong identity pointer, a field mapped to a name the contract does not have, a write group on the
wrong operation) and requires the suite to fail, and the leak scan has a test showing that it can
fail.

**Scope.** The scenarios run against the simulator, with the recorded responses of Dokploy 0.30.6.
They establish that the engine and a specification together behave as specified against a double
that follows the contract; they do not establish by themselves that Dokploy behaves as the specification says.
At `eval-B1`, 35 of the 36 kinds are enrolled; `project`, whose coverage is `partial`, is exercised
by focused engine tests instead.

### Live engine tests

The live tests run the engine against a real Dokploy. For each supported version, continuous
integration starts a disposable stack from the digest-pinned image, runs the tests sequentially, and
always tears the stack down. The tests are written by hand and cover the settings kinds and one
project document. They take resources of each covered kind through their life cycle (create, converge,
update, drift and repair, secret rotation, replacement, adoption for adopt-only kinds, and removal),
exercise every arm of the DNS provider, notification and vault provider unions, resolve selectors by
name, repair an environment variable and a content file edited directly in Dokploy, and deploy an
application until its deployment record reports `done`.

They also include one failure that Dokploy produces on its own: a registry whose login fails is
rejected and saved anyway; recovery closes the failed journal, and the next plan records the remote
value.

**Scope.** The live tests are narrower than the conformance suite: they do not run the generated
scenarios against the real platform, and they inject no artificial faults, since a lost request or
response cannot be produced reliably against a real server. Their role is to confirm, on the real
platform, the behaviours that the simulator copies.

## 7.3 The round-trip gate

The round-trip gate tests the contract of P3 on real instances. For each supported version:

1. Start a fresh instance and apply and deploy a seed workspace.
2. Import the whole instance into a first workspace.
3. Delete the state of a copy of that workspace, start a second fresh instance, and apply and deploy
   the copy on it.
4. Import the second instance into a second workspace.
5. Compare the two workspaces file by file, by path and content digest, excluding the state, which is
   bound to an instance. Any difference fails the gate.

The seed workspace contains a project with shared environment variables and a tag, its `production`
environment, an application with a Docker image source, public and secret environment variables and a
deployment policy, a patch whose content comes from a file, and a settings tag. The gate therefore
checks import, rebuild and re-import for five kinds, including a secret, a content file, a relation,
a resource made with its parent and a deployment.

Two further checks support the contract. Every import proves, before it writes anything, that the
first plan of the document it produced is empty (Section 6.4). And property tests generate random
valid documents and require that rendering and parsing them is an identity.

**Scope.** The gate covers the kinds of its seed workspace, not all 36 kinds.

## 7.4 What the method establishes

Taken together, the layers support three claims. First, every request field of every procedure the
specifications use is accounted for, for both supported versions (Section 7.1). Second, for every
enrolled kind, the engine driven by the specification creates, updates, replaces, deletes, detects and
repairs drift, refuses unsafe changes and recovers from lost requests and responses as Sections 5 and
6 state, against a simulator that follows the request contract and the recorded response shapes
(Section 7.2). Third, on real instances of both versions, the covered kinds live through their
life cycle and the seed workspace survives import, rebuild and re-import (Sections 7.2 and 7.3).

The method leaves four gaps, which bound the evaluation of Section 9 and are discussed in Section 10:
response fields are not classified mechanically; the simulator is faithful by construction rather
than by differential testing; fault injection runs only against the simulator; and the live round
trip covers five kinds.
