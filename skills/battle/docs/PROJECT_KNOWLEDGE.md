# Project Knowledge: battle

**Last updated:** 2026-06-27 21:02 EDT by agent  
**Status:** Active development, pending review/commit

## Current Understanding

- Battle is a Red vs Blue security competition skill with a long-running
  orchestrator, digital twin isolation, AIxCC-style scoring, and report output.
- Production Battle should be an orchestration layer over subagents and Docker,
  not a large bespoke security engine. The host schedules rounds, chooses
  personas, dispatches subagents, provisions Docker runtimes, collects receipts,
  scores hard runtime signals, writes reports, and persists learning.
- All target code and all team-generated executable code must run in Docker:
  exploit probes, fuzzers, payloads, repro scripts, patch builds, tests,
  migrations, dependency installs, and replay checks. The host is control plane
  only.
- Docker target runtimes may be rebuilt and relaunched between rounds. Persist
  controlled volumes/artifacts for target state, patch state, crash artifacts,
  and evidence; store strategic context and learnings in `$memory`.
- Docker runtimes must support dynamic language/toolchain selection. Any target
  language may be added to the runtime image or selected adapter.
- Warm runtimes should support high-throughput mutation attempts. On capable
  workstation hardware, Battle should be able to schedule thousands of
  short-lived exploit/defense attempts with 10-15 second Docker execution
  windows when the required language/toolchain is already present.
- Battle search is combinatorial. Red should try every plausible exploit family
  and combination within safety/time budgets; Blue should do the same for
  patch, hardening, configuration, test, detection, and mitigation combinations.
  Successful combinations are promoted in `$memory`; failures are retained as
  negative evidence.
- Red and Blue are subagent teams. The orchestrator/cron must attach an explicit
  persona to every dispatched subagent, and may run multiple personas per team
  concurrently for creative, less predictable strategies.
- Red and Blue have broad agent-side research freedom through `$dogpile`,
  `$brave-search`, `$memory`, GitHub/code search, docs, papers, CVEs, and
  public writeups. This does not grant host execution or open target-container
  network by default.
- The real scorekeeper is environment outcome: Red wins a round when the system
  goes down, crashes, leaks, violates an invariant, or remains exploitable in
  the allotted time. Blue wins when the system remains up through the allotted
  time, the patch/hardening lands before failure, required behavior still works,
  and Red's current exploit no longer succeeds.
- Subagent handoffs and receipts should reuse the compact Tau-style schema shape
  (`tau.agent_handoff.v1` and `tau.subagent_receipt.v1`) with Battle-specific
  fields layered on top.
- Architecture hierarchy: Battle calls modular Tau subagent contracts; Tau and
  the loop/agentic harness execute subagents; the harness uses `$scillm` as the
  LLM/model caller. Battle should not become a direct model-provider router.
- The existing multi-round loop still needs a scorekeeper/evidence phase before
  Blue patch claims can be treated as accepted defense evidence.
- The production Battle monitor should be a React + Tailwind + shadcn + D3
  tracking UI over the active battle round, with a right-sidebar chat UX for
  human interjection and course correction. Sidebar messages must become
  schema-valid handoffs or human-interjection records before changing
  orchestration.
- The production monitor should also include a live graph view over `$memory`
  graph/BM25 recall: related exploits, defense mutations, personas, target code
  symbols, CWEs, endpoints, crashes, promotions, and negative-evidence trails.
  Graph traversal should support "show related attempts" while BM25 supports
  textual search over the same memory-backed evidence.
- Brave-search research on 2026-06-27 points toward a Canvas/WebGL graph layer
  for hundreds/thousands of live exploit attempts, with D3 force/layout math and
  React/SVG for labels, axes, selection chrome, accessible summaries, and the
  right-sidebar drill-down. Candidate directions include react-force-graph style
  Canvas/WebGL rendering and PixiJS+D3 hybrid rendering.
- Battle Monitor v1 now includes a Watch-style right sidebar chat surface. It
  renders starter chips, messages, a composer, stable `data-qid` selectors,
  `data-qs-action` hooks, and local `battle.human_interjection.v1` preview
  receipts. It is not connected to Tau, cron, persona mutation, Docker execution,
  or scorekeeper state yet.
