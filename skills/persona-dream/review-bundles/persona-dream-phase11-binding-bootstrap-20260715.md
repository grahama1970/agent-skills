# Persona Dream Phase 11 Current-Revision Binding Bootstrap

## Immutable objective

Persist and deterministically verify every Persona Dream stage before the first
Kling/fal generation call. Do not submit, authorize, or simulate a provider
generation. The next artifact must remove real Phase 11 technical blockers for
active revision `rev_idea_f3f9c48d5cc2`, or return one exact blocker.

## Source authority

- Repository: `grahama1970/agent-skills`
- Branch: `main`
- Commit: `9ce346f4`
- Skill root: `skills/persona-dream`
- Run: `pipeline-complete`
- Active revision: `rev_idea_f3f9c48d5cc2`
- Rejected semantic-mix revision: `rev_repair_a8b93ffeca8f`

Read the current files from GitHub at commit `9ce346f4`; do not infer their
contents from older conversation context.

## Live evidence already established

- Phases 01-10: `ACTIVE_CONSISTENT`, 10/10 accepted stages.
- Explicit human idea: `pd_idea_45a9d20d629b4e08863a9618b5f83982`.
- Memory Phase 11 key:
  `pd_phase11_d1440cf980f38c916f0fa93bff648b17e036e58feb43a941`.
- Memory exact reread: 1 document, `semantic_sync_state=synced`.
- Qdrant point: `d7cfc55d-e97d-5ba7-a0d9-ff1fc4cf2650`.
- Question-shaped dense recall: score `0.7934561`.
- Phase 11 gate: `BLOCKED_PROVIDER_GATE`.
- Actual provider generation attempts: 0.
- Paid authorization: false.
- Provider ready / live submit ready: false / false.

Committed current Phase 11 artifacts are under:

`skills/persona-dream/reports/pipeline-complete/.persona-dream/revisions/rev_idea_f3f9c48d5cc2/phase_11_submit_return/canonical/`

## Exact failing command

```bash
./run.sh capture-phase11-provider-source-snapshot \
  --run-root /home/graham/workspace/experiments/agent-skills-main/skills/persona-dream/reports/pipeline-complete \
  --revision-id rev_idea_f3f9c48d5cc2 \
  --json
```

Observed failure:

```text
FileNotFoundError: .../rev_idea_f3f9c48d5cc2/phase_11_submit_return/preflight/phase11_payload_binding.json
prepare_revision_qualification.GateBlocked: BLOCKED_REVISION_JSON_INVALID
```

The exception is not converted into a canonical Phase 11 blocked receipt.

## Root cause established from repository evidence

`capture_phase11_provider_source_snapshot.py` reads the candidate binding before
capturing official provider evidence. The active revision has no candidate
binding. Only the rejected semantic-mix revision contains one:

`.../rev_repair_a8b93ffeca8f/phase_11_submit_return/preflight/phase11_payload_binding.json`

That old binding is not reusable as authority. It is bound to the rejected
revision, commit-pinned old URLs, `Kling v3 Pro` wording while selecting the
Standard endpoint, and SB_003 spoken dialogue while `generate_audio=false`.

The canonical compiler currently tolerates the missing binding by producing a
blocked request with null provider fields, zero character packs, missing
start/end media, and these main blockers:

```text
BLOCKED_CHARACTER_ELEMENT_PACK_COUNT:0:expected:2
BLOCKED_MEDIA_ROLE_COUNTS
BLOCKED_PROVIDER_END_IMAGE_URL_MISSING
BLOCKED_PROVIDER_MEDIA_URL_INVALID
BLOCKED_PROVIDER_REQUEST_NULL_FIELD
BLOCKED_PROVIDER_SOURCE_SNAPSHOT_MISSING
BLOCKED_PROVIDER_START_IMAGE_URL_MISSING
BLOCKED_UPSTREAM_VALIDATION_MIGRATION_RECEIPT_IDENTITY
```

## Current relevant files

- `skills/persona-dream/scripts/capture_phase11_provider_source_snapshot.py`
- `skills/persona-dream/scripts/phase11_canonical_common.py`
- `skills/persona-dream/scripts/compile_phase11_canonical_live_request.py`
- `skills/persona-dream/scripts/reconcile_phase11_upstream_validation.py`
- `skills/persona-dream/scripts/capture_phase11_public_media_evidence.py`
- `skills/persona-dream/run.sh`
- `skills/persona-dream/contracts/phase11_live_request.v1.schema.json`
- `skills/persona-dream/contracts/phase11_media_binding_manifest.v2.schema.json`
- `skills/persona-dream/contracts/phase11_provider_source_snapshot.v1.schema.json`
- `skills/persona-dream/tests/test_phase11_canonical_live_request.py`
- `skills/persona-dream/tests/test_phase11_technical_evidence.py`

## External research performed by project agent

Brave Search returned the official current fal pages:

- https://fal.ai/models/fal-ai/kling-video/v3/standard/image-to-video/api
- https://fal.ai/models/fal-ai/kling-video/v3/standard/image-to-video

The API result describes Standard image-to-video, customizable multi-shot
generation, `start_image_url`, custom elements/reference images, and CFG scale.
WebGPT must independently verify current provider fields from official fal
sources, but the patch must remain zero-call.

## Required code result

Return a bounded unified diff, not a roadmap. The patch must:

1. Add a deterministic command or compiler step that creates the active
   revision's `phase11_payload_binding.json` exclusively from the active
   revision, Phase 10 payload, immutable artifact index, and explicit current
   publication evidence. It must never copy authority from
   `rev_repair_a8b93ffeca8f`.
2. Bind exactly one global start anchor, one global end anchor, six
   continuity-only storyboard frames, and exactly two character element packs
   (Embry and Kai), with exact artifact IDs and hashes.
3. Produce a Standard-endpoint request with no `Pro` wording, no null request
   fields, durations consistent with the declared time ranges, and a genuinely
   silent SB_003 when `generate_audio=false`.
4. Keep provenance/publication evidence explicit. Do not invent successful
   probes or claim provider-side fetches. If current public evidence is absent,
   emit a precise blocked receipt and the deterministic next command.
5. Make `capture-phase11-provider-source-snapshot` fail closed with a canonical
   `BLOCKED_*` JSON receipt when the binding is absent/invalid; no traceback.
6. Preserve `actual_provider_call_attempts=0`, `submitted=false`,
   `paid_call_authorized=false`, `provider_ready=false`, and
   `live_submit_ready=false` throughout this patch.
7. Add focused tests for missing binding, active-revision mismatch, old-revision
   URL rejection, Standard/Pro mismatch, silent SB_003, exact 1+1+6 media roles,
   and two element packs.
8. Name exact commands that should pass after applying the diff. The final
   technical gate may remain blocked only on real publication/source/adapter
   evidence not created by this patch.

Do not modify Memory service internals, UI, Watch, Phases 12-16, approval
receipts, or execute fal/Kling.
