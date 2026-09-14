---
name: qra-grade-advice
description: >
  Fetch or validate one QRA, run the speed-first grading/advice contract, and
  emit a typed qra_grade_advice.v1 packet for Graham review. Use when users say
  grade this QRA, review a QRA, run QRA advice, process the QRA pool, evaluate
  QRA rationale, or decide whether slow browser reviewers like WebGPT are worth
  the latency.
triggers:
  - grade this QRA
  - review a QRA
  - run QRA advice
  - process QRA pool
  - QRA grade advice
  - evaluate QRA rationale
  - WebGPT QRA value gate
provides:
  - qra-grade-advice
  - qra-pool-worker
  - qra-browser-value-gate
composes:
  - best-practices-qra
  - best-practices-prompt
  - best-practices-python
  - best-practices-security
  - best-practices-report
  - best-practices-subagent
  - deslop
  - ponytail
  - brave-search
  - dogpile
  - arxiv
  - ask
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
runtime_self_improvement: basic
taxonomy:
  - qra
  - grading
  - provenance
  - evaluation
  - speed
  - browser-review
disciplines:
  - evaluation-quality
  - agentic-orchestration
  - research-retrieval
  - engineering-standards
---

# qra-grade-advice

Speed-first QRA grading/advice skill. It turns one `qra_pool.item.v1` into one
`qra_grade_advice.v1` packet. The packet is advisory until Graham accepts it.

## Commands

```bash
./run.sh validate-qra fixtures/sample_qra.json
./run.sh fixture fixtures/sample_qra.json --out /tmp/qra-grade-advice.json
./run.sh validate-advice /tmp/qra-grade-advice.json
./sanity.sh
```

`pool-once` is intentionally thin and conventional: it leases one item from
`POST <pool-url>/lease`, emits local deterministic advice, then posts to
`POST <pool-url>/advice`. Use it only after the pool API adopts the schemas in
`qra_grade_advice.models`.

```bash
./run.sh pool-once --pool-url http://127.0.0.1:8787
```

## Workflow

1. Validate inbound `qra_pool.item.v1` with Pydantic before any prose or model use.
2. Run deterministic local checks first.
3. Prefer fast Pi/API lanes for ordinary QRAs.
4. Escalate to browser advisors only when the value gate says they may change the outcome:
   disagreement, low confidence, client-sensitive/high-impact item, security/compliance
   concern, explicit request, or calibration sampling.
5. Emit typed `qra_grade_advice.v1` with lane latency/value fields.
6. Keep browser/model language provenance-labeled as advisory draft text.

## WebGPT latency rule

WebGPT is not a default blocker for ordinary QRAs. Its 25min+ latency must be
justified by retained calibration metrics: new blocker/high findings, grade
change, rewrite-advice change, or clear usefulness. Otherwise it remains an
escalation/calibration lane.

## Proof boundary

The current local command proves schema validation and deterministic packet
shape only. It does not prove live Pi subagent fanout, `$ask` browser-panel
execution, or a real pool endpoint until those receipts exist.
