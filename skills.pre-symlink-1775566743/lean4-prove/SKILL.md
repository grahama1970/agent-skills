---
name: lean4-prove
description: >
  Retrieval-augmented Lean4 proof generation with self-improving lab.
  Queries 94k+ exemplars from DeepSeek-Prover V1+V2, uses hybrid search (BM25 + semantic + graph),
  generates via Claude, compiles via lean-interact (20 parallel silos), retries on failure.
  Lab mode: HF dataset ingestion, parallel compilation, English↔Lean4 autoformalization,
  GRPO training with compiler rewards, convergence loop, and adversarial benchmarking.
allowed-tools: Bash, Read, Docker
triggers:
  - prove this
  - lean4 proof
  - generate proof
  - verify lean4
  - lean4-prove
  - formalize this requirement
  - lab ingest
  - lab compile
  - lab formalize
  - lab converge
  - lab benchmark
  - lab report
metadata:
  short-description: Retrieval-augmented Lean4 proof generation with self-improving lab

provides:
  - lean4-prove
  - lean4-lab
composes:
  - memory
  - code-runner
  - scillm
  - edge-verifier
  - embedding
  - task-monitor
  - ops-runpod
  - create-gpt
  - episodic-archiver
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# lean4-prove

Retrieval-augmented Lean4 proof generation for engineering requirements. Uses 94,000+ proven theorems from DeepSeek-Prover V1+V2 to guide proof synthesis via hybrid search (BM25 + semantic + graph traversal).

## Architecture (updated 2026-03-29)

```
Requirement + Tactics + Persona
        │
        ▼
┌───────────────────────────┐
│ 1. RECALL similar proofs  │  ← Hybrid search on ArangoDB
│    from 94k+ exemplars    │     (BM25 + semantic + graph)
└───────────────────────────┘
        │
        ▼
┌───────────────────────────┐
│ 2. BUILD support pack     │
│    - Validated imports    │
│    - Tactic patterns      │
│    - Similar proofs       │
└───────────────────────────┘
        │
        ▼
┌───────────────────────────┐
│ 3. /code-runner session   │  ← LLM via /scillm (httpx)
│    propose → compile →    │     DoD: lean4 HTTP compile
│    fix → retry (5 rounds) │     Escalation: text → claude
└───────────────────────────┘
        │
        ▼
┌───────────────────────────┐
│ 4. COMPILE via HTTP svc   │  ← lean4-prove-service:8604
│    lean-interact backend  │     (lean4 v4.28.0 + Mathlib)
└───────────────────────────┘
        │
   ┌────┴────┐
   │         │
 Success   Failure
   │         │
   ▼         ▼
 Return   /code-runner retries
          with error feedback
          (up to max_rounds)
```

### Key Changes (2026-03-29)
- **LLM**: Uses `/scillm` via httpx (NOT `claude -p` subprocess)
- **Retry loop**: Delegated to `/code-runner` (propose→compile→fix→retry)
- **Compile**: lean4-prove-service HTTP at :8604 (NOT docker exec)
- **Model**: `text` (scillm cascade) by default, not `opus`
- **Toolchain**: Pinned to Lean v4.28.0 (Mathlib not yet released for v4.29.0)

## Why Retrieval-Augmented?

1. **Determinism** - Exact provenance: "used these 3 proofs as templates"
2. **Version alignment** - Exemplars use imports that actually work
3. **Fewer hallucinations** - Constrained to lemmas that exist
4. **Tactic idioms** - Transfers working `simp` sets and proof patterns

## Usage

```bash
# Basic proof
./run.sh --requirement "Prove n + 0 = n"

# With tactics preference
./run.sh -r "Prove commutativity of addition" -t "simp,ring,omega"

# With persona context
./run.sh -r "Prove message integrity" -p "cryptographer"

# Via stdin (JSON)
echo '{"requirement": "Prove n + 0 = n", "tactics": ["rfl"]}' | ./run.sh

# Custom settings (uses /scillm text cascade by default)
./run.sh -r "Prove theorem" --candidates 3 --retries 5 --model text
```

## Output

```json
{
  "success": true,
  "code": "import Mathlib\n\ntheorem list_append_length (xs ys : List α) :\n    (xs ++ ys).length = xs.length + ys.length := by\n  induction xs with\n  | nil => simp\n  | cons x xs ih => simp [List.cons_append, ih]",
  "attempts": 1,
  "candidate": 0,
  "errors": null,
  "retrieval": {
    "retrieved": 5,
    "tactics_added": ["simp", "aesop", "norm_num", "intro"],
    "imports_count": 3
  }
}
```

