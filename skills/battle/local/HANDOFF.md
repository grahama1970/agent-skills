# Handoff Report: battle adaptive-lineage receipt

**Timestamp**: 2026-07-20T17:13:44Z  
**Active Agent**: Codex  
**Branch**: `battle-adaptive-lineage-goal`  
**Current objective**: finish `GOAL_ADAPTIVE_LINEAGE.md` recovery from the
agent-skills worktree, not the pi-mono shell.

> Evidence rule for the next agent: trust receipts and command artifacts, not
> stale prose. The old `GOAL_ADAPTIVE_LINEAGE.md` completion section says
> `GOAL STATUS: MET`, but this recovery task supersedes that stale closure
> claim. Current status is **pending WebGPT acceptance for the agent-skills
> hosted receipt**.

## 1. Project Overview

- **Ecosystem**: Python Battle backend under `skills/battle/src/battle_skill`
  plus TypeScript/React/Pixi spectator under `skills/battle/spectator`.
- **Core purpose**: prove one canonical BATTLE-004 adaptive lineage:
  `G0 -> {G1-A, G1-B} -> G2`, with a live SciLLM + Docker qualification receipt
  and a spectator that renders that exact receipt with honest live/recorded
  state.
- **Current hosting decision**: agent-skills owns the receipt host. Use
  `http://127.0.0.1:3003/#battle/receipt?engine=pixi`. Do not resume from
  `pi-mono/packages/ux-lab` or add a standalone `#battle/live` route.

## 2. Current State

- **Backend receipt is fresh and live**:
  `skills/battle/local/adaptive-lineage-relive-20260720T144034Z/adaptive-lineage-qualification.json`.
  It reports `status: PASS`, `run_id: arena-adaptive-lineage-20260720T144034Z`,
  `battle_id: battle-004`, 4 primary SciLLM calls, 4 HTTP completions,
  4 red specimens, no budget overrun, and exactly one G2 Judge completion.
- **Fixture is normalized with descriptive exploit names**:
  `skills/battle/spectator/src/lineage/__fixtures__/adaptive-lineage-live.json`
  has `data_source: live`, selected `G1-A`, runner-up `G1-B`, criterion
  `novelty_distance`, and names:
  `G0 Seed Slip`, `G1-A Module Slip`, `G1-B Arc Courier`, `G2 ZipInfo Path`.
- **Agent-skills host exists and is committed**:
  `skills/battle/spectator/index.html`, `src/main.tsx`, `src/standalone.css`,
  and `scripts/{build-static,serve-static}.mjs`.
  `curl http://127.0.0.1:3003/__host.json` returns host
  `agent-skills battle spectator` and entry `skills/battle/spectator/src/main.tsx`.
- **Live-browser proof exists**:
  `skills/battle/local/agent-skills-host-verify-20260720T1646Z/surf-assertions.json`
  targets `http://127.0.0.1:3003/#battle/receipt?engine=pixi`, `mocked:false`,
  `live:true`, screenshot bytes `254726`, and asserts visible text for
  `ADAPTIVE LINEAGE`, `LIVE: Qual PASS`, all four exploit names, and
  `G1-A Module Slip · selected G1`.
- **WebGPT acceptance for this new host is not obtained**:
  `skills/battle/local/webgpt-design-review-20260720T1706Z/response.receipt.json`
  reports `submitted_to_chatgpt:false`. The earlier `:3002` WebGPT acceptances
  do not cover the new agent-skills `:3003` host.

## 3. What is Working Well

- Recent Battle commits on this branch:
  - `f3d9d5c36 battle: host receipt from agent-skills`
  - `4e6eda537 battle: name adaptive lineage exploits`
  - `e5e2893a7 battle: render live adaptive lineage receipt`
- Focused deterministic checks already passed for the committed host work:
  - `node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json`
  - `node scripts/build-static.mjs`
  - Curl of `:3003/__host.json`
  - Surf screenshot/assertion readback of the receipt route
- Current evidence posture:
  - `mocked: no`
  - `live: yes`
  - exercised: real adaptive-lineage qualification receipt, normalized fixture,
    standalone agent-skills static host, live browser render
  - unverified: WebGPT design acceptance for the agent-skills hosted page

## 4. What is Currently Broken Or Pending

- **WebGPT transport / ChatGPT response health is the active blocker**. The
  blocker summary is
  `skills/battle/local/webgpt-agent-skills-host-blocker-20260720T1721Z.md`.
  Attachment-backed review attempts either stayed at `prepared_prompt` or left
  the prompt in the composer; a focused text-only sanity reached
  `submitted_to_chatgpt:true` but then stalled with `Stop answering` and no
  sentinel.
