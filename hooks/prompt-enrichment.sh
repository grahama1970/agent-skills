#!/bin/bash
set -euo pipefail
# Prompt Enrichment & Triage Hook
#
# Fires on: UserPromptSubmit (every prompt, before Claude processes it)
# Purpose: Classify prompt complexity and inject appropriate ceremony level
#
# Triage levels:
#   CHAT     - Questions, discussions, no code (no ceremony)
#   SIMPLE   - Quick code fixes, reads, small edits (light reminders)
#   COMPLEX  - Multi-file refactors, new features, architecture (full pipeline)
#   RESEARCH - Deep research tasks (memory + dogpile)
#
# Does NOT block prompts. Only injects additionalContext.

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty' 2>/dev/null)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."' 2>/dev/null)

[[ -z "$PROMPT" ]] && exit 0

# ─────────────────────────────────────────────────────────────
# TRIAGE: Classify prompt complexity
# ─────────────────────────────────────────────────────────────

WORD_COUNT=$(echo "$PROMPT" | wc -w)
LEVEL="CHAT"

# Detect explicit skill references — must start with / and have a hyphen (not URLs)
HAS_SKILL_REF=false
echo "$PROMPT" | grep -qE '(^|[[:space:]])/[a-z]+-[a-z]+' && HAS_SKILL_REF=true

# Code action indicators — require imperative verb + technical context
# Narrower than before: "add a comment" won't trigger, but "add a function to parser.py" will
HAS_CODE_WORDS=false
echo "$PROMPT" | grep -qiE '\b(fix|refactor|implement|migrate|debug|deploy|split|merge)\b' && HAS_CODE_WORDS=true
# "add/create/build/write/modify/change/delete/remove/update/test" only count if paired with code context
if [[ "$HAS_CODE_WORDS" == "false" ]]; then
    echo "$PROMPT" | grep -qiE '\b(add|create|build|write|modify|change|delete|remove|update|test)\b.*(function|class|method|file|module|service|endpoint|route|hook|skill|component|test|api|handler|model)' && HAS_CODE_WORDS=true
fi

# File/path indicators — require file extension (not bare paths)
HAS_FILE_REFS=false
echo "$PROMPT" | grep -qE '\b[a-zA-Z0-9_/-]+\.(py|rs|ts|tsx|js|jsx|sh|toml|json|yaml|qml)\b' && HAS_FILE_REFS=true

# Architecture/complexity indicators
HAS_ARCH_WORDS=false
echo "$PROMPT" | grep -qiE '\b(architect|design|pipeline|system|service|daemon|schema|migration|overhaul|rewrite|restructure|comprehensive)\b' && HAS_ARCH_WORDS=true

# Research indicators
HAS_RESEARCH_WORDS=false
echo "$PROMPT" | grep -qiE '\b(research|investigate|explore|compare|benchmark|evaluate|assess|analyze|study|deep dive|dogpile|best practices)\b' && HAS_RESEARCH_WORDS=true

# Skills-related
HAS_SKILLS_REF=false
echo "$PROMPT" | grep -qiE '\bskill|SKILL\.md|skills-ci|\.pi/skills' && HAS_SKILLS_REF=true

# UI/UX indicators
HAS_UI_WORDS=false
echo "$PROMPT" | grep -qiE '\b(ui|ux|interface|component|layout|design|screen|widget|button|form|modal|dialog|sidebar|navbar|theme|style|css|tailwind|shadcn|react|qml|frontend)\b' && HAS_UI_WORDS=true
# Require UI word + action word to avoid false positives on discussions
IS_UI_TASK=false
if [[ "$HAS_UI_WORDS" == "true" ]] && [[ "$HAS_CODE_WORDS" == "true" ]]; then
    IS_UI_TASK=true
fi

# Prompt/LLM authoring indicators
IS_PROMPT_TASK=false
echo "$PROMPT" | grep -qiE '\b(prompt|system message|few.shot|chain.of.thought|llm instruction|system prompt|user prompt|assistant prompt)\b' && IS_PROMPT_TASK=true
# Also detect prompt-lab references
echo "$PROMPT" | grep -qiE '/prompt-lab' && IS_PROMPT_TASK=true

# Classify
if [[ "$IS_PROMPT_TASK" == "true" ]]; then
    LEVEL="PROMPT"
elif [[ "$IS_UI_TASK" == "true" ]]; then
    LEVEL="UI"
elif [[ "$HAS_ARCH_WORDS" == "true" ]] && { [[ "$HAS_CODE_WORDS" == "true" ]] || [[ $WORD_COUNT -gt 30 ]]; }; then
    LEVEL="COMPLEX"
