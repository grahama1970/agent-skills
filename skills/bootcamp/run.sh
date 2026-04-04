#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(dirname "$SCRIPT_DIR")"
UV="${UV:-uv}"

STATE_DIR="${HOME}/.embry"
STATE_FILE="${STATE_DIR}/bootcamp_state.json"

STEPS=("welcome" "health-check" "data-overview" "first-query" "baseline")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

usage() {
    cat <<'EOF'
Usage:
  ./run.sh start --role ROLE [--dry-run]
  ./run.sh resume

Roles: operator | compliance-officer | developer

Options:
  --role ROLE   Onboarding track (required for start)
  --dry-run     Print the full onboarding script without executing sub-skills
EOF
    exit 1
}

save_state() {
    local role="$1" step_idx="$2"
    mkdir -p "$STATE_DIR"
    cat > "$STATE_FILE" <<EOJSON
{
  "role": "${role}",
  "completed_step": ${step_idx},
  "total_steps": ${#STEPS[@]},
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOJSON
}

# ---------------------------------------------------------------------------
# Role-specific content generators
# ---------------------------------------------------------------------------

welcome_content() {
    local role="$1"
    cat <<EOF

================================================================================
  STEP 1 / 5 — Welcome
================================================================================

Welcome to Embry OS.  I'm Embry Lawson and I'll be walking you through your
first session.

EOF
    case "$role" in
        operator)
            cat <<'EOF'
You're joining as a Manufacturing Floor Operator.  Embry OS gives you voice-
first access to compliance data, sensor feeds, and work-order context — no
typing required.  Your primary interfaces will be the Stream Deck, voice
commands, and the 10ft wall display.

Key concepts for your role:
  - Voice commands via push-to-talk (Meta+Space) or Stream Deck button
  - Sensor monitoring dashboards on SPARTA wall display
  - Manufacturing provenance tracking — every component traced from vendor
    to finished assembly
EOF
            ;;
        compliance-officer)
            cat <<'EOF'
You're joining as a Compliance Officer.  Embry OS provides continuous drift
detection across program generations (F-16 -> F-22 -> F-35 -> next), OSCAL
export for NIST controls, and a full audit timeline backed by ArangoDB.

Key concepts for your role:
  - 3-Tier Validation Cascade for compliance verification
  - OSCAL JSON export via /export-oscal
  - Compliance drift detection comparing control sets across programs
  - Audit timeline with full revision history
EOF
            ;;
        developer)
            cat <<'EOF'
You're joining as a Developer.  Embry OS is built on 7 FastAPI daemons
communicating over Unix sockets and D-Bus, with 200+ skills as the universal
extension mechanism.  Skills are deliberately simple (SKILL.md + run.sh +
sanity.sh) so the barrier to new functionality is near zero.

