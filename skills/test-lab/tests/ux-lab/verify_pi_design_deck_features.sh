#!/usr/bin/env bash
# Blind adversarial tests for ux-lab pi-design-deck feature adoption
# The coding agent NEVER sees this file — only pass/fail output.
set -euo pipefail

BRIDGE="/home/graham/workspace/experiments/open-pencil/src/automation/bridge.ts"
SKILL_DIR="/home/graham/.claude/skills/ux-lab"
RUN_SH="$SKILL_DIR/run.sh"
SKILL_MD="$SKILL_DIR/SKILL.md"
GALLERY_DIR="$SKILL_DIR/references/component-gallery"

PASS=0
FAIL=0
RESULTS=()

check_grep() {
    local id="$1" desc="$2" pattern="$3" file="$4"
    if grep -qE "$pattern" "$file" 2>/dev/null; then
        RESULTS+=("PASS [$id] $desc")
        PASS=$((PASS + 1))
    else
        RESULTS+=("FAIL [$id] $desc")
        FAIL=$((FAIL + 1))
    fi
}

check_not_grep() {
    local id="$1" desc="$2" pattern="$3" file="$4"
    if ! grep -qE "$pattern" "$file" 2>/dev/null; then
        RESULTS+=("PASS [$id] $desc")
        PASS=$((PASS + 1))
    else
        RESULTS+=("FAIL [$id] $desc")
        FAIL=$((FAIL + 1))
    fi
}

check_file_exists() {
    local id="$1" desc="$2" path="$3"
    if [[ -f "$path" ]]; then
        RESULTS+=("PASS [$id] $desc")
        PASS=$((PASS + 1))
    else
        RESULTS+=("FAIL [$id] $desc")
        FAIL=$((FAIL + 1))
    fi
}

check_line_count_min() {
    local id="$1" desc="$2" path="$3" min="$4"
    local count
    count=$(wc -l < "$path" 2>/dev/null || echo 0)
    if (( count >= min )); then
        RESULTS+=("PASS [$id] $desc (${count} lines)")
        PASS=$((PASS + 1))
    else
        RESULTS+=("FAIL [$id] $desc (${count} < ${min} lines)")
        FAIL=$((FAIL + 1))
    fi
}

echo "=== UX-Lab Pi-Design-Deck Feature Adoption Blind Tests ==="
echo ""

# ─── Feature 1: SSE Event Stream ─────────────────────────────────────────

echo "--- Feature 1: SSE Event Stream ---"

check_grep "SSE.1" "bridge.ts has sseClients set" \
    "sseClients.*=.*new Set" "$BRIDGE"

check_grep "SSE.2" "bridge.ts has GET /events endpoint" \
    "app\.get\('/events'" "$BRIDGE"

check_grep "SSE.3" "bridge.ts SSE uses text/event-stream content type" \
    "text/event-stream" "$BRIDGE"

check_grep "SSE.4" "bridge.ts SSE sends connected event on init" \
    "type.*:.*connected" "$BRIDGE"

check_grep "SSE.5" "bridge.ts SSE cleans up on abort signal" \
    "sseClients.delete" "$BRIDGE"

check_grep "SSE.6" "bridge.ts broadcasts ops to SSE clients" \
    "for.*const client of sseClients" "$BRIDGE"

check_grep "SSE.7" "run.sh has events command" \
    "events\)" "$RUN_SH"

check_grep "SSE.8" "run.sh events uses curl with SSE streaming" \
    "curl.*-N.*/events" "$RUN_SH"

check_grep "SSE.9" "SKILL.md documents SSE event stream" \
    "SSE event stream" "$SKILL_MD"

# ─── Feature 2: Session Snapshots ─────────────────────────────────────────

echo "--- Feature 2: Session Snapshots ---"

check_grep "SNAP.1" "bridge.ts has SNAPSHOT_DIR at ~/.config/open-pencil/snapshots" \
    "SNAPSHOT_DIR.*open-pencil.*snapshots" "$BRIDGE"

check_grep "SNAP.2" "bridge.ts has POST /snapshots endpoint (save)" \
    "app\.post\('/snapshots'" "$BRIDGE"

check_grep "SNAP.3" "bridge.ts has GET /snapshots endpoint (list)" \
    "app\.get\('/snapshots'" "$BRIDGE"

check_grep "SNAP.4" "bridge.ts has GET /snapshots/:id endpoint (get specific)" \
    "app\.get\('/snapshots/:id'" "$BRIDGE"

check_grep "SNAP.5" "bridge.ts writes snapshots with UUID" \
    "crypto\.randomUUID" "$BRIDGE"

check_grep "SNAP.6" "bridge.ts creates snapshot dir recursively" \
    "mkdirSync.*SNAPSHOT_DIR.*recursive" "$BRIDGE"

check_grep "SNAP.7" "run.sh has snapshots command" \
    "snapshots\)" "$RUN_SH"

check_grep "SNAP.8" "run.sh has snapshot-save command" \
    "snapshot-save\)" "$RUN_SH"

check_grep "SNAP.9" "run.sh has snapshot-load command" \
    "snapshot-load\)" "$RUN_SH"

check_grep "SNAP.10" "SKILL.md documents session snapshots" \
    "Session snapshots" "$SKILL_MD"

