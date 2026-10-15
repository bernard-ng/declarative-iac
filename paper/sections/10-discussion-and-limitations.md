# 10 Discussion and limitations

The introduction set out to supply the declarative semantics that a procedure-oriented API leaves out,
in a form that is complete, checkable against the API and free of per-resource engine code. It
proposed three decisions: semantics as data, a kind-agnostic engine, and mechanical completeness and
conformance. This section examines how far each decision holds at `eval-B1` (Section 10.1), where the
engine still names a kind (Section 10.2), what limits the evidence (Section 10.3), and which next steps
those limits suggest (Section 10.4).

## 10.1 What the results support

**Semantics as data.** Thirty-six specifications with 625 fields describe everything the engine needs
to know about Dokploy's resources, and they use 223 of its 604 procedures. Every mismatch class of
Section 3 is closed by a construct of the language (Table 7), and even the most complex kinds,
`application` and `web_server`, need no hook. This is the role that a vendor-published resource schema
plays for AWS Cloud Control API (Section 2.4). The Dokploy specifications show that an integrator can
write such a schema for an API whose vendor did not, provided the schema also records what a
procedure-oriented API adds: the role of each procedure, write groups, identity discovery and read
authority. The OpenAPI generators of Section 2.4, by contrast, leave the mapping from procedures to
resources to hand-written configuration.

**Mechanical completeness.** The coverage ledger leaves no request field of a used procedure
unclassified, for both supported versions (Section 7.1). Completeness is therefore a property the
build checks, not a claim of the author. It holds on the request side only; the response side is
discussed in Section 10.3.

**Behaviour on real instances.** [RESULT: one or two sentences on Q1–Q4, once Section 9 reports the
live runs.] The defects that [Hassan et al. 2024](https://doi.org/10.1145/3660790) found most often in
state reconciliation concern the inventory of managed resources. In the present design the inventory
rests on two specification attributes: which read proves that a resource is absent, and how the
identity of a new object is learned. Experiments L2 and L3 test those attributes on real instances,
through the drift operators that delete or add objects (H4, H5) and through the duplicate and orphan
outcomes of interrupted applies (U1, U2). [RESULT: whether any inventory defect was observed.]

## 10.2 Where the engine still names a kind

Decision 2, principle P1 and Section 6 state that the engine contains no knowledge of any kind. At
`eval-B1` this holds with five exceptions. To find them, every string literal equal to a kind name
was located in the non-test source of the engine-layer crates (59 files), and each occurrence was
classified. Ten occurrences use the word for something else, such as the `project:` root keyword of a
document, whose kind is itself taken from the specifications. The remaining 19 lines, in 10 files,
serve five concerns (Table 17).

**Table 17.** Places where the engine names a kind at `eval-B1`.

| Concern | Kinds named | Lines | Files | Nature |
|---|---|---:|---:|---|
| Deployment records are looked up by deployment type | `application`, `compose` | 4 | 2 | platform binding |
| A null server selector means Dokploy's own host (`{ local: true }`) | `server` | 8 | 7 | platform binding |
| Vault references are resolved through the vault provider kind | `vault_provider` | 2 | 1 | kind knowledge |
| Import recognises the four git-provider kinds as one family | four git providers | 4 | 1 | kind knowledge |
| Import selects project roots by kind name | `project` | 1 | 1 | kind knowledge |

The first two concerns are among the platform-specific parts listed in Section 8.3: how deployments
are observed, and platform conventions such as `{ local: true }`. They account for 12 of the 19 lines
and would be rewritten for another API, with the rest of the binding. The other three are knowledge
about particular kinds, and each has a direct remedy in the language: an attribute that marks a kind
as a source of secret references, a family attribute shared by kinds that differ only in their
provider, and the registry's project root, which the document reader already uses. Section 8's rule
applies here as well: extend the language, not the engine. The simulator, which Section 7 also
describes as free of kind knowledge, names `application` and `compose` on 2 lines, in its emulation
of the same deployment lookup.

The search has a known blind spot. It finds kinds that are named; knowledge expressed through field or
procedure names would not be found. The 19 lines are therefore a lower bound on kind-specific engine
code, obtained by a mechanical rule whose classifications are listed with the results.

## 10.3 Threats to validity

**Construct validity.** The twelve mismatch classes and their boundaries are the author's judgement.
The kind counts of Table 3 follow from mechanical tests on the specifications and are reproducible,
but a different coder could draw the classes differently. A second, independent classification with
a measure of agreement would strengthen Section 3.

**Completeness of observation.** The coverage ledger classifies request fields only. Because the
contract declares every response as an empty object, the shapes of responses come from 731 recorded
files, and a response field that the specifications misread is found only when a recorded or live
response contradicts it. The independent read-only client of Section 9 reduces this gap for the 16
kinds it observes, but it does not close it.

**Fidelity of the simulator.** The simulator is faithful by construction: it applies the request
contract and returns the recorded shapes. No differential test compares its answers with Dokploy's on
the same requests. The conformance results of Section 7.2, including all fault-injection results,
transfer to Dokploy only as far as the simulator copies it. Experiment L3 injects faults on real
instances for three scenarios and so tests the fault behaviour directly, but only for the kinds those
scenarios declare. [RESULT: whether L3 agreed with the simulator's fault model.]

**Internal validity.** The same person built the system, the harness and the scenarios. The harness
limits what this can bias: it runs the system as a black box, its oracles do not read the
specifications, and its hypotheses were fixed before the live runs. A shared misconception would
still pass unnoticed, for example a planning rule that is wrong in both the engine and the expected
plan of a lifecycle scenario.

**External validity.** The evaluation covers one platform and two adjacent versions whose 604
operations are identical, on a single host. The procedure of Section 8 has not yet been applied to a
second API, so its generality is argued, not shown. Within Dokploy, 9 of the 36 kinds are not
exercised by the live scenarios because they need external accounts, a second host or key material,
and deployments are outside the live experiments. The round trip of L4 covers 15 kinds, three times
the five of the system's own gate (Section 7.3), but not all 36.

## 10.4 Future work

The limits above suggest five next steps, in order of the evidence they would add:

1. Run the pre-registered experiments on both versions and report them in Section 9, including every
   violating run.
2. Classify response fields mechanically, by checking each specification's read paths against the
   recorded responses, and run the check beside the request-side ledger.
3. Test the simulator differentially, by replaying the generated conformance scenarios against a real
   instance and comparing request and response sequences.
4. Move the three kind-specific concerns of Table 17 into the specification language, and repeat the
   search of Section 10.2 as a check in continuous integration.
5. Apply the procedure of Section 8 to a second self-hosted platform with a procedure-oriented API,
   with a second coder classifying its mismatches independently.
