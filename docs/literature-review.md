# Declarative control planes over RPC APIs

*Scope: prior work relevant to deriving an Infrastructure-as-Code (IaC) reconciliation engine from an RPC API that was not designed for declarative management, with Dokploy's tRPC API (exported as OpenAPI 3.1) as the case study. Sources were retrieved from OpenAlex, Semantic Scholar and CrossRef, then expanded one step backward and forward along the citation graph of the closest papers. Practitioner documentation is flagged as grey literature.*

## Bottom line

No published work we found does the whole thing the paper proposes: systematically derive resource, identity and lifecycle semantics from a procedure-oriented API, build a plan/apply reconciler on top of it, and evaluate convergence, idempotency and drift handling empirically. The idea itself is not new, though. It sits where four research lines meet, and each one supplies part of the method and part of the evaluation vocabulary. The paper has to position itself against all four.

1. **Convergent configuration management** (CFEngine, Puppet, idempotence/convergence testing) supplies the formal notions of convergence and idempotence that RQ2 should use.
2. **State-reconciliation controllers** (Kubernetes, Sieve, Acto, Anvil) supply the closest modern analogue of "desired state → observe → diff → act" and the strongest testing and verification methods for it.
3. **Model-driven bridging of declarative models and imperative interfaces** (model-driven provisioning, TOSCA, models@run.time synchronisation engines generated from management APIs, OCCI) is the most direct intellectual precedent for RQ1 and RQ4. Most of this work is 10–18 years old, is framed around MDE and not IaC, and has limited empirical evaluation.
4. **API specification analysis** (RESTler-style dependency inference, API design-rule studies, Google's declarative-friendly API guidelines, HashiCorp's OpenAPI→Terraform generator) supplies the inference techniques and the "what makes an API IaC-hostile" criteria behind RQ3.

