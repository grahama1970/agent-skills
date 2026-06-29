# Project Knowledge: battle

**Last updated:** 2026-06-29 18:28 EDT by agent
**Status:** Active development, bounded Battle v1 multi-round Tau/memory feedback proof passed

## Current Understanding

- Battle is a Red vs Blue security competition skill with a long-running
  orchestrator, digital twin isolation, AIxCC-style scoring, and report output.
- Production Battle should be an orchestration layer over subagents and Docker,
  not a large bespoke security engine. The host schedules rounds, chooses
  personas, dispatches subagents, provisions Docker runtimes, collects receipts,
  scores hard runtime signals, writes reports, and persists learning.
- Battle v1 has three competitive/design roles plus one objective recorder:
  Arena Team, Red Team, Blue Team, and Scorekeeper/Judge. The Arena Team is not
  the judge. It builds/selects the project/app/digital twin and secretly plants
  one or more vulnerabilities, then records hidden ground truth for the
  scorekeeper. Red attacks; Blue defends; the scorekeeper records objective
  runtime outcomes.
- Red and Blue should work asynchronously and dynamically, not as a fixed
  Red-then-Blue script. Blue must be able to scan for vulnerabilities, refresh
  `$ingest-code`/`$treesitter` context, recall CWE and patch history from
  `$memory`, research mitigations, and patch hidden bugs before Red exploits
  them. Red simultaneously recalls, researches, scans, mutates payloads, and
  attempts exploit chains.
- Battle sessions are hidden-vulnerability races. The scorekeeper tracks
  whether Red exploited before Blue patched, or Blue patched before Red
  succeeded, along with service uptime, crash state, regression behavior,
  exploit proof, patch timing, and false-defense outcomes.
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
- Speed is a scoring factor. Blue may choose accurate but slower methods such
  as deep static analysis, full `$ingest-code --treesitter`, or extensive
  regression generation; if Red exploits first, Red wins that session. Battle
  should reward strategies that balance accuracy, latency, and race pressure.
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
- Persona-conditioned workers may choose the `$scillm` model or surface they
  want within scenario budgets and provider policy. A lower-parameter or local
  model may be better for fast mutation generation, odd exploit combinations,
  or triage than a larger model. Receipts must record model/surface choice,
  persona, reason selected, latency/cost when available, and scope.
- Tau is currently consumed from the alpha checkout under
  `/home/graham/workspace/experiments/tau`, especially
  `/home/graham/workspace/experiments/tau/experiments` for goal-locked
  subagent schemas/proofs. Eventually Tau should become a proper `$tau` skill:
  a light, stable wrapper over the Tau project once the harness reaches beta.
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
- Battle subagents should treat `$memory` as the knowledge front door. Granting
  a subagent `$memory` access already exposes the routing and grounding products
  Battle needs for strategy work: `/intent`, `/answer`, `/clarify`, `/deflect`,
  `/recall`, entity-aware routing, and the memory side of evidence-case
  crosswalk workflows. Battle should not reimplement those as separate bespoke
  wrappers.
- Persona memory should color research and scan order. For example, a Red
  worker with persona `Sigmund Freud` should recall persona memories and prior
  Battle/code/CWE context before choosing `$brave-search`, `$dogpile`,
  `$github-search`, `$arxiv`, `$ingest-code`, or `$treesitter` actions. Persona
  framing can shape hypotheses, but scorekeeper evidence remains objective.
- Workers may use `$github-search` to find relevant repos/code/issues, clone
  selected public repositories into bounded `/tmp/battle-<run-id>/...`
  directories for read-only inspection, parse them with `$treesitter`, and store
  useful patterns in `$memory`. Cloned PoC/exploit code must not execute on the
  host; any execution belongs inside Docker and needs a receipt.
- Battle now has a first subagent smoke entry point:
  `./run.sh subagent-smoke battle-002 --out /tmp/battle-002-smoke-fast --fast-scan`.
  It runs one simple Red/Blue fixture with a real `/search?q=<term>` web entry
  point, seeded SQL injection/XSS behavior, Tau-shaped Red/Blue receipts,
  Tau receipt validation, optional `$hack audit` fast reconnaissance, SQLite
  event ledger, deterministic Blue patch, and scorekeeper replay.
- The current Red default for the subagent smoke is the explicit
  `brandon-bailey` persona. Brandon should be treated as having expert access
  to SPARTA corpora through `$memory` routes and collections including
  `persona_memory`, `sparta_qra`, `sparta_controls`, and `sparta_url_knowledge`.
- The first Tau alpha bug found during Battle integration was that importing
  `tau_coding.subagent_receipt` pulled in Tau rendering/TUI and failed without
  `textual`. Tau should keep receipt validation and agentic harness paths
  independent from the TUI.
- Battle now has a first Arena Team Docker proof entry point:
  `./run.sh arena-docker-smoke battle-003 --out /tmp/battle-003-arena`.
  It uses the `battle-003` fixture, where Arena Team records hidden SQL
  injection and reflected XSS ground truth for a tiny `/search?q=<term>` app.
  Blue starts first and patches inside Docker; Red starts later and attempts
  the hidden exploit inside Docker; the scorekeeper replays exploit-safe and
  regression checks inside Docker.
