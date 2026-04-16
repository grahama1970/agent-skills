# Task List: 7 Competitive Feature Skills
Created: 2026-02-19
Goal: Implement 7 new skills identified from competitive landscape analysis. Each skill builds on existing infrastructure with no architecture changes.

## Context
From 2026-02-19 competitive landscape analysis (Palantir AIP, MES/digital twin, agentic AI trends), 7 feature gaps were identified. Each is a single skill following SKILL.md + run.sh + sanity.sh conventions. All read existing ArangoDB data or compose existing skills — no new daemons, no new databases, no bloat.

## Crucial Dependencies
| Library/API | Usage | Sanity Script | Status |
|-------------|-------|---------------|--------|
| ArangoDB (localhost:8529) | Graph queries for OSCAL, timeline, assurance case | sanity/arango_conn.py | [x] PASS (embedded in each skill's --dry-run) |
| graphviz (Python) | GSN diagram rendering | sanity/graphviz_render.py | [x] PASS (embedded in create-assurance-case sanity) |
| NIST OSCAL schema | JSON export format | sanity/oscal_schema.py | [x] PASS (embedded in export-oscal validate) |

## Quality Gates (All Tasks)
- Pre-hook: `./sanity.sh` must pass before implementation
- Post-hook: `./sanity.sh` must pass after implementation
- Each skill MUST have: SKILL.md (YAML frontmatter), run.sh, sanity.sh, pyproject.toml
- Each skill MUST follow best-practices-skills conventions

---

## Tasks

### Group 0: Dependency Sanity (Sequential)

- [x] **Task 1**: Create shared sanity script for ArangoDB connectivity
  - Write `sanity/arango_conn.py` that verifies ArangoDB is reachable at localhost:8529 and `lessons` collection exists
  - Definition of Done:
    - Test: `python3 sanity/arango_conn.py` exits 0 when ArangoDB is running
    - Assertion: Script prints "PASS: ArangoDB reachable, lessons collection exists"

- [x] **Task 2**: Create sanity script for graphviz availability
  - Write `sanity/graphviz_render.py` that imports graphviz Python package and renders a trivial dot graph to SVG
  - Definition of Done:
    - Test: `python3 sanity/graphviz_render.py` exits 0 and produces a valid SVG
    - Assertion: Output file is valid SVG (contains `<svg` tag)

- [x] **Task 3**: Create sanity script for OSCAL JSON schema validation
  - Write `sanity/oscal_schema.py` that validates a minimal OSCAL assessment-results JSON document against expected structure
  - Definition of Done:
    - Test: `python3 sanity/oscal_schema.py` exits 0
    - Assertion: Minimal OSCAL document validates with required fields (uuid, metadata, results)

### Group 1: Core Skills — Read-Only Query Skills (Parallel after Group 0)

- [x] **Task 4**: Create `/export-oscal` skill
  - NIST OSCAL JSON export of compliance evidence from ArangoDB
  - Queries `sparta_controls`, `sparta_qra`, and `lessons` collections
  - Outputs OSCAL assessment-results JSON with control implementations and evidence
  - Commands: `export --framework NIST-800-171` `export --framework CMMC-L2` `validate <file.json>`
  - Definition of Done:
    - Test: `./run.sh export --framework NIST-800-171 --dry-run` produces valid OSCAL JSON structure
    - Test: `./sanity.sh` exits 0
    - Assertion: Output contains `assessment-results` with `uuid`, `metadata.title`, and at least one `result`

- [x] **Task 5**: Create `/compliance-timeline` skill
  - Chronological audit view from existing `lesson_revisions` and `edge_revisions` append-only collections
  - Commands: `show --days 30` `show --scope sparta` `diff --from 2026-01-01 --to 2026-02-01`
  - Rich table output with timestamps, action types, affected documents
  - Definition of Done:
    - Test: `./run.sh show --days 30 --dry-run` produces formatted timeline output
    - Test: `./sanity.sh` exits 0
    - Assertion: Output shows chronological entries with timestamp, action, document fields

- [x] **Task 6**: Create `/create-assurance-case` skill
  - GSN (Goal Structuring Notation) diagram from compliance graph
  - Queries ArangoDB for control hierarchies and evidence chains
  - Renders via graphviz to SVG/PNG
  - Commands: `render --control AC-1` `render --framework NIST-800-171` `export-dot --control AC-1`
  - Definition of Done:
    - Test: `./run.sh export-dot --control AC-1 --dry-run` produces valid DOT notation
    - Test: `./sanity.sh` exits 0
    - Assertion: DOT output contains GSN node types (Goal, Strategy, Solution, Context)

- [x] **Task 7**: Create `/monitor-drift-sensors` skill
  - CUSUM and Page-Hinkley statistical drift detection on sensor data streams
  - Reads sensor data from ArangoDB or stdin (JSON lines)
  - Fires D-Bus alerts via `org.embry.State` when drift detected
  - Commands: `watch --sensor vibration --threshold 3.0` `analyze <data.jsonl>` `status`
  - Definition of Done:
    - Test: `./run.sh analyze --dry-run < fixtures/drift_sample.jsonl` detects injected drift
    - Test: `./sanity.sh` exits 0
    - Assertion: Output identifies drift point within 5 samples of injected shift

### Group 2: Composition Skills — Build on Existing Skills (Parallel after Group 1)

- [x] **Task 8**: Create `/bootcamp` skill
  - Guided onboarding via Embry Lawson persona
  - Composes: `/interview` for structured Q&A, `/service-status` for health check, `/data-audit` for pipeline status
  - Commands: `start --role operator` `start --role compliance-officer` `start --role developer` `resume`
  - Steps: welcome → health check → data overview → first query → compliance baseline
  - Definition of Done:
    - Test: `./run.sh start --role developer --dry-run` produces onboarding script with 5+ steps
    - Test: `./sanity.sh` exits 0
    - Assertion: Dry-run output includes welcome, health-check, data-overview, first-query, baseline steps

- [x] **Task 9**: Create `/benchmark-models` skill
  - Standardized compliance QRA tests against candidate LLMs
  - Composes: `/scillm` for model invocation, `/test-lab` patterns for evaluation
  - Commands: `run --model deepseek-v3 --suite compliance-basic` `compare --models "deepseek-v3,llama-3.1-70b"` `report`
  - Measures: accuracy on 20 compliance QRA gold-set, latency p50/p95, token cost
  - Definition of Done:
    - Test: `./run.sh run --model mock --suite compliance-basic --dry-run` produces benchmark scaffold
    - Test: `./sanity.sh` exits 0
    - Assertion: Dry-run output shows test cases, expected metrics columns (accuracy, latency_p50, cost)

- [x] **Task 10**: Create `/sync-sites` skill
  - OSTree static-delta federation for multi-plant deployment
  - Commands: `generate-delta --from <commit> --to <commit>` `apply-delta <delta-file>` `status` `verify-signature <delta-file>`
  - Air-gapped mode: writes delta to specified path (USB mount point)
  - Connected mode: pushes delta to remote OSTree repo
  - Definition of Done:
    - Test: `./run.sh status --dry-run` shows current OSTree deployment info
    - Test: `./sanity.sh` exits 0
    - Assertion: Dry-run status shows deployment hash, origin, and refspec fields

### Group 3: Final Validation (Sequential after all)

- [x] **Task 11**: Cross-skill integration validation
  - Run all 7 new skill sanity.sh scripts in sequence
  - Verify SKILL.md frontmatter has correct `provides` and `composes` fields
  - Verify no duplicate `provides` capabilities across new skills
  - Store all 7 features in `/memory` with embry_os scope for retrieval
  - Definition of Done:
    - Test: All 7 `sanity.sh` scripts exit 0
    - Test: `grep -c "^provides:" .pi/skills/{export-oscal,compliance-timeline,create-assurance-case,monitor-drift-sensors,bootcamp,benchmark-models,sync-sites}/SKILL.md` returns 7
    - Assertion: All 7 skills registered with unique provides capabilities and stored in memory

## Execution Order
- Group 0: Tasks 1-3 sequential (dependency verification)
- Group 1: Tasks 4-7 parallel (after Group 0 passes)
- Group 2: Tasks 8-10 parallel (after Group 1 passes)
- Group 3: Task 11 sequential (final validation)

## Cost Optimization
- Tasks 1-3: Haiku (simple sanity scripts)
- Tasks 4-7: Sonnet (moderate complexity, AQL queries + CLI)
- Tasks 8-10: Sonnet (composition logic, dry-run scaffolding)
- Task 11: Haiku (validation only)
