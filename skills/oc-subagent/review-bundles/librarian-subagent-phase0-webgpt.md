# WebGPT Review Bundle: Persistent Librarian Subagent Phase 0

## Review Request

Adjudicate whether the proposed `librarian` persistent subagent should be added to the oc-subagent persona set, and correct its scope before any persona file is created.

Return one of:

- `VERDICT: PASS`
- `VERDICT: NEEDS_CHANGES`
- `VERDICT: BLOCKED`

For `NEEDS_CHANGES`, provide concrete corrections to the subagent boundary, state contract, permissions, and routing rules. For `BLOCKED`, name the missing local evidence or decision.

This is review only. No commands. No repository edits.

## User Context

The user asked whether the project should have a graph that uses characters, books/author/source, and Theory-of-Mind. The answer under review is: yes, but this should not be implied by doc QRA outputs alone. QRA pairs are recall aids. A separate graph-producing flow is needed for canonical lore facts, Theory-of-Mind states, relationship states, evidence, and upsert candidates.

The user then asked whether this needs to be a subagent with `$memory` access, or whether the project agent should do it. The current proposed answer is:

- The project agent remains the controller and must validate/authorize actual graph mutation.
- A dedicated persistent subagent may be useful as the catalog/key/provenance steward.
- That subagent should not independently mutate canonical ArangoDB graph state.

The user now asks to collaborate with WebGPT on this “librarian” subagent, using current `$memory` context, because it might make a good persistent subagent.

## Memory Context

`$memory` recall was run with:

```text
query: librarian subagent persona dream theory of mind graph arangodb memory
mode: brief
```

Observed result:

```text
found: true
should_scan: false
confidence: 0.477
items: 5
```

The returned items were low-signal for this exact design question: several `problem`/`solution` fields were empty, and no decisive prior contract for a librarian subagent was recovered. Treat memory as indicating that graph/memory work exists in the project, but not as authoritative design proof for this persona boundary.

Memory constraints that must be preserved:

- Use `$memory` endpoints/skill workflows for project memory behavior.
- Do not bypass the memory project with ad hoc raw AQL as a normal subagent behavior.
- Memory writes need receipts and should be scoped, not silent global mutation.

## Current Local Router Evidence

Current oc-subagent persona router has these relevant entries:

```text
doc-extractor: Source-prep section JSONL, raw/clean alignment, cleanup notes, alias repair candidates, and section validation. Primary skills: memory, extractor.

doc-qra: Document summaries, grounded QRA pairs, doc2qra validation, and memory storage receipts. Primary skills: memory, doc2qra.
```

The router already says:

```text
Final canonical lore facts, Theory-of-Mind states, relationship states, graph upserts, retrieval units, and Qdrant materialization are not owned by Doc Extractor or Doc QRA. Route those to a separate future lore-extractor flow or persona.
```

Doc QRA persona also says:

```text
Treat QRA pairs as recall aids only, not final canon facts, Theory-of-Mind states, relationship states, or graph-ready lore records.
```

## Proposed Subagent Name

Candidate id: `librarian`

Alternative names under consideration:

- `lore-librarian`
- `graph-librarian`
- `source-librarian`

Review question: should the persona use the broad stable name `librarian`, or a narrower name to prevent scope creep?

## Proposed Role

The `librarian` is a persistent catalog, identity, ordering, provenance, and graph-key steward for long-running source ingestion and lore graph workflows.

It should own continuity across runs:

- what sources are known
- which source sections belong to which book/transcript/persona artifact
- canonical source identity and creator/author identity
- deterministic graph key prefixes
- alias and identity decisions
- unresolved identity conflicts
- ingestion manifests
- dry-run upsert candidate manifests
- validation receipts

It is not the model that reads prose and invents lore facts. It is the steward that keeps graph-producing work ordered, keyed, attributable, and ready for review.

## Proposed Non-Ownership Boundary

The `librarian` should not own:

- raw document extraction or cleanup; that remains `doc-extractor`
- QRA generation; that remains `doc-qra`
- final lore fact extraction from prose; that should be a separate `lore-extractor` or equivalent
- final Theory-of-Mind inference from prose; that should be produced by the lore extraction flow and validated by evidence
- final ArangoDB graph mutation; that remains project-agent/materializer controlled after validation
- broad truth adjudication or canon sufficiency; that may need fact-checker/assurance review
- UI/dashboard work

## Proposed Primary Skills

Candidate primary skills:

- `memory`
- `ops-arango`
- `edge-verifier`
- `taxonomy`

Concern:

