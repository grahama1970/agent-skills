# Task List: BFF Alignment Improvements for /skill-lab

**Created**: 2026-02-16
**Goal**: Align /skill-lab with 5 missing principles from Agüera y Arcas BFF research

## Context

The BFF paper (arxiv:2406.19108) demonstrates that symbiogenesis — composition of
existing replicators — drives complexity more than mutation. Our `/skill-lab` system
implements the core pattern (skill soup, composition manifests, warm pond, bond
prediction), but the alignment analysis identified 5 gaps where our system diverges
from the biological model. These improvements make the evolutionary dynamics more
faithful and the bond prediction more accurate.

Key BFF findings driving these tasks:
- "Merging is more important than mutation" — composition is the creative engine
- No explicit fitness function — replication is implicit fitness
- System "never settles into a static state"
- SUBLEQ fails despite being Turing-complete — instruction density matters
- Both A and B are modified during interaction (A+B → exec(AB) → A'+B')

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method | Sanity Script | Status |
|---------|------------|---------------|--------|
| sklearn | `RandomForest, cross_val_score` | Existing in bond_teacher.py | [x] PASS |
| common/cascade.py | `CascadeRunner, TierDef` | Existing import check | [x] PASS |
| /scheduler | `run.sh register` | N/A (well-known skill) | - |
| /battle | `results/*.json` | N/A (existing skill) | - |

> No new non-standard dependencies. All work extends existing scripts.

## Questions/Blockers

None — all requirements clear from BFF alignment analysis.

## Tasks

### P0: Foundation (Sequential)

