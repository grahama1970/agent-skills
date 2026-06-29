---
name: battle
description: >
  Red vs Blue team security competition orchestrator. Runs long-running overnight
  battles with 1000s of interactions, scoring, and insight generation.
allowed-tools:
  - Bash
  - Read
triggers:
  - battle
  - thunderdome
  - red vs blue
  - overnight battle
  - security competition
  - red team vs blue team
metadata:
  short-description: Red vs Blue team security competition
  requires: docker
provides:
  - competitive-selection
  - docker-isolation
composes:
  - hack
  - anvil
  - memory
  - treesitter
  - taxonomy
  - task-monitor
  - ops-docker
  - code-runner

complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
taxonomy:
  - competition
  - selection
  - resilience
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Battle Skill

**Red vs Blue Team Security Competition Orchestrator**

Pits a Red Team (attack) against a Blue Team (defense) in a long-running competitive loop. Each team leverages all `.pi/skills` to attack or defend a target codebase.

## Architecture

Production Battle is an orchestration skill, not a large bespoke security
engine. The host-side process should schedule rounds, choose personas, dispatch
subagents, provision Docker runtimes, collect receipts, score hard runtime
signals, write reports, and persist learning. Target code and team-generated
code must execute only inside Docker.

Required production invariants:

- Battle has three active roles plus one objective recorder. **Arena Team**
  builds or selects the project/app/digital twin and secretly plants one or more
  vulnerabilities. Arena Team is not the judge. **Red Team** attacks. **Blue
  Team** scans, patches, hardens, and defends. **Scorekeeper/Judge** records
  objective runtime outcomes from hidden oracles and receipts.
- Production Red and Blue work asynchronously and dynamically, not as a fixed
  Red-then-Blue script. Blue may scan for vulnerabilities, run `$ingest-code`
  or `$treesitter`, recall CWE and patch history, research mitigations, and
  patch before Red exploits a hidden bug. Red may simultaneously recall,
  research, scan, mutate payloads, and exploit.
- The scheduler should support bounded parallelism when advantageous. Multiple
  personas/workers per team may run concurrently, with explicit budgets,
  worker ids, persona ids, model choices, and receipts. Do not implement
  unbounded thread spawning.
- Red and Blue are subagent teams. Each dispatched subagent must include an
  explicit persona selected by the orchestrator for that turn. Multiple personas
  per team may run concurrently when the turn benefits from breadth.
- Red-team `$hack` execution is a subagent responsibility, not a Battle Python
  import. Battle performs or schedules scan/research/memory recall, builds the
  candidate exploit list, chooses the Red persona, dispatches an
  `agent-skills/agents`/Tau subagent with that contract, and records the
  returned exploit receipt.
- Subagent handoffs and receipts should follow the compact Tau-style JSON
  contract shape used by `tau.agent_handoff.v1` and `tau.subagent_receipt.v1`,
  with Battle-specific fields layered on top rather than a separate ad hoc
  protocol.
- Battle calls modular Tau subagent contracts. Tau and the loop/agentic harness
  own subagent execution and use `scillm` as the LLM/model caller. Battle owns
  team selection, persona assignment, Docker runtimes, scorekeeping, artifacts,
  and memory promotion.
- Model choice is strategic and may be persona-owned, but all calls route
  through Tau/loop and `$scillm`. SOTA models may be used for planning, small or
  local low-parameter models for high-throughput mutation generation and triage,
  specialist models for language/security niches, and batch calls for broad
  candidate generation. Receipts must record persona, model/surface, reason
  selected, latency/cost when available, and proof scope.
- Red and Blue have free research access through approved agent-side research
  skills, including `dogpile`, `brave-search`, `memory`, `github-search`,
  `arxiv`, `ingest-code`, `treesitter`, docs, papers, CVEs, and public
  writeups.