On failure:

```json
{
  "success": false,
  "code": null,
  "attempts": 9,
  "errors": [
    "Candidate 0 attempt 1: unknown identifier 'natAdd'",
    "Candidate 1 attempt 1: type mismatch..."
  ],
  "retrieval": {
    "retrieved": 5,
    "tactics_added": ["simp", "exact"],
    "imports_count": 3
  }
}
```

## Parameters

| Parameter           | Default   | Description                           |
| ------------------- | --------- | ------------------------------------- |
| `--requirement, -r` | (required)| Theorem to prove                      |
| `--tactics, -t`     | none      | Comma-separated preferred tactics     |
| `--persona, -p`     | none      | Persona context for generation        |
| `--candidates, -n`  | 3         | Number of /code-runner sessions       |
| `--retries`         | 3         | Max rounds per /code-runner session   |
| `--model`           | text      | scillm model (text, gemini, deepseek) |
| `--container`       | lean_runner | Docker container (legacy, ignored)  |
| `--timeout`         | 120       | Compilation timeout (seconds)         |

## Environment Variables

```bash
# Proof generation
LEAN4_TIMEOUT=120                # Compile timeout (seconds)
LEAN4_MAX_RETRIES=3              # Retries per /code-runner session
LEAN4_CANDIDATES=3               # Number of /code-runner sessions
LEAN4_PROVE_MODEL=text           # scillm model (text cascade by default)

# LLM backend (uses /scillm httpx, NOT claude -p)
SCILLM_API_BASE=http://localhost:4001  # scillm Docker proxy
SCILLM_PROXY_KEY=sk-dev-proxy-123      # scillm auth key

# Compilation backend (HTTP service preferred)
LEAN4_SERVICE_URL=http://127.0.0.1:8604  # lean4-prove-service FastAPI

# Retrieval (requires ArangoDB with ingested dataset)
LEAN4_RETRIEVAL=1                # Enable/disable retrieval (default: 1)
LEAN4_RETRIEVAL_K=5              # Number of exemplars to retrieve
ARANGO_URL=http://127.0.0.1:8529 # ArangoDB connection
ARANGO_DB=memory                 # Database name (same as memory skill)
```

## Dataset Setup

The skill uses 94,000+ theorems from DeepSeek-Prover V1+V2 for retrieval:
- **V1**: 27,503 theorems (`status: "proven"`)
- **V2**: 66,708 theorems (`status: "ok"` for 11,689 proven + others)

One-time ingest:

```bash
# Ingest full dataset (~5 min)
./ingest.sh

# Or limit for testing
./ingest.sh --limit 1000
```

This populates the `lean_theorems` collection in ArangoDB with:
- `formal_statement` - The theorem statement
- `formal_proof` - Working proof code
- `header` - Validated imports (Mathlib, Aesop, etc.)
- `tactics` - Extracted tactic names
- `source` - "deepseek-prover-v1" or "deepseek-prover-v2"
- `status` - "proven" (V1) or "ok"/"failed"/etc. (V2)

## LLM Backend

Uses `/scillm` Docker proxy via httpx (NOT `claude -p` subprocess).
The scillm text cascade routes to DeepSeek-V3 by default.

## HTTP API (lean4-prove-service at :8604)

The Docker container exposes these endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Worker count + timeout |
| `/compile` | POST | Compile Lean4 code (no LLM) |
| `/compile-batch` | POST | Compile multiple proofs in parallel |
| `/step-verify` | POST | Per-tactic incremental elaboration |
| `/prove` | POST | **Full pipeline**: generate via scillm → compile → retry |

### POST /prove (composition endpoint)

This is what `/create-evidence-case` and other skills call via httpx. No subprocess.

```json
POST http://127.0.0.1:8604/prove
{
  "requirement": "Prove that for all natural numbers n, n + 0 = n",
  "tactics": ["rfl", "simp"],
  "model": "text",
  "max_retries": 3,
  "timeout": 60
}
```

Response:
```json
{
  "success": true,
  "code": "theorem test (n : Nat) : n + 0 = n := by simp",
  "attempts": 1,
  "errors": null
}
```

