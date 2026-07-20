# Handoff Report: Persona Dream

**Timestamp:** 2026-07-20T17:10:00Z
**Active agent:** Codex
**Repository:** `grahama1970/agent-skills`
**Target branch:** `main`
**Latest implementation-proof commit before this handoff:** `e0998120f924de7c56a003baf0fb8d2da8919405`
**Skill root:** `skills/persona-dream`
**Current skill contract:** `SKILL.md`

## 1. Operating Model

The human's intent is agent-facing, not audience-facing: `persona-dream` should
prove that an agent can dream from memory residue and that each pipeline step
checks its inputs, outputs, lineage, and side-effect boundaries. The human does
not need to judge dream content for the core automation path.

Source-derived workflow:

1. **Initiating idea / request** — intended and partially implemented.
   The skill contract says Phase 01 must persist an explicit human idea and bind
   Phase 01-10 records to deterministic ids and canonical SHA-256 values.

2. **Live persona memory recall** — implemented for `generate`; now also
   independently checked by `check-live-memory-recall`.
   The non-fixture path calls Memory over Unix socket
   `/run/user/1000/embry/memory.sock`, endpoint `/recall`, then records recall
   receipts and normalized residue.

3. **Residue normalization and fail-closed no-dream gate** — implemented.
   `persona_dream.py generate` writes `response.json` and exits 3 with
   `status: blocked`, `reason: no_dream` when no usable residue exists.

4. **Static dream packet generation** — implemented.
   Successful runs write `residue_links.json`, `dream_packet.json`,
   `dream_prompt.txt`, `frame_prompts.json`, `contact_sheet.png`,
   `dream_reflection.md`, `memory_write_receipt.json`, `manifest.json`, and
   stage reports.

5. **No-write default** — implemented.
   `--no-write-memory` writes `memory_write_receipt.json` with
   `status: skipped`, `reason: write_memory_false`. Memory writeback remains
   explicit and must not be inferred.

6. **Video planning path** — implemented for deterministic planning only.
   `--mode video_plan` can emit story, character/scene bible, storyboard, timed
   transcript, multimodal prompts, voice handoff plan, and stage report.
   It does not prove provider execution.

7. **Revision qualification / provider readiness** — intended and represented
   by many existing gates, but not newly proven by the latest work.
   Existing contracts describe active revision qualification, Phase 11
   zero-call boundaries, failed historical canaries, and provider final gates.

8. **Generated image/video/audio lanes** — intended downstream lanes.
   Still images must go through receipt-backed image generation. Motion,
   voice, mux, Watch observation, interpretation, and persistence require their
   own receipts. No paid provider call is authorized by the current handoff.

9. **Cognitive loop / durable dream memory** — implemented historically for
   specific canonical runs, but not exercised by the new live-memory rung.
   Prior project knowledge records Phase 13-16 work and canonical dream memory
   writes. The latest proof does not rerun that full loop.

## 2. Current State

Recent commits relevant to this handoff:

- `e0998120f` — `persona-dream: add live memory recall check`
- `96accaaba` — `persona-dream: add pipeline robustness harness`
- `1b4d564cb` — prior handoff report for pilot execution / human gates

The two latest commits were pushed to `origin/main` and remote-ref verified at
the time of work.

The handoff helper required by the `/handoff` skill was not available in this
clean worktree:

```text
test -x .pi/skills/handoff/run.sh -> exit 1
```

This handoff was therefore produced by manual source inspection, recent commit
history, existing `HANDOFF.md` / `README.md` / `PROJECT_KNOWLEDGE.md`, and the
latest deterministic receipts.

## 3. What Is Working

### Offline Pipeline Robustness Harness

Command:

```bash
cd skills/persona-dream
./run.sh check-pipeline-robustness \
  --output-root /tmp/persona-dream-robustness-post-live-rung-20260720 \
  --json
```

Receipt:

```text
/tmp/persona-dream-robustness-post-live-rung-20260720/pipeline_robustness_receipt.v1.json
```

Observed summary:

```text
status: PASS_PERSONA_DREAM_PIPELINE_ROBUSTNESS
check_count: 14
passed_count: 14
failed_count: 0
mocked: false
live: false
fixture_backed: true
actual_provider_call_attempts: 0
```