- Persona memory should be recalled before research and scan selection. Persona
  framing can color `$brave-search`, `$dogpile`, `$github-search`, and `$arxiv`
  queries, but scorekeeper evidence remains objective.
- Workers may clone selected public GitHub repositories into bounded
  `/tmp/battle-<run-id>/github-research/...` directories for read-only
  inspection. Cloned PoC/exploit code must not execute on the host. If any
  research code is run, built, fuzzed, or adapted into a probe, it must execute
  inside Docker and produce a command receipt.
- All target apps, exploit probes, fuzzers, payloads, repro scripts, patch
  builds, tests, migrations, dependency installs, and replay checks run in
  Docker. The host is control plane only.
- Docker target runtimes may be rebuilt and relaunched between rounds. Persist
  only controlled volumes and artifacts that must survive a rebuild; store
  durable strategic context and learnings in `$memory`.
- Docker runtimes must support dynamic language/toolchain selection. Any code
  language required by the target may be added to the runtime image or selected
  adapter; Battle should not hard-code one language.
- Battle should be high-throughput when the target runtime is warm: thousands of
  exploit/defense mutations may be attempted with tight 10-15 second Docker
  execution windows on capable workstation hardware.
- Battle should use combinatorial mutation. Red tries every plausible exploit
  family and combination within safety/time budgets; Blue tries every plausible
  patch, hardening, configuration, test, detection, and mitigation combination.
  Successful combinations receive stronger promotion than isolated tactics.
- Research may burst concurrently from the agent side. Red and Blue may fan out
  multiple `brave-search` and `dogpile` calls, including 10x concurrent Brave
  search batches when needed, then store useful results and negative evidence in
  `$memory`.
- Target containers default to no network. External research happens from the
  agent side through controlled skills unless a scenario explicitly grants
  target-container network access.
- Each session is a hidden-vulnerability race. The scorekeeper records objective
  outcomes: exploit-before-patch, patch-before-exploit, system down, system
  still up after the allotted time, exploit success, crash artifacts, patch
  timing, regression behavior, resource limits, and replay results. It is not
  an LLM judge and is separate from Arena Team.

Based on research into RvB framework, DARPA AIxCC, and Microsoft PyRIT:

```
┌─────────────────────────────────────────────────────────┐
│                 Battle Orchestrator                      │
│  - Game loop (RvB pattern)                              │
│  - Concurrent Red/Blue execution                        │
│  - Entropy-driven termination                           │
│  - Checkpointing for overnight runs                     │
└─────────────────────────────────────────────────────────┘
         │                              │
    ┌────┴────┐                    ┌────┴────┐
    │ Red Team │                   │ Blue Team│
    │ (Thread) │                   │ (Thread) │
    ├──────────┤                   ├──────────┤
    │ Skills:  │                   │ Skills:  │
    │ - hack   │                   │ - anvil  │
    │ - memory │                   │ - memory │
    └──────────┘                   └──────────┘
         │                              │
         └──────────┬───────────────────┘
                    │
    ┌───────────────┴────────────────────┐
    │           Digital Twin              │
    │  ┌─────────────────────────────┐   │
    │  │ Mode: git_worktree          │   │
    │  │   - Red attacks arena       │   │
    │  │   - Blue patches workspace  │   │
    │  │   - Cherry-pick to test     │   │
    │  ├─────────────────────────────┤   │
    │  │ Mode: docker                │   │
    │  │   - Isolated containers     │   │
    │  │   - Battle network          │   │
    │  ├─────────────────────────────┤   │
    │  │ Mode: qemu                  │   │
    │  │   - Emulated firmware       │   │
    │  │   - GDB attach points       │   │
    │  └─────────────────────────────┘   │
    └────────────────────────────────────┘
```

## Digital Twin Modes

The battle skill supports multiple target types through its Digital Twin system:

### 1. Source Code (git_worktree)
For battling over git repositories. Creates isolated git worktrees for each team.

