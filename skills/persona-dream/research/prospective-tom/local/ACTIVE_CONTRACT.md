# Active Contract

Artifact: PCTOM-R Gate 1 deterministic social episode corpus.

Input: deterministic simulator templates for four scenario families.

Output shape: one development corpus JSON with 12 social episodes and one JSON
checker receipt with status, errors, counts, invariant checks, and explicit
claim boundaries.

Must include: hidden world state, counterpart beliefs/goals/preferences,
deterministic counterpart policy, information access by agent, observable
history, allowed next actions, actual next action, first-order ToM label,
second-order ToM label, and simulator-config label source.

Must not include: model calls, provider calls, memory writes, Phase 01-16 state
machine changes, outcome scoring claims, or prediction-accuracy claims.

Runtime/tooling: Python standard library only.

Inspection method: run `scripts/build_social_episode_corpus.py`, then
`scripts/check_social_episode_corpus.py` against the generated corpus and a
mutated negative corpus.

Failure conditions: malformed JSON, missing fields, wrong family counts,
actual action outside allowed actions, policy/action mismatch, missing
first-/second-order labels, non-simulator label source, LLM judge ground truth,
or episode-list hash mismatch.

Allowed writes: files under `skills/persona-dream/research/prospective-tom/`
and `run.sh` dispatch entries for the builder/checker.

Forbidden writes: memory records, provider receipts, production Phase 01-16
state files, generated image/video/audio artifacts.

Report format: command outputs and the generated JSON receipts.
