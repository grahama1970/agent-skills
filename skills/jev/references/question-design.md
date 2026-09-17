# Jev question design — house patterns

Derived from the TypeSafe docs (full bundle), the official skill
(`vendor/typesafe-ai-official.md`), and the 2026-09-17 WebGPT consult
(`/tmp/webgpt-jev/02_response.md`, transport-proven).

## The five rules

1. **One evidence-backed judgment per question.** A "gut-check a knowledgeable
   person makes in seconds given the right context." If it needs weighing
   multiple factors, decompose into factors and combine in code.
2. **Question IDs are never sent to the model.** Put the complete meaning in
   `instructions`. Reference state parts with backticked paths
   (`ticket.messages[0].text`).
3. **Always provide an escape hatch.** `INSUFFICIENT_CONTEXT` /
   `insufficient_evidence` / `no_match` — abstention is the adapter's, not a
   business label. Never coerce an unknown into a positive label.
4. **Choice for nominal verdicts, Score only for real spectra.**
   PASS/FAIL/BLOCKED are not points on a spectrum — use Choice. Score's
   probability-weighted mean can hide two very different risk distributions.
5. **Criteria carry concrete definitions**, not single words. "SATISFIED:
   The supplied evidence directly establishes every obligation…" not "good".

## State construction

- Give each question enough state to answer: source text, identities,
  relationships, policies, current facts. Named JSON fields when context has
  several parts.
- **Never feed a creator's "all checks passed" summary as evidence.** Bind to
  receipts/artifacts obtained independently. Schema-safe output does not make
  untrusted input safe — injected instructions can aim for a perfectly valid
  label.
- Keep deterministic facts OUT of Jev: compute exit codes, schema checks,
  receipt authenticity locally; ask Jev only the semantic residue.

## Confidence routing

- Confidence = distribution concentration, NOT correctness. Store the full
  distribution; calibrate on the residual traffic your local tiers don't solve.
- Route by cause: low-confidence-with-evidence → LLM tier; missing evidence →
  evidence acquisition (a bigger model reading the same incomplete bundle
  cannot supply a missing test result); disallowed egress → bypass before
  transmission.
- Per-task (and where costs differ, per-label) thresholds. A false SERVES_GOAL
  label and a false release approval are not interchangeable.
- Expected latency with fallback rate F: `T_jev + F·T_fallback`. Measure F.

## Composed-gate warning

Atomic questions over the same misleading passage fail TOGETHER. Measure the
composed gate's false-positive rate, not each question's accuracy. Nine
satisfied criteria never compensate for one violated mandatory one — enforce
mandatory-check precedence in the reducer, and never average criterion scores
into a release verdict.
