# Phase 07 Prompt Renderer — Diagnosis & Resolution

**Date:** 2026-07-18
**Scope:** storyboard node + prompt renderer + Tau loop path (successor revision
`rev_successor_943b01ecd9a3`). Frozen `rev_upstream_bf3b05d47fb8` untouched.

## 1. What the contract demands

The Phase 07 command-loop preflight
(`scripts/phase07_storyboard_tau_node.py::_run_phase07_live_preflight`) shells out
to `scripts/validate_persona_dream_spine_chain.py`, which validates a
`spine_chain_manifest.v1.json` (`schema persona_dream.spine.chain_contract_manifest.v1`).
The manifest must carry, and every artifact must hash-match:

- **Upstream stages** `phase01` / `phase02` / `phase06`: each a typed contract
  (`memory_residue_contract.v1` / `story_contract_prompt.v1` /
  `script_prompt_contract.v1`) + a validator receipt with a `PASS_*` status, with
  `contract_sha256` recorded and re-hashed.
- **`phase07.panel_prompt_contracts`**: exactly **8** entries, each with
  - a `panel_prompt_contract.v2` file (`contract_path` + `contract_sha256`), which
    must itself validate (`validate_phase07`) and must **not** embed
    `compiled_prompt`, and must bind `input_contracts.phase06_script_prompt_contract`
    to phase06's path+sha;
  - a prompt-contract validator receipt (`required_validator_status =
    PASS_PROMPT_CONTRACT`);
  - a **`compiled_prompt` proof** (`schema persona_dream.phase07.compiled_prompt_proof.v1`)
    pointing at a compiled-prompt file whose `sha256` is re-hashed, with
    `derived_from_contract_path`/`derived_from_contract_sha256` == the entry's
    contract, `render_mode == "deterministic"`, `renderer.deterministic == true`,
    `renderer.name == "phase07_prompt_renderer"`, and `may_be_hand_edited == false`
    (`validate_persona_dream_spine_chain.py::_check_phase07`, lines ~378-418).
- **`edge_bindings`** phase01→02→06 (path+sha, receipts) and
  **`reviewer_preconditions`** (`persona_dream.spine.reviewer_pass_precondition.v1`);
  when the node runs the reviewer role it additionally requires **non-empty
  `acceptance_claims`** each carrying a `PASS_*` validator receipt and a
  `validated_artifact_sha256` (`phase07_storyboard_tau_node.py` lines 1482-1492).

**Hashes that must match:** manifest↔file for every contract, receipt, and
compiled prompt; the compiled-prompt proof's `derived_from_contract_sha256` ==
the contract sha; edge-binding `from_contract_sha256` == the upstream contract
sha; acceptance-claim `validator_receipt_sha256` == the receipt file.

## 2. Where the renderer was referenced — and whether it ever existed

`phase07_prompt_renderer` appears **only as a string** — the `renderer.name` field
inside manifests (test fixtures under `tests/fixtures/spine_chain/**` and
`tests/fixtures/phase07_live_preflight/**`) and in the WebGPT design notes
(`local/spine_chain_hash_convention_webgpt_*.md`). The **validator never imports,
executes, or re-derives** a renderer: it only checks that the compiled-prompt file
hashes to the recorded sha and that the manifest metadata *asserts*
deterministic/not-hand-edited. Git history confirms no renderer file ever existed:

- `git log --all --diff-filter=A -- "*phase07_prompt_renderer*"` → **empty** (no
  such file was ever added), in both `agent-skills` and `tau`.
- No non-fixture `spine_chain_manifest*.json` or `*script_prompt_contract*` exists
  anywhere under `reports/` — the entire spine-chain apparatus had **never been
  run for real**; it lived only as test fixtures.

## 3. What was hand-authored historically

The one precedent spine chain on the 12TB drive
(`/mnt/storage12tb/persona-dream/phase07_tau_runs/run-20260708T112035Z-sequential-storyboard-current-gate/work/`)
satisfied the gate with **hand-authored stubs**:

- Every `phase07/prompts/*.md` compiled prompt is a **2-line placeholder**:
  `"Persona Dream compiled prompt for sb_00X.<frame>.attempt_001.\nUse typed Phase
  06 fields only."` — identical to the repo's own good fixture
  (`tests/fixtures/spine_chain/good/phase07/prompts/*.md`). Not derived from any
  panel/script content.
