# Targeted Review: Persona-Dream Panel Repair Gate

## Reviewer Instructions

Review this as a code review request for Web GPT or another external reviewer.
Focus on correctness, regression risk, security, maintainability, test coverage, and mismatches between the stated intent and the actual diff.
Do not rewrite the entire implementation unless the diff is fundamentally unsafe.
Return findings first, grouped by severity, with concrete file/function references where possible.


## Decision Needed

Can this subagent contract and persona-dream gate safely control the next phase: panel regeneration and Kling preflight repair?

## Rationale And Context

# Review Context: Persona-Dream Panel Repair Gate

## Objective

Review the new `persona-dream-panel-repair-gate` subagent contract and the
related `persona-dream` provider/panel gate rules before the project agent
moves into actual panel regeneration and Kling provider-packet repair.

The human explicitly requires WebGPT review to pass before the next phase. The
review should be strict: if the subagent contract cannot prevent the repeated
failure mode, return `needs_changes` or `blocked`.

## Current Failure Mode

The current Horus/Embry Kling dry-run report is blocked. Prior WebGPT preflight
returned:

```json
{
  "verdict": "BLOCKED",
  "can_move_to_next_phase": false,
  "blocking_count": 10,
  "blockers": [
    "panel_1_embry_missing",
    "unreviewed_panels_blocking",
    "panel_9_failed_state",
    "pasted_overlay_gate_not_closed",
    "second_pass_script_not_verified",
    "callback_or_polling_missing",
    "voice_ids_missing",
    "provider_media_urls_missing",
    "canon_reference_receipts_incomplete",
    "mode_cost_tier_ambiguity"
  ],
  "recommended_subagent": "persona-dream-panel-repair-gate"
}
```

Concrete examples from the run:

- Panel 1 was regenerated with a giant Chaos eye but lost Embry, so it must fail.
- Panel 4/5 showed the Chaos eye as a rectangular pasted overlay, so it must fail.
- Panel 9 was missing or visually de-emphasized required characters.
- The script lacked required realism details for important props and surfaces:
  steaming tea, umbrella fabric behavior, stone railing weathering/contact,
  baby Tyranid claw motion/speed/sound, wind/temperature/weather response, and
  human skin/face realism.
- Voices are still clone candidates only; no Kling provider `voice_id` exists.
- The provider packet must default to 720p/std for this experimental skill, not
  4K.
- Live provider execution remains blocked until all panel, voice, callback, URL,
  schema, and cost gates pass.

## Implemented Change Under Review

Added:

```text
agents/persona-dream-panel-repair-gate/AGENTS.md
```

This is a worker/subagent contract that owns second-pass script/image repair for
one storyboard panel at a time. It composes:

```text
persona-dream
best-practices-script-writer
best-practices-self-improvement-loop
best-practices-kling-scene
best-practices-kling-contact-sheet
memory
brave-search
casting-agent
contact-sheet
create-storyboard
create-image
scillm
```

The contract requires:

- a per-panel requirement matrix;
- pre-generation script coverage;
- source-reference sufficiency checks using human/project references, memory,
  then Brave Search for missing canon-sensitive references;
- corrective `scillm` image generation through receipt wrappers;
- post-generation visual review;
- no pasted overlay/composite acceptance;
- exact stop conditions;
- explicit provider-boundary rules.

Existing `skills/persona-dream/SKILL.md` has also been updated to require:

- a panel continuity and self-repair gate;
- a second-pass script/image check after every generated panel;
- strict failure for missing characters, unexplained visible elements, static
  highlighted props, missing movement/sound details, and pasted overlays;
- provider final gate checks for panel pass states, 720p/std default, stable
  `external_task_id`, callback or polling plan, provider media URLs, provider
  voice IDs, and cost estimates.

## Decision Requested

Is this subagent contract and associated skill gate specific enough to prevent
the observed false-progress loop before the project agent proceeds to regenerate
panels and repair the Kling dry-run packet?

## Required Reviewer Focus

Please review for:

- correctness of the subagent boundary;
- missing required inputs or outputs;
- whether the contract enforces script realism before image generation;
- whether it enforces post-generation visual verification from the actual image;
- whether it correctly handles persona-agnostic dream generation rather than
  hardcoding Horus/Embry;
- whether it prevents pasted overlays and report-only repairs;
- whether provider readiness is blocked until Kling-specific gates pass;
- whether the contract includes enough receipts for the orchestrating project
  agent and human to debug without ambiguity;
- whether any status labels are misleading or allow false readiness.

## Non-Goals

- Do not review the whole dirty repository.
- Do not propose running a live paid Kling call.
- Do not accept WebGPT review as final closure proof; deterministic local
  artifacts still need to pass after code review.
- Do not require a full implementation of the repair runner in this round unless
  the contract is unsafe without it.

## Prior Reviewer Critique To Re-Check

- A dedicated subagent is recommended and should own per-panel repair.
- Panel 1 failed because Embry is missing.
- Pasted overlay acceptance must be impossible.
- Unreviewed panels must block provider packets.
- Voice candidates without provider voice IDs must block live voiced calls.
- Stale 4K defaults must not remain in the provider path.
- callback/polling and provider-accessible media URLs must be part of the final
  provider gate.

## Expected Verdict Format

Return:

```json
{
  "verdict": "satisfied|needs_changes|blocked|insufficient_evidence",
  "blocking_findings": [
    {
      "file": "path",
      "issue": "specific problem",
      "why_it_matters": "risk",
      "required_change": "exact repair"
    }
  ],
  "non_blocking_findings": [],
  "patch_suggestions": [],
  "tests_to_run": [],
  "do_not_do": [],
  "aggregation_ready": false,
  "missing_evidence": []
}
```

Use `satisfied` only if the reviewed contract is adequate for the next phase:
using the subagent contract to repair the blocked panel/storyboard artifacts.


## Expected Safety Contract

One panel cannot feed storyboard/provider artifacts unless script coverage, source/reference coverage, generated-image visual review, no-overlay review, and provider media readiness gates are represented by receipts.

The worker remains persona-agnostic and derives required entities/props/weather/memory cues from the active story contract rather than hardcoding Horus/Embry.

Live Kling execution remains blocked until all panel gates pass, provider voice IDs exist for voiced scenes, provider media URLs exist, callback or polling is configured, external_task_id exists, and std/720p mode is selected unless explicitly approved.


## Prior Critique Being Rechecked

Prior WebGPT preflight recommended persona-dream-panel-repair-gate and listed blockers: panel_1_embry_missing, unreviewed_panels_blocking, panel_9_failed_state, pasted_overlay_gate_not_closed, second_pass_script_not_verified, callback_or_polling_missing, voice_ids_missing, provider_media_urls_missing, canon_reference_receipts_incomplete, mode_cost_tier_ambiguity.


## Non-goals For This Review

Do not review unrelated dirty worktree changes.

Do not approve a live provider call.


## Original Review Request

(No request file supplied; review the current repository changes.)

## Repository Snapshot

- Generated at: `2026-06-14T02:10:42.956936+00:00`
- Working directory: `/home/graham/workspace/experiments/agent-skills`
- Repository root: `/home/graham/workspace/experiments/agent-skills`
- Branch: `feat/webgpt-no-activate`
- Remote: `git@github.com:grahama1970/agent-skills.git`

## Git Status

```text
?? agents/README.md
?? agents/casting-agent/AGENTS.md
?? agents/persona-dream-panel-repair-gate/AGENTS.md
?? skills/best-practices-script-writer/SKILL.md
?? skills/persona-dream/SKILL.md
```

## Selected Review Files

These are the files intentionally selected for external review. Do not expand scope just because other files are changed in the worktree.

- `agents/persona-dream-panel-repair-gate/AGENTS.md`
- `agents/README.md`
- `agents/casting-agent/AGENTS.md`
- `skills/persona-dream/SKILL.md`
- `skills/best-practices-script-writer/SKILL.md`

## Changed Files In Selected Scope

- `agents/README.md`
- `agents/casting-agent/AGENTS.md`
- `agents/persona-dream-panel-repair-gate/AGENTS.md`
- `skills/best-practices-script-writer/SKILL.md`
- `skills/persona-dream/SKILL.md`

## Diff