The container calls `/scillm` (via `host.docker.internal:4001`) for LLM generation
and compiles locally with lean-interact (20-worker pool, Mathlib cached).

## Compilation Backend

The lean4-prove-service container uses lean-interact with a 20-worker LeanServerPool.
Mathlib is cached in Docker volumes (`lean4-lake-cache`, `lean4-mathlib-cache`).
Toolchain pinned to **v4.28.0** (Mathlib not yet released for v4.29.0).

## Requirements

1. **lean4-prove-service** Docker container running (lean-interact + Mathlib cached)
2. **scillm** Docker proxy running at :4001 (reachable from container via `host.docker.internal`)
3. **/code-runner** skill available (for CLI invocation; not used by HTTP API)
4. **ArangoDB** running locally (for retrieval - optional but recommended)
5. **Dataset ingested** via `./ingest.sh` (one-time setup)

## Tactics

Common Lean4/Mathlib tactics to suggest:

| Tactic      | Use For                 |
| ----------- | ----------------------- |
| `rfl`       | Reflexivity proofs      |
| `simp`      | Simplification          |
| `ring`      | Ring arithmetic         |
| `omega`     | Linear arithmetic       |
| `decide`    | Decidable propositions  |
| `exact`     | Exact term construction |
| `apply`     | Apply lemmas            |
| `induction` | Inductive proofs        |

## Examples

### Engineering: List operations

```bash
./run.sh -r "Prove length(xs ++ ys) = length(xs) + length(ys)" -t "simp,induction"
```

### Engineering: State machine property

```bash
./run.sh -r "When mux_enable is false, output shall equal default_value" \
  -p "embedded systems engineer" -t "simp,cases,decide"
```

### Engineering: Protocol correctness

```bash
./run.sh -r "Prove message append preserves checksum: checksum(msg ++ data) = update(checksum(msg), data)" \
  -t "simp,induction,ring"
```

### Cryptography

```bash
./run.sh -r "Prove that XOR is self-inverse: a ⊕ a = 0" -p "cryptographer" -t "simp,decide"
```

### Complex theorem

```bash
./run.sh -r "Prove the sum of first n natural numbers equals n*(n+1)/2" \
  -t "induction,simp,ring" \
  --candidates 5 \
  --retries 5
```

## Difference from lean4-verify

| Skill          | Purpose                                                          |
| -------------- | ---------------------------------------------------------------- |
| `lean4-verify` | Compile-only. Takes Lean4 code, returns pass/fail                |
| `lean4-prove`  | Full pipeline. Takes requirement, generates + compiles + retries |

Use `lean4-verify` when you already have Lean4 code to check.
Use `lean4-prove` when you need to generate the proof from a requirement.

## Advanced: Memory Integration

The skill integrates with the memory project for hybrid retrieval (BM25 + semantic + graph traversal):

```bash
# One-time setup: embed theorems and create edges
ARANGO_PASS=yourpass ARANGO_DB=memory python integrate_memory.py
```

This creates:
- **Embeddings**: 39k+ theorem embeddings in `lesson_embeddings` for semantic search
- **Tactic edges**: 10k+ edges between theorems sharing primary tactics
- **Similarity edges**: Edges between semantically similar theorems (cosine > 0.7)

This enables:
- **Semantic search**: Find theorems by meaning, not just keywords
- **Multi-hop traversal**: "What proofs use similar tactics?"
- **Impact analysis**: "If I change lemma X, what breaks?"

### Proof Jobs Queue (Control Extraction Pipeline)

The control extraction pipeline (s12_framework_mapper) queues `proof_jobs` in ArangoDB for lean4-prove to consume. Each job represents a requirement→control pair where the requirement claims to implement a framework control (NIST, CWE, SPARTA, etc.).

**Queue**: `proof_jobs` collection (40,210 pending jobs as of 2026-02-25)

```json
{
  "source_type": "requirement_control",
  "requirement_chunk": "datalake_chunks/<key>",
  "control_id": "AC-2",
  "control_ref": "sparta_controls/<key>",
  "framework": "NIST",
  "requirement_text": "The system SHALL implement automated account management...",
  "status": "pending",
  "priority": 1,
  "attempts": 0
}
```

**On success**: Creates `proof_requirement_edges` and updates `requirement_control_edges.lean4_status` from "pending" to "proved".

