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
  - dogpile
  - memory
  - treesitter
  - taxonomy
  - task-monitor
  - ops-docker
  - code-runner
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
taxonomy:
  - competition
  - selection
  - resilience
disciplines:
  - compliance-security
  - agentic-orchestration
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Battle Skill

**Red vs Blue Team Security Competition Orchestrator**

Pits a Red Team (attack) against a Blue Team (defense) in a long-running competitive loop. Each team leverages all `.pi/skills` to attack or defend a target codebase.


## Invariant battles (the common case)

Battle's default scoring targets exploitation (system-down, command injection),
but the most frequent real use of an adversarial Red/Blue loop is verifying a
PROJECT-SPECIFIC INVARIANT: "no PII value leaks", "the ledger balances", "the
parser drops no record", "the authz check cannot be bypassed".

Supply a pluggable invariant Judge -- a small independent module
`judge(target_dir, params) -> {passed, violations, evidence}` (schema
`battle.invariant_result.v1`). Red's objective becomes "produce an input that
makes the Judge fail"; Blue's is "make it pass"; the scorekeeper reads the Judge
result, never an agent's self-report. Judges are fail-closed: a judge that
errors is a FAILED invariant, never a silent pass.

```bash
python3 -m battle_skill.invariant_judge \
  --judge fixtures/reference-judges/no_data_leak_judge.py \
  --target <released-output-dir> \
  --params '{"policy": "policy.json", "output_subdir": "corpus"}'
```

`fixtures/reference-judges/no_data_leak_judge.py` is the anonymizer
confidentiality invariant as a Judge: it independently scans released output
(JSON scalars incl decoded escapes, numeric expansion, SQLite cells + schema
DDL + header integers, text/CSV, report.json, and captured stdout/stderr) for
any policy value in any representation.


## Contract variation-family research (generic Battle composition)

Battle is not project-specific. For any project or skill with an
`acceptance_contract.bundle.v1`, Battle should expand each contract item through
Dogpile before claiming comprehensive adversarial coverage:

```bash
./run.sh contract-variation-plan \
  --acceptance-bundle /path/to/acceptance_bundle.json \
  --dogpile-source brave-search \
  --dogpile-source arxiv \
  --out /tmp/battle-variation-plan.json
```

The output is `battle.contract_variation_plan.v1`. It maps every acceptance case
to source-bearing Dogpile research lanes and reusable variation families. Use
repeatable `--dogpile-source` filters when a Battle phase needs only selected
Dogpile providers such as `brave-search`, `arxiv`, `github-search`, `youtube`,
`brave-questions`, `feeds`, `wayback`, or `context7` instead of the full source
fanout. The reusable variation families include
representation equivalence, encoding/normalization, parser differentials,
release-surface boundaries, lossy conversion, split/composed facts, scale,
retry/concurrency, authorization, and failure-leak boundaries. Dogpile is research
input only: it discovers meaningful variation families and source evidence.
Battle then freezes selected families into deterministic generators, runs the
real target in Docker/QEMU/digital-twin evidence gates, emits `battle.case_receipt.v1`
per case, aggregates with `battle.campaign_aggregate.v1`, and retains the
workflow classes as `$agentic-evals` cases. A serious release gate should expect
hundreds of deterministic cases and roughly 20-30 retained eval classes when the
contract surface is broad; smaller smoke gates must label themselves as smoke.


## Invariant campaigns (test the contract floor, then attack beyond it)

An invariant *battle* judges one output. An invariant *campaign* has Red generate
the whole MATRIX of input "versions" the target's spec names -- every format x
every representation x the documented edge cases -- PLUS random fuzz, runs the
real target on each, and the Judge scores every output. Every case emits a
`battle.case_receipt.v1` with fixture precheck, execution, rejection, security
Judge, optional functional Judge, and verdict fields. A campaign PASSES only if
all case receipts pass, required `MUST_ACCEPT` cases are actually accepted and
functionally judged, required `MUST_REJECT` cases are safely rejected, and the
computed `battle.campaign_aggregate.v1` has no failed or incomplete cases. One
failing version is a concrete, reproducible Red win.

