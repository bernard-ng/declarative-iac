# E2: Automatic semantic inference against the specs as ground truth

**Question.** Which parts of a kind spec could a tool infer from the API contract alone, and which
require human knowledge or live probing? (RQ1)

**Ground truth.** The B1 specs, reviewed by a second annotator on a stratified sample (agreement
reported as Cohen's κ). Disagreements are adjudicated and logged; the adjudicated spec is the gold label.

**Inferred targets (per kind).** operation roles (create/read_one/list/update/remove/deploy),
write-group partition, id field and parameter, create-identity strategy, parent attachment field,
field mutability class, value class (secret/content/public), nullability.

**Inference sources, evaluated cumulatively.**
1. *Lexical:* router and procedure names.
2. *Schema:* request schemas in the OpenAPI document (required fields, `*Id` inputs, enum/format).
3. *Fixtures:* recorded live responses (field presence on read, echoed vs generated values).
4. *Dynamic probing* (optional, needs Dokploy): create/read/update each field and observe.

**Metrics.** Precision, recall, F1 per target and source level; share of spec content no source
recovers ("irreducible annotation"). Report per kind family (settings flat, project leaf, service).

**Baseline.** E0 lexical mapping. **Status:** designed; implement `infer.py` with sources 1–3 first.
