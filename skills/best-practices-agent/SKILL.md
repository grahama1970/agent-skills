---
name: best-practices-agent
description: >
  Non-negotiable agent behavior rules. Covers: no silent failures, no error bypassing,
  no raw AQL, no direct imports, no parallel infrastructure, no swallowed exceptions,
  use existing skills, fix errors don't dodge them, transparency in verdicts,
  no simulated reviews, and evidence-gated decisions.
triggers:
  - best practices agent
  - agent rules
  - agent behavior
  - what not to do
  - recurring violations
  - agent anti-patterns
  - silent failures
  - error handling rules
  - bypass errors
  - simulated review
  - fake validation
  - evidence-gated decisions
license: MIT
taxonomy:
  - precision
  - resilience
provides:
  - best-practices-agent
  - skill-validation
composes:
  - best-practices-arangodb
  - best-practices-python
  - best-practices-skills
  - memory
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Agent Best Practices (NON-NEGOTIABLE)

These rules exist because agents violate them **every session**. Each rule below was
written after the user corrected the same mistake multiple times. Breaking any of
these rules erodes trust and wastes the user's time.

**Load this skill at the start of every session. No exceptions.**

## The Meta-Rule

> When you find an error, **FIX IT**. Do not work around it, do not swallow it,
> do not pretend it didn't happen. The user would rather you spend 10 minutes
> fixing a root cause than 2 minutes bypassing it and creating a landmine.

---

## Rule 1: No Silent Failures — `agent-no-silent-failures`

**Severity: CRITICAL**

NEVER swallow exceptions, return empty results on error, or hide failures behind
fallback paths. If something fails, the user MUST know.

### Bad patterns (BANNED)

```python
# BAD: Silent swallow
try:
    result = client.recall(q=query)
except Exception:
    result = []  # ← User never knows it failed

# BAD: Degraded fallback that hides the real problem
try:
    result = daemon_call("/recall", {"q": query})
except ConnectionError:
    result = bm25_only_fallback(query)  # ← Masks broken daemon

# BAD: Return empty instead of raising
def get_controls(ids):
    try:
        return db.collection("sparta_controls").get_many(ids)
    except Exception:
        return {}  # ← Caller thinks there are no controls

# BAD: except: pass
try:
    important_operation()
except:
    pass
```

### Good patterns (REQUIRED)

```python
# GOOD: Raise with context
try:
    result = client.recall(q=query)
except Exception as exc:
    raise RuntimeError(f"Memory recall failed for '{query}': {exc}") from exc

# GOOD: Log AND raise
try:
    resp = client.post("/recall", json={"q": query})
    resp.raise_for_status()
except httpx.HTTPStatusError as exc:
    logger.error("Daemon /recall returned %d: %s", exc.response.status_code, exc.response.text)
    raise

# GOOD: Specific exception handling with clear action
try:
    result = daemon_call("/recall", {"q": query})
except ConnectionError as exc:
    raise RuntimeError(
        "Memory daemon is down. Start it: systemctl --user start embry-memory"
    ) from exc
```

### Why this matters

Silent failures create **invisible bugs**. The agent reports success, the user moves on,
and hours later discovers the data was never stored, the search never ran, or the
validation never checked anything. The user has corrected this pattern dozens of times.

---

## Rule 2: Fix Errors, Don't Bypass Them — `agent-fix-not-bypass`

**Severity: CRITICAL**

When you encounter an error during your work, **STOP and fix it**. Do not:
- Comment out the broken code and write a workaround
- Add a try/except around it and continue
- Skip the failing step and move to the next one
- Add a `# TODO: fix this later` and proceed
- Change the input to avoid triggering the bug

### Bad patterns (BANNED)

```python
# BAD: Bypassing a broken import
# from graph_memory.lessons.store import store_lesson  # ImportError
# Workaround: inline the storage logic
def store_lesson_inline(doc):
    db.collection("lessons").insert(doc)  # ← Lost all validation

# BAD: Skipping a failing test instead of fixing the code
@pytest.mark.skip(reason="flaky, will fix later")
def test_critical_feature():
    ...

# BAD: Changing input to avoid the bug
# Original: process_all_documents(docs)
# Error: crashes on docs with unicode
process_all_documents([d for d in docs if d.isascii()])  # ← Data loss
```

### Good patterns (REQUIRED)

