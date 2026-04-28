# `$ask argue` Prompt Payload Review Bundle

Purpose: external review fixture for the bounded `/ask --argue` prompt protocol.

Canonical invocation:

```bash
./run.sh ask "Should this service use retries or queues?" \
  --argue \
  --argue-personas "Brandon:for,Margaret:against" \
  --argue-rounds 2 \
  --oracle-backend subagent-runner
```

Route payload:

```json
{
  "schema_version": "ask.argue.prompt_payload.v1",
  "mode": "argue",
  "personas": "Brandon:for,Margaret:against",
  "rounds": 2,
  "roundtable": true,
  "roundtable_role_preset": "argue",
  "roundtable_mode": "argue",
  "oracle_backend": "subagent-runner",
  "write_policy": "artifacts_only"
}
```

Required advocate turn prompt fields:

```json
{
  "turn_number": 1,
  "round": 1,
  "persona": "Brandon",
  "protocol_role": "for",
  "required_prompt_markers": [
    "Structured argue protocol:",
    "Assigned side: FOR Advocate (for)",
    "Argue only your assigned side, but acknowledge real limits.",
    "Make claims that a neutral judge can score against the rubric.",
    "\"protocol_role\": \"for|against\"",
    "\"strongest_point\": \"...\"",
    "\"weakest_point\": \"...\""
  ]
}
```

Required judge rubric:

```json
[
  "evidence_strength",
  "failure_mode_coverage",
  "assumption_quality",
  "target_relevance",
  "falsifiability",
  "implementation_cost_or_risk"
]
```

Required judge verdict enum:

```json
[
  "FOR",
  "AGAINST",
  "NO_CLEAR_WINNER",
  "INSUFFICIENT_EVIDENCE"
]
```

Required judge output contract:

```json
{
  "verdict": "FOR | AGAINST | NO_CLEAR_WINNER | INSUFFICIENT_EVIDENCE",
  "winner": "for|against|none",
  "rubric_scores": {
    "evidence_strength": {
      "for": 0,
      "against": 0,
      "winner": "for|against|tie"
    }
  },
  "decisive_reasons": ["..."],
  "confidence": "high|medium|low"
}
```

Review requirements:

- The judge decides the stronger argument by rubric, not confidence or persona preference.
- `INSUFFICIENT_EVIDENCE` is mandatory when neither side provides grounded support.
- `NO_CLEAR_WINNER` is mandatory when sides trade off without a clear dominant case.
- The final answer must include `Verdict`, `Rubric Scores`, `Strongest FOR Argument`, `Strongest AGAINST Argument`, `Decisive Gaps`, `Project Agent Decision`, and `Confidence`.
