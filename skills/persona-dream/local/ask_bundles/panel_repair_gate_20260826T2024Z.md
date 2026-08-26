# Persona Dream Panel Repair Gate Ask Bundle

## Immutable Goal

Every `$persona-dream` pipeline step must pass, including day ingest, dream packet, post-dream journal, spoken journal, memory carry, artifact storage, storyboard/Kling boundary, and an audible first-person live dynamic Chatterbox conversation where Horus and Embry discuss Embry's dream, mood, and feelings. The scientific point is to assess whether dream and journal state can influence emotional dynamics in conversation without changing the factual answer.

## Current Run Root

`/mnt/storage12tb/skills/persona-dream/outputs/manual-full-cycle-20260826T194135Z`

## Proven Local State

- Day ingest passed for `2026-08-26`: `PASS_DAY_INGESTED`, `events=8`, `read_back=8`.
- `run-dream-cycle` spine passed in `/mnt/storage12tb/skills/persona-dream/outputs/manual-full-cycle-20260826T194135Z-spine`: `dag_run/run-receipt.json` status `PASS`, `node_count=3`, `completed_node_count=3`.
- Journal rendered and spoken through retained commands; journal audio receipt status `PASS_JOURNAL_SPOKEN`, `mocked=false`, `live=true`, `asr_ok=true`.
- Memory write passed: `memory_write_status=ok`.
- Dream artifacts stored: `PASS_DREAM_ARTIFACTS_STORED`, modalities `audio,image`, `read_back=2`.
- Dynamic Horus/Embry conversation passed: `PASS_DYNAMIC_CONVERSATION`, `pairs=3`, `conversation.jsonl` has `embry=3`, `horus=3`, six audio files exist, Tau text calls are live `gpt-5.5` HTTP 200.
- Conversation was carried to memory: `PASS_CONVERSATION_CARRIED`, `carried=6`, `read_back=6`.

## Retained Repairs Already Added

- `fulfill-story-contract-work-order` was added after a prior `$ask gpt-5.5-high` review. It consumes `story_contract_work_order.json`, emits accepted `story_contract.json`, and validates with `validate-story-contract`.
- `fulfill-storyboard-panel-work-order` was added with `$agentic-evals` coverage. It consumes `storyboard_panel_work_order.json`, emits `storyboard_panel_receipt.json`, and validates with `validate-storyboard-panel`.

## Current Pipeline Stop

Command:

```bash
bash skills/persona-dream/run.sh pipeline-loop-run \
  /mnt/storage12tb/skills/persona-dream/outputs/manual-full-cycle-20260826T194135Z \
  --direction forward \
  --output /mnt/storage12tb/skills/persona-dream/outputs/manual-full-cycle-20260826T194135Z/receipts/pipeline_loop_run_after_storyboard_panel.json \
  --json
```

Result:

- `status=BLOCKED`
- `stop_reason=work_order_written`
- `active_loop.phase=panel_repair_gate`
- `active_loop.path=receipts/panel_repair_gate_receipt.json | panel_repair_gate_receipt.json`
- `active_loop.validator=validate-panel-repair-gate --require-provider-eligible`
- wrote `/mnt/storage12tb/skills/persona-dream/outputs/manual-full-cycle-20260826T194135Z/receipts/panel_repair_work_order.json`

The work order requires:

- Read `storyboard_panel_receipt.json`, continuity ledger, panel work order, `SKILL.md`, and project knowledge.
- Create a real panel image through the approved Scillm/GPT image lane.
- Do not use Nano Banana or Gemini final imagery.
- Run independent read-only visual review through `panel-reviewer`.
- Write `requirement_matrix`, `generation_receipt`, script coverage receipts, visual review receipt, no-overlay receipt, provider-media readiness fields.
- Emit `request.json`, `response.json`, `panel_repair_gate_receipt.json`, and `status_transition_log.jsonl`.

Acceptance criteria:

- `panel_repair_gate_receipt.status == PASS_PANEL_REVIEWED`
- all panel repair subgates are `PASS`
- `provider_eligibility == true`
- `provider_packet_status == PROVIDER_READY`
- `remaining_blockers` is empty
- no Nano Banana/Gemini final panel generation
- no live/paid provider call unless explicitly authorized

## Existing Code Context

- `skills/persona-dream/scripts/validate_panel_repair_gate.py` enforces the final receipt.
- `skills/persona-dream/scripts/write_panel_repair_work_order.py` writes the handoff work order only.
- `skills/persona-dream/scripts/validate_panel_repair_work_order.py` validates the work order only.
- `skills/persona-dream/pipeline/s05_panels/create_panel.py` can generate a panel using `--backend scillm`, routed through `skills/create-image/run.sh`.
- `skills/persona-dream/scripts/panel_review_check.py` routes single-image review through the sanctioned Tau VLM adapter.
- `skills/persona-dream/scripts/repair_panels_and_write_verdicts.py` is unusable because it hardcodes an old run root and uses forbidden `nano-banana`.
- `skills/persona-dream/scripts/repair_panels_and_write_verdicts_scillm.py` is also old/hardcoded and writes prose PASS verdicts, not the required panel repair gate receipt.

## Question For GPT-5.5 High

Given the no-bespoke constraint and current retained command surface, what is the smallest legitimate next implementation path?

Specifically answer:

1. Should the project add a retained `fulfill-panel-repair-work-order` command that wraps existing `create_panel.py --backend scillm`, Tau VLM review, and `validate-panel-repair-gate`, with `$agentic-evals` coverage?
2. If yes, what exact output artifacts and fields must it write to satisfy `validate-panel-repair-gate --require-provider-eligible` without falsely claiming provider/Kling submission?
3. Is local/public provider media eligibility possible without explicit public upload authorization, or must this gate remain blocked until a public media publication/preflight command runs?
4. What should the next deterministic command sequence be after this work order?

Return a focused implementation recommendation. Do not expand the immutable goal or replace it with dashboard/report work.
