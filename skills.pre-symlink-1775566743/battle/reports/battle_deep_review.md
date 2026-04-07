# Deep Review: battle skill

## Scope
1. `.pi/skills/battle` core modules, CLI, digital twin, agents, memory, scoring.
2. `worktrees/battle_20260205_113118/*` referenced only to trace brittle paths and TODOs.

## High
1. Resume loses battle configuration on restart. File: `.pi/skills/battle/battle.py`, `.pi/skills/battle/state.py`, `.pi/skills/battle/orchestrator.py`.
Risk: `resume` reconstructs `BattleOrchestrator` with only `target_path` and `max_rounds`, while `BattleState` does not persist `twin_mode`, `docker_image`, `qemu_machine`, `chaos`, `model`, or `concurrent`. A resumed battle can silently switch modes (e.g., docker -> copy) and produce inconsistent results or incorrect scoring.
Fix: Persist orchestration configuration in `BattleState` (mode, docker image, qemu machine, chaos, model, concurrent) when creating the state, serialize in `to_dict`, restore in `from_dict`, and pass into `BattleOrchestrator` on resume.
Minimal test: Create a `BattleState` with non-default config, `save` and `load`, then assert `resume` uses the same config to build the orchestrator (mode, docker image, qemu machine, chaos, model).

2. Concurrent timeouts do not actually stop workers. File: `.pi/skills/battle/orchestrator.py`.
Risk: `run_round_concurrent` calls `future.result(timeout=...)`, but the `ThreadPoolExecutor` is in a `with` block that waits for all threads on exit, so a timed-out worker can still block the round end. This defeats the timeout and can hang overnight runs.
Fix: On timeout, cancel futures and shut down the executor with `wait=False` and `cancel_futures=True`, or use `cf.wait` with timeout and return immediately while signaling a stop event that workers check.
Minimal test: Inject a worker that sleeps longer than `worker_timeout` and assert the round returns within the timeout budget.

## Medium
1. Git worktree sync does not apply uncommitted Blue patches. File: `.pi/skills/battle/digital_twin.py`, `.pi/skills/battle/blue_team.py`.
Risk: `sync_blue_to_arena` cherry-picks `HEAD` from the Blue worktree, but Blue patches are applied via `anvil` without creating a commit. This leaves the arena unchanged in git mode, so defenses are never evaluated.
Fix: In git mode, detect a dirty Blue worktree. If dirty, either commit with a battle-scoped message and cherry-pick, or generate a patch via `git diff` and apply it to the arena. Alternatively fall back to the copy-mode sync for git worktrees.
Minimal test: Modify a file in the Blue worktree without committing, call `sync_blue_to_arena`, and assert the arena file matches.

2. Strategy evolution query uses the wrong round numbers. File: `.pi/skills/battle/memory.py`.
Risk: `query_strategy_evolution` iterates `range(last_n_rounds)` and queries “Round 0..N” regardless of current round. This misses the most recent rounds and can bias strategy selection.
Fix: Base the loop on `self.current_round`, for example querying `current_round`, `current_round-1`, etc.
Minimal test: Set `current_round=5`, `last_n_rounds=2`, and assert the queries target rounds 5 and 4.

3. `battle_monolith.py` exceeds 800 lines and is still scanned. File: `.pi/skills/battle/battle_monolith.py`.
Risk: The 3720-line monolith is a maintenance hazard and triggers monitor alerts. It is labeled as a backup in `sanity.sh`, but still lives in the main skill path.
Fix: Move the monolith to a `legacy/` or `reports/` archive path and update `sanity.sh` to check the new location. If it must stay, split into smaller modules or add a clear deprecation note. Ask before deleting.
Minimal test: Run `./sanity.sh` after the move to ensure the backup check still passes.

## Low
1. Brittle local paths in worktree README artifacts. File: `.pi/skills/battle/worktrees/battle_20260205_113118/*/packages/coding-agent/examples/custom-tools/orchestrate/README.md`.
Risk: Embedded absolute paths (e.g., `/home/graham/workspace/experiments/memory/.claude/hooks/quality-gate.sh`) reduce portability and trigger monitor alerts.
Fix: Update the source template in the main repo (not the generated worktree copies) to use `$PI_MONO_ROOT` or a relative path. Consider excluding `worktrees/` from monitoring or repository tracking.
Minimal test: Rebuild a worktree and confirm the README no longer contains absolute user paths.

2. Aspirational TODOs in worktree packages are out of scope for battle. Files: `worktrees/.../packages/ai/scripts/generate-models.ts`, `worktrees/.../packages/web-ui/example/src/main.ts`, `worktrees/.../packages/web-ui/src/components/SandboxedIframe.ts`, `worktrees/.../packages/pods/docs/plan.md`, `worktrees/.../packages/mom/src/agent.ts`.
Risk: These TODOs are not owned by the battle skill and represent upstream package debt. They should not block battle review unless battle depends on them at runtime.
Fix: Track in the owning packages; do not patch generated worktrees directly.
Minimal test: None for battle; defer to package-specific test plans.

## Missing tests
1. `BattleState` serialization and resume config preservation (state.py + battle.py).
2. `DigitalTwin` git mode sync behavior with dirty working tree (digital_twin.py).
3. `Scorer.score_round` with mixed verified/unverified patches and severity multipliers (scoring.py).
4. `BattleMemory.query_strategy_evolution` round selection (memory.py).
