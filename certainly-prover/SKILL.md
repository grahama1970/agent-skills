---
name: certainly-prover
description: Prove mathematical statements using Lean4 theorem prover. Use when asked to prove, verify, or formalize mathematical properties.
allowed-tools: Read, Bash, Grep, Glob
metadata:
  short-description: Lean4 theorem proving via scillm
---

# Certainly Prover

Formally verify mathematical statements by generating Lean4 proofs.

## Simplest Usage

```python
from scillm.integrations.certainly import prove_requirement

result = await prove_requirement("Prove that n + 0 = n")

if result["ok"]:
    print(result["lean4_code"])   # The proof
else:
    print(result["suggestion"])   # How to fix
```

## Common Patterns

### Prove an identity
```python
result = await prove_requirement("Prove that 0 + n = n", tactics=["simp"])
# result["lean4_code"] → "theorem ... := by simp"
```

### Prove an inequality
```python
result = await prove_requirement("Prove n < n + 1", tactics=["omega"])
# result["lean4_code"] → "theorem ... := by omega"
```

### Prove algebra
```python
result = await prove_requirement("Prove (a+b)² = a² + 2ab + b²", tactics=["ring"])
# result["lean4_code"] → "theorem ... := by ring"
```

### Handle failure
```python
result = await prove_requirement("Prove 2 + 2 = 5")
if not result["ok"]:
    print(result["failure_reason"])  # "mathematically false..."
    print(result["suggestion"])      # "Change to '2 + 2 = 4'"
```

## Response Fields

**On success (`result["ok"] == True`):**
| Field | Example |
|-------|---------|
| `lean4_code` | `"theorem add_zero (n : ℕ) : n + 0 = n := by simp"` |
| `summary` | `"Proof found (7406ms)"` |
| `tactic_used` | `"simp tactic which knows about Nat.add_zero"` |
| `compile_time_ms` | `7406` |

**On failure (`result["ok"] == False`):**
| Field | Example |
|-------|---------|
| `failure_reason` | `"mathematically false in standard arithmetic"` |
| `suggestion` | `"Change to 'Prove that 2 + 2 = 4'"` |
| `summary` | `"Proof failed: mathematically false..."` |
| `num_attempts` | `3` |

## Tactic Hints

Tactics guide the prover. Default is fine for most cases.

| Tactic | When to use |
|--------|-------------|
| `simp` | Identities, simplification (default, try first) |
| `omega` | Integer/natural number arithmetic |
| `ring` | Polynomial algebra |
| `linarith` | Linear inequalities |
| `decide` | True/false propositions |

```python
# Let prover choose (usually works)
result = await prove_requirement("Prove n + 0 = n")

# Suggest specific tactics
result = await prove_requirement("Prove n + 0 = n", tactics=["simp", "rfl"])
```

See [TACTICS.md](TACTICS.md) for full reference.

## CLI for Quick Tests

```bash
python -m lean4_prover.certainly_min "Prove n + 0 = n" --tactics simp
```

## Prerequisites

Requires three things:

1. **lean_runner container** running:
   ```bash
   # Check: docker ps | grep lean_runner
   # Start: cd /path/to/lean4 && make lean-runner-up
   ```

2. **OPENROUTER_API_KEY** set:
   ```bash
   export OPENROUTER_API_KEY=sk-or-...
   ```

3. **scillm[certainly]** installed:
   ```bash
   pip install scillm[certainly]
   ```

**Quick check:**
```python
from scillm.integrations.certainly import is_available, check_lean_container
print("Package:", is_available())
print("Container:", check_lean_container())
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `certainly not available` | `pip install scillm[certainly]` |
| `lean_runner not running` | `make lean-runner-up` in lean4 repo |
| `OPENROUTER_API_KEY not set` | Export the API key |
| Timeout | Add `compile_timeout_s=180` |
| Proof fails | Check `result["suggestion"]` for guidance |