```python
# GOOD: Diagnose the import error
# ImportError: cannot import 'store_lesson' from 'graph_memory.lessons.store'
# Investigation: function was renamed to 'store_lesson_v2' in commit abc123
# Fix: update the import
from graph_memory.lessons.store import store_lesson_v2 as store_lesson

# GOOD: Fix the flaky test
def test_critical_feature():
    # Was flaky because of race condition in teardown
    # Fix: use fresh DB connection per test
    with fresh_db_connection() as db:
        ...

# GOOD: Fix the unicode bug
def process_document(doc):
    # Was crashing on unicode because of .encode('ascii')
    # Fix: use utf-8
    text = doc.encode('utf-8')
    ...
```

### The STOP-INVESTIGATE-FIX pattern

1. **STOP** — Don't write any more code
2. **INVESTIGATE** — Read the error, find the root cause
3. **FIX** — Fix the actual problem
4. **VERIFY** — Confirm the fix works
5. **RESUME** — Continue your original task

If you genuinely cannot fix it (e.g., requires infrastructure the user needs to set up),
**tell the user explicitly** what's broken and what they need to do. Do NOT silently
work around it.

---

## Rule 3: No Raw AQL / No Direct Imports — `agent-no-raw-aql`

**Severity: CRITICAL**

ALL memory/data access goes through the embry-memory daemon Unix socket. NEVER:

- `from graph_memory import ...` (any submodule)
- `from graph_memory.api import MemoryClient`
- `from graph_memory.cli.query import ...`
- `httpx.post("http://127.0.0.1:8529/_db/memory/_api/cursor", ...)`
- `from arango import ArangoClient`
- Any direct ArangoDB HTTP call

### The ONLY correct pattern

```python
import httpx

transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
client = httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0)

# Recall
resp = client.post("/recall", json={"q": "my question", "limit": 20})

# Learn
resp = client.post("/learn", json={"problem": "...", "solution": "..."})

# Taxonomy
resp = client.post("/taxonomy/coverage", json={"collection": "lessons"})
resp = client.post("/taxonomy/untagged", json={"collection": "lessons", "field": "bridge_attributes"})
resp = client.post("/taxonomy/query", json={"collection": "lessons", "filters": {"scope": "operational"}})
resp = client.post("/taxonomy/tag", json={"collection": "lessons", "key": "abc", "bridge_attributes": ["Precision"]})
resp = client.post("/taxonomy/batch-tag", json={"collection": "lessons", "updates": [...]})

# Bulk key lookup
resp = client.post("/recall/by-keys", json={"collection": "lessons", "keys": ["k1", "k2"]})

# Paginated listing
resp = client.post("/list", json={"collection": "sparta_qra", "limit": 50, "offset": 0})

# Theory of Mind
resp = client.get("/tom/graham")
resp = client.post("/tom/graham/evolve", json={...})

# Analytics
resp = client.post("/analytics/run", json={...})
```

### If the daemon doesn't have an endpoint for what you need

**STOP and tell the user.** Say: "The daemon doesn't have an endpoint for X.
Should I add one to the memory project's FastAPI app?" Do NOT fall back to raw AQL.

### Available daemon endpoints (complete list)

Core: `/recall`, `/learn`, `/recall/by-keys`, `/list`
Taxonomy: `/taxonomy/coverage`, `/taxonomy/sample`, `/taxonomy/tag`, `/taxonomy/batch-tag`, `/taxonomy/untagged`, `/taxonomy/query`
Graph: `/related`, `/residue`, `/add-edge`, `/add-edges`, `/trace`
ToM: `/tom/{user_id}`, `/tom/{user_id}/evolve`, `/tom/{user_id}/update-belief`
Intent: `/clarify`, `/deflect`, `/intent`
Analytics: `/analytics/run`
Drift: `/drift`
Health: `/health`

---

## Rule 4: No Parallel Infrastructure — `agent-no-parallel-infra`

**Severity: HIGH**

Before building ANYTHING new, check if it already exists. The #1 source of
architectural debt is agents creating parallel systems that duplicate existing skills.

### Check BEFORE building

| If you need... | Use this | NOT this |
|----------------|----------|----------|
| Semantic search | `/memory recall` | New FAISS index |
| Text search | `/memory recall` (BM25 built-in) | Python whoosh/tantivy |
| Tag extraction | `/taxonomy` | New bridge extractor |
| LLM completion | `/scillm` proxy (port 4001) | `openai.Client()` directly |
| Prompt iteration | `/prompt-lab` | Hand-written prompts in code |
| Entity extraction | `/extract-entities` | New regex classifier |
| Web fetching | `/fetcher` | `requests.get()` with custom retry |
| PDF extraction | `/extract-pdf` or `/extractor` | PyMuPDF inline |
| Evidence cases | `/create-evidence-case` | Bespoke scoring script |
| Formal proofs | `/lean4-prove` | Raw curl to port 8604 |
| Embeddings | Embedding service (port 8602) | Loading model in-process |
| Code review | `/review-code` | Manual diff reading |

