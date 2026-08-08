---
name: monitor-skills
description: >
  Continuous skill health monitoring with auto-drift correction.
  Runs every N minutes to ensure all projects have the newest skills.
  Never worry about skill drift again.
triggers:
  - monitor skills
  - skill drift
  - sync skills auto
  - skills health
allowed-tools:
  - Bash
  - Read
metadata:
  short-description: Auto-correct skill drift across all projects
provides:
  - skill-monitoring
  - model-health-monitoring
composes:
  - common
  - create-figure
  - task-monitor
  - agentic-evals
taxonomy:
  - observability
  - drift-detection
disciplines:
  - observability-operations
  - developer-tooling
---

# Monitor Skills

**Continuous skill monitoring with auto-drift correction.** Never worry about skill drift again.

## How It Works

```
Every 15 minutes:
  1. Scan all registered projects for skill versions
  2. For each skill, find the NEWEST version
  3. Auto-sync newest → canonical → all projects
  4. Report any conflicts to agent-inbox
  5. Update task-monitor with status
```

## Quick Start

```bash
cd .pi/skills/monitor-skills

# One-time check and auto-correct
./run.sh sync

# Check drift without correcting
./run.sh check

# Show current health status
./run.sh status

# Register for continuous monitoring (every 15 min)
./run.sh register --interval 15m

# View sync history
./run.sh history
```

## Commands

### `sync` - Auto-correct drift now

```bash
./run.sh sync [OPTIONS]
  --dry-run         Preview without syncing
  --skill NAME      Sync specific skill only
  --force           Overwrite even if destination is newer
```

Finds the newest version of each skill and syncs to all locations.

### `check` - Drift report only

```bash
./run.sh check [OPTIONS]
  --json            Output as JSON
  --skill NAME      Check specific skill
```

Reports drift without auto-correcting. Useful for understanding state.

### `status` - Health dashboard

```bash
./run.sh status
```

Shows:
- Last sync time
- Skills with active drift
- Sanity test pass rates
- Projects with missing skills

### `register` - Enable continuous monitoring

```bash
./run.sh register [OPTIONS]
  --interval 15m    Sync frequency (default: 15m)
  --disable         Disable continuous monitoring
```

Registers with scheduler for automatic drift correction.

### `history` - View sync log

```bash
./run.sh history [OPTIONS]
  --limit N         Show last N entries (default: 20)
  --skill NAME      Filter by skill
```

## Sync Strategy

For each skill across all projects:

1. **Find newest** - Compare modification times of key files (*.py, *.md, *.sh)
2. **Content hash** - Verify content actually differs (not just timestamps)
3. **Sync to canonical** - Push newest to ~/workspace/experiments/agent-skills/skills
4. **Broadcast** - Sync canonical to all registered projects
5. **Log** - Record sync action for history

**Conflict handling:**
- Newest always wins (per-skill, not per-project)
- Conflicts logged to agent-inbox for awareness
- Never delete skills, only update or add

## Scheduler Integration

```bash
# Register for 15-minute auto-sync
./run.sh register --interval 15m

# Creates scheduler job:
#   monitor-skills-sync: */15 * * * *
```

The scheduler job:
1. Runs `./run.sh sync --quiet`
2. Reports to task-monitor
3. Notifies agent-inbox on conflicts

## Task Monitor Integration

Every sync updates task-monitor state at:
```
~/.pi/monitor-skills/task_state.json
```

Tracks:
- Skills synced this run
- Conflicts detected
- Projects updated
- Last successful sync

## Registered Projects

Same as skills-broadcast - reads from:
```
~/.agent_skills_targets
```

Default targets:
- ~/workspace/experiments/agent-skills (canonical)
- All projects in ~/.agent_skills_targets
- ~/.pi/agent/skills (global)

## Notification on Conflicts

When drift is auto-corrected, a notification is sent to agent-inbox:

```markdown
## Skill Drift Auto-Corrected

| Skill | Source | Synced To |
|-------|--------|-----------|
| dogpile | pi-mono/.agent | 5 projects |
| memory | memory/.agents | 5 projects |

No action needed - drift was automatically resolved.
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONITOR_SKILLS_INTERVAL` | 15m | Sync frequency |
| `MONITOR_SKILLS_QUIET` | 0 | Suppress output |
| `MONITOR_SKILLS_DRY_RUN` | 0 | Preview mode |
| `MONITOR_SKILLS_NOTIFY` | 1 | Send notifications |

## Relationship to Other Skills

