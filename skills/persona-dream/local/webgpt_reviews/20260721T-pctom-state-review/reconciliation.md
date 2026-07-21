# Persona Dream PCTOM-R WebGPT Review Reconciliation

Date: 2026-07-21

## Transport Evidence

The requested WebGPT review was attempted first through the real `$ask` Tau DAG
runtime. The Tau DAG compiled and dispatched `handler-webgpt`, but the first
browser transport failed closed because the prompt referenced private local
filesystem paths that the browser reviewer could not read.

Artifacts:

- Ask request bundle:
  `skills/persona-dream/local/webgpt_reviews/20260721T-pctom-state-review/review-request.md`
- Ask DAG receipt:
  `skills/persona-dream/local/webgpt_reviews/20260721T-pctom-state-review/ask-artifacts/persona-dream-pctom-state-review-20260721/tau-receipts/dag-receipt.json`
- Recovery packet:
  `skills/persona-dream/local/webgpt_reviews/20260721T-pctom-state-review/ask-artifacts/persona-dream-pctom-state-review-20260721/node-artifacts/handler-webgpt/browser-recovery-packet.json`

The browser recovery path used a sanitized prompt with no absolute local paths:

- Sanitized prompt:
  `skills/persona-dream/local/webgpt_reviews/20260721T-pctom-state-review/webgpt-prompt-sanitized.md`
- Clean response:
  `skills/persona-dream/local/webgpt_reviews/20260721T-pctom-state-review/response.sanitized.md`
- Raw response:
  `skills/persona-dream/local/webgpt_reviews/20260721T-pctom-state-review/response.sanitized.raw.md`
- Metadata:
  `skills/persona-dream/local/webgpt_reviews/20260721T-pctom-state-review/response.sanitized.meta.json`
- Submit receipt:
  `skills/persona-dream/local/webgpt_reviews/20260721T-pctom-state-review/response.sanitized.receipt.json`

Surf metadata:

```json
{
  "status": "recovered_focus_changed",
  "proof_status": "degraded_focus",
  "response_proof_status": "response_proven",
  "submitted_to_chatgpt": true,
  "controlled_tab_id": "837360427",
  "requested_tab_id": "837360427",
  "raw_contains_sentinel": true,
  "clean_contains_sentinel": false,
  "focus_changed": true,
  "transport_degraded": true
}
```

This is usable advisory review evidence with degraded background-focus proof. It
is not deterministic local proof of any Persona Dream research claim.

## WebGPT Advisory Verdict

WebGPT's advisory assessment:

```text
The PCTOM-R research program is on track as an experimental reliability and
causal-evaluation platform, but the main scientific efficacy claim is not
currently supported.
```

The review distinguishes the narrower supported claim from the unsupported main
claim:

- Supported: Persona Dream has a substantial executable protocol and artifact
  surface for prospective conditions, action selection, revisions, recall,
  fault containment, duplicate service submission suppression, and fail-closed
  behavior in several slices.
- Not supported: the current local evidence does not show that counterfactual
  dreaming improves prospective, calibrated ToM prediction or planning.
- Negative evidence matters: current completed planning slices show CD tied,
  worse than the strongest baseline, or associated with the only observed harm.

## Source-Derived Step Model

1. Provenance-bound episode formation:
   recall query -> accepted raw source id/content hash -> normalized residue ->
   treatment assignment.
2. Partner-specific prospective state:
   predict a particular partner's future belief, intent, utterance, or action
   before observing the outcome.
3. Sealed prediction commitment:
   commit full distributions, evidence lineage, and admissible information
   before reveal.
4. Controlled counterfactual intervention:
   M/R/D/CD must be explicit versioned interventions, not prompt labels.
5. Outcome reveal and proper scoring:
   reveal only after commitment; use deterministic Brier/log-loss/calibration
   scoring.
6. Belief-to-action translation:
   prove better beliefs change constrained actions and realized regret.
