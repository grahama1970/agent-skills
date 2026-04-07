# Task List: Enhanced QEMU Digital Twin for Battle Skill

## Context

Enhance the battle skill's QEMU mode based on dogpile research findings. The key pattern is:
"Boot once to a stable service boundary, snapshot, then loop inputs with coverage feedback and fast restore."

Research sources: Codex synthesis, FIRM-AFL paper, AFL++ qemuafl, BusyBox fuzzing study.

## Crucial Dependencies (Sanity Scripts)

| Library/Tool | API/Method | Sanity Script | Status |
|--------------|------------|---------------|--------|
| qemu-system-* | `-gdb tcp::1234` | `sanity/qemu_gdb.py` | [x] PASS |
| QEMU savevm/loadvm | snapshot API | `sanity/qemu_snapshot.py` | [x] PASS (4.9ms restore!) |
| Docker + QEMU | container isolation | `sanity/qemu_docker.sh` | [x] PASS |
| qemuafl | AFL++ QEMU mode | `sanity/afl_qemu.sh` | [x] PASS (in Docker) |

> ✅ AFL++ installed in Docker container - all fuzzing runs inside container

## Tasks

### Phase 1: QEMU-in-Docker Foundation

- [x] **Task 1**: Create qemu-twin Dockerfile
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - Notes: Based on research - QEMU should run inside Docker for reproducibility
  - **Sanity**: N/A (infrastructure)
  - **Definition of Done**:
    - Test: `docker build -t battle-qemu-twin .pi/skills/battle/docker/`
    - Assertion: Image builds successfully with qemu-system-arm, qemu-system-riscv64, qemu-system-x86_64

- [x] **Task 2**: Update DigitalTwin._setup_qemu_mode to use Docker
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 1
  - Notes: Wrap QEMU execution in Docker container for isolation
  - **Sanity**: `sanity/qemu_docker.sh`
  - **Definition of Done**:
    - Test: `./run.sh battle firmware.bin --qemu-machine arm --rounds 1`
    - Assertion: QEMU runs inside container, not on host

### Phase 2: Snapshot Management

- [x] **Task 3**: Implement golden snapshot creation
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 2
  - Notes: Create snapshot after boot completes, before fuzzing starts
  - **Sanity**: `sanity/qemu_snapshot.py`
  - **Definition of Done**:
    - Test: Snapshot file created in worktree after boot
    - Assertion: `savevm` command succeeds, snapshot file < 500MB

- [x] **Task 4**: Implement fast snapshot restore for fuzzing loop
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 3
  - Notes: Use QEMU loadvm for sub-second restore between fuzz iterations
  - **Sanity**: `sanity/qemu_snapshot.py`
  - **Definition of Done**:
    - Test: Measure restore time over 100 iterations
    - Assertion: Average restore time < 500ms (achieved: 91.6ms)

- [x] **Task 5**: Add QCOW2 overlay support for Blue team patches
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 3
  - Notes: Blue team patches applied via overlay, preserving original
  - **Sanity**: N/A (uses qemu-img)
  - **Definition of Done**:
    - Test: Blue team creates patch, overlay captures delta
    - Assertion: Original firmware unchanged, patch in overlay

### Phase 3: GDB Integration

- [x] **Task 6**: Add automatic GDB stub configuration
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - Notes: Each team gets unique GDB port, written to config file
  - **Sanity**: `sanity/qemu_gdb.py`
  - **Definition of Done**:
    - Test: `gdb -ex "target remote localhost:PORT" -ex "info registers"`
    - Assertion: GDB connects successfully, registers readable

- [x] **Task 7**: Add symbol loading support
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 6
  - Notes: Load ELF symbols if available, calculate load addresses for PIE
  - **Sanity**: `sanity/qemu_gdb.py`
  - **Definition of Done**:
    - Test: Set breakpoint on known function
    - Assertion: Breakpoint hits at correct address (verified: *0x10000)

### Phase 4: AFL++ Coverage Integration (Red Team)

- [x] **Task 8**: Integrate qemuafl for coverage-guided fuzzing
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 4
  - Notes: Use AFL++ QEMU mode for Red team attacks
  - **Sanity**: `sanity/afl_qemu.sh`
  - **Definition of Done**:
    - Test: AFL++ runs against simple binary in QEMU
    - Assertion: Coverage map populated, execs/sec > 100
    - Implemented: start_afl_fuzzing(), get_fuzzing_stats()

- [x] **Task 9**: Add crash collection and triage
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 8
  - Notes: Capture crashes, restore snapshot, attach GDB for backtrace
  - **Sanity**: N/A (integration)
  - **Definition of Done**:
    - Test: Trigger known crash, verify triage output
    - Assertion: Backtrace shows crash location with symbols
    - Implemented: collect_crashes(), triage_crash()

- [x] **Task 10**: Implement corpus management
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 8
  - Notes: Save interesting inputs, sync between rounds
  - **Sanity**: N/A (file operations)
  - **Definition of Done**:
    - Test: Corpus grows over multiple rounds
    - Assertion: Corpus directory contains > 10 unique inputs after 5 rounds
    - Implemented: add_to_corpus(), get_corpus_stats(), sync_corpus_from_findings()

### Phase 5: Peripheral Stubbing (Prevent Hangs)

- [x] **Task 11**: Add basic peripheral stub configuration
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - Notes: P2IM-style stubs to prevent firmware boot hangs
  - **Sanity**: N/A (QEMU config)
  - **Definition of Done**:
    - Test: Firmware that hangs on real hardware boots in emulator
    - Assertion: Boot completes within 30 seconds
    - Implemented: configure_peripheral_stubs(), _get_peripheral_stub_options()