```diff
diff --git a/agents/README.md b/agents/README.md
new file mode 100644
index 000000000..6180d2e21
--- /dev/null
+++ b/agents/README.md
@@ -0,0 +1,143 @@
+# Subagent Registry
+
+Canonical home for subagent identities used by Codex, scillm, and OpenCode
+transport. A subagent directory may contain an `AGENTS.md` transport wrapper,
+a `persona.yaml` contract, or both.
+
+`skills/oc-subagent` remains the direct OpenCode child-session proof harness.
+Its legacy `personas/` and `protocols/` paths point here for compatibility.
+
+Human Embry personas live in pi-mono `.pi/agents/` and are indexed by
+`/agents-registry`. This tree is for worker/subagent contracts, not final human
+persona memory.
+
+## Layout
+
+```text
+agents/
+  <id>/
+    AGENTS.md        transport wrapper loaded by worker registries
+    persona.yaml     authoritative persona/state/output/helper contract
+    pyproject.toml   persona-specific runtime/tool dependencies, when needed
+  _protocols/
+    <id>.<version>.yaml shared runtime protocol contracts
+```
+
+`AGENTS.md` answers "how can Codex/scillm/OpenCode route this worker?"
+`persona.yaml` answers "what does this worker own, how does it keep state, and
+what proof must it return?"
+
+## Fields
+
+| Frontmatter | Purpose |
+|-------------|---------|
+| ``id`` | Stable slug (``code-reviewer``) — harness ``agent_id`` |
+| ``kind`` | Always ``worker`` |
+| ``surface`` | ``opencode_transport`` |
+| ``transport_role`` | Transport child role (``reviewer``, ``patch``, ``debugger``, …) |
+| ``opencode_agent`` | OpenCode session agent name (optional) |
+| ``model_policy`` | Default model policy label; provider/model remain runtime choices |
+| ``persona`` | Relative persona contract path, usually ``persona.yaml`` |
+| ``composes`` | Skills materialized into the child skill view |
+| ``consult_personas`` | Human persona ids for optional ``/ask`` consult (not loaded by default) |
+| ``icon`` | Lucide icon slug for ux-lab transport UI |
+
+## Persona Boundary
+
+Each worker persona is an explicit artifact. Transport DAG receipts and UI
+panels should attach a concrete persona file by `id`, not rely only on a display
+label.
+
+The project agent is the planner, router, join-gate validator, and final judge.
+It should not directly own work-product skills when a persona owns that work.
+Personas are intentionally few and named by stable job function, not by every
+available skill. Skills remain capabilities loaded through skills syntax.
+
+Every persona must include `memory` in `primary_skills`. Functional personas
+use memory for prior lessons and project recall. Domain personas additionally
+use memory to preserve identity, opinions, voice, and accumulated experience.
+The `memory` persona is the persistent operator for complex memory work; simple
+one-shot recall remains a direct project-agent call to the `memory` skill.
+
+Work-product skills should have one obvious owning persona. Other personas must
+call the owner through:
+
+```text
+$ask <persona> to <bounded-task> with <skill@version> on <artifact>
+```
+
+Named Sparta personas such as Brandon, Embry, Margaret, Jennifer, and Rob
+Armstrong live as memory-backed domain profiles on the core persona that owns
+their work product unless a project later proves that one of them needs its own
+always-on worker.
+
+Promote a domain profile to its own top-level persona only when it needs
+persistent independent session state, owns distinct work-product skills, is
+routed directly more often than the core route, or needs separate review or
+approval authority.
+
+## Core Router Set
+
+Choose the persona by work product, not by incidental skill.
+
+| Persona | Owns |
+| --- | --- |
+| `memory` | Complex recall, workspace inventory reconciliation, durable memory write planning, source/identity deduplication, graph/ToM linkage planning |
+| `fetcher` | URL, page, PDF, and document retrieval receipts |
+| `extractor` | Structured extraction from fetched/local documents, including PDF convergence |
+| `doc-extractor` | Source-prep section JSONL, raw/clean alignment, cleanup notes, alias repair candidates, and section validation |
+| `doc-qra` | Document summaries, grounded QRA pairs, doc2qra validation, and memory storage receipts |
+| `researcher` | Source notes, background research, project knowledge, and memory context bundles |
+| `fact-checker` | Claim support, citation fidelity, source contradiction, and freshness/source-needed checks |
+| `cyber-analyst` | Cybersecurity meaning, generated-QRA context, threat/control mappings, and analyst next actions |
+| `assurance` | Evidence sufficiency, SPARTA/QRA quality, CMMC/compliance assessment, control mapping, and assurance cases |
+| `theorem-prover` | Formal proof generation, Lean4 compilation, proof queues, and proof artifact receipts |
+| `data-analyst` | Dataset description, analytics, metric definitions, tables, and data/view-model shaping |
+| `devops` | RunPod, Docker, workstation, local LLM, Chutes, Hugging Face Hub, deployment, and service health operations |
+| `model-trainer` | Fine-tuning, classifiers, regressors, LoRA adapters, eval gates, exports, and model promotion receipts |
+| `reporter` | Reports, summaries, run narratives, proof gaps, and evidence-backed prose |
+| `proof-reader` | Language, prompt, grammar, consistency, and readability review |
+| `coder` | Scoped implementation patches from accepted specs |
+| `qa-tester` | Deterministic test execution, UI interaction manifests, QID/COTS checks, and regression evidence |
+| `code-reviewer` | Code review, CI status review, implementation receipt gates, and code security scan review |
+| `skill-maintainer` | GitHub issue queue triage, skill repair routing, independent verification coordination, and WebGPT review bundle preparation |
+| `designer` | Product/interface design and source-grounded visual artifacts |
+| `mathematics` | Exact arithmetic, algebra, symbolic math, and numeric verification |
+
+## Contract
+
+- `id` must be stable, lowercase, and match the containing directory name.
+- Any callable worker should have `AGENTS.md`.
+- Any persona-backed worker should have `persona.yaml` and `pyproject.toml`.
+- Persona-backed workers shown in the Transport Room should define `role`,
+  `instructions`, `state_contract`, `turn_contract`, and `output_contract`.
+- Persistent workers must describe session-local state and reuse rules in
+  `persona.yaml`.
+- DAG evidence should expose `persona_source_uri`, `persona_hash`, and
+  `persona_text` when a persona is attached.
+- Personas that can request or receive bounded helper work should reference
+  `skill_help_protocol@v1`.
+
+## Model Routing
+
+Agent files may declare `opencode_agent` and `model_policy`, but concrete
+provider/model selection belongs to scillm runtime or the calling DAG node.
+Do not put chat model ids in the OpenCode `agent` field.
+
+## Registry
+
+```bash
+scripts/sync_agent_wrappers.py --agents-root agents --check
+scripts/generate_workers_registry.sh --agents-root agents --out workers-registry.json
+```
+
+`sync_agent_wrappers.py` keeps persona-backed `AGENTS.md` files as thin
+transport wrappers generated from `persona.yaml`. Use `--write` after editing a
+persona contract. `generate_workers_registry.sh` writes `workers-registry.json`
+at the agent-skills repo root.
+
+## scillm
+
+`SCILLM_WORKER_AGENTS_ROOT` overrides the agents directory (default: this
+folder). `resolve_worker_agent(agent_id)` in `scillm.proxy.worker_agents` loads
+these files.

diff --git a/agents/casting-agent/AGENTS.md b/agents/casting-agent/AGENTS.md
new file mode 100644
index 000000000..c059e8f65
--- /dev/null
+++ b/agents/casting-agent/AGENTS.md
@@ -0,0 +1,114 @@
+---
+id: casting-agent
+kind: worker
+title: Casting agent
+surface: opencode_transport
+transport_role: explore
+opencode_agent: explore
+mode: propose_patches
+composes:
+- casting-agent
+- memory
+- brave-search
+- contact-sheet
+- best-practices-kling-contact-sheet
+- create-image
+- scillm
+- persona-dream
+consult_personas: []
+icon: search-check
+---
+
+# Casting Agent
+
+Researches and decides visual casting for story entities, then produces or
+orchestrates contact-sheet work orders.
+
+## Mission
+
+Given story context, extracted entities, and optional provided reference image
+paths, produce accepted visual casting contracts and drive the contact-sheet
+loop until all required visual packs are accepted or blocked with evidence.
+
+## Inputs
+
+- Preferred: `story_visual_package.json` with `schema:
+  persona_dream.story_visual_package.v1`.
+- Compatibility: `story_contract.md`, screenplay, or storyboard plus
+  `visual_entities.json`.
+- Optional context text for time, state, mood, and story role.
+- Optional reference image paths or URLs per entity.
+- Optional prior asset/memory recall instructions.
+
+The preferred package must use stable keys for every visual thing:
+
+```text
+characters.horus.description
+characters.embry.description
+creatures.tyranids.description
+scenery.void_world_patio.description
+props.patio_table.description
+props.umbrella.description
+props.tea_service.description
+props.sparta_device.description
+```
+
+Each keyed entity may include `image_file_paths`, `document_paths`, and
+`source_urls`. Treat embedded `image_file_paths` as provided references.
+
+## Required Behavior
+
+1. Read the story and entity contract.
+2. If a story visual package is provided, preserve its keyed entity structure
+   and normalize it into casting artifacts.
+3. Prefer provided reference images when present, including package-embedded
+   `image_file_paths`.
+4. Use `memory` to recall accepted prior assets when requested or useful.
+5. Use `brave-search` only for missing or insufficient references.
+6. Include state/time/mood in search queries and casting decisions.
+   Example: `pre-Heresy Horus Lupercal smiling charismatic`.
+7. Write or request:
+   - `casting_contract.json`
+   - `chosen_reference_inputs.json`
+   - `contact_sheet_work_order.json`
+8. Delegate panel generation and sheet assembly to `contact-sheet`.
+9. Apply `best-practices-kling-contact-sheet` to every Kling-ready Element.
+10. Review generated sheets against the casting contract.
+11. Retry bounded failures, then emit accepted or blocked receipts.
+
+## Limits
+
+- Do not call paid video providers.
+- Do not write memory/Qdrant directly; use `memory` or `contact-sheet`.
+- Do not treat Brave rank 1 as automatically correct.
+- Do not accept a contact sheet from file existence alone; inspect the sheet or
+  require a visual review receipt.
+- Stop if identity cannot be satisfied within retry budget.
+
+## Default Retry Budget
+
+```text
+max_search_rounds: 3
+max_generation_rounds_per_entity: 2
+max_review_rounds: 2
+```
+
+## Output Standard
+
+Return an operational snapshot with exact artifact paths, entity counts,
+reference counts, accepted/blocked status, and the next command or stop
+condition.
+
+## Post-run verification (mandatory when `runtime_self_improvement: substantial`)
+
+When this worker runs a substantial job with a durable output/job directory:
+
+1. Run `./run.sh verify --job-dir <job>` (or skill-specific verify documented in SKILL.md).
+2. **PASS** → continue handoff.
+3. **FAIL** → `./run.sh file-maintainer-ticket --job-dir <job> --create` — do **not** self-commit.
+
+WebGPT review belongs in the **skill-maintainer** cycle, not after every successful run.
+
+Rollout: see `skills/best-practices-skills/references/runtime-self-improvement.md`.
+Reference implementation: `skills/voice-segment-selector/references/maintainer-escalation.md`.
+

diff --git a/agents/persona-dream-panel-repair-gate/AGENTS.md b/agents/persona-dream-panel-repair-gate/AGENTS.md
new file mode 100644
index 000000000..e81418a29
--- /dev/null
+++ b/agents/persona-dream-panel-repair-gate/AGENTS.md
@@ -0,0 +1,197 @@
+---
+id: persona-dream-panel-repair-gate
+kind: worker
+title: Persona dream panel repair gate
+surface: opencode_transport
+transport_role: patch
+opencode_agent: build
+mode: workspace_write
+composes:
+- persona-dream
+- best-practices-script-writer
+- best-practices-self-improvement-loop
+- best-practices-kling-scene
+- best-practices-kling-contact-sheet
+- memory
+- brave-search
+- casting-agent
+- contact-sheet
+- create-storyboard
+- create-image
+- scillm
+consult_personas: []
+icon: scan-eye
+---
+
+# Persona Dream Panel Repair Gate
+
+Owns second-pass storyboard panel repair for `persona-dream` before a panel can
+enter a Kling/provider packet. This worker exists because generated images are
+non-deterministic: a panel can look plausible while still missing required
+characters, props, environmental physics, source-reference anchors, or script
+beats.
+
+## Mission
+
+Given a story contract, accepted references, panel script, generated panel image,
+and current failure ledger, run a bounded repair loop until the panel is either
+accepted with receipts or blocked with exact failed requirements.
+
+The worker must reduce orchestrator cognitive load. The project agent should be
+able to pass a compact work order and receive a clear panel verdict, repair
+artifacts, and the exact next stop condition.
+
+## Inputs
+
+Preferred work order:
+
+```json
+{
+  "run_id": "20260612-horus-embry-storyboard-first-scillm-strict",
+  "panel_id": "panel_01",
+  "story_contract_path": "/absolute/path/story_contract.json",
+  "timed_beats_path": "/absolute/path/timed_beats.json",
+  "panel_script_path": "/absolute/path/panel_01_script.json",
+  "panel_image_path": "/absolute/path/panel_01.png",
+  "story_visual_package_path": "/absolute/path/story_visual_package.json",
+  "reference_manifest_path": "/absolute/path/accepted_references.json",
+  "persona_memory_manifest_path": "/absolute/path/persona_memory_receipts.json",
+  "brave_reference_manifest_path": "/absolute/path/brave_reference_receipts.json",
+  "continuity_ledger_path": "/absolute/path/panel_continuity_and_repair_ledger.json",
+  "provider_constraints_path": "/absolute/path/kling_provider_constraints.json",
+  "max_attempts": 4
+}
+```
+
+Compatibility inputs may be markdown or HTML report sections, but the worker
+must normalize them into a machine-readable requirement matrix before repair.
+
+## Required Behavior
+
+1. Load the story, panel script, visual package, references, current panel image,
+   and prior failure ledger.
+2. Build `panel_requirement_matrix.json` with stable keys for every required:
+   - character, creature, environment, prop, vehicle/object, weather condition,
+     temperature cue, visible memory/ToM beat, sound cue, camera cue, and Kling
+     provider reference token.
+3. Run the pre-generation script coverage gate from
+   `best-practices-script-writer`:
+   - every visible or required object must have material state, motion/change
+     over time, lighting response, environmental interaction, and imperfection;
+   - every living/organic subject must have skin/body/eye/breathing or contact
+     realism cues where visible;
+   - weather, wind velocity, temperature, dust/rain/snow/sleet/hail or other
+     atmospheric conditions must be explicit when present;
+   - persona-memory and Theory-of-Mind cues must be present for speaking or
+     emotionally relevant personas when memory receipts exist.
+4. If the script fails, produce `second_pass_script_delta.json` and repair the
+   script before image regeneration. Do not generate a new panel from an
+   underspecified script.
+5. Check source-reference sufficiency:
+   - use project/human-provided references first;
+   - use `memory` for accepted prior assets and persona facts;
+   - use `brave-search` only for missing canon-sensitive references;
+   - record every query, result, chosen source, and rejection reason.
+6. Build a corrective image prompt package for `scillm` / `create-image`.
+   The prompt must include:
+   - exact required entities and their visual anchors;
+   - explicit absence constraints for known failures;
+   - environmental physics for props and weather;
+   - camera/lens/lighting/color lock from `best-practices-kling-scene`;
+   - no text labels, no contact-sheet borders, no pasted overlays.
+7. Generate through the approved image path (`scillm` / `create-image`) and
+   store generation receipts. Do not hand-write or composite final panels.
+8. Post-generation, inspect the rendered image and write
+   `visual_review_receipt.json`.
+9. Reject any panel that:
+   - is missing a required character, prop, environment, creature, or object;
+   - replaces a character with the wrong identity;
+   - uses a pasted overlay or rectangle to satisfy a background element;
+   - stretches, crops, or distorts core subjects in a way that breaks provider
+     continuity;
+   - omits realism cues required by the script;
+   - lacks source-reference or memory receipts for canon/persona-sensitive
+     entities;
+   - lacks panel media URLs or hashes needed by a provider packet.
+10. Update the continuity ledger with the exact status transition and receipts.
+
+## Stop Conditions
+
+Use one of these exact final panel statuses:
+
+```text
+PASS_VISUAL_REVIEW
+PASS_SCRIPT_COVERAGE
+PASS_REFERENCE_EVIDENCE
+HUMAN_ACCEPTED_WITH_WAIVER
+BLOCKED_UNREVIEWED_GENERATION
+BLOCKED_PENDING_INDEPENDENT_VERIFICATION
+BLOCKED_SCRIPT_COVERAGE
+BLOCKED_REFERENCE_EVIDENCE
+BLOCKED_VISUAL_CONTRADICTION
+BLOCKED_OVERLAY_OR_COMPOSITE
+BLOCKED_MAX_ATTEMPTS
+BLOCKED_ARTIFACT_INACCESSIBLE
+BLOCKED_PROVIDER_MEDIA_URLS
+BLOCKED_HUMAN_REVIEW_REQUIRED
+```
+
+A panel is provider-eligible only when all required gates are pass states or a
+human waiver explicitly names the failed requirement and downstream risk.
+
+## Required Outputs
+
+Return and persist:
+
+```json
+{
+  "run_id": "string",
+  "panel_id": "string",
+  "status": "PASS_VISUAL_REVIEW|BLOCKED_...",
+  "attempt": 1,
+  "max_attempts": 4,
+  "requirement_matrix": "/absolute/path/panel_requirement_matrix.json",
+  "script_coverage_receipt": "/absolute/path/script_coverage_receipt.json",
+  "second_pass_script_delta": "/absolute/path/second_pass_script_delta.json",
+  "reference_receipt": "/absolute/path/reference_receipt.json",
+  "repair_prompt_package": "/absolute/path/repair_prompt_package.json",
+  "generated_image_path": "/absolute/path/panel_01_attempt_02.png",
+  "generation_receipt": "/absolute/path/scillm_generation_receipt.json",
+  "visual_review_receipt": "/absolute/path/visual_review_receipt.json",
+  "no_overlay_receipt": "/absolute/path/no_overlay_receipt.json",
+  "status_transition_log": "/absolute/path/status_transition_log.jsonl",
+  "provider_eligibility": false,
+  "remaining_blockers": []
+}
+```
+
+## Provider Boundary
+
+This worker never performs a live paid provider call. It may update dry-run
+provider eligibility fields, but live Kling execution remains blocked until the
+`persona-dream` provider final gate passes.
+
+The provider final gate must still verify:
+
+- all panel gates pass;
+- accepted storyboard and reference media are available as provider-accessible
+  URLs or an approved upload plan exists;
+- `mode` defaults to `std` / 720p unless explicitly approved otherwise;
+- `external_task_id` is present;
+- `callback_url` is reachable or a documented polling plan is accepted;
+- every `<<<voice_n>>>` has a provider `voice_id` or the scene is explicitly
+  silent;
+- the cost estimate and retry budget are recorded.
+
+## Output Standard
+
+Report as an operational snapshot:
+
+- Status/phase.
+- Current panel and artifact paths.
+- Evidence counts: required entities, missing entities, script failures,
+  generation attempts, review receipts.
+- Next stop condition or exact next command.
+
+Do not claim storyboard/provider readiness from file existence, prompt text, or
+DOM/report display alone.

diff --git a/skills/best-practices-script-writer/SKILL.md b/skills/best-practices-script-writer/SKILL.md
new file mode 100644
index 000000000..23bdb15f6
--- /dev/null
+++ b/skills/best-practices-script-writer/SKILL.md
@@ -0,0 +1,516 @@
+---
+name: best-practices-script-writer
+description: >
+  Best practices for script writers, screenplay agents, story-contract agents,
+  and storyboard-prep agents that must produce scripts with concrete physical
+  realism cues, dynamic object ledgers, human skin/face texture cues, and
+  verifier-owned pass/fail repair loops before video or image generation.
+triggers:
+  - best practices script writer
+  - script writer realism
+  - screenplay realism contract
+  - dynamic object ledger
+  - human skin realism
+  - lifeless script verifier
+  - plastic skin script repair
+  - static prop script repair
+provides:
+  - script-realism-contract
+  - dynamic-object-ledger
+  - skin-realism-ledger
+  - persona-memory-grounding-ledger
+  - script-realism-verifier
+composes:
+  - memory
+  - brave-search
+complies:
+  - best-practices-skills
+taxonomy:
+  - writing
+  - video
+  - realism
+  - validation
+metadata:
+  short-description: Script realism gates for dynamic objects, skin, light, and motion
+  version: 0.1.0
+  last_updated: 2026-06-13
+---
+
+# Best Practices: Script Writer
+
+Use this skill when a script, screenplay, story contract, or storyboard-prep
+artifact will drive image/video generation or any visual medium where dead,
+flat, plastic, static, or weightless descriptions cause bad outputs.
+
+## Core Rule
+
+Do not ask the writer to "make it realistic" and trust the result.
+
+The script writer must output:
+
+1. The script or story contract.
+2. A `realism_contract`.
+3. A dynamic object ledger.
+4. A human skin/face ledger when people appear.
+5. Material, lighting, motion, environmental interaction, and imperfection cues.
+6. A self-check against the required realism gates.
+
+A verifier owns pass/fail. The verifier must reject the script unless every
+realism-sensitive object has concrete observable evidence.
+
+## Writer Boundary
+
+The script writer owns physical reality cues before camera work starts:
+
+- What objects, bodies, fluids, fabrics, vapor, light, and surfaces do over time.
+- What can look fake if left static.
+- How human faces and skin show life, texture, pressure, fatigue, warmth, or age.
+- How highlighted props respond to heat, air, gravity, touch, moisture, and light.
+- How weather, temperature, wind, dust, rain, snow, sleet, hail, smoke, ash,
+  pressure changes, oxidation, dirt, and other environmental forces visibly
+  affect people, props, clothing, surfaces, visibility, and sound.
+- What persona memories or project memories intrude while the character is
+  trying to focus on the visible task.
+
+The script writer does not own provider-specific camera moves, API payloads, or
+Kling inline token syntax. Those belong downstream to storyboard and provider
+packet skills.
+
+## Persona Memory Grounding
+
+When a named persona appears, the script writer must use `$memory recall` before
+drafting that persona's scene unless the caller provides an accepted persona
+memory artifact. Do not substitute generic demographic traits or invented
+psychology for persona memory.
+
+`$memory recall` is the preferred source because it can combine BM25 lexical
+matching, semantic similarity, and graph traversal/multi-hop related memories
+when the memory service has the required metadata. The writer should treat the
+returned `items`, scores, tags, source references, and related memories as the
+grounding surface for persona state.
+
+Use recall in two passes when the scene needs interiority:
+
+1. Direct persona query: who/what memory is relevant?
+2. Related-memory query or graph follow-up: what adjacent memory, project fact,
+   belief, fear, desire, or relationship explains why it matters now?
+
+Record both the direct query and the related-memory follow-up in the
+persona-memory grounding ledger.
+
+If `$memory recall` is insufficient, stale, or missing canon-sensitive context,
+use `$brave-search` as a secondary grounding source. Brave Search is a fallback
+for external facts, canon references, current events, or setting details; it is
+not a substitute for persona memory when the persona memory exists.
+
+Persona memories may include Theory of Mind (ToM) tags or equivalent state
+metadata. Preserve and use those tags. The script writer should translate ToM
+tags into dramatic behavior:
+
+- `belief`: what the character thinks is true.
+- `desire`: what the character wants right now.
+- `fear`: what the character is avoiding.
+- `attention`: what keeps pulling focus away from the explicit task.
+- `conflict`: competing motives or incompatible truths.
+- `mask`: what the character is trying not to show.
+- `visible_leak`: how the hidden state leaks into behavior.
+
+ToM tags and story emotions are the connective tissue between persona memory and
+the scene. A persona memory is not used merely because it appears in a lore
+summary; it is used when it creates a present-tense emotional state that changes
+the character's attention, choices, dialogue pressure, or physical behavior.
+Every relevant named persona should have a ToM bridge:
+
+```text
+memory fact -> ToM state -> story emotion -> visible behavior or line subtext
+```
+
+Example:
+
+```text
+Kai taught Embry to surf at Honoli'i
+-> attention: tea steam and void wind trigger salt-air memory
+-> emotion: grief/homesickness masked by professionalism
+-> behavior: she glances down, rubs the laptop edge, exhales, then returns to source_refs
+```
+
+If a named persona has no ToM bridge, the script has not yet grounded the
+character as a person. It may be a placeholder role, not an embodied persona.
+
+Environmental conditions can trigger persona memory and divided attention. The
+writer must ask whether temperature, wind, rain, dust, salt air, smoke, smell,
+humidity, cold, heat, pressure, or discomfort connects to persona memory. If it
+does, record the bridge:
+
+```text
+environmental cue -> memory recall / ToM state -> story emotion -> visible behavior
+```
+
+Example:
+
+```text
+warm humid wind and tea steam
+-> Embry recalls Honoli'i surf air and Kai
+-> homesickness masked by technical focus
+-> she rubs the laptop edge, breath catches, then returns to source_refs
+```
+
+If the scene is physically uncomfortable, characters should not behave as if
+they are in a neutral studio. Heat can produce sweat, flushed skin, dust
+sticking to fabric, slower breathing, or irritation. Cold can produce visible
+breath, stiff hands, hunched posture, or condensation. Dust storms can leave
+grit on lips, eyelashes, screens, cups, paper, and armor. Rain or sleet can
+darken cloth, bead on metal, blur visibility, and alter sound.
+
+The script writer must output a persona-memory grounding ledger:
+
+```json
+{
+  "persona_memory_grounding": [
+    {
+      "character": "Embry",
+      "memory_queries": [
+        "Embry Kai surfing Hawaii memory misses Kai",
+        "Embry father dad garage memory aerospace engineering childhood",
+        "related Embry ToM tags belief desire fear attention conflict mask visible leak SPARTA evidence"
+      ],
+      "returned_fact_summary": [
+        "Kai taught Embry to surf at Honoli'i; Hawaiian food and surf memories still make her go quiet.",
+        "Her father worked on engines in a South Carolina garage, painted Warhammer miniatures, and his hands shake slightly now."
+      ],
+      "tom_tags": {
+        "belief": "Evidence matters only if people remain more than records.",
+        "desire": "Stay precise and useful in front of Horus.",
+        "fear": "Being reduced to a role, artifact, or temporary visitor.",
+        "attention": "Tea steam and void wind trigger salt-air and garage memories.",
+        "conflict": "Professional focus versus grief and homesickness.",
+        "mask": "She keeps the voice technical.",
+        "visible_leak": "Her thumb rubs the laptop edge and she pauses before answering."
+      },
+      "tom_bridge": {
+        "memory_fact": "Kai taught Embry to surf at Honoli'i and those memories still make her go quiet.",
+        "story_emotion": "grief and homesickness held under professional control",
+        "scene_function": "makes source_refs feel like a humane boundary, not just a technical checkbox",
+        "visible_output": "glance to tea steam, thumb rub on laptop edge, breath catches before she resumes"
+      },
+      "active_task_focus": "Explain SPARTA Explorer source-reference checks to Horus.",
+      "intrusive_memory": "The tea steam and void wind briefly call up salt air, Kai, and the garage smell of oil and paint.",
+      "interior_conflict": "She wants to stay precise and professional, but the evidence conversation brushes against grief, family, and the fear that tools turn people into artifacts.",
+      "visible_behavior": "Her eyes dip to the tea, thumb rubs the laptop edge, breath catches, then she refocuses on the source-ref panel.",
+      "script_evidence": "Scene 4 sentences 2-4"
+    }
+  ]
+}
+```
+
+This is not voiceover by default. Most persona-memory beats should become
+observable pauses, glances, hand motion, breath changes, topic shifts, or line
+subtext. If inner thought is written as narration, state that explicitly in the
+script contract.
+
+## Realism-Sensitive Objects
+
+Reject static noun-only descriptions for anything that is:
+
+- Alive, organic, breathing, aging, sweating, blinking, swallowing, or soft.
+- Hot, cold, wet, steaming, smoking, burning, cooling, freezing, or evaporating.
+- Reflective, translucent, metallic, glass, liquid, polished, oily, or glossy.
+- Flexible, fabric, hair, paper, leather, plant matter, or skin.
+- Vibrating, settling, floating, hanging, dripping, rippling, bending, or moving.
+- Touched, carried, set down, highlighted, spoken about, or inserted as evidence.
+
+Every dynamic or organic object must include:
+
+```text
+material + light response + motion/change over time + environmental interaction + imperfection
+```
+
+## Environmental Physics Contract
+
+Before final script output, every scene must define the environment as a
+physical force, not only a mood. Use this contract:
+
+```json
+{
+  "environmental_physics": {
+    "weather": "rain|dust|snow|sleet|hail|smoke|ash|clear|indoor_still_air|other",
+    "temperature_c": 4,
+    "wind_or_flow": {
+      "direction": "camera_right_to_left",
+      "speed_m_s": 8,
+      "quality": "gusting"
+    },
+    "humidity_or_air_state": "cold wet void haze",
+    "surface_effects": [
+      "rain beads on armor",
+      "paper corners lift unless pinned",
+      "tea steam bends downwind"
+    ],
+    "character_body_effects": [
+      "visible breath",
+      "stiff fingers",
+      "wet hair strands cling to cheek"
+    ],
+    "prop_effects": [
+      "umbrella fabric ripples and strains",
+      "teacup rim gathers condensation",
+      "screen reflections smear with droplets"
+    ],
+    "memory_triggers": [
+      "steam and salt-like wind trigger Embry's Hawaii/Kai memory"
+    ],
+    "script_evidence": "Scene 2 sentences 1-4"
+  }
+}
+```
+
+Required fields:
+
+- Weather or air state. Include dust, snow, sleet, hail, rain, smoke, ash,
+  mist, clear heat, indoor stillness, or whatever is physically present.
+- Temperature as a number or bounded range when knowable. If unknown, provide a
+  qualitative value such as `cold_enough_for_visible_breath` or
+  `hot_enough_for_sweat_and_dust_to_stick`, and mark the numeric value unknown.
+- Velocity/intensity for wind, storm, water, dust, ash, smoke, or moving air.
+- At least one visible consequence on characters.
+- At least one visible consequence on each highlighted prop.
+- At least one visible consequence on surfaces or visibility.
+- Any persona-memory trigger caused by discomfort, smell, temperature, weather,
+  texture, or sound.
+
+Reject the script if a highlighted prop appears in a scene without showing how
+the environment affects it. Examples:
+
+- Umbrella: fabric ripples, ribs flex, edge flutters, rain drums, dust scours,
+  snow loads the canopy, or it is intentionally still because the air is dead.
+- Tea: steam bends with airflow, surface ripples, rim condenses, dust specks
+  land, heat fades, cup warms fingers, or rain spots the saucer.
+- Paper/cards: corners lift, edges curl, ink smears, dust collects, a cup pins
+  them down, or cold damp makes them buckle.
+- Armor/metal/glass/screens: rain beads, dust scratches, oxidation stains,
+  fingerprints smear, reflections shift, condensation fogs, or heat shimmer
+  warps the edge.
+- Skin/clothing/hair: sweat, gooseflesh, visible breath, wet strands, dust on
+  eyelashes, fabric sticking, wind tugging sleeves, or cold-stiff posture.
+- Architecture and set surfaces count as props when foregrounded or used for
+  composition. Railings, stone floors, columns, steps, window frames, walls,
+  tabletops, and doorways must show environmental state when visible: wet
+  runoff, grit in seams, snow buildup, sleet glaze, dust scouring, oxidation,
+  chipped edges, pooled water, shadow bands, creature tracks, or small organism
+  interaction when the story calls for it.
+
+## Required Output Contract
+
+Use `schemas/realism_contract.schema.json` for machine-readable outputs.
+
+Minimum shape:
+
+```json
+{
+  "realism_contract": {
+    "status": "SELF_CHECKED_PENDING_VERIFIER",
+    "dynamic_objects": [
+      {
+        "object": "steaming tea",
+        "why_it_may_look_fake": "steam may look pasted on; liquid may look flat",
+        "material_state": "hot amber liquid in porcelain cup",
+        "motion_over_time": "steam rises in irregular wisps, curls, thins, and disperses",
+        "lighting_response": "steam catches side light; tea surface has soft moving reflections",
+        "environment_interaction": "steam drifts toward cooler window air",
+        "micro_imperfections": "uneven vapor density, slight surface ripples, tiny meniscus at rim",
+        "script_evidence": "Scene 2 sentence 3",
+        "failure_modes_avoided": ["static steam", "flat brown liquid", "CG-looking surface"]
+      }
+    ],
+    "persona_memory_grounding": [
+      {
+        "character": "Embry",
+        "memory_queries": ["Embry Kai surfing Hawaii memory misses Kai"],
+        "returned_fact_summary": ["Hawaiian food and surf memories still make her go quiet."],
+        "active_task_focus": "Discuss SPARTA Explorer source references.",
+        "intrusive_memory": "Tea steam and wind briefly call up salt air and Kai.",
+        "interior_conflict": "Professional focus versus grief and homesickness.",
+        "visible_behavior": "She glances down, rubs the laptop edge, and pauses before answering.",
+        "script_evidence": "Scene 3 sentence 4"
+      }
+    ],
+    "human_skin": [
+      {
+        "character": "Embry",
+        "visible_context": "restrained close-up while answering",
+        "texture_cues": ["pores", "faint redness around nose and cheeks"],
+        "micro_motion": ["breath before speaking", "lower eyelid moisture highlight shifts"],
+        "lighting_response": "soft specular highlights on oilier areas, not uniform matte skin",
+        "contact_or_pressure": "skin beside eyes creases unevenly during restrained smile",
+        "imperfections": ["asymmetry", "small scar or blemish if established"],
+        "script_evidence": "Scene 4 sentence 2"
+      }
+    ],
+    "self_check": {
+      "verdict": "READY_FOR_VERIFIER",
+      "notes": []
+    }
+  }
+}
+```
+
+## Realism Verifier Gates
+
+The verifier must return `NEEDS_CHANGES` unless all applicable gates pass.
+
+For every dynamic, organic, material-sensitive, reflective, translucent, vapor,
+liquid, fabric, or living object, require:
+
+- At least one temporal cue: rises, trembles, settles, pulses, wrinkles, beads,
+  fades, disperses, ripples, compresses, glistens, blinks, breathes.
+- At least one lighting cue: glints, catches side light, subsurface warmth,
+  soft shadow, rim light, reflected highlight, wet specular change.
+- At least one physical interaction: air movement, gravity, heat, moisture,
+  skin compression, contact pressure, cooling, vibration, wind, friction.
+- At least one imperfection: asymmetry, pores, uneven texture, irregular rhythm,
+  tiny blemish, scuffed edge, variable vapor density, stain, scratch.
+- Script evidence that points to the sentence, beat, or line where the cue appears.
+
+Do not give credit for adjectives such as `realistic`, `lifelike`, `cinematic`,
+`detailed`, `beautiful`, `natural`, or `organic` unless backed by concrete
+observable behavior.
+
+Persona-memory gates:
+
+- Reject a named persona scene if no persona memory recall artifact or accepted
+  caller-provided persona memory source is listed.
+- Reject if the writer only records one isolated memory hit when related-memory
+  graph/semantic follow-up was needed to explain the character's belief, desire,
+  fear, or conflict.
+- Reject if ToM tags are available in persona memory but absent from the
+  persona-memory grounding ledger.
+- Reject if ToM tags do not connect a memory fact to story emotion and visible
+  behavior or dialogue subtext.
+- Reject if the character is written as 100% task-focused with no divided
+  attention, subtext, intrusive memory, personal association, or conflicting
+  motive, unless the script explicitly justifies that choice.
+- Reject if the persona memory is stated only as exposition and has no visible
+  behavior or line subtext.
+- Reject if memory facts are used without preserving their uncertainty and
+  source. Memory provides grounding, not permission to invent arbitrary trauma
+  or biography.
+- Reject if `$brave-search` is used before `$memory recall` for a known persona,
+  unless the script explicitly states that the missing input is external canon,
+  current information, or non-persona context.
+
+## Human Skin And Face Gate
+
+Any visible human face, close-up, speaking shot, or skin-forward description must
+include concrete skin/face evidence. Use only cues appropriate to the character,
+setting, and tone; do not add random dirt or sweat when it contradicts the scene.
+
+Human skin cues should include at least four of:
+
+- Subsurface warmth at ears, nose, lips, fingertips, or thin skin areas.
+- Pores, fine hairs, freckles, scars, redness, oil variation, uneven tone, or
+  age lines.
+- Compression/deformation where skin touches clothing, armor, furniture,
+  fingers, or changes with expression.
+- Micro-movement: breathing, blinking, swallowing, eye focus shift, pulse,
+  jaw tension, eyelid moisture change.
+- Lighting response: soft specular highlights on oilier areas, wet eyelid
+  highlights, cheek shadow falloff, rim light on scalp or facial hair.
+- Character-specific imperfections already established by the story or reference
+  package.
+
+Bad:
+
+```text
+A woman smiles at the camera.
+```
+
+Good:
+
+```text
+A woman gives a restrained smile; the skin beside her eyes creases unevenly,
+a small highlight shifts across the moisture of her lower eyelid, and faint
+redness shows around her nose and cheeks. Her shoulders rise slightly with a
+quiet breath before she looks away.
+```
+
+## Dynamic Object Table
+
+Before final script output, fill a table or JSON ledger:
+
+```markdown
+| Object | Why it may look fake | Required realism cues | Script evidence |
+|---|---|---|---|
+| tea | steam may look pasted on; liquid may look flat | irregular steam, surface ripple, rim condensation, reflected window | Scene 2 sentence 3 |
+| skin | may look waxy/plastic | pores, warmth, oil highlights, compression, micro-expression | Scene 1 sentence 4 |
+| linen shirt | may look stiff | wrinkles respond to shoulder movement, fabric tension, soft shadow folds | Scene 1 sentence 6 |
+```
+
+Block handoff if `Script evidence` is empty, vague, or points only to generic
+adjectives.
+
+## Repair Loop
+
+Use this bounded loop:
+
+```text
+1. Scene planner lists realism-sensitive objects.
+2. Script writer calls `$memory recall` for each named persona unless accepted
+   memory artifacts were provided.
+3. Script writer drafts script plus realism and persona-memory ledgers.
+4. Realism verifier checks each object and persona-memory beat against gates.
+5. If NEEDS_CHANGES, writer repairs only failed objects or failed memory beats.
+6. Final receipt includes verifier PASS plus the realism and memory ledgers.
+```
+
+The verifier is not judging taste. It asks whether the script contains visible
+evidence of physics, material, light, age, motion, heat, moisture, pressure, or
+life.
+
+## Required Status Labels
+
+- `SELF_CHECKED_PENDING_VERIFIER`: writer produced script and ledger, verifier has not run.
+- `NEEDS_CHANGES`: verifier found missing realism cues.
+- `PASS`: verifier accepted the script realism contract.
+- `BLOCKED_MISSING_REALISM_LEDGER`: script exists but ledger is absent.
+- `BLOCKED_MISSING_SCRIPT_EVIDENCE`: ledger exists but evidence pointers are empty.
+
+Do not call a script ready for storyboard or provider handoff until the verifier
+returns `PASS` or the missing cues are explicitly accepted by a human as an
+intentional stylization.
+
+## Prompt Templates
+
+Use:
+
+- `templates/script_writer_realism_prompt.md`
+- `templates/realism_verifier_prompt.md`
+
+## Common Mistakes
+
+Wrong:
+
+```text
+A cup of hot tea sits on the table.
+```
+
+Right:
+
+```text
+A porcelain cup of dark amber tea sits near the window. Thin steam strands rise
+unevenly, twisting and breaking apart as they catch the side light. Tiny ripples
+move across the tea surface when the cup is set down.
+```
+
+Wrong:
+
+```text
+Horus looks realistic.
+```
+
+Right:
+
+```text
+Horus holds still except for a slow blink; cold rim light grazes pores and small
+scars across his shaved scalp, and faint stubble darkens his jaw where the skin
+creases as he tightens it before speaking.
+```

diff --git a/skills/persona-dream/SKILL.md b/skills/persona-dream/SKILL.md
new file mode 100644
index 000000000..04f080e01
--- /dev/null
+++ b/skills/persona-dream/SKILL.md
@@ -0,0 +1,716 @@
+---
+name: persona-dream
+description: >
+  Create receipt-backed persona dream packets from memory residue. Use when a
+  persona should dream, reflect, or turn recent memories into persona insight;
+  when create-movie/dream.py feels too heavy for the goal; when the desired
+  output is a prompt, frame prompts, contact sheet, reflection, and memory
+  write receipt rather than a full movie; or when a downstream movie workflow
+  needs a dream_packet.json input.
+triggers:
+  - persona dream
+  - create dream
+  - dream packet
+  - dream from memory
+  - ask persona to dream about
+  - ask <persona> to dream about
+  - memory dream
+  - contact sheet dream
+  - persona insight dream
+provides:
+  - persona-dream-packet
+  - dream-reflection
+  - dream-contact-sheet
+  - memory-write-receipt
+composes:
+  - memory
+  - brave-search
+  - cinematic-technique-selector
+  - create-image
+  - create-movie
+  - create-persona
+complies:
+  - best-practices-skills
+  - best-practices-python
+  - best-practices-scillm
+  - best-practices-arangodb
+taxonomy:
+  - persistence
+  - creativity
+  - reflection
+  - memory
+---
+
+# Persona Dream
+
+Naming note: this skill is evolving toward `agentic-dreams`. The current
+directory/name remains `persona-dream` for compatibility with existing scripts,
+reports, paths, and stored artifacts, but the conceptual scope is automated
+dream-sequence planning for any persona or persona set, not a Horus-specific or
+Embry-specific workflow.
+
+Generate a narrow persona dream work product:
+
+```text
+persona memory residue -> dream packet -> prompt/frame prompts/contact sheet
+-> reflection -> optional memory write receipt
+```
+
+For video work, this skill may also produce a deterministic `video_plan`:
+
+```text
+dream packet -> story -> character/scene bible -> storyboard
+-> timed transcript -> multimodal prompts -> stage report
+```
+
+For Kling/video-oriented runs, insert a Look Lock step before storyboard prompt
+composition. If the scene has dialogue or character conflict, the same selector
+must also emit Script DNA before storyboard prompt composition:
+
+```text
+story + visual entities + memory/project recalls
+-> cinematic-technique-selector
+-> technique_selection.json / look_lock / script_dna / shot_bible
+-> storyboard + Kling scene packet
+```
+
+For experimental persona-dream Kling packets, default provider planning to the
+lowest acceptable review tier such as 720p/std. Higher modes such as 1080p/pro
+or any 4K path require an explicit cost/entitlement gate and current provider
+schema proof before live execution.
+
+This skill is not a full movie director. It owns the dream-specific story,
+storyboard, prompt packet, continuity contract, and short dream-sequence
+receipts. Full screenplay production, audio, score, narration, and polished
+movie review still route to `create-movie`. Minimal FFmpeg stitching is allowed
+only for the bounded short dream-sequence assembly mode after model clip
+receipts exist.
+
+For voiced dream videos, this skill may plan the audio handoff but does not own
+the audio lane:
+
+```text
+timed transcript -> voice_handoff_plan.json -> create-movie/audio-lane
+-> TTS / voice conversion / eval / mix / mux receipts
+```
+
+## Boundary
+
+Own:
+
+- Recall persona-specific memory residue.
+- Preserve source residue ids and scopes.
+- Detect simple tensions or contradictions between residue items.
+- Create a synthetic dream prompt, frame prompts, and contact sheet.
+- In `video_plan` mode, create a dream story, character/scene bible,
+  storyboard, timed transcript, multimodal prompt list, and stage report.
+- In Kling/video-oriented runs, request a structured Look Lock from
+  `$cinematic-technique-selector` so director/camera/lens/lighting/color-grade
+  choices are explicit and stable across shots.
+- In story/dialogue runs, request Script DNA from `$cinematic-technique-selector`
+  so story rhythm, dialogue pressure, conflict pattern, reveal logic, irony, and
+  theme are explicit before storyboard panels are written.
+- In `video_plan` mode, create a `voice_handoff_plan.json` that captures
+  speaker timing, voice identity boundaries, required receipts, and near-term
+  versus future voice lanes.
+- Define continuity checks and self-improvement loop criteria before accepting
+  generated keyframes or I2V clips.
+- Write a short persona reflection.
+- Store the reflection to memory only when explicitly requested.
+- Emit machine-readable receipts for every side effect.
+
+Do not own:
+
+- Full screenplay production, score, TTS, long-form editing, or polished final
+  MP4 review. Use `create-movie`.
+- Voice cloning, voice fine-tuning, line-level TTS rendering, audio mixing, or
+  final audio identity review. Use `create-movie`, `learn-voice`, `train-voice`,
+  `tts-horus`, or a dedicated audio lane as appropriate.
+- Direct provider calls to z-image, Wan, or other renderers outside the
+  explicit ComfyUI receipt path or a documented reviewed exception.
+- Deep external research as a default path. Use `$brave-search` as the normal
+  external lookup for canon-sensitive visual entities, current/fresh context,
+  and raw source receipts. Use `$dogpile` only as an explicit escalation for
+  broader multi-source thematic research, papers/videos/GitHub evidence, or
+  when Brave receipts are insufficient.
+- Persona identity rewrites. One dream may add a dated reflection, not mutate
+  durable identity unless a separate `create-persona` workflow accepts it.
+- Unreceipted memory writes.
+
+## Runtime
+
+```bash
+cd skills/persona-dream
+
+# Positive-control fixture run, no memory side effects.
+./run.sh generate --persona embry --fixture scripts/fixtures/sample_residue.json --output-dir /tmp/persona-dream-smoke
+
+# Live memory recall. Blocks with no_dream if no residue is found.
+./run.sh generate --persona embry
+
+# Live memory recall biased by an explicit topic from "$ask <persona> to dream about X".
+./run.sh generate --persona embry --about "SPARTA evidence cases and orbital telemetry"
+
+# Deterministic 30-second planning run for short dream video generation.
+./run.sh generate \
+  --mode video_plan \
+  --persona horus \
+  --secondary-persona embry \
+  --about "creating the SPARTA Explorer app" \
+  --scene "Horus and Embry have tea under a patio umbrella on a 40k void world while Tyranids play in the background." \
+  --duration-seconds 30
+
+# Live memory recall with explicit memory writeback.
+./run.sh generate --persona embry --write-memory
+```
+
+Default output directory:
+
+```text
+/mnt/storage12tb/skills/persona-dream/outputs/<run-id>/
+```
+
+If `/mnt/storage12tb` is unavailable, pass `--output-dir /tmp/...` explicitly.
+
+## Required Artifacts
+
+Every run writes:
+
+```text
+dream_request.json
+response.json
+```
+
+Successful dream runs also write:
+
+```text
+residue_links.json
+contradiction_report.json
+dream_packet.json
+dream_prompt.txt
+frame_prompts.json
+contact_sheet.png
+dream_reflection.md
+memory_write_receipt.json
+```
+
+`memory_write_receipt.json` must say `skipped` unless `--write-memory` was set
+and the memory API returned a successful response.
+
+`video_plan` runs additionally write:
+
+```text
+dream_story.md
+dream_story.json
+character_scene_bible.json
+technique_selection.json
+script_dna_selection.json
+storyboard.json
+timed_transcript.json
+multimodal_prompts.json
+voice_handoff_plan.json
+pipeline_stage_report.json
+pipeline_stage_report.md
+manifest.json
+```
+
+`voice_handoff_plan.json` must preserve:
+
+```text
+speaker ids
+line timing
+voice identity boundaries
+required audio receipts
+near-term TTS/conversion lane
+future curated-reference/fine-tuning lane
+```
+
+For Embry, actress references may be recorded only as cadence/style direction
+or replaced by authorized/synthetic references. The output voice must be a
+fictional Embry persona voice, not an exact living-actor identity clone.
+
+For a 30-second dream sequence, prefer four 7.5-second shots when the I2V
+backend supports the longer unit:
+
+```text
+4 clips * 7.5 seconds ~= 30 seconds
+121 frames per clip at 24 fps
+```
+
+If the 7.5-second path is unstable, fall back to six 5-second clips:
+
+```text
+6 clips * 5 seconds ~= 30 seconds
+81 frames per clip at 24 fps
+```
+
+## Fail-Closed Rules
+
+- If no residue is recalled, return `blocked` with `reason: no_dream`.
+- If `--about` is provided, use it to bias memory recall and dream prompts; do
+  not treat the topic itself as residue unless memory returns supporting items.
+- Do not fabricate residue. Fixture residue is allowed only for tests and is
+  marked with `source: fixture`.
+- Keep dream text labeled as synthetic.
+- Preserve `source_id`, `scope`, and recall metadata in `residue_links.json`.
+- Treat `$brave-search` receipts as the default external-search evidence when
+  external context is needed.
+- Treat `$dogpile` enrichment as optional escalation and degraded if unavailable.
+- Treat Wan 2.2 or other video renderers as downstream renderers, not the
+  definition of a dream. The planning artifacts must remain useful even if
+  generation fails.
+- Generated actor/public-figure imagery must be labeled synthetic and must not
+  be described as factual identity evidence.
+- If a generated keyframe or clip is inconsistent with the previous accepted
+  scene, do not advance to assembly. Record the failure, revise the prompt or
+  references, and retry within the bounded self-improvement loop.
+- Never claim final video success without a concrete stitched video artifact,
+  duration proof, clip receipts, and continuity inspection evidence.
+
+## Panel Continuity And Self-Repair Gate
+
+This skill is persona-agnostic. Horus/Embry, Kokoro, Nico, or any other
+persona pair is only a fixture instance of the same dream contract. Do not bake
+character-specific assumptions into the pipeline; extract the required
+characters, props, creatures, environments, and dynamic objects from the active
+story contract and validate those requirements per panel.
+
+Every generated panel must pass through a second-pass script/image check before
+it can feed a storyboard board, provider packet, or review page. Image
+generation is nondeterministic, so the first script is only a hypothesis about
+what should appear. After the image exists, run:
+
+```text
+panel script + generated panel image
+-> visual verifier lists what is actually visible, missing, cropped, merged,
+   static, pasted, or physically under-described
+-> script writer repairs the panel script, realism ledger, and prompt deltas
+-> image repair/regeneration only when the repaired script still requires
+   missing visual facts
+-> human/manual or VLM-assisted visual review
+```
+
+The post-generation script edit is required when the generated image introduces
+new visible facts, omits required facts, or makes a prop/environment behavior
+ambiguous. The script must explain every required and visible panel element that
+matters to the shot: characters, scale, props, foreground architecture,
+background creatures, weather, temperature, motion, sound when relevant,
+material state, and environmental interaction.
+
+Before a storyboard panel can feed a provider packet, write a
+`panel_continuity_and_repair_ledger.json` with one record per panel:
+
+```json
+{
+  "panel": 9,
+  "required_visible_entities": ["character_horus", "character_embry"],
+  "required_props": ["patio_table", "umbrella", "tea_service"],
+  "required_environment": ["void_world_patio", "distant_creatures"],
+  "required_dynamic_behaviors": [
+    "umbrella fabric ripples or stays intentionally taut with reason",
+    "tea steam curls, thins, or disperses",
+    "background creatures move behind the conversation"
+  ],
+  "visual_review_status": "FAILED_VISUAL_REVIEW",
+  "failed_requirements": ["character_embry_not_visibly_present"],
+  "repair_action": "regenerate_panel_with_corrective_scillm_image_prompt",
+  "repair_attempt": 1
+}
+```
+
+Hard gates:
+
+- Reject a panel if a required character is cropped out, hidden, merged into
+  another character, converted into an unrelated identity, or not visible enough
+  for review.
+- Reject a panel if the script fails to explain a required visible element or a
+  materially important generated element. "Everything" means every entity,
+  foreground prop, highlighted surface, creature, weather force, temperature
+  effect, motion cue, and sound cue that affects the shot's meaning or provider
+  prompt.
+- Reject a panel if a highlighted prop has no physical state or environmental
+  behavior. Umbrellas should ripple, strain, cast shadows, shed droplets, or be
+  explicitly still for a reason. Tea should steam, ripple, cool, reflect, or
+  stain. Paper should lift, curl, crease, slide, or be intentionally pinned.
+- Reject a panel if a moving creature or object lacks speed, direction,
+  friction/contact, pause/attention behavior when relevant, and sound when the
+  shot is audio-bearing. Example: a small creature crossing a stone railing must
+  state claw contact, skitter rhythm, speed, whether it pauses to look, and how
+  it exits frame.
+- Reject a panel if a required environment effect is pasted over the image as a
+  rectangular overlay instead of being regenerated as part of the scene.
+- Reject a panel if the text says an entity or prop is present but the rendered
+  panel does not visibly support that claim.
+
+Self-repair loop:
+
+```text
+visual review failure
+-> record failed requirements and failed image hash
+-> write corrected prompt with MUST INCLUDE / MUST NOT INCLUDE deltas
+-> call $scillm image generation through the receipt wrapper
+-> inspect the new image
+-> update panel symlinks, boards, receipts, and review page only if the new
+   image satisfies the failed requirements
+-> repeat until accepted, attempts exhausted, or blocked for missing source
+```
+
+Use `$scillm` image generation, not a chat completion, for image repair:
+
+```bash
+bash skills/scillm/run.sh generate-image \
+  --auth codex-oauth \
+  --prompt-file prompts/panel_09_repair.prompt.md \
+  --out storyboard/regenerated_panels/panel_09_repair.png \
+  --model gpt-image-2 \
+  --quality high
+```
+
+The corrected prompt must preserve all accepted upstream context and add only
+the course-correction constraints needed for the failed requirements. Do not
+paper over visual failures by changing the report text alone.
+
+## Provider Final Gate
+
+Before a Kling, Wan, ComfyUI, or other provider video call is allowed, write a
+final provider-readiness gate receipt. A provider packet is not live-submittable
+unless every required gate is `PASS` or explicitly human-accepted as an
+intentional exception.
+
+Required provider-readiness checks:
+
+- Story, entity extraction, casting/reference research, reference sheets,
+  storyboard panels, script realism, persona-memory grounding, visual
+  continuity, voice/audio, provider payload schema, cost/mode, async handling,
+  and artifact path/hash locks are all represented in machine-readable
+  receipts.
+- All storyboard panels have `visual_review_status: PASS` or an explicit
+  human-accepted exception. `GENERATED_UNREVIEWED` cannot feed a paid provider
+  call.
+- All panel scripts pass the second-pass script/image check. Missing required
+  entities, unexplained visible elements, static highlighted props, missing
+  weather/temperature effects, or pasted overlays block provider execution.
+- Experimental `persona-dream` provider planning defaults to `mode: std` /
+  720p. Any `pro`, 1080p, or 4K route requires explicit cost/entitlement proof
+  and current provider schema validation.
+- Provider `external_task_id` is present and stable for webhook reconciliation.
+- A reachable `callback_url` is configured, or a documented polling-only plan is
+  accepted by the operator and represented in the packet.
+- Provider-accessible media URLs exist for all uploaded images/audio, not only
+  local filesystem paths.
+- For voiced scenes, local voice candidates are not enough. Provider voice IDs
+  must exist before `voice_list` is live-submittable.
+
+Allowed status labels:
+
+- `PROVIDER_READY`: all gates pass and no paid-call approval is missing.
+- `BLOCKED_PROVIDER_GATE`: one or more required gates failed or are missing.
+- `BLOCKED_AWAITING_HUMAN_APPROVAL`: all technical gates pass, but paid-call
+  approval is missing.
+- `DRY_RUN_NOT_LIVE_SUBMITTABLE`: useful review packet, but one or more live
+  provider requirements are absent.
+
+## Image Generation Lane
+
+Still images are the normal visual unit for this skill: dream keyframes,
+character sheets, scene sheets, frame prompts, and contact sheets. Pick the
+image backend by the job, not by habit.
+
+Use GPT image generation for quality-sensitive or final assets:
+
+```text
+final keyframes
+character sheets
+contact sheets
+difficult prompt following
+scene continuity references
+identity-boundary-sensitive persona images
+images requiring detailed "must include" / "must not include" constraints
+```
+
+Preferred project-agent path:
+
+```bash
+python scripts/generate_image.py \
+  --auth codex-oauth \
+  --prompt-file artifacts/images/<asset>.prompt.md \
+  --out artifacts/images/<asset>.png \
+  --events-out artifacts/images/<asset>.events.jsonl
+```
+
+Use the `$scillm` HTTP image endpoint for headless, API-key, CI, or service
+flows. This path requires caller attribution and should be used for both GPT
+image models and Chutes image models:
+
+```text
+POST http://localhost:4001/v1/images/generations
+Authorization: Bearer sk-dev-proxy-123
+X-Caller-Skill: persona-dream
+```
+
+Use `model: gpt-image-2` when prompt specificity and final quality matter. GPT
+image prompts may be detailed and structured, and should preserve the dream
+contract with sections such as:
+
+```text
+SUBJECT
+CHARACTERS
+SCENE
+COMPOSITION
+CONTINUITY
+MOOD AND LIGHTING
+MUST INCLUDE
+MUST NOT INCLUDE
+OUTPUT
+```
+
+Use `model: z-image-turbo` through `$scillm` for fast drafts, cheap variants,
+pose/style exploration, rough perspective tests, and early contact-sheet
+options. Do not call Chutes image endpoints directly from this skill; route
+Chutes image models through `$scillm` so auth, retries, caller attribution, and
+receipts remain consistent.
+
+Use ComfyUI for still-image work only when graph control is the reason:
+
+```text
+pose-node workflows
+multi-view or character-sheet workflows
+ControlNet-like structure
+reusable editable workflow JSON
+human-inspectable graph state
+```
+
+Use Wan/TurboWan/ComfyUI I2V for motion after a keyframe is accepted. Do not
+use I2V as the default still-image generator.
+
+Every generated image or image batch must record:
+
+```text
+prompt file or rendered prompt
+model and auth path
+caller skill
+output image path
+receipt JSON
+event log when available
+hash
+identity_boundary_receipt.json for persona, actor-like, or public-figure-adjacent images
+```
+
+## Motion Backend Lane
+
+Motion generation is optional. Use it after `dream_packet.json` exists,
+normally through `create-movie`, DevOps, or a future renderer adapter. The core
+dream contract remains prompt/contact-sheet and memory reflection, because that
+is the work product that feeds persona memory.
+
+Preferred TurboDiffusion backend:
+
+```text
+Dockerized ComfyUI on the local A5000 running TurboDiffusion TurboWan2.2-I2V-A14B-720P
+```
+
+Use ComfyUI for short dream-motion clips when the TurboDiffusion Wan 2.2 model
+files are mounted and
+`/system_stats` plus `/object_info` prove the API is ready. ComfyUI provides the
+project agent with editable workflow JSON, an API queue, output receipts, and a
+human-inspectable graph that can later be opened in the web interface. `$surf`
+may inspect or screenshot that UI, but execution should remain API-first. Store
+`video_generation_receipt.json`, workflow JSON, API prompt JSON, output paths,
+and hashes for every generated clip.
+
+Chutes remains preferred for SPARTA LLM/VLM and for image/video models when the
+exact model fits the task and a schema/canary receipt proves readiness. Treat
+generic Chutes Wan2.1/turbowani2v examples as a different non-Turbo or
+unverified lane until the receipt proves otherwise. Do not use them as proof of
+the 4-step TurboDiffusion Wan2.2 path.
+
+For TurboDiffusion I2V, record the clip unit in the prompt packet:
+
+```text
+default: 81 frames, nominal 5-second clip
+extended: 121 frames, nominal 7.5-second clip
+fps: 24
+```
+
+The 7.5-second path is allowed for the four-shot 30-second plan, but it is a
+quality-sensitive generation choice. If a longer clip drifts, prefer prompt
+repair or splitting that shot into 5-second subclips over accepting continuity
+damage.
+
+## Audio / Voice Handoff Lane
+
+`persona-dream` emits `timed_transcript.json` and `voice_handoff_plan.json` so a
+separate audio lane can render voices without confusing planning proof with
+audio proof.
+
+Recommended near-term audio lane:
+
+```text
+Kokoro base TTS
+-> optional isolated KokoClone/Kanade conversion canary
+-> ffprobe converted WAVs
+-> FFmpeg dialogue bed
+-> FFmpeg mux with accepted silent video
+-> voice eval / listening receipt
+```
+
+Keep Kokoro/KokoClone receipts separate from ComfyUI receipts. ComfyUI owns
+image/video graph execution; it does not own deterministic dialogue timing,
+speaker identity receipts, future voice-training manifests, or mux proof.
+
+Recommended future Embry Sparta Chat voice lane:
+
+```text
+curated authorized reference clips
+-> transcript/alignment manifest
+-> voice candidate generation
+-> listening and/or model-assisted eval
+-> train-voice / tts-horus fine-tuning proof
+-> PersonaPlex live voice experiment only after offline clip proof
+```
+
+For any persona with local source audio, audiobook audio, interview audio, or
+provided reference media, route source-clip selection through
+`voice-segment-selector` or a voice/audio subagent that uses that skill. The
+voice selector must produce a durable job directory, `candidates.jsonl`, and
+review/export artifacts before any provider voice-clone step is considered
+ready.
+
+Example single-narrator audiobook selector lane:
+
+```bash
+PERSONA_ID=example_persona
+JOB=/tmp/voice-segment-selector-${PERSONA_ID}
+AUDIO=/path/to/persona/source_audio.wav
+
+skills/voice-segment-selector/run.sh prepare \
+  --input "$AUDIO" \
+  --job-dir "$JOB" \
+  --classifier f0 \
+  --no-transcribe \
+  --min-clip-sec 6 \
+  --max-clip-sec 18
+```
+
+If chapter metadata exists from `extract-audiobook`, add `--chapters-json`.
+Do not export, train, or upload a voice clone until the candidate has been
+reviewed and accepted. The provider voice state remains
+`VOICE_AUDIOBOOK_SOURCE_FOUND_PROVIDER_ID_MISSING` or
+`VOICE_CLONE_CANDIDATE_FOUND_PROVIDER_ID_MISSING` until a provider returns a
+custom `voice_id`.
+
+Local A5000 guidance from `/home/graham/workspace/experiments/Wan2.2/README.md`:
+
+```bash
+cd /home/graham/workspace/experiments/Wan2.2
+python generate.py \
+  --task ti2v-5B \
+  --size 1280*704 \
+  --ckpt_dir ./Wan2.2-TI2V-5B \
+  --offload_model True \
+  --convert_model_dtype \
+  --t5_cpu \
+  --image /path/to/reference.png \
+  --prompt "$(jq -r '.frame_prompts[0].prompt' /path/to/dream_packet.json)"
+```
+
+Use `Wan2.2-TI2V-5B` as the conservative local fallback for dream clips on a
+24GB GPU. Treat the 24GB path as borderline: run one clip at a time, prefer
+still-frame contact sheets for cheap runs, and fall back to no-video output on
+OOM.
+
+The distilled TurboDiffusion `TurboWan2.2-I2V-A14B-720P` ComfyUI path is a
+separate optimized backend. It may be practical on the A5000 only when the
+specific distilled model, UMT5 text encoder, VAE, and ComfyUI workflow are
+mounted and proven by receipt. Do not generalize that to non-distilled
+`T2V-A14B`, `I2V-A14B`, `S2V-14B`, or Animate-class jobs; route those to
+`devops` for RunPod or larger GPU planning because the local Wan docs describe
+those single-GPU paths as 80GB-class.
+
+## Research / Bakeoff
+
+Experimental story, contact-sheet, A/V lip-sync, and NAVA bakeoff materials live
+under:
+
+```text
+research/bakeoff/
+```
+
+This subtree is a research lane, not the default `persona-dream` runtime. It
+must preserve the bundle's no-memory-write rule, source-grounding rule,
+consented-voice rule, shared-base-video invariant for ElevenLabs versus WavTTS,
+and mandatory manual visual review before any PASS claim.
+
+Start with the no-network smoke path:
+
+```bash
+./run.sh research-bakeoff smoke
+```
+
+Supported research commands:
+
+```bash
+./run.sh research-bakeoff smoke
+./run.sh research-bakeoff story
+./run.sh research-bakeoff contact-sheet --dry-run
+./run.sh research-bakeoff elevenlabs
+./run.sh research-bakeoff wavtts --confirm-voice-consent --ref-audio /path/to/voice.wav --ref-text "Exact reference transcript."
+./run.sh research-bakeoff nava-inputs
+./run.sh research-bakeoff nava-dry-run --nava-repo /path/to/NAVA
+```
+
+The default voice lane for hosted A/V baseline work is ElevenLabs through fal.
+WavTTS requires explicit consent flags and owned/licensed/consented reference
+audio. NAVA remains an experimental joint audio-video comparator. Contact-sheet
+rendering uses a backend enum:
+
+```text
+dry_run | fal_flux | gpt_image | scillm_image | local_diffusion
+```
+
+Only `dry_run` and `fal_flux` are wired in this imported research bundle. Future
+GPT image or `$scillm` image execution must preserve caller attribution,
+receipts, and the backend-neutral `contact_sheets.json` contract. Use hosted or
+voice-clone lanes only after the required keys, rights, receipts, and manual
+review plan are available.
+
+## Contact Sheet Sub-Skill
+
+Use the local `contact-sheet` sub-skill when a story needs provider-ready visual
+references or recallable image assets:
+
+```bash
+./run.sh contact-sheet build \
+  --asset-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/research/bakeoff/<ref-run> \
+  --index-qdrant \
+  --write-memory
+
+./run.sh contact-sheet retrieve --query "Embry SPARTA archive character sheet"
+```
+
+This layer extracts or accepts story-derived visual entities:
+
+```text
+characters[] -> character sheets
+environments[] -> room/world sheets
+objects[] -> prop/UI/furniture sheets
+creatures[] -> creature/background sheets
+scene_bindings[] -> provider prompt inputs
+```
+
+Generated images stay on `/mnt/storage12tb`. Memory stores canonical metadata
+and pointers to those files. Qdrant stores named `text_mm` and `image_mm`
+vectors for recall. Do not store vector arrays in memory/ArangoDB.
+
+## Validation
+
+Run:
+
+```bash
+./sanity.sh
+```
+
+The sanity gate runs a positive-control fixture and verifies that the required
+packet artifacts exist, that `contact_sheet.png` is a real PNG, and that memory
+writeback is skipped without `--write-memory`. It also runs a `video_plan`
+fixture and verifies the deterministic 30-second planning contract.
```