```bash
./run.sh battle /path/to/repo --rounds 100
```

### 2. Docker Container (docker)
For battling over containerized applications. Spins up separate containers for each team.

```bash
# Using a Docker image
./run.sh battle --docker-image nginx:latest --rounds 100

# Using a Dockerfile in the target directory
./run.sh battle /path/with/Dockerfile --mode docker
```

### 3. Firmware/Microprocessor (qemu)
For battling over firmware and embedded systems. Boots firmware in QEMU emulator.

```bash
# Auto-detect architecture from ELF header
./run.sh battle firmware.elf --rounds 100

# Specify machine type explicitly
./run.sh battle firmware.bin --qemu-machine arm
./run.sh battle firmware.bin --qemu-machine riscv64
./run.sh battle bios.rom --qemu-machine x86_64
```

Supported QEMU machines:
- `arm` - ARM Cortex-M (STM32, etc.)
- `aarch64` - ARM64
- `riscv32`/`riscv64` - RISC-V
- `x86_64`/`i386` - x86
- `mips` - MIPS (routers, embedded)

### 4. Copy Mode (fallback)
For non-git directories. Creates simple file copies for each team.

## Commands

```bash
# Start a battle (10 rounds for testing)
./run.sh battle /path/to/codebase --rounds 10

# Start overnight battle (1000 rounds)
./run.sh battle /path/to/codebase --overnight

# Battle a Docker container
./run.sh battle --docker-image myapp:latest --rounds 100

# Battle firmware with QEMU
./run.sh battle firmware.bin --qemu-machine arm --rounds 100

# Check battle status
./run.sh status

# Resume interrupted battle
./run.sh resume <battle-id>

# Generate report from completed battle
./run.sh report <battle-id>

# Run the deterministic Battle v0 fixture proof
./run.sh battle-fixture battle-001 --out /tmp/battle-001

# Run the current Tau AgentHarness proof rung
./run.sh tau-agentic-smoke battle-002 --out /tmp/battle-002-tau-agentic --fast-scan

# Run the current Arena Team Docker race proof rung
./run.sh arena-docker-smoke battle-003 --out /tmp/battle-003-arena

# Run Arena Docker race with Tau AgentHarness action-selection receipts
./run.sh arena-docker-smoke battle-003 --out /tmp/battle-003-arena-agentic --agentic --red-persona brandon-bailey --blue-persona coder

# Run Arena Docker race with live Scillm chat planning plus Tau receipts
./run.sh arena-docker-smoke battle-003 --out /tmp/battle-003-arena-scillm --agentic --scillm-plan --red-persona brandon-bailey --blue-persona coder --scillm-model opencode/kimi-k2.6

# Run Arena Docker race with Scillm, Tau, and memory/code/research context receipts
./run.sh arena-docker-smoke battle-003 --out /tmp/battle-003-arena-context --agentic --scillm-plan --context-receipts --red-persona brandon-bailey --blue-persona coder --scillm-model opencode/kimi-k2.6

# Run the four-party Docker operational proof
./run.sh battle-v1-operational battle-003 --out /tmp/battle-v1-operational-a --red-workers 2 --blue-workers 2 --max-attempts 4 --require-memory

# Run the expanded warm-pond Tau worker-fanout proof
./run.sh battle-v1-operational battle-004 --out /tmp/battle-v1-expanded-tau-032 --red-workers 32 --blue-workers 32 --max-attempts 32 --require-memory --tau-live --research-broker

# Run the generated warm-pond fixture preflight
./run.sh battle-v1-operational battle-005 --out /tmp/battle-v1-generated-no-tau-003 --red-workers 16 --blue-workers 16 --max-attempts 16 --require-memory --tau-deterministic --research-broker

# Current Tau scaling blocker reproduction
./run.sh battle-v1-operational battle-005 --out /tmp/battle-v1-generated-tau-064 --red-workers 64 --blue-workers 64 --max-attempts 64 --require-memory --tau-live --research-broker
```