- [x] **Task 12**: Add MMIO logging for unknown peripherals
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 11
  - Notes: Log MMIO accesses to help debug boot failures
  - **Sanity**: N/A (logging)
  - **Definition of Done**:
    - Test: MMIO log file created during boot
    - Assertion: Log shows address, size, read/write for each access
    - Implemented: enable_mmio_logging(), read_mmio_log(), _get_mmio_log_options()

### Phase 6: Learning Architecture (Critical)

- [x] **Task 13**: Create BattleMemory class with team-specific collections
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - Notes: Each team gets dedicated memory collection (battle_red_<id>, battle_blue_<id>)
  - **Sanity**: Memory skill must be available
  - **Definition of Done**:
    - Test: Store and recall from team-specific collection
    - Assertion: Red cannot access Blue's learnings, vice versa (verified: separate scopes)

- [x] **Task 14**: Add research phase using /dogpile
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 13
  - Notes: Before each attack/defense, team can research strategies via dogpile
  - **Sanity**: Dogpile skill must be available
  - **Definition of Done**:
    - Test: Red team researches "ARM heap overflow exploitation"
    - Assertion: Research results stored in team memory with source attribution
    - Implemented: BattleMemory.research() method

- [x] **Task 15**: Integrate /taxonomy for finding classification
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 13
  - Notes: Classify attacks (CWE), defenses (mitigation type), vulnerabilities (severity)
  - **Sanity**: Taxonomy skill must be available
  - **Definition of Done**:
    - Test: Finding tagged with CWE-122 (heap overflow), CVSS score
    - Assertion: Tags queryable for pattern analysis
    - Implemented: BattleMemory.classify() method

- [x] **Task 16**: Create BattleEpisode archiver (per-round learning)
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 13, Task 15
  - Notes: Based on episodic-archiver pattern - stores full round transcript with embeddings
  - **Sanity**: N/A (new implementation)
  - **Definition of Done**:
    - Test: Complete round, archive episode, query "what worked"
    - Assertion: Episode contains: actions, outcomes, learnings, taxonomy tags
    - Implemented: BattleMemory.store_round_episode() method

- [x] **Task 17**: Implement cross-round strategy evolution
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 14, Task 16
  - Notes: Teams query past episodes to evolve strategies ("last 3 rounds, buffer overflows failed - try format strings")
  - **Sanity**: N/A (integration)
  - **Definition of Done**:
    - Test: Team adapts strategy based on past failures
    - Assertion: Round N+1 strategy differs from Round N based on learnings
    - Implemented: BattleMemory.query_strategy_evolution() method

- [x] **Task 18**: Add pre-round research budget
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 14
  - Notes: Limit research calls per round to prevent infinite loops (e.g., 3 dogpile calls max)
  - **Sanity**: N/A (configuration)
  - **Definition of Done**:
    - Test: Team exceeds budget, gets warning
    - Assertion: Research calls capped, excess logged but not executed

### Phase 7: Update Battle Orchestrator

- [x] **Task 19**: Update RedAgent with learning loop
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 8, Task 14, Task 16
  - Notes: Red team: recall → research → attack → reflect → store
  - **Sanity**: N/A (integration)
  - **Definition of Done**:
    - Test: Red team attack round completes with findings
    - Assertion: Findings include coverage %, crash count, AND stored learnings
    - Implemented: RedAgent.execute_learning_loop() with 5 phases

- [x] **Task 20**: Update BlueAgent with learning loop
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 5, Task 14, Task 16
  - Notes: Blue team: recall → research → defend → reflect → store
  - **Sanity**: N/A (integration)
  - **Definition of Done**:
    - Test: Blue team patches crash, arena verifies fix
    - Assertion: Patch strategy AND outcome stored in team memory
    - Implemented: BlueAgent.execute_learning_loop() with 5 phases

- [x] **Task 21**: Update game loop with learning phases
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 19, Task 20
  - Notes: Each round: Research Phase → Action Phase → Reflection Phase
  - **Sanity**: N/A (integration)
  - **Definition of Done**:
    - Test: Complete 10 rounds, verify learning accumulation
    - Assertion: Round 10 strategies differ from Round 1 based on accumulated knowledge
    - Implemented: RedAgent/BlueAgent.execute_learning_loop() integrates all phases

- [x] **Task 22**: Add round-level snapshot checkpointing
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 3, Task 4, Task 16
  - Notes: Save full battle state including QEMU snapshots AND team memories
  - **Sanity**: N/A (integration)
  - **Definition of Done**:
    - Test: Resume battle from checkpoint
    - Assertion: Battle continues with same state AND accumulated learnings
    - Implemented: save_full_checkpoint() + restore_from_checkpoint() methods

## Completion Criteria

### QEMU Digital Twin
1. QEMU runs inside Docker container (isolated, reproducible)
2. Golden snapshot created after boot, restored in < 500ms
3. GDB attaches successfully with symbol support
4. AFL++ coverage-guided fuzzing works for Red team
5. Blue team patches via QCOW2 overlay
6. Peripheral stubs prevent common boot hangs

### Learning Architecture (Critical)
7. Each team has isolated memory collection (cannot access opponent's learnings)
8. Teams can research via /dogpile before each round
9. All findings classified with /taxonomy (CWE, severity, mitigation type)
10. Per-round episodes archived with embeddings for semantic recall
11. Teams demonstrably evolve strategies based on past rounds
12. Research budget prevents infinite loops
13. Checkpoints include accumulated learnings

## Questions/Blockers

None - proceeding with recommended defaults:
- User-mode QEMU: Optional `--qemu-mode user` flag
- Peripheral stubbing: Minimal (UART, timer, IRQ) + MMIO logging
- Crash triage: GDB scripting first

---

**Note**: Phase 7 (Learning Architecture) is the critical differentiator that makes this a true AI vs AI competition.