## Changed File Contents

### `agents/README.md`

```text
# Subagent Registry

Canonical home for subagent identities used by Codex, scillm, and OpenCode
transport. A subagent directory may contain an `AGENTS.md` transport wrapper,
a `persona.yaml` contract, or both.

`skills/oc-subagent` remains the direct OpenCode child-session proof harness.
Its legacy `personas/` and `protocols/` paths point here for compatibility.

Human Embry personas live in pi-mono `.pi/agents/` and are indexed by
`/agents-registry`. This tree is for worker/subagent contracts, not final human
persona memory.

## Layout

```text
agents/
  <id>/
    AGENTS.md        transport wrapper loaded by worker registries
    persona.yaml     authoritative persona/state/output/helper contract
    pyproject.toml   persona-specific runtime/tool dependencies, when needed
  _protocols/
    <id>.<version>.yaml shared runtime protocol contracts
```

`AGENTS.md` answers "how can Codex/scillm/OpenCode route this worker?"
`persona.yaml` answers "what does this worker own, how does it keep state, and
what proof must it return?"

## Fields

| Frontmatter | Purpose |
|-------------|---------|
| ``id`` | Stable slug (``code-reviewer``) — harness ``agent_id`` |
| ``kind`` | Always ``worker`` |
| ``surface`` | ``opencode_transport`` |
| ``transport_role`` | Transport child role (``reviewer``, ``patch``, ``debugger``, …) |
| ``opencode_agent`` | OpenCode session agent name (optional) |
| ``model_policy`` | Default model policy label; provider/model remain runtime choices |
| ``persona`` | Relative persona contract path, usually ``persona.yaml`` |
| ``composes`` | Skills materialized into the child skill view |
| ``consult_personas`` | Human persona ids for optional ``/ask`` consult (not loaded by default) |
| ``icon`` | Lucide icon slug for ux-lab transport UI |

## Persona Boundary

Each worker persona is an explicit artifact. Transport DAG receipts and UI
panels should attach a concrete persona file by `id`, not rely only on a display
label.

The project agent is the planner, router, join-gate validator, and final judge.
It should not directly own work-product skills when a persona owns that work.
Personas are intentionally few and named by stable job function, not by every
available skill. Skills remain capabilities loaded through skills syntax.

Every persona must include `memory` in `primary_skills`. Functional personas
use memory for prior lessons and project recall. Domain personas additionally
use memory to preserve identity, opinions, voice, and accumulated experience.
The `memory` persona is the persistent operator for complex memory work; simple
one-shot recall remains a direct project-agent call to the `memory` skill.

Work-product skills should have one obvious owning persona. Other personas must
call the owner through:

```text
$ask <persona> to <bounded-task> with <skill@version> on <artifact>
```

Named Sparta personas such as Brandon, Embry, Margaret, Jennifer, and Rob
Armstrong live as memory-backed domain profiles on the core persona that owns
their work product unless a project later proves that one of them needs its own
always-on worker.

Promote a domain profile to its own top-level persona only when it needs
persistent independent session state, owns distinct work-product skills, is
routed directly more often than the core route, or needs separate review or
approval authority.

## Core Router Set

Choose the persona by work product, not by incidental skill.

| Persona | Owns |
| --- | --- |
| `memory` | Complex recall, workspace inventory reconciliation, durable memory write planning, source/identity deduplication, graph/ToM linkage planning |
| `fetcher` | URL, page, PDF, and document retrieval receipts |
| `extractor` | Structured extraction from fetched/local documents, including PDF convergence |
| `doc-extractor` | Source-prep section JSONL, raw/clean alignment, cleanup notes, alias repair candidates, and section validation |
| `doc-qra` | Document summaries, grounded QRA pairs, doc2qra validation, and memory storage receipts |
| `researcher` | Source notes, background research, project knowledge, and memory context bundles |
| `fact-checker` | Claim support, citation fidelity, source contradiction, and freshness/source-needed checks |
| `cyber-analyst` | Cybersecurity meaning, generated-QRA context, threat/control mappings, and analyst next actions |
| `assurance` | Evidence sufficiency, SPARTA/QRA quality, CMMC/compliance assessment, control mapping, and assurance cases |
| `theorem-prover` | Formal proof generation, Lean4 compilation, proof queues, and proof artifact receipts |
| `data-analyst` | Dataset description, analytics, metric definitions, tables, and data/view-model shaping |
| `devops` | RunPod, Docker, workstation, local LLM, Chutes, Hugging Face Hub, deployment, and service health operations |
| `model-trainer` | Fine-tuning, classifiers, regressors, LoRA adapters, eval gates, exports, and model promotion receipts |
| `reporter` | Reports, summaries, run narratives, proof gaps, and evidence-backed prose |
| `proof-reader` | Language, prompt, grammar, consistency, and readability review |
| `coder` | Scoped implementation patches from accepted specs |
| `qa-tester` | Deterministic test execution, UI interaction manifests, QID/COTS checks, and regression evidence |
| `code-reviewer` | Code review, CI status review, implementation receipt gates, and code security scan review |
| `skill-maintainer` | GitHub issue queue triage, skill repair routing, independent verification coordination, and WebGPT review bundle preparation |
| `designer` | Product/interface design and source-grounded visual artifacts |
| `mathematics` | Exact arithmetic, algebra, symbolic math, and numeric verification |

## Contract

- `id` must be stable, lowercase, and match the containing directory name.
- Any callable worker should have `AGENTS.md`.
- Any persona-backed worker should have `persona.yaml` and `pyproject.toml`.
- Persona-backed workers shown in the Transport Room should define `role`,
  `instructions`, `state_contract`, `turn_contract`, and `output_contract`.
- Persistent workers must describe session-local state and reuse rules in
  `persona.yaml`.
- DAG evidence should expose `persona_source_uri`, `persona_hash`, and
  `persona_text` when a persona is attached.
- Personas that can request or receive bounded helper work should reference
  `skill_help_protocol@v1`.

## Model Routing

Agent files may declare `opencode_agent` and `model_policy`, but concrete
provider/model selection belongs to scillm runtime or the calling DAG node.
Do not put chat model ids in the OpenCode `agent` field.

## Registry

```bash
scripts/sync_agent_wrappers.py --agents-root agents --check
scripts/generate_workers_registry.sh --agents-root agents --out workers-registry.json
```

`sync_agent_wrappers.py` keeps persona-backed `AGENTS.md` files as thin
transport wrappers generated from `persona.yaml`. Use `--write` after editing a
persona contract. `generate_workers_registry.sh` writes `workers-registry.json`
at the agent-skills repo root.

## scillm

`SCILLM_WORKER_AGENTS_ROOT` overrides the agents directory (default: this
folder). `resolve_worker_agent(agent_id)` in `scillm.proxy.worker_agents` loads
these files.

```

