# Prompt-reviewer QRA generation contract review

You are the prompt-reviewer expert. Review this request only.

## Required action
Write one JSON receipt to `/mnt/data/dewey_prompt_solution/agent-skills/agents/dba-auditor/tests/fixtures/prompt-reviewer-receipt.json`.
Do not mutate the database. Do not run create-qras. Do not add embeddings.

## Required receipt fields
- schema_version: dewey.prompt-review.receipt.v1
- request_sha256: 7d0c4e54b02b27243a1bcd92b7c8233a2b2c50ab65b1c0bb7711e0074d679d82
- verdict: PASS | NEEDS_CHANGES | BLOCKED
- prompt_contract_ok: boolean
- response_contract_ok: boolean
- approved_for_qra_generation: boolean
- blocking_findings: array
- findings: array
- honesty: { mocked, live, database_mutation_allowed }

PASS is allowed only if the prompt and expected response contract are safe for candidate QRA generation.
NEEDS_CHANGES or BLOCKED must explain the exact contract defect.

## Request JSON
```json
{
  "created_at": "2026-06-25T16:59:28Z",
  "expected_response_contract": {
    "pass_requirements": [
      "verdict == PASS",
      "prompt_contract_ok == true",
      "response_contract_ok == true",
      "approved_for_qra_generation == true",
      "blocking_findings is empty",
      "receipt request_sha256 matches the request JSON"
    ],
    "receipt_path": "/mnt/data/dewey_prompt_solution/agent-skills/agents/dba-auditor/tests/fixtures/prompt-reviewer-receipt.json",
    "valid_verdicts": [
      "BLOCKED",
      "NEEDS_CHANGES",
      "PASS"
    ]
  },
  "failed_dimensions": [
    "qra_coverage_per_control"
  ],
  "honesty": {
    "database_mutation_allowed": false,
    "does_not_prove": [
      "Dewey readiness",
      "QRA generation success",
      "monitor-sparta green",
      "human QRA review"
    ],
    "live": false,
    "mocked": false
  },
  "model_pool": "qra-deepseek-pool",
  "qra_gap_context": {
    "qra_missing_generation_required": 4883,
    "repair_lane": "monitor-sparta create-qras backfill",
    "repair_owner": "Dewey DBA auditor",
    "source_health_path": null
  },
  "qra_generation_contract": {
    "database_write_policy": "candidate_only_no_inline_embeddings",
    "disallowed_output_fields": [
      "embedding",
      "embeddings",
      "vector",
      "vectors",
      "expert_blessed",
      "human_reviewed"
    ],
    "prompt_contract_ok_requirements": [
      "Prompt identifies exact SPARTA control/source/QRA gap inputs.",
      "Prompt requires structured JSON output only.",
      "Prompt forbids invented controls, sources, citations, or reviewed status.",
      "Prompt requires candidate trust state unless an external human review receipt is supplied.",
      "Prompt preserves source/provenance IDs and corpus/profile scope."
    ],
    "required_output_fields": [
      "control_id",
      "question",
      "rationale",
      "answer_type",
      "source_refs",
      "trust_state",
      "generated_by",
      "generated_at"
    ]
  },
  "request_id": "fixture-qra-review",
  "schema_version": "dewey.prompt-review.request.v1",
  "task": "review_qra_generation_prompt_contract"
}
```
