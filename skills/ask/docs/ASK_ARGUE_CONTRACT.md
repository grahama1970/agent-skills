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
