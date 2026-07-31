# Battle Arena Frontend/Backend Roundtable Packet

Objective:
Get reviewer next steps for turning Battle Arena into a fully working frontend + backend system, without losing current proof discipline.

Immutable goal or acceptance bar for this Ask roundtable:
Produce an evidence-backed executable slice manifest for the next local implementation phase of Battle Arena. The roundtable must not claim implementation completion; it must identify concrete backend, frontend/Pixi, integration, testing, and deployment slices with local deterministic proof gates.

Repository and branch constraint:
- Canonical repo: `/home/graham/workspace/experiments/agent-skills`
- Branch/source of truth: `agent-skills@main` only.
- Do not continue from `battle-adaptive-lineage-goal`, issue worktrees, or copied `/tmp` trees.

Current issue state:
- #1040 is closed as completed after deterministic Git triage.
- Open `battle in:title` issues: none from `gh search issues --repo grahama1970/agent-skills --state open 'battle in:title'`.
- Remaining open `agent-work` items are project-watchdog and persona-dream family, not Battle-title tickets.

#1040 proof:
- Required command exercised: `git cherry main battle-adaptive-lineage-goal` in primary worktree.
- Total entries: 245
- Patch-equivalent to main (`-`): 50 -> `merged_to_main_patch_equivalent`
- Branch-only (`+`): 195 -> `deliberately_dropped_from_main_for_issue_1040_wrong_lane_branch_only`
- Proof committed to remote main: `166cb20f320085b715e00c171ec89dfe171eb085`
- Remote check: `git ls-remote origin refs/heads/main` returned `166cb20f320085b715e00c171ec89dfe171eb085`.
- Proof artifact path: `skills/persona-dream/local/issue-1040-branch-triage-20260728/issue-1040-proof.md`

Battle deterministic evidence gathered this turn:
- `skills/battle/sanity.sh` exit 0, final `Result: PASS`.
- Sanity includes normalized UX JSON contract PASS for parent-spawn and sparse fixtures, UX handoff summary PASS, and UX data contract index PASS.
- Backend eval inside sanity is informational: `13/14` passed, known ticketed failure `fixture_valid::battle-004-kill-shot-pixi-replay`; sanity still returned PASS because it is known/ticketed.
- `$test-interactions` against the actual Battle built UI served from `skills/battle/spectator/dist` at `http://127.0.0.1:3015/#battle` passed 12/12 with 0 failures and 0 warnings.
- Interaction results path: `skills/battle/local/test-interactions-20260728-roundtable-battle3015/captures/results.json`
- Final screenshot path: `skills/battle/local/test-interactions-20260728-roundtable-battle3015/captures/battle-receipt-controls/0012_pane-controls_screenshot.png`

Important environment finding:
- `http://127.0.0.1:3002` is currently SPARTA Explorer, not Battle. Process cwd: `/home/graham/workspace/experiments/sparta/explorer`.
- Attempting Battle interactions on 3002 first rendered Global Posture/SPARTA content; this is evidence of deployment/route ambiguity, not a Battle component failure.
- Battle source package lacks root `index.html` in the current worktree, but `skills/battle/spectator/dist/index.html` exists and serves correctly as static build on 3015.

Battle skill constraints to preserve:
- Battle is an orchestration skill: host schedules, teams run as Tau/subagents, target code executes only in Docker.
- Backend emits semantic truth only: clock, events, segments, lanes, receipt ids, lineage, Judge outcomes, validation/fail-closed fields.
- Backend must not emit Pixi pixels, animation names, spritesheet paths, particle instructions, or renderer object ids.
- Pixi maps normalized adapter output to visuals; missing receipts disable terminal effects.
- DOM owns qids/accessibility; Pixi-only interaction is not enough.

Frontend/Pixi constraints to preserve:
- DOM/Pixi split: React DOM owns header, scoreboard, live events, sticky labels, controls, qids, keyboard accessibility; Pixi owns animated track surface/effects to the right of the fixed 290px label gutter.
- Receipt-backed event enables effect; missing receipt disables effect.
- Every selectable Pixi lane/marker/outcome needs a DOM hit-target mirror with `data-qid`, `data-qs-action`, `title`, `aria-label`, keyboard focus behavior.
- Run `$test-interactions` and inspect screenshots for visible proof before implementation closure.

Known evidence gaps / current blockers for “fully working”:
- Local proof covers current fixtures and built UI interactions, not an always-on production deployment.
- 3002 is not serving Battle; production route/hosting source of truth needs a clear owner and launch command.
- `skills/battle/sanity.sh` reports known backend eval case `fixture_valid::battle-004-kill-shot-pixi-replay` in informational backend eval.
- Current checks do not prove long-running live red/blue arena campaigns, real provider reliability, SSE/live transport at deployment scale, or full Battle frontend/backend end-to-end under fresh receipts.
- Ask/Web reviewers are advisory only; local deterministic commands remain the proof gates.

Questions for every seat:
1. POSITION: What is the next implementation direction to get Battle Arena frontend/backend fully working from this state?
2. EVIDENCE: Which facts above support that direction, and what additional local evidence should be collected first?
3. RISKS: What are the most likely false-green traps for Battle Arena now?
4. QUESTIONS: Name only blockers that require human input or external authority.
5. EXECUTABLE_SLICES: Propose a slice manifest. Each slice must include owner (`codex-loop`, `project-agent-script`, or `human`), target artifact/command, acceptance check, and proof boundary.

Expected response format:
Use these headings exactly: POSITION, EVIDENCE, RISKS, QUESTIONS, EXECUTABLE_SLICES. Keep recommendations concrete and rank the first three slices.

Proof boundary:
This roundtable is advisory. It cannot close the Battle implementation goal. It should produce the next slice manifest; implementation closure still needs local tests, backend receipts, browser screenshots/CDP evidence, and `$test-interactions`.