### The anti-silo test

Before writing ANY new function, ask:
1. Does a daemon endpoint already do this?
2. Does a skill's `run.sh` already do this?
3. Does a Python module in the project already do this?

If yes to any → **use it**. If no → ask the user before building it.

---

## Rule 5: No Swallowed HTTP Errors — `agent-no-swallowed-http`

**Severity: HIGH**

When calling any HTTP endpoint, ALWAYS check the response status. NEVER assume success.

```python
# BAD: Assumes success
resp = client.post("/recall", json={"q": query})
data = resp.json()  # ← Crashes with decode error on 500

# BAD: Checks but ignores
resp = client.post("/recall", json={"q": query})
if resp.status_code != 200:
    return []  # ← Silent failure (Rule 1 violation too)

# GOOD: Check and raise
resp = client.post("/recall", json={"q": query})
if resp.status_code != 200:
    raise RuntimeError(f"Daemon /recall failed ({resp.status_code}): {resp.text}")
data = resp.json()

# ALSO GOOD: Use raise_for_status()
resp = client.post("/recall", json={"q": query})
resp.raise_for_status()
data = resp.json()
```

---

## Rule 6: No Reimplementing What Exists — `agent-no-reimplementation`

**Severity: HIGH**

The codebase has solutions for common problems. Do NOT reimplement them.

| Already exists | Location | Do NOT reimplement |
|----------------|----------|--------------------|
| Snowball stemming | ArangoDB `text_en` analyzer | Python stemming code |
| Stop word removal | ArangoDB `text_en` analyzer | Python stopword lists |
| BM25 scoring | ArangoDB `BM25()` function | Python TF-IDF |
| Cosine similarity | ArangoDB `COSINE_SIMILARITY()` | Python numpy dot product |
| Fuzzy matching | ArangoDB `LEVENSHTEIN_DISTANCE()` | Python editdistance |
| Entity classification | `source_framework` field on `sparta_controls` | Regex-based framework guessing |
| Bridge extraction | `/taxonomy` skill | New keyword matching |
| Domain terms | `domain_terms` collection | Hardcoded term lists |
| Control lookup | `sparta_controls` collection | Hardcoded control maps |
| Deduplication | `problem_hash` field + UPSERT | Python-side dedup |

---

## Rule 7: Memory First — `agent-memory-first`

**Severity: HIGH**

Before scanning the codebase, before reading files, before grepping:

```bash
/memory recall --q "description of the problem"
```

If memory has the answer → use it. Do NOT scan the codebase redundantly.
If memory doesn't have it → solve it, then `/memory learn` the solution.

This is not optional. This is THE workflow.

---

## Rule 8: Transparency in Verdicts — `agent-transparency`

**Severity: HIGH**

Every verdict, assessment, or decision MUST show **WHY**, not just **WHAT**.

```markdown
# BAD: Opaque verdict
Result: SATISFIED

# GOOD: Transparent verdict
Result: SATISFIED
Why: 3/3 entities resolved (SV-AC-2 → 14 QRAs, CWE-89 → 8 QRAs, SV-CF-1 → 6 QRAs)
Grounding: All entities confirmed in sparta_controls (8,979 total)
Technique bridge: SV-AC-2 and SV-CF-1 share technique T1548 (MITRE ATT&CK)
What could be wrong: If the question assumes a relationship between AC-2 and CF-1
  that doesn't exist, the technique bridge would be coincidental
```

This applies to:
- Evidence case verdicts
- QRA quality assessments
- Entity extraction results (show RESOLVED vs UNRESOLVED)
- Any pass/fail gate

---

## Rule 9: No Simulated Agents / Evidence-Gated Decisions — `agent-no-simulated-review`

**Severity: CRITICAL**

> Deeper companion: [`references/NO_SIMULATED_REVIEW.md`](references/NO_SIMULATED_REVIEW.md) (synced from upstream `grahama1970/agent-skills` on 2026-05-13).

Agents must not create authoritative-looking review, second-pass, validation, or
closure results from heuristics or partial checks.

A heuristic may create a hint. It may not create a confirmed finding, correction,
core bug, or closure state.

