# Handoff Report: Battle

**Timestamp**: 2026-07-16T15:41:27-04:00
**Active Agent**: Codex
**Repository**: `grahama1970/agent-skills`
**Branch**: `codex/battle-v16-arena-contract`
**Commit / origin/main**: `f36e42c18e6479c9fcb578168c55fbcee8030d59`

## 1. Immutable Goal

Create and qualify one working end-to-end Battle Arena where:

1. Red and Blue operate through Tau/SciLLM against one bounded, non-mocked Arena.
2. Battle owns policy, Docker execution, receipts, selection, and public projection.
3. Judge owns security outcomes.
4. Durable team-scoped Memory is recalled and demonstrably used by the provider.
5. The campaign can test whether Memory changes Judge-confirmed Red or Blue outcomes.
6. The public Pixi spectator replays the same authoritative campaign with working sprite states.

The goal is **not complete**. Memory use is proven, but outcome improvement is not. The V16 live topology qualification and fresh browser proof are blocked as described below.

## 2. Current Phase

```text
Phase: V16 RelayForge live-topology qualification
Status: BLOCKED_CURRENT_MILESTONE
Top backend blocker: Tau Red output contract does not emit action_proposals
Top frontend blocker: UX Lab on 127.0.0.1:3002 is unavailable; no fresh CDP proof
```

The highest-priority backend action is the reviewed Battle + Tau action-proposal repair. Do not move to V17, Music M2, more schemas, broader campaigns, additional sprite production, or experiment dashboards before the V16 live topology command emits its final qualification receipt.

## 3. Project Overview And Ownership

- **Ecosystem**: Python Battle control plane, Tau/SciLLM provider execution, Docker Arena, deterministic Judge, Memory API, React/Pixi spectator.
- **Battle owns**: public team contracts, campaign policy, artifact validation, Docker execution, receipt chains, Judge invocation, selection, normalized public fixtures.
- **Tau owns**: persona-attached Red/Blue provider execution and materialization of provider-authored outputs.
- **Judge owns**: exploit/defense outcomes. Generated code, action proposals, Memory, music, and animation are not outcome authority.
- **Frontend owns**: rendering authoritative normalized fixtures. It must not infer Battle truth.

## 4. Implemented Reality

### V16 deterministic Arena

Commit `f36e42c18` contains the V16 live-topology runner, schemas, CLI, tests, and the public request-id leakage repair.

The retained deterministic qualification at:

```text
/tmp/battle-v16-live-topology-deterministic-5938/deterministic-qualification.json
```

records deterministic acceptance for:

```text
RF-A
RF-B
RF-C
RF-D decoy isolation
broad quarantine
decoy shutdown
```

Its aggregate status remains `BLOCKED` because it predates the separate live Memory and topology qualification receipts. Do not reinterpret that artifact as full V16 qualification.

Frozen runtime identity:

```text
service image id:
sha256:93e6a4c824bd062657b063531f65e8b91295ac5733757a46fce45666b5ba041f

base image:
python@sha256:6c4dd321d176d61ea848dc8c73a4f7dbae8f70e0ee48bb411ea2f045b599fa8e

target identity SHA-256:
b45bf5e2750cb2f76f24e83e6936e02acaf36a911db600276e7a1eef777ac16b
```

### Live Memory use

Artifact:

```text
/tmp/battle-v16-memory-chain-proof-5938/memory-chain-qualification.json
```

Evidence:

```text
status: PASS
mocked: false
live: true
fixture_fallback_used: false
outcome_improvement_proven: false
```

This proves one team-scoped measured RelayForge record was written and exactly recalled through the production Memory API, and a live Tau/SciLLM provider cited and used it to change a strategy artifact. It does not prove that Memory improved either team.

### Live topology attempt

Artifact root:

```text
/tmp/battle-v16-live-topology-proof-5938/
```

Positive evidence:

```text
input-binding.json: PASS
provider-manifest-receipt.json: PASS
mocked: false
live: true for both provider calls
fixture_fallback_used: false
private_identifier_match_count: 0
```

The final qualification receipt was not emitted. Battle correctly failed closed because Red supplied no structured topology action proposal.

## 5. Current Broken And Blocked

### Blocker A: Red action-proposal contract is missing across Battle and Tau

Observed failure:

```text
provider response lacks structured action_proposals
```

Red materialized the legacy contract:

```text
artifact_type
exploit_py
rationale
strategy_genome
```