- The `arena-docker-smoke` proof is explicitly non-agentic:
  `mocked: no`, `live: docker_hidden_vulnerability_race`, `agentic: false`,
  `models_used: []`. It proves the narrow Arena hidden-ground-truth race and
  Docker command boundary only. It does not prove Tau subagents, `$scillm`,
  external/local model routing, multi-mutation swarms, memory promotion, or the
  React+D3 monitor.
- The first `battle-003` bug found during implementation was Docker mounted
  workspace write failure from inside the container. Fix: pass
  `--user <host-uid>:<host-gid>` to `docker run` for the fixture command
  containers so Blue can write the controlled workspace volume while target
  execution remains in Docker.
- `arena-docker-smoke` now has an `--agentic` mode:
  `./run.sh arena-docker-smoke battle-003 --out /tmp/battle-003-arena-agentic --agentic --red-persona brandon-bailey --blue-persona coder`.
  This mode writes Tau Red/Blue handoffs, runs one Tau `AgentHarness` turn per
  team with a deterministic local provider, writes Tau subagent receipts,
  validates those receipts, records model-selection metadata, records a SQLite
  event ledger, and then runs the same Docker-contained hidden-vulnerability
  race.
- The `battle-003` agentic proof still does not exercise `$scillm`, hosted or
  local model routing, memory promotion, multi-mutation swarms, Tau loop repair
  cycles, or the React+D3 monitor. Its model-selection receipt explicitly says
  `scillm=not_exercised`.
- `arena-docker-smoke` now has a `--scillm-plan` mode:
  `./run.sh arena-docker-smoke battle-003 --out /tmp/battle-003-arena-scillm --agentic --scillm-plan --red-persona brandon-bailey --blue-persona coder --scillm-model opencode/kimi-k2.6`.
  This mode calls live Scillm chat for Red and Blue action selection, writes
  `tau/red-scillm-selection.json` and `tau/blue-scillm-selection.json`, then
  continues through Tau AgentHarness receipt validation and Docker-contained
  scorekeeper replay.
- The Scillm project-agent doctor is not fully green in this environment, but
  it advanced past auth when using the running container's `SCILLM_MASTER_KEY`.
  Receipt `/home/graham/workspace/experiments/scillm/.scillm/proofs/project_agent_sanity/20260628T135005Z/receipt.json`
  has `auth_preflight.ok=true`; it also records usable chat/tool/batch/delegate
  lanes, while failing overall because shell `scillm` resolves to the wrong CLI
  and one OpenCode model-override lane failed.
- Battle uses Scillm's source-module fallback path for the proof rung rather
  than the broken shell `scillm` command. The first Battle Scillm run failed
  closed with `ModuleNotFoundError: No module named 'httpx'` because
  `SCILLM_PYTHON` was resolved to the bare uv-managed Python interpreter.
  Fix: keep the configured venv path instead of calling `.resolve()`.
- `arena-docker-smoke` now has a `--context-receipts` mode:
  `./run.sh arena-docker-smoke battle-003 --out /tmp/battle-003-arena-context --agentic --scillm-plan --context-receipts --red-persona brandon-bailey --blue-persona coder --scillm-model opencode/kimi-k2.6`.
  This mode calls `$memory` over HTTP for `/recall`, runs a Docker-contained
  fast scan, calls live Brave batch search from scan/persona context, extracts
  Python AST code context for the target, writes a deterministic research seed
  receipt, generates warm-pond exploit/defense candidates, executes a bounded
  set of selected warm-pond combinations in isolated Docker workspaces, stores
  one outcome document through `$memory` `/upsert` into `battle_round_memory`,
  records those artifacts in the scoreboard/run receipts, and appends memory/
  scan/research/warm-pond/execution/store events to the SQLite subagent ledger.
- The current context proof records Tree-sitter as a blocked optional
  diagnostic, not a Battle failure. `skills/treesitter/run.sh symbols ...`
  currently fails because the treesitter-tools environment imports `typer`,
  which imports `click`, and `click` is missing. Battle uses Python AST fallback
  for the code-context receipt in this rung.
- Battle Monitor now has a narrow React+D3 graph proof for generated
  `battle-003` context artifacts. `BattleForceGraph.tsx` uses D3 force layout
  math with React-owned SVG DOM to show Arena/Red/Blue/Judge players, receipts,
  scorekeeper verdict, race signals, Docker fast scan, Brave research,
  warm-pond candidates, bounded warm-pond execution, and the memory-upsert
  context node. The graph inspector and hidden accessibility table are backed
  by loaded artifacts, not static fixture arrays. This is still not the final
  Canvas/WebGL live swarm monitor for hundreds or thousands of attempts.
- Battle now has a four-party operational proof entry point:
  `./run.sh battle-v1-operational battle-003 --out /tmp/battle-v1-operational-a --red-workers 2 --blue-workers 2 --max-attempts 4 --require-memory`.
  It runs Arena Team, Red Team, Blue Team, and Scorekeeper roles, dispatches
  bounded asynchronous Red/Blue worker pools, records memory recall and
  promotion receipts, replays every selected warm-pond attempt in Docker, writes
  a SQLite event ledger, and emits `graph/battle-v1-force-graph.json`.
- Battle v1 operational now includes a live research broker before warm-pond
  candidate selection. It writes `context/research-broker-receipt.json`, runs
  Brave batch search plus Red/Blue GitHub and Dogpile research lanes with
  `threadpool_as_completed`, and records completion order. Target execution
  remains Docker-only; research lanes are agent-side retrieval and must not run
  PoC code on the host.
