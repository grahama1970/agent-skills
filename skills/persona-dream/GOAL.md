# Persona Dream Immutable Goal

Last updated: 2026-07-17

## Immutable Goal

Produce a working Kling video from the `persona-dream` pipeline.

This is not complete until the pipeline has a returned/downloaded video artifact,
technical video proof, visual review artifacts, and memory persistence evidence
for every pipeline step listed below.

Minimum final evidence:

- Kling/provider submit receipt.
- Kling/provider poll or callback receipt.
- Downloaded MP4 or provider-returned video artifact.
- `ffprobe` receipt proving duration, codec, and readability.
- Frame contact sheet from the returned video.
- Post-Kling continuity review receipt.
- Final report that names what passed, what was mocked, what was live, and what
  remains unverified.
- Memory write and exact reread evidence for every pipeline step.

## Current Boundary

The active revision `rev_upstream_bf3b05d47fb8` crossed the live Kling boundary
once for repaired request
`sha256:ca90ba9fd76a1e2d682b326e65b18f5e8168d81bf829cb9e8c6a3db6779c840f`.
Provider request `019f70ac-3864-7d81-9e86-5fae6a676e0d` completed after 54
polls with no resubmit. The returned source MP4 passes technical validation and
the twelve-frame continuity review. The exact Kai line and ocean ambience are
post-muxed into the final MP4.

Current gate language:

```text
active repaired Kling request submitted: yes, exactly one provider call
active repaired Kling video returned: yes, 16,957,429-byte source MP4
active provider request id: 019f70ac-3864-7d81-9e86-5fae6a676e0d
active ffprobe: readable H.264, 10.041667 seconds
active frame contact sheet: 12 frames in a 4x3 PNG, sha256:9a97c5093d055f50a7b43eee9ad2ae48287f2416c2551e0becfe1442b70540a6
active continuity review: pass, including SB_004 commit action and visible lava-reef/safe-channel boundary
audio strategy: post_mux; Kling request intentionally has generate_audio=false
step 37 voice handoff: exact live Kai line rendered and hash-bound; ready for mux
step 38 final assembly: pass; muxed MP4 sha256:ec9da2af5b73ae4cff5df707341d83e59a90e6c56ef1197505ea68ae247d691a
audio proof: stream present, mean -32.6 dB, max -15.5 dB
pipeline-step Memory exact reread: 42/42, semantic sync 42/42, Qdrant pointers 42/42
revision persistence audit: pass, zero failed checks
agent evidence acceptance: pass
not proven: human subjective voice quality or lip synchronization
```

No agent may claim final, green, complete, fixed, or verified for this goal
unless those concrete artifacts exist and are cited.

## Memory Persistence Contract

Every step below must write a durable memory record through `$memory`.

Default collection:

```text
persona_dream_pipeline_steps
```

Default `_key` shape:

```text
persona_dream:<run_id>:<revision_id>:<step_no_padded>:<step_slug>
```

Each step record must include:

```text
schema
run_id
revision_id
step_no
step_slug
step_name
status
inputs
outputs
receipt_paths
artifact_hashes
request_hash when applicable
provider_task_id when applicable
memory_write_method: /store or /upsert
memory_write_receipt
exact_reread_receipt
semantic_sync_state when recallable
qdrant_collection and qdrant_point_id when recallable
claims.proves
claims.does_not_prove
blocker when blocked
observed_at
```

Rules:

- Use `$memory` `/store` for a single record and `/upsert` for batches.
- Do not write vector arrays into ArangoDB memory documents.
- Exact gates must reread by `_key` or exact `/list` filters, not only semantic
  recall.
- Semantic recall or Qdrant sync can support discoverability, but it does not
  replace exact reread proof.
- If a step is blocked, write the blocked record anyway with the concrete
  blocker and next required action.
- If an upstream revision changes, downstream memory records must be marked
  stale or superseded instead of being reused silently.

## Serial Pipeline Steps

Each row is a required pipeline step. The memory persistence column is
non-optional for every row.

