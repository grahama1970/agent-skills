# Battle

![Battle card](../../docs/assets/project-cards/battle.webp)

Battle is a Red vs Blue security competition skill. It creates isolated target
workspaces, lets Red attack and Blue defend, scores the round outcomes, and
preserves enough state to resume, report, or inspect a long-running campaign.

The skill is designed for adversarial security work, not generic task routing:
Red finds and proves vulnerabilities; Blue patches or hardens; the orchestrator
tracks rounds, scores, termination conditions, and reports.

Agents must treat [`SKILL.md`](SKILL.md) as the runtime contract. This README is
the human/operator guide.

## Use It For

| Need | Start here |
|---|---|
| See available Battle commands | `./run.sh --help` |
| Run a source-code Red vs Blue round | `./run.sh battle /path/to/codebase --rounds 10` |
| Inspect recent battle state | `./run.sh status` |
| Generate a battle report | `./run.sh report <battle-id>` |

## Operating Contract

Battle's production shape is intentionally simple:

```text
cron/orchestrator
  -> choose Red and Blue personas for the turn
  -> call modular Tau subagent contracts
  -> Tau uses loop / agentic harness execution
  -> loop / agentic harness uses $scillm for LLM calls
  -> run all target/team code inside Docker
  -> observe whether the system goes down or remains up
  -> write scorekeeper receipts and reports
  -> store learnings in $memory
```

The orchestrator may select one persona per team or multiple concurrent
personas per team. Every dispatched subagent must have an explicit persona
attached. Persona selection is part of the strategy surface: it encourages
creative, non-identical, and less predictable approaches while preserving the
same Tau-style schema and evidence requirements for every actor. Red and Blue
have free research access through approved agent-side skills such as `$dogpile`,
`$brave-search`, `$memory`, GitHub search, papers, docs, CVEs, and writeups.
That research freedom does not grant host execution. All target code and all
team-generated executable code runs inside Docker.

Tau is the modular subagent contract/orchestration layer for Battle. Battle
selects teams, personas, budgets, target runtimes, and score rules, then emits
Tau-style handoffs. Tau and the loop/agentic harness own subagent execution.
That harness uses `$scillm` as the LLM/model caller, giving teams access to SOTA
models, small/fast low-parameter models, and narrow specialist models without
making Battle a direct provider router.

Hard invariants:

- Host code is control plane only: schedule, dispatch, mount/copy, collect,
  score, and report.
- Target apps, exploit probes, fuzzers, payloads, repro scripts, patch builds,
  tests, migrations, dependency installs, and replay checks run in Docker.
- Docker target runtimes are disposable between rounds when needed.
- Persistent volumes carry only the round state that must survive a rebuild or
  relaunch, such as target data volumes, baseline source snapshots, Blue patch
  workspaces, crash artifacts, and scorekeeper evidence.
- Strategic context, summaries, lessons, persona performance, exploit/patch
  observations, and cross-round learning are stored in `$memory`, not only in
  local files.
- Target containers default to no network. Red and Blue research happens from
  the agent side through controlled skills unless a scenario explicitly grants
  target-container network access.
- Docker images/toolchains are selected or built dynamically for the target
  language stack. Any language required by the target may be added to the
  runtime image; Battle should not reimplement language-specific build logic.
- Model selection is strategic but routed through Tau/loop. Different personas
  and tasks may use different `$scillm` models: high-reasoning SOTA models for
  planning, low-parameter fast models for mutation generation or triage,
  specialist models for language/security niches, and batch calls for broad
  candidate generation.
- Throughput is a design goal. On a capable workstation, Battle should be able
  to schedule thousands of isolated exploit or defense mutations, with tight
  10-15 second attempt windows when the Docker runtime already has the required
  language/toolchain.
- Research can burst when needed. Red and Blue may run multiple concurrent
  `$brave-search` and `$dogpile` calls from the agent side, including 10x
  parallel Brave searches for fast strategy discovery, then store useful
  findings and dead ends in `$memory`.
- Search should be combinatorial. Red should try any and every plausible exploit
  family and combination within safety/time budgets; Blue should do the same for
  patch, hardening, configuration, testing, detection, and mitigation
  combinations. Feedback from Docker outcomes determines what gets promoted.

Round scoring is environment-outcome based. Red wins when the target goes down,
crashes, leaks, violates an invariant, or remains exploitable inside the
allotted time. Blue wins when the target remains up through the allotted time,
the patch/hardening lands before failure, required behavior still works, and
Red's current exploit no longer succeeds. The scorekeeper records hard signals;
it is not an LLM judge.

## Round Loop