This proves fixture-backed static/video planning, contract, lineage,
stale-write, respawn, run-state, run-root, provider-routing, FAL-preflight, and
spine-chain fixture families still execute under one deterministic harness. It
does not prove live memory recall or provider execution.

### Live Memory Recall Rung

New command:

```bash
cd skills/persona-dream
./run.sh check-live-memory-recall \
  --persona embry \
  --about "pipeline robustness autonomous dream residue" \
  --limit 6 \
  --run-id persona-dream-live-memory-r3 \
  --output-root /tmp/persona-dream-live-memory-r3-20260720 \
  --receipt-out /tmp/persona-dream-live-memory-r3-20260720/live_memory_recall_receipt.v1.json \
  --timeout-s 90 \
  --json
```

Receipt:

```text
/tmp/persona-dream-live-memory-r3-20260720/live_memory_recall_receipt.v1.json
```

Observed summary:

```text
status: PASS_LIVE_MEMORY_RECALL
mocked: false
live: true
fixture_backed: false
child_exit_code: 0
successful_query_count: 5
failed_query_count: 0
residue_count: 6
unique_source_count: 6
memory_write_status: skipped
actual_provider_call_attempts: 0
observed_blockers: []
```

The receipt checks:

- output root is fresh before execution;
- no fixture is used;
- five expected one-persona recall query receipts exist;
- query counts and accepted counts are internally consistent;
- each query receipt records `accepted_source_ids`,
  `accepted_source_ids_sha256`, and `accepted_normalized_count`;
- emitted residue `(scope, source_id)` pairs map back to accepted source ids in
  the live query receipts;
- no partial recall error is allowed for PASS;
- normalized residue has nonempty `source_id`, `scope`, and `text`;
- residue is non-synthetic and not fixture-marked;
- duplicate `(scope, source_id)` pairs are rejected;
- explicit persona ids must match requested persona aliases when present;
- `dream_packet.residue_items` equals `residue_links.items`;
- frame prompt source ids and contradiction refs resolve to residue source ids;
- stage-02 recall receipts agree with `residue_links.json`;
- every manifest artifact exists under the output root;
- writeback remains skipped under `--no-write-memory`;
- provider call count remains zero.

### Stale Output Boundary

Negative command reran `check-live-memory-recall` against the already populated
live output root and asserted the checker exits 1.

Receipt:

```text
/tmp/persona-dream-live-memory-r3-nonempty-20260720.json
```

Observed summary:

```text
status: BLOCKED_LIVE_MEMORY_INVARIANT
child_exit_code: null
errors: ["output_root_exists_nonempty"]
observed_blockers:
  - BLOCKED_LIVE_MEMORY_INVARIANT
  - output_root_exists_nonempty
```

This proves the checker does not silently reuse a nonempty output directory.

## 4. WebGPT / Browser Oracle State

Browser Oracle round 1 for project `dream` routed correctly:

```text
requested_tab_id: 837359230
controlled_tab_id: 837359230
controlled_tab_id_mismatch: false
tab_was_created: false
proof_status: response_proven
```

Round 1 advised the exact live-memory rung that was implemented:

- keep `check-pipeline-robustness` offline by default;
- add separate `check-live-memory-recall`;
- invoke the existing generator instead of duplicating recall logic;
- PASS only when live recall, non-fixture lineage, and no-write checks all pass;
- classify no-residue, unavailable memory, stale output, malformed artifacts,
  partial recall, duplicate residue, and writeback mismatch fail-closed.

Round 2 was submitted with the actual patch and receipts but failed as a
transport/reviewer artifact, not as local code evidence:

```text
GitHub issue: https://github.com/grahama1970/agent-skills/issues/481
raw WebGPT output: "Pro thinking"
proof_status: submitted_no_response_proof
failure: missing_sentinel
```

After the failed listen attempt, Browser Oracle reported the new bound tab as
stale:

```text
project: dream
tab_id: 837359738
readiness: needs_attention
issues: ["tab_stale_manual_binding"]
```

Next agent should repair/rebind Browser Oracle before further WebGPT use.

## 5. What Is Brittle

- `check-live-memory-recall` is live-state dependent. Memory ranking and
  contents are mutable, so do not compare semantic content to a golden fixture.
  Use source ids, scopes, hashes, query receipts, and lineage checks instead.