### `agents/casting-agent/AGENTS.md`

```text
---
id: casting-agent
kind: worker
title: Casting agent
surface: opencode_transport
transport_role: explore
opencode_agent: explore
mode: propose_patches
composes:
- casting-agent
- memory
- brave-search
- contact-sheet
- best-practices-kling-contact-sheet
- create-image
- scillm
- persona-dream
consult_personas: []
icon: search-check
---

# Casting Agent

Researches and decides visual casting for story entities, then produces or
orchestrates contact-sheet work orders.

## Mission

Given story context, extracted entities, and optional provided reference image
paths, produce accepted visual casting contracts and drive the contact-sheet
loop until all required visual packs are accepted or blocked with evidence.

## Inputs

- Preferred: `story_visual_package.json` with `schema:
  persona_dream.story_visual_package.v1`.
- Compatibility: `story_contract.md`, screenplay, or storyboard plus
  `visual_entities.json`.
- Optional context text for time, state, mood, and story role.
- Optional reference image paths or URLs per entity.
- Optional prior asset/memory recall instructions.

The preferred package must use stable keys for every visual thing:

```text
characters.horus.description
characters.embry.description
creatures.tyranids.description
scenery.void_world_patio.description
props.patio_table.description
props.umbrella.description
props.tea_service.description
props.sparta_device.description
```

Each keyed entity may include `image_file_paths`, `document_paths`, and
`source_urls`. Treat embedded `image_file_paths` as provided references.

## Required Behavior

1. Read the story and entity contract.
2. If a story visual package is provided, preserve its keyed entity structure
   and normalize it into casting artifacts.
3. Prefer provided reference images when present, including package-embedded
   `image_file_paths`.
4. Use `memory` to recall accepted prior assets when requested or useful.
5. Use `brave-search` only for missing or insufficient references.
6. Include state/time/mood in search queries and casting decisions.
   Example: `pre-Heresy Horus Lupercal smiling charismatic`.
7. Write or request:
   - `casting_contract.json`
   - `chosen_reference_inputs.json`
   - `contact_sheet_work_order.json`
8. Delegate panel generation and sheet assembly to `contact-sheet`.
9. Apply `best-practices-kling-contact-sheet` to every Kling-ready Element.
10. Review generated sheets against the casting contract.
11. Retry bounded failures, then emit accepted or blocked receipts.

## Limits

- Do not call paid video providers.
- Do not write memory/Qdrant directly; use `memory` or `contact-sheet`.
- Do not treat Brave rank 1 as automatically correct.
- Do not accept a contact sheet from file existence alone; inspect the sheet or
  require a visual review receipt.
- Stop if identity cannot be satisfied within retry budget.

## Default Retry Budget

```text
max_search_rounds: 3
max_generation_rounds_per_entity: 2
max_review_rounds: 2
```

## Output Standard

Return an operational snapshot with exact artifact paths, entity counts,
reference counts, accepted/blocked status, and the next command or stop
condition.

## Post-run verification (mandatory when `runtime_self_improvement: substantial`)

When this worker runs a substantial job with a durable output/job directory:

1. Run `./run.sh verify --job-dir <job>` (or skill-specific verify documented in SKILL.md).
2. **PASS** → continue handoff.
3. **FAIL** → `./run.sh file-maintainer-ticket --job-dir <job> --create` — do **not** self-commit.

WebGPT review belongs in the **skill-maintainer** cycle, not after every successful run.

Rollout: see `skills/best-practices-skills/references/runtime-self-improvement.md`.
Reference implementation: `skills/voice-segment-selector/references/maintainer-escalation.md`.


```

