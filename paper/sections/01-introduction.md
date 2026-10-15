# 1 Introduction

Infrastructure as code (IaC) has become the standard way to provision and operate software
infrastructure, and it has attracted a growing body of research on its practice, defects and tooling
([Rahman et al. 2018](https://doi.org/10.1016/j.infsof.2018.12.004);
[Guerriero et al. 2019](https://doi.org/10.1109/icsme.2019.00092)). Most current tools are
declarative. The user writes the complete intended state, and the tool reads the current state,
computes the difference and issues the operations that close it. Kubernetes controllers apply the
same principle continuously as *state reconciliation*: each controller observes the cluster and acts
until the observed state matches the declared one
([Burns et al. 2016](https://doi.org/10.1145/2890784)). Terraform and Pulumi apply it on demand,
and Crossplane applies it continuously through Kubernetes controllers. In each case a provider
plug-in translates a desired resource into calls on a vendor API.

Declarative tools need the managed API to make a resource legible. The tool must be able to name a
resource stably, read its current state, tell whether it is absent, change it predictably and learn
the identity of what it creates. Google's API design guidance makes these requirements explicit for
*declarative-friendly* interfaces. Such resources use only standard, strongly consistent methods,
avoid custom methods, carry an etag and expose a reconciling flag while changes are in flight
([AIP-121](https://google.aip.dev/121); [AIP-128](https://google.aip.dev/128)). Cloud vendors that
offer uniform resource access describe each resource type with a schema of identifiers and of
read-only, create-only and write-only properties (AWS Cloud Control API [TODO: cite vendor documentation]). Where an API does not meet
these requirements, the gap is closed by hand: a provider author writes per-resource code that knows
which call creates what, which fields can change and how to read the result back.

Many platforms, particularly self-hosted ones built with remote-procedure-call frameworks, expose
procedures rather than resources. Dokploy, an open-source platform for deploying applications and
databases on one's own servers, is a representative case. Its tRPC API, exported as an OpenAPI 3.1
document, has 604 operations in 57 routers. Only 178 of them (29.5%) have names that resemble create,
read, list, update or delete. Every successful response is declared as an empty object, so the
contract says nothing about what a read returns. A single application is written through a general
`update`, a separate `saveEnvironment`, a `saveBuildType`, and a different procedure for each of its
six source types. A create returns the new object for some resource kinds, a boolean or nothing for
others. Names are not guaranteed to be unique, even among siblings. Some objects exist on every instance and cannot be
created or deleted, and some are created implicitly with their parent. None of these properties is
unusual for an RPC surface designed for a web dashboard. Together, however, they remove most of what
a declarative tool relies on.

Prior work has bridged declarative models and imperative interfaces, but under different
assumptions. Model-driven provisioning generated workflows from declarative object models to drive
procedural provisioning tools ([El Maghraoui et al. 2006](https://doi.org/10.1007/11925071_21)).
TOSCA combined declarative topologies with imperative management plans
([Breitenbücher et al. 2014](https://doi.org/10.1109/ic2e.2014.56)). Research on models at run time
generated synchronisers between running systems and their models from management APIs, and inferred
the models from client code ([Song et al. 2010a](https://doi.org/10.1007/978-3-642-12261-3_14);
[Song et al. 2010b](https://doi.org/10.1007/978-3-642-16129-2_13)). These approaches either target
resource-oriented interfaces or rely on connectors written per resource type, and they do not check
whether a mapping covers the API. More recent IaC research has examined defects in existing engines,
particularly in *state reconciliation*
([Hassan et al. 2024](https://doi.org/10.1145/3660790)), and the testing and verification of IaC
programs and plans ([Sokolowski et al. 2024](https://doi.org/10.1109/tse.2024.3393070);
[Perdereau et al. 2026](https://doi.org/10.5281/zenodo.22747162)). That work assumes a provider layer
already exists. How to supply the missing declarative semantics for a procedure-oriented API, in a form
that is complete, checkable against the API and free of per-resource engine code, has received
little attention.

This report describes such a method and its implementation for Dokploy. The method rests on three
decisions.

1. **Semantics as data.** Everything the API leaves implicit about a resource kind is written once, in a
   declarative *kind specification*. This covers its identity and natural key, the role of each
   procedure, the partition of its fields into *write groups* carried by different procedures, how the
   identity of a new object is learned, which reads prove absence, and the type, mutability and secrecy
   of each field.
2. **A kind-agnostic engine.** The engine contains no knowledge of any kind. It derives document
   parsing, discovery, tolerant projection of untyped responses, three-way planning, journaled
   execution with read-back verification, recovery from uncertain outcomes, deployment and import
   from the specifications.
3. **Mechanical completeness and conformance.** A *coverage ledger* fails the build when any request field of a procedure a
   specification uses is not classified; response shapes come from recorded live captures, because
   the contract has none. Conformance scenarios are generated from each specification and run
   against a simulator built from the contract and those captures, and live tests run the engine
   against real Dokploy instances. A round-trip
   contract states when an instance has been reproduced.

The reference implementation, dokploy-iac, manages 36 resource kinds with 625 fields through 223
of Dokploy's procedures. It supports Dokploy 0.30.6 and 0.30.7.

The report makes five contributions:

1. **A characterisation of the gap** between procedure-oriented APIs and declarative management, as
   twelve classes of mismatch, each illustrated and measured on Dokploy.
2. **A kind specification language** whose constructs close those mismatches, together with
   presence semantics that distinguish unmanaged, cleared and managed values.
3. **The algorithms of a kind-agnostic reconciliation engine**, with the safety invariants they
   preserve, including how uncertain mutations are journaled and settled.
4. **A verification method** that combines the coverage ledger, specification-derived conformance
   scenarios, a simulator whose responses are copied from live
   instances, and a round-trip contract.
5. **An evaluation and a replication guide.** The evaluation covers convergence, idempotency,
   recovery and round trip on Dokploy [RESULT: headline outcome]. The guide gives a step-by-step
   procedure, with the decisions to take at each step, for applying the method to another API.

The scope is deliberately bounded. The method manages an existing platform through its public API
and does not modify that API. Installing the platform, creating the first administrator and API key,
and operational actions such as start, stop and log reading remain outside the declarative model.
Identity and commercial features (users, roles, single sign-on, licensing) are out of scope for the
Dokploy implementation.

The remainder of the report is organised as follows. Section 2 reviews related work. Section 3 analyses
what Dokploy's API leaves out. Section 4 states the design principles. Section 5 presents the
specification language and Section 6 the engine algorithms. Section 7 describes the verification
method. Section 8 explains how to apply the approach to another API, Section 9 reports the evaluation,
and Sections 10 and 11 discuss limitations and conclude.
