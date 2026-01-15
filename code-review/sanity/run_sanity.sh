#!/usr/bin/env bash
# Sanity checks for code-review skill providers
# Usage: ./run_sanity.sh [provider] [model]
#   ./run_sanity.sh                    # Run all sanity checks
#   ./run_sanity.sh openai gpt-5.2     # Run specific provider/model
#   ./run_sanity.sh anthropic opus-4.5
#   ./run_sanity.sh github gpt-5.2

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
REQUEST_FILE="$SCRIPT_DIR/test_request.md"
OUTPUT_DIR="/tmp/code-review-sanity"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Run a single provider/model sanity check
run_sanity_check() {
    local provider="$1"
    local model="$2"
    local timeout="${3:-120}"

    log_info "Testing: provider=$provider model=$model"

    # Check if provider CLI is available
    local check_output
    if ! check_output=$(python "$SKILL_DIR/code_review.py" check --provider "$provider" 2>&1); then
        log_error "Provider $provider not available:"
        echo "$check_output"
        return 1
    fi

    # Create output directory for this test
    local test_output_dir="$OUTPUT_DIR/${provider}_${model}"
    mkdir -p "$test_output_dir"

    local output_file="$test_output_dir/output.json"
    local log_file="$test_output_dir/run.log"

    log_info "Output dir: $test_output_dir"
    log_info "Running review command (timeout=${timeout}s)..."

    local start_time=$(date +%s)

    # Run the review command (no timeout - runs until completion)
    if python "$SKILL_DIR/code_review.py" review \
        --file "$REQUEST_FILE" \
        --provider "$provider" \
        --model "$model" \
        > "$output_file" 2> "$log_file"; then

        local end_time=$(date +%s)
        local duration=$((end_time - start_time))

        log_info "Command completed in ${duration}s"

        # Validate output
        if [ -s "$output_file" ]; then
            # Check if output is valid JSON
            if python -c "import json; json.load(open('$output_file'))" 2>/dev/null; then
                log_info "Valid JSON output"

                # Check for response content
                local response_len=$(python -c "import json; print(len(json.load(open('$output_file')).get('response', '')))")
                log_info "Response length: $response_len chars"

                if [ "$response_len" -gt 100 ]; then
                    log_info "${GREEN}PASS${NC}: $provider/$model - Got substantive response"
                    echo ""
                    echo "--- Response preview (first 500 chars) ---"
                    python -c "import json; r=json.load(open('$output_file')).get('response',''); print(r[:500])"
                    echo "---"
                    return 0
                else
                    log_warn "Response seems too short ($response_len chars)"
                    cat "$output_file"
                    return 1
                fi
            else
                log_error "Output is not valid JSON"
                cat "$output_file"
                return 1
            fi
        else
            log_error "No output produced"
            cat "$log_file"
            return 1
        fi
    else
        local exit_code=$?
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))

        log_error "Command failed after ${duration}s (exit code: $exit_code)"
        echo "--- stderr ---"
        cat "$log_file"
        echo "--- stdout ---"
        cat "$output_file" 2>/dev/null || echo "(empty)"
        return 1
    fi
}

# Main
main() {
    mkdir -p "$OUTPUT_DIR"

    if [ ! -f "$REQUEST_FILE" ]; then
        log_error "Test request file not found: $REQUEST_FILE"
        exit 1
    fi

    log_info "Sanity check for code-review skill"
    log_info "Request file: $REQUEST_FILE"
    log_info "Output dir: $OUTPUT_DIR"
    echo ""

    # If specific provider/model given, run just that
    if [ $# -ge 2 ]; then
        local provider="$1"
        local model="$2"
        local timeout="${3:-120}"

        if run_sanity_check "$provider" "$model" "$timeout"; then
            log_info "${GREEN}SANITY CHECK PASSED${NC}: $provider/$model"
            exit 0
        else
            log_error "${RED}SANITY CHECK FAILED${NC}: $provider/$model"
            exit 1
        fi
    fi

    # Run all configured sanity checks
    local passed=0
    local failed=0
    local skipped=0

    declare -A TESTS=(
        ["openai:gpt-5.2"]="120"
        ["anthropic:opus-4.5"]="120"
        ["github:gpt-5"]="120"
    )

    for test_spec in "${!TESTS[@]}"; do
        local provider="${test_spec%%:*}"
        local model="${test_spec##*:}"
        local timeout="${TESTS[$test_spec]}"

        echo ""
        echo "=============================================="
        echo "Testing: $provider / $model"
        echo "=============================================="

        # Check if provider is available before testing
        if ! python "$SKILL_DIR/code_review.py" check --provider "$provider" >/dev/null 2>&1; then
            log_warn "Skipping $provider - CLI not available"
            ((skipped++))
            continue
        fi

        if run_sanity_check "$provider" "$model" "$timeout"; then
            ((passed++))
        else
            ((failed++))
        fi
    done

    echo ""
    echo "=============================================="
    echo "SANITY CHECK SUMMARY"
    echo "=============================================="
    echo -e "Passed:  ${GREEN}$passed${NC}"
    echo -e "Failed:  ${RED}$failed${NC}"
    echo -e "Skipped: ${YELLOW}$skipped${NC}"
    echo ""

    if [ "$failed" -gt 0 ]; then
        log_error "Some sanity checks failed"
        exit 1
    else
        log_info "All sanity checks passed"
        exit 0
    fi
}

main "$@"
