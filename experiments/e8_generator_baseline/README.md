# E8: General-purpose generator baseline

**Question.** Starting from the same pinned OpenAPI document, how much of the B1 kind semantics does
HashiCorp's `tfplugingen-openapi` recover, and what must be configured by hand? (RQ4)

**Procedure.** Write the minimal generator config that maps each B1 kind to its create/read/update/
delete operations; run the generator; compare the provider code specification with the B1 spec on:
kinds mapped, attributes typed, computed/required/optional classification, and the constructs it
cannot express (empty response schemas, several write operations per kind, union-dispatched
writes, write-only secrets, relations, singletons). Report configuration lines needed.

**Scope note.** The generator produces a schema skeleton, not request logic, so this is a coverage
comparison, not a functional benchmark.
