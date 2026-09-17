---
name: jev
description: >
  Ask TypeSafe Jev (System One) typed judgment questions: state in, typed answers
  with probabilities and confidence out. Use for bounded semantic decisions that
  today burn a text-LLM roundtrip plus JSON parsing: failure triage against a
  catalog, goal-drift labeling, evidence/claim stance checks, reviewer-gate
  criterion screening, taxonomy classification tiers. Enforces house policy:
  egress gate, fail-closed abstention, state-hash binding, execution_runs
  telemetry. NOT for retrieval, open-ended generation, entity extraction
  replacement, or sub-200ms paths.
triggers:
  - jev
  - typesafe
  - system one judgment
  - typed decision
  - calibrated decision
provides:
  - jev ask (typed judgment calls with fail-closed receipts)
  - versioned question presets for triage, goal-drift, edge stance, tau gates
composes:
  - memory
  - triage-error
  - tau
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
taxonomy:
  - validation
  - classification
  - resilience
runtime_self_improvement: none
disciplines:
  - engineering-standards
  - evaluation-quality
---

# Jev — typed judgments for agent harnesses

Jev evaluates a `state` against typed questions and returns structured answers
(`choice` / `score` / `noul`) with probabilities and confidence — no text
generation, no parsing. 70–500ms, $0.042/MTok input (output free), hosted-only.

## When to use Jev (and when not)

| Use Jev for | Do NOT use Jev for |
|---|---|
| Closed-set classification (failure codes, drift labels, stances) | Retrieval / recall (no LLM on that path anyway) |
| Screening a review bundle criterion-by-criterion | Replacing deterministic extractors (Flashtext/RapidFuzz) |
| Selecting among locally-enumerated candidates | Open-ended generation, novel query plans |
| Confidence-routed escalation decisions | Sub-200ms fast paths (never add a network hop) |
| Anything currently: LLM -> JSON -> repair_json -> parse | Final completion/release authority (receipts decide) |

Full judgment-design guidance: `references/question-design.md`.
Official TypeSafe agent guidance (vendored, MIT): `vendor/typesafe-ai-official.md`.

## Commands

```bash
./run.sh tasks                                   # list question presets
./run.sh gate --state @state.json                # egress-gate check only (no call)
./run.sh ask --preset goal_drift --state @state.json --allow-egress
./run.sh ask --questions @my_questions.json --state '{"error": "..."}' --allow-egress
```

`ask` prints a `jev.receipt.v1` JSON: answers, probabilities, decision
(`accept` / `abstain`), thresholds, state+questions hashes, model, usage, took_ms.
Abstention and errors exit nonzero — fail closed, never fabricate.

## House policy (enforced by the adapter, not by convention)

1. **Egress gate**: every call requires `--allow-egress` (or `JEV_EGRESS_POLICY=allow`)
   AND must pass the restricted-marker scan (CUI markings, blocked terms). Unknown
   policy = no request. Authorize the COMPLETE payload — questions and criteria
   are transmitted too.
2. **Fail-closed**: low confidence (<0.98 default), timeout, 429/529, missing or
   malformed answer → `abstain`/`error` receipt, nonzero exit. Callers route
   abstentions to the existing LLM cascade. Keeping the fallback does NOT make a
   confidently-wrong answer safe — acceptance thresholds are the control.
3. **Binding**: receipts carry sha256 of state, question map, and model id. A
   cached verdict must never approve changed content.
4. **Telemetry**: durations POST to memory `/execution-runs` (best effort).

## Threshold defaults (env-overridable)

`JEV_ACCEPT_CONFIDENCE=0.98` (choice/score accept bar), `JEV_ACCEPT_NOUL=0.98`
(noul extreme bar), `JEV_TIMEOUT_S=10`, `JEV_MODEL=jev-latest`.
Tune per task AFTER shadow measurement — these are starting points, not
established performance. Escalation cost math: with fallback rate F,
E[latency] = T_jev + F·T_fallback — measure F before promising wins.

## Question presets (`questions/*.json`, versioned)

| Preset | For | Questions |
|---|---|---|
| `triage_error` | triage-error skill: classify unresolved failures | `failure_code` (Choice over catalog + no_match) |
| `goal_drift` | goal-drift nightly labeling | `goal_relation`, `scope_relation`, `progress_novelty` |
| `edge_stance` | memory edge-verifier | `stance` (verifies/contradicts/related/unrelated/insufficient_evidence) |
| `tau_gate` | tau reviewer screening | `criterion_support`, `blocker_disposition` |

Presets are templates: generate `criteria` from the LIVE versioned catalog at
call time (e.g. actual failure codes), never inline stale copies.