For anonymization/privacy targets, the acceptance contract is only the floor.
When an `acceptance_contract.bundle.v1` exists, the arena build may pass it as
`acceptance_floor` to the production adapter. Battle then fails closed unless
every `acceptance_cases[]` id maps to at least one campaign generator case in the
profile's `required_case_ids`; those are the bare-minimum adversarial versions
that MUST pass before any extra fuzz or beyond-contract cases matter. Battle must
also run a beyond-contract campaign that attacks surfaces a client brief often
omits: JSON keys and duplicate keys, CSV headers/dialects/multiline cells,
SQLite identifiers/defaults/generated values/partial indexes/triggers,
filenames, report.json, stdout/stderr, alternate encodings, and same-identity
representation traps. A clean brief-matrix replay alone is a smoke proof, not a
comprehensive Battle proof.

```bash
python3 -m battle_skill.invariant_campaign \
  --generator fixtures/reference-generators/anon_brief_matrix.py \
  --target-run-cmd 'docker run --rm -v {input}/corpus:/trial/input/corpus:ro -v {input}/policy.json:/trial/input/policy.json:ro -v {output}:/trial/output anonymization-trial run' \
  --judge fixtures/reference-judges/no_data_leak_judge.py \
  --gen-params '{"fuzz": 20}' --judge-params '{"output_subdir": "corpus"}'
```

`fixtures/reference-generators/anon_brief_matrix.py` yields the anonymization
brief's versions: the four formats, JSON string/int/float/scientific, SQLite
TEXT/INTEGER/REAL, Unicode NFC/NFD, BOM, JSON \u-escape, SQLite CHECK-literal,
plus fuzz. It also carries the oai-trial roundtable edge cases: formatted policy
phone values stored as digit-only JSON/SQLite numerics, the same identity seeded
across every in-scope format, and lossy leading-zero / large-float traps.
`fixtures/reference-generators/anon_beyond_brief_matrix.py` is the required next
rung for privacy/anonymization proof: it tries non-obvious schema/path/encoding/
log/release-boundary surfaces that go beyond the literal acceptance contract. A
generator + target-run-cmd + judge is a pluggable trio: point it at any project's
spec matrix and invariant.

The no-data-leak Judge also supports an explicit opt-in interpretation profile
for transformation semantics. These guarantees are OFF unless declared in
`--judge-params`, so Battle does not silently expand the contract after seeing a
failure:

```json
{
  "interpretation_profile": {
    "decoders": ["base64", "base64url", "hex"],
    "record_local_reconstruction": true,
    "max_decoded_bytes": 4096
  }
}
```

With that profile, whole scalar/token base64/base64url/hex values are decoded
once and record-local adjacent JSON/CSV/SQLite scalar fields may reconstruct a
complete policy value. Arbitrary recursive decoding, global field joins, and
visual-confusable character folding remain out of the default blocking gate.

After Red finds failing cases and Blue patches the target, emit the replayable
lineage receipt instead of summarizing in prose:

```bash
./run.sh invariant-lineage-receipt \
  --red-campaign /tmp/red-result.json \
  --replay-campaign /tmp/replay-result.json \
  --target oai-trial \
  --out /tmp/battle-lineage.json
```

A `battle.invariant_adaptive_lineage.v1` PASS proves Red found contract edge
cases, Blue removed those Red wins, and the independent Judge replay passed.

Then Battle must produce a `$create-report`-validated report with `$project-state`
context and an explicit exploits table. The report is the human-readable decision
artifact; receipts remain the authority. Generate fresh project state first,
then render the report:

```bash
PROJECT_STATE_ROOT=/path/to/target ../project-state/run.sh report --json --output /tmp/project-state.json
./run.sh invariant-report \
  --campaign /tmp/battle-brief-fuzz.json \
  --campaign /tmp/battle-beyond-brief.json \
  --adaptive-lineage /tmp/battle-lineage.json \
  --project-state /tmp/project-state.json \
  --target oai-trial \
  --out-json /tmp/battle-report.json \
  --out-md /tmp/battle-report.md
```

`invariant-report` writes `create_report.report.v1`, validates it through
`skills/create-report/run.sh validate`, renders Markdown through
`skills/create-report/run.sh render`, and appends `## Exploits Table`. The table
must be plain-spoken and scannable: one row per attack case, with columns for
`Scope`, `Contractual?`, `Adaptive lineage?`, `Case`, `Exploit / attack`,
`Why chosen`, `Expectation`, `Result`, and `Judge evidence`. `Scope` separates
`contractual` acceptance-floor cases from `beyond-contract` probes;
`Why chosen` explains non-contractual probes; `Adaptive lineage?` marks Red wins
that were fixed and replayed; `RED_WIN` blocks release. The table is derived
from `battle.case_receipt.v1` when present, falling back to legacy `case_log`
only for older campaign receipts. A Battle closure without that report is
missing the decision surface even if campaign receipts pass.

