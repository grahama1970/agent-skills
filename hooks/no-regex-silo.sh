#!/bin/bash
# no-regex-silo: Block regex-based domain classification in Python files
#
# Fires on Edit/Write of .py files. Checks for patterns that indicate
# regex is being used to classify domain terms when ArangoDB should do it.
#
# This is NOT about banning `import re` — regex is fine for tokenization
# (splitting text into words). It's about catching the ANTI-PATTERN of
# using regex to decide what a token MEANS when the database already knows.
#
# Anti-patterns caught:
#   1. Hardcoded frozenset/set of domain terms (>10 entries)
#   2. re.compile patterns that classify entity types (ID_LIKE, CONTROL_ID, etc.)
#   3. Stopword lists > 50 entries (use BM25 analyzer instead)
#   4. Hand-rolled stemming/morphology functions
#   5. Files > 800 lines (best-practices-python)

INPUT=$(cat)
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.filePath // empty' 2>/dev/null)

# Only check Python files
[[ "$FILE" != *.py ]] && exit 0
[[ ! -f "$FILE" ]] && exit 0

WARNINGS=""

# 1. Large hardcoded frozensets/sets (domain knowledge that belongs in ArangoDB)
FROZENSET_SIZE=$(grep -cE '^\s+"[A-Z]' "$FILE" 2>/dev/null | head -1)
FROZENSET_BLOCKS=$(grep -n 'frozenset({' "$FILE" 2>/dev/null)
if [[ -n "$FROZENSET_BLOCKS" ]]; then
    while IFS= read -r line; do
        LINENO=$(echo "$line" | cut -d: -f1)
        # Count entries in this frozenset (lines with quoted strings until closing brace)
        ENTRIES=$(sed -n "${LINENO},/})/p" "$FILE" | grep -cE '"[^"]+"|'"'"'[^'"'"']+'"'"'')
        if [[ $ENTRIES -gt 10 ]]; then
            WARNINGS+="Line $LINENO: frozenset with $ENTRIES hardcoded entries. Domain knowledge belongs in ArangoDB, not Python code.\n"
        fi
    done <<< "$FROZENSET_BLOCKS"
fi

# 2. Regex patterns that classify entity types
if grep -qE 're\.compile.*\b(ID_LIKE|CONTROL_ID|CAP_PHRASE|ENTITY_RE|PATTERN_RE)' "$FILE" 2>/dev/null; then
    MATCH=$(grep -nE 're\.compile.*\b(ID_LIKE|CONTROL_ID|CAP_PHRASE|ENTITY_RE|PATTERN_RE)' "$FILE" | head -3)
    WARNINGS+="Regex used for entity classification — query ArangoDB instead:\n$MATCH\n"
fi

# 3. Stopword lists > 50 entries
STOP_BLOCKS=$(grep -n '_STOP_WORDS\|_STOP\s*=' "$FILE" 2>/dev/null)
if [[ -n "$STOP_BLOCKS" ]]; then
    while IFS= read -r line; do
        LINENO=$(echo "$line" | cut -d: -f1)
        ENTRIES=$(sed -n "${LINENO},/})/p" "$FILE" | grep -cE '"[^"]+"|'"'"'[^'"'"']+'"'"'')
        if [[ $ENTRIES -gt 50 ]]; then
            WARNINGS+="Line $LINENO: Stopword list with $ENTRIES entries. BM25's text_en analyzer handles stop words and IDF-based filtering already.\n"
        fi
    done <<< "$STOP_BLOCKS"
fi