## Battle v0 Fixture Proof

Battle v0 is a narrow, deterministic proof rung for the Battle artifact contract.
It runs one local Red -> Blue -> Judge fixture and emits replayable receipts:

- `red-receipt.json`
- `blue-receipt.json`
- `judge/judge-receipt.json`
- `scoreboard.json`
- `monitor-index.json`
- `run-receipt.json`

The Battle v0 scoreboard is derived from the independent Judge receipt, not from
Blue-side self-certification fields. This addresses the current battle loop gap
where a Blue patch can carry `verified` and `functionality_preserved` claims
without a separate Judge phase.

The fixture proof is intentionally limited:

```text
mocked: no
live: local_deterministic_fixture
agentic: false
models_used: []
```

It proves the receipt boundary and monitor artifact rendering for the local
fixture only. It does not prove real Red or Blue agent behavior, scillm,
OpenCode, anvil, code-runner, memory learning, Docker, QEMU, or multi-round
campaign readiness. See `docs/BATTLE_V0.md` for the validation commands and
artifact-backed monitor proof path.

## Battle v1 Target Contract

Battle v1 is the next proof ladder, not yet production-complete. It should add:

- Arena Team fixture generation with hidden vulnerabilities and hidden ground
  truth for the scorekeeper.
- Asynchronous Red/Blue workers with bounded parallelism.
- Persona-conditioned worker choice of research tools and `$scillm`
  model/surface within scenario policy.
- Blue-side proactive scanning: `$memory`, `$ingest-code`, `$treesitter`, CWE
  context, research, patch, and regression checks.
- Docker-only execution for target, probe, build, test, fuzz, PoC, and replay
  commands.
- Scorekeeper receipts for exploit-before-patch or patch-before-exploit race
  outcomes.
- React+D3 force-directed drill-down monitor backed only by real receipts,
  ledger rows, and `$memory` graph/BM25 data.

The current `tau-agentic-smoke` command proves only a narrow Tau
`AgentHarness` boundary with a deterministic local provider:

```text
mocked: no
live: local_fixture_with_tau_agent_harness
agentic: true
models_used: ["tau-local-deterministic-provider"]
```

It does not prove `$scillm`, Ollama/local model routing, hosted models,
OpenCode delegate execution, Docker-contained target execution, hidden Arena
Team vulnerability generation, asynchronous scheduling, or the React+D3 live
monitor.

The current `arena-docker-smoke` command proves the first hidden-vulnerability
race boundary:

```text
mocked: no
live: docker_hidden_vulnerability_race
agentic: false by default, true with --agentic
models_used: [] by default, ["tau-local-deterministic-provider"] with --agentic,
  and also ["opencode/kimi-k2.6"] with --scillm-plan
```

It uses the `battle-003` fixture. Arena Team records hidden SQL injection and
reflected XSS ground truth, Blue patches first inside Docker, Red attempts the
hidden exploit later inside Docker, and the scorekeeper replays exploit-safe and
regression checks inside Docker. The current local proof produced
`BATTLE_ARENA_DOCKER_SMOKE_ASSERT_PASS`, `run.status=PASS`,
`run.verdict=BLUE_SUCCESS`, `score.race.patch_before_exploit=True`,
`judge.arena_team_is_judge=False`, `judge.exploit_blocked_after_patch=True`,
and `judge.regression_tests_pass=True` under `/tmp/battle-003-arena`.

With `--agentic`, the same command also runs Red and Blue action selection
through Tau `AgentHarness`, writes Tau handoffs and Tau subagent receipts,
validates those receipts, and records a SQLite event ledger. The current local
agentic proof produced `BATTLE_ARENA_DOCKER_AGENTIC_ASSERT_PASS`,
`tau.team.status=PASS`, `tau.team.tau_receipts_valid=True`,
`tau.harness.red.status=PASS`, `tau.harness.blue.status=PASS`,
`red.persona=brandon-bailey`, and `blue.persona=coder` under
`/tmp/battle-003-arena-agentic`.