- Current Battle v1 operational local evidence:
  `/tmp/battle-v1-operational-a/run-receipt.json` and
  `/tmp/battle-v1-operational-b/run-receipt.json` both have `status=PASS` and
  `verdict=BLUE_SUCCESS`; both generated artifact sets passed
  `sanity/battle_v1_operational_acceptance.py`; the second run passed
  `--require-recall-found`.
- Current research-broker local evidence:
  `/tmp/battle-v1-research-broker-002/run-receipt.json` has `status=PASS` and
  `verdict=BLUE_SUCCESS`; `context/research-broker-receipt.json` has
  `status=PASS`, `mode=threadpool_as_completed`, `lane_count=5`,
  `passed_lane_count=5`, and `blocked_lane_count=0`; the generated artifact set
  passed `sanity/battle_v1_operational_acceptance.py`.
- Current research-dispatch local evidence:
  `/tmp/battle-v1-research-dispatch-001/run-receipt.json` has `status=PASS`,
  `verdict=BLUE_SUCCESS`, and `execution.tau_live_status=PASS`;
  `tau-live/manifest.json` has `scheduling.mode=asyncio.as_completed`;
  `context/warm-pond-receipt.json` has `selection_rule="highest research-adjusted affinity, deterministic id tiebreaker, Docker replay before memory promotion"`,
  `research_weighted_candidate_count=6`, and
  `research_weighted_combination_count=8`; Red and Blue worker receipts both
  have `research_dispatch.research_boost=0.2`; the artifact set passed
  `sanity/battle_v1_operational_acceptance.py --allow-first-recall-empty --min-red-workers 1 --min-blue-workers 1`.
- Battle now has an expanded warm-pond worker-fanout fixture:
  `./run.sh battle-v1-operational battle-004 --out /tmp/battle-v1-expanded-tau-032 --red-workers 32 --blue-workers 32 --max-attempts 32 --require-memory --tau-live --research-broker`.
  `battle-004` keeps the same tiny Docker-only SQLi/XSS Arena app shape as
  `battle-003`, but adds scenario-defined extra exploit and defense candidates.
  Current local evidence under `/tmp/battle-v1-expanded-tau-032` has
  `run.status=PASS`, `run.verdict=BLUE_SUCCESS`,
  `warm_pond.exploit_candidate_count=12`, `warm_pond.defense_candidate_count=8`,
  `warm_pond.combination_count=96`, Tau `scheduling.granularity=worker`,
  Tau `scheduling.handoff_count=64`, Tau `scheduling.worker_count=64`,
  `scorekeeper.attempt_count=32`, `scorekeeper.passed_attempt_count=32`, and
  `subagent-ledger.sqlite` event count `105`. This raises the current live Tau
  handoff pressure proof from 8x8 to 32x32 workers for the fixture. It still
  does not prove unbounded swarm execution, Tau loop repair cycles, Scillm
  delegate/batch/tool execution, or production hidden-vulnerability generation.
- Battle now has a generated warm-pond fixture:
  `./run.sh battle-v1-operational battle-005 --out /tmp/battle-v1-generated-no-tau-003 --red-workers 16 --blue-workers 16 --max-attempts 16 --require-memory --research-broker --tau-deterministic`.
  `battle-005` keeps the same Docker-only SQLi/XSS Arena app shape as
  `battle-003`/`battle-004`, but generates warm-pond candidate metadata from a
  compact `warm_pond_generator` block in `scenario.json`. Current local
  evidence under `/tmp/battle-v1-generated-no-tau-003` has
  `run.status=PASS`, `run.verdict=BLUE_SUCCESS`,
  `BATTLE_V1_OPERATIONAL_ACCEPTANCE_PASS`,
  `warm_pond.warm_pond_generator.enabled=True`,
  `generated_exploit_candidate_count=16`,
  `generated_defense_candidate_count=8`,
  `warm_pond.exploit_candidate_count=20`,
  `warm_pond.defense_candidate_count=10`,
  `warm_pond.combination_count=200`, `scorekeeper.attempt_count=16`,
  `scorekeeper.passed_attempt_count=16`, and `subagent-ledger.sqlite` event
  count `56`.
- The previous raw 64x64 Tau live worker-fanout run is preserved as blocked
  evidence, not accepted proof. Repro:
  `./run.sh battle-v1-operational battle-005 --out /tmp/battle-v1-generated-tau-064 --red-workers 64 --blue-workers 64 --max-attempts 64 --require-memory --research-broker --tau-live`.
  Battle wrote `/tmp/battle-v1-generated-tau-064/run-receipt.json` with
  `status=BLOCKED` and `reason=tau_live_handoff_failed`; Tau wrote
  `/tmp/battle-v1-generated-tau-064/tau-live/manifest.json` with
  `status=BLOCKED`, `handoff_count=128`, 80 worker calls `PASS`, and 48 worker
  calls `BLOCKED`. Upstream ticket `https://github.com/grahama1970/tau/issues/42`
  is now closed with structured Tau backpressure.