`ops-arango` may be too much authority for a persistent persona if it can write directly. The safer design may allow read-only schema/collection inspection and dry-run candidate generation, with project-agent-approved upsert only.

Review question: should `librarian` have `ops-arango` as a primary skill, a secondary/admin skill, or no direct Arango skill at all?

## Proposed State Contract

Persistent state should be explicit and auditable:

```yaml
state_contract:
  persistent: true
  fields:
    graph_schema_version: string
    namespace_policy: object
    source_registry:
      type: list
      item_fields:
        - source_id
        - source_type
        - title
        - author_or_creator_id
        - source_hash
        - artifact_paths
        - ingestion_status
    identity_registry:
      type: list
      item_fields:
        - canonical_entity_id
        - entity_type
        - preferred_name
        - aliases
        - source_support
        - unresolved_conflicts
    run_manifests:
      type: list
      item_fields:
        - run_id
        - source_ids
        - section_artifact_ids
        - downstream_artifact_ids
        - validator_verdict
    graph_key_plan:
      type: object
      required_prefixes:
        - authors
        - source_docs
        - source_chapters
        - source_sections
        - evidence
        - entities
        - lore_facts
        - lore_events
        - tom_states
        - relationship_states
```

Review question: are these the right persistent fields, or should persistent memory be limited to a smaller subset with run artifacts carrying the rest?

## Proposed Output Contract

The `librarian` should produce files/receipts, not silent mutation:

```text
source-catalog.jsonl
ordered-ingestion-manifest.json
identity-registry-delta.jsonl
graph-key-plan.json
upsert-candidate-manifest.json
librarian-validation.json
memory-receipt.json
```

Minimum validation expectations:

- every source has a stable id, type, title, creator/author/source attribution, and hash
- every graph key candidate follows namespace policy
- every upsert candidate has evidence linkage or is rejected as incomplete
- every identity merge has source support or is marked unresolved
- no final graph mutation is claimed from the librarian artifact alone

## Proposed Graph Shape For Downstream Materialization

Vertex collections:

```text
authors
source_docs
source_chapters
source_sections
evidence
entities
lore_facts
lore_events
tom_states
relationship_states
style_notes
canon_rules
```

Edge collections:

```text
has_author
has_chapter
has_section
from_section
supported_by
has_subject
has_object
held_by
about_fact
about_event
about_entity
targets
relationship_from
relationship_to
style_of
```

Example ToM linkage:

```text
tom_states/tom_001 --held_by--> entities/horus
tom_states/tom_001 --about_fact--> lore_facts/fact_001
tom_states/tom_001 --supported_by--> evidence/ev_001
```

Review question: should the librarian define this graph shape, merely enforce an existing schema, or defer graph shape entirely to a graph-materializer/lore-extractor?

## Proposed Help Policy

Bounded helper calls only:

```yaml
help_policy:
  max_helper_calls_per_turn: 3
  allowed_helpers:
    - helper_agent: doc-extractor
      allowed_for:
        - missing raw spans
        - broken offsets
        - section order repair
        - source hash mismatch
    - helper_agent: doc-qra
      allowed_for:
        - recall aid generation from validated source sections
        - summary/QRA provenance references
    - helper_agent: lore-extractor
      allowed_for:
        - lore fact candidates
        - Theory-of-Mind candidate records
        - relationship state candidates
      note: future persona; not yet present
    - helper_agent: edge-verifier
      allowed_for:
        - candidate edge validation
        - evidence linkage check
```

Review question: should `librarian` be allowed to summon `lore-extractor`, or should the project agent coordinate that step separately?

## Proposed Persona Summary

If accepted, the persona should likely say:

```text
You are the persistent librarian for source and graph readiness. You maintain source identity, ordering, provenance, namespace keys, and upsert-candidate manifests for lore workflows. You may use memory to recall and store scoped catalog decisions with receipts. You do not perform final lore inference, ToM inference, or direct ArangoDB graph mutation. You emit auditable manifests and validation reports for project-agent approval.
```

## Questions For WebGPT

1. Should this be a persistent top-level subagent?
2. Should the id be `librarian`, `lore-librarian`, `graph-librarian`, or something else?
3. Should it have direct `$ops-arango` access? If yes, should that be read-only/schema-only/dry-run-only?
4. What exact ownership boundary prevents overlap with `doc-extractor`, `doc-qra`, future `lore-extractor`, `edge-verifier`, and the project agent?
5. Which fields belong in persistent memory, and which should remain per-run artifacts?
6. Should the librarian define graph schema, enforce an existing graph schema, or only produce key/provenance plans?
7. What concrete corrections are needed before creating a `personas/librarian/persona.yaml`?
