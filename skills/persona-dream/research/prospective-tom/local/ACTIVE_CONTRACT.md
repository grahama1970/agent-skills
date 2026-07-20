# Active Contract

Artifact: PCTOM-R Gate 0 lineage checker slice.

Input: fixture case directories containing recall receipts, normalized residue,
dream branches, and one sealed ToM prediction commitment.

Output shape: one JSON receipt with status, errors, counts, lineage links,
hash checks, and explicit claim boundaries.

Must include: accepted source-id hash recomputation, residue-to-recall
resolution, branch-to-residue resolution, prediction-to-branch resolution,
prediction evidence-to-residue resolution, sealed-before-reveal check, and
probability-sum checks.

Must not include: model calls, provider calls, memory writes, Phase 01-16 state
machine changes, outcome scoring claims, or semantic quality claims.

Runtime/tooling: Python standard library only.

Inspection method: run `scripts/check_prospective_tom_protocol.py` against
positive and negative fixtures.

Failure conditions: malformed JSON, missing required files, source-id hash
mismatch, unresolved residue, unresolved dream branch, unsealed prediction,
bad prediction payload hash, or invalid probability distribution.

Allowed writes: files under `skills/persona-dream/research/prospective-tom/`
and a `run.sh` dispatch entry for the checker.

Forbidden writes: memory records, provider receipts, production Phase 01-16
state files, generated image/video/audio artifacts.

Report format: command outputs and the generated JSON receipts.