With `--scillm-plan`, the same command additionally calls live Scillm chat for
Red and Blue action selection before Tau and Docker. The current local Scillm
proof produced `BATTLE_ARENA_DOCKER_SCILLM_ASSERT_PASS`,
`run.execution.scillm_plan=True`, `models_used` containing
`opencode/kimi-k2.6`, Red and Blue Scillm action-selection receipts with
`status=PASS`, and 10 SQLite event rows under `/tmp/battle-003-arena-scillm`.

With `--context-receipts`, the same command additionally calls `$memory` over
HTTP for `/recall`, runs a Docker-contained fast scan, calls live Brave batch
search from scan/persona context, extracts Python AST code context, writes a
deterministic research seed receipt, generates warm-pond exploit/defense
candidates, executes a bounded set of selected warm-pond combinations in
isolated Docker workspaces, and stores one outcome document through `$memory`
`/upsert` into `battle_round_memory`. The current local context proof produced
`BATTLE_ARENA_DOCKER_CONTEXT_ASSERT_PASS` and
`BATTLE_SCAN_BRAVE_WARM_POND_ASSERT_PASS` and
`BATTLE_WARM_POND_EXECUTION_ASSERT_PASS`, with
`run.execution.context_receipts=True`, `context.memory.recall_status=PASS`,
`context.memory.store_status=PASS`, `memory.upsert.inserted=1`,
`fast_scan.finding_count=2`, `brave_search.result_count=8`,
`warm_pond.combination_count=16`, `warm_pond_execution.selected_attempt_count=4`,
`warm_pond_execution.passed_attempt_count=4`, `code_context.symbol_count=7`,
and 22 SQLite event rows under `/tmp/battle-003-arena-context`. Its Tree-sitter
diagnostic is currently `BLOCKED` because the treesitter-tools environment is
missing `click`; the Battle proof uses Python AST fallback for this rung.

This proof does not exercise Scillm delegate, batch, or tool execution inside
Battle, an unbounded warm-pond swarm, Dogpile/GitHub-search candidate
enrichment, memory graph promotion or cross-round reuse, Tau loop repair
cycles, Tree-sitter success, or the React+D3 live monitor.

The current `battle-v1-operational` command is the next bounded proof rung. It
runs Arena, Red, Blue, and Scorekeeper roles against `battle-003`, dispatches
bounded asynchronous Red/Blue worker pools, records memory recall and
live research-broker receipts, records warm-pond promotion receipts, replays
every selected attempt inside Docker, and writes a generated force graph for the
monitor:

```text
mocked: no
live: docker_four_party_operational
agentic: true
docker_only: true
red_blue_async: true
models_used: ["tau-local-deterministic-provider"]
```

Validation:

```bash
./run.sh battle-v1-operational battle-003 --out /tmp/battle-v1-operational-a --red-workers 2 --blue-workers 2 --max-attempts 4 --require-memory --research-broker
python3 sanity/battle_v1_operational_acceptance.py /tmp/battle-v1-operational-a --allow-first-recall-empty

./run.sh battle-v1-operational battle-003 --out /tmp/battle-v1-operational-b --red-workers 2 --blue-workers 2 --max-attempts 4 --require-memory --research-broker
python3 sanity/battle_v1_operational_acceptance.py /tmp/battle-v1-operational-b --require-recall-found
```

