# Issue 1040 Branch Triage Proof

## Scope

Ticket: https://github.com/grahama1970/agent-skills/issues/1040

Repository: `/home/graham/workspace/experiments/agent-skills`

Branch policy applied: Battle work source of truth is `agent-skills@main`; `battle-adaptive-lineage-goal` is not a continuation branch.

## Commands

- `git fetch origin main battle-adaptive-lineage-goal`

- `git cherry main battle-adaptive-lineage-goal`

- `git cherry origin/main battle-adaptive-lineage-goal`

- per-entry `git show -s` and `git diff-tree --name-status -r --root <sha>` readback recorded in JSONL

## Refs

- `head`: `f7f0399a9301b71677f43d1489bac08c1304b58a`

- `main`: `f7f0399a9301b71677f43d1489bac08c1304b58a`

- `origin_main`: `58bf218ad329e43b444f93fd3e819b986ff5256e`

- `battle_branch`: `1b6f164b82a4d5c7edeeb13c64d4eef5c2359bfe`

- `origin_battle_branch`: `7604741f2c6548f1936621810564e280e0566094`

## Result

- Total `git cherry main battle-adaptive-lineage-goal` entries: `245`

- Patch-equivalent to main (`-`): `50` -> disposition `merged_to_main_patch_equivalent`

- Branch-only (`+`): `195` -> disposition `deliberately_dropped_from_main_for_issue_1040_wrong_lane_branch_only`

## Evidence Files

- `/home/graham/workspace/experiments/agent-skills/skills/persona-dream/local/issue-1040-branch-triage-20260728/git-cherry-main-vs-battle-adaptive-lineage-goal.txt`

- `/home/graham/workspace/experiments/agent-skills/skills/persona-dream/local/issue-1040-branch-triage-20260728/git-cherry-origin-main-vs-battle-adaptive-lineage-goal.txt`

- `/home/graham/workspace/experiments/agent-skills/skills/persona-dream/local/issue-1040-branch-triage-20260728/commit-readback-main-vs-battle-adaptive-lineage-goal.jsonl`

- `/home/graham/workspace/experiments/agent-skills/skills/persona-dream/local/issue-1040-branch-triage-20260728/summary.json`

## Disposition Rule

`-` entries are patch-equivalent to `main` according to Git patch-id comparison and are classified as merged to main. `+` entries remain unique to `battle-adaptive-lineage-goal`; under the main-only Battle instruction and this ticket’s lane-invariant, they are deliberately not merged into `main` from this wrong-lane branch. This proof does not delete the branch; it resolves the issue by recording per-commit merge/drop disposition without destructive worktree operations.

## Representative Branch-Only Entries

- `57522af20` feat(embry-voice): fail-closed resemblyzer Horus speaker gate [1 changed path rows]

- `78e4ed25f` feat(embry-voice): canonical emitters for the three unproduced spine events [2 changed path rows]

- `78d8e039f` feat(embry-voice): wire speaker-gate and voice-render emitters into turn flow [1 changed path rows]

- `002ab7239` Recover live human wake event in physical audio_e2e turns [1 changed path rows]

- `1da4c6106` Allow compiling audio_e2e campaigns at a later attempt number [2 changed path rows]

- `215fec986` Honor CHATTERBOX_HOST_OUT_DIR when resolving rendered audio [1 changed path rows]

- `17c4299bf` fix(embry-voice-control): fresh managed-listener run dir per invocation [2 changed path rows]

- `c90c0cffc` feat(embry-voice): produce entities.extraction.completed for chat projection [3 changed path rows]

- `321b58a16` embry-voice-control: inject per-tone Orpheus emotion prosody into synthesized case audio [4 changed path rows]

- `5c59703bc` Expand spoken-text machine tokens DAG, HD, UX [1 changed path rows]

- `19c70a75c` Handle pyannote.audio in spoken-text expansion and ASR aliases [2 changed path rows]

- `0c7719247` Alias ASR spellings horace->horus, embree/henry->embry [1 changed path rows]

- `ee97ac634` Phonetic token equivalence and length-scaled render budget [2 changed path rows]

- `2dc4d4e83` Validate clone turn assets against the tone-tagged synthesis prompt [1 changed path rows]

- `365a2dbcc` Retry listener turn capture when runtime WER gate fails [1 changed path rows]