Each round is a learning and mutation cycle:

```text
1. Recall
   - read prior Battle round receipts and summaries from $memory
   - inspect project knowledge for current campaign state
   - use $memory code_symbols / ingest-code output for target structure

2. Research
   - Red and Blue run $dogpile / $brave-search / GitHub / docs / CVE research
   - the orchestrator may fan out concurrent research calls when speed matters
   - each team researches freely from the agent side

3. Mutate
   - orchestrator chooses explicit personas for each subagent
   - Red tries many penetration ideas, including rough or unlikely ones
   - Red mixes high-level and low-level techniques: auth bypasses, parser abuse,
     dependency attacks, fuzzing, memory corruption, race conditions, config
     mistakes, protocol quirks, payload chains, and crash reproducers
   - Red intentionally tries odd combinations because warm-pond evolutionary
     exploit search depends on mutation, recombination, and selection
   - Blue tries patch, hardening, test, config, and mitigation variants
   - both teams combine candidate tactics aggressively instead of testing only
     one neat idea at a time
   - all executable attempts run inside Docker
   - short-lived Docker attempts are scheduled aggressively when the runtime is
     already warm and has the required language support

4. Score
   - system down before allotted time favors Red
   - system still up after allotted time with behavior preserved favors Blue
   - scorekeeper writes objective receipts and artifacts

5. Promote
   - successful exploit, patch, defense, persona, and research strategies are
     promoted into $memory for future rounds
   - successful combinations are promoted more strongly than isolated tactics
     because the interaction is often the winning strategy
   - failed or low-value mutations are retained as negative evidence so teams
     avoid repeating them blindly
```

This is intentionally evolutionary. Battle should try many ideas, including
some that are naive, strange, or cross-layer combinations of high-level and
low-level exploits, because surprising attacks and defenses can win. The gate is
not whether an idea sounds elegant; the gate is whether Docker evidence shows
that it brought the system down or kept it up. Successful mutations are
promoted; failed mutations remain searchable negative evidence.

## Current Surfaces

Battle currently exposes two useful surfaces:

1. **Battle orchestrator** for multi-round Red vs Blue runs over source,
   container, or firmware targets.
2. **Battle v0** for a deterministic one-round fixture proof with Red, Blue, and
independent Judge receipts.

Battle v0 is the safer first rung to run when checking the artifact contract. It
does not exercise live Red or Blue agents.

## Quickstart

Run from `skills/battle`:

```bash
./run.sh --help
```

Run a normal source-code battle:

```bash
./run.sh battle /path/to/codebase --rounds 10
```

Run an overnight battle:

```bash
./run.sh battle /path/to/codebase --overnight
```

Run a Docker target:

```bash
./run.sh battle --docker-image myapp:latest --rounds 100
```

Run a QEMU/firmware target:

```bash
./run.sh battle firmware.bin --qemu-machine arm --rounds 100
```

Inspect recent battles:

```bash
./run.sh status
```

Resume a paused battle:

```bash
./run.sh resume <battle-id>
```

Generate a report:

```bash
./run.sh report <battle-id>
```

## Battle v0 Fixture Proof

Battle v0 runs a deterministic fixture:

```text
Red proves a seeded path traversal exploit
Blue applies a deterministic patched file
Judge verifies the synced arena independently
Scoreboard derives from the Judge receipt
Monitor renders generated artifacts
```

Run it from `skills/battle`:

```bash
./run.sh battle-fixture battle-001 --out /tmp/battle-001
```

Expected backend artifacts:

```text
/tmp/battle-001/battle-plan.json
/tmp/battle-001/red-receipt.json
/tmp/battle-001/blue-receipt.json
/tmp/battle-001/judge/judge-receipt.json
/tmp/battle-001/scoreboard.json
/tmp/battle-001/monitor-index.json
/tmp/battle-001/run-receipt.json
```

The Battle v0 run receipt states the claim boundary:

```text
mocked: no
live: local_deterministic_fixture
agentic: false
models_used: []
```

This proves only the deterministic fixture contract. It does not prove real Red
agent behavior, real Blue agent behavior, scillm, OpenCode, anvil, code-runner,
memory learning, Docker, QEMU, or multi-round campaign readiness.

## Normalized UX JSON Contract

Battle can emit a normalized JSON fixture for the spectator UX. The UX must
render this contract as data; it must not infer child lanes, Blue kills, fastest
crashes, survivor promotions, or live replay actions from sparse receipts.

Generate a canonical BATTLE-004 parent-spawn proof when fresh receipt-backed
lineage data is needed:

```bash
./run.sh arena-tau-public-only-proof battle-004 \
  --spawn-red-child-on-blue-success \
  --red-workers 1 \
  --blue-workers 1 \
  --out /tmp/battle-004-parent-spawn-proof
```

The parent-spawn flag is fail-closed: Battle first requests one parent Red lane,
Judge-replays the parent against Blue, and requests one child Red lane only when
the parent lane has a `BLUE_SUCCESS` handoff. The emitted
`run-receipt.json#lineage_request` records whether lineage was requested and
whether `lineage-receipts.json` was produced.

Generate normalized JSON from a Battle proof directory:

```bash
./run.sh generate-ux-fixture \
  --input /path/to/battle-proof \
  --battle-id battle-004 \
  --out /tmp/battle-004.normalized.json
```

Validate the backend values, portable JSON Schema, and fail-closed render
guards:

```bash
./run.sh validate-ux-contract /tmp/battle-004.normalized.json
```

Validate the checked-in backend handoff bundle before a renderer consumes it:

```bash
./run.sh validate-ux-handoff-summary local/battle-004-ux-json-contract-summary.json
```

Stable local JSON handoff artifacts are checked into the Battle skill for UI
implementers and reviewers:

```text
local/battle-004-parent-spawn.normalized.json
local/battle-004-sparse.normalized.json
local/battle-004-ux-json-contract-summary.json
```

The parent-spawn artifact is receipt-backed with `mocked=false`,
`lineage.mode=receipt_backed`, and `child_spawn_count=1`. The sparse artifact is
receipt-backed with `mocked=false`, `lineage.mode=missing`, and
`child_spawn_count=0`. The summary file names both artifacts and is covered by
`tests/test_battle_event_adapter_contract.py`, which validates that the summary
matches the actual local normalized JSON values.

The local handoff summary locks the canonical BATTLE-004 source contract to
`/api/import-zip`, `CWE-22`, and Zip Slip path traversal. The validator compares
both local normalized fixtures against that lock and fails closed if a fixture
drifts to another route, CWE, vulnerability family, or shell title.

The portable JSON Schema enforced by `validate-ux-contract` is:

```text
schemas/battle.normalized_ux_fixture.v1.schema.json
```

The validator checks that:

- `scenario.public_entrypoint` is a path such as `/api/import-zip`, not a
  method-prefixed label.
- `spectator_shell` provides receipt-backed header, fact chip, score, round
  time, and receipt ticker values for the shell. The UX should render these
  values instead of hard-coding mockup copy or labeling receipt playback as
  live execution.
- `renderer_binding_contract` provides exact JSON path bindings for the shell,
  round time, scrollable timeline, moving playhead, parent spawn/collapse,
  lane label/activity layout, Agent Detail cockpit, and Docker replay CTA.
  This is a data contract for renderer implementers, not visual design authority. Optional Pixi race renderer: `docs/BATTLE_RACE_ENGINE_PIXI_SPIKE.md` (Phase 1 spike; DOM remains default)
  direction.
- `lineage_request` records requested/not-requested/proven parent-spawn state.
  It is explanatory state only; the UX must not render child lanes from
  `lineage_request` without matching `lineage.spawns[]` receipt records.
- `lineage.spawn_count`, `scoreboard.child_spawn_count`, and
  `ux_contract.receipt_backed_values.child_spawn_count` agree.
- Parent/child lane relationships exist only when a lineage receipt names both
  lanes.
- `tau.spawned_child` is absent when lineage is missing.
- `lineage.groups[]` and lane `lineageGroupId`/`collapsible` fields agree so
  the UX can render parent/child collapse state without inferring it.
- `blue.blocked_red` targets are backed by `scoreboard.per_pair`
  `BLUE_SUCCESS` verdicts.
- Replay buttons remain receipt-only unless replay metadata provides an
  executable endpoint or command receipt.
- `timeline.playhead` and `timeline.viewport` are present as receipt replay
  values; they must not be treated as live stream proof.
- `timeline.playhead.keyframes[]` lists receipt-backed lane event positions
  sorted by `x`, so the renderer can animate a moving playhead as receipt
  replay rather than live stream execution.
- Lane event markers include `label_band`, `marker_priority`, and
  `collision_group` so the renderer can avoid overlapping labels/icons without
  inventing placement rules.
- Lane `activitySegments[]` provides between-marker action phases such as
  research, payload, useful signal, handoff, patch gate, and Judge replay.
  The UX should render these values instead of inventing exploit activity.