- Battle v0 is the current deterministic proof rung. It runs one local fixture:
  Red proves a seeded path traversal exploit, Blue applies a deterministic
  patched `app.py`, Judge verifies the synced arena, and the scoreboard derives
  from the Judge receipt.
- Battle v0 claim scope is intentionally narrow:
  `mocked: no`, `live: local_deterministic_fixture`, `agentic: false`,
  `models_used: []`.
- The Battle monitor is artifact-backed. It fetches generated JSON from
  `/artifacts/battle-001` and fails closed with `BATTLE MONITOR BLOCKED` when
  required artifacts are missing or unreadable.
- Kimi's downloaded README was Tau-specific. Only the reusable receipt-backed
  proof-rung prose was adapted into Battle docs; Tau schemas, GitHub transport,
  Memory chat, and Tau-specific claims were intentionally not copied.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-06-27 | Implement Battle v0 as deterministic fixture proof, not agentic battle. | Establishes the receipt/Judge/monitor contract before adding scillm, OpenCode, Docker, QEMU, or multi-round complexity. |
| 2026-06-27 | Derive Battle v0 scoreboard status from the independent Judge receipt. | Avoids Blue self-certification via `Patch.verified` or `Patch.functionality_preserved`. |
| 2026-06-27 | Preserve `INSUFFICIENT_EVIDENCE` as a first-class status. | An unscoreable battle is different from a failed battle. |
| 2026-06-27 | Use deterministic patched-file replacement for Battle Blue instead of `git apply`. | The fixture runs in copy mode and should not depend on Git behavior. |
| 2026-06-27 | Keep the Blue duplicate recall/research bug as a follow-up, not part of Battle v0. | It is real but outside the Battle receipt/Judge/monitor scope. |
| 2026-06-27 | Store Battle monitor `node_modules` on `/mnt/storage12tb` and symlink it back. | Keeps heavy dependency directories out of the skill folder per storage policy. |
| 2026-06-27 | Treat Production Battle as Docker-only code execution plus subagent orchestration. | Low-level exploit work may be destructive; host execution of target/team code is not acceptable. |
| 2026-06-27 | Require explicit personas on every Red/Blue subagent dispatch. | Personas increase strategic diversity and make team responses less homogeneous while preserving a common receipt schema. |
| 2026-06-27 | Score rounds by uptime/down outcome over allotted time. | The environment outcome is the real judge; the scorekeeper records and reports hard signals. |
| 2026-06-27 | Persist round learning in `$memory` and controlled Docker volumes/artifacts. | Containers may be rebuilt between rounds, but strategic context and required state must survive. |
| 2026-06-27 | Require a right-sidebar human interjection/course-correction UX in the production monitor. | Humans need a visible way to pause, redirect personas, approve goal changes, and add context while preserving the artifact trail. |
| 2026-06-27 | Treat Battle as warm-pond evolutionary exploit/defense search. | Many high/low-level ideas and combinations should be tried quickly; successful mutations are promoted and failures become negative evidence. |
| 2026-06-27 | Make Battle an orchestrator of Tau subagents, not the LLM runtime. | Keeps Battle focused on teams, personas, Docker isolation, scoring, artifacts, and memory promotion while Tau/loop/scillm handle agent execution. |
| 2026-06-27 | Add memory-backed graph/BM25 visualization to the production monitor target. | Related exploit/defense mutations should be inspectable as a live graph while the battle runs. |
| 2026-06-27 | Implement the first Battle Monitor right-sidebar chat UX as local preview. | Reuses the Watch shared-chat interaction pattern while blocking orchestration mutation until schema-valid backend handling exists. |
| 2026-06-27 | Move Red `$hack` usage behind persona-attached subagents. | Battle should pass a scan/research/memory-derived exploit candidate list to an `agent-skills/agents`/Tau subagent, not import `$hack` modules directly. |
| 2026-06-27 | Move Python implementation under `src/battle_skill/`. | Skill root should expose `SKILL.md`, `run.sh`, `sanity.sh`, docs, config, fixtures, and monitor assets; implementation modules belong in a package. |
| 2026-06-27 | Register Battle with `$browser-oracle`. | `skills/battle/.ask/browser-oracles.yaml` maps to WebGPT project `battle`; the live binding points at tab `837356871`. |
| 2026-06-27 | Use `$memory` HTTP endpoints for programmatic Battle memory integration. | `memory_integration.py` uses `httpx` with `/recall` and `/store`; deprecated CLI learn and direct Arango/common memory imports are not used. |