**Priority**: NIST and SPARTA jobs are priority 1; others priority 2.

**Lemma Graph Structure**:
```
sparta_controls/AC-2 (SPEC)
    ↑ chunk_control_edges (EVIDENCE — many)
    ↑ requirement_control_edges (CLAIM — subset with lean4_status)
    ↑ proof_requirement_edges (PROOF — when lean4 succeeds)
```

### Multi-Predicate Support

The QRA consistency verifier supports 5 relationship predicates via `PREDICATE_REGISTRY`:

| Predicate | Lean4 Type | Parameter | Axiom |
|-----------|-----------|-----------|-------|
| `subsumes` | `Control -> Control -> Prop` | None | Transitivity |
| `countered_by` | `Control -> Control -> Prop` | `bool` (enabled) | Negation: enabled → ¬ threat_active |
| `mitigated_by` | `Control -> Control -> Prop` | `float` (coverage) | Threshold: coverage_met → risk_reduced |
| `exploits` | `Control -> Control -> Prop` | `bool` (vulnerable) | Propagation: vulnerable → compromised |
| `maps_to` | `Control -> Control -> Prop` | None | Symmetry |

Edge types from ArangoDB are normalized (`"maps-to"` → `maps_to`) and matched to the correct predicate automatically.

### Typed Parameters

Controls can have typed parameters for what-if analysis:

- **`bool`**: Toggle (enabled/disabled, vulnerable/not) — emits `Prop` axioms
- **`float`**: Slider with bounds (coverage %, confidence score) — emits coverage_met/risk_reduced propositions
- **`enum`**: Dropdown (NOMINAL/DEGRADED/CRITICAL) — emits `inductive ControlStatus`

Parameters are modeled via the `ControlParameter` dataclass in `qra_models.py`.

### What-If Queries

Identify which theorem chains break when a control parameter changes:

```bash
# Dry-run: generate Lean4 without compiling
python qra_consistency.py what-if --control REC-0001 --param enabled --value false --dry-run

# Full compilation
python qra_consistency.py what-if --control REC-0001 --param enabled --value false

# JSON output for inspector panel consumption
python qra_consistency.py what-if --control REC-0001 --param enabled --value false --dry-run --output-format json
```

JSON output:
```json
{
  "control": "REC-0001",
  "parameter": "enabled",
  "new_value": false,
  "affected_chains": [
    {
      "chain": "REC-0001 -> T1595 -> SC-7",
      "predicate": "countered_by",
      "status": "BROKEN"
    }
  ],
  "summary": { "total": 4, "broken": 2, "held": 2 }
}
```

The UX Lab inspector panel composes with this command for cascade propagation analysis.

### Lemma Dependency Graph

Impact analysis via what-if queries and lemma dependency tracking:

```
Query: "What's affected if REC-0001 is disabled?"

Answer (via what-if):
  REC-0001 (enabled=false)
    └── countered_by T1595 (BROKEN — counter-control disabled)
          └── mitigated_by SC-7 (BROKEN — upstream broke)
```

### Engineering Use Cases

1. **Ambiguity detection**: Formalization fails → requirement is vague
2. **Completeness check**: "Are all state transitions covered?"
3. **Regression impact**: "Change to X affects theorems Y, Z" (via what-if)
4. **Cross-reference**: "Which requirements share this lemma?"
5. **Cascade analysis**: "If I disable this control, what chains break?" (via what-if)

## Common Mistakes

### WRONG: `claude -p` subprocess for LLM calls
```bash
echo "Prove n+0=n" | claude -p  # old approach, uses subprocess
```
### RIGHT: LLM calls go through /scillm via httpx
```python
./run.sh -r "Prove n + 0 = n" --model text  # uses scillm cascade
```
### WRONG: Running proofs without lean4-prove-service
```bash
./run.sh -r "Prove theorem"  # fails if :8604 service is not running
```
### RIGHT: Verify the compilation service is healthy first
```bash
curl -s http://127.0.0.1:8604/health  # check worker count
./run.sh -r "Prove theorem"
```
### WRONG: Lean v4.29.0 toolchain (Mathlib not released for it)
```
leanpkg.toml: lean = "leanprover/lean4:v4.29.0"
```
### RIGHT: Pin to v4.28.0 (current Mathlib-compatible version)
```
./run.sh -r "Prove theorem"  # uses container's pinned toolchain
```