Core principle:

```text
If no model or human reviewed it, do not call it a review.
If no audit proved it, do not call it confirmed.
If no deterministic gate passed, do not call it closed.
```

### Bad patterns (BANNED)

```python
# BAD: Heuristic becomes correction label
if bbox_area > 0.45:
    risk_reasons.append("bbox_over_broad")

# BAD: Label copy masquerades as review
if "bbox_over_broad" in risk_reasons:
    result["decision"] = "emit_correction"
    result["confidence"] = "high"

# BAD: Misleading name — no LLM or human is actually reviewing
python run_second_pass_reviews.py

# BAD: Report says closed without deterministic gate
status = "core_fixed"  # no core patch, no fixture, no rerun
```

### Good patterns (REQUIRED)

```python
# GOOD: Heuristic is only a hint
if bbox_area > 0.45:
    risk_reasons.append("bbox_suspect_large_area")

# GOOD: Audit decides strong label
audit = bbox_audit_for_element(element)
if audit.status == "confirmed":
    risk_reasons.append("bbox_over_broad")
elif audit.status == "insufficient_evidence":
    risk_reasons.append("bbox_audit_insufficient")

# GOOD: Honest process name
python apply_deterministic_candidate_classification.py

# GOOD: Explicit adjudicator identity
result["adjudicator_kind"] = "deterministic_classifier"  # or llm / human / verifier
result["confidence"] = "deterministic"
```

### Required vocabulary discipline

Use these meanings consistently:

- `*_suspect_*` = weak heuristic hint
- `*_confirmed_*` = audit-backed finding
- `*_insufficient_evidence` = unresolved, not accepted
- `*_pending` = unresolved workflow state
- `*_fixed` / `closed` = deterministic gate passed

### Replay artifact requirement

Every model, human, or deterministic review result must be replayable.

Required artifacts:

```text
system_prompt.txt              # if LLM
user_prompt.txt                # if LLM
input_payload.json
selected_config_or_preset.json
source_artifacts/              # images, crops, diffs, overlays, logs
model_response.json            # if LLM
deterministic_response.json    # if deterministic classifier
validated_decision.json
validation_result.json
```

No replay bundle, no accepted review result.

### Closure authority hierarchy

Project agents may propose.
LLMs may adjudicate ambiguous cases.
Humans may resolve policy/semantic ambiguity.
Only deterministic gates may close.

Closure requires:

1. source evidence attached or reproducible
2. mechanism named honestly
3. result replayable
4. weak hints separated from confirmed findings
5. deterministic validation passed
6. unresolved cases remain explicitly pending

### Canary before batch

Before running a new agent/review loop on many cases, prove the contract on canaries:

- one expected positive case
- one expected negative case
- one ambiguous/insufficient-evidence case
- one expected failure case
- one regression fixture

Do not batch until the canaries pass.

---

## Rule 10: Receipts Are Not the Work — `agent-no-receipt-loop`

**Severity: CRITICAL**

Review bundles, WebGPT responses, dashboards, status pages, reports, screenshots,
and validation manifests are **receipts**. They prove or explain work. They are
not the success metric unless the user's requested deliverable is explicitly the
artifact itself.

When the real task is containment, prevention, repair, migration, deployment,
or data integrity, do not spend cycles polishing the receipt while the underlying
writer, bug, corrupted data, or failing gate remains active.

### Bad patterns (BANNED)

```text
# BAD: Better bundle, no containment progress
WebGPT asked for a better proof bundle, so the agent rebuilds the bundle three
times while the mutation-capable monitor process is still respawning.

# BAD: Dashboard/report churn instead of fixing the source
The monitor says PASS incorrectly, so the agent edits the dashboard copy instead
of patching the monitor checks or stopping the writer.

# BAD: Review loop as success metric
"WebGPT accepted the bundle" is reported as done even though no prevention patch
landed and no delayed no-respawn check ran.
```

### Good patterns (REQUIRED)

```text
# GOOD: Name the real success metric
Success is: no mutation-capable process now and after one full interval;
writer path disabled by default; endpoint verified not to spawn it.

# GOOD: Use the bundle only as proof
Patch the writer path, restart the service, run immediate and delayed checks,
then update the review bundle to document those facts.

# GOOD: Stop when the receipt exposes real work
If a reviewer finds "containment proof incomplete", do not just add prose.
Run the containment check. If it fails, identify and patch the respawn source.
```

### Required operating pattern