The recent empirical IaC literature (2024–2026) makes the case that the problem matters. [Hassan et al. 2024](https://doi.org/10.1145/3660790) analysed 5,110 *state reconciliation* defects in IaC tools. The formal-verification side is converging on Terraform plan semantics: see [Perdereau et al. 2026](https://doi.org/10.5281/zenodo.22747162), the BPlan artifact for an accepted SEFM 2026 paper. The strongest novelty claim open to you is therefore not "a Terraform provider for Dokploy". It is **a reproducible, evaluated method for turning a non-resource-oriented RPC surface into a safe declarative control plane, plus a characterisation of which API properties block that transformation.**

---

## Part I: Convergent declarative management

### Convergence and idempotence

The theory of what "apply until nothing changes" means comes from 1990s–2000s system administration, not from cloud IaC. CFEngine is built on *convergent* statements, which move agents toward an ideal state implied by policy ([Burgess 2005](https://doi.org/10.5220/0001159201830188)). Couch and Sun formalised this algebraically ([Couch & Sun 2003](https://doi.org/10.1007/978-3-540-39671-0_4)). They then used a state-machine model to show that, for a single host and some classes of configuration process, reproducibility of observed effect can be verified statically ([Couch & Sun 2004](https://doi.org/10.1016/j.scico.2004.04.002)). Your invariant 22 ("apply followed by plan converges to no changes") is exactly this property, and the paper should name its lineage.

The testing branch of this line is the most directly reusable for RQ2. [Hummer et al. 2013](https://doi.org/10.1007/978-3-642-45065-5_19) introduced model-based testing of idempotence for IaC automations and found non-idempotent scripts in public repositories. [Hanappi et al. 2016](https://doi.org/10.1145/2983990.2984000) generalised this to *reliable convergence* under transient faults. They model scripts as partially ordered resource actions over state-transition graphs and prove that if a pairwise *preservation* property holds for all resource pairs, the whole configuration converges. That result lets them avoid enumerating every execution order. It maps directly onto your dependency-ordered executor. If you can argue preservation (or something close to it) for Dokploy resource pairs, you get a compositional convergence argument rather than a purely empirical one. On the verification side, Rehearsal checks Puppet manifests for determinism and idempotence ([Shambaugh et al. 2016](https://doi.org/10.1145/2908080.2908083)). Tortoise addresses the *drift* direction: shell changes that silently diverge from the declared configuration are lifted back into the specification ([Weiss et al. 2017](https://doi.org/10.1109/ase.2017.8115673)). More generally, [Ramalingam & Vaswani 2013](https://doi.org/10.1145/2429069.2429100) frame idempotence as the property that makes retry-based fault tolerance correct. That framing justifies your refusal to blindly retry non-idempotent mutations whose outcome is unknown (invariant 16).

### State reconciliation in cluster managers

Kubernetes popularised a different point in the design space: level-triggered controllers that continuously observe state and act to converge it ([Burns et al. 2016](https://doi.org/10.1145/2890784)). Most of the recent systems research on reconciliation correctness targets this model. Sieve perturbs a controller's view of cluster state (stale, intermediate or unobserved states) and compares state evolution with and without perturbation. It found 46 safety and liveness bugs in ten popular controllers ([Sun et al., OSDI 2022](https://www.usenix.org/conference/osdi22/presentation/sun)). Its design depends on reconciliation systems exposing *state-centric interfaces*. That property is precisely what a procedure-oriented API lacks, and it is worth stating as a contrast in the paper. Acto extends this to end-to-end testing of operator operation correctness ([Gu et al. 2023](https://doi.org/10.1145/3600006.3613161)). Anvil (Sun et al., OSDI 2024, pp. 649–666) goes further and formally verifies liveness of controllers. Its property, informally "eventually stable reconciliation", is the formal target your RQ2 is approximating empirically. Kivi model-checks controller interactions (Liu et al., [arXiv:2311.02800](https://arxiv.org/abs/2311.02800)).

The empirical side shows the failure modes are common. [Xu et al. 2024](https://doi.org/10.1145/3650212.3680396) present the first comprehensive study of Kubernetes operator bugs. [Yu et al. 2025](https://doi.org/10.1109/icdcs63083.2025.00015) target post-reconciliation state correctness. [An & Potop-Butucaru 2026](https://doi.org/10.1145/3820355.3820393) formalise conflicts between multiple reconciling controllers. That last issue is relevant if Dokploy's own background processes (deployments, auto-deploy hooks) mutate the same fields your engine owns.

The key difference from your setting is that Kubernetes controllers reconcile against an API server that *already* stores declarative spec/status objects. Your engine has to synthesise that desired/observed separation on the client side, over procedures that carry no spec/status split. That is the gap your paper fills.

---

## Part II: Declarative–imperative bridging

### Model-driven provisioning and TOSCA

The closest older precedent for "declarative desired state compiled into calls on procedural tools" is IBM's model-driven provisioning work. [El Maghraoui et al. 2006](https://doi.org/10.1007/11925071_21) explicitly frame the problem as *bridging the gap between declarative object models and procedural provisioning tools*. They use AI partial-order planning to generate workflows that take a data centre from its current state to the desired one. The CHAMPS system similarly derives parallel change plans from runtime dependency information ([Keller et al. 2004](https://doi.org/10.1109/noms.2004.1317679)). Both are planners over a dependency graph, like your `petgraph`-ordered planner, but neither infers the action vocabulary from an API. It is hand-modelled.

TOSCA standardised the two styles: declarative topology models interpreted by a runtime, and imperative management plans ([Binz et al. 2013](https://doi.org/10.1007/978-1-4614-7535-4_22)). [Breitenbücher et al. 2014](https://doi.org/10.1109/ic2e.2014.56) generate imperative provisioning plans from declarative topologies, the same compile-declarative-into-imperative step your planner performs. [Wettinger et al. 2014](https://doi.org/10.1007/978-3-662-45391-9_23) compare *convergent* deployment automation with a *compensation-based* alternative built on fine-grained snapshots. That comparison is directly relevant to your choice of no automatic rollback after partial failure (invariant 19), and it gives a named baseline to argue against. Two theoretical results bound what is achievable. The Aeolus component model shows that plan achievability is undecidable in the general case and becomes polynomial only under restrictions ([Di Cosmo et al. 2014](https://doi.org/10.1016/j.ic.2014.11.002)). Kramer and Magee's quiescence criterion defines when structural change can be applied safely to a running system ([Kramer & Magee 1990](https://doi.org/10.1109/32.60317)). Citing these lets you state precisely which restrictions (acyclic dependencies, no inter-resource conflicts) make your planning problem tractable.

### Models@run.time synchronisation

The line most similar to RQ1 and RQ4 is models@run.time: a model causally connected to a running system, so that reading the model reflects the system and editing it changes the system ([Blair et al. 2009](https://doi.org/10.1109/mc.2009.326); [Morin et al. 2009](https://doi.org/10.1109/mc.2009.327); survey in [Bencomo et al. 2019](https://doi.org/10.1007/s10270-018-00712-x)). Song and colleagues made three contributions that are strikingly close to the proposed paper:

- **Generating synchronisation engines.** The developer supplies a meta-model plus a description of how to manipulate elements via the system's *management API*, and a bidirectional synchroniser is generated ([Song et al. 2010a](https://doi.org/10.1007/978-3-642-12261-3_14)).
- **Inferring the meta-model automatically** by analysing client code that calls the management API ([Song et al. 2010b](https://doi.org/10.1007/978-3-642-16129-2_13)).
- **Handling conflicts** between model-side and system-side changes and failures of system manipulations ([Song et al. 2010c](https://doi.org/10.1016/j.jss.2010.12.009)). This is the models@run.time name for drift and partial failure.

Related MDE work bridges APIs to models generically ([Izquierdo et al. 2011](https://doi.org/10.1016/j.infsof.2011.09.006)) or extracts models from Web API documentation ([Rodríguez et al. 2012](https://doi.org/10.1007/978-3-642-35623-0_14)). The same group applied runtime models to cloud resources ([Zhang et al. 2013](https://doi.org/10.1007/978-3-642-41533-3_35)).

The cloud-specific continuation is the CloudML/CloudMF framework. It pairs a provisioning DSL with a models@run.time engine that compares the current and target models and derives adaptation actions ([Ferry et al. 2014](https://doi.org/10.1109/ucc.2014.36); [Ferry et al. 2018](https://doi.org/10.1145/3125621)). The OCCI community built similar model-driven tooling: generated connectors ([Zalila et al. 2019](https://doi.org/10.1016/j.future.2019.04.015)), model-driven configuration management ([Korte et al. 2018](https://doi.org/10.5220/0006693001000111)), model comparison that yields runtime adaptation steps ([Erbel et al. 2018](https://doi.org/10.5220/0006774405170525)) and TOSCA↔OCCI mapping ([Challita et al. 2021](https://doi.org/10.1007/s10270-021-00869-y)). **This is the related work most likely to be raised by a reviewer as "already done".** Your answer should be that these systems assume a *resource-oriented* target interface (OCCI is CRUD-over-resources by design) or hand-written connectors. None of them evaluates convergence, idempotence or drift over a real procedure-oriented API with untyped responses.

### Bidirectional transformations

Formally, the mapping between your configuration model and Dokploy state is a view-update problem. The lens framework ([Foster et al. 2007](https://doi.org/10.1145/1232420.1232424); cross-discipline survey [Czarnecki et al. 2009](https://doi.org/10.1007/978-3-642-02408-5_19)) gives *get*/*put* laws (GetPut, PutGet) that correspond closely to "import then plan is empty" and "apply then plan is empty". Your ownership-aware three-way diff (desired, stored, remote) is a three-way merge. [Khanna et al. 2007](https://doi.org/10.1007/978-3-540-77050-3_40) showed that diff3 has surprisingly weak guarantees, which is a useful citation when you justify fail-closed handling of conflicting changes. Framing the SDK projection as a (partial) lens and stating which laws hold, and where Dokploy breaks them (write-only secrets, server-computed fields), would give RQ1 a crisp formal backbone.

---

## Part III: Semantic inference from APIs

### Dependency and resource inference

The REST-testing literature has the most mature techniques for automatically recovering the resource structure you need. RESTler infers producer-consumer dependencies from an OpenAPI specification: if request B consumes an ID produced by A, then B must follow A. It then refines those inferences from dynamic feedback ([Atlidakis et al. 2019](https://doi.org/10.1109/icse.2019.00083)). Morest builds a global property graph of API dependencies and repairs it adaptively during execution ([Liu et al. 2022](https://doi.org/10.1145/3510003.3510133)). [Kim et al. 2022](https://doi.org/10.1145/3533767.3534401) benchmark ten such tools and show that inferring correct operation sequences remains the central difficulty. [Martin-Lopez et al. 2021](https://doi.org/10.1109/tsc.2021.3050610) show that OpenAPI cannot express inter-parameter dependencies at all and propose a DSL for them. For your RQ1, these techniques can be repurposed to classify tRPC procedures into create/read/update/delete/action roles, derive parent–child containment (project → environment → application), and detect which input fields are IDs of other resources. This is a concrete, evaluable pipeline where the literature gives you precision/recall baselines.

### What makes an API IaC-friendly

RQ3 has less academic grounding than the others, which is itself an opportunity. [Petrillo et al. 2016](https://doi.org/10.1007/978-3-319-46295-0_10) assessed cloud providers' REST APIs against REST design best practices. APIstic provides structural metrics over 1.27 million OpenAPI descriptions that could be used to situate Dokploy's surface ([Serbout & Pautasso 2024](https://doi.org/10.1145/3643991.3644932)). The RPC-versus-resource debate itself goes back to [Pautasso et al. 2008](https://doi.org/10.1145/1367497.1367606), and API-style migration studies such as [Brito et al. 2019](https://doi.org/10.1109/saner.2019.8667986) offer an evaluation template for "cost of adapting clients to a different API paradigm".

The sharpest criteria come from grey literature. Google's AIP-128 (*Declarative-friendly interfaces*, [google.aip.dev/128](https://google.aip.dev/128)) requires, among other things, that such resources use only strongly consistent standard methods, avoid custom methods, carry an etag, and expose a `reconciling` flag when changes take time. It also motivates the whole guideline by saying uniformity lets declarative adapters be generated automatically. AIP-121 ([google.aip.dev/121](https://google.aip.dev/121)) defines the resource-oriented design that tRPC procedures generally do not follow. AWS Cloud Control API and its resource-type schemas (primary identifier, read-only, create-only and write-only properties) are an industrial example of exactly the semantic annotations your engine has to *infer* for Dokploy. Kubernetes server-side apply's field-ownership model is the closest industrial analogue to your "omitted fields are unmanaged" and ownership-aware diff. **A strong RQ3 contribution would be to operationalise AIP-128-style properties as a checklist, score the Dokploy API against it, and show which failures forced handwritten adapter code.**

### Industrial generators

HashiCorp's `tfplugingen-openapi` turns an OpenAPI 3.x description into a Terraform provider code specification. Because OpenAPI does not fully align with Terraform's design principles, the developer must write a YAML generator config that maps operations to resources, and the tool is in technical preview ([README](https://github.com/hashicorp/terraform-plugin-codegen-openapi); [DESIGN.md](https://github.com/hashicorp/terraform-plugin-codegen-openapi/blob/main/DESIGN.md)). A competing vendor notes that it generates only schema and data-handling types, not the request logic ([Speakeasy](https://www.speakeasy.com/blog/how-to-build-terraform-providers)). Crossplane's Upjet ([github.com/crossplane/upjet](https://github.com/crossplane/upjet)) and Pulumi's Terraform bridge ([github.com/pulumi/pulumi-terraform-bridge](https://github.com/pulumi/pulumi-terraform-bridge)) generate providers from *existing Terraform providers*, so they inherit rather than derive semantics. These tools make a natural **RQ4 baseline**: the share of Dokploy resources you can cover with zero, configuration-only and handwritten adaptation, compared with what `tfplugingen-openapi` produces from the same vendored OpenAPI document.

---

## Part IV: IaC reliability precedents

### Empirical defect studies

The IaC mapping study by [Rahman et al. 2018](https://doi.org/10.1016/j.infsof.2018.12.004) and the 44-interview industrial study by [Guerriero et al. 2019](https://doi.org/10.1109/icsme.2019.00092) established that IaC tooling lags behind general software engineering. Defect taxonomies followed: 1,448 OpenStack defect commits in [Rahman et al. 2020](https://doi.org/10.1145/3377811.3380409), security smells in [Rahman et al. 2019](https://doi.org/10.1109/icse.2019.00033), and a 2026 systematic review of IaC quality assurance ([El Hayani et al. 2026](https://doi.org/10.1016/j.jss.2026.113080)). Two 2024 studies target the engine layer rather than user scripts, which is where your contribution lives. [Hassan et al. 2024](https://doi.org/10.1145/3660790) define state reconciliation as querying and comparing infrastructure state before changing it. Across 5,110 defects they identify eight categories, three of them new, with *inventory* management the most frequent. [Drosos et al. 2024](https://doi.org/10.1145/3689799) analyse 360 bugs in Ansible, Puppet and Chef, covering manifestation, root cause, reproduction conditions and fixes. Both provide category schemes you can use to classify the failure cases your evaluation provokes.

### Testing and verifying IaC engines

A cluster of 2022–2026 work, mainly from Salvaneschi's and Ang Chen's groups, is the current frontier:

- ProTI tests Pulumi programs automatically with mocked resources, motivated by the finding that under 1% of public Pulumi programs had tests in August 2022 ([Sokolowski et al. 2024](https://doi.org/10.1109/tse.2024.3393070); see also [Sokolowski & Salvaneschi 2023](https://doi.org/10.1109/icsa-c57050.2023.00072) and [Sokolowski 2022](https://doi.org/10.1145/3540250.3558912) on dynamic IaC).
- Zodiac mines semantic checks for Azure Terraform resources that pass compilation but fail at deployment (500+ checks, 200+ buggy projects) ([Qiu et al. 2024](https://doi.org/10.1145/3694715.3695974)). This is the "API semantics not captured by the schema" problem your tolerant read models address.
- TerraFault uses LLM-guided search to find bugs in *updates* rather than initial deployments ([Xiang et al. 2025](https://doi.org/10.1109/aiops66738.2025.00011)). Its framing, that engines are well-tested for greenfield but not for change, matches your partially configured and drifted initial conditions.
- Lilac lifts brownfield cloud state into IaC programs, combining LLM-extracted lifting rules with symbolic checks ([Peng et al. 2025](https://doi.org/10.1109/aiops66738.2025.00007)). This is directly relevant to your *import* semantics.
- BPlan formalises Terraform in Maude and verifies that plan execution never duplicates a resource and never leaves a dangling dependency ([Perdereau et al. 2026](https://doi.org/10.5281/zenodo.22747162); artifact of a SEFM 2026 paper). These are the same properties your move and replace semantics must guarantee.
- RIVA uses LLM agents for drift detection that is robust to erroneous tool outputs ([Abuzakuk et al. 2026](https://doi.org/10.1145/3805621.3807644)).
- Position papers argue that IaC should rest on firmer principles ([Qiu et al. 2023](https://doi.org/10.1145/3626111.3628206), "cloudless computing") and compare agent use of SDKs, CLIs and IaC interfaces ([Yang et al. 2025](https://doi.org/10.1145/3759441.3759443)).

LLM-based IaC generation ([Kon et al. 2024](https://doi.org/10.52202/079017-4273); [Zhang et al. 2026](https://doi.org/10.1145/3797142)) is adjacent but orthogonal. It generates *user* configurations, not engines. It becomes relevant only if you use an LLM for semantic inference in RQ1, in which case Lilac's LLM-plus-symbolic-validation pattern is the right template.

### Partial failure and outcome uncertainty

Your journal/checkpoint design and the "outcome unknown" error class have classic foundations. The ambiguity of RPC failure semantics goes back to [Birrell & Nelson 1984](https://doi.org/10.1145/2080.357392). Compensation for partially executed long-running operations goes back to Sagas ([García-Molina & Salem 1987](https://doi.org/10.1145/38713.38742)). AURA models deployment as DAG traversal and re-executes only the failed parts ([Giannakopoulos et al. 2017](https://doi.org/10.1109/ccgrid.2017.133)). The paper should state explicitly why it chooses journaled forward recovery over Saga-style compensation, citing [Wettinger et al. 2014](https://doi.org/10.1007/978-3-662-45391-9_23) for the trade-off.

---

## Positioning table

| Line of work | Representative | Derives resource model from API? | Declarative plan/diff? | Handles drift / partial failure? | Evaluated convergence empirically? | Target interface |
|---|---|---|---|---|---|---|
| Convergent CM testing | Hummer 2013; Hanappi 2016 | No | Implicit (resource DSL) | Transient faults | Yes (Puppet scripts) | OS resources |
| K8s reconciliation testing/verification | Sieve 2022; Acto 2023; Anvil 2024 | No | Controller loop | Yes (stale/partial views) | Yes / formally | State-centric API server |
| Model-driven provisioning / TOSCA | El Maghraoui 2006; Breitenbücher 2014 | No (hand-modelled) | Yes (AI planning / plan generation) | Limited | Limited | Scripts and services |
| Models@run.time sync engines | Song 2010a,b,c | **Partly (meta-model inference)** | Bidirectional sync | Conflicts, exceptions | Case studies | Management APIs (JMX etc.) |
| CloudMF / OCCI | Ferry 2018; Erbel 2018 | No (connectors) | Model comparison | Limited | Case studies | Resource-oriented (OCCI) |
| REST dependency inference | RESTler 2019; Morest 2022 | **Yes (dependencies)** | No | No | N/A (testing) | REST/OpenAPI |
| IaC engine reliability | Hassan 2024; TerraFault 2025; BPlan 2026 | No | Terraform plan | Studied as defects | Partly | Cloud provider APIs |
| Industrial generators | tfplugingen-openapi; Upjet | Config-driven mapping | Delegated to Terraform | Delegated | No | OpenAPI / TF providers |
| **Proposed paper** | Dokploy case study | **Yes (tRPC/OpenAPI)** | **Yes (three-way, ownership-aware)** | **Yes (journal, fail-closed)** | **Target of RQ2** | **Procedure-oriented RPC** |

---

## Gaps the paper can occupy

**Gap 1: no evaluated method for non-resource-oriented APIs.** Every declarative-bridging system above assumes either a resource-oriented target (OCCI, Kubernetes, AIP-compliant APIs, Cloud Control) or hand-written connectors. Song et al.'s meta-model inference is the only automated derivation, and it targets Java management APIs through client-code analysis, not RPC schemas. This supports RQ1 directly.

**Gap 2: the tRPC→OpenAPI export loses response semantics.** Your own Phase 0 audit found that all 604 operations in the vendored Dokploy OpenAPI document declare HTTP 200 as a closed empty object, so read models had to be handwritten. We infer that this is a systematic consequence of exporting TypeScript-inferred procedure outputs through an OpenAPI adapter. Zodiac shows schema-invisible semantics matter even for well-specified clouds, but no study characterises this class of loss. Measuring it, and the adapter code it forces, is a clean RQ3/RQ4 result.

**Gap 3: convergence evaluated under brownfield and drift.** Hanappi-style convergence testing and Sieve-style perturbation both exist, but neither has been applied to a client-side IaC engine over an RPC API under the empty / partial / drifted × repeated-apply design you propose. TerraFault's observation that update paths are under-tested supports this design.

**Gap 4: formal characterisation of the projection.** The lens laws and Hanappi's preservation property are available but have not been applied to IaC-over-RPC. Stating which laws hold per resource type, and which Dokploy behaviours break them (write-only passwords, environment documents, server-generated fields), would turn RQ1 from descriptive to analytical.

**Gap 5: an API-friendliness scorecard.** AIP-128 prescribes properties for declarative-friendliness, but it is a design guideline, not an empirical instrument. Operationalising it and validating it against the adapter effort observed on Dokploy (and ideally one or two other self-hosted PaaS APIs, to reduce single-case threats) would generalise beyond the case study.

## Implications for the evaluation design

The literature suggests four concrete adjustments to the planned experiment.

1. Define convergence and idempotence formally, following Couch & Sun and Hanappi et al. Report *k-apply convergence* (number of applies to reach an empty plan) as well as the binary one-apply result.
2. Add Sieve-style fault injection at the SDK seam: stale reads, interrupted mutations, and responses dropped after the server commits. That directly exercises invariants 15, 16 and 19.
3. Classify every failure found using the Hassan et al. 2024 categories, so results can be compared with the Terraform/Ansible defect literature.
4. Use `tfplugingen-openapi` on the same vendored OpenAPI document as the RQ4 baseline, measuring resources covered, attributes correctly classified (computed, optional, required, immutable) and lines of handwritten code in each approach.

**Likely venues.** Engine-and-evaluation papers of this type have appeared at ICSE, FSE/PACMSE ([Hassan et al. 2024](https://doi.org/10.1145/3660790)), OOPSLA/PACMPL ([Drosos et al. 2024](https://doi.org/10.1145/3689799)), TSE ([Sokolowski et al. 2024](https://doi.org/10.1109/tse.2024.3393070)), SOSP ([Qiu et al. 2024](https://doi.org/10.1145/3694715.3695974)) and SEFM ([Perdereau et al. 2026](https://doi.org/10.5281/zenodo.22747162)). For a first paper, ICSE-SEIP, ICSME, ICSA or the experience track of FSE are realistic. MODELS is appropriate if the lens/models@run.time framing is foregrounded.

---

## Reference list

Academic sources (DOI-resolved):

- Abuzakuk et al. 2026: RIVA: LLM agents for reliable configuration drift detection. https://doi.org/10.1145/3805621.3807644
- An & Potop-Butucaru 2026: A formal model of multi-controller orchestration systems in cloud management. https://doi.org/10.1145/3820355.3820393
- Atlidakis et al. 2019: RESTler: stateful REST API fuzzing. ICSE. https://doi.org/10.1109/icse.2019.00083
- Bencomo et al. 2019: Models@run.time: a guided tour. SoSyM. https://doi.org/10.1007/s10270-018-00712-x
- Binz et al. 2013: TOSCA: portable automated deployment and management of cloud applications. https://doi.org/10.1007/978-1-4614-7535-4_22
- Birrell & Nelson 1984: Implementing remote procedure calls. TOCS. https://doi.org/10.1145/2080.357392
- Blair et al. 2009: Models@run.time. IEEE Computer. https://doi.org/10.1109/mc.2009.326
- Breitenbücher et al. 2014: Combining declarative and imperative cloud application provisioning based on TOSCA. IC2E. https://doi.org/10.1109/ic2e.2014.56
- Brito et al. 2019: Migrating to GraphQL: a practical assessment. SANER. https://doi.org/10.1109/saner.2019.8667986
- Burgess 2005: A tiny overview of cfengine: convergent maintenance agent. https://doi.org/10.5220/0001159201830188
- Burns et al. 2016: Borg, Omega, and Kubernetes. CACM. https://doi.org/10.1145/2890784
- Challita et al. 2021: Model-based cloud resource management with TOSCA and OCCI. SoSyM. https://doi.org/10.1007/s10270-021-00869-y
- Couch & Sun 2003: On the algebraic structure of convergence. https://doi.org/10.1007/978-3-540-39671-0_4
- Couch & Sun 2004: On observed reproducibility in network configuration management. SCP. https://doi.org/10.1016/j.scico.2004.04.002
- Czarnecki et al. 2009: Bidirectional transformations: a cross-discipline perspective. https://doi.org/10.1007/978-3-642-02408-5_19
- Di Cosmo et al. 2014: Aeolus: a component model for the cloud. Inf. & Comp. https://doi.org/10.1016/j.ic.2014.11.002
- Drosos et al. 2024: When your infrastructure is a buggy program. OOPSLA/PACMPL. https://doi.org/10.1145/3689799
- El Hayani et al. 2026: Quality assurance in infrastructure as code. JSS. https://doi.org/10.1016/j.jss.2026.113080
- El Maghraoui et al. 2006: Model driven provisioning: bridging the gap between declarative object models and procedural provisioning tools. Middleware. https://doi.org/10.1007/11925071_21
- Erbel et al. 2018: Comparison and runtime adaptation of cloud application topologies based on OCCI. https://doi.org/10.5220/0006774405170525
- Ferry et al. 2014: CloudMF. UCC. https://doi.org/10.1109/ucc.2014.36
- Ferry et al. 2018: CloudMF. ACM TOIT. https://doi.org/10.1145/3125621
- Foster et al. 2007: Combinators for bidirectional tree transformations. TOPLAS. https://doi.org/10.1145/1232420.1232424
- García-Molina & Salem 1987: Sagas. SIGMOD. https://doi.org/10.1145/38713.38742
- Giannakopoulos et al. 2017: AURA: recovering from transient failures in cloud deployments. CCGrid. https://doi.org/10.1109/ccgrid.2017.133
- Gu et al. 2023: Acto: automatic end-to-end testing for operation correctness of cloud system management. SOSP. https://doi.org/10.1145/3600006.3613161
- Guerriero et al. 2019: Adoption, support, and challenges of infrastructure-as-code. ICSME. https://doi.org/10.1109/icsme.2019.00092
- Hanappi et al. 2016: Asserting reliable convergence for configuration management scripts. OOPSLA. https://doi.org/10.1145/2983990.2984000
- Hassan et al. 2024: State reconciliation defects in infrastructure as code. FSE/PACMSE. https://doi.org/10.1145/3660790
- Hummer et al. 2013: Testing idempotence for infrastructure as code. Middleware. https://doi.org/10.1007/978-3-642-45065-5_19
- Izquierdo et al. 2011: API2MoL: automating the building of bridges between APIs and MDE. IST. https://doi.org/10.1016/j.infsof.2011.09.006
- Keller et al. 2004: The CHAMPS system: change management with planning and scheduling. NOMS. https://doi.org/10.1109/noms.2004.1317679
- Khanna et al. 2007: A formal investigation of diff3. FSTTCS. https://doi.org/10.1007/978-3-540-77050-3_40
- Kim et al. 2022: Automated test generation for REST APIs: no time to rest yet. ISSTA. https://doi.org/10.1145/3533767.3534401
- Kon et al. 2024: IaC-Eval. NeurIPS D&B. https://doi.org/10.52202/079017-4273
- Korte et al. 2018: Model-driven configuration management of cloud applications with OCCI. https://doi.org/10.5220/0006693001000111
- Kramer & Magee 1990: The evolving philosophers problem: dynamic change management. TSE. https://doi.org/10.1109/32.60317
- Liu et al. 2022: Morest: model-based RESTful API testing with execution feedback. ICSE. https://doi.org/10.1145/3510003.3510133
- Martin-Lopez et al. 2021: Specification and automated analysis of inter-parameter dependencies in web APIs. TSC. https://doi.org/10.1109/tsc.2021.3050610
- Morin et al. 2009: Models@run.time to support dynamic adaptation. IEEE Computer. https://doi.org/10.1109/mc.2009.327
- Pautasso et al. 2008: RESTful web services vs. "big" web services. WWW. https://doi.org/10.1145/1367497.1367606
- Peng et al. 2025: Automated lifting for cloud infrastructure-as-code programs (Lilac). AIOps. https://doi.org/10.1109/aiops66738.2025.00007
- Perdereau et al. 2026: BPlan: formal verification of stability in Terraform changes (artifact; SEFM 2026 paper). https://doi.org/10.5281/zenodo.22747162
- Petrillo et al. 2016: Are REST APIs for cloud computing well-designed? ICSOC. https://doi.org/10.1007/978-3-319-46295-0_10
- Qiu et al. 2023: Simplifying cloud management with cloudless computing. HotNets. https://doi.org/10.1145/3626111.3628206
- Qiu et al. 2024: Unearthing semantic checks for cloud IaC programs (Zodiac). SOSP. https://doi.org/10.1145/3694715.3695974
- Rahman et al. 2018: A systematic mapping study of infrastructure as code research. IST. https://doi.org/10.1016/j.infsof.2018.12.004
- Rahman et al. 2019: The seven sins: security smells in IaC scripts. ICSE. https://doi.org/10.1109/icse.2019.00033
- Rahman et al. 2020: Gang of eight: a defect taxonomy for IaC scripts. ICSE. https://doi.org/10.1145/3377811.3380409
- Ramalingam & Vaswani 2013: Fault tolerance via idempotence. POPL. https://doi.org/10.1145/2429069.2429100
- Rodríguez et al. 2012: Extracting models from Web API documentation. https://doi.org/10.1007/978-3-642-35623-0_14
- Serbout & Pautasso 2024: APIstic: a large collection of OpenAPI metrics. MSR. https://doi.org/10.1145/3643991.3644932
- Shambaugh et al. 2016: Rehearsal: a configuration verification tool for Puppet. PLDI. https://doi.org/10.1145/2908080.2908083
- Sokolowski 2022: Infrastructure as code for dynamic deployments. ESEC/FSE. https://doi.org/10.1145/3540250.3558912
- Sokolowski & Salvaneschi 2023: Towards reliable infrastructure as code. ICSA-C. https://doi.org/10.1109/icsa-c57050.2023.00072
- Sokolowski et al. 2024: Automated infrastructure as code program testing (ProTI). TSE. https://doi.org/10.1109/tse.2024.3393070
- Song et al. 2010a: Generating synchronization engines between running systems and their model-based views. https://doi.org/10.1007/978-3-642-12261-3_14
- Song et al. 2010b: Inferring meta-models for runtime system data from the clients of management APIs. MODELS. https://doi.org/10.1007/978-3-642-16129-2_13
- Song et al. 2010c: Supporting runtime software architecture: a bidirectional-transformation-based approach. JSS. https://doi.org/10.1016/j.jss.2010.12.009
- Weiss et al. 2017: Tortoise: interactive system configuration repair. ASE. https://doi.org/10.1109/ase.2017.8115673
- Wettinger et al. 2014: Compensation-based vs. convergent deployment automation for services operated in the cloud. ICSOC. https://doi.org/10.1007/978-3-662-45391-9_23
- Xiang et al. 2025: Automated bug discovery in cloud IaC updates with LLM agents (TerraFault). AIOps. https://doi.org/10.1109/aiops66738.2025.00011
- Xu et al. 2024: An empirical study on Kubernetes operator bugs. ISSTA. https://doi.org/10.1145/3650212.3680396
- Yang et al. 2025: Cloud infrastructure management in the age of AI agents. SIGOPS OSR. https://doi.org/10.1145/3759441.3759443
- Yu et al. 2025: Arsc: automated reconciliation for state correctness of cluster management. ICDCS. https://doi.org/10.1109/icdcs63083.2025.00015
- Zalila et al. 2019: Model-driven cloud resource management with OCCIware. FGCS. https://doi.org/10.1016/j.future.2019.04.015
- Zhang et al. 2013: Runtime model based management of diverse cloud resources. MODELS. https://doi.org/10.1007/978-3-642-41533-3_35
- Zhang et al. 2026: Deployability-centric IaC generation. FSE/PACMSE. https://doi.org/10.1145/3797142

Venue papers without DOIs:

- Sun et al. 2022: Automatic reliability testing for cluster management controllers (Sieve). OSDI, pp. 143–159. https://www.usenix.org/conference/osdi22/presentation/sun
- Sun et al. 2024: Anvil: verifying liveness of cluster management controllers. OSDI, pp. 649–666.
- Liu et al.: Kivi: verification for cluster management. arXiv:2311.02800 (preprint).

Grey literature (practitioner documentation):

- Google AIP-128, Declarative-friendly interfaces: https://google.aip.dev/128 ; AIP-121, Resource-oriented design https://google.aip.dev/121
- HashiCorp terraform-plugin-codegen-openapi: https://github.com/hashicorp/terraform-plugin-codegen-openapi
- Speakeasy, How to generate Terraform providers: https://www.speakeasy.com/blog/how-to-build-terraform-providers
- Crossplane Upjet: https://github.com/crossplane/upjet ; Pulumi Terraform bridge https://github.com/pulumi/pulumi-terraform-bridge
- AWS Cloud Control API and CloudFormation resource-type schema; Kubernetes server-side apply (vendor documentation; cite the current doc pages when drafting)