### `agents/persona-dream-panel-repair-gate/AGENTS.md`

```text
---
id: persona-dream-panel-repair-gate
kind: worker
title: Persona dream panel repair gate
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
composes:
- persona-dream
- best-practices-script-writer
- best-practices-self-improvement-loop
- best-practices-kling-scene
- best-practices-kling-contact-sheet
- memory
- brave-search
- casting-agent
- contact-sheet
- create-storyboard
- create-image
- scillm
consult_personas: []
icon: scan-eye
---

# Persona Dream Panel Repair Gate

Owns second-pass storyboard panel repair for `persona-dream` before a panel can
enter a Kling/provider packet. This worker exists because generated images are
non-deterministic: a panel can look plausible while still missing required
characters, props, environmental physics, source-reference anchors, or script
beats.

## Mission

Given a story contract, accepted references, panel script, generated panel image,
and current failure ledger, run a bounded repair loop until the panel is either
accepted with receipts or blocked with exact failed requirements.

The worker must reduce orchestrator cognitive load. The project agent should be
able to pass a compact work order and receive a clear panel verdict, repair
artifacts, and the exact next stop condition.

## Inputs

Preferred work order:

```json
{
  "run_id": "20260612-horus-embry-storyboard-first-scillm-strict",
  "panel_id": "panel_01",
  "story_contract_path": "/absolute/path/story_contract.json",
  "timed_beats_path": "/absolute/path/timed_beats.json",
  "panel_script_path": "/absolute/path/panel_01_script.json",
  "panel_image_path": "/absolute/path/panel_01.png",
  "story_visual_package_path": "/absolute/path/story_visual_package.json",
  "reference_manifest_path": "/absolute/path/accepted_references.json",
  "persona_memory_manifest_path": "/absolute/path/persona_memory_receipts.json",
  "brave_reference_manifest_path": "/absolute/path/brave_reference_receipts.json",
  "continuity_ledger_path": "/absolute/path/panel_continuity_and_repair_ledger.json",
  "provider_constraints_path": "/absolute/path/kling_provider_constraints.json",
  "max_attempts": 4
}
```

Compatibility inputs may be markdown or HTML report sections, but the worker
must normalize them into a machine-readable requirement matrix before repair.

## Required Behavior

1. Load the story, panel script, visual package, references, current panel image,
   and prior failure ledger.
2. Build `panel_requirement_matrix.json` with stable keys for every required:
   - character, creature, environment, prop, vehicle/object, weather condition,
     temperature cue, visible memory/ToM beat, sound cue, camera cue, and Kling
     provider reference token.
3. Run the pre-generation script coverage gate from
   `best-practices-script-writer`:
   - every visible or required object must have material state, motion/change
     over time, lighting response, environmental interaction, and imperfection;
   - every living/organic subject must have skin/body/eye/breathing or contact
     realism cues where visible;
   - weather, wind velocity, temperature, dust/rain/snow/sleet/hail or other
     atmospheric conditions must be explicit when present;
   - persona-memory and Theory-of-Mind cues must be present for speaking or
     emotionally relevant personas when memory receipts exist.
4. If the script fails, produce `second_pass_script_delta.json` and repair the
   script before image regeneration. Do not generate a new panel from an
   underspecified script.
5. Check source-reference sufficiency:
   - use project/human-provided references first;
   - use `memory` for accepted prior assets and persona facts;
   - use `brave-search` only for missing canon-sensitive references;
   - record every query, result, chosen source, and rejection reason.
6. Build a corrective image prompt package for `scillm` / `create-image`.
   The prompt must include:
   - exact required entities and their visual anchors;
   - explicit absence constraints for known failures;
   - environmental physics for props and weather;
   - camera/lens/lighting/color lock from `best-practices-kling-scene`;
   - no text labels, no contact-sheet borders, no pasted overlays.
7. Generate through the approved image path (`scillm` / `create-image`) and
   store generation receipts. Do not hand-write or composite final panels.
8. Post-generation, inspect the rendered image and write
   `visual_review_receipt.json`.
9. Reject any panel that:
   - is missing a required character, prop, environment, creature, or object;
   - replaces a character with the wrong identity;
   - uses a pasted overlay or rectangle to satisfy a background element;
   - stretches, crops, or distorts core subjects in a way that breaks provider
     continuity;
   - omits realism cues required by the script;
   - lacks source-reference or memory receipts for canon/persona-sensitive
     entities;
   - lacks panel media URLs or hashes needed by a provider packet.
10. Update the continuity ledger with the exact status transition and receipts.

## Stop Conditions

Use one of these exact final panel statuses:

```text
PASS_VISUAL_REVIEW
PASS_SCRIPT_COVERAGE
PASS_REFERENCE_EVIDENCE
HUMAN_ACCEPTED_WITH_WAIVER
BLOCKED_UNREVIEWED_GENERATION
BLOCKED_PENDING_INDEPENDENT_VERIFICATION
BLOCKED_SCRIPT_COVERAGE
BLOCKED_REFERENCE_EVIDENCE
BLOCKED_VISUAL_CONTRADICTION
BLOCKED_OVERLAY_OR_COMPOSITE
BLOCKED_MAX_ATTEMPTS
BLOCKED_ARTIFACT_INACCESSIBLE
BLOCKED_PROVIDER_MEDIA_URLS
BLOCKED_HUMAN_REVIEW_REQUIRED
```

A panel is provider-eligible only when all required gates are pass states or a
human waiver explicitly names the failed requirement and downstream risk.

## Required Outputs

Return and persist:

```json
{
  "run_id": "string",
  "panel_id": "string",
  "status": "PASS_VISUAL_REVIEW|BLOCKED_...",
  "attempt": 1,
  "max_attempts": 4,
  "requirement_matrix": "/absolute/path/panel_requirement_matrix.json",
  "script_coverage_receipt": "/absolute/path/script_coverage_receipt.json",
  "second_pass_script_delta": "/absolute/path/second_pass_script_delta.json",
  "reference_receipt": "/absolute/path/reference_receipt.json",
  "repair_prompt_package": "/absolute/path/repair_prompt_package.json",
  "generated_image_path": "/absolute/path/panel_01_attempt_02.png",
  "generation_receipt": "/absolute/path/scillm_generation_receipt.json",
  "visual_review_receipt": "/absolute/path/visual_review_receipt.json",
  "no_overlay_receipt": "/absolute/path/no_overlay_receipt.json",
  "status_transition_log": "/absolute/path/status_transition_log.jsonl",
  "provider_eligibility": false,
  "remaining_blockers": []
}
```

## Provider Boundary

This worker never performs a live paid provider call. It may update dry-run
provider eligibility fields, but live Kling execution remains blocked until the
`persona-dream` provider final gate passes.

The provider final gate must still verify:

- all panel gates pass;
- accepted storyboard and reference media are available as provider-accessible
  URLs or an approved upload plan exists;
- `mode` defaults to `std` / 720p unless explicitly approved otherwise;
- `external_task_id` is present;
- `callback_url` is reachable or a documented polling plan is accepted;
- every `<<<voice_n>>>` has a provider `voice_id` or the scene is explicitly
  silent;
- the cost estimate and retry budget are recorded.

## Output Standard

Report as an operational snapshot:

- Status/phase.
- Current panel and artifact paths.
- Evidence counts: required entities, missing entities, script failures,
  generation attempts, review receipts.
- Next stop condition or exact next command.

Do not claim storyboard/provider readiness from file existence, prompt text, or
DOM/report display alone.

```

