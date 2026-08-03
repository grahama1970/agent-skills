# Prompt Improvements For The Next Dewey Round

## What worked in this R3 prompt

- It correctly framed the task as `$create-architecture`, not a review.
- It identified that Dewey is not the repair engine; `monitor_sparta.py repair-cycle` owns repair behavior.
- It included raw failure shape: embed processed/synced/dropped all 200, health unchanged, QRA worker still running after 300s.
- It named the ambiguity explicitly as QRA lane Option A/B/C.

## What to improve next time

### 1. Attach the current source files when asking for finished patches

The bundle asked for finished `monitor_sparta.py` changes but did not include the 10,780-line file. For a true finished-file patch round, attach:

```text
memory/scripts/validation/monitor_sparta.py
agent-skills/agents/dba-auditor/scripts/dewey_overnight_run.py
agent-skills/agents/dba-auditor/tests/test_dewey_monitor_sparta_nightly.py
memory/.agents/services.yaml
```

or include a repository diff of the current project-agent attempt.

### 2. Separate stale R1/R2 goals from current R3 goals

The bundle still contained older goals about cron re-enable and Dewey timeout calibration, while the R3 creation brief says the issue is inside `monitor_sparta.py repair-cycle`. Use a current-round section like:

```markdown
Authoritative R3 scope:
- Patch monitor_sparta.py repair-cycle diagnostics only.
- Do not change Dewey orchestration except UNFIXABLE_DIMENSIONS alignment if needed.
- Do not re-enable cron until live mutating proof passes.
```

### 3. State the intended QRA contract unless WebGPT is meant to decide it

A stronger prompt would say either:

```markdown
WebGPT must choose A/B/C and justify it in ARCHITECTURE.md.
```

or:

```markdown
Use Option B unless the bundle proves a bounded QRA repair lane exists.
```

For R3, Option B is the safer contract.

### 4. Require a receipt-shape assertion script

Add this to future acceptance gates:

```bash
python scripts/assert_dewey_r3_receipt_shape.py /tmp/dewey-r3-repair-cycle.json
```

This prevents a visually plausible log from passing without the required machine-readable fields.

### 5. Demand explicit evidence honesty

Use this standard block:

```markdown
Evidence status to report:
- isolated syntax/test evidence: allowed
- live mutating repair-cycle evidence: only claim if actually run with SPARTA_MONITOR_MUTATION_ENABLED=1
- cron enabled: only claim after live repair-cycle proof and morning report proof
```

## Better one-shot prompt template

```markdown
This is `$create-architecture` for Dewey R<N>. Use attached source files as the only code source of truth.

Authoritative scope:
1. Patch `memory/scripts/validation/monitor_sparta.py repair_cycle()` only.
2. Keep Dewey as orchestrator; do not make Dewey call scillm directly.
3. QRA contract: <Option A/B/C>.
4. Return one solution zip with full repo-relative changed files, tests, fixtures, MANIFEST, ARCHITECTURE, prompt_improvements, and exact sanity commands.

Evidence honesty:
- Do not claim live mutation unless a live command output is included.
- Do not re-enable cron without live proof.

If source files are missing, return numbered clarifying questions requesting exact missing files.
```
