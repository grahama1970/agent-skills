## Rule 9: No Hand-Written Prompts — `agent-no-handwritten-prompts`

**Severity: MEDIUM**

ALL LLM prompts MUST go through `/prompt-lab` for iterative evaluation.

```python

## Rule 10: Use /scillm, Not Direct OpenAI — `agent-use-scillm`

**Severity: MEDIUM**

ALL LLM calls go through the scillm proxy at `http://localhost:4001`.
NEVER use `openai.Client()` with direct API keys.

```python

## Rule 11: No Daemon Endpoint Creation in embry-os — `agent-no-daemon-endpoints`

**Severity: MEDIUM**

The daemon in `embry-os/services/memory-daemon/main.py` is a **single-file reverse proxy**.
It forwards requests to the Docker container. NEVER add business logic or new endpoints there.

All endpoint logic lives in: `memory/src/graph_memory/service/app/`

If you need a new endpoint:
1. Add the route in `memory/src/graph_memory/service/app/` (appropriate submodule)
2. Add the Pydantic model in `_models.py`
3. Restart the Docker container
4. The daemon proxy forwards it automatically

---

## Rule 12: Storage on 12TB Drive — `agent-storage-12tb`

**Severity: MEDIUM**

ALL large artifacts go on `/mnt/storage12tb/`. The root NVMe is for code only.

- Model weights → `/mnt/storage12tb/skills/<skill>/models/`
- Training logs → `/mnt/storage12tb/skills/<skill>/logs/`
- Extracted data → `/mnt/storage12tb/skills/<skill>/extracted_runs/`
- Batch results → `/mnt/storage12tb/skills/<skill>/outputs/`

Use symlinks from skill directories.

---

## Rule 13: Don't Over-Engineer Error Handling — `agent-no-over-engineering-errors`

**Severity: MEDIUM**

Adding excessive try/except blocks that catch broad exceptions HIDES bugs.
Only catch exceptions you can handle meaningfully.

```python

## Rule 14: Check Status Codes, Don't Assume Shape — `agent-check-response-shape`

**Severity: MEDIUM**

When parsing API responses, verify the response has the expected shape before accessing fields.

