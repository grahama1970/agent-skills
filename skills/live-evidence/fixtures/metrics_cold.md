# Metrics cold — per-agent-run signals and their receipts

The list to know without notes. Each signal names where it lives in my
systems today (the receipt), so any answer can drop to a concrete artifact.

## Per run / per node

- Tokens and cost per node — fast_solver_receipt and node receipts carry
  model, effort, latency segments; budget enforcement is a typed stop
  (RunBudget pattern: cycles, tokens, cost, elapsed, repeated tool-call
  signatures).
- Latency per node, split by segment — queue wait, retrieval, first content,
  total. Live floor measured on my copilot: p50 about 2s, p95 about 5s to
  first answer content; a 30-question latency gate is an eval case, not a
  dashboard hope.
- Status ladder per node — COMPILED / DISPATCHED / ACKNOWLEDGED / CANDIDATE /
  SETTLED. CANDIDATE exists so an unadmitted answer can never read as
  success; absence is reported, never dropped.
- failure_code taxonomy per lane, with recovery packet and next_command.
- Model provenance — requested vs resolved model, requested vs dispatched
  reasoning effort, downgrade reason, rate-limit substitutions recorded.
  Absence of evidence is never confirmation of the tier that answered.

## Retrieval and grounding

- Retrieval precision per lane (BM25 / vector / graph are calibrated
  separately; one shared threshold is a category error).
- Groundedness: answers are admitted, not assumed — answerability gate before
  generation, independent verifier after, citation-to-source attribution with
  content hashes. Never the same model as answerer and sole judge:
  deterministic attribution check, independent semantic check, sampled human
  slice.
- Unsupported-answer rate, segment-level (the metric that catches the
  zero-evidence-confident-answer failure). Insufficient results are held from
  publication and journaled — the fail-closed decision is itself observable.
- Confidence calibration per card; freshness of every cited source.

## Safety and compliance

- PII detection at choke points: prompt preflight before submission,
  trace/journal redaction, policy digests freezing session capabilities.
- Audit: immutable goal hash in every receipt; events.jsonl + handoff chain =
  books-and-records by construction.

## Alerting

- Alert on versioned dimensions (model, prompt, tool, policy, index, tenant),
  not just service health — the Tuesday case is flat errors with rising
  badness.
- Segment thresholds and rollback triggers set at launch (no single
  aggregate accuracy number).

## The differentiated closer

The strongest signal is a verifier that cannot be sweet-talked: my Lean 4
pipeline scores generations by whether the compiler accepts the proof —
binary, unfoolable, and it trains the generator (compiler-in-the-loop
reward). Fintech translation: independent verification of transaction
integrity, not model self-report.
