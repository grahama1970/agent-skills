# Handoff Report: Persona Dream Founding Experiment

**Timestamp**: 2026-07-16T19:40:00Z
**Active Agent**: Codex
**Operational status**: `BLOCKED_CURRENT_GATE: PHASE_13_EXECUTABLE_INTERPRETATION_MISSING`

## 1. Project Overview

- **Ecosystem**: Python pipeline and validators, TypeScript API/UI, Memory/Arango/Qdrant persistence, Scillm/Watch analysis, and a fal.ai Kling provider adapter.
- **Core purpose**: Determine whether Embry can construct a synthetic dream from grounded memory residue, watch the returned dream, form bounded self-interpretations and Theory-of-Mind candidates, persist the explicitly synthetic dream, recall it later, and exhibit useful bounded behavior without identity drift.
- **Immutable run**: `pipeline-complete`.
- **Immutable revision**: `rev_idea_f3f9c48d5cc2`.
- **Dream ID**: `dream_ff2ce7f310fdda2d`.

## 2. Current State (Doc-Code Alignment)

### Implemented reality

- Phases 01-10 are `ACTIVE_CONSISTENT` for the canonical revision, with immutable artifact qualification and Memory semantic evidence.
- Phase 11 has a submit-once adapter, hash-bound approval receipts, provider-return envelope, download receipt, and ffprobe receipt.
- The corrected Phase 11 request produced a real Kling video.
- Phase 12 binds the real provider return to a Watch observation packet and independently validates the video/frame lineage.
- Phase 13-16 remain dry-run scaffolding. No accepted grounded interpretation, accepted ToM receipt, synthetic-dream Memory transaction, graph traversal, semantic recall, or bounded behavior receipt exists.

### Documentation drift

- `README.md` still says no live provider return or Watch analysis has been proven. That is stale.
- `PROJECT_KNOWLEDGE.md` records earlier Phase 11 failures and preflight state but does not yet record the successful corrected request, provider return, or Phase 12 Watch pass.
- `SKILL.md` has not yet been updated with the real Phase 11-12 proof boundary.
- Do not update those documents to claim Phase 13-16 until live artifacts exist.

### Git state

- Served/working checkout: `/home/graham/workspace/experiments/agent-skills-main`.
- Working checkout HEAD: `590f0dd8c45623c3f038b1cd1cba2cb026bc05b1`.
- Current `origin/main` observed during handoff: `f36e42c18e6479c9fcb578168c55fbcee8030d59`.
- The live Phase 11-12 evidence is pushed on `origin/main` at `0854cd9b67b44b6a07b6abb04132d6cfe4eb79e7`.
- The served checkout is intentionally dirty and diverged. Do not reset, pull, rebase, or overwrite it.
- Use a clean worktree from current `origin/main` for proof and push; transplant only focused Persona Dream commits/patches.

## 3. What Is Working

### Phases 01-10

- Canonical revision: `rev_idea_f3f9c48d5cc2`.
- Qualification is scoped to the intended Phase 01-10 production evidence.
- Stable storyboard artifact IDs and revision-scoped asset hydration are implemented.
- Memory qualification includes deterministic records and semantic synchronization for the qualified revision.

### Phase 11 provider result

- Corrected request body SHA-256: `sha256:ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41`.
- Successful provider request ID: `019f6bef-0c0f-7921-8a5e-a1f12890fb75`.
- Successful-request ledger attempts: `1`.
- Returned MP4 size: `18,520,578` bytes.
- Returned MP4 SHA-256: `sha256:2545394fb8e48694acb2751b25cbf6fc55a4dfdbde66e241deecfb5f2f1ecd33`.
- ffprobe: 10.041667 seconds, 1280x720, H.264.
- Video path:
  `reports/pipeline-complete/.persona-dream/revisions/rev_idea_f3f9c48d5cc2/phase_11_submit_return/provider_return/ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41/provider_return.mp4`

Full disclosure: there were two provider submissions across two payload hashes. The earlier payload returned HTTP 422 because Kling rejected `end_image_url` with `multi_prompt`. It was terminally fenced and not retried. The corrected payload made one submission and succeeded. Do not report total experiment provider submissions as one.

### Phase 12 Watch result

- Observation packet:
  `reports/pipeline-complete/.persona-dream/revisions/rev_idea_f3f9c48d5cc2/phase_12_watch_observation/dream_observation_packet.v1.json`
- Packet SHA-256: `sha256:835ae475ac26ae3a7e8fb79da2f570949285fd8aafbe39203ef5033adb2f95f7`.
- Status: `PASS_DREAM_OBSERVATION_CONTRACT_PROVIDER_RETURN`.
- `mocked: false`.
- `live: true`.
- `provider_returned: true`.
- `persona_watched_provider_dream: true`.
- Watch frames: 12.
- Described frames: 12.
- Requested visual model: `codex-vision`.
- Served model: `gpt-5.5`.
- Audio absence is expected because `generate_audio=false`.
- Validator errors: `[]`.

Deterministic check:

```bash
skills/persona-dream/run.sh check-dream-observation-packet \
  --packet skills/persona-dream/reports/pipeline-complete/.persona-dream/revisions/rev_idea_f3f9c48d5cc2/phase_12_watch_observation/dream_observation_packet.v1.json \
  --run-root skills/persona-dream/reports/pipeline-complete \
  --json
```