elif [[ "$HAS_RESEARCH_WORDS" == "true" ]] && [[ "$HAS_CODE_WORDS" == "false" ]]; then
    LEVEL="RESEARCH"
elif [[ "$HAS_CODE_WORDS" == "true" ]] || [[ "$HAS_FILE_REFS" == "true" ]] || [[ "$HAS_SKILL_REF" == "true" ]]; then
    LEVEL="SIMPLE"
fi

# Upgrade to COMPLEX if multiple signals present
SIGNAL_COUNT=0
[[ "$HAS_CODE_WORDS" == "true" ]] && SIGNAL_COUNT=$((SIGNAL_COUNT + 1))
[[ "$HAS_FILE_REFS" == "true" ]] && SIGNAL_COUNT=$((SIGNAL_COUNT + 1))
[[ "$HAS_ARCH_WORDS" == "true" ]] && SIGNAL_COUNT=$((SIGNAL_COUNT + 1))
[[ "$HAS_SKILLS_REF" == "true" ]] && SIGNAL_COUNT=$((SIGNAL_COUNT + 1))
[[ $WORD_COUNT -gt 50 ]] && SIGNAL_COUNT=$((SIGNAL_COUNT + 1))

if [[ "$LEVEL" == "SIMPLE" ]] && [[ $SIGNAL_COUNT -ge 3 ]]; then
    LEVEL="COMPLEX"
fi

# ─────────────────────────────────────────────────────────────
# MEMORY RECALL: Invoke /memory recall for code/research tasks
# Returns prior solutions via BM25 + semantic + graph traversal
# ─────────────────────────────────────────────────────────────

MEMORY_CONTEXT=""
if [[ "$LEVEL" != "CHAT" ]] && [[ "$LEVEL" != "" ]]; then
    MEMORY_SKILL="$HOME/workspace/experiments/pi-mono/.pi/skills/memory/run.sh"
    if [[ -x "$MEMORY_SKILL" ]]; then
        # Truncate prompt to first 200 chars for query (avoid shell escaping issues)
        QUERY=$(echo "$PROMPT" | head -c 200 | tr -d '"' | tr '\n' ' ')
        MEMORY_RESULT=$(timeout 8 "$MEMORY_SKILL" recall --q "$QUERY" --k 3 2>/dev/null || echo '{"results":[]}')

        # Check if memory found anything
        FOUND_COUNT=$(echo "$MEMORY_RESULT" | jq -r '.results | length' 2>/dev/null || echo "0")
        if [[ "$FOUND_COUNT" -gt 0 ]]; then
            # Extract summaries from results
            MEMORY_CONTEXT="MEMORY RECALL found $FOUND_COUNT prior solution(s):\n"
            MEMORY_CONTEXT+=$(echo "$MEMORY_RESULT" | jq -r '.results[] | "  - [\(.confidence // "?")] \(.problem // .question // .title // "untitled"): \(.solution // .answer // .summary // "no summary")[0:200]"' 2>/dev/null | head -5)
            MEMORY_CONTEXT+="\n"
        fi
    fi
fi

# ─────────────────────────────────────────────────────────────
# BUILD CONTEXT based on triage level
# ─────────────────────────────────────────────────────────────

CONTEXT=""

# ─────────────────────────────────────────────────────────────
# HARD RULES (injected on EVERY non-CHAT prompt)
# These exist because Claude repeatedly violates them.
# ─────────────────────────────────────────────────────────────

HARD_RULES="HARD RULES — NO EXCEPTIONS:\n"
HARD_RULES+="- NO new regex classifiers. NO bespoke AQL. NO new daemon endpoints. NO graph_memory imports.\n"
HARD_RULES+="- ALL code goes in /home/graham/workspace/experiments/memory/. Nowhere else. Ever.\n"
HARD_RULES+="- Use EXISTING daemon endpoints via httpx Unix socket. If it can't be done with /recall, /learn, /clarify, /intent, /store, /analytics/run, /taxonomy/* — ask Graham.\n"

