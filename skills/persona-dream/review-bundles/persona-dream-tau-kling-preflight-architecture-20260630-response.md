Yes — the architecture shape is coherent only if the ledger, not the HTML report, is the source of truth. A compact dashboard is acceptable as a view, but Kling must be gated by immutable step receipts, approved artifact hashes, upstream hash locks, explicit provider readiness, and human paid-call authorization.

I could verify the current persona-dream skill contract, including Look Lock / Script DNA before storyboard/Kling packet creation, explicit cost/entitlement gates for higher provider modes, and the boundary that persona-dream owns planning/receipts but not the full movie/audio lane. I could not verify the skills/persona-dream/pipeline/README.md seven-directory file in the current GitHub view, so I treat that seven-step compression as supplied local evidence, not as repository-confirmed.

1. Corrected preflight ledger step list

Use the seven directories only as implementation groupings. The human-facing ledger should expose these rows:

request_idea_intake — idea, constraints, duration, live/dry-run mode, voiced/unvoiced, provider tier.

dreaming_persona_selection — selected persona/personas and allowed memory scopes.

memory_recall — recalled memory records, queries, source ids.

residue_grounding — provenance, contradictions, “do not fabricate residue” gate.

dream_packet — approved dream packet.

story_video_plan — story outline and video plan.

character_object_environment_bible — JSON for all characters, objects, props, setting, environment.

producer_persona_selection — producer attached.

producer_creative_team_selection — producer-selected director and script writer.

creative_authority_receipts — producer/director/script-writer authority and scope receipts.

look_lock — stable director/camera/lens/lighting/color-grade choices.

script_dna — rhythm, dialogue pressure, conflict pattern, reveal logic, theme.

contact_sheet_requirements — matrix of required character/object/environment sheets.

character_contact_sheets — per-character contact sheets and reviews.

object_prop_environment_contact_sheets — per-object/prop/environment contact sheets and reviews.

voice_requirements — speaking-character matrix; may be NOT_APPLICABLE only with explicit unvoiced run contract.

orpheus_tts_voice_gate — per-speaking-character voice readiness, classifier/human-review receipts, or blocking gap.

complete_script — full script.

timed_transcript — speaker ids, timings, handoff constraints.

storyboard_prompt_composition — source-grounded storyboard prompt payload.

storyboard — complete storyboard JSON.

storyboard_panel_receipts — per-panel text/image intent receipts.

panel_generation_loop — generated panel artifacts and generator receipts.

panel_visual_review_loop — visual reviewer checks for identity, continuity, objects, environment.

panel_continuity_repair_ledger — failed checks, repair targets, iteration history.

surgical_panel_repair — repair artifacts when needed, otherwise explicit NOT_APPLICABLE.

panel_repair_gate — final panel set PASS gate.

panel_source_receipts — final source lineage for every accepted panel.

kling_payload_composition — complete panel-specific Kling-optimized JSON/text/image payloads.

provider_media_publication_work_order — what must be staged for provider access.

local_provider_media_staging — local media staged with hashes.

publication_preflight — media paths, MIME types, dimensions, access requirements.

publication_authorization — explicit permission to publish/stage assets.

public_url_probe — actual URL probe receipts; no assumed accessibility.

provider_media_handoff — provider-facing media bundle.

provider_media_lock — immutable provider media manifest.

kling_scene_packet — final provider packet.

provider_final_gate — current provider schema/entitlement/readiness proof.

paid_call_authorization — explicit human/cost authorization.

kling_submit — blocked until rows 1–39 are current PASS or valid NOT_APPLICABLE.

kling_poll_callback

kling_output_retrieval

ffprobe_technical_validation

frame_contact_sheet

post_kling_continuity_review

voice_audio_handoff_lane — required only when voiced; otherwise explicit NOT_APPLICABLE.

final_assembly_movie_lane

report_generation

gate_validation_loop

upstream_revision_invalidation

final_acceptance_boundary

The existing skill already defines core successful artifacts such as dream_packet.json, frame_prompts.json, contact_sheet.png, and video-plan artifacts including character_scene_bible.json, storyboard.json, timed_transcript.json, multimodal_prompts.json, voice_handoff_plan.json, and manifest.json. The ledger should therefore prove those artifacts, not merely mention them.

