# lean4-prove Walkthrough (2026-03-29)

## One Sentence

`POST http://127.0.0.1:8604/prove` — send a requirement, get back compiled Lean4 code. No subprocess, no CLI, no Docker exec. One httpx call.

## Architecture

```
Any skill (e.g. /create-evidence-case)
    │
    │  httpx POST :8604/prove
    │  {"requirement": "Prove n + 0 = n"}
    ▼
┌─────────────────────────────────────────┐
│  lean4-prove-service (Docker, host net) │
│                                         │
│  1. /scillm (127.0.0.1:4001)           │
│     → LLM generates Lean4 code         │
│                                         │
│  2. lean-interact (20-worker pool)      │
│     → Compiles locally, Mathlib cached  │
│                                         │
│  3. If fail → error feedback to LLM    │
│     → Retry (up to max_retries)         │
│                                         │
│  4. Return {success, code, attempts}    │
└─────────────────────────────────────────┘
```

Everything happens inside the container. The caller makes one HTTP call and gets back the result. No subprocess nesting, no shell scripts, no Docker exec.

## Endpoints

### GET /health

Check before calling `/prove`. If `prove_available: false`, skip the lean4 gate.

```bash
curl -s http://127.0.0.1:8604/health | python3 -m json.tool
```

```json
{
  "ok": true,
  "workers": 4,
  "timeout": 60.0,
  "scillm_reachable": true,
  "prove_available": true,
  "stats": {
    "proofs_attempted": 12,
    "proofs_succeeded": 10,
    "success_rate": 0.83,
    "compiles_total": 45,
    "avg_compile_ms": 1250.3,
    "last_proof_at": "2026-03-29T17:51:52Z"
  }
}
```

### POST /prove (full pipeline)

Generate + compile + retry. This is what `/create-evidence-case` calls.

```bash
curl -s http://127.0.0.1:8604/prove \
  -H "Content-Type: application/json" \
  -d '{"requirement": "Prove that 1 + 1 = 2", "max_retries": 3}'
```

```json
{
  "success": true,
  "code": "theorem one_plus_one_eq_two : 1 + 1 = 2 := rfl",
  "attempts": 1,
  "errors": null
}
```

**Parameters:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `requirement` | string | (required) | Theorem or requirement to prove |
| `model` | string | "text" | scillm model for generation |
| `max_retries` | int | 3 | Max compile→fix rounds per proof mode |
| `timeout` | float | 60.0 | Compile timeout per attempt (seconds) |
| `proof_modes` | string[] | all 5 defaults | Which proof modes to race concurrently |

**Proof Modes** (fundamentally different approaches — most will fail, first compile wins):

| Mode | Approach | Best For |
|------|----------|----------|
| `tactic` | Goal-transforming tactics (simp, ring, omega) | Algebraic, arithmetic |
| `term` | Direct proof term construction (rfl, ⟨a,b⟩) | Simple propositions |
| `automation` | Proof search (aesop, exact?, apply?) | General theorems |
| `decision` | Decision procedures (native_decide, decide) | Decidable/finite props |
| `requirements` | Engineering formalization (structures, mitigates, covers) | SPARTA domain proofs |
| `induction` | Induction/cases for recursive structures | Nat, List, Tree |
| `structured` | calc chains, have steps, named intermediates | Complex multi-step |

Default race: `["tactic", "term", "automation", "decision", "requirements"]`

### POST /prove with concurrent strategies (race 3, first wins)

```bash
curl -s http://127.0.0.1:8604/prove \
  -H "Content-Type: application/json" \
  -d '{
    "requirement": "Prove that for all n, n + 0 = n",
    "strategies": [
      {"model": "text", "tactics": ["rfl", "simp"]},
      {"model": "text", "tactics": ["induction", "omega"], "temperature": 0.4},
      {"model": "text-gemini", "tactics": ["decide"], "temperature": 0.6}
    ],
    "max_retries": 3
  }'
```

```json
{
  "success": true,
  "code": "theorem add_zero (n : Nat) : n + 0 = n := by rfl",
  "strategy_index": 0,
  "attempts": 1,
  "all_results": [
    {"success": true, "attempts": 1, "strategy_index": 0},
    null,
    null
  ]
}
```

All strategies run concurrently. First compiled proof wins, others are cancelled.
`all_results[i] = null` means that strategy was cancelled before completing.
Each strategy has its own LLM model, tactics, and temperature.

### POST /compile (compile only, no LLM)

When you already have Lean4 code and just want to check if it compiles.

```bash
curl -s http://127.0.0.1:8604/compile \
  -H "Content-Type: application/json" \
  -d '{"code": "theorem test : 1 + 1 = 2 := by rfl", "timeout": 30}'
```

```json
{
  "success": true,
  "error": null,
  "stdout": "",
  "elapsed_ms": 1250.3
}
```

### POST /compile-batch (batch compilation)

Compile multiple proofs in parallel using the 20-worker pool.

```bash
curl -s http://127.0.0.1:8604/compile-batch \
  -H "Content-Type: application/json" \
  -d '{
    "proofs": [
      "theorem t1 : 1 + 1 = 2 := by rfl",
      "theorem t2 : 2 + 2 = 4 := by native_decide",
      "theorem t3 : True := trivial"
    ],
    "timeout": 30
  }'
```