case "$LEVEL" in
    CHAT)
        # No ceremony needed for conversations/questions
        exit 0
        ;;

    SIMPLE)
        CONTEXT+="[TRIAGE: SIMPLE — light verification applies]\n"
        CONTEXT+="$HARD_RULES"
        if [[ -n "$MEMORY_CONTEXT" ]]; then
            CONTEXT+="$MEMORY_CONTEXT"
        else
            CONTEXT+="- MEMORY FIRST: Check /memory recall for prior solutions before scanning code.\n"
        fi

        # Add best-practices reminders based on likely file types
        if echo "$PROMPT" | grep -qiE 'python|\.py|arango|aql'; then
            CONTEXT+="- Consult /best-practices-python and /best-practices-arangodb if modifying those files.\n"
        fi
        if [[ "$HAS_SKILLS_REF" == "true" ]]; then
            CONTEXT+="- NON-NEGOTIABLE: Run /skills-ci scan BEFORE starting (baseline) and AFTER finishing.\n"
        fi
        ;;

    COMPLEX)
        CONTEXT+="[TRIAGE: COMPLEX — full pipeline required]\n"
        CONTEXT+="$HARD_RULES\n"
        if [[ -n "$MEMORY_CONTEXT" ]]; then
            CONTEXT+="$MEMORY_CONTEXT\n"
        fi
        CONTEXT+="MANDATORY WORKFLOW for complex tasks:\n"
        CONTEXT+="1. /memory recall — Check if this problem has been solved before\n"
        CONTEXT+="2. /plan — Create a structured task file with verification criteria\n"
        CONTEXT+="3. /review-plan — Validate the plan before executing\n"
        CONTEXT+="4. /orchestrate — Execute the plan with quality gates\n"
        CONTEXT+="5. /test-lab — Adversarial blind testing before declaring done\n"
        CONTEXT+="\n"
        CONTEXT+="OPTIONAL (use when needed):\n"
        CONTEXT+="- /interview — If requirements are ambiguous, ask the human\n"
        CONTEXT+="- /dogpile — If you need deep research on unfamiliar topics\n"
        CONTEXT+="\n"
        CONTEXT+="NON-NEGOTIABLE:\n"
        CONTEXT+="- Consult relevant /best-practices-* skills before modifying code\n"
        if [[ "$HAS_SKILLS_REF" == "true" ]]; then
            CONTEXT+="- Run /skills-ci scan BEFORE (baseline) and AFTER (verify no regressions)\n"
        fi
        CONTEXT+="- Produce VERIFIABLE evidence (actual command output), not aspirational status tables\n"
        CONTEXT+="- The verification gate WILL check your work at session end. Claims without evidence will be blocked.\n"
        ;;

    RESEARCH)
        CONTEXT+="[TRIAGE: RESEARCH — investigation mode]\n"
        CONTEXT+="$HARD_RULES"
        if [[ -n "$MEMORY_CONTEXT" ]]; then
            CONTEXT+="$MEMORY_CONTEXT\n"
        fi
        CONTEXT+="1. /memory recall — Check what we already know about this topic\n"
        CONTEXT+="2. /dogpile — Deep multi-source search if memory is insufficient\n"
        CONTEXT+="3. /memory learn — Store findings for future sessions\n"
        ;;

    UI)
        CONTEXT+="[TRIAGE: UI/UX — design verification required]\n"
        CONTEXT+="$HARD_RULES\n"
        if [[ -n "$MEMORY_CONTEXT" ]]; then
            CONTEXT+="$MEMORY_CONTEXT\n"
        fi
        CONTEXT+="MANDATORY WORKFLOW for UI/UX tasks:\n"
        CONTEXT+="1. /memory recall — Check prior design decisions and patterns\n"
        CONTEXT+="2. Consult /best-practices-react (or /best-practices-kde for QML)\n"
        CONTEXT+="3. Implement the UI changes\n"
        CONTEXT+="4. BLOCKING: /review-design — Screenshot-based design review BEFORE declaring done\n"
        CONTEXT+="5. BLOCKING: /test-interactions — Systematic interaction testing\n"
        CONTEXT+="\n"
        CONTEXT+="DO NOT skip steps 4-5. UI work without visual verification produces invisible regressions.\n"
        ;;

    PROMPT)
        CONTEXT+="[TRIAGE: PROMPT — /prompt-lab mandatory]\n"
        CONTEXT+="$HARD_RULES\n"
        if [[ -n "$MEMORY_CONTEXT" ]]; then
            CONTEXT+="$MEMORY_CONTEXT\n"
        fi
        CONTEXT+="BLOCKING: ALL LLM prompts MUST go through /prompt-lab.\n"
        CONTEXT+="- NO hand-writing prompts in Python string literals\n"
        CONTEXT+="- NO inline system messages without /prompt-lab evaluation\n"
        CONTEXT+="- /prompt-lab iterates, evaluates, and version-controls prompts\n"
        CONTEXT+="- Hand-written prompts silently degrade LLM output quality\n"
        ;;
esac

# ─────────────────────────────────────────────────────────────
# OUTPUT
# ─────────────────────────────────────────────────────────────

if [[ -n "$CONTEXT" ]]; then
    jq -n --arg ctx "$(echo -e "$CONTEXT")" '{
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": $ctx
        }
    }'
else
    exit 0
fi