- Battle now consumes the Tau #42 contract by applying a local safe fanout cap
  before calling Tau live. Current proof command:
  `./run.sh battle-v1-operational battle-005 --out /tmp/battle-v1-generated-tau-064-capped --red-workers 64 --blue-workers 64 --max-attempts 64 --require-memory --research-broker --tau-live`.
  Local evidence under `/tmp/battle-v1-generated-tau-064-capped` has
  `run.status=PASS`, `run.verdict=BLUE_SUCCESS`,
  `execution.tau_live_status=PASS`, and
  `BATTLE_V1_OPERATIONAL_ACCEPTANCE_PASS` with
  `--min-red-workers 32 --min-blue-workers 32`.
  `context/tau-live-preflight-receipt.json` has `capped=true`,
  `requested_attempt_count=64`, `requested_handoff_count=128`,
  `max_live_handoffs=64`, `effective_attempt_count=32`, and
  `effective_handoff_count=64`. `tau-live/manifest.json` has `status=PASS`,
  `mocked=false`, `live=true`, `scheduling.granularity=worker`,
  `scheduling.mode=asyncio.as_completed`, `scheduling.handoff_count=64`, and
  `scheduling.worker_count=64`. This proves the highest currently safe bounded
  Tau live fanout for Battle's worker-granularity bridge; it does not prove
  unbounded 128-worker Tau live completion.
- Battle now has a bounded multi-round feedback proof entry point:
  `./run.sh battle-v1-multiround battle-005 --out /tmp/battle-v1-multiround-tau-002 --rounds 2 --red-workers 2 --blue-workers 2 --max-attempts 2 --require-memory --research-broker --tau-live`.
  This composes two Docker-only Battle v1 operational rounds. Round 1 stores a
  feedback document into `$memory` collection `lessons`; round 2 must retrieve
  the exact feedback token through `/recall` before the recalled promoted and
  negative combination IDs can influence warm-pond affinity. Current evidence:
  `/tmp/battle-v1-multiround-tau-002/run-receipt.json` has `status=PASS`,
  `verdict=BLUE_SUCCESS`, `execution.live=docker_multiround_memory_feedback`,
  `execution.tau_live=true`, `true_recall_ok=true`,
  `memory_influenced_round_count=1`, and `negative_evidence_count=8`.
  `/tmp/battle-v1-multiround-tau-002/round-feedback/round-002-memory-recall-receipt.json`
  has `status=PASS`, `found=true`, `exact_token_match=true`, and
  `matching_item_count=1`. Round 2
  `context/warm-pond-receipt.json` has
  `previous_round_memory_weighted_combination_count=6`.
  `/tmp/battle-v1-multiround-tau-002/round-feedback/negative-evidence-receipt.json`
  has `status=PASS` and `negative_evidence_count=8`. Both round Tau live
  manifests have `status=PASS`, `scheduling.granularity=worker`, and
  `handoff_count=4`. Acceptance command:
  `python3 sanity/battle_v1_multiround_acceptance.py /tmp/battle-v1-multiround-tau-002 --rounds 2 --min-red-workers 2 --min-blue-workers 2`
  produced `BATTLE_V1_MULTIROUND_ACCEPTANCE_PASS`.
- During the first multi-round run, Battle exposed a memory timing/recall
  weakness: `/upsert` to `lessons` succeeded, but immediate `/recall` initially
  returned no items. Battle now records bounded `/recall` attempts and requires
  an exact feedback-token match. `/list` remains diagnostic persistence
  evidence only and is not accepted as cross-round recall proof.
- The first research-broker proof exposed `agent-skills#51`: concurrent Dogpile
  searches shared `skills/dogpile/dogpile_partial_results.tmp/json`, causing
  one lane to fail with `FileNotFoundError`. The fix uses per-session
  partial-result paths and PID-specific temp files in `skills/dogpile/cli.py`;
  the issue was closed with proof from `/tmp/battle-v1-research-broker-002`.
- `$memory` accepted `battle_mutation_memory` documents through `/upsert`.
  Plain `/recall` with `collections=["battle_mutation_memory"]` can return no
  items for that custom collection, but `/recall` with
  `recall_profile="procedural_memory"` returns the promoted mutation records.
  Battle uses that profile-backed recall path; `/list` fallback evidence is
  diagnostic persistence proof only.