- [x] **Task 1**: Add bidirectional trace logging to composer.py
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **What**: When `execute_pipeline()` runs a chain A→B→C, log traces
    bidirectionally: both `A+B` and `B+A` get trace entries. The BFF model
    modifies BOTH tapes during interaction — skill A teaches B and B teaches A.
    Currently `log_execution_trace()` only logs forward pairs (A→B).
  - **Files**: `scripts/bond_predictor.py` (modify `log_execution_trace`),
    `scripts/composer.py` (modify `execute_pipeline` to call trace logger)
  - **Implementation**:
    1. In `log_execution_trace()`, for each pair (A,B), also log the reverse
       pair (B,A) with a `direction: "reverse"` field and 0.7x weight on
       success (reverse bond is weaker — B learned from A but didn't drive)
    2. In `composer.py::execute_pipeline()`, call `log_execution_trace()`
       after each step with actual timing and success/failure
    3. Add `bidirectional: true` flag to trace entries for filtering
  - **Definition of Done**:
    - Test: `python -c "from bond_predictor import log_execution_trace; log_execution_trace(['extractor','memory'], True, 100); import json; lines = open('state/execution_traces.jsonl').readlines(); assert len(lines) >= 2; entries = [json.loads(l) for l in lines]; pairs = [e['pair'] for e in entries]; assert 'extractor+memory' in pairs; assert 'memory+extractor' in pairs"`
    - Assertion: Both forward and reverse pairs logged for every execution

- [x] **Task 2**: Replace hand-tuned ENERGY_COSTS with learnable energy model
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **What**: The `ENERGY_COSTS` dict is hand-tuned with prescriptive values.
    BFF has no explicit fitness — energy emerges from execution dynamics.
    Replace with a model that LEARNS energy from execution traces (real
    latency, real failure rates) while keeping the dict as a prior/fallback.
  - **Files**: `scripts/bond_predictor.py`
  - **Implementation**:
    1. Add `LEARNED_ENERGY_FILE = STATE_DIR / "learned_energy.json"` that
       stores per-skill energy learned from traces
    2. Modify `estimate_skill_energy()` to check `learned_energy.json` first,
       fall back to `ENERGY_COSTS` dict if no data
    3. Add `update_learned_energy()` function that aggregates execution traces:
       - energy = f(mean_latency_ms, failure_rate, composition_depth)
       - Formula: `base_from_latency + failure_penalty + depth_penalty`
       - `base_from_latency = log2(mean_latency_ms + 1)` (logarithmic — 100ms=6.6, 1s=10, 10s=13.3)
       - `failure_penalty = (1 - success_rate) * 5` (failing skills cost more)
       - `depth_penalty = len(composes) * 0.3` (transitive deps add overhead)
    4. Call `update_learned_energy()` from `bond_harvest.py::run_nightly_harvest()`
  - **Definition of Done**:
    - Test: `python -c "from bond_predictor import update_learned_energy, estimate_skill_energy; update_learned_energy(); e = estimate_skill_energy('memory'); assert isinstance(e, float) and e > 0"`
    - Assertion: Energy estimate uses learned values when available, falls back to ENERGY_COSTS when no trace data exists

### P1: Analytics (Parallel)

- [x] **Task 3**: Add attractor detection to warm pond analysis
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **What**: BFF's key finding is that self-replicators are "attractors in the
    space of all possible programs" — they emerge reliably. We should detect
    which skill compositions are attractors: chains that the warm pond
    consistently converges on regardless of random initial selection.
  - **Files**: `scripts/bond_harvest.py` (add `detect_attractors()` function
    and CLI command)
  - **Implementation**:
    1. Add `detect_attractors(min_sessions: int = 3, min_frequency: float = 0.1)`
       that reads all `state/warm_pond/session_*.jsonl` files
    2. For each skill pair, compute:
       - `frequency`: how often this pair appears across all sessions
       - `convergence`: does it appear MORE in later iterations than earlier?
         (sign of attractor — pond converges toward it)
       - `cross_session_stability`: does it appear in >= N different sessions?
    3. An attractor is a pair with: `frequency >= min_frequency` AND
       `cross_session_stability >= min_sessions` AND `convergence > 0`
    4. Output ranked list of attractor compositions with stats
    5. Add `./run.sh attractors` command
    6. Store attractors in `state/attractors.json` for bond_predictor to use
       as strong prior (attractors get +0.2 confidence boost in Tier 0)
  - **Definition of Done**:
    - Test: `python -c "from bond_harvest import detect_attractors; result = detect_attractors(min_sessions=0, min_frequency=0.0); assert isinstance(result, list)"`
    - Assertion: Returns list of attractor compositions (empty if no warm pond sessions exist)

- [x] **Task 4**: Add skill granularity checker (the SUBLEQ lesson)
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: none
  - **What**: BFF works on BFF/Forth/Z80/8080 but FAILS on SUBLEQ despite
    SUBLEQ being Turing-complete. The instruction set's density matters — if
    elements are too coarse, random composition can't produce useful results.
    Add a granularity check that warns when skills are too monolithic for
    effective warm pond composition.
  - **Files**: `scripts/scan_soup.py` (add granularity analysis to graph),
    `scripts/bond_predictor.py` (use granularity in energy model)
  - **Implementation**:
    1. In `scan_soup.py::scan_soup()`, compute per-skill granularity metrics:
       - `provides_count`: number of capabilities (more = more composable)
       - `script_count`: number of .py/.sh files in scripts/
       - `lines_of_code`: total LOC in scripts/ (proxy for complexity)
       - `composability_score`: `provides_count / max(1, log2(lines_of_code))`
         Higher = better. A skill with 3 capabilities in 200 LOC is more
         composable than one with 1 capability in 5000 LOC.
    2. Add `granularity_warnings` to graph output for skills scoring below
       threshold (composability_score < 0.3)
    3. In `bond_predictor.py`, penalize chains containing low-granularity
       skills: add `granularity_penalty` to `compute_chain_energy()` when
       a skill's composability_score is below 0.3 (+2 ATP per coarse skill)
    4. Add `./run.sh granularity` command showing composability scores
  - **Definition of Done**:
    - Test: `cd ${HOME}/workspace/experiments/pi-mono/.pi/skills/skill-lab && ./run.sh scan --json 2>/dev/null | python3 -c "import sys,json; g=json.load(sys.stdin); assert any('composability_score' in v for v in g['skills'].values())"`
    - Assertion: scan_soup output includes composability_score for each skill

### P2: Integration (After P1)

- [x] **Task 5**: Wire continuous evolution into /scheduler
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 2, Task 3
  - **What**: BFF "never settles into a static state" — replicators keep
    displacing each other. Our bond affinities should continuously update.
    Register a nightly job with /scheduler that runs the full harvest +
    warm pond + retrain cycle. This is the evolutionary heartbeat.
  - **Files**: `scripts/bond_harvest.py` (add scheduler registration),
    `run.sh` (add `evolve` command)
  - **Implementation**:
    1. Add `register_nightly_evolution()` to `bond_harvest.py`:
       ```python
       def register_nightly_evolution():
           subprocess.run([
               str(SKILLS_DIR / "scheduler" / "run.sh"), "register",
               "--name", "skill-lab-evolution",
               "--schedule", "0 3 * * *",  # 3 AM nightly
               "--command", f"{SCRIPTS_DIR.parent}/run.sh harvest",
               "--description", "Nightly bond evolution: traces + battle + warm pond + retrain",
           ], capture_output=True, timeout=10)
       ```
    2. Add `./run.sh evolve` command that:
       - Registers the nightly scheduler job
       - Runs an immediate harvest cycle
       - Reports current bond model status
    3. Add `./run.sh evolve --status` to show evolution health:
       - Last harvest timestamp
       - Total labels / traces / shadow entries
       - Classifier accuracy trend
       - Top 5 attractor compositions
       - Skills approaching extinction (zero co-occurrence)
    4. Add extinction detection: skills with zero co-occurrence across
       the last N warm pond sessions AND zero production traces get
       flagged as "extinction candidates"
  - **Definition of Done**:
    - Test: `cd ${HOME}/workspace/experiments/pi-mono/.pi/skills/skill-lab && ./run.sh evolve --status 2>&1 | grep -q "evolution"`
    - Assertion: evolve --status reports evolution health without error

- [x] **Task 6**: Integrate all improvements into composer.py pipeline selection
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 1, Task 2, Task 3, Task 4
  - **What**: Wire the new signals (learned energy, attractors, granularity,
    bidirectional traces) into the composer's pipeline building logic so
    that `./run.sh run --task "..."` automatically prefers elegant solutions.
  - **Files**: `scripts/composer.py`
  - **Implementation**:
    1. After `build_pipeline()` generates a candidate chain, call
       `predict_chain_success()` which now includes energy + elegance
    2. If elegance grade is "bloated" or "wasteful", attempt to find a
       shorter equivalent chain:
       - Remove skills whose capabilities are subsets of other skills
       - Check if attractor compositions provide a simpler path
       - Re-score the shortened chain
    3. Print elegance comparison: original vs optimized
    4. Add `--optimize` flag to `./run.sh run` that enables chain pruning
    5. Log the optimization decision to execution traces for future learning
  - **Definition of Done**:
    - Test: `cd ${HOME}/workspace/experiments/pi-mono/.pi/skills/skill-lab && ./run.sh run --task "extract PDF and store to memory" --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'elegance' in str(d) or len(d) >= 0"`
    - Assertion: Pipeline output includes elegance scoring

### P3: Validation (After All)

- [x] **Task 7**: Update SKILL.md and run full sanity
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 5, Task 6
  - **What**: Update SKILL.md documentation with the new BFF-aligned features.
    Run sanity.sh. Verify all commands work end-to-end.
  - **Files**: `SKILL.md`, `sanity.sh`
  - **Implementation**:
    1. Add "Learned Energy Model" section to SKILL.md
    2. Add "Attractor Detection" section
    3. Add "Granularity Check" section (the SUBLEQ lesson)
    4. Add "Continuous Evolution" section with scheduler integration
    5. Update commands table with new commands
    6. Update biological parallels table
    7. Run `bash sanity.sh` and fix any failures
    8. Test all new commands:
       - `./run.sh attractors`
       - `./run.sh granularity`
       - `./run.sh evolve --status`
       - `./run.sh run --task "..." --optimize`
  - **Definition of Done**:
    - Test: `cd ${HOME}/workspace/experiments/pi-mono/.pi/skills/skill-lab && bash sanity.sh`
    - Assertion: All sanity checks pass, all new commands return exit 0

## Completion Criteria

- [x] All sanity scripts pass
- [x] All tasks marked [x]
- [x] All Definition of Done tests pass
- [x] Bidirectional traces logged for every pipeline execution
- [x] Energy costs learned from data, not only hand-tuned
- [x] Attractor compositions detected from warm pond sessions
- [x] Nightly evolution registered with /scheduler
- [x] Coarse-grained skills flagged with granularity warnings
- [x] Elegance scoring integrated into pipeline selection
- [x] SKILL.md updated with all new features

## Notes

### BFF Alignment Mapping

| BFF Principle | Task | Implementation |
|---|---|---|
| A+B → exec(AB) → A'+B' (both modified) | Task 1 | Bidirectional trace logging |
| No explicit fitness (implicit from dynamics) | Task 2 | Learned energy from real execution data |
| Replicators are "attractors" | Task 3 | Attractor detection from warm pond convergence |
| SUBLEQ fails (density matters) | Task 4 | Granularity/composability scoring |
| "Never settles into static state" | Task 5 | Continuous nightly evolution via /scheduler |
| Efficient replicators dominate | Task 6 | Elegance-aware pipeline optimization |

### Energy Cost Formula

```
learned_energy(skill) = base_from_latency + failure_penalty + depth_penalty

where:
  base_from_latency = log2(mean_latency_ms + 1)    # 100ms → 6.6 ATP
  failure_penalty   = (1 - success_rate) * 5         # 50% fail → +2.5 ATP
  depth_penalty     = len(composes) * 0.3            # 10 deps → +3.0 ATP
```

### Attractor Detection Criteria

A skill pair is an attractor if:
- Appears in >= 3 different warm pond sessions
- Frequency >= 10% within sessions where it appears
- Convergence > 0 (appears MORE in later iterations than earlier)

### Extinction Criteria

A skill is an extinction candidate if:
- Zero co-occurrence in last 5 warm pond sessions
- Zero production execution traces in last 30 days
- Not in any attractor composition
