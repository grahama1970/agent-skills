# Runtime Integration Patterns

These patterns ensure skills integrate well with the broader agent ecosystem.

## Task-Monitor Integration (MANDATORY — No Exceptions)

**ALL skills MUST report to `/task-monitor`.** This is non-negotiable. Every skill — whether batch, nightly, one-shot, or continuous — must start a session, report accomplishments, and end the session. Without task-monitor integration, skill execution is invisible: failures go undetected, progress is unmeasured, and the system cannot self-diagnose.

Skills that process multiple items should additionally report per-item progress.

### Minimum Pattern: Session Start/End (ALL skills)

Every skill must at minimum call `start-session` and `end-session`:

```python
import subprocess
from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent
TM_RUN = SKILLS_DIR / "task-monitor" / "run.sh"

def _tm(args: list[str]) -> bool:
    if not TM_RUN.exists():
        return False
    try:
        return subprocess.run(
            [str(TM_RUN), *args],
            capture_output=True, text=True, timeout=30,
        ).returncode == 0
    except Exception:
        return False

## Minimal template

```markdown
---
name: example-skill
description: >
  One-sentence description with trigger phrases (what users will ask for).
---

## Batch Skill Template

For skills with batch operations, include these sections in SKILL.md:

```markdown

## Anti-patterns

- Missing or fenced frontmatter.
- Overlong `SKILL.md` that duplicates references.
- CHANGELOG files inside a skill (README.md is allowed for `provides:` skills).
- Hidden dependencies or undocumented environment assumptions.
- **Rolling your own YAML parser** — use `pyyaml`. Minimal/fallback parsers silently
  break on `>` fold syntax, `|` literal blocks, nested dicts, and quoted strings.
  The `/skill-lab` scan_soup.py bug (Feb 2026) caused ALL 166 skill descriptions to
  register as empty `[]` in `/memory` because the fallback parser treated `>` as a
  list indicator. This made capability-aware routing useless — BM25 couldn't match
  task queries to skills because the description field was blank.
- **Reimplementing helper skills** — if a helper skill already exists, import/call it
  instead of writing bespoke code. Skills compose, not duplicate. Key delegations:
  - YouTube ops → `ingest-youtube` (search, download, transcripts, IPRoyal rotation)
  - Stem separation → `create-stems`
  - LLM completions → `scillm`
  - Embeddings → `embedding`
  - Web search → `brave-search`, `dogpile`
  - PDF extraction → `extractor`
  - Memory recall/learn → `memory`
- **Using argparse or click** — all Python CLIs use `typer`. Argparse and click are banned.
  The codebase has been fully migrated (Feb 2026). Do not re-introduce them.
- **Missing dotenv loading** — any `.py` file that calls `os.getenv()` MUST load `.env`
  at module level before the first call. Use `dotenv_helper.load_env()` or the inline
  `load_dotenv(find_dotenv(usecwd=True), override=False)` pattern. See
  `best-practices-python/rules/conventions-dotenv-required.md` for details.
- **Missing antipattern documentation** — skills composed by 3+ other skills MUST have
  a `## Common Mistakes` section with concrete WRONG/RIGHT examples. Format:
  ```
  ## Common Mistakes

  WRONG: data.get("results", [])
  RIGHT: data.get("items", [])
  WHY: API returns "items" not "results"

  WRONG: curl http://localhost:8601/recall
  RIGHT: curl --unix-socket /run/user/1000/embry/memory.sock http://localhost/recall
  WHY: Memory daemon uses Unix socket, not TCP
  ```
  Agents misuse high-fan-in skills repeatedly. Prose warnings don't work — only
  concrete code examples prevent the same mistake from recurring. `/skills-ci` checks
  this (`skills.missing_antipatterns`).
- **Incomplete pyproject.toml dependencies** — every `import` in a skill's `.py` files
  MUST have a corresponding entry in `pyproject.toml` `[project.dependencies]`. After
  adding/modifying any Python file, cross-check imports against declared deps. Run
  `uv sync && uv run python -c "import <module>"` to verify. This is a hard gate —
  missing deps cause `ModuleNotFoundError` after venv recreation, a silent regression
  that only surfaces when the skill runs in isolation or after `/skills-broadcast`.

---

See [PATTERNS.md](PATTERNS.md) for runtime integration patterns including task-monitor, NDJSON streaming, self-correction loops, quality gates, memory integration, and human-in-the-loop.

---

# At start of any run:
_tm(["start-session", "--project", "my-skill"])

# After each meaningful phase:
_tm(["add-accomplishment", "--text", "Phase 1: processed 42 items"])

# At end of run:
_tm(["end-session", "--notes", "Completed successfully: 42 items processed"])
```

### Pattern: task_monitor_client.py (Batch Operations)

For skills that process multiple items, create a `task_monitor_client.py` that additionally:

1. Registers tasks in `~/.pi/task-monitor/registry.json`
2. Writes state to `<skill_name>_task_state.json`
3. Updates progress per item (not just on completion)

```python
# task_monitor_client.py - Minimal structure
from pathlib import Path
import json, time, os
from datetime import datetime

TASK_MONITOR_REGISTRY = Path.home() / ".pi" / "task-monitor" / "registry.json"
STATE_FILE = Path(__file__).parent / "my_skill_task_state.json"

