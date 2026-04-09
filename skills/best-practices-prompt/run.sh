#!/usr/bin/env bash
set -eo pipefail
unset VIRTUAL_ENV
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<'EOF'
best-practices-prompt — Prompt quality gate with HTML inspection

Usage:
  ./run.sh review --prompt <file>   Open prompt in browser with weasel-word highlights + checklist
  ./run.sh review --prompt <file> --payload <file>  Include the data payload too
  ./run.sh check  --prompt <file>   CLI-only weasel word scan (no browser)
  ./run.sh rules                    Print all rules (SKILL.md)
  ./run.sh help                     This message

Options:
  --prompt, -p     Prompt file to review (.txt, .md, or .py with inline strings)
  --payload, -d    Optional payload/context file that accompanies the prompt
  --no-open        Generate HTML but don't open browser
EOF
}

# --- Weasel word list ---
WEASEL_WORDS="relevant|appropriate|comprehensive|thorough|important|ensure|consider|properly|meaningful|high.quality|as needed|various|leverage|utilize"

cmd_check() {
    local PROMPT_FILE="" PAYLOAD_FILE=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --prompt|-p) PROMPT_FILE="$2"; shift 2 ;;
            --payload|-d) PAYLOAD_FILE="$2"; shift 2 ;;
            *) shift ;;
        esac
    done

    if [[ -z "$PROMPT_FILE" || ! -f "$PROMPT_FILE" ]]; then
        echo "ERROR: --prompt <file> required" >&2
        exit 1
    fi

    # Check if prompt contains a placeholder like {evidence_case_json} or {payload}
    local HAS_PLACEHOLDER=false
    if grep -qE '\{[a-z_]+_json\}|\{payload\}|\{document\}|\{input\}|<evidence|<payload|<document' "$PROMPT_FILE"; then
        HAS_PLACEHOLDER=true
    fi

    # REQUIRE payload if prompt has a placeholder (Rule 15: grounding-match-pipeline-schema)
    if [[ "$HAS_PLACEHOLDER" == true && ( -z "$PAYLOAD_FILE" || ! -f "$PAYLOAD_FILE" ) ]]; then
        echo "═══════════════════════════════════════════════════════════"
        echo "  BLOCKED: Prompt contains a data placeholder but no"
        echo "  --payload was provided."
        echo ""
        echo "  Rule 15 (grounding-match-pipeline-schema) requires the"
        echo "  ENTIRE prompt payload to verify field paths match."
        echo ""
        echo "  A prompt without its payload is UNTESTABLE."
        echo ""
        echo "  Fix: ./run.sh check --prompt $PROMPT_FILE --payload <payload.json>"
        echo "═══════════════════════════════════════════════════════════"
        exit 2
    fi

    echo "=== Weasel Word Scan: $(basename "$PROMPT_FILE") ==="
    local COUNT=0
    while IFS= read -r line; do
        local LINENO_NUM=$(echo "$line" | cut -d: -f1)
        local CONTENT=$(echo "$line" | cut -d: -f2-)
        echo "  LINE $LINENO_NUM: $CONTENT"
        COUNT=$((COUNT + 1))
    done < <(grep -niE "$WEASEL_WORDS" "$PROMPT_FILE" || true)

    if [[ $COUNT -eq 0 ]]; then
        echo "  PASS: No weasel words found"
    else
        echo ""
        echo "  FAIL: $COUNT lines contain weasel words"
        echo "  Fix these before sending to /review-prompt"
    fi

    # Checklist checks
    echo ""
    echo "=== Checklist ==="
    local PASS=0 FAIL=0

    # Check for JSON schema
    if grep -qiE '(json|schema|"type"|"properties"|Pydantic)' "$PROMPT_FILE"; then
        echo "  [x] Output format specified"; PASS=$((PASS+1))
    else
        echo "  [ ] Output format specified — MISSING"; FAIL=$((FAIL+1))
    fi

    # Check for example
    if grep -qiE '(example|input.*output|expected.*output|sample)' "$PROMPT_FILE"; then
        echo "  [x] Example present"; PASS=$((PASS+1))
    else
        echo "  [ ] Example present — MISSING"; FAIL=$((FAIL+1))
    fi

    # Check for imperative voice (starts with verb-like words)
    if grep -qE '^(Extract|Return|List|Check|Parse|Generate|Create|Find|Scan|Output|Identify|Classify)' "$PROMPT_FILE"; then
        echo "  [x] Imperative voice"; PASS=$((PASS+1))
    else
        echo "  [ ] Imperative voice — not detected"; FAIL=$((FAIL+1))
    fi

    # Check for rejection criteria
    if grep -qiE '(do not|don.t|must not|never|invalid|reject|ignore|skip|exclude)' "$PROMPT_FILE"; then
        echo "  [x] Rejection criteria present"; PASS=$((PASS+1))
    else
        echo "  [ ] Rejection criteria — MISSING"; FAIL=$((FAIL+1))
    fi

    # Check for rationale header (Rule 0)
    if head -1 "$PROMPT_FILE" | grep -q '^# RATIONALE'; then
        echo "  [x] Rationale header"; PASS=$((PASS+1))
    else
        echo "  [ ] Rationale header — MISSING (Rule 0, NON-NEGOTIABLE)"; FAIL=$((FAIL+1))
    fi

    # Rule 15: Payload field path verification
    if [[ -n "$PAYLOAD_FILE" && -f "$PAYLOAD_FILE" ]]; then
        echo ""
        echo "=== Payload Field Verification (Rule 15) ==="
        local FIELD_ERRORS=0
        # Only check INPUT data paths: patterns with [] or . (e.g., glossary[].framework,
        # prior_qra_evidence[].answer). Bare field names (answer, id, framework) are
        # output schema fields — NOT checked against the input payload.
        while IFS= read -r field_ref; do
            # Get the root key (before first [] or .)
            local top_key=$(echo "$field_ref" | sed 's/\[\].*//; s/\..*//; s/[^a-zA-Z0-9_]//g')
            if [[ -n "$top_key" ]]; then
                if ! python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert sys.argv[2] in (d if isinstance(d,dict) else d[0] if isinstance(d,list) and d else {})" "$PAYLOAD_FILE" "$top_key" 2>/dev/null; then
                    echo "  MISSING: '$top_key' referenced in prompt but NOT in payload"
                    FIELD_ERRORS=$((FIELD_ERRORS+1))
                fi
            fi
        done < <(grep -oE '`[a-z_]+(\[\]|\.[a-z_]+)[a-z_\[\].]*`' "$PROMPT_FILE" | tr -d '`' | sort -u)

        if [[ $FIELD_ERRORS -eq 0 ]]; then
            echo "  [x] All referenced fields exist in payload"; PASS=$((PASS+1))
        else
            echo "  [ ] $FIELD_ERRORS field(s) missing from payload"; FAIL=$((FAIL+1))
        fi
    fi

    echo ""
    echo "Score: $PASS passed, $FAIL failed, $COUNT weasel words"
    [[ $FAIL -eq 0 && $COUNT -eq 0 ]] && echo "Result: PASS" || echo "Result: NEEDS WORK"
    [[ $FAIL -gt 0 || $COUNT -gt 0 ]] && exit 1 || exit 0
}

