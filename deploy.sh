#!/bin/bash
# Deploy agent skills and hooks to all AI agent directories
# Source: /home/graham/workspace/experiments/agent-skills
#
# Supports: Claude Code, Codex, Pi Agent (skills); Claude Code (hooks)
#
# Usage:
#   ./deploy.sh              # Deploy skills + hooks globally
#   ./deploy.sh --check      # Show what would be deployed
#   ./deploy.sh --skills     # Deploy only skills
#   ./deploy.sh --hooks      # Deploy only hooks

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/skills"
HOOKS_DIR="$SCRIPT_DIR/hooks"

# Agent directories
CLAUDE_SKILLS="$HOME/.claude/skills"
CLAUDE_HOOKS="$HOME/.claude/hooks"
CODEX_SKILLS="$HOME/.codex/skills"
PI_SKILLS="$HOME/.pi/agent/skills"

# Parse args
check_only=false
deploy_skills=true
deploy_hooks=true

for arg in "$@"; do
    case "$arg" in
        --check) check_only=true ;;
        --skills) deploy_hooks=false ;;
        --hooks) deploy_skills=false ;;
    esac
done

echo "=== Agent Skills & Hooks Deployment ==="
echo "Source: $SCRIPT_DIR"
echo ""

# Count items
skill_count=$(find "$SKILLS_DIR" -maxdepth 2 -name "SKILL.md" 2>/dev/null | wc -l)
hook_count=$(find "$HOOKS_DIR" -maxdepth 1 -name "*.sh" 2>/dev/null | wc -l)

echo "Skills found: $skill_count"
echo "Hooks found:  $hook_count"
echo ""

if $check_only; then
    echo "Skills to deploy:"
    for skill in "$SKILLS_DIR"/*/SKILL.md; do
        [[ -f "$skill" ]] && echo "  - $(basename $(dirname "$skill"))"
    done
    echo ""
    echo "Hooks to deploy:"
    for hook in "$HOOKS_DIR"/*.sh; do
        [[ -f "$hook" ]] && echo "  - $(basename "$hook")"
    done
    echo ""
    echo "Target locations:"
    echo "  Skills:"
    echo "    Claude Code: $CLAUDE_SKILLS"
    echo "    Codex:       $CODEX_SKILLS"
    echo "    Pi Agent:    $PI_SKILLS"
    echo "  Hooks:"
    echo "    Claude Code: $CLAUDE_HOOKS"
    exit 0
fi

# Helper function for symlink creation
create_symlink() {
    local source="$1"
    local target="$2"
    local name="$3"

    mkdir -p "$(dirname "$target")"

    if [[ -L "$target" ]]; then
        rm "$target"
    elif [[ -d "$target" ]]; then
        echo "  Warning: $target is a directory, backing up..."
        mv "$target" "${target}.bak.$(date +%s)"
    fi

    ln -s "$source" "$target"
    echo "  ✓ $name -> $target"
}

# Deploy skills
if $deploy_skills; then
    echo "Deploying skills..."
    create_symlink "$SKILLS_DIR" "$CLAUDE_SKILLS" "Claude Code skills"
    create_symlink "$SKILLS_DIR" "$CODEX_SKILLS" "Codex skills"
    create_symlink "$SKILLS_DIR" "$PI_SKILLS" "Pi Agent skills"
    echo ""
fi

# Deploy hooks
if $deploy_hooks; then
    echo "Deploying hooks..."
    create_symlink "$HOOKS_DIR" "$CLAUDE_HOOKS" "Claude Code hooks"
    echo ""
fi

echo "=== Deployment Complete ==="
echo ""
echo "Skills available globally for:"
echo "  - Claude Code (~/.claude/skills/)"
echo "  - Codex (~/.codex/skills/)"
echo "  - Pi Agent (~/.pi/agent/skills/)"
echo ""
echo "Hooks available for:"
echo "  - Claude Code (~/.claude/hooks/)"
echo ""
echo "Per-project setup (optional):"
echo "  # Skills"
echo "  ln -s $SKILLS_DIR .agents/skills"
echo "  ln -s ../.agents/skills .claude/skills"
echo ""
echo "  # Hooks (if project needs custom hooks)"
echo "  ln -s $HOOKS_DIR .claude/hooks"