## Open Questions

- [ ] Should the next Battle PR add a real Judge phase to the existing
  multi-round `BattleOrchestrator` loop?
- [ ] Should the Blue duplicate recall/research fix be handled before or after
  integrating agentic Battle Red/Blue backends?
- [ ] What should the first Tau-style Battle handoff/receipt schema extension
  be called?
- [ ] Which `$memory` collection name should store Battle cross-round learning:
  `battle_memory`, `subagent_memory`, or a more specific pair such as
  `battle_round_memory` and `battle_persona_memory`?
- [ ] What is the first Docker language-runtime adapter to prove after the
  deterministic fixture: Python-only, polyglot auto-detect, or target-declared?
- [ ] Should the production Battle monitor be implemented as a new Tailwind /
  shadcn / D3 surface or by replacing the current Vite proof monitor in place?
- [ ] What backend endpoint should consume `battle.human_interjection.v1`:
  Battle directly, Tau route parser, or a shared human-interjection service?

## Key Files

| File | Purpose |
|------|---------|
| `src/battle_skill/cli.py` | Typer CLI; includes `battle-fixture` for deterministic fixture runs. |
| `src/battle_skill/battle_fixture.py` | Deterministic Battle v0 Red -> Blue -> Judge runner and artifact writer. |
| `src/battle_skill/judge.py` | Independent deterministic Judge for exploit-safe and regression commands. |
| `src/battle_skill/receipts.py` | Red, Blue, Judge, and command receipt dataclasses plus JSON writer. |
| `fixtures/battle-001/` | Seeded path traversal target, exploit check, tests, and deterministic patch. |
| `monitor/battle/` | React artifact monitor plus Playwright checks. |
| `.ask/browser-oracles.yaml` | Directory-local WebGPT project mapping for `$browser-oracle` and `$webgpt-review`. |
| `docs/BATTLE_V0.md` | Detailed Battle v0 claim scope, artifact contract, validation commands, and non-claims. |
| `README.md` | Human-facing Battle overview with Battle v0 and evidence discipline. |
| `SKILL.md` | Agent-facing Battle skill contract, now including Battle v0 fixture proof notes. |

## Evidence State

Last inspected local artifacts from the Battle v0 run:

```text
/tmp/battle-001/run-receipt.json
/tmp/battle-001/scoreboard.json
/tmp/battle-001/judge/judge-receipt.json
skills/battle/monitor/battle/test-results/battle-monitor.png
/tmp/codex-ui-verification/agent-skills/battle-monitor/latest.json
```

Last inspected values:

```text
run.status=PASS
run.verdict=BLUE_SUCCESS
run.live=local_deterministic_fixture
score.status=PASS
score.verdict=BLUE_SUCCESS
judge.exploit_blocked_after_patch=True
judge.regression_tests_pass=True
Playwright screenshot size=207521 bytes
```

Additional checks performed:

```text
BATTLE_README_CONTENT_CHECK_PASS
BATTLE_PROSE_TAU_LEAK_CHECK_PASS
PY_MODULE_DOCSTRINGS_PASS
python3 scripts/check_mock_evidence_claims.py -> OK: checked 300 test file(s); no mock+proof claim violations
```

## Non-Claims

Battle v0 does not prove:

- real Red agent behavior
- real Blue agent behavior
- scillm or OpenCode execution
- anvil or code-runner patch quality
- multi-round learning
- Docker or QEMU modes
- memory learning
- Lean or QRA assurance
- production Battle readiness

## Infrastructure State

- Battle runtime state defaults to `/mnt/storage12tb/skills/battle/`.
- The skill root should not contain real `.venv`, `artifacts`, `battles`,
  `reports`, `worktrees`, `node_modules`, or `__pycache__` directories.
- Generated monitor artifacts under `monitor/battle/public/artifacts/` are proof
  copies for UI validation and should not be treated as source.
- Current Battle worktree state is uncommitted and pending review.
- Full clean validation should be rerun before any closure, commit, or readiness
  claim.