## Purpose Boundary

Battle's purpose is the Red/Blue security competition backend: authorized target
setup, isolated execution, Red attack generation, Blue defense generation,
independent Judge replay, scorekeeper receipts, adaptive lineage, and durable
learning. Adaptive lineage is a backend learning loop that spawns, evaluates,
selects, and promotes or rejects child Red/Blue evidence from Judge-backed
receipts.

PixiJS is only a spectator/replay surface for Battle receipts. A PixiJS pass
proves that recorded receipts can be inspected in a fun replay; it does not
prove the Battle orchestrator, provider-driven subagents, Docker/QEMU isolation,
overnight scheduler, scorekeeper, or memory learning works. Do not close core
Battle readiness from PixiJS evidence alone, and do not block backend adaptive
lineage on replay polish beyond truthful receipt inspectability.

## Architecture

Production Battle is an orchestration skill, not a large bespoke security
engine. The host-side process should schedule rounds, choose personas, dispatch
subagents, provision Docker runtimes, collect receipts, score hard runtime
signals, write reports, and persist learning. Target code and team-generated
code must execute only inside Docker.

Required production invariants:

- Red and Blue are subagent teams. Each dispatched subagent must include an
  explicit persona selected by the orchestrator for that turn. Multiple personas
  per team may run concurrently when the turn benefits from breadth.
- Battle execution requires a `security.target_authorization.v1` manifest before
  Docker, QEMU, target runtime setup, Hack delegation, proof replay, or patch
  replay starts. The manifest binds project/operator scope and target identity;
  it is not a legal opinion and does not prove exploit success or patch
  effectiveness.
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
- SciLLM is a Tau-owned provider sidecar. Battle operators and project agents
  must not call `$scillm`, `/scillm`, `http://localhost:4001`,
  `/v1/chat/completions`, or `/v1/scillm/*` directly for Battle proof work.
  Express provider work as Tau DAGs, Tau command-loop nodes, or Tau skill nodes,
  then consume Tau receipts and node outputs.
- Model choice is strategic but routed through Tau/loop: SOTA models for
  planning, small fast models for high-throughput mutation generation and
  triage, specialist models for language/security niches, and batch calls for
  broad candidate generation.
- Red and Blue have free research access through approved agent-side research
  skills, including `dogpile`, `brave-search`, `memory`, GitHub/code search,
  docs, papers, CVEs, and public writeups.
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
- Dogpile research receipts are design input for Battle, not proof. Use them to
  seed Red exploit-family menus, Blue hardening/detection menus, GitHub
  security-tool candidates, DARPA/AIxCC context, and follow-up research
  questions. Exploit success, patch effectiveness, tool safety, and repository
  adoption still require Battle-owned Docker/QEMU execution, hard runtime
  signals, and Judge replay.
- Security repositories found through Dogpile must flow through `$github-search`
  evaluation criteria first. Any adopted repo code, PoC, scanner, or payload
  still runs only inside Battle's isolated target/runtime gates; do not execute
  untrusted repo-provided install scripts or payloads on the host.
- Target containers default to no network. External research happens from the
  agent side through controlled skills unless a scenario explicitly grants
  target-container network access.
- The scorekeeper records objective outcomes: system down, system still up after
  the allotted time, exploit success, crash artifacts, patch timing, regression
  behavior, resource limits, and replay results. It is not an LLM judge.

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

# Run the reactive Blue + independent Judge Docker proof
./run.sh prove-reactive-judge-round \
  --authorization-manifest skills/battle/fixtures/reactive-judge/authorization.json \
  --out /tmp/battle-reactive-judge-round

# Run canonical BATTLE-004 with parent-spawn lineage requested
./run.sh arena-parent-spawn-proof battle-004 --out /tmp/battle-004-parent-spawn --red-workers 2 --blue-workers 2
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

## Reactive Judge Round Proof

`prove-reactive-judge-round` is the deterministic local Docker proof rung for
the default Battle round authority boundary. It runs a small authorized fixture
with one command-injection behavior and one candidate patch:

```text
mocked: no
live: local_docker_fixture
agentic: false
models_used: []
```

The proof emits:

- `authorization-validation.json`
- `immutable-baseline-manifest.json`
- `event-ledger.json`
- `red-hack-observation.json`
- `judge-1/judge-1-receipt.json`
- `blue/proactive-blue-input.json`
- `blue/reactive-blue-input.json`
- `blue/candidate-patch-receipt.json`
- `judge-2/judge-2-receipt.json`
- `scorekeeper-receipt.json`
- `round-receipt.json`
- `artifact-hash-manifest.json`

The required phase order is authorization, immutable baseline, concurrent Red
and proactive Blue, Red observation, Judge #1 confirmation, reactive Blue,
candidate patch, Judge #2 replay, scorekeeper, and round receipt. Proactive Blue
must receive no private Red finding. Reactive Blue may receive only the
Judge-confirmed finding and replay contract. The scorekeeper derives Red/Blue
scores only from Judge receipts; Blue `verified`, `success`, and
`functionality_preserved` fields are advisory and not score authority.

The ordinary in-process `battle` round now fails closed at this same authority
boundary: it preserves proactive overlap, dispatches reactive Blue only for
Judge-confirmed findings, and does not award Blue score without a Judge #2
success verdict. The local Docker proof is the executable receipt path for the
complete reactive/Judge behavior. It does not prove provider-driven Red/Blue
quality, arbitrary target exploitability, production deployment readiness, or
overnight scheduler readiness.

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

## Nondeterministic Exploit Specimen Synthesis

Battle Red agents may behave as nondeterministic exploit-code authors. A Red
exploit subagent may combine high-level web, protocol, MITM, packet, timing,
source-level, binary, assembly, fuzzing, and obscure research-derived
techniques into generated exploit specimens.

Most generated specimens may be bad ideas: they may fail to compile, fail at
runtime, combine irrelevant methods, or produce no useful target signal. Battle
treats those outputs as genetic material, not proof.

Battle owns deterministic selection and evidence:

- generated code must be materialized as an artifact;
- generated code must run only in Docker;
- stdout, stderr, HTTP observations, timing, exit code, and optional packet
  summaries must be captured;
- runnable code is not exploit success;
- target contact is not exploit success;
- Judge replay is required before any exploit-success claim;
- memory promotion requires replayable evidence.

The first backend proof rung is `exploit-combiner-proof`. It is fixture-backed,
`agentic:false`, and proves the specimen lifecycle only: bad generated code,
Docker execution, captured failure observations, target contact, runnable
unproven code, and fail-closed non-claims. Live Tau generation, child
materialization, packet capture, Blue adaptation, memory promotion, and Judge
exploit-success replay are later rungs.

The second backend proof rung is `spawn-architect-proof`. It is fixture-backed,
`agentic:false`, and proves the DAG birth contract only: Battle loads a
spawn-policy decision, constructs a child knowledge packet from parent specimen
evidence, authors a `tau.dag_contract.v1` child exploit-synthesis DAG, validates
private-artifact exclusions, and records that Tau execution is deferred to PR3.
It does not run Tau, materialize a child exploit, generate live exploit code,
compile child code, contact the target, or claim exploit success.

The current live Tau child DAG canary is `live-tau-child-dag-canary`. It is
non-mocked and invokes the existing local Tau DAG runtime without fixture
fallback. The PR3b/PR3c boundary is:

```text
lineage-summarizer PASS
research-scout PASS with Tau-validated source-bearing design-input receipts
method-combiner PASS with a deterministic exploit genome candidate
exploit-code-author PASS only when Tau/SciLLM returns provider_live:true
provider-authorship evidence; otherwise BLOCKED at the precise attestation gap
```

The PR3c boundary may materialize provider-authored child exploit code, but it
does not compile child code, run a child specimen in Docker, or claim exploit
success. Compile repair, Docker execution, and Judge replay are later gates.

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
    judge.py                 # Deterministic scorekeeper verifier
    receipts.py              # Receipt dataclasses and JSON writer
    report.py                # Report generation
    qemu_support.py          # QEMU emulator support
    qemu_peripherals.py      # QEMU peripheral emulation
  fixtures/battle-001/       # Deterministic local fixture
  spectator/               # Self-contained BATTLE-004 spectator UI + Pixi engine
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