- `0a134a1bb` Treat WER-failed committed chains as non-recoverable [1 changed path rows]

- `f5faed145` Also retry listener captures on managed-listener timeouts [1 changed path rows]

- `7e4a401c8` Treat abandoned partial chains as non-recoverable captures [1 changed path rows]

- `809071940` Treat all recovery anomalies on receiptless turns as capture debris [1 changed path rows]

- `e8ea22564` Wait for listener re-arm before playing the post-wake query [1 changed path rows]

- `12b26dec9` Continue past blocked cases instead of aborting the campaign [1 changed path rows]

- `f686337b9` Park blocked cases: never re-attempt or continue their turns [1 changed path rows]

- `48bbca654` watch: execute Marcus canary live; refute 02:48 claim; fix stale-clip cache [41 changed path rows]

- `63e9ad1ad` audio_e2e: event-driven post-wake query handoff + loopback transport wiring [3 changed path rows]

- `cbcd81ea0` watch: record streaming gate from 3-round WebGPT assessment [28 changed path rows]

- `80a59f97a` audio_e2e: size managed-listener cycle budget for bounded re-captures [1 changed path rows]

- `e6ac30b72` audio_e2e: ignore unlocatable [0,0] sentinel entity spans in projection validation [3 changed path rows]

- `af6b82f72` watch: land P0A/P0B source-session journal + fail-closed replay [10 changed path rows]

- `cfb9f7cf7` battle: make adaptive-lineage panel receipt-authoritative (WebGPT BLOCK fix) [133 changed path rows]

- `73b5a4b56` watch: land UI live-event consumption gate with browser proof [8 changed path rows]

## Representative Patch-Equivalent Entries

- `7ac8e0d30` Fix WebGPT download routing after tab replacement [4 changed path rows]

- `9282ed14a` battle: land adaptive-lineage migration + adaptive immutable goal [21 changed path rows]

- `53198045c` battle: refresh adaptive-lineage-live fixture from fresh live qualification [1 changed path rows]

- `034617cad` battle: finish adaptive-lineage UX — distinct sprites + live comparison panel [13 changed path rows]

- `66f6c2872` battle: record adaptive-lineage UX-live completion handoff [1 changed path rows]

- `71df4d498` battle: run sprite creator↔reviewer loop; fix mapping + pixi HMR init [12 changed path rows]

- `36aa85060` battle: update handoff — deploy/pixi/sprite-reviewer caveats resolved [1 changed path rows]

- `1a29893d0` battle: mark adaptive-lineage immutable goal MET (12/12 criteria, evidence) [1 changed path rows]

- `ebf05ef11` battle: fix pytest collection (exclude fixture/artifact test_app.py) + stale child_tau_dag terminal/command_spec assertions [2 changed path rows]

- `4919c1641` battle: make proof_card PR3B test deterministic (force unreachable provider -> exploit-code-author BLOCKED regardless of live SciLLM) [1 changed path rows]

- `2f3ab21e8` battle: fix campaign event journal source_created_at None (schema requires date-time string; fall back to commit timestamp) [1 changed path rows]

- `833a1f5a1` battle: fix no-mockup-leakage lifecycle-fail-closed check (match current fail-closed copy/data-material marker, not stale 'not emitted' string) [1 changed path rows]

- `f9ede98d9` battle: v13 prove — replace non-deterministic frozen-hash checks with structural receipt validation (schema+PASS+wellformed events) [1 changed path rows]

- `60cd8e7ba` Add ask Tau DAG front door [6 changed path rows]

- `76b739dea` Clarify Tau-owned SciLLM DAG adapters [3 changed path rows]

- `a77324567` Strengthen ask Tau DAG stress gates [9 changed path rows]

- `8931ee990` Teach ask tau-dag live scillm routing [5 changed path rows]

- `6ac1f67b6` ask tau-dag: fail closed when runtime artifacts are missing (tau#113) [1 changed path rows]

- `cc3f8e2e3` ask tau-dag: unique node ids for repeated roundtable handlers [1 changed path rows]

- `3896738d7` ask roundtable: no local paths in browser-bound handler prompts [1 changed path rows]

## Proof Boundary

- mocked: no

- live: no, local Git-only proof

- exercised: Git branch ancestry/patch-id readback and GitHub issue lease

- remains unverified: Battle runtime behavior; no branch deletion was performed

