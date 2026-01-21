---
name: lean4-prove
description: >
  Generate and verify Lean4 proofs using Claude OAuth.
  This skill combines proof generation with compilation verification in a retry loop.
allowed-tools: Bash, Read, Docker
triggers:
  - prove this
  - lean4 proof
  - generate proof
  - verify lean4
  - lean4-prove
metadata:
  short-description: Lean4 proof generation/verification pipeline
---

# lean4-prove

Generate and verify Lean4 proofs using Claude OAuth. This skill combines proof generation with compilation verification in a retry loop.

## How It Works

```
Requirement + Tactics + Persona
        │
        ▼
┌───────────────────────┐
│ Generate N candidates │  ← Claude OAuth (parallel)
│ via Claude Sonnet 4   │
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│ Compile each in       │  ← lean_runner Docker
│ lean_runner container │
└───────────────────────┘
        │
   ┌────┴────┐
   │         │
 Success   Failure
   │         │
   ▼         ▼
 Return   Retry with error feedback
          (up to max_retries)
```

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

# Custom settings
./run.sh -r "Prove theorem" --candidates 5 --retries 5 --model claude-sonnet-4-20250514
```

## Output

```json
{
  "success": true,
  "code": "theorem add_zero (n : Nat) : n + 0 = n := rfl",
  "attempts": 1,
  "candidate": 0,
  "errors": null
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
  ]
}
```

## Parameters

| Parameter           | Default                  | Description                       |
| ------------------- | ------------------------ | --------------------------------- |
| `--requirement, -r` | (required)               | Theorem to prove                  |
| `--tactics, -t`     | none                     | Comma-separated preferred tactics |
| `--persona, -p`     | none                     | Persona context for generation    |
| `--candidates, -n`  | 3                        | Parallel proof candidates         |
| `--retries`         | 3                        | Max retries per candidate         |
| `--model`           | claude-sonnet-4-20250514 | Claude model                      |
| `--container`       | lean_runner              | Docker container name             |
| `--timeout`         | 120                      | Compilation timeout (seconds)     |

## Environment Variables

```bash
LEAN4_CONTAINER=lean_runner      # Docker container
LEAN4_TIMEOUT=120                # Compile timeout
LEAN4_MAX_RETRIES=3              # Retries per candidate
LEAN4_CANDIDATES=3               # Parallel candidates
LEAN4_PROVE_MODEL=opus           # Claude model (opus recommended for proofs)
```

## Authentication

Uses Claude Code CLI (`claude -p`) in headless non-interactive mode.

The CLI is called with:
- `-p` flag for print/headless mode
- `--output-format text` for plain text output
- `--max-turns 1` for single-turn operation

Environment variables `CLAUDE_CODE` and `CLAUDECODE` are cleared to avoid recursion detection when called from within Claude Code.

No separate API key required - authentication is handled via your Claude subscription.

## Requirements

1. **Docker** with `lean_runner` container running (Lean4 + Mathlib installed)
2. **Claude Code CLI** (`claude`) in PATH with valid authentication

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

### Simple arithmetic

```bash
./run.sh -r "Prove for all natural numbers n, n + 0 = n" -t "rfl"
```

### With persona

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