| Skill | Purpose | How monitor-skills uses it |
|-------|---------|---------------------------|
| `skills-broadcast` | Sync mechanism | Uses rsync logic for actual sync |
| `skills-ci` | Validation | Runs after sync to verify health |
| `task-monitor` | Progress tracking | Reports sync status |
| `agent-inbox` | Notifications | Sends conflict alerts |
| `scheduler` | Automation | Registers continuous job |

## Skill Gap Detection

**Detects skills that should exist but don't.** Mines transcripts and episodic archives for unserved user requests, then validates via a 3-tier Shadow-LEGO cascade.

### Commands

```bash
# Run gap detection (preview mode)
./run.sh gap-scan --dry-run --json

# Run gap detection (persist results, notify inbox)
./run.sh gap-scan

# Show gap scan history and state
./run.sh gap-status

# Register nightly 4:00 AM job + existing sync
./run.sh register-nightly
```

### Pipeline Phases

1. **Mine transcripts** — `chain_miner.mine_sessions(min_skills=0)` for 0-skill or frustrated sessions
2. **Query episodic archives** — `memory/run.sh recall` for abandoned/failed sessions
3. **Deduplicate** — SHA-256 hash against `gap_seen_hashes.json`
4. **3-tier cascade** via `CascadeRunner`:
   - Tier 0 (heuristic): `gap_detector.detect_gaps()` + `transition_matrix.detect_missing_skills()`
   - Tier 0.5 (classifier): sklearn RF on gap features (`shadow_mode=True`)
   - Tier 2 (teacher): `gap_synthesizer._tier_scillm()` (`is_teacher=True`)
5. **Rank proposals** — `energy_model` + `bond_predictor` → elegance score
6. **Persist & notify** — log to JSONL, shadow comparison, agent-inbox, /memory

### State Files (`~/.pi/monitor-skills/`)

| File | Format | Purpose |
|------|--------|---------|
| `gap_labels.jsonl` | JSONL | Teacher labels for classifier training |
| `gap_proposals.jsonl` | JSONL | Ranked gap proposals for human review |
| `gap_shadow.jsonl` | JSONL | Classifier vs teacher agreement |
| `gap_seen_hashes.json` | JSON | Dedup: already-processed request hashes |
| `task_state_gap.json` | JSON | Task-monitor integration |

### Nightly Schedule

```
3:00 AM  — monitor-taxonomy T1 (heuristic probes + autofix)
3:15 AM  — monitor-taxonomy T1.5 (classifier probes)
3:30 AM  — monitor-taxonomy T2 (Brandon teacher)
4:00 AM  — monitor-skills gap-scan (this)
4:15 AM  — skill-lab harvest (bond_harvest nightly)
```

### Auto-Trigger Integration

