#!/bin/bash
set -eo pipefail

# lean4-prove: Generate and verify Lean4 proofs using Claude OAuth
# Input: --requirement "theorem" or JSON via stdin
# Output: JSON {success, code, attempts, errors}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default values
CONTAINER="${LEAN4_CONTAINER:-lean_runner}"
TIMEOUT="${LEAN4_TIMEOUT:-120}"
RETRIES="${LEAN4_MAX_RETRIES:-3}"
CANDIDATES="${LEAN4_CANDIDATES:-3}"
MODEL="${LEAN4_PROVE_MODEL:-claude-sonnet-4-20250514}"

REQUIREMENT=""
TACTICS=""
PERSONA=""

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --requirement|-r) REQUIREMENT="$2"; shift 2 ;;
        --tactics|-t) TACTICS="$2"; shift 2 ;;
        --persona|-p) PERSONA="$2"; shift 2 ;;
        --retries) RETRIES="$2"; shift 2 ;;
        --candidates|-n) CANDIDATES="$2"; shift 2 ;;
        --model) MODEL="$2"; shift 2 ;;
        --container) CONTAINER="$2"; shift 2 ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        --help)
            cat << 'EOF'
Usage: ./run.sh [OPTIONS]

Generate and verify Lean4 proofs using Claude OAuth.

Options:
  --requirement, -r TEXT    Theorem to prove (required, or use stdin)
  --tactics, -t LIST        Comma-separated tactics (e.g., "simp,ring,omega")
  --persona, -p TEXT        Persona context (e.g., "cryptographer")
  --retries NUM             Max retries per candidate (default: 3)
  --candidates, -n NUM      Parallel candidates to generate (default: 3)
  --model NAME              Claude model (default: claude-sonnet-4-20250514)
  --container NAME          Docker container (default: lean_runner)
  --timeout SECS            Compile timeout (default: 120)
  --help                    Show this help

Examples:
  ./run.sh --requirement "Prove n + 0 = n" --tactics "rfl"
  ./run.sh -r "Prove commutativity of addition" -t "simp,ring" -p "mathematician"
  echo '{"requirement": "Prove n + 0 = n"}' | ./run.sh

Environment Variables:
  LEAN4_CONTAINER       Default container name
  LEAN4_TIMEOUT         Default compile timeout
  LEAN4_MAX_RETRIES     Default max retries
  LEAN4_CANDIDATES      Default parallel candidates
  LEAN4_PROVE_MODEL     Default Claude model

Authentication:
  Uses OAuth token from ~/.claude/.credentials.json (Claude Max Plan)
EOF
            exit 0
            ;;
        *) shift ;;
    esac
done

# Build arguments for Python
ARGS=()

if [[ -n "$REQUIREMENT" ]]; then
    ARGS+=(--requirement "$REQUIREMENT")
fi

if [[ -n "$TACTICS" ]]; then
    ARGS+=(--tactics "$TACTICS")
fi

if [[ -n "$PERSONA" ]]; then
    ARGS+=(--persona "$PERSONA")
fi

ARGS+=(--retries "$RETRIES")
ARGS+=(--candidates "$CANDIDATES")
ARGS+=(--model "$MODEL")
ARGS+=(--container "$CONTAINER")
ARGS+=(--timeout "$TIMEOUT")

# Run Python script
if [[ -n "$REQUIREMENT" ]]; then
    python3 "$SCRIPT_DIR/prove.py" "${ARGS[@]}"
else
    # Pass stdin through
    python3 "$SCRIPT_DIR/prove.py" "${ARGS[@]}"
fi