For any operational task, write down the real success metric before creating or
refreshing a review artifact:

```text
Real success metric:
- What process, writer, endpoint, data state, or user-visible behavior must be true?
- What deterministic proof shows it is true?
- What delayed/retry proof is needed to show it stays true?
- What remains explicitly blocked or pending?
```

Only after that may the agent package a review bundle, status report, or visual
artifact. The receipt must point to the proof; it must not replace the proof.

### SPARTA containment example

```text
Wrong goal:
- create a better WebGPT review bundle

Right goal:
- prove no monitor_sparta supervisor, health --fix, observe-loop, or coverage
  endpoint can spawn mutation-capable work by default
- verify immediately and after one full 300-second interval
- patch fail-closed prevention paths first
- only then package the review bundle as evidence
```

---

## Rule 11: Monitor Lanes Must Close the Loop — `agent-monitor-lane-closure`

**Severity: CRITICAL**

Monitor skills are not passive reports. A `monitor-*` skill has two jobs:

1. **Monitor truth:** observe, classify, report, and fail closed.
2. **Repair orchestration:** decide what is safe, run bounded repairs, verify
   positive evidence, and continue until healthy or blocked.

A monitor is not complete because it detected a problem, wrote a manifest, or
reported a queue. Every failing dimension must have exactly one lane state and
exactly one next action.

### Required lane states

| Lane state | Meaning | Required behavior |
|------------|---------|-------------------|
| `healthy` | Positive evidence passes | Continue scheduled observation |
| `auto_repairable` | Deterministic, bounded, reversible, and backed by an existing approved skill/service | Run repair automatically in bounded batches, verify after each batch, continue until empty or failed |
| `review_gated` | Mutation, semantic, policy, schema, source, or high-cost risk | Write the manifest/approval artifact and surface the exact approval request |
| `blocked` | Missing dependency, service, source, credential, or endpoint | Record the blocker, exact retry/check command, and retry schedule |
| `failed_repair` | Auto repair was attempted and failed | Stop that lane, preserve logs/state, classify the failure, and escalate with resume command |
| `waived` | Human-approved non-action | Store approval source, timestamp, scope, and expiry/review date |

### Banned monitor anti-patterns

```text
# BAD: Monitor reports failure, writes manifest, then idles forever.
qra_coverage_per_control: fail
manifest: /tmp/qra_gap_manifest.json
next action: none

# BAD: Running is treated as progress.
monitor-sparta.service is active, therefore QRA backfill is progressing.

# BAD: Old backlog bucket hides a newer failing health dimension.
create_qras_remaining_calls=0, therefore QRA coverage is complete, even though
qra_coverage_per_control still fails.

# BAD: Review-gated and auto-repairable work are collapsed together.
All QRA gaps are review-gated, so no safe direct/native text-backed QRA backfill runs.
```

### Required monitor behavior

```text
# GOOD: Every failing dimension has state + action.
dimension: qra_coverage_per_control
state: auto_repairable
reason: source-backed direct/native controls have real descriptions and
        deterministic mode selection
next action: run reviewed /create-qras manifest in 100-control batch
proof after action: controls covered, QRAs stored, skipped/failed jobs,
                    no inline embeddings, gap delta

# GOOD: Risky lane is review-gated, not ignored.
dimension: relationship_comparison_candidates
state: review_gated
reason: control-to-control relationship claims require accepted
        /create-evidence-case responses
next action: write approval manifest with evidence-case status per candidate
```

### Auto-repair criteria

A monitor lane may auto-repair only when all are true:

- the source data needed for repair already exists and is not stub/padded;
- the repair uses an existing approved skill or service;
- the action is bounded by batch size or item limit;
- the action is idempotent or has deterministic keys;
- rollback/write-ahead or replay artifacts exist when mutation occurs;
- post-run verification can prove positive state change;
- failures stop the lane instead of being swallowed;
- the lane cannot synthesize unsupported source records, descriptions,
  relationships, schemas, or policy decisions.

If any criterion is false, the lane is `review_gated` or `blocked`, not
`auto_repairable`.

### Required monitor loop invariant

For every failing dimension:

```text
dimension
current_count / severity
lane_state
why this state is safe/correct
next_action
owner skill/service
retry/check cadence
proof required to transition state
artifact paths
```

The monitor must keep acting on `auto_repairable` lanes until they become
`healthy`, `failed_repair`, or `blocked`. Writing a manifest is only a receipt;
it is not the work unless the lane is explicitly `review_gated`.

### SPARTA example