2. Minimal implementable ledger schema
JSON
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "persona_dream_tau_kling_preflight_ledger.v1",
  "type": "object",
  "required": [
    "schema_version",
    "run_id",
    "mode",
    "overall_status",
    "source_refs",
    "provider",
    "paid_call_authorization",
    "approved_manifest",
    "steps"
  ],
  "properties": {
    "schema_version": { "const": "persona_dream_tau_kling_preflight_ledger.v1" },
    "run_id": { "type": "string" },
    "mode": {
      "enum": [
        "dry_run",
        "preflight_only",
        "live_submit_attempted",
        "live_complete"
      ]
    },
    "overall_status": {
      "enum": [
        "PASS_PREFLIGHT",
        "DRY_RUN_NOT_LIVE_SUBMITTABLE",
        "BLOCKED_PROVIDER_GATE",
        "BLOCKED_AWAITING_HUMAN_APPROVAL",
        "BLOCKED",
        "STALE",
        "FAILED"
      ]
    },
    "source_refs": {
      "type": "object",
      "required": ["repo_ref", "skill_contract_refs"],
      "properties": {
        "repo_ref": { "type": "string" },
        "project_knowledge_hash": { "type": ["string", "null"] },
        "skill_contract_refs": {
          "type": "array",
          "items": { "$ref": "#/$defs/artifact_ref" }
        }
      }
    },
    "provider": {
      "type": "object",
      "required": ["name", "tier", "schema_proof", "live_ready"],
      "properties": {
        "name": { "type": "string" },
        "tier": { "type": "string" },
        "schema_proof": { "$ref": "#/$defs/artifact_ref" },
        "live_ready": { "type": "boolean" },
        "blocker": { "type": ["string", "null"] }
      }
    },
    "paid_call_authorization": {
      "type": "object",
      "required": ["status", "authorization_ref"],
      "properties": {
        "status": {
          "enum": ["AUTHORIZED", "MISSING", "EXPIRED", "NOT_REQUIRED_DRY_RUN"]
        },
        "authorization_ref": { "$ref": "#/$defs/artifact_ref_or_null" },
        "cost_ceiling": { "type": ["number", "null"] },
        "authorized_by": { "type": ["string", "null"] }
      }
    },
    "approved_manifest": {
      "type": "array",
      "items": { "$ref": "#/$defs/manifest_entry" }
    },
    "steps": {
      "type": "array",
      "items": { "$ref": "#/$defs/step" }
    }
  },
  "$defs": {
    "step": {
      "type": "object",
      "required": [
        "ordinal",
        "group_id",
        "step_id",
        "question",
        "phase",
        "status",
        "required_for_kling",
        "contract_ref",
        "upstream_hashes",
        "attempts",
        "approved_artifact",
        "blocks_kling"
      ],
      "properties": {
        "ordinal": { "type": "integer" },
        "group_id": { "type": "string" },
        "step_id": { "type": "string" },
        "question": { "type": "string" },
        "phase": {
          "enum": ["intake", "planning", "assets", "panels", "provider_preflight", "kling_live", "post_kling", "final"]
        },
        "status": {
          "enum": ["PASS", "REPAIR", "BLOCKED", "STALE", "MISSING", "NOT_APPLICABLE"]
        },
        "required_for_kling": { "type": "boolean" },
        "contract_ref": { "$ref": "#/$defs/artifact_ref" },
        "upstream_hashes": {
          "type": "object",
          "additionalProperties": { "type": "string" }
        },
        "attempts": {
          "type": "array",
          "items": { "$ref": "#/$defs/attempt" }
        },
        "approved_artifact": { "$ref": "#/$defs/artifact_ref_or_null" },
        "payload_refs": {
          "type": "array",
          "items": { "$ref": "#/$defs/artifact_ref" }
        },
        "failed_checks": {
          "type": "array",
          "items": { "type": "string" }
        },
        "repair_iteration": { "type": "integer" },
        "max_iterations": { "type": "integer" },
        "blocks_kling": { "type": "boolean" },
        "blocker": { "type": ["string", "null"] },
        "downstream_unlocked": { "type": "boolean" }
      }
    },
    "attempt": {
      "type": "object",
      "required": [
        "attempt_id",
        "creator",
        "reviewer",
        "artifact",
        "verdict",
        "created_at"
      ],
      "properties": {
        "attempt_id": { "type": "string" },
        "creator": { "$ref": "#/$defs/agent_receipt_ref" },
        "reviewer": { "$ref": "#/$defs/agent_receipt_ref" },
        "artifact": { "$ref": "#/$defs/artifact_ref_or_null" },
        "verdict": {
          "enum": ["PASS", "REPAIR", "BLOCKED", "STALE", "MISSING", "CREATOR_FAILED", "REVIEWER_FAILED"]
        },
        "created_at": { "type": "string" }
      }
    },
    "agent_receipt_ref": {
      "type": "object",
      "required": ["subagent", "run_id", "receipt_path", "receipt_sha256"],
      "properties": {
        "subagent": { "type": "string" },
        "run_id": { "type": "string" },
        "receipt_path": { "type": "string" },
        "receipt_sha256": { "type": "string" }
      }
    },
    "artifact_ref": {
      "type": "object",
      "required": ["path", "sha256", "media_type"],
      "properties": {
        "path": { "type": "string" },
        "sha256": { "type": "string" },
        "media_type": { "type": "string" },
        "public_url": { "type": ["string", "null"] },
        "probe_receipt": { "$ref": "#/$defs/artifact_ref_or_null" }
      }
    },
    "artifact_ref_or_null": {
      "anyOf": [
        { "$ref": "#/$defs/artifact_ref" },
        { "type": "null" }
      ]
    },
    "manifest_entry": {
      "type": "object",
      "required": ["step_id", "artifact", "reviewer_receipt_sha256", "upstream_hashes"],
      "properties": {
        "step_id": { "type": "string" },
        "artifact": { "$ref": "#/$defs/artifact_ref" },
        "reviewer_receipt_sha256": { "type": "string" },
        "upstream_hashes": {
          "type": "object",
          "additionalProperties": { "type": "string" }
        }
      }
    }
  }
}