class MySkillTaskClient:
    def __init__(self, task_name: str, total_items: int):
        self.task_name = task_name
        self.total_items = total_items
        self.completed = 0
        self.start_time = time.time()
        self._register_task()
        self._write_state()

    def _register_task(self):
        # Register in ~/.pi/task-monitor/registry.json
        registry = {}
        if TASK_MONITOR_REGISTRY.exists():
            registry = json.loads(TASK_MONITOR_REGISTRY.read_text())
        registry[f"my-skill:{self.task_name}"] = {
            "state_file": str(STATE_FILE),
            "total": self.total_items,
            "project": "my-skill",
        }
        TASK_MONITOR_REGISTRY.write_text(json.dumps(registry, indent=2))

    def _write_state(self, final=False):
        # Write state atomically
        state = {
            "completed": self.completed,
            "total": self.total_items,
            "progress_pct": round(self.completed / self.total_items * 100, 1),
            "status": "completed" if final else "running",
        }
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2))
        os.replace(tmp, STATE_FILE)

    def update(self, **metrics):
        self.completed += 1
        self._write_state()

    def finish(self):
        self._write_state(final=True)
```

### State File Schema (Minimum)

```json
{
  "completed": 50,
  "total": 100,
  "progress_pct": 50.0,
  "status": "running",
  "last_updated": "2026-02-04 08:30:00"
}
```

### CLI Integration

Add these options to batch commands:

| Option                             | Default | Description                 |
| ---------------------------------- | ------- | --------------------------- |
| `--task-monitor/--no-task-monitor` | true    | Enable/disable task-monitor |
| `--json-stream`                    | false   | NDJSON output per item      |

## NDJSON Streaming (Required for Long-Running Batch)

Skills with batch operations MUST support `--json-stream` for real-time progress:

```bash
./run.sh batch items.txt --json-stream | tee results.jsonl

# Each line is valid JSON:
# {"item": "url1", "success": true, "timing_ms": 1234}
# {"item": "url2", "success": false, "error": "timeout"}
```

### Benefits

- Real-time monitoring: `tail -f results.jsonl | jq`
- Resume from partial runs (parse last line for progress)
- Integration with streaming parsers
- Separates progress from final summary

## Self-Correction Loops (Recommended for Validation Tasks)

Skills that validate LLM outputs SHOULD implement self-correction:

### Pattern: Send Invalid Back to LLM

```
1. Call LLM with vocabulary/schema in prompt
2. Validate response (Pydantic, JSON schema, etc.)
3. If invalid:
   a. Send correction message: "Invalid tags: X. Valid options: Y"
   b. Ask LLM to fix
   c. Track correction rounds
4. Record metrics: corrections_needed, correction_success_rate
```

### Example Correction Prompt

```
Your response contained invalid values.

Invalid: {rejected_values}
Valid options: {allowed_vocabulary}

Please correct your response. Return ONLY valid JSON with values from the allowed list.
```

### Strategy Exhaustion (Alternative Pattern)

For fetch/extraction skills, use strategy exhaustion instead:

```
1. Try learned strategy from /memory (if exists)
2. Try default strategies in order
3. On success: store winning strategy to /memory
4. On all fail: trigger /interview for human help
```

## Quality Gates (Required for Validation Tasks)

Skills that validate outputs MUST define quality gates with thresholds:

### LLM Non-Determinism Tolerance

Use 99.5% thresholds instead of 100% to account for LLM non-determinism:

```python
# Bad: Fails on any imperfection
if success_rate < 1.0:
    raise QualityGateFailed()

# Good: Tolerates LLM variance
if success_rate < 0.995:  # 99.5%
    raise QualityGateFailed()
```

### Gate Metrics Pattern

Track pass/fail per gate:

```python
@dataclass
class GateMetrics:
    passed: int = 0
    failed: int = 0

    @property
    def rate(self) -> float:
        total = self.passed + self.failed
        return self.passed / total if total > 0 else 1.0
```

## Memory Integration (Recommended)

Skills that learn from experience SHOULD integrate with `/memory`:

### Pattern: Learn from Success

```python
# On successful operation
from memory_bridge import learn_strategy

result = try_operation(url)
if result.success:
    learn_strategy(
        url=url,
        strategy_used=result.winning_strategy,
        timing_ms=result.timing_ms,
    )
```

### Pattern: Recall Before Try

```python
# Before trying default approach
from memory_bridge import get_best_strategy

learned = get_best_strategy(url)
if learned:
    # Try learned strategy first
    result = try_strategy(url, learned.strategy)
```

## Human-in-the-Loop (Recommended for Unrecoverable Failures)

Skills with automated workflows SHOULD integrate with `/interview` for human collaboration:

### When to Trigger Interview

- All automated strategies exhausted
- Ambiguous input that needs clarification
- Decision point with significant consequences

### Interview Integration Pattern

```python
from interview_generator import generate_interview

if all_strategies_failed:
    interview = generate_interview(
        context={"url": url, "errors": errors},
        questions=[
            "Do you have credentials for this site?",
            "Should we try a mirror URL?",
            "Skip this URL?",
        ]
    )
    # Write interview JSON for /interview skill
```

---

# Example Skill

Short workflow map here. Link to references/scripts as needed.
```

## Task-Monitor Integration

skill-name integrates with task-monitor for live progress tracking:

\`\`\`bash

# Run with task-monitor (enabled by default)

./run.sh batch items.txt

# View progress

cat skill_name_task_state.json | jq
\`\`\`

## NDJSON Streaming

\`\`\`bash
./run.sh batch items.txt --json-stream | tee results.jsonl
\`\`\`
```