| # | Pipeline step | Required artifact or receipt | Memory persistence requirement |
|---:|---|---|---|
| 01 | Request / Idea Intake | `dream_request.json`, idea/revision receipt, source seed | Store the exact human seed, normalized request, run id, revision id, and request hash. |
| 02 | Dreaming Persona Selection | persona selection receipt | Store selected persona ids, rejected/secondary personas, selection rationale, and scope tags. |
| 03 | Memory Recall | recall request/response receipt | Store question-shaped recall queries, collections, tags, returned keys, scores, and pass/fail scope check. |
| 04 | Residue Grounding | `residue_links.json`, `contradiction_report.json` | Store source residue ids, scopes, contradictions, missing evidence, and grounding status. |
| 05 | Dream Packet | `dream_packet.json`, `dream_prompt.txt` | Store packet hash, synthetic-content label, source residue links, and does-not-prove claims. |
| 06 | Story / Video Plan | `dream_story.md`, `dream_story.json`, `pipeline_stage_report.*` | Store accepted story/video plan hash, duration target, scene list, and acceptance status. |
| 07 | Producer Persona Selection | producer selection receipt | Store producer persona, authority boundary, decision scope, and invalidation impact. |
| 08 | Director Selection | director/DoP selection receipt | Store director/DoP selection, visual authority scope, and downstream artifacts invalidated by change. |
| 09 | Script Writer Selection | script-writer selection receipt | Store writer selection, script authority scope, and downstream artifacts invalidated by change. |
| 10 | Creative Authority Receipts | producer/director/writer authority receipt bundle | Store all creative authority ids, approvals, exceptions, and exact receipt hashes. |
| 11 | Look Lock | `technique_selection.json`, `look_lock.json`, `shot_bible.json` | Store camera, lens, lighting, color grade, movement grammar, continuity locks, and selector receipt hash. |
| 12 | Script DNA | `script_dna_selection.json` | Store story rhythm, dialogue pressure, conflict pattern, reveal logic, theme, and selector receipt hash. |
| 13 | Storyboard Prompt Composition | storyboard prompt files and prompt manifest | Store prompt inputs, accepted upstream hashes, rendered prompt hashes, and stale-check status. |
| 14 | Storyboard Panel Receipts | panel work orders, panel prompt receipts | Store one record per panel with panel id, prompt hash, required entities, and upstream revision hash. |
| 15 | Panel Continuity And Repair Ledger | `panel_continuity_and_repair_ledger.json` | Store required visible entities, props, environment, behaviors, failed requirements, and repair status. |
| 16 | Panel Generation Loop | generated panel images and image receipts | Store model/auth path, caller skill, prompt file, image path, image hash, and generation receipt. |
| 17 | Panel Visual Review Loop | visual review receipts | Store reviewer result, visible/missing entities, identity checks, overlay checks, and review evidence path. |
| 18 | Surgical Panel Repair | repair prompts, repair receipts, regenerated images | Store failed image hash, correction deltas, new image hash, attempts, and bounded-loop status. |
| 19 | Panel Repair Gate | `panel_repair_gate_receipt.json` | Store final panel status and all subgate results; only `PASS_PANEL_REVIEWED` can feed provider readiness. |
| 20 | Panel Source Receipt | `panel_source_receipt.json` | Store canonical panel source path, media hash, review status, and provider-eligible flag. |
| 21 | Provider Media Publication Work Order | publication work order receipt | Store target repo/path/url plan, source asset hash, authorization need, and proposed public URL. |
| 22 | Local Provider Media Staging | local staging receipt | Store staged file path, byte count, SHA-256, target path, and staging validation status. |
| 23 | Publication Preflight | publication preflight receipt | Store public-upload requirements, proposed URL, expected hash, and what remains unauthorized. |
| 24 | Publication Authorization | human authorization receipt | Store exact authorization text/hash, allowed action, excluded actions, spend/publication scope, and expiry. |
| 25 | Public URL Probe | URL probe receipt | Store fetched URL, HTTP status, byte count, content hash, MIME/type evidence, and parity result. |
| 26 | Provider Media Handoff | provider media handoff receipt | Store provider-accessible URLs, source hashes, element bindings, and fetchability status. |
| 27 | Provider Media Lock | provider media lock receipt | Store immutable URL/hash lock, element mapping, revision id, and stale-policy result. |
| 28 | Kling Scene Packet | `kling_scene_packet.json` or canonical live request | Store provider payload hash, multi-prompt fields, media URLs, timing, dialogue, and schema validation status. |
| 29 | Provider Final Gate | provider-readiness receipt | Store gate status, passed/failed checks, cost/mode/entitlement proof, and live-submit readiness flag. |
| 30 | Paid Call Authorization | paid-call authorization receipt | Store exact human authorization, max spend, provider request hash, attempt budget, and consumed/unused state. |
| 31 | Kling Submit | provider submit receipt | Store request hash, provider endpoint/model, external task id, provider task id, HTTP status, and raw response path. |
| 32 | Kling Poll / Callback | poll/callback event log | Store poll attempts, callback events, provider task status transitions, timestamps, and terminal state. |
| 33 | Output Retrieval | download/result receipt and returned video file | Store result URL, downloaded path, byte count, video hash, provider response hash, and retrieval status. |
| 34 | FFprobe / Technical Validation | `ffprobe.json`, technical validation receipt | Store duration, frame rate, codec, dimensions, stream readability, and pass/fail result. |
| 35 | Frame Contact Sheet | frame sheet image and receipt | Store sampled timestamps, frame sheet path, image hash, source video hash, and generation command. |
| 36 | Post-Kling Continuity Review | continuity review receipt | Store visual continuity verdict, identity/scene/action failures, screenshots/contact sheet path, and reviewer evidence. |
| 37 | Voice / Audio Handoff Lane When Voiced | `voice_handoff_plan.json`, voice receipts | Store speaker ids, voice ids or blockers, timing, consent/provenance, audio lane handoff, and voice status. |
| 38 | Final Assembly / Movie Lane | assembled MP4/mux receipts when needed | Store clip list, audio/video inputs, FFmpeg command, assembled output hash, and mux validation result. |
| 39 | Report Generation | final HTML/JSON report and validation receipt | Store report path, validation status, evidence index, mocked/live flags, and unresolved blocker list. |
| 40 | Gate Validation Loop | gate validation summary | Store all gate statuses, failed gates, blocked gates, stale gates, and the next critical-path command. |
| 41 | Upstream Revision Invalidation | invalidation ledger | Store changed upstream artifact, affected downstream records, stale markings, and regeneration requirements. |
| 42 | Final Acceptance Boundary | final acceptance receipt | Store final human/agent acceptance state, exact proof artifacts, and explicit `does_not_prove` exclusions. |

## Completion Rule

The goal is complete only when step 42 cites positive evidence from steps 31
through 36 for a real returned Kling video, plus memory persistence evidence
for steps 01 through 42.

For a voiced run, step 42 must also cite positive Step 37 and 38 evidence: an
exact transcript render, mix and FFmpeg mux receipts, a final MP4 audio stream,
and audible-output review. A silent provider return alone cannot satisfy the
immutable goal.

If any step lacks a memory write receipt and exact reread receipt, the goal is
not complete.

If any provider/Kling step is mocked, dry-run only, or blocked by missing
authorization, the goal is not complete.

If a report or dashboard says complete but the MP4, `ffprobe`, frame sheet,
continuity review, or memory receipts are missing, the report is wrong and must
be treated as a blocker, not as evidence.