Key concepts for your role:
  - Daemons live in services/*-daemon/ and communicate via /run/user/1000/embry/
  - Skills live in .pi/skills/ — each has SKILL.md, run.sh, sanity.sh
  - All LLM calls route through inference-daemon (scillm)
  - Memory First: no memory = 503, not degraded response
  - Tests: PYTHONPATH=services:$PYTHONPATH uv run python -m pytest services/tests/ -q
EOF
            ;;
    esac
}

health_check_content() {
    local role="$1" dry_run="$2"
    cat <<EOF

================================================================================
  STEP 2 / 5 — Health Check
================================================================================

Before we do anything else, let's make sure the daemons are alive.

EOF
    if [[ "$dry_run" == "true" ]]; then
        echo "[dry-run] Would execute: /service-status"
        echo ""
        echo "This calls each daemon's /health endpoint over its Unix socket and"
        echo "reports which of the 7 services (state, voice, sparta, memory,"
        echo "inference, datalake, discord) are responsive."
    else
        echo "Running /service-status ..."
        if [[ -x "${SKILLS_DIR}/service-status/run.sh" ]]; then
            bash "${SKILLS_DIR}/service-status/run.sh" || echo "[warn] service-status returned non-zero"
        else
            echo "[skip] /service-status not found at ${SKILLS_DIR}/service-status/run.sh"
        fi
    fi
}

data_overview_content() {
    local role="$1" dry_run="$2"
    cat <<EOF

================================================================================
  STEP 3 / 5 — Data Overview
================================================================================

Now let's see what data is already in the system.

EOF
    if [[ "$dry_run" == "true" ]]; then
        echo "[dry-run] Would execute: /data-audit"
        echo ""
        echo "This reports on data completeness for the SPARTA QRA pipeline,"
        echo "showing counts of Controls, URIs, QRA triples, and any gaps"
        echo "in the compliance graph."
    else
        echo "Running /data-audit ..."
        if [[ -x "${SKILLS_DIR}/data-audit/run.sh" ]]; then
            bash "${SKILLS_DIR}/data-audit/run.sh" || echo "[warn] data-audit returned non-zero"
        else
            echo "[skip] /data-audit not found at ${SKILLS_DIR}/data-audit/run.sh"
        fi
    fi
}

first_query_content() {
    local role="$1"
    cat <<EOF

================================================================================
  STEP 4 / 5 — First Query
================================================================================

Let's try a role-appropriate query so you can see the system respond.

EOF
    case "$role" in
        operator)
            cat <<'EOF'
Try asking via voice (Meta+Space) or type:

  "What is the current status of CNC machine 7?"

This routes through the inference daemon, queries the datalake for recent
sensor readings, and returns a natural-language summary.  On the factory
floor you'd use the Stream Deck or voice — no keyboard needed.

Other queries to try:
  - "Show me today's tolerance deviations"
  - "Which vendor batches arrived this week?"
  - "Flag any out-of-spec components on Line 3"
EOF
            ;;
        compliance-officer)
            cat <<'EOF'
Try this query:

  "Show compliance drift between F-16 Block 52 and F-35 Lot 15"

This invokes the drift detection endpoint, compares control sets across
program generations, and highlights where requirements diverged.

Other queries to try:
  - "Export OSCAL for AC-2 family controls"
  - "Show audit timeline for last 30 days"
  - "Which controls lack QRA coverage?"
EOF
            ;;
        developer)
            cat <<'EOF'
Try this query:

  "What skills compose into the extractor pipeline?"

This exercises the memory graph to trace skill composition chains.

Other queries to try:
  - "Show me the cascade validation flow"
  - "Which daemons does the voice skill depend on?"
  - "Run sanity checks for the last 5 modified skills"
EOF
            ;;
    esac
}

baseline_content() {
    local role="$1"
    cat <<EOF

================================================================================
  STEP 5 / 5 — Compliance Baseline
================================================================================

Finally, here's your current compliance posture.

EOF
    case "$role" in
        operator)
            cat <<'EOF'
As an operator, your compliance baseline focuses on:

  - Manufacturing process controls and their current pass/fail status
  - Sensor calibration records and last-verified dates
  - Material traceability — every alloy batch linked to vendor COA
  - Active deviations and their approval status

The SPARTA dashboard (wall display or expert workstation) shows this
in real time.  Any drift triggers a D-Bus alert that lights up your
Stream Deck.

Bootcamp complete.  Welcome aboard.
EOF
            ;;
        compliance-officer)
            cat <<'EOF'
As a compliance officer, your baseline covers:

  - NIST SP 800-171 control coverage percentage
  - Open POA&M items and remediation timelines
  - Cross-program drift alerts (legacy -> current)
  - OSCAL export readiness for each control family
  - 3-Tier Cascade validation status (Tier 0 active, Tier 1.5 pending)

Use /export-oscal and /compliance-timeline regularly to maintain audit
readiness.

Bootcamp complete.  Welcome aboard.
EOF
            ;;
        developer)
            cat <<'EOF'
As a developer, your baseline is the test suite and skill health:

  - 263+ tests passing (services/tests/)
  - 7 daemons with systemd units and health endpoints
  - 200+ skills with SKILL.md + run.sh + sanity.sh contracts
  - Nightly monitors: /monitor-skills, /monitor-skill-health, /monitor-security
  - Skill creation: /skill-lab generates new skills from existing patterns

Run the test suite now to verify your environment:
  PYTHONPATH=services:$PYTHONPATH uv run python -m pytest services/tests/ -q

Bootcamp complete.  Welcome aboard.
EOF
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

cmd_start() {
    local role="" dry_run="false"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --role)   role="$2"; shift 2 ;;
            --dry-run) dry_run="true"; shift ;;
            *)        echo "Unknown option: $1"; usage ;;
        esac
    done

    if [[ -z "$role" ]]; then
        echo "Error: --role is required"
        usage
    fi

    case "$role" in
        operator|compliance-officer|developer) ;;
        *) echo "Error: invalid role '$role' (must be operator|compliance-officer|developer)"; exit 1 ;;
    esac

    for i in "${!STEPS[@]}"; do
        case "${STEPS[$i]}" in
            welcome)        welcome_content "$role" ;;
            health-check)   health_check_content "$role" "$dry_run" ;;
            data-overview)  data_overview_content "$role" "$dry_run" ;;
            first-query)    first_query_content "$role" ;;
            baseline)       baseline_content "$role" ;;
        esac

        if [[ "$dry_run" == "false" ]]; then
            save_state "$role" "$i"
        fi
    done
}

cmd_resume() {
    if [[ ! -f "$STATE_FILE" ]]; then
        echo "No saved bootcamp state found at $STATE_FILE"
        echo "Start a new session with: ./run.sh start --role ROLE"
        exit 1
    fi

    local role completed_step
    role="$(grep '"role"' "$STATE_FILE" | sed 's/.*: *"\(.*\)".*/\1/')"
    completed_step="$(grep '"completed_step"' "$STATE_FILE" | sed 's/.*: *\([0-9]*\).*/\1/')"

    local next_step=$((completed_step + 1))
    if [[ $next_step -ge ${#STEPS[@]} ]]; then
        echo "Bootcamp already complete for role '${role}'.  Start fresh with:"
        echo "  ./run.sh start --role ${role}"
        exit 0
    fi

    echo "Resuming bootcamp for role '${role}' from step $((next_step + 1))/${#STEPS[@]} (${STEPS[$next_step]})..."

    for i in $(seq "$next_step" $((${#STEPS[@]} - 1))); do
        case "${STEPS[$i]}" in
            welcome)        welcome_content "$role" ;;
            health-check)   health_check_content "$role" "false" ;;
            data-overview)  data_overview_content "$role" "false" ;;
            first-query)    first_query_content "$role" ;;
            baseline)       baseline_content "$role" ;;
        esac
        save_state "$role" "$i"
    done
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if [[ $# -lt 1 ]]; then
    usage
fi

SUBCMD="$1"; shift

case "$SUBCMD" in
    start)  cmd_start "$@" ;;
    resume) cmd_resume ;;
    *)      echo "Unknown subcommand: $SUBCMD"; usage ;;
esac