```json
{
  "results": [
    {"success": true, "error": null, "stdout": "", "elapsed_ms": 1200.0},
    {"success": true, "error": null, "stdout": "", "elapsed_ms": 1180.0},
    {"success": true, "error": null, "stdout": "", "elapsed_ms": 950.0}
  ],
  "total_ms": 1450.0
}
```

The batch endpoint uses the full 20-worker pool — all proofs compile in parallel.

### POST /step-verify (tactic-by-tactic verification)

For GRPO training: verify each tactic step incrementally.

```bash
curl -s http://127.0.0.1:8604/step-verify \
  -H "Content-Type: application/json" \
  -d '{
    "theorem_header": "theorem test (n : Nat) : n + 0 = n := by",
    "tactics": ["induction n", "simp", "simp [Nat.succ_add]"]
  }'
```

## Python Usage (from any skill)

### Single proof (what /create-evidence-case does)

```python
import httpx

LEAN4_URL = "http://127.0.0.1:8604"

def prove_requirement(requirement: str) -> dict | None:
    try:
        resp = httpx.post(
            f"{LEAN4_URL}/prove",
            json={"requirement": requirement, "max_retries": 3},
            timeout=180,
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except (httpx.ConnectError, httpx.TimeoutException):
        return None

result = prove_requirement("Prove that for all n, n + 0 = n")
if result and result["success"]:
    print(f"Proof: {result['code']}")
```

### Check health before calling

```python
def lean4_available() -> bool:
    try:
        r = httpx.get(f"{LEAN4_URL}/health", timeout=5)
        return r.json().get("prove_available", False)
    except Exception:
        return False
```

### Batch compile (e.g. for QRA verification pipeline)

```python
proofs = [
    "theorem t1 : 1 + 1 = 2 := by rfl",
    "theorem t2 (n : Nat) : n + 0 = n := by simp",
    "theorem t3 : True := trivial",
]

resp = httpx.post(
    f"{LEAN4_URL}/compile-batch",
    json={"proofs": proofs, "timeout": 60},
    timeout=300,
)
results = resp.json()["results"]
for proof, result in zip(proofs, results):
    status = "OK" if result["success"] else f"FAIL: {result['error'][:80]}"
    print(f"  {status} ({result['elapsed_ms']:.0f}ms)")
```

## CLI Usage (standalone, uses /code-runner)

```bash
# Basic proof
./run.sh --requirement "Prove n + 0 = n"

# With tactics
./run.sh -r "Prove commutativity of addition" -t "simp,ring,omega"

# JSON via stdin
echo '{"requirement": "Prove n + 0 = n"}' | ./run.sh
```

The CLI path goes through `/code-runner` for iterative fix loops with escalation. The HTTP path is lighter — direct scillm + compile inside the container.

## How It Fits in /create-evidence-case

```
/create-evidence-case runner.py
    │
    ├─ Step 1: On-topic check
    ├─ Step 2: /memory recall
    ├─ Step 2b: /extract-entities (grounding gate)
    ├─ Step 3: Same-technique bridge
    ├─ Step 4: Semantic relation
    │
    ├─ Step 5a: Provability classifier (/assistant classify lean4_provable)
    │   └─ If "not_formalizable" with confidence >= 0.80 → skip lean4
    │
    ├─ Step 5b: POST :8604/prove        ← THIS IS THE CALL
    │   └─ Returns {success, code} or None (service down)
    │   └─ Gate: proof_success OR proof_skipped → gate passes
    │
    ├─ Step 5c: Plausibility gate
    └─ Step 6: Persist case to /memory
```

The lean4 gate is one of 6 boolean gates. If the service is down (`prove_available: false` from `/health`), the gate is skipped — not blocked. If the proof fails, the gate records the failure but doesn't block SATISFIED on its own (other gates compensate).

## Docker Setup

```yaml
# docker-compose.yml
services:
  lean4-prove:
    build: .
    container_name: lean4-prove-service
    network_mode: host          # reaches scillm at 127.0.0.1:4001
    environment:
      - LEAN4_SERVICE_PORT=8604
      - LEAN4_WORKERS=4
      - SCILLM_API_BASE=http://127.0.0.1:4001
    volumes:
      - lean4-lake-cache:/root/.elan        # elan toolchain cache
      - lean4-mathlib-cache:/tmp            # Mathlib build cache
      - ./service.py:/app/service.py:ro     # hot-reload without rebuild
      - ./compiler.py:/app/compiler.py:ro
```

**First startup:** Downloads Lean4 v4.28.0 + Mathlib (~10 min). Subsequent starts use cached volumes (~5 sec).

**Toolchain:** Pinned to v4.28.0. Mathlib not yet released for v4.29.0 as of 2026-03-29.

## What Changed (2026-03-29)

| Before | After |
|--------|-------|
| `claude -p` subprocess for LLM | httpx to `/scillm` inside container |
| `docker exec` for compilation | lean-interact 20-worker pool inside container |
| ThreadPoolExecutor + manual retry | `/code-runner` (CLI) or internal retry loop (HTTP) |
| No health check for service state | `/health` with scillm reachability + proof stats |
| No `/prove` endpoint | Full pipeline: generate + compile + retry via HTTP |
| Bridge network (can't reach scillm) | Host network (127.0.0.1:4001) |
| `elan default stable` (v4.29.0) | Pinned to v4.28.0 (Mathlib compatibility) |
| Baked service.py in image | Volume-mounted for hot-reload |