- Battle Monitor now also renders the `battle-v1-operational` generated
  artifacts. Local UI proof: `npm run build` passed, `npm run test:e2e` reported
  `4 passed`, and the inspected screenshot is
  `skills/battle/monitor/battle/test-results/battle-monitor-v1-operational.png`.
  The generic CDP hook captured a stale non-Battle surface, so
  `.codex/ui-verification/latest.json` records Playwright as the usable visual
  proof and notes the CDP mismatch.

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
| 2026-06-27 | Use `$memory` HTTP endpoints for programmatic Battle memory integration. | Battle uses `httpx` with `/recall` and `/upsert`; deprecated CLI learn and direct Arango/common memory imports are not used. |
| 2026-06-28 | Treat `$memory` as the subagent knowledge front door. | A Battle subagent with `$memory` access can use intent classification, answer/clarify/deflect routing, recall, entity-aware routing, and evidence-case crosswalk support without Battle reimplementing those capabilities. |
| 2026-06-28 | Use the alpha Tau checkout directly until a `$tau` skill exists. | Battle should integrate against `/home/graham/workspace/experiments/tau/experiments` now, then switch to a light `$tau` skill wrapper when Tau reaches beta. |
| 2026-06-28 | Add `battle-002` as the first simple subagent smoke fixture. | The fixture gives Red one SQLi/XSS attack and Blue one deterministic defense around a concrete `/search` web entry point. |
| 2026-06-28 | Make Brandon Bailey the default Red persona for Battle subagent smoke. | Brandon has expert SPARTA/cybersecurity memory context and is a better adversarial Red persona than a generic cyber analyst label. |
| 2026-06-28 | Keep Tau TUI out of Battle subagent validation. | Battle needs Tau's agentic harness/receipt boundary, not Textual/TUI dependencies. Receipt validation must work headlessly. |
| 2026-06-28 | Add `tau-agentic-smoke` as the next Battle/Tau proof rung. | This command runs Red and Blue through Tau `AgentHarness` with a deterministic local provider, validates Tau receipts, runs the Battle scorekeeper, and writes a SQLite ledger. It still does not prove scillm/external model execution. |
| 2026-06-28 | Clear `UV_PROJECT_ENVIRONMENT` before nested Tau `uv run` calls. | Battle `run.sh` points uv at `/mnt/storage12tb/skills/battle/.venv`; nested Tau uv calls must not inherit that path or Tau can overwrite Battle's venv while Battle is still running. |
| 2026-06-28 | Name the third Battle role Arena Team. | Arena Team builds/selects the app/digital twin and secretly plants vulnerabilities; it is not the judge. |
| 2026-06-28 | Model production Battle as asynchronous Red/Blue races. | Red and Blue should act concurrently with bounded parallelism, dynamic scan/research/patch choices, and hidden-vulnerability race scoring. |
| 2026-06-28 | Let workers choose `$scillm` models/surfaces within policy. | Model choice is part of the evolutionary strategy surface; lower-parameter or local models may win some exploit races through speed or niche behavior. |
| 2026-06-28 | Require Docker-only execution for all target/probe/build/test/PoC code. | External research and model calls are control-plane actions; executable Battle code must stay in Docker. |
| 2026-06-28 | Use React+D3 for a force-directed drill-down Battle v1 monitor only after real artifacts exist. | The UI should render receipts/ledger/memory graph data, not dashboard theater; Canvas/SVG hybrid is expected for hundreds or thousands of live attempts. |
| 2026-06-28 | Add `arena-docker-smoke` as the first Arena Team Docker race proof. | It proves a hidden SQLi/XSS race with Arena ground truth, asynchronous Red/Blue timing, Docker-contained target commands, and scorekeeper replay before adding Tau/scillm or swarm complexity. |
| 2026-06-28 | Run Battle Docker proof containers with the host UID/GID for mounted workspaces. | Rootless or remapped Docker can deny writes to host-mounted files; Blue patching needs controlled volume writes without moving executable code to the host. |
| 2026-06-28 | Add `--agentic` to `arena-docker-smoke`. | This combines the proven Tau `AgentHarness`/receipt boundary with the proven Docker hidden-vulnerability race without claiming live `$scillm` or swarm behavior. |
| 2026-06-28 | Add `--scillm-plan` to `arena-docker-smoke`. | This adds live Scillm chat action-selection receipts before Tau and Docker while preserving the Docker-only target execution boundary. |
| 2026-06-28 | Keep `BATTLE_SCILLM_PYTHON` unresolved. | Executing the symlinked venv Python preserves installed dependencies such as `httpx`; resolving it to the underlying uv Python loses the environment. |
| 2026-06-28 | Add `--context-receipts` to `arena-docker-smoke`. | This proves memory-first recall, AST code-context extraction, deterministic research seed receipts, and one `$memory` `/upsert` outcome write without claiming graph promotion or cross-round reuse. |
| 2026-06-28 | Add artifact-backed React+D3 graph proof to Battle Monitor. | This verifies the monitor can render generated `battle-003` Arena/Tau/context artifacts as a force-directed evidence graph before building the full live swarm interface. |
| 2026-06-28 | Require the context proof to record memory recall, Docker scan, Brave research, warm-pond candidates, and memory upsert before the race. | Battle strategy must start from prior memory and fresh reconnaissance; scan/research evidence should weight exploit and defense combinations rather than appearing after the score. |
| 2026-06-28 | Add bounded warm-pond execution before the main race. | Candidate generation alone is not enough; selected exploit/defense combinations now execute in isolated Docker workspaces with per-attempt receipts and revert-by-discarding semantics. |
| 2026-06-28 | Add `battle-v1-operational` as the four-party Docker proof rung. | This moves beyond context smoke by proving Arena/Red/Blue/Scorekeeper roles, async worker overlap, Docker-only replay evidence, memory promotion, generated force graph artifacts, and monitor rendering for one bounded fixture. |
| 2026-06-28 | Use `$memory` `procedural_memory` recall profile for Battle mutation memory. | `/upsert` and `/list` prove `battle_mutation_memory` persistence, but profile-backed `/recall` is the semantic recall proof path for custom procedural mutation records. |

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
- [ ] What is the first Arena Team fixture generator proof: one hidden web bug,
  a mixed JavaScript/low-level bug, or a generated suite of small app variants?
- [ ] Which Scillm surfaces are allowed in the first live Red/Blue worker proof:
  chat only, batch plus chat, or delegate for repo-tool workers?