- **Existing Battle WebGPT tab is busy**. Tab `837359249` contains the prior
  `:3003` review prompt and still showed `Thinking` / `Stop answering` when
  inspected. Do not submit a new prompt into that tab while it is busy.
- **Port `3002` is unusable in this session**. It is held by a stale D-state Vite
  child from an earlier attempt. Use `3003` until reboot or kernel release.
- **Do not trust `#battle/live` claims**. That route was verified false earlier;
  valid served hashes are `#battle`, `#battle/isolation`, and `#battle/receipt`.
- **Repo is dirty from unrelated agents**. Stage Battle handoff/artifact paths
  explicitly only. Never `git add -A`.

## 5. Next Steps

1. Inspect whether the prior Battle WebGPT tab has produced a sentinel:
   ```bash
   cd skills/surf
   ./run.sh js "return JSON.stringify({title:document.title,url:location.href,text:document.body.innerText.slice(-4000)},null,2)" --tab-id 837359249 --json
   ```
   If it is still thinking, do not reuse it.

2. Do not rerun the broad Battle WebGPT review first. Run a tiny text-only Surf
   WebGPT sanity after ChatGPT response health recovers:
   ```bash
   cd skills/surf
   ./run.sh webgpt.submit --input <text-only-request.md> --output <response.md> \
     --raw-output <response.raw.md> --meta-output <response.meta.json> \
     --receipt-output <response.receipt.json> --submitted-output <response.submitted.md> \
     --create-tab --timeout 180
   ```
   Only retry the Battle review once the text-only sanity reaches
   `proof_status: response_proven`.

3. Then submit the existing evidence bundle through Surf using a fresh,
   identity-proven tab. The bundle exists at:
   ```bash
   skills/battle/local/webgpt-design-review-20260720T1706Z/request.md
   skills/battle/local/webgpt-design-review-20260720T1706Z/battle-agent-skills-host-review-bundle.zip
   ```
   A created-tab preflight passed once:
   ```bash
   cd skills/surf
   ./run.sh webgpt.preflight --create-tab --no-activate --json
   ```
   If zip attachments still leave `Send prompt` disabled, use the screenshot
   request path:
   `skills/battle/local/webgpt-design-review-20260720T1721Z/request.md` plus
   `skills/battle/local/agent-skills-host-verify-20260720T1646Z/surf-receipt-agent-skills-3003.png`.

4. When WebGPT returns `ACCEPTED` with a Surf sentinel-backed response, commit
   the relevant handoff/review artifacts by explicit path and push:
   ```bash
   git add skills/battle/local/HANDOFF.md \
     skills/battle/local/webgpt-design-review-20260720T1706Z/request.md \
     skills/battle/local/webgpt-design-review-20260720T1706Z/battle-agent-skills-host-review-bundle.zip \
     skills/battle/local/webgpt-design-review-20260720T1706Z/response.md \
     skills/battle/local/webgpt-design-review-20260720T1706Z/response.raw.md \
     skills/battle/local/webgpt-design-review-20260720T1706Z/response.meta.json \
     skills/battle/local/webgpt-design-review-20260720T1706Z/response.receipt.json \
     skills/battle/local/webgpt-design-review-20260720T1706Z/response.submitted.md
   git diff --cached --name-only
   git commit -m "battle: handoff adaptive lineage host state"
   git push origin battle-adaptive-lineage-goal
   git ls-remote origin refs/heads/battle-adaptive-lineage-goal
   ```

5. Only after the accepted review is committed and remote-verified, audit the
   immutable goal checklist. Do not use closure language unless the final report
   cites the backend receipt, browser screenshot/assertions, WebGPT response, and
   remote commit proof.

## 6. Project Context for Success

- **Key files**:
  - `skills/battle/src/battle_skill/adaptive_lineage.py`
  - `skills/battle/src/battle_skill/arena_live_battle_proof.py`
  - `skills/battle/spectator/src/lib/battle-adaptive-lineage-view-model.ts`
  - `skills/battle/spectator/src/lib/battle-data.ts`
  - `skills/battle/spectator/src/main.tsx`
  - `skills/battle/spectator/scripts/build-static.mjs`
  - `skills/battle/spectator/scripts/serve-static.mjs`
- **Current local server**:
  `node scripts/serve-static.mjs --host 127.0.0.1 --port 3003` from
  `skills/battle/spectator`.
- **Avoid npm** in this environment. `npm --version` and Vite operations hung.
  Use direct Node scripts:
  ```bash
  cd skills/battle/spectator
  node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json
  node scripts/build-static.mjs
  node scripts/serve-static.mjs --host 127.0.0.1 --port 3003
  ```
- **Do not move back to pi-mono**. The current recovery path is agent-skills
  hosted receipt evidence plus WebGPT acceptance for that host.