With `--research-broker`, `battle-v1-operational` writes
`context/research-broker-receipt.json`, runs Brave batch search plus Red/Blue
GitHub and Dogpile retrieval lanes concurrently with
`threadpool_as_completed`, records completion order, and converts the live
research lane receipts into a `research_signal_summary` before warm-pond
candidate selection. Research lanes are agent-side retrieval only; cloned or
discovered PoC code must not execute on the host. Current proof evidence under
`/tmp/battle-v1-research-dispatch-001` recorded `status=PASS`,
`passed_lane_count=5`, `blocked_lane_count=0`, `research_weighted_candidate_count=6`,
`research_weighted_combination_count=8`, Red and Blue worker
`research_dispatch.research_boost=0.2`, Tau `scheduling.mode=asyncio.as_completed`,
and `BATTLE_V1_OPERATIONAL_ACCEPTANCE_PASS`.

The `battle-004` fixture expands this proof rung without changing the target
shape. It keeps the same Docker-only SQLi/XSS Arena app and scorekeeper oracle,
but adds scenario-defined warm-pond exploit and defense candidates. Current
local live evidence under `/tmp/battle-v1-expanded-tau-032` recorded
`BATTLE_V1_OPERATIONAL_ACCEPTANCE_PASS`, `warm_pond.exploit_candidate_count=12`,
`warm_pond.defense_candidate_count=8`, `warm_pond.combination_count=96`,
`tau-live/manifest.json scheduling.granularity=worker`,
`scheduling.handoff_count=64`, `scheduling.worker_count=64`,
`scorekeeper.attempt_count=32`, `scorekeeper.passed_attempt_count=32`, and
`subagent-ledger.sqlite` event count `105`. This proves the current Battle
worker handoff adapter can drive Tau worker-granularity fanout at 32 Red and
32 Blue workers for this fixture. It still does not prove unbounded swarm
execution, Tau loop repair cycles, Scillm delegate/batch/tool execution, or a
production hidden-vulnerability generator.

The `battle-005` fixture adds compact scenario-driven warm-pond generation on
the same Docker-only SQLi/XSS Arena app. Current local preflight evidence under
`/tmp/battle-v1-generated-no-tau-003` recorded
`BATTLE_V1_OPERATIONAL_ACCEPTANCE_PASS`,
`warm_pond.warm_pond_generator.enabled=True`,
`generated_exploit_candidate_count=16`,
`generated_defense_candidate_count=8`, `combination_count=200`,
`scorekeeper.attempt_count=16`, and `scorekeeper.passed_attempt_count=16`.

The current live Tau scaling blocker is the 64 Red + 64 Blue worker run under
`/tmp/battle-v1-generated-tau-064`. Battle generated 128 worker handoffs and
Tau consumed them at worker granularity, but `tau-live/manifest.json` ended
`status=BLOCKED`, `process.exit_code=2`, `timeout_expired=false`, with 80
worker calls `PASS` and 48 `BLOCKED` on blank `scillm_http_error` at roughly
90 seconds. This is filed upstream as `grahama1970/tau#42`. Treat 64x64 Tau
live as pending until that Tau issue is resolved or Battle implements explicit
bounded backpressure/degradation.

The first live research-broker run exposed `agent-skills#51`: concurrent
Dogpile processes shared one partial-results temp file. The fix is in
`skills/dogpile/cli.py`: per-session partial-result paths plus PID-specific
temp files.

This proof still does not execute an unbounded swarm, Tau loop repair cycles,
Scillm delegate/batch/tool execution, QEMU/AFL campaigns, orchestrator-mutating
chat, or live websocket streaming. Its `$memory` proof uses `/recall` with the
`procedural_memory` recall profile for promoted `battle_mutation_memory`
records. If a `/list` fallback appears in the receipt, treat it as diagnostic
persistence evidence only, not semantic recall proof.

The current monitor proof now renders a narrow React+D3 artifact graph over the
generated `battle-003` context artifacts. `BattleForceGraph.tsx` uses D3 force
layout math and React-owned SVG DOM to connect Arena/Red/Blue/Judge players,
scorekeeper receipts, race signals, Docker fast scan, Brave research,
warm-pond candidates, bounded warm-pond execution, and the memory-upsert context
node. It is artifact-backed and fail-closed through `loadBattleArtifacts`; it is
not yet the final high-throughput Canvas/WebGL live attempt graph. Current proof
artifacts:

