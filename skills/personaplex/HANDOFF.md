# Handoff Report: Agent Skills / PersonaPlex Create-Architecture Work

**Timestamp**: 2026-06-23T13:15:25-04:00
**Active Agent**: Codex

## 1. Project Overview

- **Ecosystem**: Python skill repository with shell wrappers, local HTML review artifacts, WebGPT/SUrf browser automation, and deterministic sanity scripts.
- **Core Purpose**: `/home/graham/workspace/experiments/agent-skills` is the canonical source for reusable agent skills, hooks, and supporting artifacts. The active work is in `skills/personaplex` and `create-architecture/*`, where WebGPT creates solution zip bundles and the project agent ports/tests/light-fixes them.
- **Current collaboration rule**: For greenfield/architecture-heavy PersonaPlex work, the project agent must not freelance the design. Use `$create-architecture` to send a concrete GOAL/HANDOFF/evidence bundle to WebGPT, require a downloadable zip, port it mechanically, run local proof, update the HTML progress page, then create the next gap report.

## 2. Current State (Doc-Code Alignment)

- **Documented Features**:
  - `skills/personaplex/SKILL.md` describes PersonaPlex voice prompt generation, native `.pt` cache creation, offline E2E verification, and live conversation readiness boundaries.
  - `skills/create-architecture/SKILL.md` now governs the WebGPT creation loop: GOAL/HANDOFF docs, downloadable solution zip, project-agent port/test/light-fix role, prompt improvements, and per-round HTML/CSS progress reporting.
  - `reviews/personaplex-deepgram/compliance-memory-decision-tree.html` is the primary visible progress report for the PersonaPlex compliance-memory routing work.
- **Implemented Reality**:
  - P0/P1/P2 deterministic/control-plane slices have been ported into `skills/personaplex`.
  - P3-P5 combined slice has been ported into `skills/personaplex` from a WebGPT zip and locally sanity checked.
  - The current implementation proves deterministic fallback receipts, latest-turn stale fencing, output gate data-stop behavior, canonical local conversation history fallback records, no inline vectors, and fail-closed clarify behavior when evidence is unavailable.
- **Drift/Misalignments**:
  - The HTML report clearly marks real Deepgram, real GPU PersonaPlex, live `$memory /upsert`, and live `create-evidence-case` as missing or partial. Do not claim those are proven.
  - The repository is heavily dirty from broad unrelated work. Treat unrelated changes as user/workspace state; do not revert.
  - `skills/handoff/SKILL.md` says to run `.pi/skills/handoff/run.sh`, but this checkout only had `skills/handoff/run.sh`; that local script was run instead.
  - Some `skills/personaplex/scripts/__pycache__` and `tests/__pycache__` files exist locally from test execution. The P3-P5 WebGPT zip also contained bytecode artifacts; they were not intentionally ported as source.

## 3. What is Working Well

- **P3-P5 WebGPT solution zip**:
  - Downloaded file: `create-architecture/P3-P5-live-websocket-memory-evidence-combined/20260623T170047Z/personaplex-p3-p5-live-websocket-memory-evidence-combined-solution.zip`
  - SHA-256: `46f9caa2153bfdbe5ea01ced76bb56b02c6afc567f6859e3f61bbef88df05fce`
  - `MANIFEST.json.bundle_filename` matched the zip name.
- **Ported P3-P5 files**:
  - `skills/personaplex/docs/p3_p5_receipt_schema.json`
  - `skills/personaplex/fixtures/p3_p5_two_turn_fixture.json`
  - `skills/personaplex/sanity_p3_p5_live_websocket_memory_evidence_combined.sh`
  - `skills/personaplex/scripts/personaplex_p3_p5_combined_probe.py`
  - `skills/personaplex/scripts/personaplex_p3_p5_live_services.py`
  - `skills/personaplex/tests/test_p3_p5_live_websocket_memory_evidence_combined.py`
- **Local proof already captured**:
  - `python3 -m py_compile ...` for P3-P5 scripts/tests exited `0`.
  - Focused P3-P5 tests: `Ran 6 tests`, `OK`.
  - P3-P5 sanity script: `p3-p5 combined sanity ok`.
  - Combined PersonaPlex test discovery: `Ran 26 tests`, `OK`.
  - Final receipt: `/tmp/personaplex-p3-p5-combined-sanity/p3-p5-final-receipt.json`.
