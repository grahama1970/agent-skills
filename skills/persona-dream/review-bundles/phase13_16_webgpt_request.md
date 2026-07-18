# Persona Dream Phase 13-16 implementation request

## Objective

Continue the founding Persona Dream experiment from the real Phase 12 provider-return observation through:

1. grounded self-interpretation tied to exact Phase 12 visual evidence and original source-memory residue;
2. explicit Theory-of-Mind candidate validation with accept/reject reasons and no identity drift;
3. persistence of the explicitly synthetic dream through the real Memory `/upsert` contract;
4. exact reread plus Qdrant semantic recall and explicit Arango graph-edge traversal proof;
5. bounded later persona/Chatterbox behavior comparison proving useful uptake without identity drift.

## Current live authority

- Repository: `agent-skills@main`
- Current remote base: `0854cd9b`
- Run: `pipeline-complete`
- Revision: `rev_idea_f3f9c48d5cc2`
- Dream: `dream_ff2ce7f310fdda2d`
- Request body SHA-256: `sha256:ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41`
- Provider request ID: `019f6bef-0c0f-7921-8a5e-a1f12890fb75`
- Provider call attempts: exactly `1`
- Provider MP4 SHA-256: `sha256:2545394fb8e48694acb2751b25cbf6fc55a4dfdbde66e241deecfb5f2f1ecd33`
- Phase 12 packet SHA-256: `sha256:835ae475ac26ae3a7e8fb79da2f570949285fd8aafbe39203ef5033adb2f95f7`
- Watch: 12/12 frames described, requested `codex-vision`, served `gpt-5.5`
- Phase 12 proof: `mocked:false`, `live:true`, provider return and Watch lineage pass with zero checker errors.

## Required implementation discipline

- Author code, schemas, validators, focused tests, `run.sh` commands, and exact execution commands as one downloadable git patch based on `0854cd9b`.
- Reuse the real `memory` skill runtime and `/upsert`; do not implement a parallel persistence client or fake Memory.
- All writes must use deterministic keys and include synthetic-content labeling, run/revision/dream/request/video/observation hashes, persona scope, and evidence references.
- Interpretation generation must be grounded in the supplied Phase 12 packet and original source-memory residue. A model response is a candidate claim, not acceptance proof.
- Validate ToM candidates separately. Preserve uncertainty and reject unsupported claims.
- Prove Memory by exact reread, semantic pointer sync, positive dense recall, and explicit graph-edge write/traversal receipt.
- Behavior proof must compare bounded baseline and post-dream probes, cite the synthetic dream only when relevant, and fail on identity/persona scope drift. Do not claim general personality change.
- No Kling/fal calls. Actual provider attempts must remain exactly one.
- Mocked tests may cover wiring only. Provide deterministic and live commands/artifacts for the real run.
- Update `PROJECT_KNOWLEDGE.md`, `README.md`, and `SKILL.md` only after the corresponding live gates pass.
- Do not return another roadmap. Return an apply-ready patch plus commands and precise pass/block states.

## Existing defect to replace

`write_cognitive_loop_dry_run.py` only emits fixed dry-run placeholders, zero Memory writes, unexecuted recall/behavior probes, and always-blocked ToM. Replace or supersede it with executable Phase 13-16 stages while keeping fixture behavior fail-closed.

## Acceptance artifacts

The implementation must produce committed artifacts under the immutable revision for:

- `phase_13_interpretation/dream_self_interpretation.v1.json`
- `phase_13_interpretation/tom_validation_receipt.v1.json`
- `phase_14_memory/dream_memory_transaction_receipt.v1.json`
- `phase_15_recall/dream_recall_receipt.v1.json`
- `phase_15_recall/dream_graph_traversal_receipt.v1.json`
- `phase_16_behavior/dream_behavior_receipt.v1.json`
- one terminal founding-experiment receipt that quotes `mocked`, `live`, `proves`, and `does_not_prove`.

End the response with a unique `<<<WEBGPT_DONE:...>>>` sentinel and attach the patch as a downloadable file.