- Lane `cockpit` is the authoritative Agent Detail/right-pane payload. It
  contains Tau identity, current turn, six public-trace fields, stdout/stderr,
  skill/tool proof labels, learned/next move, Blue outcome, latest receipt, and
  replay CTA state. The UX should not infer these values from lane labels.
  Use these exact field paths:
  `lane.cockpit.selected_tau_exploit_subagent`,
  `lane.cockpit.current_turn`, `lane.cockpit.public_trace`,
  `lane.cockpit.output.stdout`, `lane.cockpit.output.stderr`,
  `lane.cockpit.skills_tools`, `lane.cockpit.blue_outcome`,
  `lane.cockpit.latest_receipt_id`, and `lane.cockpit.replay`.
  `lane.cockpit.replay` must mirror `lane.replay` so the Agent Detail pane and
  lane-level Docker replay CTA cannot drift.
- Child lane event x-positions are rebased to the child lane `xStart`; a child
  lane must not show research, payload, patch, or Judge events before its
  receipt-backed spawn point.
- `lane.replay.cta` is present when a Judge replay receipt exists. The CTA
  label is `REPLAY IN DOCKER`, but it must stay `state=receipt_only` with a
  `disabled_reason` unless `lane.replay.can_execute_now=true` and an executable
  replay endpoint or command receipt is attached.

The skill sanity gate validates the stable local UX fixtures by default and can
also validate an extra generated UX fixture:

```bash
BATTLE_UX_CONTRACT_FIXTURE=/tmp/battle-004.normalized.json ./sanity.sh
```

## Battle Monitor

The Battle monitor is artifact-backed. It must load generated JSON from:

```text
/artifacts/battle-001/monitor-index.json
/artifacts/battle-001/scoreboard.json
/artifacts/battle-001/red-receipt.json
/artifacts/battle-001/blue-receipt.json
/artifacts/battle-001/judge/judge-receipt.json
```

To inspect the generated run in the monitor:

```bash
cd /path/to/agent-skills/skills/battle
rm -rf monitor/battle/public/artifacts/battle-001
mkdir -p monitor/battle/public/artifacts/battle-001
cp -R /tmp/battle-001/* monitor/battle/public/artifacts/battle-001/

cd monitor/battle
npm install
npm run build
npm run test:e2e
```

The monitor must fail closed with `BATTLE MONITOR BLOCKED` if required generated
artifacts are missing or unreadable.

The production monitor should be a modern React + Tailwind + shadcn + D3
tracking interface, not a decorative dashboard. Its primary object is the active
battle round: selected personas, Docker runtime state, uptime/down timer,
subagent receipts, exploit/patch evidence, scorekeeper signals, persistent
volume/artifact state, and `$memory` learning writes.

The D3 layer should visualize Red and Blue activity in near real time:
exploit/defense attempts, combinations, persona lanes, container attempts,
crashes, patches, scorekeeper events, promotions, and negative-evidence trails.
The interaction model should feel closer to an Unsloth Studio training run view
than a static report: a live stream of attempts, metrics, rates, current
leaders, resource pressure, and promotion decisions, with enough detail to
inspect a specific attempt without losing the global race.
Because Battle stores attempts, outcomes, promotions, failures, personas, and
code-context links in `$memory`, the monitor should also expose a live graph
view of related exploit and defense mutations. Nodes can represent exploit
families, concrete attempts, payload chains, target code symbols, Blue
mitigations, personas, and promoted memories. Edges can represent mutation,
recombination, blocked-by, promoted-from, code-symbol, same-CWE, same-endpoint,
or same-crash relationships. Graph traversal and BM25 recall from `$memory`
should drive search, clustering, and "show related attempts" interactions.
For 100s or 1000s of live exploit attempts, prefer a Canvas/WebGL graph layer
such as a React force-graph or PixiJS-style renderer using D3 force/layout math,
not one SVG element per event. Keep SVG/React for axes, labels, selection
chrome, tooltips, accessible summaries, and the right-sidebar drill-down. The
operator should be able to click a node or event and answer immediately: what
exploit is being tried, where it is occurring, what status it is in, what Blue
did in response, whether the system stayed up, and whether the mutation was
promoted to `$memory`.
Use React for DOM ownership and D3 for scales/layout/math. Use keyed data,
`ResizeObserver`, responsive `viewBox`, colorblind-safe redundant encodings, and
a hidden accessible data table. For thousands of live attempts, use a Canvas/SVG
hybrid: Canvas for dense event streams and SVG/React for axes, labels,
selection, and sidebar-linked detail.

