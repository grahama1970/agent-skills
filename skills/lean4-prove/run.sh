#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -eo pipefail

# lean4-prove: Generate and verify Lean4 proofs using Claude OAuth
# Input: --requirement "theorem" or JSON via stdin
# Output: JSON {success, code, attempts, errors}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'


PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Default values
CONTAINER="${LEAN4_CONTAINER:-lean_runner}"
TIMEOUT="${LEAN4_TIMEOUT:-120}"
RETRIES="${LEAN4_MAX_RETRIES:-3}"
CANDIDATES="${LEAN4_CANDIDATES:-3}"
MODEL="${LEAN4_PROVE_MODEL:-text}"

# ---------------------------------------------------------------------------
# Subcommand: serve (HTTP compilation service daemon)
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "serve" ]]; then
    shift
    exec "$SCRIPT_DIR/serve.sh" "$@"
fi

# ---------------------------------------------------------------------------
# Subcommand: qra-verify (Phase 1 QRA consistency verification)
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "qra-verify" ]]; then
    shift
    # Defaults for qra-verify
    QRA_SCOPE="sparta"
    QRA_LIMIT=10
    QRA_SOURCE="hierarchy"
    QRA_FORMAT="text"
    QRA_CMD="verify"

    while [[ $# -gt 0 ]]; do
        case $1 in
            --scope) QRA_SCOPE="$2"; shift 2 ;;
            --limit) QRA_LIMIT="$2"; shift 2 ;;
            --source) QRA_SOURCE="$2"; shift 2 ;;
            --format) QRA_FORMAT="$2"; shift 2 ;;
            --container) CONTAINER="$2"; shift 2 ;;
            --timeout) TIMEOUT="$2"; shift 2 ;;
            generate) QRA_CMD="generate"; shift ;;
            list-chains) QRA_CMD="list-chains"; shift ;;
            verify) QRA_CMD="verify"; shift ;;
            --help)
                cat << 'QRAEOF'
Usage: ./run.sh qra-verify [SUBCOMMAND] [OPTIONS]

Verify QRA control chains for subsumption transitivity via Lean4 proofs.

Subcommands:
  verify        Compile and verify chains (default)
  generate      Generate Lean4 code without compiling (dry run)
  list-chains   List available chains from ArangoDB

Options:
  --scope TEXT      Dataset scope (default: sparta)
  --limit NUM       Max chains (default: 10)
  --source TEXT     Chain source: hierarchy or relationships (default: hierarchy)
  --format TEXT     Output: text or json (default: text)
  --container NAME  Docker container (default: lean_runner)
  --timeout SECS    Compile timeout (default: 120)

Examples:
  ./run.sh qra-verify --scope sparta --limit 5
  ./run.sh qra-verify generate --source relationships --limit 3
  ./run.sh qra-verify list-chains --limit 20
QRAEOF
                exit 0
                ;;
            *) shift ;;
        esac
    done

    QRA_ARGS=("$QRA_CMD"
        --scope "$QRA_SCOPE"
        --limit "$QRA_LIMIT"
        --source "$QRA_SOURCE"
        --container "$CONTAINER"
        --timeout "$TIMEOUT"
    )

    if [[ "$QRA_CMD" == "verify" ]]; then
        QRA_ARGS+=(--output-format "$QRA_FORMAT")
    fi

    python3 "$SCRIPT_DIR/qra_consistency.py" "${QRA_ARGS[@]}"
    exit $?
fi

# ---------------------------------------------------------------------------
# Subcommand: lab (self-improving lab capabilities)
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "lab" ]]; then
    shift
    python3 "$SCRIPT_DIR/lab_cli.py" "$@"
    exit $?
fi

# ---------------------------------------------------------------------------
# Standard proof generation mode
# ---------------------------------------------------------------------------

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