- **Receipt anchors**:
  - `ok=true`
  - `turn_count=2`
  - `active_turn_id=2`
  - `sealed_turn_keys=["conversation:p3p5-session:000002"]`
  - `stale_rejection_count=1`
  - `queue_depth_at_release=0`
  - `live_websocket=false`
  - `real_deepgram=false`
  - `real_gpu_personaplex=false`
  - `real_memory_upsert=false`
  - `real_create_evidence_case=false`
- **HTML/UI progress proof**:
  - Updated file: `reviews/personaplex-deepgram/compliance-memory-decision-tree.html`
  - Fresh UI marker: `.codex/ui-verification/latest.json`
  - Screenshot: `/tmp/codex-ui-verification/agent-skills/personaplex-compliance-memory-decision-tree-p3-p5-section/20260623T171228Z.png`
  - Visual inspection confirmed the page shows the P3-P5 section, zip SHA, manifest contract, `Ran 6 tests`, `p3-p5 combined sanity ok`, and `Ran 26 tests, OK`.

## 4. What is Currently Broken

- **Failed Tests**:
  - No targeted PersonaPlex tests failed in the last run. Combined discovery returned `Ran 26 tests`, `OK`.
- **Known Issues**:
  - Real Deepgram ASR/VAD is not proven. Current receipt explicitly says `deepgram_mode=deterministic_transcript_fixture` and `real_deepgram=false`.
  - Real GPU PersonaPlex/Moshi inference is not proven. Current receipt says `real_gpu_personaplex=false`.
  - Real `$memory /upsert` is not proven. Current receipt says `attempted=false`, `real_memory_upsert=false`, `unavailable_reason=memory_url_not_configured`.
  - Real `create-evidence-case` is not proven. Current receipt says `attempted=false`, `real_create_evidence_case=false`, and routes to `/memory /clarify`.
  - Conversation compaction remains a follow-on. Rolling summaries, immutable source turn retention, graph/vector lifecycle, and CAS session-head updates are not implemented in P3-P5.
  - The P3-P5 zip included generated `__pycache__` files. Treat this as a packaging hygiene issue for future WebGPT requests; source files remain usable.
- **Recent Regressions**:
  - No PersonaPlex regression was observed after P3-P5 port; combined P0-P5 test discovery passed.
  - Earlier process regression: the project agent repeatedly stopped early and treated architecture/review artifacts as enough. The corrected workflow is now documented in this handoff and in the HTML report.

## 5. Next Steps

1. **Do endpoint discovery before the next WebGPT creation round**:
   - Identify actual `$memory /upsert` URL/body contract.
   - Identify actual `create-evidence-case` transport: HTTP endpoint, skill CLI, or memory route.
   - Identify how to run live PersonaPlex WebSocket/Deepgram proof without conflating fixture transcript proof with real `speech_final=true`.
2. **Run the next `$create-architecture` round for one real-service target**:
   - Recommended first slice: `P6-real-memory-upsert-transport`, because P3-P5 already has a configurable memory adapter and local fallback receipts.
   - Alternate slice: `P7-real-evidence-case-transport`, if the endpoint/skill contract is easier to discover.
   - More expensive slice: `P8-live-deepgram-websocket-proof`, requiring real WebSocket/server facts and `DEEPGRAM_API_KEY` from `~/.zshrc`.
3. **For the WebGPT request, include these artifacts**:
   - `reviews/personaplex-deepgram/compliance-memory-decision-tree.html`
   - `create-architecture/P3-P5-live-websocket-memory-evidence-combined/20260623T170047Z/sanity-report.md`
   - `create-architecture/P3-P5-live-websocket-memory-evidence-combined/20260623T170047Z/gap-report.md`
   - `/tmp/personaplex-p3-p5-combined-sanity/p3-p5-final-receipt.json`
   - Relevant source files from `skills/personaplex/scripts/`
4. **Require a zip, not prose**:
   - WebGPT must return a downloadable finished-file zip.
   - The zip must include `MANIFEST.json.bundle_filename` matching the zip filename.
   - If WebGPT returns `CONTINUE_FOR_PART_2` or prose-only, treat that as not enough and continue the creation loop.
