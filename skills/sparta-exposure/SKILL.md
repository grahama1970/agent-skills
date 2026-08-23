---
name: sparta-exposure
description: >
  Route SPARTA/F-36 exposure questions through grounded Memory entity extraction,
  evidence-case construction, monitor-sparta freshness context, and Sparta
  Explorer Coverage/Supply Chain navigation without inventing controls,
  crosswalks, or live exposure facts.
allowed-tools:
  - Bash
  - Read
metadata:
  short-description: SPARTA/F-36 exposure request adapter
---

# SPARTA Exposure

Use this skill when a user asks about SPARTA/F-36 exposure, blast radius,
coverage exposure, control exposure, or supply-chain exposure.

This is not a new source of truth. It is a request-time adapter that composes
existing SPARTA pipeline skills and Explorer read models.

## Scope

The v1 scope is SPARTA/F-36 only.

Do not generalize this skill to arbitrary enterprise risk, generic GRC,
non-SPARTA cyber posture, or non-F-36 programs until the human explicitly asks
for that next domain.

## Source Responsibilities

- `/memory` owns intent routing, recall, QRA retrieval, and request records.
- `/extract-entities` owns entity grounding. Its `proof_packet.assertions`,
  `resolution_map`, `nodes.anchors`, and `nodes.unsupported` are the grounding
  authority.
- `/create-evidence-case` owns crosswalk chains, QRA/evidence snapshots, and
  candidate QRA review flow.
- `/monitor-sparta` owns pipeline health, coverage findings, backlog state, and
  freshness/staleness receipts. It does not prove the answer by itself.
- Sparta Explorer Coverage and Supply Chain pages render existing read models
  and provide `data-qid` navigation targets. The UI does not decide grounding.

## Request Flow

1. Run the normal `/memory` intent path.
2. Run `/extract-entities` on the full user question before answering.
3. Read grounding from the extractor's structured fields, not from BM25 overlap,
   prompt keywords, regexes, or hand-authored exposure phrase lists.
4. If the question has no grounded SPARTA/F-36 target, ask a clarification.
5. If the question contains both a grounded control and an unsupported premise,
   clarify the unsupported premise instead of answering from the grounded
   control alone.
6. If grounded entities are sufficient, build or fetch a `/create-evidence-case`
   result for the target control, relationship, or QRA.
7. Add `/monitor-sparta` context only as freshness and coverage status. If the
   latest monitor receipt is stale, say it is stale and fail closed for live
   exposure claims.
8. For vendor, supplier, and blast-radius questions, connect the answer to the
   Sparta Explorer Supply Chain read model when available.
9. For control-family, QRA, and coverage questions, connect the answer to the
   Sparta Explorer Coverage read model when available.
10. Answer only from the evidence case, grounded QRA content, monitor receipt,
    and read-model records. Otherwise clarify.

## Required Routing Cases

| User question | Required route |
| --- | --- |
| `what is our exposure?` | `clarify_missing_target` |
| `what is our exposure for AC-3?` | `extract_entities_then_create_evidence_case` |
| `what is our exposure from CM0001 to DE-0009.05?` | `relationship_evidence_case` |
| `show supplier exposure for vendor X` | `supply_chain_read_model_then_evidence_case_if_grounded` |
| `how does AC-3 relate to ham sandwiches?` | `clarify_unsupported_premise` |
| `what is our exposure to flying saucers?` | `clarify_or_deflect_ungrounded_term` |

The `flying saucers` example is intentionally a red-flag example, not a SPARTA
corpus term. It must never be preserved as grounded vocabulary.

## Output Contract

Return a structured exposure packet before any prose answer:

```json
{
  "schema": "sparta.exposure.v1",
  "scope": "SPARTA/F-36",
  "question": "...",
  "route": "answer|clarify|deflect",
  "answerability": "grounded|needs_clarification|unsupported_premise|no_match|stale_context",
  "target_entities": [],
  "unsupported_terms": [],
  "entity_context_ref": "entity_context.json or service receipt",
  "evidence_case_ref": null,
  "monitor_sparta_ref": null,
  "monitor_freshness": "fresh|stale|unavailable",
  "read_model_refs": [],
  "recommended_ui_targets": []
}
```

The prose answer may follow this packet, but the packet is the reviewable
artifact humans and agents should inspect first.

## Sparta Explorer UX Hooks

Use `data-qid` values only as navigation and review anchors. They are not proof.

Known useful targets:

- Coverage page and coverage actions for QRA/control-family evidence review.
- Supply Chain page and supply-chain actions for vendor, supplier, dependency,
  and blast-radius review.
- Chat content items for evidence cases, draft QRAs, and interview review forms.

When the answer chooses an existing QRA, the human-facing item should expose the
full QRA question, reasoning, answer, evidence case reference, and a similarity
or match score comparing the user's question to the QRA question.

## Draft And Human Signoff Boundary

If no existing QRA answers a grounded exposure question, create only a draft
candidate. A draft must still pass:

1. `/memory` intent routing.
2. `/extract-entities` grounding.
3. `/create-evidence-case` crosswalk/evidence construction.
4. Creator/reviewer review.
5. Human review through an `/interview` content item in chat.
6. Recorded human signoff before promotion to approved QRA content.

The human must be able to edit the draft question, reasoning, answer, alternate
question phrasings, and final signoff decision.

## Fail-Closed Rules

- Do not answer bare `what is our exposure?`; ask for a target such as a control,
  supplier, component, mission thread, artifact, or QRA.
- Do not answer an unsupported premise by leaning on an unrelated grounded term.
- Do not let BM25 overlap ground nouns that `/extract-entities` marked
  unsupported.
- Do not present stale `/monitor-sparta` output as live operational exposure.
- Do not invent crosswalk chains, controls, vendors, suppliers, or QRA facts.
- Do not bypass `/create-evidence-case` for relationship exposure.
- Do not use regex, keyword lists, or exposure phrase lists for intent routing.

## Validation

Run the local contract guard:

```bash
./run.sh check --json
```

Run the agentic eval fixture from the `agentic-evals` skill:

```bash
/home/graham/workspace/experiments/agent-skills/skills/agentic-evals/run.sh run fixtures/agentic_eval.json
```

This proves only the local skill contract and examples. It does not prove live
Memory, ArangoDB, monitor-sparta, or Sparta Explorer integration.
