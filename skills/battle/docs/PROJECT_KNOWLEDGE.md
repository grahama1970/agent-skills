# Project Knowledge: battle

**Last updated:** 2026-07-04 14:51 by agent
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
- Arena constrains the project context, target language, entry point, hidden bug
  class, runtime image/profile, and allowed language sets. Red and Blue then
  choose their own implementation language/tooling dynamically from that allowed
  surface, and receipts must record `red_selected_language` and
  `blue_selected_language`.
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
- Fair Arena battles require a level playing field: Arena/Judge may know the
  private answer key, but Red and Blue must receive the same public bundle at
  the same time. Red should not know Blue's patch, Blue should not know Red's
  exploit in the first proactive-defense phase, and neither team should know the
  hidden bug class, CWE, finding id, oracle source, safe patch template, or how
  many hidden vulnerabilities exist unless the public scenario intentionally
  says so.
- The next live Battle rung must use the Tau harness for Red/Blue execution.
  Battle should emit `tau.agent_handoff.v1` handoffs that reference only
  `arena/team-public/`; Tau/loop owns subagent execution and can call `$scillm`
  behind that boundary; Battle then consumes `tau.subagent_receipt.v1` receipts
  and executable artifacts for Docker Judge replay. A direct Battle-to-Scillm
  Red/Blue path is the wrong boundary and should not be promoted.
- Arena should support multiple hidden vulnerabilities per battle through a
  private ledger such as `arena/private/hidden-vulnerability-ledger.json`.
  Vulnerabilities should carry `id`, `entry_point`, `difficulty`, `weight`,
  oracle path, and scoring state. Red/Blue should not know the ledger or the
  vulnerability count; Judge/scoreboard should report per-vulnerability outcomes
  after consuming private oracle results and team submissions.
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

- **BATTLE-004 spectator timeline (ux-lab):** default renderer remains DOM/SVG/CSS
  `RaceViewport`. Optional Pixi race-world spike is behind `#battle?engine=pixi`
  only. Authoritative Phase 1 contract: `docs/BATTLE_RACE_ENGINE_PIXI_SPIKE.md`.
  Backend JSON stays renderer-neutral — no pixels, Pixi aliases, animation
  names, frame ids, particle parameters, or spritesheet paths. Optional
  `actor_visual.variant_id` is a stable cosmetic roster id only, not proof.
  Phase 1 uses procedural `Graphics` (no sprite sheets); atlases are Phase 2+.
  Phase 2+ sprite direction is original vintage Sega Genesis-like 16-bit
  side-view grimdark sci-fi sprites, validated by Battle sprite schemas.
  Agent skills: official `pixijs*` + `best-practices-battle-pixi` overlay.
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
- Arena subagent proof now has a narrow CLI entrypoint:
  `./run.sh arena-subagent-proof`. The first fresh proof at
  `/tmp/battle-arena-subagent-002` used prior score history, live Brave Search,
  and a Docker-only hidden oracle to build `arena-zip-slip-import-001`.
  It produced Tau handoff/receipt artifacts, `scenario.json`,
  `hidden-ground-truth.json`, `arena-receipt.json`, and generated target files.