## 4. What Is Currently Broken

### Current gate: Phase 13

`scripts/write_cognitive_loop_dry_run.py` is not an implementation of Phase 13-16. It emits:

- a fixed dry-run interpretation proposal;
- zero accepted interpretations;
- always-blocked ToM;
- zero Memory writes;
- unexecuted recall probes;
- unexecuted behavior probes.

There is no executable `check-phase13-grounded` command. The desired command currently fails:

```bash
skills/persona-dream/run.sh check-phase13-grounded \
  --run-root skills/persona-dream/reports/pipeline-complete \
  --revision-id rev_idea_f3f9c48d5cc2 \
  --json
```

Required Phase 13 outputs do not exist:

```text
phase_13_interpretation/dream_self_interpretation.v1.json
phase_13_interpretation/tom_validation_receipt.v1.json
```

### WebGPT code-authoring state

- Exact project tab ID: `837358135`.
- Exact URL:
  `https://chatgpt.com/g/g-p-6a2d6f0882fc8191b3d9c40b349dd193/c/6a50d492-490c-83ea-a034-4760ea336861`
- Browser Oracle project: `persona-dream`.
- The duplicate stale binding named `dream` was removed; only `persona-dream` should point to this tab.
- Phase 13 code request:
  `review-bundles/phase13_code_bundle.md`
- Immutable gate draft:
  `review-bundles/phase13_code_gate.json`
- Source provenance:
  `review-bundles/phase13_code_bundle.source-provenance.json`
- Submission receipt:
  `review-bundles/phase13_code_bundle-response.receipt.json`
- Heartbeat:
  `review-bundles/phase13_code_bundle-response.meta.heartbeat.json`

The bounded code request was submitted to the exact tab from a clean branch tracking `origin/main`. The receipt says `submitted_to_chatgpt:true`. The 1200-second transport window ended with `phase:"failed"`, `page_state:"stalled"`, no response body, and no patch/ZIP. This is not a code deliverable and earns no progress credit.

The checked-in WebGPT CLI is behind its `SKILL.md`: the documented `--gate` option is not implemented. The bundle still contains the gate fields, but the anti-avoidance engine was not invoked by the CLI.

### Brave research state

- A valid Brave key is configured.
- `skills/brave-search/brave_search.py` hung without results.
- A direct Brave API fallback was bounded to 15 seconds and failed with DNS resolution timeout.
- No external research findings were obtained; do not claim otherwise.

## 5. Next Steps

1. Recover the existing WebGPT turn, without submitting a duplicate:

   ```bash
   python3 skills/webgpt/scripts/webgpt_cli.py listen \
     -p persona-dream --timeout 300 \
     -o skills/persona-dream/review-bundles/phase13_code_bundle-recovered-response.md
   ```

2. Accept the WebGPT result only if it contains a unified diff or non-empty finished-file ZIP and its metadata proves:

   ```text
   requested_tab_id == controlled_tab_id == 837358135
   controlled_tab_id_mismatch == false
   tab_was_created == false
   ```

3. Apply the patch only in a clean worktree based on current `origin/main`. Reconcile it against the real Phase 12 packet and Persona Dream/Memory/Scillm contracts.

4. Run focused wiring tests, explicitly labeled `mocked: yes` when fixtures are used.

5. Run the real Phase 13 writer and the required `check-phase13-grounded` command. Pass requires real observation SHA binding, positive accepted interpretation count, accepted/rejected ToM counts, zero unsupported claims, persona scope `embry`, and unchanged provider ledgers.

6. Commit and push the focused Phase 13 implementation and real artifacts.

7. Only after Phase 13 passes, create the next bounded gate for Phase 14 real Memory `/upsert`, exact reread, and synthetic-origin preservation. Do not combine Phase 14-16 into one WebGPT request.

8. Subsequent gates are Phase 15 semantic plus explicit graph traversal recall, then Phase 16 bounded baseline/post-dream behavior with identity-drift rejection.

## 6. Project Context for Success

### Key source files

- `scripts/write_cognitive_loop_dry_run.py`: current non-executable Phase 13-16 scaffold.
- `tests/test_cognitive_loop_dry_run.py`: fixture-only scaffold tests.
- `scripts/write_dream_observation_packet.py`: Phase 12 live packet writer.
- `scripts/check_dream_observation_packet.py`: Phase 12 independent checker.
- `schemas/dream_observation_packet.v1.schema.json`: Phase 12 schema.
- `run.sh`: command dispatcher.
- `PROJECT_KNOWLEDGE.md`, `README.md`, `SKILL.md`: stale after the successful provider return and Watch pass.

### Relevant commits

- `0854cd9b` on `origin/main`: persists the real provider return, Watch evidence, Phase 12 packet, and provider-return lineage implementation.
- `d249e364`: rejects unsupported multi-prompt `end_image_url` and compiles the corrected request.
- Local equivalent commits in the dirty served checkout are `590f0dd8` and `04aabc4d`; do not push them directly over current main.

### Non-claims

- Phase 13 grounded self-interpretation is not implemented or proven.
- ToM candidates are not accepted or persisted.
- Synthetic dream Memory persistence is not implemented or proven.
- Explicit Arango graph traversal is not proven.
- Later semantic recall and bounded persona/Chatterbox behavior are not proven.
- The founding research hypothesis remains unproven.
