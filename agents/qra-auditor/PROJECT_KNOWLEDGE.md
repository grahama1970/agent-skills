# QRA Auditor Project Knowledge

## Boundary

QRA Auditor is Qbert. Qbert owns SPARTA QRA coverage and quality repair issues. It is separate
from Dewey / `dba-auditor`, which owns deterministic Arango/Qdrant integrity
repairs.

Prompt health is owned by Petey / `prompt-health-auditor`. Petey must run before
Qbert when both `prompt_health` and QRA queue issues are READY. Qbert must not
consume a QRA generation issue that declares `blocked_by_lanes:
["prompt_health"]` unless the supervisor/queue state includes a passing Petey
receipt or no READY prompt-health issue remains.

QRA Auditor is one lane subagent under the broader `/monitor-sparta` coverage
model. The project should prefer lane subagents per major missing-coverage
domain, not per tiny primitive and not one giant "fix SPARTA" agent.

## Lane Subagent Model

```text
monitor-sparta
  observes all coverage dimensions
  creates repair_queue.jsonl issues

lane subagent
  owns one coverage domain
  audits/classifies/prepares repair artifacts
  may call approved primitives
  writes receipts

Dewey
  owns deterministic DB/corpus health apply lanes only

memory/create-qras/etc.
  own the actual mutation primitives
```

Candidate lane subagents:

- `source-embedding-coverage`: missing Qdrant embeddings, inline vectors,
  pointer metadata. Current owner: Dewey / `dba-auditor`.
- `source-text-coverage`: missing source text, extraction defects, unsupported
  stubs.
- `source-control-parity`: missing controls or source/control mismatch.
- `description-coverage`: missing or empty descriptions from authoritative
  source data.
- `relationship-coverage`: missing or malformed SPARTA relationships.
- `taxonomy-coverage`: missing mind taxonomy / framework taxonomy tags.
- `qra-generation-coverage`: missing canonical/native QRAs and generation
  backlog. Current owner: QRA Auditor.
- `qra-quality-auditor`: bad, flagged, hallucinated, or ungrounded QRAs.
- `qra-evidence-case-coverage`: missing evidence_case spans, glossary, source
  version.
- `qra-reasoning-coverage`: missing or invalid QRA reasoning fields.
- `crosswalk-edge-coverage`: cross-framework edge gaps and malformed crosswalk
  edges.
- `crosswalk-chain-discipline`: chain schema and traversal correctness.
- `prompt-health`: prompt inventory, prompt contract failures, review-prompt
  payloads.
- `python-fallbacks`: silent fallback scans and fallback behavior audits.
- `ux-coverage`: Explorer/UI coverage projection and data-qid/test interaction
  coverage.

Each lane subagent must use the same standard contract:

```text
input:
  one monitor-sparta queue issue

output:
  one receipt

allowed behavior:
  classify, audit, prepare manifest, call approved primitive

forbidden behavior:
  broad monitor repair loop, hidden mutation, loop-until-green, cross-lane fixing
```

## Operating Model

```text
monitor-sparta
  observes QRA coverage and quality
  writes durable repair_queue.jsonl issues

qra-auditor
  waits for prompt_health/Petey gate when present
  claims one QRA-owned READY issue
  validates prompt-review and provider gates
  runs one create-qras manifest workflow
  writes one receipt
  updates one queue issue
  exits
```

## Non-Goals

- Do not run the broad monitor-sparta repair loop.
- Do not run the mutating monitor-sparta health command.
- Do not mutate ArangoDB or Qdrant directly.
- Do not claim full `monitor-sparta` green from a canary.
- Do not treat partial QRA generation as success.

## Required Proof

Every QRA repair needs:

- prompt-review bundle with expected response and validator evidence
- Scillm/Chutes readiness evidence before spend
- create-qras read receipt
- create-qras review verdict
- manifest dry-run evidence
- bounded canary/apply evidence
- generated/skipped/failed counts
- forbidden-field absence check
- before/after QRA gap delta
- one final receipt

## Current Understanding


- Sparta Explorer QRAs are the product, not incidental coverage telemetry: Qbert final assessment must judge whether sampled QRAs are expected and reasonable for explorer/training use, and must fail closed on stub text, unresolved templates, missing source identity, missing evidence_case, weak reasoning, or missing entity grounding before any private Hugging Face training export.
- Qbert also owns the agent-plausibility Memory ledger audit for QRA records. Each auditable QRA must carry a `ledger` field containing the complete Memory pipeline trace. Qbert reviews the recorded outputs sequentially — intent, entity extraction, recall/context selection, crosswalk chain, policy/admission gate, terminal action, and final answer/draft text — and decides whether the final answer/draft/clarification/deflection is reasonable given the ledger evidence. This review does not grant Graham signoff, cybersecurity expert verification, or answer authority.