```python

## Rule 15: Mandatory Skill Chains by Task Type — `agent-mandatory-chains`

**Severity: CRITICAL**

Agents MUST follow the prescribed skill chain for each task type. Do NOT skip
verification steps. Do NOT ship unvalidated work.

### Task Type: Multi-File Implementation (COMPLEX)

```
/plan → /review-plan → /orchestrate → /create-walkthrough (optional)
```

- **BLOCKING**: Do NOT start coding until `/plan` produces a reviewed task file
- Triage hook will classify as COMPLEX when task touches 3+ files or crosses skill boundaries
- `/review-plan` validates blind tests, claims, and DoD before `/orchestrate` runs

### Task Type: UI / Frontend / UX Work

```
/ux-lab (prototype) → implement → /review-design (visual audit) → /test-interactions (functional verification)
```

- **BLOCKING**: Do NOT merge UI changes without `/review-design` screenshot review
- `/test-interactions` runs systematic interaction tests against the live UI
- `/ux-lab` is the workbench — prototype there, not in production code

### Task Type: LLM Prompt Writing

```
/prompt-lab (iterate + evaluate) → implement
```

- **BLOCKING**: No hand-written prompts in code. Ever.
- `/prompt-lab` tracks versions, runs evals, measures quality

### Task Type: Evidence / Validation / Assessment

```
/create-evidence-case → /review-conversation → /evidence-case-lab (convergence)
```

- Must show grounding evidence (RESOLVED vs UNRESOLVED)
- Must pass adversarial batch (0% false positive rate)

### Task Type: Data Pipeline / Ingestion

```
/memory recall (check prior) → implement → /taxonomy (tag) → /monitor-* (verify)
```

- NEVER skip `/memory recall` — prior solutions exist for most data problems
- ALL ingested data must be taxonomy-tagged

### Task Type: Moderate Tasks (2-5 files)

```
Consider /plan first → implement → verify
```

- Not mandatory, but strongly recommended
- If the agent's first approach fails, `/plan` becomes mandatory for the retry

### Enforcement via Triage Hook

The `UserPromptSubmit` triage hook classifies every task:

| Classification | Required Chain | Gate |
|---------------|---------------|------|
| **SIMPLE** | None — just do it | Light verification |
| **MODERATE** | `/plan` recommended | Nudge in hook output |
| **COMPLEX** | `/plan` → `/review-plan` mandatory | Hard block in hook output |
| **UI/UX** | `/review-design` + `/test-interactions` mandatory | Hard block |
| **PROMPT** | `/prompt-lab` mandatory | Hard block |

---

## Rule 16: Read Stored Memories Before Acting — `agent-read-memories`

**Severity: CRITICAL**

MEMORY.md and feedback memories are NOT aspirational documentation. They are
**rules from prior sessions** that exist because you already made the mistake.
Ignoring them means the user repeats the same correction every session indefinitely.

### Before ANY significant action

1. **Read MEMORY.md** — it has project context, completed work, and technical notes
2. **Read relevant feedback memories** — they have corrections you've already received
3. **Check if a feedback memory contradicts what you're about to do** — if yes, STOP

### Specific memories that get ignored repeatedly

| Memory | What it says | What agents do instead |
|--------|-------------|----------------------|
| `feedback_uxlab_first.md` | NEVER write TSX without `/ux-lab` pipeline | Blurt out 500+ lines of bespoke TSX |
| `feedback_frictionless_ux.md` | No animations, keyboard-first, dense layouts | Add fancy animations and card-heavy designs |
| `MEMORY.md` project status | Lists completed phases, key decisions | Re-investigate things already decided |

### The test

If the user has to say "I already told you this" — you failed Rule 16.

### `/review-plan` enforcement

`/review-plan` SHOULD check feedback memories and flag task files that contradict
known user preferences as **FAIL**.

---

## Rule 17: Service-First Architecture — `agent-service-first`

**Severity: CRITICAL**

Before writing ANY code that calls another skill via subprocess, you MUST audit
running HTTP services and POST to them instead. Subprocess spawning bypasses
service-level concurrency control, retry logic, rate limiting, health monitoring,
and cost tracking — and wastes ~2s per call in fork overhead.

### Before writing subprocess code

1. Run `docker ps` and `systemctl --user list-units 'embry-*'` to see what's running
2. Check `/health` endpoints on known ports
3. Check `/openapi.json` or `/docs` on the memory daemon for available endpoints
4. Map every planned subprocess call to its HTTP service alternative

### Service registry

| Service | Port | Endpoints | Use instead of |
|---------|------|-----------|----------------|
| embry-memory | Unix socket / 8601 | /learn, /recall, /taxonomy/tag, /taxonomy/batch-tag, /store, /related, /analytics/run | memory/run.sh, taxonomy/run.sh |
| embry-embedding | 8602 | /embed, /embed/batch | embedding/run.sh |
| embry-chutes-call | 8630 | /v1/chat/completions, /batch | doc2qra/run.sh, scillm calls |
| embry-inference | systemd | local LLM | ollama subprocess |

### Decision tree

```
Need to call another skill?
├── Is there a running HTTP service? → POST to it
├── Does memory daemon have the endpoint? → Use it
├── Is it a one-shot CLI tool with no service? → subprocess is OK
└── Would >3 calls happen in a loop? → MUST use HTTP (fork bomb risk)
```

### Bad patterns

```python

## Adding New Rules

When the user corrects a pattern that isn't listed here:
1. Add a new rule with a unique ID (e.g., `agent-new-rule-name`)
2. Include: severity, bad patterns, good patterns, and WHY it matters
3. Update the quick reference checklist if applicable