When `gap_labels.jsonl` accumulates ≥ 30 teacher labels and no `gap_classifier.pkl` exists, `probe_auto_trigger()` (Trigger #5) fires `skill-lab/run.sh train train-classifier` to bootstrap the Tier 0.5 classifier.

## Silo Detection

**Architectural violation scanner.** Detects skills that bypass shared infrastructure (`/memory`, `/taxonomy`) by reimplementing AQL queries, bridge extraction, or search logic locally. These silos cause data fragmentation and make centralized improvements invisible to the offending skill.

### What It Detects

#### 1. Raw AQL Outside /memory

Skills should use `/memory recall`, `/memory learn`, or the `arango_client.py` shared layer -- never raw AQL strings.

**Scan command:**
```bash
rg "db\.aql\.execute|FOR.*IN.*FILTER" .pi/skills/ --type py -l
```

**Patterns flagged:**
- `db.aql.execute(` -- direct ArangoDB query execution
- `FOR doc IN <collection> FILTER` -- inline AQL query strings

#### 2. Custom Bridge/Taxonomy Extraction

Skills should use `/taxonomy extract` for bridge attribute tagging -- never maintain their own keyword dictionaries.

**Scan command:**
```bash
rg "bridge_keywords|BRIDGE_TERMS|precision.*resilience.*fragility|Stealth.*Corruption.*Loyalty" .pi/skills/ --type py -l
```

**Patterns flagged:**
- Hardcoded bridge attribute dictionaries (`bridge_keywords`, `BRIDGE_TERMS`)
- Inline lists of bridge dimensions (Precision, Resilience, Fragility, Corruption, Loyalty, Stealth)

#### 3. Custom BM25/Vector Search Implementations

Skills should use `/memory recall` for retrieval -- never reimplement BM25 or vector similarity search.

**Scan command:**
```bash
rg "BM25|bm25_score|cosine_similarity|vector_search|ANALYZER.*text_en" .pi/skills/ --type py -l
```

**Patterns flagged:**
- Custom BM25 scoring functions
- Local cosine similarity implementations
- Direct ArangoSearch analyzer usage (`ANALYZER(... "text_en")`)

### Known Exceptions

These files are intentionally allowed to contain the flagged patterns:

| File | Reason |
|------|--------|
| `sparta-intent/arango_exec.py` | EXECUTION layer for intent-mapped queries -- this IS the AQL interface by design |
| `extract_training_data.py` | Classifier training data export -- offline tooling, not runtime |

### Running the Full Silo Scan

```bash
# Step 1: Find all AQL usage in skills
rg "db\.aql\.execute|FOR.*IN.*FILTER" .pi/skills/ --type py -n

# Step 2: Find custom bridge/taxonomy extraction
rg "bridge_keywords|BRIDGE_TERMS|precision.*resilience.*fragility|Stealth.*Corruption.*Loyalty" .pi/skills/ --type py -n

# Step 3: Find custom search implementations
rg "BM25|bm25_score|cosine_similarity|vector_search|ANALYZER.*text_en" .pi/skills/ --type py -n

# Step 4: Cross-reference against exceptions
# Remove matches in: sparta-intent/arango_exec.py, extract_training_data.py
```

### Health Report Format

Violations appear in the health report under **Architectural Violations**:

```markdown
## Architectural Violations (Silo Detection)

| Violation Type | File | Line | Pattern |
|----------------|------|------|---------|
| Raw AQL | skills/foo/bar.py | 42 | db.aql.execute("FOR doc IN...") |
| Custom Bridge | skills/baz/extract.py | 17 | BRIDGE_TERMS = {"Stealth": ...} |
| Custom Search | skills/qux/find.py | 89 | cosine_similarity(vec_a, vec_b) |

**Action required:** Refactor to use /memory or /taxonomy shared infrastructure.
Exceptions: sparta-intent/arango_exec.py (execution layer), extract_training_data.py (offline training).
```

### Integration with Sync Cycle

The silo detection scan runs as part of every `./run.sh check` and `./run.sh status` invocation. Violations are:

1. Reported in the health dashboard output
2. Logged to task-monitor state
3. Sent to agent-inbox if new violations appear since the last scan

Zero violations is the target. Any new violation should be fixed before the next sync cycle.

## Visualization

After health checks or drift scans, offer to visualize via `/create-figure`:

```bash
# Skill drift across projects (which projects are stale)
create-figure heatmap --input drift.json --output drift-heatmap.png

# Silo violation trend over time
create-figure metrics --input violations.json --output silo-trend.png --type line --title "Silo Violations"

# Gap proposal ranking
create-figure metrics --input gap_proposals.jsonl --output gaps.png --type hbar --title "Skill Gap Proposals"
```

**When to offer:** After presenting drift or silo scan results, ask: "Want me to visualize the health status?"

## Why Auto-Correct?

Manual drift management doesn't scale:
- Easy to forget to sync after edits
- Multiple projects means multiple sync points
- Conflicts compound over time

Auto-correction ensures:
- Newest version always wins
- All projects stay current
- No manual sync needed
- Conflicts are logged, not lost

## Agent Behavior Rule (Non-Negotiable)

- The agent MUST NOT stop and wait for the human to ask for status or remember to check
- If a cycle fails, diagnose the failure, attempt auto-repair, and continue
- Only escalate to the human if genuinely blocked after exhausting /dogpile research

**Anti-pattern**: Reporting status and waiting for the human to ask "what next?" is UNACCEPTABLE. The agent must proactively fix issues and continue the monitoring loop.

## Common Mistakes

### WRONG: Using rsync --delete when syncing skills
```bash
rsync --delete source/ dest/  # can wipe entire skill directories
```

### RIGHT: Use additive sync only (--update)
```bash
rsync --update source/ dest/  # never deletes, only updates newer files
```

### WRONG: Reimplementing AQL queries, bridge extraction, or search in a skill
```python
db.aql.execute("FOR doc IN lessons FILTER ...")  # silo! use /memory
```

### RIGHT: Use /memory and /taxonomy shared infrastructure
```bash
.pi/skills/memory/run.sh recall --q "query" --collections lessons
.pi/skills/taxonomy/run.sh extract "text to tag"
```

### WRONG: Reporting drift status and waiting for human to ask what to do
```bash
./run.sh check  # reports drift, then stops
```

### RIGHT: Auto-correct drift proactively
```bash
./run.sh sync  # auto-corrects, then reports what changed
```
