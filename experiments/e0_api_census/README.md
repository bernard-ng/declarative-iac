# E0: API census

**Question.** How far is Dokploy's tRPC surface from a resource-oriented API, and which part of it
does a declarative engine actually need? (RQ1, RQ3)

**Inputs.** `openapi/dokploy.json` (0.30.6) and `openapi/v0.30.7.json` at the snapshot; all kind specs.

**Procedure.** For every operation: router, procedure, HTTP method, request-field count, whether the
200 response schema is the closed empty object, a lexical role from the procedure name
(create/read_one/list/update/delete/other), and the roles the specs give it (create, write_group,
read_list, membership, ...). The specs serve as the expert annotation of the API.

**Outputs.** `operations.csv`, `routers.csv`, `summary.json`.

**Preliminary result (B1, exploratory).** 604 operations in 57 routers on both versions; all 604
declare an empty 200 response. 178 operations (29.5%) have a CRUD-like name. The specs use 223
operations in 37 routers, and 78 of those 223 (35%) do **not** have a CRUD-like name
(`save*Provider`, `saveEnvironment`, per-provider `create*`/`update*`, `byProjectId`, settings
getters). A name-based mapping would therefore miss about a third of the operations the engine
needs, which is the baseline E2 must beat.