## Key Files

| File | Purpose |
|------|---------|
| `src/battle_skill/cli.py` | Typer CLI; includes `battle-fixture` for deterministic fixture runs. |
| `src/battle_skill/battle_fixture.py` | Deterministic Battle v0 Red -> Blue -> Judge runner and artifact writer. |
| `src/battle_skill/judge.py` | Independent deterministic Judge for exploit-safe and regression commands. |
| `src/battle_skill/receipts.py` | Red, Blue, Judge, and command receipt dataclasses plus JSON writer. |
| `fixtures/battle-001/` | Seeded path traversal target, exploit check, tests, and deterministic patch. |
| `fixtures/battle-002/` | Simple stdlib web fixture with `/search`, seeded SQL injection/XSS checks, tests, and deterministic patch. |
| `src/battle_skill/subagent_smoke.py` | One Red/Blue Tau-shaped subagent smoke runner with SQLite ledger, optional `$hack` fast scan, and optional Tau `AgentHarness` execution. |
| `fixtures/battle-003/` | Arena hidden SQL injection/XSS Docker race fixture with hidden ground truth, vulnerable app, exploit oracle, tests, and deterministic patch. |
| `src/battle_skill/arena_docker_smoke.py` | Arena Team hidden-vulnerability Docker race proof runner; dispatches Red/Blue/scorekeeper commands through Docker, optionally runs Scillm chat and Tau AgentHarness action selection, and writes receipts. |
| `monitor/battle/` | React artifact monitor plus Playwright checks. |
| `.ask/browser-oracles.yaml` | Directory-local WebGPT project mapping for `$browser-oracle` and `$webgpt-review`. |
| `docs/BATTLE_V0.md` | Detailed Battle v0 claim scope, artifact contract, validation commands, and non-claims. |
| `docs/research/warm-pond-evolutionary-security.md` | Research/design note for Battle warm-pond mutation search, memory/Tree-sitter attraction weighting, and crosswalk-chain affinity. |
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
./run.sh subagent-smoke battle-002 --out /tmp/battle-002-smoke-fast --fast-scan -> status=PASS
BATTLE_SUBAGENT_SMOKE_ASSERT_PASS 7
PYTHONPATH=/home/graham/workspace/experiments/tau/src python3.14 import tau_coding.subagent_receipt -> PASS
./run.sh tau-agentic-smoke battle-002 --out /tmp/battle-002-tau-agentic --fast-scan -> status=PASS
BATTLE_TAU_AGENTIC_ASSERT_PASS
sqlite3 /tmp/battle-002-tau-agentic/subagent-ledger.sqlite -> 9 grouped event rows, including red/blue tau_agent_harness_turn=PASS
./run.sh arena-docker-smoke battle-003 --out /tmp/battle-003-arena -> status=PASS, verdict=BLUE_SUCCESS
BATTLE_ARENA_DOCKER_SMOKE_ASSERT_PASS
/tmp/battle-003-arena/run-receipt.json -> execution.live=docker_hidden_vulnerability_race, mocked=False, agentic=False
/tmp/battle-003-arena/scoreboard.json -> race.patch_before_exploit=True
/tmp/battle-003-arena/judge/judge-receipt.json -> arena_team_is_judge=False, exploit_blocked_after_patch=True, regression_tests_pass=True
/tmp/battle-003-arena/arena-receipt.json -> hidden_vulnerability_count=2
./run.sh arena-docker-smoke battle-003 --out /tmp/battle-003-arena-agentic --agentic --red-persona brandon-bailey --blue-persona coder -> status=PASS, verdict=BLUE_SUCCESS
BATTLE_ARENA_DOCKER_AGENTIC_ASSERT_PASS
/tmp/battle-003-arena-agentic/run-receipt.json -> execution.live=docker_hidden_vulnerability_race, agentic=True, models_used=["tau-local-deterministic-provider"]
/tmp/battle-003-arena-agentic/tau/team-receipt.json -> status=PASS, tau_receipts_valid=True, red/blue harness status=PASS
/tmp/battle-003-arena-agentic/tau/model-selection.json -> red.scillm=not_exercised, blue.scillm=not_exercised
/tmp/battle-003-arena-agentic/subagent-ledger.sqlite -> 8 grouped event rows for model_selection, Red/Blue handoff, Red/Blue AgentHarness, Red/Blue validation, team receipt
Scillm doctor with active container key -> /home/graham/workspace/experiments/scillm/.scillm/proofs/project_agent_sanity/20260628T135005Z/receipt.json, status=FAIL, auth_preflight.ok=True, chat/tool/batch/delegate lanes mostly usable, shell CLI resolution failed
./run.sh arena-docker-smoke battle-003 --out /tmp/battle-003-arena-scillm --agentic --scillm-plan --red-persona brandon-bailey --blue-persona coder --scillm-model opencode/kimi-k2.6 -> status=PASS, verdict=BLUE_SUCCESS
BATTLE_ARENA_DOCKER_SCILLM_ASSERT_PASS
/tmp/battle-003-arena-scillm/run-receipt.json -> execution.live=docker_hidden_vulnerability_race, agentic=True, scillm_plan=True, models_used includes opencode/kimi-k2.6
/tmp/battle-003-arena-scillm/tau/red-scillm-selection.json -> status=PASS, response_text nonempty
/tmp/battle-003-arena-scillm/tau/blue-scillm-selection.json -> status=PASS, response_text nonempty
/tmp/battle-003-arena-scillm/subagent-ledger.sqlite -> 10 events, including red/blue scillm_action_selection=PASS
./run.sh arena-docker-smoke battle-003 --out /tmp/battle-003-arena-context --agentic --scillm-plan --context-receipts --red-persona brandon-bailey --blue-persona coder --scillm-model opencode/kimi-k2.6 -> status=PASS, verdict=BLUE_SUCCESS
BATTLE_ARENA_DOCKER_CONTEXT_ASSERT_PASS
BATTLE_SCAN_BRAVE_WARM_POND_ASSERT_PASS
BATTLE_WARM_POND_EXECUTION_ASSERT_PASS
/tmp/battle-003-arena-context/run-receipt.json -> execution.live=docker_hidden_vulnerability_race, agentic=True, scillm_plan=True, context_receipts=True, models_used includes opencode/kimi-k2.6
/tmp/battle-003-arena-context/context/context-receipt.json -> status=PASS, memory.recall_status=PASS, memory.store_status=PASS
/tmp/battle-003-arena-context/context/fast-scan-receipt.json -> status=PASS, finding_count=2, families=["reflected_xss","sql_injection"]
/tmp/battle-003-arena-context/context/brave-search-receipt.json -> status=PASS, query_count=4, result_count=8
/tmp/battle-003-arena-context/context/warm-pond-receipt.json -> status=PASS, exploit_candidate_count=4, defense_candidate_count=4, combination_count=16
/tmp/battle-003-arena-context/context/warm-pond-execution-receipt.json -> status=PASS, selected_attempt_count=4, passed_attempt_count=4, failed_attempt_count=0
/tmp/battle-003-arena-context/context/memory-store-receipt.json -> status=PASS, collection=battle_round_memory, response.inserted=1, response.errors=[]
/tmp/battle-003-arena-context/context/code-context-receipt.json -> status=PASS, symbol_count=7, treesitter.status=BLOCKED, treesitter.reason=treesitter_command_failed
/tmp/battle-003-arena-context/context/treesitter.stderr.txt -> ModuleNotFoundError: No module named 'click'
/tmp/battle-003-arena-context/subagent-ledger.sqlite -> 22 events, including memory_recall=PASS, fast_scan=PASS, brave_search=PASS, code_context=PASS, research_seed=PASS, warm_pond_candidates=PASS, warm_pond_execution=PASS, warm_pond_attempt=PASS x4, memory_store=PASS, red/blue scillm_action_selection=PASS
npm run build in skills/battle/monitor/battle -> PASS
npm run test:e2e in skills/battle/monitor/battle -> 3 passed
skills/battle/monitor/battle/test-results/battle-monitor-v1-context-graph.png -> 514623 bytes
~/.codex/hooks/verify-ui-cdp.sh --url http://127.0.0.1:4174/?artifactBase=/artifacts/battle-003-arena-context --name battle-monitor-v1-context-graph -> /tmp/codex-ui-verification/agent-skills/battle-monitor-v1-context-graph/20260628T150035Z.read.json
.codex/ui-verification/latest.json -> battle-monitor-v1-context-graph meta marker
skills/battle/sanity.sh -> BATTLE_SANITY_PASS
./run.sh battle-v1-operational battle-004 --out /tmp/battle-v1-expanded-no-tau-001 --red-workers 12 --blue-workers 12 --max-attempts 12 --require-memory --research-broker --tau-deterministic -> status=PASS
python3 sanity/battle_v1_operational_acceptance.py /tmp/battle-v1-expanded-no-tau-001 --allow-first-recall-empty --min-red-workers 12 --min-blue-workers 12 -> BATTLE_V1_OPERATIONAL_ACCEPTANCE_PASS
/tmp/battle-v1-expanded-no-tau-001/context/warm-pond-receipt.json -> exploit_candidate_count=12, defense_candidate_count=8, combination_count=96
/tmp/battle-v1-expanded-no-tau-001/scorekeeper/scorekeeper-receipt.json -> attempt_count=12, passed_attempt_count=12
./run.sh battle-v1-operational battle-004 --out /tmp/battle-v1-expanded-tau-012 --red-workers 12 --blue-workers 12 --max-attempts 12 --require-memory --tau-live --research-broker -> status=PASS
python3 sanity/battle_v1_operational_acceptance.py /tmp/battle-v1-expanded-tau-012 --allow-first-recall-empty --min-red-workers 12 --min-blue-workers 12 -> BATTLE_V1_OPERATIONAL_ACCEPTANCE_PASS
/tmp/battle-v1-expanded-tau-012/tau-live/manifest.json -> scheduling.granularity=worker, handoff_count=24, worker_count=24
./run.sh battle-v1-operational battle-004 --out /tmp/battle-v1-expanded-tau-024 --red-workers 24 --blue-workers 24 --max-attempts 24 --require-memory --tau-live --research-broker -> status=PASS
python3 sanity/battle_v1_operational_acceptance.py /tmp/battle-v1-expanded-tau-024 --allow-first-recall-empty --min-red-workers 24 --min-blue-workers 24 -> BATTLE_V1_OPERATIONAL_ACCEPTANCE_PASS
/tmp/battle-v1-expanded-tau-024/tau-live/manifest.json -> scheduling.granularity=worker, handoff_count=48, worker_count=48
./run.sh battle-v1-operational battle-004 --out /tmp/battle-v1-expanded-tau-032 --red-workers 32 --blue-workers 32 --max-attempts 32 --require-memory --tau-live --research-broker -> status=PASS
python3 sanity/battle_v1_operational_acceptance.py /tmp/battle-v1-expanded-tau-032 --allow-first-recall-empty --min-red-workers 32 --min-blue-workers 32 -> BATTLE_V1_OPERATIONAL_ACCEPTANCE_PASS
/tmp/battle-v1-expanded-tau-032/tau-live/manifest.json -> scheduling.granularity=worker, handoff_count=64, worker_count=64, completion_order_count=64
/tmp/battle-v1-expanded-tau-032/scorekeeper/scorekeeper-receipt.json -> attempt_count=32, passed_attempt_count=32
/tmp/battle-v1-expanded-tau-032/subagent-ledger.sqlite -> 105 events
./run.sh battle-v1-operational battle-005 --out /tmp/battle-v1-generated-tau-064-capped --red-workers 64 --blue-workers 64 --max-attempts 64 --require-memory --research-broker --tau-live -> status=PASS
python3 sanity/battle_v1_operational_acceptance.py /tmp/battle-v1-generated-tau-064-capped --allow-first-recall-empty --min-red-workers 32 --min-blue-workers 32 -> BATTLE_V1_OPERATIONAL_ACCEPTANCE_PASS
/tmp/battle-v1-generated-tau-064-capped/context/tau-live-preflight-receipt.json -> capped=true, requested_handoff_count=128, max_live_handoffs=64, effective_handoff_count=64
/tmp/battle-v1-generated-tau-064-capped/tau-live/manifest.json -> status=PASS, mocked=false, live=true, scheduling.granularity=worker, scheduling.mode=asyncio.as_completed, handoff_count=64, worker_count=64
/tmp/battle-v1-generated-tau-064-capped/run-receipt.json -> status=PASS, verdict=BLUE_SUCCESS, execution.tau_live_status=PASS, models_used=["gpt-5.5"]
./run.sh battle-v1-multiround battle-005 --out /tmp/battle-v1-multiround-tau-002 --rounds 2 --red-workers 2 --blue-workers 2 --max-attempts 2 --require-memory --research-broker --tau-live -> status=PASS
python3 sanity/battle_v1_multiround_acceptance.py /tmp/battle-v1-multiround-tau-002 --rounds 2 --min-red-workers 2 --min-blue-workers 2 -> BATTLE_V1_MULTIROUND_ACCEPTANCE_PASS
/tmp/battle-v1-multiround-tau-002/round-feedback/round-002-memory-recall-receipt.json -> status=PASS, found=true, exact_token_match=true, endpoint=/recall
/tmp/battle-v1-multiround-tau-002/rounds/round-002/context/warm-pond-receipt.json -> previous_round_memory_weighted_combination_count=6
/tmp/battle-v1-multiround-tau-002/round-feedback/negative-evidence-receipt.json -> status=PASS, negative_evidence_count=8
/tmp/battle-v1-multiround-tau-002/rounds/round-001/tau-live/manifest.json -> status=PASS, scheduling.handoff_count=4
/tmp/battle-v1-multiround-tau-002/rounds/round-002/tau-live/manifest.json -> status=PASS, scheduling.handoff_count=4
```

## Non-Claims

Current Battle proof rungs do not yet prove:

- real Red agent behavior
- real Blue agent behavior
- Scillm delegate, batch, tool, or Tau-loop model execution
- anvil or code-runner patch quality
- unbounded multi-round learning
- production multi-round Docker mode or QEMU mode beyond the bounded
  `battle-v1-multiround` fixture proof
- memory graph promotion or cross-round learning reuse beyond exact-token
  `/recall` from `lessons` in the bounded proof
- Lean or QRA assurance
- production Battle readiness
- live Tau AgentHarness execution with scillm or an external model
- loop repair cycle execution
- Docker-contained Battle target execution for `battle-002`
- memory persona ingestion for Brandon Bailey
- Arena Team hidden-vulnerability generation
- asynchronous Red/Blue bounded-parallel scheduler execution
- persona-owned Scillm model selection
- GitHub-research clone inspection inside a Battle worker
- live-streaming React+D3 monitor updates from a running scheduler
- high-throughput Canvas/WebGL live swarm monitor for 100s/1000s of attempts
- Scillm delegate, batch, or tool execution inside Battle
- asynchronous multi-worker swarm behavior beyond one Red worker and one Blue
  worker in the Docker proof
- `$memory` graph promotion from the Docker race proof
- Tree-sitter success in the context proof until the treesitter-tools
  dependency issue is fixed

## Infrastructure State

- Battle runtime state defaults to `/mnt/storage12tb/skills/battle/`.
- The skill root should not contain real `.venv`, `artifacts`, `battles`,
  `reports`, `worktrees`, `node_modules`, or `__pycache__` directories.
- Generated monitor artifacts under `monitor/battle/public/artifacts/` are proof
  copies for UI validation and should not be treated as source.
- Current Battle worktree state is uncommitted and pending review.
- Full clean validation should be rerun before any closure, commit, or readiness
  claim.
