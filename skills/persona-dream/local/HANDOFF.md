# Handoff Report: Persona Dream Phase 07 Storyboard

**Timestamp**: 2026-07-07T19:55:00Z
**Active Agent**: Codex

## 1. Project Overview

- **Ecosystem**: Python skill scripts plus Tau DAG command-spec dispatch.
- **Core Purpose**: Persona Dream builds a multi-pane creative pipeline. Phase 07 turns prior idea/story/script/contact-sheet/voice/crew artifacts into storyboard panels for Kling planning.

## 2. Current State

- Tau auth/model-routing is no longer the active blocker for this slice.
- Persona Dream now has a targeted `sb_001` optimum contract path that separates creator candidate frames from reviewer-owned accepted frames.
- The targeted `sb_001` reviewer proof passed live through Tau after correcting Persona Dream's reviewer model-policy gate.

## 3. Working Evidence

- Fixture payload validator:
  `python3 skills/persona-dream/fixtures/phase07_optimum_payload_sb001/tools/validate_optimum_payload.py skills/persona-dream/fixtures/phase07_optimum_payload_sb001/sb_001.optimum_prompt_payload.v1.json`
  Result: `PASS`
- Contract invariant validator:
  `python3 /home/graham/Downloads/assert_panel_contract.py skills/persona-dream/fixtures/phase07_optimum_payload_sb001/sb_001.optimum_prompt_payload.v1.json`
  Result: `PASS: panel contract invariants hold`
- Targeted unit proof:
  `pytest -q skills/persona-dream/tests/test_phase07_storyboard_tau_node.py`
  Result: `11 passed`
- Live Tau targeted reviewer proof:
  `/mnt/storage12tb/persona-dream/phase07_tau_runs/run-20260707T194050Z-sb001-targeted-gate/run/dag-receipt.json`
  Result: `status=PASS`, `mocked=false`, `live=true`, edge `panel-reviewer -> human`.
- Reviewer verdict:
  `/mnt/storage12tb/persona-dream/phase07_tau_runs/run-20260707T194050Z-sb001-targeted-gate/work/receipts/storyboard_review_verdict.json`
  Result: `PASS_PANEL_REVIEWED`, `accepted=true`, `blockers=[]`.
- Generated frames:
  `/mnt/storage12tb/persona-dream/phase07_tau_runs/run-20260707T192042Z-sb001-optimum-contract/work/generated_storyboard_frames/sb_001_start_frame.png`
  `/mnt/storage12tb/persona-dream/phase07_tau_runs/run-20260707T192042Z-sb001-optimum-contract/work/generated_storyboard_frames/sb_001_end_frame.png`

## 4. What Changed

- `skills/persona-dream/scripts/phase07_storyboard_tau_node.py`
  - Allows targeted `generation_scope.target_panel_ids` proof packets without applying full-storyboard panel-count and unrelated seed gates.
  - Keeps full storyboard packets fail-closed on panel count and seed coverage.
  - Writes panel-level `required_identities` from `required_entities`.
  - Requires existing identity review receipts to match the current reviewer policy before reuse.
  - Allows `panel-reviewer` to use `gpt-5.5` while keeping `panel-creator` on `gpt-2`.
- `skills/persona-dream/fixtures/phase07_optimum_payload_sb001/sb_001.optimum_prompt_payload.v1.json`
  - Identity review policy is `gpt-5.5`.
  - Identity references require pane, generator, and reviewer visibility.
  - Terminal truth rule forbids creator-owned `accepted_frame`.
- `skills/persona-dream/tests/test_phase07_storyboard_tau_node.py`
  - Covers reviewer `gpt-5.5` policy.
  - Covers stale identity review receipt rejection.
  - Covers targeted proof packet gating.
  - Covers panel-level required identity injection.

## 5. What Is Still Not Complete

- The full four-panel Phase 07 storyboard has not been regenerated and accepted through the creator/reviewer loop after this patch.
- The UI at `http://localhost:3002/dream#storyboard` may still show stale report artifacts unless refreshed from the accepted 12TB run.
- The targeted reviewer pass reused generated `sb_001` frames from the prior live creator run; it did not rerun the creator after the last panel-level `required_identities` patch.
- `provider_live` in the Tau DAG receipt is false because the reviewer-only rerun did not call the image provider; the earlier creator run contains the live image generation receipts.

## 6. Next Steps

1. Commit only the relevant Persona Dream code, fixture, validator, tests, and this handoff file.
2. Rebuild or sync the storyboard UI/report from the accepted targeted `sb_001` packet if the UI needs to display this proof.
3. Generalize the targeted flow to sequential panels:
   - `sb_001` accepted end frame becomes temporal continuity reference for `sb_002`.
   - Each panel must keep Embry/Kai character sheets as hard identity truth.
   - Only reviewer-accepted frames can feed the next panel.
4. Run full four-panel Phase 07 through Tau only after the targeted `sb_001` proof is accepted as the base rung.