```text
skills/battle/monitor/battle/test-results/battle-monitor-v1-context-graph.png
.codex/ui-verification/latest.json
/tmp/codex-ui-verification/agent-skills/battle-monitor-v1-context-graph/20260628T150035Z.png
```

## Scoring System (AIxCC-style)

| Metric | Weight | Description |
|--------|--------|-------------|
| Vulnerability Discovery | 1x | Red team finds vulnerability |
| Exploit Proof | +0.5x | Red team proves exploitability |
| Successful Patch | 3x | Blue team patches vulnerability |
| Time Decay | Variable | Faster responses score higher |
| Functionality Preserved | Required | Patches must not break code |

### Scores

- **TDSR** (True Defense Success Rate): Vulnerabilities fixed AND code works
- **FDSR** (Fake Defense Success Rate): Attack blocked but code broken
- **ASC** (Attack Success Count): Total unique exploits discovered

## Game Loop (Learning-Based)

Each round follows a **learn → act → reflect** pattern:

```
Round k:

┌─────────────────────────────────────────────────────────────┐
│                    1. RESEARCH PHASE                         │
├─────────────────────────────────────────────────────────────┤
│ Red Team:                      Blue Team:                    │
│ - Recall past attack attempts  - Recall past defenses        │
│ - Query /dogpile for new       - Query /dogpile for          │
│   exploitation techniques        hardening strategies        │
│ - Review opponent's patterns   - Analyze attack evolution    │
│ (Budget: 3 research calls max)                               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    2. ACTION PHASE                           │
├─────────────────────────────────────────────────────────────┤
│ Red Team Attack:               Blue Team Defense:            │
│ - Execute learned strategy     - Apply patches via anvil     │
│ - AFL++ fuzzing with coverage  - Verify via QCOW2 overlay    │
│ - Collect crashes/findings     - Run regression tests        │
│ - Tag findings with /taxonomy  - Tag patches with /taxonomy  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   3. REFLECTION PHASE                        │
├─────────────────────────────────────────────────────────────┤
│ Both Teams:                                                  │
│ - Archive round episode (actions, outcomes, learnings)       │
│ - Store successful strategies in /memory                     │
│ - Update belief about opponent's capabilities                │
│ - Evolve strategy for next round                            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   4. SCORING & CHECKPOINT                    │
├─────────────────────────────────────────────────────────────┤
│ - Calculate AIxCC-style scores                               │
│ - Check termination conditions                               │
│ - Save checkpoint (QEMU state + team memories)              │
└─────────────────────────────────────────────────────────────┘
```

### Memory Architecture

Each team maintains isolated knowledge:

```
battle_red_<battle_id>/           battle_blue_<battle_id>/
├── strategies/                   ├── strategies/
│   ├── successful_attacks        │   ├── successful_patches
│   └── failed_attempts           │   └── broken_defenses
├── research/                     ├── research/
│   └── dogpile_results           │   └── dogpile_results
├── episodes/                     ├── episodes/
│   ├── round_001.json            │   ├── round_001.json
│   └── round_002.json            │   └── round_002.json
└── taxonomy/                     └── taxonomy/
    ├── cwe_classifications       ├── mitigation_types
    └── severity_scores           └── effectiveness_scores
```

Teams **cannot access opponent's memory** - this creates true adversarial learning.

## Termination Conditions

Battle ends when ANY condition is met:

1. **Null Production**: Both teams fail to generate new findings for 3 rounds
2. **Maximum Rounds**: Configured limit reached
3. **Metric Convergence**: Scores stable for 5 consecutive rounds
4. **Kill Switch**: Manual termination via `./run.sh stop`

## Task Monitor Integration

