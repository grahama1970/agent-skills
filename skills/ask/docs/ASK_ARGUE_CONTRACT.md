# /ask Argue Contract

`/ask argue` is an adversarial decision protocol. It uses two parallel
read-only `/scillm` advocate calls followed by one sequential `/scillm` judge
call and a deterministic verifier.

```text
FOR advocate || AGAINST advocate
  ↓
sequential judge
  ↓
deterministic verifier
  ↓
argue.md + argue.json artifacts
```

## Non-Goals

- `/ask argue` does not edit files.
- `/ask argue` does not silently invoke `/code-runner`.
- `/ask argue` does not force certainty by default.

## `/scillm` Adapter Requirements

The default backend is `/scillm`, not a single local model prompt. The runtime
must follow the `/ask` DAG and `/scillm` skill contract:

- call `POST /v1/chat/completions`;
- set `Authorization: Bearer sk-dev-proxy-123`;
- set `X-Caller-Skill: ask`;
- request `response_format: {"type": "json_object"}`;
- omit `max_tokens`;
- run the FOR and AGAINST calls with `asyncio.create_task` and
  `asyncio.as_completed`;
- run the judge only after both advocate outputs are available.
- attach `scillm_metadata` to every node with `ask_id`, `protocol`,
  `node_id`, `node_role`, `batch_id`, `item_id`, `question_hash`,
  `source_bundle_id`, and `artifact_dir`;
- pass a serialized source bundle through `/scillm` `source` so grounding
  diagnostics are available without exposing fabricated IDs to the model.

`/ask` stores returned `/scillm` observability fields under each node's
`scillm` object, including call id, returned metadata, grounding status, and
batch-resume indicators when the proxy supplies them.

## Verdicts

The judge must return one of:

```text
FOR
AGAINST
NO_CLEAR_WINNER
INSUFFICIENT_EVIDENCE
```

`FOR` or `AGAINST` is only admissible when the judge identifies:

1. the deciding criterion;
2. the evidence supporting the winning side;
3. the strongest counterargument;
4. why the counterargument does or does not overturn the verdict;
5. what evidence would change the verdict.

Otherwise the judge must use `NO_CLEAR_WINNER` or `INSUFFICIENT_EVIDENCE`.

## Required Judge Fields

```json
{
  "verdict": "FOR | AGAINST | NO_CLEAR_WINNER | INSUFFICIENT_EVIDENCE",
  "confidence": "low | medium | high",
  "decision_required": false,
  "tie_breaker": "",
  "decision_criterion": "",
  "winning_side": "FOR | AGAINST | none",
  "deciding_factors": [],
  "strongest_for_argument": "",
  "strongest_against_argument": "",
  "strongest_counterargument": "",
  "why_counterargument_does_or_does_not_win": "",
  "evidence_used": [],
  "assumptions": [],
  "missing_evidence": [],
  "what_would_change_the_verdict": [],
  "recommended_next_action": "",
  "uncertainty_disclosure": ""
}
```

## Verifier Rules

The verifier rejects:

- `FOR` or `AGAINST` with empty `evidence_used`;
- `FOR` or `AGAINST` with no `strongest_counterargument`;
- `FOR` or `AGAINST` without a counterargument resolution;
- `FOR` or `AGAINST` without `what_would_change_the_verdict`;
- `high` confidence when `missing_evidence` is non-empty;
- `NO_CLEAR_WINNER` without tie-breaking evidence requirements;
- `INSUFFICIENT_EVIDENCE` without listing missing evidence;
- judge evidence that does not come from advocate outputs.

## Failure Semantics

`/ask argue` must fail closed. A failed advocate or judge `/scillm` call must
not bubble out as an unstructured exception after losing protocol artifacts.

Required behavior:

- one advocate fails: write both advocate artifacts, mark the failed advocate as
  `status: failed`, skip the judge, write `judge.json`, `argue.json`, and
  `verifier.log`, then enter `needs_attention`;
- judge fails: preserve both advocate artifacts, write `judge.json` with
  `status: failed`, write `argue.json` and `verifier.log`, then enter
  `needs_attention`;
- timeout errors use the same `needs_attention` path and record `error_type`;
- safe default is always `do_not_trust_verdict`.

The `needs_attention.reason` for backend failures is:

```text
argue_scillm_call_failed
```

## Decision Required

By default, `/ask argue` allows calibrated abstention. A forced binary call
requires explicit intent:

```bash
./run.sh ask "argue whether we should do X" \
  --argue \
  --decision-required \
  --tie-breaker more-reversible
```

Allowed tie-breakers:

```text
lower-risk
more-reversible
simpler
cheaper-to-test
fail-closed
higher-upside
```

With `--decision-required`, the judge must still disclose uncertainty.