7. Non-destructive revision and incremental recall:
   preserve prior prediction and error; later recall must use revisions without
   corrupting literal history.
8. Reliability surface and causal localization:
   measure repeated execution, semantic perturbations, faults, and first
   divergence.

## Status Classification

- `IMPLEMENTED`: typed protocol and schemas; M/R/D/CD condition execution;
  prediction commitments; outcome reveal and deterministic scoring machinery;
  action selection; belief revision; local/live Memory revision recall; causal
  replay artifacts; fault-injection trials; service-boundary idempotency and
  duplicate-submission suppression.
- `PARTIALLY_PROVEN`: end-to-end prospective sealing; complete provenance from
  recall query through prediction; calibration across held-out partners; live
  retry/resume through actual Tau execution; Memory security beyond exact
  reread; causal attribution of planning failure; generalization beyond four
  scenario families.
- `MISSING`: evidence that CD improves predictive score or calibration; evidence
  that CD reduces planning regret against the strongest baseline; proof that
  the action policy is sensitive to genuinely better beliefs; a powered
  preregistered family-held-out effect estimate; naturalistic multi-turn
  partner adaptation; full R(k, epsilon, lambda) reliability surface.
- `ASPIRATIONAL`: general prospective ToM improvement across models and partner
  types; robust long-horizon adaptation; secure/selectively forgetting long-term
  memory; automatic causal localization across arbitrary Tau failures;
  multimodal dreaming that adds scientific value beyond the text-first protocol.

## Reconciled Next Gate

The next engineering gate should be causal identifiability plus end-to-end
lineage, not a broader retry service and not a corpus redesign to force a CD win.

Immediate artifact targets:

- `pctom_causal_identifiability_manifest.json`
- `pctom_end_to_end_lineage_receipt.json`
- `pctom_oracle_policy_sensitivity.jsonl`
- `pctom_oracle_policy_sensitivity_receipt.json`

Required experiment:

1. Use existing sealed strict120/full64 roots; do not make new provider calls
   initially.
2. For selected episodes, reconstruct lineage:
   recall query -> accepted raw source id/content hash -> normalized residue
   hash -> condition assignment -> dream/counterfactual branch hash ->
   prediction commitment hash -> sealed timestamp -> outcome reveal hash ->
   score -> action decision -> revision.
3. Keep the action selector, action set, and utility function fixed.
4. Evaluate three belief inputs:
   actual committed distribution, oracle distribution aligned with hidden
   outcome, and anti-oracle distribution.
5. Record action, expected utility, realized regret, and action switches.

Stop conditions:

- lineage completeness below 100%;
- post-reveal information can influence a commitment;
- oracle beliefs do not reduce regret versus observed beliefs;
- anti-oracle beliefs do not worsen regret versus oracle beliefs;
- no action switches occur on episodes where the Bayes-optimal action differs.

If oracle beliefs cannot improve actions under the current policy and scenarios,
then more CD generation is not interpretable. The action policy, utility model,
or scenario identifiability must be repaired before additional efficacy runs.

## What Not To Do Next

- Do not generate video or provider-heavy dream media.
- Do not polish UX Lab dashboards.
- Do not evaluate subjective dream vividness or creativity.
- Do not scale provider calls before the action policy passes oracle
  sensitivity.
- Do not tune the corpus specifically to force a CD win.
- Do not count 64 rows as 64 independent scientific units when they derive from
  four scenario families.
- Do not rerun already accepted cells while repairing the two 502 failures.
- Do not merge synthetic revisions into canonical, identity, or source memory.
- Do not replace fail-closed behavior with permissive partial continuation.
- Do not claim general ToM from story-style or binary prediction performance.

## Current Research Claim Boundary

Current local evidence supports that PCTOM-R is now a serious executable test
platform. It does not support the main efficacy claim that counterfactual
dreaming improves prospective calibrated ToM prediction or planning. The next
proof needs to show that the policy can exploit demonstrably better beliefs
before spending more live calls on CD efficacy.
