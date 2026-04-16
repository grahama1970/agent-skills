---
name: sparta-stress-test
description: >
  Stress tests the full SPARTA query pipeline: intent classification, QRA retrieval,
  disambiguation, NLG synthesis, and error detection.
triggers:
  - sparta-stress-test
provides:
  - sparta-pipeline-validation
composes:
  - sparta-intent
  - create-figure
  - task-monitor
---

# /sparta-stress-test

Stress tests the full SPARTA query pipeline: intent classification, QRA retrieval,
disambiguation, NLG synthesis, and error detection.

## Triggers

- `/sparta-stress-test` — Run stress test with default settings
- `/sparta-stress-test run --count 100` — Run N questions
- `/sparta-stress-test run --difficulty ambiguous` — Test specific difficulty
- `/sparta-stress-test generate-bank` — Generate question bank from SPARTA data
- `/sparta-stress-test report --last-run` — Show graded results

## Composability

- Depends on `/sparta-intent` for query classification
- Depends on disambiguation guides (Brandon, Embry, Horus)
- Depends on NLG synthesis for response quality grading
- Optionally uses `/assistant` classifiers (Tier 0.5)
- Feeds results back to monitor_sparta.py convergence loop

## What It Tests

| Difficulty | % | Expected Action | Purpose |
|-----------|---|-----------------|---------|
| Simple | 30% | QUERY | Single-control, direct IDs |
| Medium | 25% | QUERY | Cross-control, multi-framework |
| Complex | 20% | QUERY | Multi-hop, F-36 LEO synthesis |
| Ambiguous | 15% | CLARIFY | Vague, overly broad queries |
| Flawed | 10% | NO_MATCH | Wrong IDs, invalid format |

## 7 Grading Dimensions

1. `action_correctness` — Did intent mapper choose the right action?
2. `name_match` — Does response reference correct control?
3. `technique_coverage` — Fraction of expected techniques found
4. `cm_coverage` — Fraction of expected CMs found
5. `disambiguation_quality` — Does clarification suggest right controls?
6. `error_detection` — Caught the bad ID? Suggested closest match?
7. `response_naturalness` — No pipe separators, no raw JSON, reads as conversation
