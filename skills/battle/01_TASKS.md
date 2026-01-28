# Task List: Battle Skill - Red vs Blue Team Competition

**Created**: 2025-01-28
**Goal**: Build a dedicated skill for long-running Red vs Blue team security competitions with 1000s of interactions, scoring, and insight generation.

## Context

Based on research into RvB framework, DARPA AIxCC, Microsoft PyRIT, and DeepTeam, we're building an orchestration system that pits a Red Team (attack) against a Blue Team (defense) in an overnight competitive loop. Each team leverages existing `.pi/skills` (hack, anvil, memory, etc.).

Key architectural decisions:
- Sequential imperfect-information game (RvB pattern)
- Externalized state management (agents communicate via environment)
- Entropy-driven termination (stop when strategies converge)
- Task-monitor integration for overnight progress tracking
- AIxCC-style scoring (TDSR, attack count, time decay)

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method | Sanity Script | Status |
|---------|------------|---------------|--------|
| N/A | Uses existing skills (hack, anvil, memory) | N/A | N/A |

> No new external dependencies - composes existing skills.

## Questions/Blockers

None - architecture validated by research (RvB, AIxCC patterns).

---

## Tasks

### P0: Setup (Sequential)

- [ ] **Task 1**: Create skill directory structure
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - Notes: Create .pi/skills/battle/ with SKILL.md, run.sh, pyproject.toml, sanity.sh
  - **Sanity**: None (file creation)
  - **Definition of Done**:
    - Test: `test -f .pi/skills/battle/run.sh && test -f .pi/skills/battle/SKILL.md`
    - Assertion: Skill directory exists with required files

- [ ] **Task 2**: Implement externalized state management
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 1
  - Notes: State as externalized history pattern - BattleState, RoundLog, InteractionHistory classes
  - **Sanity**: None (standard dataclasses)
  - **Definition of Done**:
    - Test: `.pi/skills/battle/sanity.sh` passes state serialization test
    - Assertion: BattleState can serialize/deserialize 1000 rounds without data loss

### P1: Core Components (Parallel)

- [ ] **Task 3**: Implement Red Team agent
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - Notes: Planner + Executor + Reporter pattern. Delegates to hack skill for scan/audit/exploit.
  - **Sanity**: None (uses hack skill)
  - **Definition of Done**:
    - Test: Red agent can generate attack plan and execute via hack skill
    - Assertion: `RedAgent.attack()` returns AttackResult with findings

- [ ] **Task 4**: Implement Blue Team agent
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - Notes: Fault localization + patch generation + verification. Delegates to anvil skill.
  - **Sanity**: None (uses anvil skill)
  - **Definition of Done**:
    - Test: Blue agent can receive attack log and generate patch
    - Assertion: `BlueAgent.defend()` returns DefenseResult with patch diff

- [ ] **Task 5**: Implement scoring system
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - Notes: AIxCC-style scoring - TDSR, FDSR, ASC, time decay, functionality preservation
  - **Sanity**: None (pure Python math)
  - **Definition of Done**:
    - Test: Scoring calculates correctly for sample battle data
    - Assertion: `Scorer.calculate()` returns scores matching expected values

- [ ] **Task 6**: Implement task-monitor integration
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - Notes: Register battle with task-monitor, push progress updates each round
  - **Sanity**: None (uses task-monitor skill)
  - **Definition of Done**:
    - Test: Battle progress visible in task-monitor TUI
    - Assertion: `register_battle()` and `update_progress()` succeed

### P2: Game Loop (Sequential after P1)

- [ ] **Task 7**: Implement game loop orchestrator
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 3, Task 4, Task 5, Task 6
  - Notes: RvB-style game loop with Bayesian belief updates, entropy-driven termination
  - **Sanity**: None (orchestration logic)
  - **Definition of Done**:
    - Test: Game loop runs 10 rounds with mock agents
    - Assertion: Loop terminates correctly, state persists between rounds

- [ ] **Task 8**: Implement checkpointing for overnight runs
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 7
  - Notes: Save state every N rounds, resume capability, kill switch
  - **Sanity**: None (file I/O)
  - **Definition of Done**:
    - Test: Battle can be stopped and resumed from checkpoint
    - Assertion: Resumed battle continues from last checkpoint round

### P3: Reporting (Sequential after P2)

- [ ] **Task 9**: Implement report generation
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 7, Task 8
  - Notes: Executive summary, vulnerability report, attack evolution, defense timeline, winner declaration
  - **Sanity**: None (markdown/JSON generation)
  - **Definition of Done**:
    - Test: Report generates from sample battle data
    - Assertion: Report contains all required sections with correct data

- [ ] **Task 10**: Implement CLI interface
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 7
  - Notes: Typer CLI with battle, status, resume, report commands
  - **Sanity**: None (typer CLI)
  - **Definition of Done**:
    - Test: `./run.sh --help` shows all commands
    - Assertion: `./run.sh battle --target . --rounds 10` executes

### P4: Validation (After All Previous)

- [ ] **Task 11**: Create comprehensive sanity.sh
  - Agent: general-purpose
  - Parallel: 4
  - Dependencies: Task 10
  - Notes: Test all components, run mini-battle (10 rounds)
  - **Sanity**: N/A (this IS the sanity test)
  - **Definition of Done**:
    - Test: `./sanity.sh` passes all checks
    - Assertion: Exit code 0, all components functional

- [ ] **Task 12**: Run full integration test (100 rounds)
  - Agent: general-purpose
  - Parallel: 4
  - Dependencies: Task 11
  - Notes: Full battle with real hack/anvil integration, verify scoring and reporting
  - **Sanity**: N/A (integration test)
  - **Definition of Done**:
    - Test: 100-round battle completes with winner declared
    - Assertion: Report generated, scores calculated, no errors

---

## Completion Criteria

- [ ] All sanity scripts pass
- [ ] All tasks marked [x]
- [ ] `./run.sh battle --target . --rounds 10` executes successfully
- [ ] Task-monitor shows battle progress
- [ ] Report generated with winner and insights
- [ ] No regressions in hack or anvil skills

## Notes

Key patterns from research:
- **RvB Framework**: Sequential game, externalized state, entropy termination
- **AIxCC Scoring**: 3x weight for patches vs discovery, time decay
- **PyRIT**: Multi-turn orchestration, objective scoring
- **DeepTeam**: Async batch processing for scale

Memory integration is critical - both teams should recall prior strategies.
