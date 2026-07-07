# Handoff Report: persona-dream

**Timestamp**: 2026-07-07T13:42:00Z
**Active Agent**: Codex

## 1. Project Overview

- **Ecosystem**: Python skill runtime plus React/UX Lab wrapper.
- **Core Purpose**: `persona-dream` builds receipt-backed persona dream pipeline artifacts: idea, story, crew, contact sheets, voices, script, storyboard, provider packets, and memory/project-knowledge receipts.
- **Current Active Surface**: `http://localhost:3002/dream#storyboard`, Phase 07 Storyboard.

## 2. Current State (Doc-Code Alignment)

- **Documented Contract**: Storyboard panels must be generated through a Tau creator/reviewer loop, must preserve Embry/Kai identity with contact/reference sheets, and must fail closed when visual identity review fails.
- **Implemented Reality**: The Phase 07 packet and UI currently show `BLOCKED_PANEL_REVIEW`, not a passing storyboard. The pane is correctly blocked, but the visible SB_001 frame in the browser still does not prove Embry identity.
- **Source Repair Applied**: `phase07_storyboard_tau_node.py` now separates generated `candidate_frame` from reviewer-owned `accepted_frame`. The creator path no longer writes `accepted_frame`; the reviewer promotion path is the only source path that writes `accepted_frame`, and accepted frames must include `accepted_by: panel-reviewer`.
- **Drift/Misalignments**:
  - The prompt payload previously treated Embry/Kai as weak `required_entities` rather than hard `required_identities`.
  - A generated frame was able to appear as an `accepted_frame` while nested identity review had `status: FAIL`. Source validation now catches this state and blocks old creator-minted frames with `accepted_*_not_reviewer_accepted`.
  - Local image replacement updated on-disk PNGs, but CDP still showed a stale/wrong SB_001 frame in the live pane, meaning the rendered asset path/cache remains unresolved.

## 3. What is Working Well

- `skills/persona-dream/SKILL.md` now contains the correct fail-closed principles for panel continuity and self-repair.
- `skills/persona-dream/PROJECT_KNOWLEDGE.md` records the Phase 07 identity-gate lesson.
- Project knowledge recall for `persona-dream` was verified after the prior commit:
  - `project: persona-dream`
  - `chunks: 32`
  - `phase07_lesson: True`
  - `identity_first_decision: True`
  - `fail_closed_decision: True`
  - `structured_schema_question: True`
- The latest CDP run successfully loaded the Storyboard pane and produced a screenshot artifact.
- The optimum SB_001 payload fixture validates with `PASS`, while the current live Phase 07 packet fails the hard identity contract:
  - `python3 skills/persona-dream/fixtures/phase07_optimum_payload_sb001/tools/validate_optimum_payload.py skills/persona-dream/fixtures/phase07_optimum_payload_sb001/sb_001.optimum_prompt_payload.v1.json` -> `PASS`
  - `python3 skills/persona-dream/tools/assert_panel_contract.py skills/persona-dream/reports/pipeline-complete/phase_07_storyboard_live_tau/storyboard_packet.json` -> `FAIL: required_identities must include Embry and Kai`

## 4. What is Currently Broken

- **Primary Blocker**: Phase 07 Storyboard is still blocked.
- **Rendered Evidence**:
  - CDP command:
    `~/.codex/hooks/verify-ui-cdp.sh --url http://localhost:3002/dream#storyboard --name persona-dream-storyboard-sb001-provider-image-repair`
  - Screenshot:
    `/tmp/codex-ui-verification/agent-skills/persona-dream-storyboard-sb001-provider-image-repair/20260707T130010Z.png`
  - Visible result: layout renders, blocker cards wrap, but SB_001 still shows the wrong identity frame in the live pane.
- **Local File Evidence**:
  - Repaired provider PNG:
    `skills/persona-dream/reports/pipeline-complete/phase_07_storyboard_live_tau/generated_storyboard_frames/sb_001_start_frame.provider.png`
  - New SHA:
    `0dd1624f46b34462206cf37ec472039760c925c27744e715f531fd014148e77b`
  - Backup of stale provider frame:
    `skills/persona-dream/reports/pipeline-complete/phase_07_storyboard_live_tau/generated_storyboard_frames/sb_001_start_frame.provider.pre_identity_repair_20260707T1257Z.png`
- **Known Issue**: Browser/UI is still rendering a stale or alternate image source despite local provider PNG replacement.
- **Failed Acceptance**: Do not claim Phase 07 pass until the rendered screenshot visibly shows Embry and Kai identity-correct panels and reviewer status is `PASS_PANEL_REVIEWED`.

## 5. Next Steps

1. Trace the live `<img src>` for SB_001 in `DreamWorkspace.tsx`/UX Lab runtime and compare the served bytes to the repaired PNG SHA.
2. Add cache busting or correct source-path selection so the browser renders the intended repaired asset, not a stale provider/cached frame.
3. Fix the Phase 07 acceptance model so `accepted_frame` is written only after panel-reviewer identity continuity PASS.
   - Source patch is applied; the live packet still needs regeneration through the repaired Tau DAG.
4. Regenerate Phase 07 through Tau using hard `required_identities`, attached Embry/Kai identity references, and no fallback image provider.
5. Re-run CDP and visually inspect the screenshot. Acceptance requires the screenshot to show Embry and Kai as the correct characters, not just a blocked status page.

## 6. Project Context for Success

- **Key Files**:
  - `skills/persona-dream/scripts/phase07_storyboard_tau_node.py`
  - `skills/persona-dream/reports/pipeline-complete/phase_07_storyboard_live_tau/storyboard_packet.json`
  - `skills/persona-dream/reports/pipeline-complete/phase_07_storyboard_live_tau/phase_07_storyboard_packet_tau_dag_contract.json`
  - `skills/persona-dream/reports/pipeline-complete/phase_07_storyboard_live_tau/receipts/storyboard_review_verdict.json`
  - `skills/persona-dream/reports/pipeline-complete/phase_07_storyboard_live_tau/generated_storyboard_frames/`
  - `skills/persona-dream/PROJECT_KNOWLEDGE.md`
- **Relevant UI Files**:
  - `/home/graham/workspace/experiments/agent-skills/skills/persona-dream/ui/src/DreamWorkspace.tsx`
  - `/home/graham/workspace/experiments/pi-mono/packages/ux-lab/server/index.ts`
- **Do Not Claim**:
  - storyboard pass
  - provider readiness
  - identity continuity fixed in UI
  - Tau loop success
  until a fresh CDP screenshot and storyboard review receipt prove it.