- The precedent `panel_prompt_contract.v2` files bind **fictional fixture assets**
  (`embry_reference_sheet_2024`, `phase01/media/*.txt`, `sb003_accepted_frame`),
  not the successor's real `embry_contact_sheet_v3` or the accepted frames.
- The manifest nonetheless asserted `renderer.deterministic = true`,
  `render_mode = "deterministic"`, `may_be_hand_edited = false`,
  `renderer.name = "phase07_prompt_renderer"` — all four **fabricated**: no renderer
  produced the stub, and it *was* hand-edited.

**Answer to "was the renderer ever real?": No.** It was an aspirational name in a
manifest field. The integrity gate had a hole — it bound a file to a claim but
never verified the file was a deterministic function of the contract — so
hand-authored stubs passed while asserting "deterministic / not hand-edited."

## 4. Resolution (implemented)

`scripts/phase07_prompt_renderer.py` makes the claim **true** rather than removing
the guarantee:

- `compile_prompt(contract)` is a **pure, byte-stable function of the on-disk
  panel prompt contract** (typed Phase 06 fields only; no raw source text). The
  compiled prompt is provably `compile_prompt(contract)`.
- The renderer builds the four upstream spine contracts as **typed projections
  hash-bound to the successor's real phase artifacts**, builds the 8
  `panel_prompt_contract.v2` files bound to the **real** `embry_contact_sheet_v3`
  + Kai reference and the **accepted Phase C frames** as temporal-continuity
  references, renders each compiled prompt, runs the real validators, and
  assembles the manifest + edge bindings + reviewer preconditions.
- Reviewer acceptance is **honest**: `reviewer_preconditions.acceptance_claims`
  are bound to the real Phase C actual-pixel identity-review receipts + accepted
  frame bytes (each emits a `PASS_STORYBOARD_FRAME_ACCEPTED` receipt).
- `verify_render(manifest)` re-derives every compiled prompt from its contract and
  fails closed on any byte drift — the "deterministic / not hand-edited" claim is
  now **re-checkable**, closing the hole. A tampered prompt is rejected both by
  `verify_render` and by the spine validator (`BLOCKED_COMPILED_PROMPT_HASH_MISMATCH`).

Unit tests: `tests/test_phase07_prompt_renderer.py` (9 tests) — determinism
(byte-identical across output dirs), compiled-prompt-is-pure-function, hash
binding, `validate_phase07` pass, full spine-gate pass, acceptance-claim binding,
tamper rejection (verify + spine validator + tampered contract). All green.

## 5. Tau loop / max_steps finding

There is **no hard `max_steps=2`** in the Tau command loop. On branch
`issue-74-ready-queue-condition-block` (tau `416edc5a`): the handoff loop default
is 5 (`handoff_dispatch.py:662`), and `persona_dream_panel_proof.py:75` runs it
with `max_steps=4`. The historical stop-at-2 is a **DAG-contract config case** —
a 2-node (creator+reviewer, each `max_attempts=1`) contract with no
`limits.max_total_attempts` derives `_max_steps == 2` (`project_dag.py:4228`) and
stops with `stop_reason=max_steps_exhausted`. Raising `limits.max_total_attempts`
(or node `max_attempts`) reaches the 3rd node. **No tau code change was required.**

Empirically (dry-run, `scillm_live_panel=False`, no paid/image call), the loop
advances **panel-creator → panel-reviewer → persona-dream-panel-repair-gate** (the
panel-specific 3rd node) and halts at `next_agent_is_human` — not a step-2
truncation. See `phase_07_storyboard_live_tau/tau_loop_preflight_proof/tau_command_loop_evidence.v1.json`.

## 6. Proof

`scripts/prove_phase07_tau_loop_preflight.py` renders the chain into the successor
tree and runs the full matrix; receipt:
`phase_07_storyboard_live_tau/tau_loop_preflight_proof/tau_loop_preflight_proof_receipt.v1.json`
(`status: PASS_TAU_LOOP_PREFLIGHT_PROOF`). It proves: deterministic render,
spine-chain gate PASS on genuinely rendered artifacts, node creator+reviewer live
preflight PASS in the local no-provider gate (both full-storyboard and targeted
`require_target_scope=True`). No paid provider call; no image generation; the
accepted Phase C frames are reused.
