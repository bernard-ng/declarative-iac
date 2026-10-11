# 2 Related work

Four lines of work bear on this report. They are reviewed from the most general to the closest:
declarative configuration and its convergence, reconciliation in cluster managers, bridging
declarative models and imperative interfaces, and the analysis and generation of tooling from API
descriptions. The section ends with a summary of how the present method differs.

## 2.1 Declarative configuration and convergence

Declarative configuration management predates cloud IaC. CFEngine introduced *convergent* operations,
which move a host towards the state a policy implies whatever its starting point
([Burgess 2005](https://doi.org/10.5220/0001159201830188)). Couch and Sun formalised convergence
algebraically ([Couch & Sun 2003](https://doi.org/10.1007/978-3-540-39671-0_4)). They also showed
that, for a single host and some classes of process, reproducibility of the observed effect can be
verified statically ([Couch & Sun 2004](https://doi.org/10.1016/j.scico.2004.04.002)). Testing work
turned these notions into checks on real scripts. [Hummer et al. 2013](https://doi.org/10.1007/978-3-642-45065-5_19)
proposed model-based testing of idempotence and found non-idempotent automations in public
repositories. [Hanappi et al. 2016](https://doi.org/10.1145/2983990.2984000) tested *reliable
convergence* under transient faults. They showed that when a pairwise *preservation* property holds
between resources, the whole configuration converges without every execution order being enumerated.
Rehearsal checks Puppet manifests for determinism and idempotence
([Shambaugh et al. 2016](https://doi.org/10.1145/2908080.2908083)). Tortoise repairs configurations
after manual changes have made a system drift from its specification
([Weiss et al. 2017](https://doi.org/10.1109/ase.2017.8115673)). More generally, idempotence is the
property that makes retry-based fault tolerance correct
([Ramalingam & Vaswani 2013](https://doi.org/10.1145/2429069.2429100)).

Empirical studies of IaC have since characterised what goes wrong in practice. These include defect
taxonomies of IaC scripts ([Rahman et al. 2020](https://doi.org/10.1145/3377811.3380409)), security
smells ([Rahman et al. 2019](https://doi.org/10.1109/icse.2019.00033)), and faults in the engines of
Ansible, Puppet and Chef ([Drosos et al. 2024](https://doi.org/10.1145/3689799)).
[Hassan et al. 2024](https://doi.org/10.1145/3660790) studied 5,110 defects in *state
reconciliation*, the step that queries and compares infrastructure state before changing it, and
found eight categories, with infrastructure inventory the most frequent. Tool research has addressed
program testing for general-purpose IaC languages
([Sokolowski et al. 2024](https://doi.org/10.1109/tse.2024.3393070)) and semantic checks that
Terraform programs violate only at deployment time
([Qiu et al. 2024](https://doi.org/10.1145/3694715.3695974)). Other work has addressed bugs that
appear only when an existing deployment is updated
([Xiang et al. 2025](https://doi.org/10.1109/aiops66738.2025.00011)) and lifting existing cloud state
into IaC programs ([Peng et al. 2025](https://doi.org/10.1109/aiops66738.2025.00007)). Formal work has
begun to verify plans: BPlan models Terraform in Maude and checks that applying a plan never
duplicates a resource or leaves a dependency dangling
([Perdereau et al. 2026](https://doi.org/10.5281/zenodo.22747162); research artifact of a 2026
conference paper).

This literature supplies the vocabulary used here (convergence, idempotence, drift, reconciliation
defects) and several of the properties the evaluation tests. It studies engines and programs above
an existing provider layer, however, and does not address how that layer is built when the API offers
no resources.

## 2.2 Reconciliation in cluster managers

Borg, Omega and Kubernetes organise cluster management as a set of controllers that each observe
shared state and act to converge it on a declared target
([Burns et al. 2016](https://doi.org/10.1145/2890784)). This design has prompted a line of work on
controller correctness. Sieve perturbs a controller's view of cluster state (stale, intermediate and
unobserved states) and compares the resulting state evolution with an unperturbed run; it found 46
safety and liveness bugs in ten controllers
([Sun et al. 2022](https://www.usenix.org/conference/osdi22/presentation/sun)). Acto tests the
operation correctness of Kubernetes operators end to end
([Gu et al. 2023](https://doi.org/10.1145/3600006.3613161)). Anvil verifies controller liveness
formally (Sun et al. 2024, OSDI, pp. 649–666). Empirical studies have catalogued operator bugs
([Xu et al. 2024](https://doi.org/10.1145/3650212.3680396)) and conflicts between controllers that
reconcile the same objects ([An & Potop-Butucaru 2026](https://doi.org/10.1145/3820355.3820393)).
Kubernetes also defines field ownership for declarative updates (server-side apply), which records
which manager owns which field [TODO: cite the Kubernetes server-side apply documentation]. The present method adopts a related rule: a document owns exactly
the fields it names.

These systems reconcile against an API server that already stores declarative objects with a
separation between specification and status. Sieve's design depends explicitly on that
state-centric interface. A procedure-oriented API offers no such interface, so the separation
between desired and observed state has to be constructed on the client side.

## 2.3 Bridging declarative models and imperative interfaces

The closest earlier work connects declarative models with imperative or procedural interfaces.

[El Maghraoui et al. 2006](https://doi.org/10.1007/11925071_21) bridged declarative object models
and procedural provisioning tools: AI planning generated the workflow that takes a data centre from
its current to its desired state. The CHAMPS system derived parallel change plans from dependency
information ([Keller et al. 2004](https://doi.org/10.1109/noms.2004.1317679)). The TOSCA standard
describes applications declaratively as topologies and imperatively as management plans
([Binz et al. 2013](https://doi.org/10.1007/978-1-4614-7535-4_22)), and imperative plans can be
generated from declarative topologies
([Breitenbücher et al. 2014](https://doi.org/10.1109/ic2e.2014.56)).
[Wettinger et al. 2014](https://doi.org/10.1007/978-3-662-45391-9_23) contrasted convergent
deployment automation with a compensation-based alternative built on snapshots. Theoretical results
bound what such planners can achieve. Plan achievability is undecidable in the general Aeolus
component model and tractable only under restrictions
([Di Cosmo et al. 2014](https://doi.org/10.1016/j.ic.2014.11.002)). Quiescence defines when a running
system can be changed safely ([Kramer & Magee 1990](https://doi.org/10.1109/32.60317)).

Research on models at run time keeps a model causally connected to a running system, so that the
model reflects the system and editing the model changes it
([Blair et al. 2009](https://doi.org/10.1109/mc.2009.326);
[Morin et al. 2009](https://doi.org/10.1109/mc.2009.327); survey in
[Bencomo et al. 2019](https://doi.org/10.1007/s10270-018-00712-x)). Song and colleagues came closest
to the present problem:

- they generated synchronisation engines from a meta-model plus a description of how to manipulate
  its elements through the system's management API
  ([Song et al. 2010a](https://doi.org/10.1007/978-3-642-12261-3_14));
- they inferred such meta-models from client code that calls the API
  ([Song et al. 2010b](https://doi.org/10.1007/978-3-642-16129-2_13));
- they handled conflicts between model and system changes
  ([Song et al. 2010c](https://doi.org/10.1016/j.jss.2010.12.009)).

Related model-driven work built bridges between APIs and models
([Izquierdo et al. 2011](https://doi.org/10.1016/j.infsof.2011.09.006)), extracted models from Web API
documentation ([Rodríguez et al. 2012](https://doi.org/10.1007/978-3-642-35623-0_14)) and managed
cloud resources through run-time models
([Zhang et al. 2013](https://doi.org/10.1007/978-3-642-41533-3_35)). In the cloud setting, CloudMF
combines a provisioning language with a models-at-run-time engine that adapts a running multi-cloud
deployment to a target model ([Ferry et al. 2018](https://doi.org/10.1145/3125621)). Tooling built on the Open Cloud Computing
Interface (OCCI) generates connectors and compares topologies to adapt them at run time
([Zalila et al. 2019](https://doi.org/10.1016/j.future.2019.04.015);
[Korte et al. 2018](https://doi.org/10.5220/0006693001000111);
[Erbel et al. 2018](https://doi.org/10.5220/0006774405170525);
[Challita et al. 2021](https://doi.org/10.1007/s10270-021-00869-y)).

Formally, the mapping between a declarative document and remote state is a view-update problem.
Lenses express it as a pair of transformations with round-trip laws
([Foster et al. 2007](https://doi.org/10.1145/1232420.1232424); cross-disciplinary overview in
[Czarnecki et al. 2009](https://doi.org/10.1007/978-3-642-02408-5_19)). Three-way merging, which
planning against desired, recorded and observed state resembles, has weaker guarantees than often
assumed ([Khanna et al. 2007](https://doi.org/10.1007/978-3-540-77050-3_40)).

This body of work established that declarative intent can drive imperative interfaces through
generated or modelled mappings. Most of it, however, targets interfaces that are already
resource-oriented (OCCI is CRUD over resources by design) or relies on connectors written per
resource type. None of it provides a mechanical check that a mapping covers every field the
interface exposes, and the evaluations are largely case demonstrations rather than tests of
convergence and recovery.

## 2.4 Analysing and generating tooling from API descriptions

REST-testing research has developed techniques to recover the structure of an API from its
description. RESTler infers producer–consumer dependencies between requests from an OpenAPI document,
so that a request consuming an identifier is ordered after the request producing it
([Atlidakis et al. 2019](https://doi.org/10.1109/icse.2019.00083)). Morest maintains a property graph
of such dependencies and repairs it during execution
([Liu et al. 2022](https://doi.org/10.1145/3510003.3510133)). A comparison of ten tools identified
the construction of valid operation sequences as the central difficulty
([Kim et al. 2022](https://doi.org/10.1145/3533767.3534401)). OpenAPI cannot express dependencies
between parameters, for which a dedicated language has been proposed
([Martin-Lopez et al. 2021](https://doi.org/10.1109/tsc.2021.3050610)). Studies of API design have
assessed cloud REST APIs against design practice
([Petrillo et al. 2016](https://doi.org/10.1007/978-3-319-46295-0_10)) and collected structural
metrics over more than a million OpenAPI descriptions
([Serbout & Pautasso 2024](https://doi.org/10.1145/3643991.3644932)).

On the tooling side, HashiCorp's OpenAPI provider generator turns an OpenAPI 3 document into a
Terraform provider code specification. A developer must still write a configuration that maps
operations to resources, because a general HTTP API description does not align with the provider
model on its own; the output covers schema and data handling, not request logic
([terraform-plugin-codegen-openapi](https://github.com/hashicorp/terraform-plugin-codegen-openapi)).
Crossplane's Upjet ([github.com/crossplane/upjet](https://github.com/crossplane/upjet)) and Pulumi's
Terraform bridge ([github.com/pulumi/pulumi-terraform-bridge](https://github.com/pulumi/pulumi-terraform-bridge))
generate providers from existing Terraform providers, so they inherit resource semantics rather
than derive them. AWS Cloud Control API takes the opposite route: the vendor publishes, for each
resource type, a schema that declares the primary identifier and the read-only, create-only and
write-only properties, and a uniform create–read–update–delete–list interface follows from it [TODO: cite the AWS Cloud
Control API and CloudFormation resource-schema documentation].

These generators and schemas show which information a declarative tool needs from an API. When the
API is resource-oriented they recover much of it from the description; when it is not, they leave it
to hand-written configuration or code. The kind specification proposed here can be read as a
Cloud-Control-style resource schema written by the integrator for an API whose vendor did not
provide one. It is extended with what a procedure-oriented API additionally requires: the role of
each procedure, write groups, identity discovery, read authority, and structural shapes.

## 2.5 Summary

Table 1 summarises the comparison. The present method combines elements that earlier work treated
separately:

- the convergence and recovery properties studied for configuration management and controllers;
- the model-to-interface mapping studied for models at run time and cloud modelling;
- the description-driven generation used in API tooling.

It adds what none of them provides for a procedure-oriented API: a per-kind specification of the
missing semantics, a mechanical check that the specifications cover every field the API exposes, and
conformance scenarios derived from the same specifications.

**Table 1.** Positioning of the method against related work.

| Line of work | Representative work | Target interface | Mapping to the interface | Completeness check | Convergence and recovery evaluated |
|---|---|---|---|---|---|
| Convergent configuration | Hanappi et al. 2016; Shambaugh et al. 2016 | Host resources | Built into the tool's resource types | No | Yes |
| Cluster reconciliation | Sun et al. 2022; Gu et al. 2023 | State-centric API server | Controller code per resource | No | Yes |
| Model-driven provisioning, TOSCA | El Maghraoui et al. 2006; Breitenbücher et al. 2014 | Scripts and services | Hand-modelled plans and artifacts | No | Limited |
| Models at run time | Song et al. 2010a, 2010b | Management APIs | Generated from a meta-model and API description | No | Case studies |
| Cloud modelling, OCCI | Ferry et al. 2018; Zalila et al. 2019 | Resource-oriented cloud APIs | Connectors per resource type | No | Case studies |
| API tooling generators | terraform-plugin-codegen-openapi; Upjet | OpenAPI or existing providers | Configuration or inherited code | No | No |
| **This report** | dokploy-iac | **Procedure-oriented RPC API** | **Declarative kind specifications, no per-kind engine code** | **Yes (coverage ledger)** | **[RESULT]** |
