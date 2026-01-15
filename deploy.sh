#!/bin/bash
# Deploy skills to all AI agent skill directories
# Source: /home/graham/workspace/experiments/agent-skills
#
# Supports: Claude Code, Codex, Antigravity
#
# Usage:
#   ./deploy.sh           # Deploy to global locations
#   ./deploy.sh --check   # Show what would be deployed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR"

# Agent skill directory locations
CLAUDE_GLOBAL="$HOME/.claude/skills"
CODEX_GLOBAL="$HOME/.codex/skills"

check_only=false
[[ "${1:-}" == "--check" ]] && check_only=true

echo "=== Agent Skills Deployment ==="
echo "Source: $SKILLS_DIR"
echo ""

# Count skills (directories with SKILL.md)
skill_count=$(find "$SKILLS_DIR" -maxdepth 2 -name "SKILL.md" | wc -l)
echo "Skills found: $skill_count"
echo ""

if $check_only; then
    echo "Skills to deploy:"
    for skill in "$SKILLS_DIR"/*/SKILL.md; do
        [[ -f "$skill" ]] && echo "  - $(basename $(dirname "$skill"))"
    done
    echo ""
    echo "Target locations:"
    echo "  Claude Code: $CLAUDE_GLOBAL"
    echo "  Codex:       $CODEX_GLOBAL"
    exit 0
fi

# Deploy to Claude Code
echo "Deploying to Claude Code..."
mkdir -p "$(dirname "$CLAUDE_GLOBAL")"
if [[ -L "$CLAUDE_GLOBAL" ]]; then
    rm "$CLAUDE_GLOBAL"
elif [[ -d "$CLAUDE_GLOBAL" ]]; then
    echo "  Warning: $CLAUDE_GLOBAL is a directory, backing up..."
    mv "$CLAUDE_GLOBAL" "${CLAUDE_GLOBAL}.bak.$(date +%s)"
fi
ln -s "$SKILLS_DIR" "$CLAUDE_GLOBAL"
echo "  ✓ Symlinked to $CLAUDE_GLOBAL"

# Deploy to Codex
echo "Deploying to Codex..."
mkdir -p "$(dirname "$CODEX_GLOBAL")"
if [[ -L "$CODEX_GLOBAL" ]]; then
    rm "$CODEX_GLOBAL"
elif [[ -d "$CODEX_GLOBAL" ]]; then
    echo "  Warning: $CODEX_GLOBAL is a directory, backing up..."
    mv "$CODEX_GLOBAL" "${CODEX_GLOBAL}.bak.$(date +%s)"
fi
ln -s "$SKILLS_DIR" "$CODEX_GLOBAL"
echo "  ✓ Symlinked to $CODEX_GLOBAL"

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Skills are now available globally for:"
echo "  - Claude Code (any project)"
echo "  - Codex (any project)"
echo "  - Antigravity (via .agents/skills symlink per project)"
echo ""
echo "Per-project setup (optional):"
echo "  ln -s $SKILLS_DIR .agents/skills"
echo "  ln -s ../.agents/skills .claude/skills"
echo "  ln -s ../.agents/skills .codex/skills"