# ─── Feature 3: Generate-More Loop ───────────────────────────────────────

echo "--- Feature 3: Generate-More Loop ---"

check_grep "GEN.1" "bridge.ts has generateMoreRequests queue" \
    "generateMoreRequests" "$BRIDGE"

check_grep "GEN.2" "bridge.ts has POST /generate-more endpoint" \
    "app\.post\('/generate-more'" "$BRIDGE"

check_grep "GEN.3" "bridge.ts drains generate-more on RPC response" \
    "generateMoreRequests.splice" "$BRIDGE"

check_grep "GEN.4" "bridge.ts piggybacks generateMore on RPC response" \
    "response\.generateMore|pending_generates" "$BRIDGE"

check_grep "GEN.5" "bridge.ts sends generate-more events to SSE" \
    "generate-more" "$BRIDGE"

check_grep "GEN.6" "SKILL.md documents generate-more loop" \
    "Generate-more loop|generate-more" "$SKILL_MD"

check_grep "GEN.7" "SKILL.md enforces prompt-lab validation for generate-more" \
    "MUST.*prompt-lab|validated by.*prompt-lab" "$SKILL_MD"

# ─── Feature 4: Component Gallery ────────────────────────────────────────

echo "--- Feature 4: Component Gallery ---"

check_file_exists "GAL.1" "INDEX.md exists" \
    "$GALLERY_DIR/INDEX.md"

check_file_exists "GAL.2" "LOOKUP.md exists" \
    "$GALLERY_DIR/LOOKUP.md"

check_file_exists "GAL.3" "actions.md component file exists" \
    "$GALLERY_DIR/components/actions.md"

check_file_exists "GAL.4" "navigation.md component file exists" \
    "$GALLERY_DIR/components/navigation.md"

check_file_exists "GAL.5" "inputs.md component file exists" \
    "$GALLERY_DIR/components/inputs.md"

check_file_exists "GAL.6" "data-display.md component file exists" \
    "$GALLERY_DIR/components/data-display.md"

check_file_exists "GAL.7" "feedback.md component file exists" \
    "$GALLERY_DIR/components/feedback.md"

check_file_exists "GAL.8" "overlays.md component file exists" \
    "$GALLERY_DIR/components/overlays.md"

check_file_exists "GAL.9" "layout.md component file exists" \
    "$GALLERY_DIR/components/layout.md"

# Verify gallery has actual content (not stubs)
check_line_count_min "GAL.10" "LOOKUP.md has 45+ term entries" \
    "$GALLERY_DIR/LOOKUP.md" 50

check_grep "GAL.11" "LOOKUP.md has NVIS token references" \
    "nvis|NVIS" "$GALLERY_DIR/LOOKUP.md"

check_grep "GAL.12" "INDEX.md has 7 category table entries" \
    "actions|navigation|inputs|data-display|feedback|overlays|layout" "$GALLERY_DIR/INDEX.md"

check_grep "GAL.13" "run.sh has gallery command" \
    "gallery\)" "$RUN_SH"

check_grep "GAL.14" "SKILL.md documents component gallery" \
    "[Cc]omponent gallery" "$SKILL_MD"

# ─── Feature 5: /memory Integration ──────────────────────────────────────

echo "--- Feature 5: /memory Integration ---"

check_grep "MEM.1" "run.sh has memory-save command" \
    "memory-save\)" "$RUN_SH"

check_grep "MEM.2" "run.sh has memory-list command" \
    "memory-list\)" "$RUN_SH"

check_grep "MEM.3" "run.sh references embry-memory socket" \
    "embry-memory.sock|MEMORY_SOCKET" "$RUN_SH"

check_grep "MEM.4" "SKILL.md documents /memory integration" \
    "/memory integration|memory-save|memory-list" "$SKILL_MD"

check_grep "MEM.5" "SKILL.md composes memory skill" \
    "memory" "$SKILL_MD"

# ─── Feature 6: Prompt Validation Rule ───────────────────────────────────

echo "--- Feature 6: Prompt Validation Rule ---"

check_grep "PROMPT.1" "SKILL.md composes prompt-lab" \
    "prompt-lab" "$SKILL_MD"

check_grep "PROMPT.2" "SKILL.md enforces MUST for prompt validation" \
    "MUST.*prompt-lab|MUST be validated" "$SKILL_MD"

check_grep "PROMPT.3" "SKILL.md says no bespoke prompts" \
    "no bespoke prompts" "$SKILL_MD"

# ─── Cross-Cutting: SKILL.md Composition Declarations ────────────────────

echo "--- Cross-Cutting: Composition ---"

check_grep "COMP.1" "SKILL.md composes list includes prompt-lab" \
    "prompt-lab" "$SKILL_MD"

check_grep "COMP.2" "SKILL.md composes list includes memory" \
    "memory" "$SKILL_MD"

# ─── Report ──────────────────────────────────────────────────────────────

echo ""
echo "=== Results ==="
for r in "${RESULTS[@]}"; do
    echo "  $r"
done
echo ""
echo "TOTAL: $PASS passed, $FAIL failed out of $((PASS + FAIL)) checks"

if (( FAIL > 0 )); then
    exit 1
else
    echo "ALL CHECKS PASSED"
    exit 0
fi