The important correction to your proposed row is attempts[]. A single creator and reviewer field loses repair history. The report may show the latest attempt first, but the ledger must preserve every attempt.

3. Where Tau creator/reviewer receipts attach

Attach receipts at three levels:

Attempt level: every creator run writes a creator receipt before review starts. Every reviewer run writes a reviewer receipt against the exact artifact hash it reviewed.

Step level: the step stores all attempts, latest status, failed checks, blocker, and current upstream hash lock.

Manifest level: only a PASS reviewer can promote an artifact into the approved manifest. The manifest entry must include artifact hash, reviewer receipt hash, and upstream hashes.

The transaction order should be:

creator returns or fails
-> persist creator receipt
-> persist candidate artifact ref/hash if any
-> reviewer evaluates exact candidate hash
-> persist reviewer receipt
-> if PASS, atomically promote artifact to approved_manifest
-> recompute downstream stale locks
-> unlock next eligible step

Do not let the HTML report decide pass/fail. It should only render ledger, receipts, artifact previews, full text payloads, image payload refs, and blockers.

4. Architecture diagram nodes and edges

Render this in UX Lab as a Tau-controlled ledger pipeline, not as seven boxes.

Nodes
Human Request / Idea
Tau Orchestrator
Step Contract Registry
Source / Memory / Project Knowledge Snapshot
Immutable Receipt Store
Preflight Ledger
Approved Artifact Manifest
Staleness / Downstream Invalidation Engine
Creator Subagent Loop
Reviewer Subagent Loop
No-Omission Preflight Step Chain
UX Lab Report Renderer
Provider / Kling Boundary
Media Publication + URL Probe
Provider Final Gate
Paid Call Authorization
Kling Submit
Kling Poll / Callback
Kling Output Retrieval
FFprobe Technical Validation
Frame Contact Sheet
Post-Kling Continuity Review
Voice / Audio Handoff Lane
Final Assembly / Movie Lane
Final Acceptance Boundary
Edges
Human Request -> Tau Orchestrator
Tau Orchestrator -> Step Contract Registry
Tau Orchestrator -> Source / Memory / Project Knowledge Snapshot
Tau Orchestrator -> No-Omission Preflight Step Chain

For each step:
  Step Contract Registry -> Creator Subagent Loop
  Approved Artifact Manifest -> Creator Subagent Loop
  Creator Subagent Loop -> Immutable Receipt Store
  Creator Subagent Loop -> Reviewer Subagent Loop
  Reviewer Subagent Loop -> Immutable Receipt Store
  Reviewer Subagent Loop -- PASS --> Approved Artifact Manifest
  Reviewer Subagent Loop -- REPAIR --> Creator Subagent Loop
  Reviewer Subagent Loop -- BLOCKED/STALE/MISSING --> Staleness / Downstream Invalidation Engine
  Staleness / Downstream Invalidation Engine -> Preflight Ledger