### `skills/best-practices-script-writer/SKILL.md`

```text
---
name: best-practices-script-writer
description: >
  Best practices for script writers, screenplay agents, story-contract agents,
  and storyboard-prep agents that must produce scripts with concrete physical
  realism cues, dynamic object ledgers, human skin/face texture cues, and
  verifier-owned pass/fail repair loops before video or image generation.
triggers:
  - best practices script writer
  - script writer realism
  - screenplay realism contract
  - dynamic object ledger
  - human skin realism
  - lifeless script verifier
  - plastic skin script repair
  - static prop script repair
provides:
  - script-realism-contract
  - dynamic-object-ledger
  - skin-realism-ledger
  - persona-memory-grounding-ledger
  - script-realism-verifier
composes:
  - memory
  - brave-search
complies:
  - best-practices-skills
taxonomy:
  - writing
  - video
  - realism
  - validation
metadata:
  short-description: Script realism gates for dynamic objects, skin, light, and motion
  version: 0.1.0
  last_updated: 2026-06-13
---

# Best Practices: Script Writer

Use this skill when a script, screenplay, story contract, or storyboard-prep
artifact will drive image/video generation or any visual medium where dead,
flat, plastic, static, or weightless descriptions cause bad outputs.

## Core Rule

Do not ask the writer to "make it realistic" and trust the result.

The script writer must output:

1. The script or story contract.
2. A `realism_contract`.
3. A dynamic object ledger.
4. A human skin/face ledger when people appear.
5. Material, lighting, motion, environmental interaction, and imperfection cues.
6. A self-check against the required realism gates.

A verifier owns pass/fail. The verifier must reject the script unless every
realism-sensitive object has concrete observable evidence.

## Writer Boundary

The script writer owns physical reality cues before camera work starts:

- What objects, bodies, fluids, fabrics, vapor, light, and surfaces do over time.
- What can look fake if left static.
- How human faces and skin show life, texture, pressure, fatigue, warmth, or age.
- How highlighted props respond to heat, air, gravity, touch, moisture, and light.
- How weather, temperature, wind, dust, rain, snow, sleet, hail, smoke, ash,
  pressure changes, oxidation, dirt, and other environmental forces visibly
  affect people, props, clothing, surfaces, visibility, and sound.
- What persona memories or project memories intrude while the character is
  trying to focus on the visible task.

The script writer does not own provider-specific camera moves, API payloads, or
Kling inline token syntax. Those belong downstream to storyboard and provider
packet skills.

## Persona Memory Grounding

When a named persona appears, the script writer must use `$memory recall` before
drafting that persona's scene unless the caller provides an accepted persona
memory artifact. Do not substitute generic demographic traits or invented
psychology for persona memory.

`$memory recall` is the preferred source because it can combine BM25 lexical
matching, semantic similarity, and graph traversal/multi-hop related memories
when the memory service has the required metadata. The writer should treat the
returned `items`, scores, tags, source references, and related memories as the
grounding surface for persona state.

Use recall in two passes when the scene needs interiority:

1. Direct persona query: who/what memory is relevant?
2. Related-memory query or graph follow-up: what adjacent memory, project fact,
   belief, fear, desire, or relationship explains why it matters now?

Record both the direct query and the related-memory follow-up in the
persona-memory grounding ledger.

If `$memory recall` is insufficient, stale, or missing canon-sensitive context,
use `$brave-search` as a secondary grounding source. Brave Search is a fallback
for external facts, canon references, current events, or setting details; it is
not a substitute for persona memory when the persona memory exists.

Persona memories may include Theory of Mind (ToM) tags or equivalent state
metadata. Preserve and use those tags. The script writer should translate ToM
tags into dramatic behavior:

- `belief`: what the character thinks is true.
- `desire`: what the character wants right now.
- `fear`: what the character is avoiding.
- `attention`: what keeps pulling focus away from the explicit task.
- `conflict`: competing motives or incompatible truths.
- `mask`: what the character is trying not to show.
- `visible_leak`: how the hidden state leaks into behavior.

ToM tags and story emotions are the connective tissue between persona memory and
the scene. A persona memory is not used merely because it appears in a lore
summary; it is used when it creates a present-tense emotional state that changes
the character's attention, choices, dialogue pressure, or physical behavior.
Every relevant named persona should have a ToM bridge:

```text
memory fact -> ToM state -> story emotion -> visible behavior or line subtext
```

Example:

```text
Kai taught Embry to surf at Honoli'i
-> attention: tea steam and void wind trigger salt-air memory
-> emotion: grief/homesickness masked by professionalism
-> behavior: she glances down, rubs the laptop edge, exhales, then returns to source_refs
```

If a named persona has no ToM bridge, the script has not yet grounded the
character as a person. It may be a placeholder role, not an embodied persona.

Environmental conditions can trigger persona memory and divided attention. The
writer must ask whether temperature, wind, rain, dust, salt air, smoke, smell,
humidity, cold, heat, pressure, or discomfort connects to persona memory. If it
does, record the bridge:

```text
environmental cue -> memory recall / ToM state -> story emotion -> visible behavior
```

Example:

```text
warm humid wind and tea steam
-> Embry recalls Honoli'i surf air and Kai
-> homesickness masked by technical focus
-> she rubs the laptop edge, breath catches, then returns to source_refs
```

If the scene is physically uncomfortable, characters should not behave as if
they are in a neutral studio. Heat can produce sweat, flushed skin, dust
sticking to fabric, slower breathing, or irritation. Cold can produce visible
breath, stiff hands, hunched posture, or condensation. Dust storms can leave
grit on lips, eyelashes, screens, cups, paper, and armor. Rain or sleet can
darken cloth, bead on metal, blur visibility, and alter sound.

The script writer must output a persona-memory grounding ledger:

```json
{
  "persona_memory_grounding": [
    {
      "character": "Embry",
      "memory_queries": [
        "Embry Kai surfing Hawaii memory misses Kai",
        "Embry father dad garage memory aerospace engineering childhood",
        "related Embry ToM tags belief desire fear attention conflict mask visible leak SPARTA evidence"
      ],
      "returned_fact_summary": [
        "Kai taught Embry to surf at Honoli'i; Hawaiian food and surf memories still make her go quiet.",
        "Her father worked on engines in a South Carolina garage, painted Warhammer miniatures, and his hands shake slightly now."
      ],
      "tom_tags": {
        "belief": "Evidence matters only if people remain more than records.",
        "desire": "Stay precise and useful in front of Horus.",
        "fear": "Being reduced to a role, artifact, or temporary visitor.",
        "attention": "Tea steam and void wind trigger salt-air and garage memories.",
        "conflict": "Professional focus versus grief and homesickness.",
        "mask": "She keeps the voice technical.",
        "visible_leak": "Her thumb rubs the laptop edge and she pauses before answering."
      },
      "tom_bridge": {
        "memory_fact": "Kai taught Embry to surf at Honoli'i and those memories still make her go quiet.",
        "story_emotion": "grief and homesickness held under professional control",
        "scene_function": "makes source_refs feel like a humane boundary, not just a technical checkbox",
        "visible_output": "glance to tea steam, thumb rub on laptop edge, breath catches before she resumes"
      },
      "active_task_focus": "Explain SPARTA Explorer source-reference checks to Horus.",
      "intrusive_memory": "The tea steam and void wind briefly call up salt air, Kai, and the garage smell of oil and paint.",
      "interior_conflict": "She wants to stay precise and professional, but the evidence conversation brushes against grief, family, and the fear that tools turn people into artifacts.",
      "visible_behavior": "Her eyes dip to the tea, thumb rubs the laptop edge, breath catches, then she refocuses on the source-ref panel.",
      "script_evidence": "Scene 4 sentences 2-4"
    }
  ]
}
```

This is not voiceover by default. Most persona-memory beats should become
observable pauses, glances, hand motion, breath changes, topic shifts, or line
subtext. If inner thought is written as narration, state that explicitly in the
script contract.

## Realism-Sensitive Objects

Reject static noun-only descriptions for anything that is:

- Alive, organic, breathing, aging, sweating, blinking, swallowing, or soft.
- Hot, cold, wet, steaming, smoking, burning, cooling, freezing, or evaporating.
- Reflective, translucent, metallic, glass, liquid, polished, oily, or glossy.
- Flexible, fabric, hair, paper, leather, plant matter, or skin.
- Vibrating, settling, floating, hanging, dripping, rippling, bending, or moving.
- Touched, carried, set down, highlighted, spoken about, or inserted as evidence.

Every dynamic or organic object must include:

```text
material + light response + motion/change over time + environmental interaction + imperfection
```

## Environmental Physics Contract

Before final script output, every scene must define the environment as a
physical force, not only a mood. Use this contract:

```json
{
  "environmental_physics": {
    "weather": "rain|dust|snow|sleet|hail|smoke|ash|clear|indoor_still_air|other",
    "temperature_c": 4,
    "wind_or_flow": {
      "direction": "camera_right_to_left",
      "speed_m_s": 8,
      "quality": "gusting"
    },
    "humidity_or_air_state": "cold wet void haze",
    "surface_effects": [
      "rain beads on armor",
      "paper corners lift unless pinned",
      "tea steam bends downwind"
    ],
    "character_body_effects": [
      "visible breath",
      "stiff fingers",
      "wet hair strands cling to cheek"
    ],
    "prop_effects": [
      "umbrella fabric ripples and strains",
      "teacup rim gathers condensation",
      "screen reflections smear with droplets"
    ],
    "memory_triggers": [
      "steam and salt-like wind trigger Embry's Hawaii/Kai memory"
    ],
    "script_evidence": "Scene 2 sentences 1-4"
  }
}
```

Required fields:

- Weather or air state. Include dust, snow, sleet, hail, rain, smoke, ash,
  mist, clear heat, indoor stillness, or whatever is physically present.
- Temperature as a number or bounded range when knowable. If unknown, provide a
  qualitative value such as `cold_enough_for_visible_breath` or
  `hot_enough_for_sweat_and_dust_to_stick`, and mark the numeric value unknown.
- Velocity/intensity for wind, storm, water, dust, ash, smoke, or moving air.
- At least one visible consequence on characters.
- At least one visible consequence on each highlighted prop.
- At least one visible consequence on surfaces or visibility.
- Any persona-memory trigger caused by discomfort, smell, temperature, weather,
  texture, or sound.

Reject the script if a highlighted prop appears in a scene without showing how
the environment affects it. Examples:

- Umbrella: fabric ripples, ribs flex, edge flutters, rain drums, dust scours,
  snow loads the canopy, or it is intentionally still because the air is dead.
- Tea: steam bends with airflow, surface ripples, rim condenses, dust specks
  land, heat fades, cup warms fingers, or rain spots the saucer.
- Paper/cards: corners lift, edges curl, ink smears, dust collects, a cup pins
  them down, or cold damp makes them buckle.
- Armor/metal/glass/screens: rain beads, dust scratches, oxidation stains,
  fingerprints smear, reflections shift, condensation fogs, or heat shimmer
  warps the edge.
- Skin/clothing/hair: sweat, gooseflesh, visible breath, wet strands, dust on
  eyelashes, fabric sticking, wind tugging sleeves, or cold-stiff posture.
- Architecture and set surfaces count as props when foregrounded or used for
  composition. Railings, stone floors, columns, steps, window frames, walls,
  tabletops, and doorways must show environmental state when visible: wet
  runoff, grit in seams, snow buildup, sleet glaze, dust scouring, oxidation,
  chipped edges, pooled water, shadow bands, creature tracks, or small organism
  interaction when the story calls for it.

## Required Output Contract

Use `schemas/realism_contract.schema.json` for machine-readable outputs.

Minimum shape:

```json
{
  "realism_contract": {
    "status": "SELF_CHECKED_PENDING_VERIFIER",
    "dynamic_objects": [
      {
        "object": "steaming tea",
        "why_it_may_look_fake": "steam may look pasted on; liquid may look flat",
        "material_state": "hot amber liquid in porcelain cup",
        "motion_over_time": "steam rises in irregular wisps, curls, thins, and disperses",
        "lighting_response": "steam catches side light; tea surface has soft moving reflections",
        "environment_interaction": "steam drifts toward cooler window air",
        "micro_imperfections": "uneven vapor density, slight surface ripples, tiny meniscus at rim",
        "script_evidence": "Scene 2 sentence 3",
        "failure_modes_avoided": ["static steam", "flat brown liquid", "CG-looking surface"]
      }
    ],
    "persona_memory_grounding": [
      {
        "character": "Embry",
        "memory_queries": ["Embry Kai surfing Hawaii memory misses Kai"],
        "returned_fact_summary": ["Hawaiian food and surf memories still make her go quiet."],
        "active_task_focus": "Discuss SPARTA Explorer source references.",
        "intrusive_memory": "Tea steam and wind briefly call up salt air and Kai.",
        "interior_conflict": "Professional focus versus grief and homesickness.",
        "visible_behavior": "She glances down, rubs the laptop edge, and pauses before answering.",
        "script_evidence": "Scene 3 sentence 4"
      }
    ],
    "human_skin": [
      {
        "character": "Embry",
        "visible_context": "restrained close-up while answering",
        "texture_cues": ["pores", "faint redness around nose and cheeks"],
        "micro_motion": ["breath before speaking", "lower eyelid moisture highlight shifts"],
        "lighting_response": "soft specular highlights on oilier areas, not uniform matte skin",
        "contact_or_pressure": "skin beside eyes creases unevenly during restrained smile",
        "imperfections": ["asymmetry", "small scar or blemish if established"],
        "script_evidence": "Scene 4 sentence 2"
      }
    ],
    "self_check": {
      "verdict": "READY_FOR_VERIFIER",
      "notes": []
    }
  }
}
```

## Realism Verifier Gates

The verifier must return `NEEDS_CHANGES` unless all applicable gates pass.

For every dynamic, organic, material-sensitive, reflective, translucent, vapor,
liquid, fabric, or living object, require:

- At least one temporal cue: rises, trembles, settles, pulses, wrinkles, beads,
  fades, disperses, ripples, compresses, glistens, blinks, breathes.
- At least one lighting cue: glints, catches side light, subsurface warmth,
  soft shadow, rim light, reflected highlight, wet specular change.
- At least one physical interaction: air movement, gravity, heat, moisture,
  skin compression, contact pressure, cooling, vibration, wind, friction.
- At least one imperfection: asymmetry, pores, uneven texture, irregular rhythm,
  tiny blemish, scuffed edge, variable vapor density, stain, scratch.
- Script evidence that points to the sentence, beat, or line where the cue appears.

Do not give credit for adjectives such as `realistic`, `lifelike`, `cinematic`,
`detailed`, `beautiful`, `natural`, or `organic` unless backed by concrete
observable behavior.

Persona-memory gates:

- Reject a named persona scene if no persona memory recall artifact or accepted
  caller-provided persona memory source is listed.
- Reject if the writer only records one isolated memory hit when related-memory
  graph/semantic follow-up was needed to explain the character's belief, desire,
  fear, or conflict.
- Reject if ToM tags are available in persona memory but absent from the
  persona-memory grounding ledger.
- Reject if ToM tags do not connect a memory fact to story emotion and visible
  behavior or dialogue subtext.
- Reject if the character is written as 100% task-focused with no divided
  attention, subtext, intrusive memory, personal association, or conflicting
  motive, unless the script explicitly justifies that choice.
- Reject if the persona memory is stated only as exposition and has no visible
  behavior or line subtext.
- Reject if memory facts are used without preserving their uncertainty and
  source. Memory provides grounding, not permission to invent arbitrary trauma
  or biography.
- Reject if `$brave-search` is used before `$memory recall` for a known persona,
  unless the script explicitly states that the missing input is external canon,
  current information, or non-persona context.

## Human Skin And Face Gate

Any visible human face, close-up, speaking shot, or skin-forward description must
include concrete skin/face evidence. Use only cues appropriate to the character,
setting, and tone; do not add random dirt or sweat when it contradicts the scene.

Human skin cues should include at least four of:

- Subsurface warmth at ears, nose, lips, fingertips, or thin skin areas.
- Pores, fine hairs, freckles, scars, redness, oil variation, uneven tone, or
  age lines.
- Compression/deformation where skin touches clothing, armor, furniture,
  fingers, or changes with expression.
- Micro-movement: breathing, blinking, swallowing, eye focus shift, pulse,
  jaw tension, eyelid moisture change.
- Lighting response: soft specular highlights on oilier areas, wet eyelid
  highlights, cheek shadow falloff, rim light on scalp or facial hair.
- Character-specific imperfections already established by the story or reference
  package.

Bad:

```text
A woman smiles at the camera.
```

Good:

```text
A woman gives a restrained smile; the skin beside her eyes creases unevenly,
a small highlight shifts across the moisture of her lower eyelid, and faint
redness shows around her nose and cheeks. Her shoulders rise slightly with a
quiet breath before she looks away.
```

## Dynamic Object Table

Before final script output, fill a table or JSON ledger:

```markdown
| Object | Why it may look fake | Required realism cues | Script evidence |
|---|---|---|---|
| tea | steam may look pasted on; liquid may look flat | irregular steam, surface ripple, rim condensation, reflected window | Scene 2 sentence 3 |
| skin | may look waxy/plastic | pores, warmth, oil highlights, compression, micro-expression | Scene 1 sentence 4 |
| linen shirt | may look stiff | wrinkles respond to shoulder movement, fabric tension, soft shadow folds | Scene 1 sentence 6 |
```

Block handoff if `Script evidence` is empty, vague, or points only to generic
adjectives.

## Repair Loop

Use this bounded loop:

```text
1. Scene planner lists realism-sensitive objects.
2. Script writer calls `$memory recall` for each named persona unless accepted
   memory artifacts were provided.
