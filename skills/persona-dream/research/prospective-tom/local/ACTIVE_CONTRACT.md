# Active Contract

Artifact: PCTOM-R Gate 2 ToM belief-distribution invariant checker.

Input: Gate 1 social episode corpus plus one sealed ToM belief-distribution
bundle.

Output shape: one JSON checker receipt with status, errors, counts, invariant
checks, bundle hash, and explicit claim boundaries.

Must include: probability-sum checks, visible evidence resolution, first- and
second-order label compatibility, subject/target separation, abstain/pending
handling for unsupported hypotheses, explicit counterfactual marking, sealed
before reveal, and no canonical memory writes.

Must not include: model calls, provider calls, memory writes, Phase 01-16 state
machine changes, outcome scoring claims, calibration claims, or prediction-
accuracy claims.

Runtime/tooling: Python standard library only.

Inspection method: run `scripts/check_tom_belief_distributions.py` against the
positive Gate 2 bundle and targeted negative bundles.

Failure conditions: malformed JSON, missing fields, unsealed bundle, visible
outcome, canonical memory write, invalid probability sum, unresolved/hidden
evidence, supported hypothesis not matching a Gate 1 label, unsupported claim
not abstained/pending, factual prediction using counterfactual evidence, or
counterfactual hypothesis lacking explicit synthetic context.

Allowed writes: files under `skills/persona-dream/research/prospective-tom/`
and `run.sh` dispatch entries for the checker.

Forbidden writes: memory records, provider receipts, production Phase 01-16
state files, generated image/video/audio artifacts.

Report format: command outputs and the generated JSON receipts.
