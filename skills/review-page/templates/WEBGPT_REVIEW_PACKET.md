# WebGPT Page Review Packet

## Target

Page: {{PAGE_NAME}}  
Route: {{ROUTE}}  
Lead persona: {{PERSONA}}  
Review round: {{ROUND_ID}}  

## Required decision

Return:

```text
VERDICT: PASS | NEEDS_CHANGES | BLOCKED | HUMAN_REQUIRED
PAGE_VERDICT: pass | degraded | fail | insufficient_evidence
NEXT_STEP: IMPLEMENT | CLARIFY | NONE
CODE_RUNNER_ACTIONS:
1. ...
2. ...
3. ...
CLARIFYING_QUESTIONS:
1. ...
2. ...
3. ...
```

## Non-claims

- Do not claim overall product readiness unless explicitly proven.
- Do not treat accepted ledger phases as page readiness.
- Do not accept screenshot-less visual claims.
- Do not override deterministic failure with opinion.
- Do not infer missing screenshots, qids, or JSON.

## Page purpose

{{PAGE_PURPOSE}}

## Benchmark research summary

{{WEB_RESEARCH_SUMMARY}}

## Persona lens

Persona: {{PERSONA}}

Must judge:

- layout hierarchy
- workflow fit
- evidence clarity
- visible degraded/failure states
- dashboard-theater risk
- next code-runner actions

Persona-specific concern:

{{PERSONA_CONCERN}}

## Evidence inventory

| Artifact | Path | Current? | Notes |
|---|---|---:|---|
| Page contract | `evidence/page-contract.json` | {{YES_NO}} | {{NOTES}} |
| Test interactions | `evidence/test-interactions-results.json` | {{YES_NO}} | {{NOTES}} |
| API/monitor state | `evidence/api-state.json` | {{YES_NO}} | {{NOTES}} |
| Derived page state | `evidence/derived-page-state.json` | {{YES_NO}} | {{NOTES}} |

## Deterministic test-interactions summary

| # | qid | Element / state | Action | Expected result | Actual result | Verdict | Caveat | Screenshot |
|---:|---|---|---|---|---|---|---|---|
| 1 | `{{QID}}` | {{STATE}} | {{ACTION}} | {{EXPECTED}} | {{ACTUAL}} | {{PASS_FAIL_WARN}} | {{CAVEAT}} | `screenshots/{{IMAGE}}` |

## Screenshot inventory

| # | Screenshot | State | Expected | Notes |
|---:|---|---|---|---|
| 1 | `screenshots/01-full-page.png` | Full page | Overall hierarchy visible | |
| 2 | `screenshots/02-primary-workflow.png` | Primary workflow | Main user task visible | |
| 3 | `screenshots/03-evidence-state.png` | Evidence/degraded state | Proof/caveat visible | |

## Image-by-image review request

For each screenshot, judge:

1. Is the expected state visible?
2. Is the hierarchy clear?
3. Is the evidence/failure state visible?
4. Is anything green/complete without proof?
5. What exact code-runner action follows?

## Dashboard-theater audit

Flag as fail if:

- green status hides stale/degraded source
- evidence labels do not resolve
- missing evidence appears as normal success
- refresh/navigation loses proof but UI still looks complete
- user cannot tell what is current vs cached

## Required output

Use the exact decision block above.
