---
name: best-practices-agent
description: >
  Non-negotiable agent behavior rules. Covers: no silent failures, no error bypassing,
  no raw AQL, no direct imports, no parallel infrastructure, no swallowed exceptions,
  use existing skills, fix errors don't dodge them, transparency in verdicts.
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

See [RULES_EXTENDED.md](references/RULES_EXTENDED.md) for rules 9-17 covering prompt usage, scillm, daemon endpoints, storage, error handling, response shapes, mandatory skill chains, memory reading, and service-first architecture.

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