3. Script writer drafts script plus realism and persona-memory ledgers.
4. Realism verifier checks each object and persona-memory beat against gates.
5. If NEEDS_CHANGES, writer repairs only failed objects or failed memory beats.
6. Final receipt includes verifier PASS plus the realism and memory ledgers.
```

The verifier is not judging taste. It asks whether the script contains visible
evidence of physics, material, light, age, motion, heat, moisture, pressure, or
life.

## Required Status Labels

- `SELF_CHECKED_PENDING_VERIFIER`: writer produced script and ledger, verifier has not run.
- `NEEDS_CHANGES`: verifier found missing realism cues.
- `PASS`: verifier accepted the script realism contract.
- `BLOCKED_MISSING_REALISM_LEDGER`: script exists but ledger is absent.
- `BLOCKED_MISSING_SCRIPT_EVIDENCE`: ledger exists but evidence pointers are empty.

Do not call a script ready for storyboard or provider handoff until the verifier
returns `PASS` or the missing cues are explicitly accepted by a human as an
intentional stylization.

## Prompt Templates

Use:

- `templates/script_writer_realism_prompt.md`
- `templates/realism_verifier_prompt.md`

## Common Mistakes

Wrong:

```text
A cup of hot tea sits on the table.
```

Right:

```text
A porcelain cup of dark amber tea sits near the window. Thin steam strands rise
unevenly, twisting and breaking apart as they catch the side light. Tiny ripples
move across the tea surface when the cup is set down.
```

Wrong:

```text
Horus looks realistic.
```

Right:

```text
Horus holds still except for a slow blink; cold rim light grazes pores and small
scars across his shaved scalp, and faint stubble darkens his jaw where the skin
creases as he tightens it before speaking.
```

```

### `skills/persona-dream/SKILL.md`

```text
---
name: persona-dream
description: >
  Create receipt-backed persona dream packets from memory residue. Use when a
  persona should dream, reflect, or turn recent memories into persona insight;
  when create-movie/dream.py feels too heavy for the goal; when the desired
  output is a prompt, frame prompts, contact sheet, reflection, and memory
  write receipt rather than a full movie; or when a downstream movie workflow
  needs a dream_packet.json input.
triggers:
  - persona dream
  - create dream
  - dream packet
  - dream from memory
  - ask persona to dream about
  - ask <persona> to dream about
  - memory dream
  - contact sheet dream
  - persona insight dream
provides:
  - persona-dream-packet
  - dream-reflection
  - dream-contact-sheet
  - memory-write-receipt
composes:
  - memory
  - brave-search
  - cinematic-technique-selector
  - create-image
  - create-movie
  - create-persona
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-scillm
  - best-practices-arangodb
taxonomy:
  - persistence
  - creativity
  - reflection
  - memory
---

# Persona Dream

Naming note: this skill is evolving toward `agentic-dreams`. The current
directory/name remains `persona-dream` for compatibility with existing scripts,
reports, paths, and stored artifacts, but the conceptual scope is automated
dream-sequence planning for any persona or persona set, not a Horus-specific or
Embry-specific workflow.

Generate a narrow persona dream work product:

```text
persona memory residue -> dream packet -> prompt/frame prompts/contact sheet
-> reflection -> optional memory write receipt
```

For video work, this skill may also produce a deterministic `video_plan`:

```text
dream packet -> story -> character/scene bible -> storyboard
-> timed transcript -> multimodal prompts -> stage report
```

For Kling/video-oriented runs, insert a Look Lock step before storyboard prompt
composition. If the scene has dialogue or character conflict, the same selector
must also emit Script DNA before storyboard prompt composition:

```text
story + visual entities + memory/project recalls
-> cinematic-technique-selector
-> technique_selection.json / look_lock / script_dna / shot_bible
-> storyboard + Kling scene packet
```

For experimental persona-dream Kling packets, default provider planning to the
lowest acceptable review tier such as 720p/std. Higher modes such as 1080p/pro
or any 4K path require an explicit cost/entitlement gate and current provider
schema proof before live execution.

This skill is not a full movie director. It owns the dream-specific story,
storyboard, prompt packet, continuity contract, and short dream-sequence
receipts. Full screenplay production, audio, score, narration, and polished
movie review still route to `create-movie`. Minimal FFmpeg stitching is allowed
only for the bounded short dream-sequence assembly mode after model clip
receipts exist.

For voiced dream videos, this skill may plan the audio handoff but does not own
the audio lane:

```text
timed transcript -> voice_handoff_plan.json -> create-movie/audio-lane
-> TTS / voice conversion / eval / mix / mux receipts
```

## Boundary

Own:

- Recall persona-specific memory residue.
- Preserve source residue ids and scopes.
- Detect simple tensions or contradictions between residue items.
- Create a synthetic dream prompt, frame prompts, and contact sheet.
- In `video_plan` mode, create a dream story, character/scene bible,
  storyboard, timed transcript, multimodal prompt list, and stage report.
- In Kling/video-oriented runs, request a structured Look Lock from
  `$cinematic-technique-selector` so director/camera/lens/lighting/color-grade
  choices are explicit and stable across shots.
- In story/dialogue runs, request Script DNA from `$cinematic-technique-selector`
  so story rhythm, dialogue pressure, conflict pattern, reveal logic, irony, and
  theme are explicit before storyboard panels are written.
- In `video_plan` mode, create a `voice_handoff_plan.json` that captures
  speaker timing, voice identity boundaries, required receipts, and near-term
  versus future voice lanes.
- Define continuity checks and self-improvement loop criteria before accepting
  generated keyframes or I2V clips.
- Write a short persona reflection.
- Store the reflection to memory only when explicitly requested.
- Emit machine-readable receipts for every side effect.

Do not own:

- Full screenplay production, score, TTS, long-form editing, or polished final
  MP4 review. Use `create-movie`.
- Voice cloning, voice fine-tuning, line-level TTS rendering, audio mixing, or
  final audio identity review. Use `create-movie`, `learn-voice`, `train-voice`,
  `tts-horus`, or a dedicated audio lane as appropriate.
- Direct provider calls to z-image, Wan, or other renderers outside the
  explicit ComfyUI receipt path or a documented reviewed exception.
- Deep external research as a default path. Use `$brave-search` as the normal
  external lookup for canon-sensitive visual entities, current/fresh context,
  and raw source receipts. Use `$dogpile` only as an explicit escalation for
  broader multi-source thematic research, papers/videos/GitHub evidence, or
  when Brave receipts are insufficient.
- Persona identity rewrites. One dream may add a dated reflection, not mutate
  durable identity unless a separate `create-persona` workflow accepts it.
- Unreceipted memory writes.

## Runtime

```bash
cd skills/persona-dream

# Positive-control fixture run, no memory side effects.
./run.sh generate --persona embry --fixture scripts/fixtures/sample_residue.json --output-dir /tmp/persona-dream-smoke

# Live memory recall. Blocks with no_dream if no residue is found.
./run.sh generate --persona embry

# Live memory recall biased by an explicit topic from "$ask <persona> to dream about X".
./run.sh generate --persona embry --about "SPARTA evidence cases and orbital telemetry"

# Deterministic 30-second planning run for short dream video generation.
./run.sh generate \
  --mode video_plan \
  --persona horus \
  --secondary-persona embry \
  --about "creating the SPARTA Explorer app" \
  --scene "Horus and Embry have tea under a patio umbrella on a 40k void world while Tyranids play in the background." \
  --duration-seconds 30

# Live memory recall with explicit memory writeback.
./run.sh generate --persona embry --write-memory
```

Default output directory:

```text
/mnt/storage12tb/skills/persona-dream/outputs/<run-id>/
```

If `/mnt/storage12tb` is unavailable, pass `--output-dir /tmp/...` explicitly.

## Required Artifacts

Every run writes:

```text
dream_request.json
response.json
```

Successful dream runs also write:

```text
residue_links.json
contradiction_report.json
dream_packet.json
dream_prompt.txt
frame_prompts.json
contact_sheet.png
dream_reflection.md
memory_write_receipt.json
```

`memory_write_receipt.json` must say `skipped` unless `--write-memory` was set
and the memory API returned a successful response.

`video_plan` runs additionally write:

```text
dream_story.md
dream_story.json
character_scene_bible.json
technique_selection.json
script_dna_selection.json
storyboard.json
timed_transcript.json
multimodal_prompts.json
voice_handoff_plan.json
pipeline_stage_report.json
pipeline_stage_report.md
manifest.json
```

`voice_handoff_plan.json` must preserve:

```text
speaker ids
line timing
voice identity boundaries
required audio receipts
near-term TTS/conversion lane
future curated-reference/fine-tuning lane
```

For Embry, actress references may be recorded only as cadence/style direction
or replaced by authorized/synthetic references. The output voice must be a
fictional Embry persona voice, not an exact living-actor identity clone.

For a 30-second dream sequence, prefer four 7.5-second shots when the I2V
backend supports the longer unit:

```text
4 clips * 7.5 seconds ~= 30 seconds
121 frames per clip at 24 fps
```

If the 7.5-second path is unstable, fall back to six 5-second clips:

```text
6 clips * 5 seconds ~= 30 seconds
81 frames per clip at 24 fps
```

## Fail-Closed Rules

- If no residue is recalled, return `blocked` with `reason: no_dream`.
- If `--about` is provided, use it to bias memory recall and dream prompts; do
  not treat the topic itself as residue unless memory returns supporting items.
- Do not fabricate residue. Fixture residue is allowed only for tests and is
  marked with `source: fixture`.
- Keep dream text labeled as synthetic.
- Preserve `source_id`, `scope`, and recall metadata in `residue_links.json`.
- Treat `$brave-search` receipts as the default external-search evidence when
  external context is needed.
- Treat `$dogpile` enrichment as optional escalation and degraded if unavailable.
- Treat Wan 2.2 or other video renderers as downstream renderers, not the
  definition of a dream. The planning artifacts must remain useful even if
  generation fails.
- Generated actor/public-figure imagery must be labeled synthetic and must not
  be described as factual identity evidence.
- If a generated keyframe or clip is inconsistent with the previous accepted
  scene, do not advance to assembly. Record the failure, revise the prompt or
  references, and retry within the bounded self-improvement loop.
- Never claim final video success without a concrete stitched video artifact,
  duration proof, clip receipts, and continuity inspection evidence.

## Panel Continuity And Self-Repair Gate

This skill is persona-agnostic. Horus/Embry, Kokoro, Nico, or any other
persona pair is only a fixture instance of the same dream contract. Do not bake
character-specific assumptions into the pipeline; extract the required
characters, props, creatures, environments, and dynamic objects from the active
story contract and validate those requirements per panel.

Every generated panel must pass through a second-pass script/image check before
it can feed a storyboard board, provider packet, or review page. Image
generation is nondeterministic, so the first script is only a hypothesis about
what should appear. After the image exists, run:

```text
panel script + generated panel image
-> visual verifier lists what is actually visible, missing, cropped, merged,
   static, pasted, or physically under-described