- The new checker proves accepted source-id attribution from live recall
  receipts into emitted residue, but not full raw `/recall` payload byte
  provenance.
- The checker currently treats duplicate `(scope, source_id)` pairs as a hard
  invariant failure. This is intentional; if the live fan-out returns duplicate
  records in the future, the generator should deduplicate or receipts should
  explain the duplicate rather than the checker normalizing it away.
- The offline aggregate harness is intentionally fixture-backed. Do not rename
  it or report it as live proof.
- `pytest` is not installed in the skill uv environment in the current clean
  worktree, so focused pytest was not rerun for the new script.
- `scripts/check_mock_evidence_claims.py` is absent from this `origin/main`
  worktree, so that CI-style wording checker could not be run.
- `README.md` still contains older proof-boundary prose from 2026-07-18/19 and
  does not yet describe the 2026-07-20 live-memory checker.

## 6. What Is Not Proven

- Semantic or psychological quality of dreams.
- That recalled memories were the best or most emotionally salient memories.
- Human preference or acceptance.
- Paid provider execution.
- Provider-ready storyboard or final video.
- Image, video, voice, lip-sync, mux, or Watch observation for the latest rung.
- Memory writeback durability for the latest rung.
- Complete live Phase 01-16 runtime execution.
- Repeatability against an unchanged Memory index.
- Independence from backend mocks not visible to this client.
- Full raw `/recall` payload byte provenance beyond accepted source ids.

## 7. Recommended Next Steps

1. **Repair Browser Oracle / WebGPT binding for `dream`.**
   Round 2 could not complete because the browser review did not return a
   sentinel and the binding is now stale. Do this before asking WebGPT for more
   project review.

2. **Add deterministic negative fixtures for the Gate 0 checker.**
   The live stale-output negative exists. Add fixture or monkeypatch-level tests
   for missing accepted source ids, bad source-id hash, partial query failure,
   duplicate residue, fixture marker leakage, persona mismatch,
   frame-source mismatch, and writeback mismatch. Keep them labeled as
   deterministic checker tests, not live proof.

3. **Reconcile README/current-state documentation.**
   Add a short 2026-07-20 proof-boundary note that distinguishes:
   offline fixture robustness, live Memory recall, historical Phase 13-16
   evidence, and unproven provider/audio/video lanes.

5. **Only then consider the next live rung.**
   Candidate next rung: live no-residue/unavailable-memory receipt proof using
   a controlled persona/query that returns no accepted residue or a controlled
   Memory outage. Do not fake this with mocked Memory and call it live.

## 8. Key Files

Core runtime:

```text
skills/persona-dream/SKILL.md
skills/persona-dream/README.md
skills/persona-dream/PROJECT_KNOWLEDGE.md
skills/persona-dream/run.sh
skills/persona-dream/scripts/persona_dream.py
```

Latest proof commands:

```text
skills/persona-dream/scripts/check_pipeline_robustness.py
skills/persona-dream/scripts/check_live_memory_recall.py
```

Important live proof artifacts from the latest session:

```text
/tmp/persona-dream-live-memory-r3-20260720/live_memory_recall_receipt.v1.json
/tmp/persona-dream-live-memory-r3-nonempty-20260720.json
/tmp/persona-dream-robustness-post-live-rung-20260720/pipeline_robustness_receipt.v1.json
/tmp/persona-dream-webgpt-round1-20260720-response.md
/tmp/persona-dream-webgpt-round1-20260720-response.meta.json
/tmp/persona-dream-webgpt-round2-20260720-response.receipt.json
```

## 9. Claim Boundary For Successor Agent

Use this phrasing:

```text
The 2026-07-20 live-memory rung exercised the live Memory /recall client path
without fixtures, produced six non-fixture residues, preserved residue lineage
into the dream packet, kept writeback skipped, and made zero provider calls.
```

Do not say:

```text
persona-dream is end-to-end complete
semantic dream quality is proven
provider readiness is proven
Phase 01-16 is live-proven by this rung
WebGPT verified the patch
```

WebGPT round 1 was useful advisory review. Round 2 failed to produce a
sentinel. The deterministic local receipts are the proof authority for the
latest commit.