```text
qra_coverage_per_control:
  direct/native text-backed gaps -> auto_repairable
  relationship comparison candidates -> review_gated
  terminal disposition decisions -> review_gated
  missing source text -> review_gated or blocked
  inline embedding cleanup -> review_gated unless rollback-backed and explicitly approved

Correct behavior:
  monitor-sparta classifies direct/native QRA gaps as gated_runnable,
  launches bounded reviewed /create-qras batches, verifies each batch, and
  continues until the direct gap is empty or a real blocker occurs.

Incorrect behavior:
  monitor-sparta reports 4,614 missing QRAs forever while no create-qras
  process is running and no lane is marked blocked or review-gated.
```

---

See [RULES_EXTENDED.md](references/RULES_EXTENDED.md) for additional extended rules covering prompt usage, scillm, daemon endpoints, storage, error handling, response shapes, mandatory skill chains, memory reading, and service-first architecture.

---

# BAD: Inline prompt
resp = scillm_call("You are a helpful assistant. Classify this text...")

# GOOD: Prompt from /prompt-lab with version tracking
resp = scillm_call(load_prompt("classify_text_v3"))
```

---

# BAD
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# GOOD
import httpx
resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={"Authorization": "Bearer sk-dev-proxy-123"},
    json={"model": "text", "messages": [...]}
)
```

The proxy handles cascading, retries, budget tracking, and JSON validation.

---

# BAD: Over-engineered — masks every possible bug
try:
    step1()
    step2()
    step3()
    step4()
except Exception as e:
    logger.warning(f"Something failed: {e}")
    return default_result

# GOOD: Let unexpected errors propagate
step1()
step2()
try:
    step3()  # This one has a known failure mode we can handle
except ConnectionError as exc:
    raise RuntimeError("Database unreachable for step 3") from exc
step4()
```

---

# BAD: Assumes shape
data = resp.json()
items = data["results"]  # ← KeyError if API returned error JSON

# GOOD: Validate shape
data = resp.json()
if "results" not in data:
    raise ValueError(f"Unexpected response shape: {list(data.keys())}")
items = data["results"]
```

---

## Quick Reference: The 5-Second Checklist

Before submitting ANY code, check:

1. **Did I swallow any exceptions?** → If yes, add proper error handling
2. **Did I bypass an error instead of fixing it?** → If yes, go fix the root cause
3. **Did I import graph_memory directly?** → If yes, use the daemon socket
4. **Did I build something that a skill already does?** → If yes, use the skill
5. **Does my output show WHY, not just WHAT?** → If no, add reasoning
6. **Did I call something a review without a reviewer/model?** → Rename it or wire the reviewer
7. **Did a heuristic emit a confirmed label?** → Change it to a suspect hint and add an audit
8. **Did I claim fixed/closed without a deterministic gate?** → Downgrade to pending
9. **Can the decision be replayed from artifacts?** → If no, generate replay artifacts
10. **Did I batch before a canary passed?** → Stop and prove one representative case first
11. **Am I polishing a receipt instead of fixing the real blocker?** → Define the real success metric, fix/prove that first, then package evidence
12. **Is a monitor reporting a failure without lane state + next action?** → Classify it as `auto_repairable`, `review_gated`, `blocked`, `failed_repair`, or `waived`, then run or surface the required action

---

## Enforcement

These rules are enforced by:
- **PostToolUse hooks** in `~/.claude/settings.json` (block specific patterns)
- **Code review** via `/review-code`
- **Session-start memory** loading (this skill)
- **User correction** (if you get corrected for the same thing twice, it goes in this file)

# BAD: subprocess to a skill with an HTTP service
subprocess.run(["taxonomy/run.sh", "extract", "--text", text])
subprocess.run(["embedding/run.sh", "--text", text])
subprocess.run(["doc2qra/run.sh", "--input", file])

# GOOD: HTTP to the service
httpx.post("http://localhost:8601/taxonomy/tag", json={"text": text})
httpx.post("http://localhost:8602/embed/batch", json={"texts": texts})
batch_sync(requests, caller="my-skill")  # chutes-call client
```

### `/skills-ci` enforcement

`skills-ci` scans for `subprocess.service_bypass` violations — subprocess calls
to skills that have HTTP services. This catches the pattern at static analysis time.

### Why this rule exists

Graham has corrected this pattern 3+ times. The learn-datalake fork bomb incident
(79 extractors, 141 GB RSS) was a direct consequence of subprocess spawning without
service-level concurrency control.

---