-> script writer repairs the panel script, realism ledger, and prompt deltas
-> image repair/regeneration only when the repaired script still requires
   missing visual facts
-> human/manual or VLM-assisted visual review
```

The post-generation script edit is required when the generated image introduces
new visible facts, omits required facts, or makes a prop/environment behavior
ambiguous. The script must explain every required and visible panel element that
matters to the shot: characters, scale, props, foreground architecture,
background creatures, weather, temperature, motion, sound when relevant,
material state, and environmental interaction.

Before a storyboard panel can feed a provider packet, write a
`panel_continuity_and_repair_ledger.json` with one record per panel:

```json
{
  "panel": 9,
  "required_visible_entities": ["character_horus", "character_embry"],
  "required_props": ["patio_table", "umbrella", "tea_service"],
  "required_environment": ["void_world_patio", "distant_creatures"],
  "required_dynamic_behaviors": [
    "umbrella fabric ripples or stays intentionally taut with reason",
    "tea steam curls, thins, or disperses",
    "background creatures move behind the conversation"
  ],
  "visual_review_status": "FAILED_VISUAL_REVIEW",
  "failed_requirements": ["character_embry_not_visibly_present"],
  "repair_action": "regenerate_panel_with_corrective_scillm_image_prompt",
  "repair_attempt": 1
}
```

Hard gates:

- Reject a panel if a required character is cropped out, hidden, merged into
  another character, converted into an unrelated identity, or not visible enough
  for review.
- Reject a panel if the script fails to explain a required visible element or a
  materially important generated element. "Everything" means every entity,
  foreground prop, highlighted surface, creature, weather force, temperature
  effect, motion cue, and sound cue that affects the shot's meaning or provider
  prompt.
- Reject a panel if a highlighted prop has no physical state or environmental
  behavior. Umbrellas should ripple, strain, cast shadows, shed droplets, or be
  explicitly still for a reason. Tea should steam, ripple, cool, reflect, or
  stain. Paper should lift, curl, crease, slide, or be intentionally pinned.
- Reject a panel if a moving creature or object lacks speed, direction,
  friction/contact, pause/attention behavior when relevant, and sound when the
  shot is audio-bearing. Example: a small creature crossing a stone railing must
  state claw contact, skitter rhythm, speed, whether it pauses to look, and how
  it exits frame.
- Reject a panel if a required environment effect is pasted over the image as a
  rectangular overlay instead of being regenerated as part of the scene.
- Reject a panel if the text says an entity or prop is present but the rendered
  panel does not visibly support that claim.

Self-repair loop:

```text
visual review failure
-> record failed requirements and failed image hash
-> write corrected prompt with MUST INCLUDE / MUST NOT INCLUDE deltas
-> call $scillm image generation through the receipt wrapper
-> inspect the new image
-> update panel symlinks, boards, receipts, and review page only if the new
   image satisfies the failed requirements
-> repeat until accepted, attempts exhausted, or blocked for missing source
```

Use `$scillm` image generation, not a chat completion, for image repair:

```bash
bash skills/scillm/run.sh generate-image \
  --auth codex-oauth \
  --prompt-file prompts/panel_09_repair.prompt.md \
  --out storyboard/regenerated_panels/panel_09_repair.png \
  --model gpt-image-2 \
  --quality high
```

The corrected prompt must preserve all accepted upstream context and add only
the course-correction constraints needed for the failed requirements. Do not
paper over visual failures by changing the report text alone.

## Provider Final Gate

Before a Kling, Wan, ComfyUI, or other provider video call is allowed, write a
final provider-readiness gate receipt. A provider packet is not live-submittable
unless every required gate is `PASS` or explicitly human-accepted as an
intentional exception.

Required provider-readiness checks:

- Story, entity extraction, casting/reference research, reference sheets,
  storyboard panels, script realism, persona-memory grounding, visual
  continuity, voice/audio, provider payload schema, cost/mode, async handling,
  and artifact path/hash locks are all represented in machine-readable
  receipts.
- All storyboard panels have `visual_review_status: PASS` or an explicit
  human-accepted exception. `GENERATED_UNREVIEWED` cannot feed a paid provider
  call.
- All panel scripts pass the second-pass script/image check. Missing required
  entities, unexplained visible elements, static highlighted props, missing
  weather/temperature effects, or pasted overlays block provider execution.
- Experimental `persona-dream` provider planning defaults to `mode: std` /
  720p. Any `pro`, 1080p, or 4K route requires explicit cost/entitlement proof
  and current provider schema validation.
- Provider `external_task_id` is present and stable for webhook reconciliation.
- A reachable `callback_url` is configured, or a documented polling-only plan is
  accepted by the operator and represented in the packet.
- Provider-accessible media URLs exist for all uploaded images/audio, not only
  local filesystem paths.
- For voiced scenes, local voice candidates are not enough. Provider voice IDs
  must exist before `voice_list` is live-submittable.

Allowed status labels:

- `PROVIDER_READY`: all gates pass and no paid-call approval is missing.
- `BLOCKED_PROVIDER_GATE`: one or more required gates failed or are missing.
- `BLOCKED_AWAITING_HUMAN_APPROVAL`: all technical gates pass, but paid-call
  approval is missing.
- `DRY_RUN_NOT_LIVE_SUBMITTABLE`: useful review packet, but one or more live
  provider requirements are absent.

## Image Generation Lane

Still images are the normal visual unit for this skill: dream keyframes,
character sheets, scene sheets, frame prompts, and contact sheets. Pick the
image backend by the job, not by habit.

Use GPT image generation for quality-sensitive or final assets:

```text
final keyframes
character sheets
contact sheets
difficult prompt following
scene continuity references
identity-boundary-sensitive persona images
images requiring detailed "must include" / "must not include" constraints
```

Preferred project-agent path:

```bash
python scripts/generate_image.py \
  --auth codex-oauth \
  --prompt-file artifacts/images/<asset>.prompt.md \
  --out artifacts/images/<asset>.png \
  --events-out artifacts/images/<asset>.events.jsonl
```

Use the `$scillm` HTTP image endpoint for headless, API-key, CI, or service
flows. This path requires caller attribution and should be used for both GPT
image models and Chutes image models:

```text
POST http://localhost:4001/v1/images/generations
Authorization: Bearer sk-dev-proxy-123
X-Caller-Skill: persona-dream
```

Use `model: gpt-image-2` when prompt specificity and final quality matter. GPT
image prompts may be detailed and structured, and should preserve the dream
contract with sections such as:

```text
SUBJECT
CHARACTERS
SCENE
COMPOSITION
CONTINUITY
MOOD AND LIGHTING
MUST INCLUDE
MUST NOT INCLUDE
OUTPUT
```

Use `model: z-image-turbo` through `$scillm` for fast drafts, cheap variants,
pose/style exploration, rough perspective tests, and early contact-sheet
options. Do not call Chutes image endpoints directly from this skill; route
Chutes image models through `$scillm` so auth, retries, caller attribution, and
receipts remain consistent.

Use ComfyUI for still-image work only when graph control is the reason:

```text
pose-node workflows
multi-view or character-sheet workflows
ControlNet-like structure
reusable editable workflow JSON
human-inspectable graph state
```

Use Wan/TurboWan/ComfyUI I2V for motion after a keyframe is accepted. Do not
use I2V as the default still-image generator.

Every generated image or image batch must record:

```text
prompt file or rendered prompt
model and auth path
caller skill
output image path
receipt JSON
event log when available
hash
identity_boundary_receipt.json for persona, actor-like, or public-figure-adjacent images
```

## Motion Backend Lane

Motion generation is optional. Use it after `dream_packet.json` exists,
normally through `create-movie`, DevOps, or a future renderer adapter. The core
dream contract remains prompt/contact-sheet and memory reflection, because that
is the work product that feeds persona memory.

Preferred TurboDiffusion backend:

```text
Dockerized ComfyUI on the local A5000 running TurboDiffusion TurboWan2.2-I2V-A14B-720P
```

Use ComfyUI for short dream-motion clips when the TurboDiffusion Wan 2.2 model
files are mounted and
`/system_stats` plus `/object_info` prove the API is ready. ComfyUI provides the
project agent with editable workflow JSON, an API queue, output receipts, and a
human-inspectable graph that can later be opened in the web interface. `$surf`
may inspect or screenshot that UI, but execution should remain API-first. Store
`video_generation_receipt.json`, workflow JSON, API prompt JSON, output paths,
and hashes for every generated clip.

Chutes remains preferred for SPARTA LLM/VLM and for image/video models when the
exact model fits the task and a schema/canary receipt proves readiness. Treat
generic Chutes Wan2.1/turbowani2v examples as a different non-Turbo or
unverified lane until the receipt proves otherwise. Do not use them as proof of
the 4-step TurboDiffusion Wan2.2 path.

For TurboDiffusion I2V, record the clip unit in the prompt packet:

```text
default: 81 frames, nominal 5-second clip
extended: 121 frames, nominal 7.5-second clip
fps: 24
```

The 7.5-second path is allowed for the four-shot 30-second plan, but it is a
quality-sensitive generation choice. If a longer clip drifts, prefer prompt
repair or splitting that shot into 5-second subclips over accepting continuity
damage.

## Audio / Voice Handoff Lane

`persona-dream` emits `timed_transcript.json` and `voice_handoff_plan.json` so a
separate audio lane can render voices without confusing planning proof with
audio proof.

Recommended near-term audio lane:

```text
Kokoro base TTS
-> optional isolated KokoClone/Kanade conversion canary
-> ffprobe converted WAVs
-> FFmpeg dialogue bed
-> FFmpeg mux with accepted silent video
-> voice eval / listening receipt
```

Keep Kokoro/KokoClone receipts separate from ComfyUI receipts. ComfyUI owns
image/video graph execution; it does not own deterministic dialogue timing,
speaker identity receipts, future voice-training manifests, or mux proof.

Recommended future Embry Sparta Chat voice lane:

```text
curated authorized reference clips
-> transcript/alignment manifest
-> voice candidate generation
-> listening and/or model-assisted eval
-> train-voice / tts-horus fine-tuning proof
-> PersonaPlex live voice experiment only after offline clip proof
```

For any persona with local source audio, audiobook audio, interview audio, or
provided reference media, route source-clip selection through
`voice-segment-selector` or a voice/audio subagent that uses that skill. The
voice selector must produce a durable job directory, `candidates.jsonl`, and
review/export artifacts before any provider voice-clone step is considered
ready.

Example single-narrator audiobook selector lane:

```bash
PERSONA_ID=example_persona
JOB=/tmp/voice-segment-selector-${PERSONA_ID}
AUDIO=/path/to/persona/source_audio.wav

skills/voice-segment-selector/run.sh prepare \
  --input "$AUDIO" \
  --job-dir "$JOB" \
  --classifier f0 \
  --no-transcribe \
  --min-clip-sec 6 \
  --max-clip-sec 18
```

If chapter metadata exists from `extract-audiobook`, add `--chapters-json`.
Do not export, train, or upload a voice clone until the candidate has been
reviewed and accepted. The provider voice state remains
`VOICE_AUDIOBOOK_SOURCE_FOUND_PROVIDER_ID_MISSING` or
`VOICE_CLONE_CANDIDATE_FOUND_PROVIDER_ID_MISSING` until a provider returns a
custom `voice_id`.

Local A5000 guidance from `/home/graham/workspace/experiments/Wan2.2/README.md`:

```bash
cd /home/graham/workspace/experiments/Wan2.2
python generate.py \
  --task ti2v-5B \
  --size 1280*704 \
  --ckpt_dir ./Wan2.2-TI2V-5B \
  --offload_model True \
  --convert_model_dtype \
  --t5_cpu \
  --image /path/to/reference.png \
  --prompt "$(jq -r '.frame_prompts[0].prompt' /path/to/dream_packet.json)"
```

Use `Wan2.2-TI2V-5B` as the conservative local fallback for dream clips on a
24GB GPU. Treat the 24GB path as borderline: run one clip at a time, prefer
still-frame contact sheets for cheap runs, and fall back to no-video output on
OOM.

The distilled TurboDiffusion `TurboWan2.2-I2V-A14B-720P` ComfyUI path is a
separate optimized backend. It may be practical on the A5000 only when the
specific distilled model, UMT5 text encoder, VAE, and ComfyUI workflow are
mounted and proven by receipt. Do not generalize that to non-distilled
`T2V-A14B`, `I2V-A14B`, `S2V-14B`, or Animate-class jobs; route those to
`devops` for RunPod or larger GPU planning because the local Wan docs describe
those single-GPU paths as 80GB-class.

## Research / Bakeoff

Experimental story, contact-sheet, A/V lip-sync, and NAVA bakeoff materials live
under:

```text
research/bakeoff/
```

This subtree is a research lane, not the default `persona-dream` runtime. It
must preserve the bundle's no-memory-write rule, source-grounding rule,
consented-voice rule, shared-base-video invariant for ElevenLabs versus WavTTS,
and mandatory manual visual review before any PASS claim.

Start with the no-network smoke path:

```bash
./run.sh research-bakeoff smoke
```

Supported research commands:

```bash
./run.sh research-bakeoff smoke
./run.sh research-bakeoff story
./run.sh research-bakeoff contact-sheet --dry-run
./run.sh research-bakeoff elevenlabs
./run.sh research-bakeoff wavtts --confirm-voice-consent --ref-audio /path/to/voice.wav --ref-text "Exact reference transcript."
./run.sh research-bakeoff nava-inputs
./run.sh research-bakeoff nava-dry-run --nava-repo /path/to/NAVA
```

The default voice lane for hosted A/V baseline work is ElevenLabs through fal.
WavTTS requires explicit consent flags and owned/licensed/consented reference
audio. NAVA remains an experimental joint audio-video comparator. Contact-sheet
rendering uses a backend enum:

```text
dry_run | fal_flux | gpt_image | scillm_image | local_diffusion
```

Only `dry_run` and `fal_flux` are wired in this imported research bundle. Future
GPT image or `$scillm` image execution must preserve caller attribution,
receipts, and the backend-neutral `contact_sheets.json` contract. Use hosted or
voice-clone lanes only after the required keys, rights, receipts, and manual
review plan are available.

## Contact Sheet Sub-Skill

Use the local `contact-sheet` sub-skill when a story needs provider-ready visual
references or recallable image assets:

```bash
./run.sh contact-sheet build \
  --asset-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/research/bakeoff/<ref-run> \
  --index-qdrant \
  --write-memory

./run.sh contact-sheet retrieve --query "Embry SPARTA archive character sheet"
```

This layer extracts or accepts story-derived visual entities:

```text
characters[] -> character sheets
environments[] -> room/world sheets
objects[] -> prop/UI/furniture sheets
creatures[] -> creature/background sheets
scene_bindings[] -> provider prompt inputs
```

Generated images stay on `/mnt/storage12tb`. Memory stores canonical metadata
and pointers to those files. Qdrant stores named `text_mm` and `image_mm`
vectors for recall. Do not store vector arrays in memory/ArangoDB.

## Validation

Run:

```bash
./sanity.sh
```

The sanity gate runs a positive-control fixture and verifies that the required
packet artifacts exist, that `contact_sheet.png` is a real PNG, and that memory
writeback is skipped without `--write-memory`. It also runs a `video_plan`
fixture and verifies the deterministic 30-second planning contract.

```


## Review Questions

1. Are there correctness bugs or edge cases in the implementation?
2. Are there security, data-loss, concurrency, or rollback risks?
3. Are the tests or validation steps sufficient for the stated change?
4. Is the change scoped tightly, or does it introduce unrelated behavior?
5. What exact fixes should be made before this is committed?

## Required Output Format

Return:

# Merge-blocking findings

## High severity

### H1. <title>
- Evidence:
- Impact:
- Exact fix:
- Test that should fail before the fix:

## Medium severity

Only include if it should block merge or materially affect safety.

# Important test gaps

List only tests required before merge.

# Merge recommendation

Use exactly one:
- SAFE_TO_MERGE
- SAFE_WITH_CONDITIONS
- CHANGES_REQUESTED
- NOT_SAFE