5. **After each round**:
   - Download the zip from the same controlled WebGPT tab.
   - Verify SHA, manifest, and unzip.
   - Port mechanically; do only light bug fixes needed to run.
   - Run focused tests and sanity.
   - Update `reviews/personaplex-deepgram/compliance-memory-decision-tree.html`.
   - Run `~/.codex/hooks/verify-ui-cdp.sh --url <updated-url> --name <surface>` and refresh `.codex/ui-verification/latest.json`.
   - Write or update slice `sanity-report.md`, `gap-report.md`, and `HANDOFF.md`.

## 6. Project Context for Success

- **Key Files**:
  - `skills/create-architecture/SKILL.md` - operational contract for WebGPT creation loops.
  - `skills/surf/SKILL.md` - WebGPT tab preflight, submit, extract, downloadable zip capture, and screenshot rules.
  - `skills/personaplex/SKILL.md` - PersonaPlex project boundary and proof claims.
  - `skills/personaplex/scripts/personaplex_golden_state_server.py` - live server/callsite integration surface.
  - `skills/personaplex/scripts/personaplex_p2_server_callsite.py` - P2 callsite wrapper.
  - `skills/personaplex/scripts/personaplex_p3_p5_combined_probe.py` - P3-P5 combined probe entrypoint.
  - `skills/personaplex/scripts/personaplex_p3_p5_live_services.py` - P3-P5 HTTP/live-service adapter helpers.
  - `skills/personaplex/tests/test_p3_p5_live_websocket_memory_evidence_combined.py` - P3-P5 focused tests.
  - `reviews/personaplex-deepgram/compliance-memory-decision-tree.html` - primary visible progress report.
  - `create-architecture/P3-P5-live-websocket-memory-evidence-combined/20260623T170047Z/` - current slice artifact directory.
- **Recent Changes**:
  - P3-P5 WebGPT zip downloaded from controlled tab `837354889`.
  - Six P3-P5 source/test/doc files ported into `skills/personaplex`.
  - HTML progress report updated with P3-P5 status and missing real-service flags.
  - UI verification marker regenerated at `.codex/ui-verification/latest.json`.
  - Slice artifacts written: `sanity-report.md`, `gap-report.md`, appended `HANDOFF.md`.
- **Recent Commits From Repository History**:
  - `294d2a6e5 Update Orpheus trainer takeover knowledge`
  - `c8fbc663b Add Orpheus TTS voice trainer skill`
  - `ec96f065f Add bounded researcher retry contract`
  - `6a9c9c453 Add Embry Orpheus SFX review candidates`
  - `3341b74cc Catalog Orpheus yawn SFX candidates`
- **Git Worktree Warning**:
  - The broader repo has many unrelated modifications and deletions.
  - Do not run destructive git commands.
  - Use path-scoped diffs/status for `skills/personaplex`, `reviews/personaplex-deepgram`, `create-architecture/P3-P5-live-websocket-memory-evidence-combined/20260623T170047Z`, `.codex/ui-verification/latest.json`, and `local/HANDOFF.md`.

## 7. Exact Commands Worth Reusing

```bash
PYTHONPATH="$PWD/skills/personaplex/scripts:$PWD/skills/personaplex/scripts/_p2_compat:${PYTHONPATH:-}" \
  python3 -m unittest discover -s skills/personaplex/tests -v
```

```bash
bash skills/personaplex/sanity_p3_p5_live_websocket_memory_evidence_combined.sh
```

```bash
jq . /tmp/personaplex-p3-p5-combined-sanity/p3-p5-final-receipt.json
```

```bash
~/.codex/hooks/verify-ui-cdp.sh \
  --url 'http://127.0.0.1:8771/reviews/personaplex-deepgram/compliance-memory-decision-tree.html?v=p3p5-20260623T1711#p3-p5-progress-title' \
  --name 'personaplex-compliance-memory-decision-tree-p3-p5-section'
```

## 8. Current Stop Condition

This handoff is current through the P3-P5 deterministic fallback checkpoint. The next agent should not claim live readiness until at least one future receipt records a corresponding real-service flag as `true` from an actual endpoint/WebSocket/GPU run.