Battles register with task-monitor for overnight progress tracking:

```bash
# View battle progress in TUI
.pi/skills/task-monitor/run.sh tui --filter battle
```

## Report Output

After battle completion, generates:

- **Executive Summary**: Winner, key metrics, risk score
- **Vulnerability Report**: By severity, category, remediation status
- **Attack Evolution**: How Red team adapted over rounds
- **Defense Timeline**: Blue team improvements over time
- **Recommendations**: Prioritized security improvements

## Memory + Taxonomy Integration

The skill integrates with the shared memory and taxonomy systems via
`memory_integration.py` for cross-battle learning:

- **Pre-hook (`recall_prior_battles`)**: Before starting a battle, recalls prior
  battle findings for the same target or technique. Enables teams to build on
  accumulated security knowledge across battles.
- **Post-hook (`learn_battle`)**: After battle completes, stores the full outcome
  (target, red findings, blue defenses, winner, scores, TDSR) to memory with
  taxonomy bridge tags.
- **Bridge keywords**: Precision, Resilience, Fragility, Corruption, Loyalty, Stealth
  (tuned to security/exploitation domain).
- **Tags**: `["battle", "security"] + bridges`

Gracefully degrades if `common.memory_client` or `taxonomy/taxonomy.py` are unavailable.

## File Structure

```
battle/
  SKILL.md                   # This file
  run.sh                     # Shell entry point; launches package through uv
  sanity.sh                  # Deterministic fixture and structure sanity gate
  pyproject.toml             # Dependencies
  .ask/browser-oracles.yaml  # WebGPT project mapping for browser-oracle walk-up
  src/battle_skill/
    cli.py                   # Typer CLI entry point
    config.py                # Constants and paths
    state.py                 # Data classes and BattleState
    memory.py                # Team-isolated memory system
    scoring.py               # AIxCC-style scoring
    digital_twin.py          # Git worktree, Docker, QEMU isolation
    red_team.py              # Red Team attack agent
    blue_team.py             # Blue Team defense agent
    orchestrator.py          # Game loop orchestrator
    battle_fixture.py        # Deterministic fixture proof runner
    arena_docker_smoke.py    # Arena hidden-vulnerability Docker race proof
    battle_v1_operational.py # Four-party Docker operational proof
    judge.py                 # Deterministic scorekeeper verifier
    receipts.py              # Receipt dataclasses and JSON writer
    report.py                # Report generation
    qemu_support.py          # QEMU emulator support
    qemu_peripherals.py      # QEMU peripheral emulation
  fixtures/battle-001/       # Deterministic local fixture
  fixtures/battle-003/       # Arena hidden SQLi/XSS Docker race fixture
  monitor/battle/            # Artifact-backed React monitor
```

## Leveraged Skills

| Skill | Team | Purpose |
|-------|------|---------|
| hack | Red | Scanning, auditing, exploitation |
| anvil | Blue | Multi-agent patching (Thunderdome) |
| memory | Both | Recall prior strategies |
| treesitter | Blue | Code structure analysis |
| taxonomy | Both | Classify findings |
| task-monitor | Orchestrator | Progress tracking |
| ops-docker | Both | Container management |

## Example Battle

```bash
# Start 100-round battle on current project
./run.sh battle --target . --rounds 100

# Output:
# Battle ID: battle_20250128_221500
# Target: /home/user/project
# Rounds: 100
#
# Registering with task-monitor...
# Starting Round 1/100...
# [Red] Scanning target with hack...
# [Red] Found 3 potential vulnerabilities
# [Blue] Analyzing attack logs...
# [Blue] Generating patch for SQL injection...
# [Blue] Patch applied, running verification...
# Round 1 complete. Red: 3 pts, Blue: 9 pts
# ...
#
# Battle Complete!
# Winner: Blue Team (847 pts vs 423 pts)
# Report: ./reports/battle_20250128_221500.md
```