cmd_review() {
    local PROMPT_FILE="" PAYLOAD_FILE="" NO_OPEN=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --prompt|-p) PROMPT_FILE="$2"; shift 2 ;;
            --payload|-d) PAYLOAD_FILE="$2"; shift 2 ;;
            --no-open) NO_OPEN=true; shift ;;
            *) shift ;;
        esac
    done

    if [[ -z "$PROMPT_FILE" || ! -f "$PROMPT_FILE" ]]; then
        echo "ERROR: --prompt <file> required" >&2
        exit 1
    fi

    # Convert file contents to JSON strings for safe injection into template
    local PROMPT_JSON PAYLOAD_JSON FILENAME_JSON
    PROMPT_JSON=$(python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" < "$PROMPT_FILE")
    FILENAME_JSON=$(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$(basename "$PROMPT_FILE")")

    if [[ -n "$PAYLOAD_FILE" && -f "$PAYLOAD_FILE" ]]; then
        PAYLOAD_JSON=$(python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" < "$PAYLOAD_FILE")
    else
        PAYLOAD_JSON='""'
    fi

    local TEMPLATE="$SCRIPT_DIR/template.html"
    local OUT="/tmp/prompt-review-$(date +%s).html"

    # Use Python for safe template injection (sed chokes on slashes in JSON)
    python3 -c "
import sys, json
template = open(sys.argv[1]).read()
prompt_json = sys.argv[2]
payload_json = sys.argv[3]
filename_json = sys.argv[4]
filename = sys.argv[5]
out = template.replace('{{PROMPT_JSON}}', prompt_json)
out = out.replace('{{PAYLOAD_JSON}}', payload_json)
out = out.replace('{{FILENAME_JSON}}', filename_json)
out = out.replace('{{FILENAME}}', filename)
open(sys.argv[6], 'w').write(out)
" "$TEMPLATE" "$PROMPT_JSON" "$PAYLOAD_JSON" "$FILENAME_JSON" "$(basename "$PROMPT_FILE")" "$OUT"

    echo "Generated: $OUT"
    if [[ "$NO_OPEN" != true ]]; then
        if command -v xdg-open &>/dev/null; then
            xdg-open "$OUT" 2>/dev/null &
            echo "Opened in browser"
        elif command -v open &>/dev/null; then
            open "$OUT"
        else
            echo "No browser command found. Open manually: $OUT"
        fi
    fi

    # Also print CLI summary
    if [[ -n "$PAYLOAD_FILE" && -f "$PAYLOAD_FILE" ]]; then
        cmd_check --prompt "$PROMPT_FILE" --payload "$PAYLOAD_FILE"
    else
        cmd_check --prompt "$PROMPT_FILE"
    fi
}

case "${1:-help}" in
    review)  shift; cmd_review "$@" ;;
    check)   shift; cmd_check "$@" ;;
    rules)   cat "$SCRIPT_DIR/SKILL.md" ;;
    help|-h|--help) usage ;;
    *)       echo "Unknown command: $1"; usage; exit 1 ;;
esac