Blue's strategy genome contained two action proposals, but Red's contained zero. Battle must not infer an action from exploit code or prose.

Root cause: Tau's existing Battle Red handoff, SciLLM system prompt, and materializer require the old local `import_zip` exploit schema. V16 needs an explicit Battle-owned public-action output contract that Tau honors only when present.

Reviewed repair bundle:

```text
/home/graham/Downloads/battle-v16-red-action-contract-repair.zip
SHA-256: 7fab08dd0fa696e56b94101a7a9c8d67ca84ca5cb8bf46832135348eba0e0546
```

The ZIP contains:

```text
battle-v16-red-action-contract-repair/agent-skills-f36e42c-red-action-contract.patch
battle-v16-red-action-contract-repair/tau-bad8b207-red-action-contract.patch
battle-v16-red-action-contract-repair/APPLY.md
battle-v16-red-action-contract-repair/LIVE_EVIDENCE.json
battle-v16-red-action-contract-repair/LOCAL_VERIFICATION.json
```

The patches have **not** been applied in the active repositories and have **not** passed the live topology command locally. The bundle's local verification reports only focused deterministic checks (`12 passed` Battle, `9 passed` Tau) and explicitly says `live_command_run:false`.

Tau warning: the current local Tau checkout is not at the patch base and has extensive unrelated untracked proof output. Apply the patch in an isolated Tau worktree at base commit:

```text
bad8b207f71246d63842feb7992dcad33b40e90f
```

Do not apply it over the dirty `/home/graham/workspace/experiments/tau` checkout.

### Blocker B: the Battle spectator is not currently reviewable

User-visible failure reported before the host became unavailable:

```text
Failed to fetch dynamically imported module:
http://localhost:3002/src/components/battle/BattleArenaView.tsx
```

Current evidence:

```text
curl http://127.0.0.1:3002/ -> unavailable
fresh verify-ui-cdp marker -> missing
existing .codex/ui-verification/latest.json -> stale V14 marker from July 15
```

Previous restart attempts found new Vite processes blocked in uninterruptible kernel state at `netlink_dump`, with very high host load. This is host/runtime state, not proof that the React import defect is fixed. A host reboot or network-namespace repair is likely required before restarting UX Lab and rerunning CDP.

Do not claim the arena UX is fixed or reviewable until the route renders and a fresh screenshot is visually inspected.

## 6. Next Actions In Dependency Order

### 1. Apply the reviewed two-repository repair in isolated worktrees

Agent Skills worktree base:

```bash
cd /tmp/agent-skills-main-v15
git apply --check /tmp/battle-v16-red-action-contract-repair/agent-skills-f36e42c-red-action-contract.patch
git apply /tmp/battle-v16-red-action-contract-repair/agent-skills-f36e42c-red-action-contract.patch
```

Tau must use a new isolated worktree at `bad8b207f...`; follow the bundle's `APPLY.md`. First extract the ZIP to a stable `/tmp/battle-v16-red-action-contract-repair/` directory.

Acceptance:

```text
Battle publishes an explicit team-scoped public-action contract.
Tau echoes the exact contract into provider prompts.
Tau materializes provider-authored action-proposals.json.
Battle verifies exact contract identity and proposal count.
Legacy exploit/patch behavior remains unchanged when the contract is absent.
Missing, legacy, wrong-team, and unallowed proposals fail closed.
```

### 2. Run focused checks, then the real live gate

Focused checks from `APPLY.md`:

```bash
cd /tmp/agent-skills-main-v15/skills/battle
uv run pytest -q tests/test_relayforge_v16_live_topology_contract.py

cd <isolated-tau-worktree>
uv run pytest -q tests/test_battle_live_handoff.py
```

Then run the non-mocked topology qualification using the retained `5938` artifacts or a fresh equivalently bound set:

```bash
cd /tmp/agent-skills-main-v15/skills/battle
./run.sh v16-live-topology-qualify \
  --target battle-v16-relayforge-a \
  --freeze /tmp/battle-v16-live-topology-freeze-5938 \
  --deterministic-qualification /tmp/battle-v16-live-topology-deterministic-5938 \
  --memory-chain /tmp/battle-v16-memory-chain-proof-5938 \
  --out /tmp/battle-v16-live-topology-proof-next
```

Stop condition for this backend slice:

```text
one final live-topology qualification receipt exists
mocked = false
live = true
fixture_fallback_used = false
both teams have provider-authored accepted action proposals
selected actions execute against the bounded topology
Judge binds exact provider/action/execution/target receipts
no unsupported Memory-improvement claim
```

### 3. Restore the UX host and prove the route visually

After host/kernel recovery:

```bash
~/.codex/hooks/verify-ui-cdp.sh \
  --url 'http://127.0.0.1:3002/#battle/receipt?engine=pixi' \
  --name battle
```

Required proof:

```text
fresh .codex/ui-verification/latest.json
Battle route loads without dynamic-import or AJV errors
Pixi canvas is nonblank
plague_nurgling is the single shared runner atlas for the bounded proof
sprite states are visibly correct at representative playheads
no outcome animation exceeds Judge receipts
fresh screenshot visually inspected, not only DOM assertions
```

### 4. Only then project the completed V16 campaign to the spectator

Do not build a V16 presentation fixture from a blocked topology attempt. The public fixture must be generated from the final single-run receipt chain and remain free of Tau workspaces, Docker paths, private Arena truth, and provider internals.

## 7. Key Files

Battle implementation:

```text
skills/battle/src/battle_skill/relayforge_v16_live_topology.py
skills/battle/src/battle_skill/relayforge_v16.py
skills/battle/src/battle_skill/relayforge_v16_memory_chain.py
skills/battle/src/battle_skill/cli.py
skills/battle/arena/relayforge-v16/service.py
skills/battle/tests/test_relayforge_v16_live_topology_contract.py
skills/battle/tests/test_relayforge_v16_contract.py
```

V16 schemas:

```text
skills/battle/schemas/battle.v16.live_topology_action_proposal.v1.schema.json
skills/battle/schemas/battle.v16.live_topology_action_selection.v1.schema.json
skills/battle/schemas/battle.v16.live_topology_action_execution.v1.schema.json
skills/battle/schemas/battle.v16.live_topology_judge.v1.schema.json
skills/battle/schemas/battle.v16.live_topology_qualification.v1.schema.json
```

Spectator and host integration:

```text
skills/battle/spectator/
/home/graham/workspace/experiments/chatterbox/src/components/battle/BattleArenaView.tsx
/home/graham/workspace/experiments/chatterbox/.codex/ui-verification/latest.json
```

WebGPT/oracle binding:

```text
tab id: 837358116
desktop: 2
url: https://chatgpt.com/g/g-p-6a408ce3c7a081918022e0eb6673aae3/c/6a4f8407-9d8c-83ea-b324-de316f32eb39
```

## 8. Recent Battle Commits

```text
f36e42c18 battle: qualify live RelayForge topology
ac44598ec battle: prove live RelayForge memory uptake
70d11147c battle: implement RelayForge RF-D and broad defenses
e030f9e34 battle: implement RelayForge RF-C vertical
90528656c battle: implement RelayForge RF-B vertical
8bac69b9c battle: implement RelayForge RF-A vertical
da9684e86 battle: add fail-closed RelayForge V16 skeleton
aa04e844e battle: freeze memory-sensitive arena V16 contract
```

## 9. Evidence Classification

| Evidence | mocked | live | What it proves | What it does not prove |
|---|---:|---:|---|---|
| V16 deterministic qualification | no | local Docker/deterministic | RF-A/B/C/D and broad defense mechanics | Memory use or live provider topology qualification |
| V16 Memory chain | no | yes | Exact Memory write/recall and provider use changed strategy | Better Judge outcome |
| V16 topology provider attempt | no | yes | Both provider calls ran; public/private boundary stayed clean | Accepted Red action, executed topology, final Judge result |
| WebGPT repair bundle | no | no live command | Patch review and focused deterministic checks in reviewer environment | Local live closure |
| Current spectator host | n/a | no | Nothing current; endpoint unavailable | Any UX readiness claim |

## 10. Explicit Nonclaims

Do not claim:

```text
V16 live topology qualification passed
Memory improved Red or Blue performance
Judge-confirmed Red exploit success
the Battle Arena is currently reviewable
the dynamic-import crash is fixed
the repair ZIP is integrated
the V16 campaign is projected publicly
production readiness
population-scale genetic evolution
```

## 11. Commit Discipline

The Battle worktree was clean before this handoff update and matched `origin/main` at `f36e42c18`. Commit only `skills/battle/local/HANDOFF.md` for this handoff. Do not stage unrelated files or the generated `skills/handoff/.venv`.