- Battle-004 standalone mockup mockups/battle-004-shell-preserving-scroll-timeline.html restores accepted shell proportions, sticky lane labels, global T+0 timeline, Blue intervention strip, and GOAL aligned Agent Detail proof labels (FIXTURE TRACE).

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
| 2026-06-30 | Add a narrow Arena subagent proof before broader Battle runs. | Arena must select scenarios from score/performance history plus Brave research, write hidden ground truth, and prove the bug with a Docker oracle before Red/Blue dispatch. |
| 2026-06-30 | Start the runtime matrix with a broad `battle-base` image. | `battle-base:2026.06.30` is the foundation parent for later language images. It runs as `1000:1000`, defaults to `/workspace`, includes receipt utilities (`bash`, `jq`, `file`, `tini`), and now includes common entry-point, network, USB, and Wi-Fi tools. Docker/Compose/Python were removed from the base to reduce size and keep topology orchestration in the Arena host harness. Earlier narrow proof: `/tmp/battle-base-runtime-proof-20260630/proof.json`. Current trim proof: `/tmp/battle-base-trim-proof-20260630/proof.json`. |
| 2026-06-30 | Treat entry-point driving as a base capability. | Red needs a concrete access surface and Blue protects that same surface. `battle-base:2026.06.30` includes bounded local HTTP entry-point drivers (`curl`, `ab`, `nc`, `socat`, `ip`, `battle-http-junk`). Live proof: `/tmp/battle-base-entrypoint-proof-20260630/proof.json`. |
| 2026-06-30 | Treat common network simulation primitives as a base capability. | `battle-base:2026.06.30` includes local DNS spoof simulation, service discovery, packet capture/crafting binaries, route/firewall inspection tools, and traceroute tooling (`dnsmasq`, `dig`, `nmap`, `hping3`, `tcpdump`, `nft`, `iptables`, `traceroute`). Live proof: `/tmp/battle-base-network-sim-proof-20260630/proof.json`. |
| 2026-06-30 | Treat Wi-Fi and USB/removable media operators as base tooling. | `battle-base:2026.06.30` includes Wi-Fi radio tooling (`iw`, `iwconfig`, `hostapd`, `wpa_supplicant`, `rfkill`) and USB/media tooling (`lsusb`, `udevadm`, `mkfs.vfat`, `fsck.exfat`, `mtools`, `parted`). Multi-container topology is intentionally not in the base image; Arena should orchestrate multiple containers from the host harness. Live proof: `/tmp/battle-base-trim-proof-20260630/proof.json`. |
| 2026-06-30 | Let Red and Blue dynamically choose their own implementation language from the allowed scenario/runtime surface. | The target/project language is separate from team implementation language. Arena declares `target_language`, `red_allowed_languages`, and `blue_allowed_languages`; Red/Blue receipts declare `red_selected_language` and `blue_selected_language`. Missing languages become future runtime/profile requests, not ad hoc round installs. |
| 2026-06-30 | Add the first Arena Battle proof rung. | `./run.sh arena-battle-proof` reuses Arena scenario creation, writes a language contract, runs deterministic Red/Blue/Judge phases, and emits receipts plus a scoreboard that consume `target_language`, allowed language sets, selected languages, image digest, and tool versions. Live proof: `/tmp/battle-arena-battle-proof-002`. |
| 2026-06-30 | Add a harder Arena Battle scenario kind with private answer-key separation. | `./run.sh arena-battle-proof --scenario-kind signed-token-duplicate-claim` builds a signed-token duplicate-claim authorization bypass at `/api/session/verify`, stores the answer/oracle under `arena/private/`, exposes only `arena/team-public/` to teams, then sends it through Red, Blue, Judge, and scoreboard. Live proof: `/tmp/battle-arena-battle-proof-005`. |
| 2026-06-30 | Correct the next live rung to Tau harness, not direct Scillm from Battle. | Battle owns Arena, Docker, Judge, scoreboard, and receipts; Tau owns Red/Blue subagent execution through `tau.agent_handoff.v1` and `tau.subagent_receipt.v1`; Scillm is downstream of Tau. The draft direct-Scillm runner must be replaced or rewritten before it is used as evidence. |
| 2026-06-30 | Define fair mode as simultaneous public-only for the first live Tau rung. | Red and Blue receive the same `arena/team-public/` bundle concurrently. Blue does not receive Red's exploit before its first patch/hardening attempt, and Red does not receive Blue's patch. Reactive defense can be a later separate phase with different scoring. |
| 2026-06-30 | Allow Arena scenarios to contain multiple hidden vulnerabilities. | Arena should write a private multi-vulnerability ledger and oracle suite, with difficulty-weighted per-vulnerability scoring. The first live Tau proof may execute one selected vulnerability, but schemas should not assume exactly one hidden bug. |

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
- [ ] What is the first Docker language-runtime adapter to prove after
  `battle-base`: native/C, Python, Node, Go, legacy-script, or legacy-native?
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
| `src/battle_skill/arena_subagent.py` | Arena proof runner that writes Tau/Battle receipts, performs Brave-backed scenario research, generates a target app, and runs a Docker-only hidden bug oracle. |
| `src/battle_skill/arena_battle_proof.py` | Arena -> Red/Blue -> Judge proof rung with dynamic Red/Blue language-selection receipts, scoreboard consumption, and selectable scenario kinds. |
| `src/battle_skill/arena_live_battle_proof.py` | Arena public-only Tau harness proof runner. It creates private/public Arena artifacts, writes a public-only Tau context bundle, invokes Tau's `tau_coding.battle_live_handoff` bridge, and records Red/Blue `tau.agent_handoff.v1` plus `tau.subagent_receipt.v1` artifacts. |
- | `mockups/battle-004-shell-preserving-scroll-timeline.html` | Standalone Battle-004 shell-preserving race timeline mockup; visual-only FIXTURE TRACE density for Kimi/review loop. |

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

Arena subagent proof on 2026-06-30:

```text
command=./run.sh arena-subagent-proof battle-004 --out /tmp/battle-arena-subagent-002 --prior-scoreboard /tmp/battle-v1-tau-context-002/scoreboard.json --query "OWASP file upload zip slip path traversal vulnerability"
run.status=PASS
run.mocked=false
run.live=brave_search_and_docker_oracle
research.status=PASS
research.result_count=5
scenario.public_entrypoint=/api/import-zip
scenario.hidden_vulnerability_family=Zip Slip path traversal
scenario.cwe=CWE-22
arena.score_inputs.red_score=3.0
arena.score_inputs.blue_score=7.2
arena.score_inputs.asc=2
arena.score_inputs.tdsr=1.0
docker.oracle.exit_code=0
docker.oracle.stdout=ZIP_SLIP_CONFIRMED
tau.validation.ok=True
```

Harder Arena Battle proof on 2026-06-30:

```text
command=./run.sh arena-battle-proof battle-008 --out /tmp/battle-arena-battle-proof-005 --query "signed token duplicate claim canonicalization vulnerability" --docker-image python:3.12-slim --red-language python --blue-language shell --scenario-kind signed-token-duplicate-claim
run.status=PASS
run.verdict=BLUE_SUCCESS
run.mocked=false
run.live=brave_search_and_docker_red_blue_judge
scenario.scenario_id=arena-signed-token-duplicate-claim-001
scenario.public_entrypoint=/api/session/verify
scenario.entry_point_type=signed-token-verification-api
scenario.hidden_vulnerability_family=Duplicate claim canonicalization mismatch
visibility.private_answer_key=arena/private/hidden-ground-truth.json
visibility.team_public_brief=arena/team-public/scenario-brief.json
visibility.root_hidden_ground_truth_absent=true
visibility.public_target_oracle_absent=true
red.private_answer_inputs_consumed=[]
blue.private_answer_inputs_consumed=[]
arena.oracle.status=PASS
arena.oracle.exploit_confirmed=true
red.selected_language=python
red.exploit_confirmed=true
red.stdout=DUPLICATE_CLAIM_BYPASS_CONFIRMED
blue.selected_language=shell
judge.exploit_confirmed_before_patch=true
judge.exploit_blocked_after_patch=true
judge.functionality_preserved=true
scoreboard.red_score=1.5
scoreboard.blue_score=3.6
validation.visibility_checks=19/19
artifact_count=42
```

Arena Tau public-only proof on 2026-06-30:

```text
command=./run.sh arena-tau-public-only-proof battle-009 --out /tmp/battle-arena-tau-public-only-001 --query "signed token duplicate claim canonicalization vulnerability" --docker-image python:3.12-slim --model gpt-5.5 --scillm-base-url http://localhost:4001 --timeout-s 120
run.status=PASS
run.verdict=TAU_HANDOFF_READY
run.mocked=false
run.live=brave_search_docker_arena_oracle_tau_harness
run.agentic=true
arena.private_ledger=arena/private/hidden-vulnerability-ledger.json
arena.ledger.vulnerability_slots=2
arena.team_public_brief=arena/team-public/scenario-brief.json
arena.team_public_target=arena/team-public/target/app.py
tau.manifest.status=PASS
tau.manifest.mocked=false
tau.manifest.live=true
tau.scheduling.team_count=2
red.handoff.schema=tau.agent_handoff.v1
red.receipt.schema=tau.subagent_receipt.v1
red.receipt.result.status=PASS
blue.handoff.schema=tau.agent_handoff.v1
blue.receipt.schema=tau.subagent_receipt.v1
blue.receipt.result.status=PASS
visibility.status=PASS
visibility.private_input_leaks=[]
validation.checks=17/17
artifact_count=41
non_claim=Docker replay of Tau-produced exploit and patch is still pending because Tau's current Battle bridge returns action receipts, not executable exploit/patch artifacts.
```

Arena Tau executable-artifact proof on 2026-06-30:

```text
command=./run.sh arena-tau-public-only-proof battle-010 --out /tmp/battle-arena-tau-public-only-002 --query "signed token duplicate claim canonicalization vulnerability" --docker-image python:3.12-slim --model gpt-5.5 --scillm-base-url http://localhost:4001 --timeout-s 120
run.status=PASS
run.verdict=BLUE_SUCCESS
run.mocked=false
run.live=brave_search_docker_arena_oracle_tau_harness
tau.manifest.status=PASS
tau.scheduling.team_count=2
visibility.status=PASS
visibility.private_input_leaks=[]
red.receipt.result.status=PASS
red.materialized_artifact=/tmp/battle-arena-tau-public-only-002/tau-live/red/red_exploit_submission.py
blue.receipt.result.status=PASS
blue.materialized_artifact=/tmp/battle-arena-tau-public-only-002/tau-live/blue/app.py
judge.status=PASS
judge.verdict=BLUE_SUCCESS
judge.exploit_confirmed_before_patch=true
judge.exploit_blocked_after_patch=true
judge.functionality_preserved=true
scoreboard.red_score=1.5
scoreboard.blue_score=3.6
validation.checks=18/18
artifact_count=56
non_claim=Only the first private ledger vulnerability was replayed; the second slot remains schema coverage.
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
- autonomous Red/Blue discovery or patch behavior for the new Arena scenario;
  the current harder round is deterministic but no longer exposes the private
  answer key as team input
- multi-round Arena scenario adaptation
- Tau-harness Red/Blue execution for the fair public-only Arena rung
- multiple-hidden-vulnerability scoring execution beyond private ledger schema;
  the public-only Tau executable proof writes a two-slot private ledger but only
  replays the first vulnerability
- direct Scillm calls from Battle as a valid Red/Blue execution boundary

## Infrastructure State

- Battle runtime state defaults to `/mnt/storage12tb/skills/battle/`.
- The skill root should not contain real `.venv`, `artifacts`, `battles`,
  `reports`, `worktrees`, `node_modules`, or `__pycache__` directories.
- Generated monitor artifacts under `monitor/battle/public/artifacts/` are proof
  copies for UI validation and should not be treated as source.
- Current Battle worktree state is uncommitted and pending review.
- Full clean validation should be rerun before any closure, commit, or readiness
  claim.