Approved Artifact Manifest -> Provider / Kling Boundary
Provider / Kling Boundary -> Media Publication + URL Probe
Media Publication + URL Probe -> Provider Final Gate
Provider Final Gate -> Paid Call Authorization
Paid Call Authorization -> Kling Submit
Kling Submit -> Kling Poll / Callback
Kling Poll / Callback -> Kling Output Retrieval
Kling Output Retrieval -> FFprobe Technical Validation
FFprobe Technical Validation -> Frame Contact Sheet
Frame Contact Sheet -> Post-Kling Continuity Review
Post-Kling Continuity Review -> Voice / Audio Handoff Lane
Voice / Audio Handoff Lane -> Final Assembly / Movie Lane
Final Assembly / Movie Lane -> Final Acceptance Boundary

Preflight Ledger -> UX Lab Report Renderer
Immutable Receipt Store -> UX Lab Report Renderer
Approved Artifact Manifest -> UX Lab Report Renderer

Visually, show the seven directories as swimlanes only:

s01_idea     = rows 1–5
s02_memories = rows 2–5, if implemented separately
s03_story    = rows 6–12, 18–21
s04_voice    = rows 16–17, 46
s05_panels   = rows 13–28
s06_gate     = rows 29–39, 49–50
s07_movie    = rows 40–48, 51
5. What must block Kling even if a later artifact exists

Kling must stay blocked if any of these are true:

A required upstream row is MISSING, BLOCKED, REPAIR, or STALE.

A later artifact exists but was not promoted through a PASS reviewer receipt.

Artifact hash does not match the approved manifest.

Reviewer receipt reviewed a different artifact hash than the promoted artifact.

Upstream source, memory residue, Look Lock, Script DNA, storyboard, contact sheet, panel, or provider packet hash changed after downstream approval.

Full Kling text/image/JSON payloads are missing from the ledger/report.

Contact sheets are absent, incomplete, or unreviewed.

Panel continuity repair ledger has unresolved failed checks.

A voice run is marked voiced but any speaking character lacks a current voice/Orpheus/audio handoff gate.

Public media staging exists but URL probe failed or was not run.

Provider schema proof is missing, stale, or for a different provider/tier.

Higher-cost provider mode is requested without explicit cost/entitlement authorization; the skill contract explicitly requires this for higher modes.

Paid-call authorization is missing, expired, too broad, or not bound to this exact scene packet hash.

The run is marked dry-run. It must say DRY_RUN_NOT_LIVE_SUBMITTABLE, not imply readiness.

The report exists but ledger validation fails.

The provider media lock is missing, meaning the submitted URLs/assets could differ from reviewed assets.

6. Source-derived / not-mocked implementation constraints

Source-derived:

Pipeline contracts must be read from the skill contract, project knowledge, and any local pipeline contract files.

Memory recall must preserve source residue ids and scopes. Project knowledge says persona-dream consumes memory residue and must not fabricate source residue or mutate durable persona identity.

Look Lock and Script DNA must precede storyboard/Kling scene packet work for Kling/video-oriented runs.

Voice work must be represented as a handoff lane; persona-dream may plan it but does not own voice cloning, line-level TTS rendering, audio mixing, or final audio identity review.

Must not be mocked:

Tau creator/reviewer receipts.

Artifact hashes.

Memory recall/residue ids.

Contact sheets and panel image artifacts.

Reviewer failed checks.

Public URL probes.

Provider schema proof.

Paid-call authorization.

Kling response rows, if claiming live execution.

Fixtures are fine only if the ledger says dry_run and the final state remains DRY_RUN_NOT_LIVE_SUBMITTABLE.

7. Red flags in the proposed while-loop

The loop shape is right, but it needs hardening:

Persist the creator receipt before reviewer execution. Otherwise a reviewer crash can erase proof of a creator attempt.

while step.verdict != "PASS" must have max iterations, stop conditions, and explicit CREATOR_FAILED / REVIEWER_FAILED handling.

step.verdict should be derived from the ledger, not mutable in-memory state.

unlock_next_step must be atomic with manifest promotion and stale-check recomputation.

REPAIR must include exact failed checks and repair scope, not just “try again.”

Reviewers must be read-only; they should not mutate artifacts.

Human paid-call authorization is not a reviewer verdict. It is a separate signed approval bound to cost, provider tier, payload hash, and expiration.

STALE should be generated by upstream hash comparison, not only by reviewer opinion.

The report must never collapse attempts into a single “latest status” without exposing the receipt chain.

Bottom line: this is a coherent fail-closed architecture if the durable ledger is granular, append-only, hash-bound, and rendered fully. It is not coherent if the seven directories or a compact HTML report become the apparent gate.
