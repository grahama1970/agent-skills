# Active Contract

Artifact: PCTOM-R Gate 3 counterfactual branch invariant checker.

Input: Gate 1 social episode corpus, one sealed Gate 2 ToM belief-distribution
bundle, and one counterfactual branch bundle.

Output shape: one JSON checker receipt with status, errors, counts, invariant
checks, branch/distribution bundle hashes, and explicit claim boundaries.

Must include: factual branch presence, counterfactual branch presence, synthetic
counterfactual marking, one intervened variable per counterfactual branch,
held-fixed exclusion of the intervened variable, visible evidence resolution,
BDI distribution ref resolution, factual/counterfactual distribution separation,
action-distribution checks, outcome-hidden check, and no canonical memory
writes.

Must not include: model calls, provider calls, memory writes, Phase 01-16 state
machine changes, outcome scoring claims, calibration claims, or prediction-
accuracy claims.

Runtime/tooling: Python standard library only.

Inspection method: run `scripts/check_counterfactual_branches.py` against the
positive Gate 3 branch bundle and targeted negative branch bundles.

Failure conditions: malformed JSON, missing fields, visible outcome, canonical
memory write, missing factual branch, missing counterfactual branch,
counterfactual not synthetic, factual branch with an intervention, no
intervention variable, held-fixed/intervened-variable conflict, unresolved or
hidden source evidence, unresolved distribution ref, factual branch using a
counterfactual distribution, counterfactual branch using a factual
distribution, invalid action probability sum, or action outside the episode
allowed action vocabulary.

Allowed writes: files under `skills/persona-dream/research/prospective-tom/`
and `run.sh` dispatch entries for the checker.

Forbidden writes: memory records, provider receipts, production Phase 01-16
state files, generated image/video/audio artifacts.

Report format: command outputs and the generated JSON receipts.