The monitor also needs a right-sidebar chat/interjection surface, following the
same operational role as the Watch-style human review sidebar: the human can
course-correct, pause, redirect persona selection, approve or reject a proposed
goal change, and add context without breaking the artifact trail. Sidebar
messages must become schema-valid handoffs or human-interjection records before
they affect the orchestrator. Interactive controls must have stable
`data-qid`, `data-qs-action`, and `title` attributes, and UI acceptance requires
a fresh live CDP screenshot plus the Playwright checks.

Battle Monitor v1 includes the first local version of this sidebar. It uses the
same shared-chat interaction pattern as Watch: starter chips, message bubbles,
composer, stable `data-qid` selectors, and `data-qs-action` command hooks. In
v1, submitted messages create local `battle.human_interjection.v1` preview
receipts only. They do not yet mutate Tau, cron, Docker execution, persona
selection, or scorekeeper state.

## Architecture

The skill root is an entrypoint and documentation surface. Python
implementation lives under `src/battle_skill/`; normal users and agents should
invoke `./run.sh` rather than importing root-level files.

Core modules:

```text
src/battle_skill/cli.py Typer CLI entry point
src/battle_skill/orchestrator.py multi-round game loop
src/battle_skill/digital_twin.py git worktree, copy, Docker, and QEMU isolation
src/battle_skill/red_team.py Red Team attack agent
src/battle_skill/blue_team.py Blue Team defense agent
src/battle_skill/scoring.py AIxCC-style scoring
src/battle_skill/state.py BattleState and round data classes
src/battle_skill/memory.py team-isolated memory
src/battle_skill/memory_integration.py shared memory and taxonomy hooks
src/battle_skill/report.py Markdown report generation
```

Battle v0 modules:

```text
src/battle_skill/battle_fixture.py deterministic fixture runner
src/battle_skill/judge.py deterministic scorekeeper-style verifier
src/battle_skill/receipts.py receipt dataclasses and JSON writer
fixtures/battle-001/    seeded path traversal target and patch
monitor/battle/         React artifact monitor and Playwright checks
docs/BATTLE_V0.md      detailed Battle v0 validation contract
```

## Scoring Terms

- **ASC**: Attack Success Count, unique exploits discovered.
- **TDSR**: True Defense Success Rate, vulnerabilities fixed while functionality
  still works.
- **FDSR**: Fake Defense Success Rate, attack blocked but functionality broken.

Battle v0 preserves `INSUFFICIENT_EVIDENCE` as a first-class status. It does not
collapse insufficient evidence into failure, because a failed battle and an
unscoreable battle are different operational states.

## Evidence Discipline

For Battle reports, use explicit proof language:

```text
mocked: yes|no
live: yes|no or named local/live scope
what was exercised
what remains unverified
artifact paths
```

Receipts are evidence carriers, not the work itself. A Blue patch claim is not
accepted as a successful defense until an independent Judge or equivalent
deterministic gate verifies exploit blocking and regression behavior.

## Skill Integration Notes

- `$hack` is a sibling skill. Battle must delegate to it through skill/Tau
  contracts, not `import hack`.
- Red-team `$hack` usage belongs behind an `agent-skills/agents` subagent
  dispatch. Battle chooses the persona, passes the target/scenario and candidate
  exploit list after scan/research/memory recall, and then collects the
  subagent receipt.
- `$memory` is accessed through its HTTP API (`POST /recall`, `POST /store`) via
  `httpx`, not raw ArangoDB imports or deprecated CLI learn calls.
- `$webgpt-review` resolves the dedicated Battle reviewer tab through
  `.ask/browser-oracles.yaml` and `$browser-oracle`.

## Storage Notes

Generated monitor dependencies should not live as a real `node_modules`
directory inside the skill folder. Use the workspace storage policy: keep heavy
dependency directories on `/mnt/storage12tb` and symlink them back when needed.

Battle runtime state defaults to:

```text
/mnt/storage12tb/skills/battle/
```

The skill root should not contain real `artifacts/`, `battles/`, `reports/`,
`worktrees/`, `.venv/`, or `node_modules/` directories.

Current Battle monitor convention:

```text
skills/battle/monitor/battle/node_modules ->
/mnt/storage12tb/skills/battle/monitor-battle/node_modules
```

## Current Limits

The deterministic Battle fixture is intentionally narrow. Production Battle
readiness still requires separate proof for:

- live Red and Blue agent behavior
- `hack`, `anvil`, and `code-runner` integration
- scillm or OpenCode-backed agent execution
- memory learning before and after rounds
- Docker-only target execution, dynamic language runtimes, and persisted volumes
- Tau-style subagent schemas, persona selection, and cron orchestration
- multi-round campaign convergence and termination behavior
- report correctness over real battle state