# 4. Hand-rolled stemming
# Match function defs that are actually about stemming/morphology, not coincidental
# substring matches (e.g. "system" contains "stem", "ecosystem" contains "stem").
# Requires "stem" as a snake_case component (after _ or at name start), not mid-word.
# NOTE: "morpholog" is excluded here — it false-positives on image processing code
# (morphological open/close/erode/dilate are pixel operations, not NLP stemming).
# Instead we check morpholog separately with NLP-context filtering below.
STEM_PATTERN='def\s+(\w*_)?stem(_|\w*\()|def\s+stem(_|\w*\()|def\s+\w*_stemm|def\s+stemm|def\s+\w*_lemmatiz|def\s+lemmatiz|suffix.*strip.*"(ing|ed|er|ly|ment|tion|ness|ous)"|_word_in_corpus'
if grep -qP "$STEM_PATTERN" "$FILE" 2>/dev/null; then
    MATCH=$(grep -nP "$STEM_PATTERN" "$FILE" | head -3)
    WARNINGS+="Hand-rolled stemming/morphology detected — ArangoDB text_en analyzer already stems:\n$MATCH\n"
fi

# 4b. NLP-context morphology (not image processing)
# Only flag "morpholog" when it appears in NLP context (stemming, lemmatization, analysis),
# not when it's image processing (erode, dilate, open, close, kernel, pixel, cv2, contour).
if grep -qP 'morpholog' "$FILE" 2>/dev/null; then
    # Check if the file is image processing code — skip if so
    IS_IMAGE_PROCESSING=false
    if grep -qP 'cv2|erode|dilate|kernel|contour|threshold|structuring.?element|png_bytes|pixel|image.?processing' "$FILE" 2>/dev/null; then
        IS_IMAGE_PROCESSING=true
    fi
    if [[ "$IS_IMAGE_PROCESSING" == false ]]; then
        MATCH=$(grep -nP 'morpholog' "$FILE" | head -3)
        WARNINGS+="Hand-rolled morphological analysis detected — ArangoDB text_en analyzer already handles this:\n$MATCH\n"
    fi
fi

# 5. Direct graph_memory imports in evidence-case / skills code
# The embry-memory daemon wraps graph_memory. Skills MUST call the daemon
# via httpx Unix socket, NEVER import graph_memory directly.
# This is Claude's #1 regression — it instinctively imports the module
# instead of calling the service. HARD BLOCK.
if echo "$FILE" | grep -qE 'create-evidence-case|evidence-case-lab|evidence-case-viewer'; then
    if grep -qE '^from graph_memory|^import graph_memory' "$FILE" 2>/dev/null; then
        MATCH=$(grep -nE '^from graph_memory|^import graph_memory' "$FILE" | head -5)
        WARNINGS+="HARD BLOCK: Direct graph_memory import in evidence-case code.\n"
        WARNINGS+="$MATCH\n"
        WARNINGS+="Call the embry-memory daemon via httpx Unix socket instead.\n"
        WARNINGS+="Socket: /run/user/1000/embry/memory.sock\n"
        WARNINGS+="Pattern: httpx.HTTPTransport(uds=socket) → client.post('/recall', json={...})\n"
        WARNINGS+="Tests: embry-os/services/memory-daemon/tests/test_daemon_endpoints.py\n"
    fi
fi

# 6. File length > 800 lines
LINECOUNT=$(wc -l < "$FILE")
if [[ $LINECOUNT -gt 800 ]]; then
    WARNINGS+="File is $LINECOUNT lines (max 800 per best-practices-python). Split into focused modules.\n"
fi

# Report
if [[ -n "$WARNINGS" ]]; then
    cat >&2 <<EOF

==== NO-REGEX-SILO HOOK ====
File: $FILE

$WARNINGS
RULE: Domain classification belongs in ArangoDB, not regex.
- "Is this a control ID?" → exact match query on sparta_controls
- "Is this in our domain?" → hybrid_search_sparta_qra()
- "Did they misspell this?" → rapidfuzz against domain vocabulary from ArangoDB
- Regex is ONLY for tokenization (splitting text into words)

See: MEMORY.md "No Regex for What the Database Already Does"
============================

EOF
    # Exit 2 = block and show message to Claude
    exit 2
fi

exit 0
