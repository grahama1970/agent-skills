#!/bin/bash
#
# Ops-Claude - Claude Code maintenance and diagnostics
#
# Usage:
#   ./run.sh diagnose [--fix]    Full diagnostic report
#   ./run.sh status              Show current limits and usage
#   ./run.sh fix-inotify         Increase inotify limits (sudo)
#   ./run.sh fix-heap            Set NODE_OPTIONS for larger heap
#   ./run.sh clean-skills        Remove .venv/__pycache__ from skills
#   ./run.sh clean-cache         Clear Claude Code cache
#   ./run.sh clean-all           Clean everything
#   ./run.sh gitignore           Add .gitignore to all skills dirs
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ok() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERROR]${NC} $1"; }

show_help() {
    cat <<'EOF'
Ops-Claude - Claude Code maintenance and diagnostics

Usage:
  ops-claude diagnose [--fix]    Full diagnostic report with optional auto-fix
  ops-claude status              Show current limits and usage
  ops-claude fix-inotify         Increase inotify limits (requires sudo)
  ops-claude fix-heap            Set NODE_OPTIONS for larger heap
  ops-claude clean-skills        Remove .venv/__pycache__ from skills
  ops-claude clean-cache         Clear Claude Code cache
  ops-claude clean-all           Clean everything
  ops-claude gitignore           Add .gitignore to all skills directories

Common Issues:
  ENOSPC file watcher error  →  fix-inotify
  JavaScript heap OOM        →  clean-skills + fix-heap
  Claude hangs on startup    →  clean-cache

Examples:
  ./run.sh diagnose              # Check everything
  ./run.sh diagnose --fix        # Check and fix automatically
  ./run.sh status                # Quick status check
EOF
}

# Find all skills directories across all IDEs/CLIs
# Supports: .claude, .pi, .codex, .kilocode, .github, .gemini, .agent, .agents
find_skills_dirs() {
    {
        # User-level IDE directories
        for ide_dir in .claude .pi .codex .kilocode .github .gemini .agent .agents; do
            [[ -d "$HOME/$ide_dir/skills" ]] && echo "$HOME/$ide_dir/skills"
        done

        # Project-level skills directories
        find "$HOME/workspace" -maxdepth 4 \( \
            -path "*/.claude/skills" -o \
            -path "*/.pi/skills" -o \
            -path "*/.codex/skills" -o \
            -path "*/.kilocode/skills" -o \
            -path "*/.github/skills" -o \
            -path "*/.gemini/skills" -o \
            -path "*/.agent/skills" -o \
            -path "*/.agents/skills" -o \
            -name ".skills" \
        \) -type d 2>/dev/null

        # Git submodule skills (common pattern)
        find "$HOME/workspace" -path "*/.git/modules/.skills" -type d 2>/dev/null
    } | sort -u
}

cmd_status() {
    echo "=== Claude Code Resource Status ==="
    echo ""

    # inotify limits
    local max_watches=$(cat /proc/sys/fs/inotify/max_user_watches 2>/dev/null || echo "unknown")
    local max_instances=$(cat /proc/sys/fs/inotify/max_user_instances 2>/dev/null || echo "unknown")
    local used_instances=$(find /proc/*/fd -user "$(whoami)" -lname 'anon_inode:inotify' 2>/dev/null | wc -l)

    echo "inotify:"
    echo "  max_user_watches:    $max_watches"
    echo "  max_user_instances:  $max_instances"
    echo "  used_instances:      $used_instances"

    if [[ "$max_watches" -lt 524288 ]]; then
        warn "max_user_watches is low (< 524288)"
    else
        ok "max_user_watches is adequate"
    fi

    if [[ "$used_instances" -gt $((max_instances * 80 / 100)) ]]; then
        warn "inotify instances at ${used_instances}/${max_instances} (>80%)"
    else
        ok "inotify instances at ${used_instances}/${max_instances}"
    fi

    echo ""
    echo "NODE_OPTIONS: ${NODE_OPTIONS:-not set}"

    echo ""
    echo "Skills directories:"
    local total_files=0
    local total_size=0
    while IFS= read -r dir; do
        if [[ -d "$dir" ]]; then
            local count=$(find "$dir" -type f 2>/dev/null | wc -l)
            local size=$(du -sh "$dir" 2>/dev/null | cut -f1)
            echo "  $dir: $count files ($size)"
            total_files=$((total_files + count))
        fi
    done < <(find_skills_dirs)
    echo "  TOTAL: $total_files files"

    if [[ $total_files -gt 10000 ]]; then
        warn "Too many files in skills directories ($total_files > 10000)"
    else
        ok "File count is manageable"
    fi
}

cmd_diagnose() {
    local auto_fix=false
    [[ "$1" == "--fix" ]] && auto_fix=true

    echo "=== Claude Code Diagnostics ==="
    echo ""

    local issues=0

    # Check inotify
    local max_watches=$(cat /proc/sys/fs/inotify/max_user_watches 2>/dev/null || echo "0")
    if [[ "$max_watches" -lt 524288 ]]; then
        err "inotify max_user_watches too low: $max_watches"
        issues=$((issues + 1))
        if $auto_fix; then
            echo "  Fixing..."
            cmd_fix_inotify
        else
            echo "  Fix: ./run.sh fix-inotify"
        fi
    else
        ok "inotify max_user_watches: $max_watches"
    fi

    local max_instances=$(cat /proc/sys/fs/inotify/max_user_instances 2>/dev/null || echo "0")
    if [[ "$max_instances" -lt 1024 ]]; then
        err "inotify max_user_instances too low: $max_instances"
        issues=$((issues + 1))
    else
        ok "inotify max_user_instances: $max_instances"
    fi

    # Check for bloated skills dirs
    local total_files=0
    local venv_count=0
    local pycache_count=0

    while IFS= read -r dir; do
        if [[ -d "$dir" ]]; then
            local count=$(find "$dir" -type f 2>/dev/null | wc -l)
            total_files=$((total_files + count))
            venv_count=$((venv_count + $(find "$dir" -name ".venv" -type d 2>/dev/null | wc -l)))
            pycache_count=$((pycache_count + $(find "$dir" -name "__pycache__" -type d 2>/dev/null | wc -l)))
        fi
    done < <(find_skills_dirs)

    if [[ $total_files -gt 50000 ]]; then
        err "Too many files in skills: $total_files"
        issues=$((issues + 1))
        if $auto_fix; then
            echo "  Fixing..."
            cmd_clean_skills
        else
            echo "  Fix: ./run.sh clean-skills"
        fi
    elif [[ $total_files -gt 10000 ]]; then
        warn "Many files in skills: $total_files"
    else
        ok "Skills file count: $total_files"
    fi

    if [[ $venv_count -gt 0 ]]; then
        warn "Found $venv_count .venv directories in skills (should use uvx)"
        if $auto_fix; then
            cmd_clean_skills
        fi
    fi

    # Check NODE_OPTIONS
    if [[ -z "$NODE_OPTIONS" ]] || [[ ! "$NODE_OPTIONS" =~ max-old-space-size ]]; then
        warn "NODE_OPTIONS not set for larger heap"
        echo "  Fix: ./run.sh fix-heap"
    else
        ok "NODE_OPTIONS: $NODE_OPTIONS"
    fi

    # Check for .gitignore
    local missing_gitignore=0
    while IFS= read -r dir; do
        if [[ -d "$dir" ]] && [[ ! -f "$dir/.gitignore" ]]; then
            missing_gitignore=$((missing_gitignore + 1))
        fi
    done < <(find_skills_dirs)

    if [[ $missing_gitignore -gt 0 ]]; then
        warn "$missing_gitignore skills directories missing .gitignore"
        if $auto_fix; then
            cmd_gitignore
        else
            echo "  Fix: ./run.sh gitignore"
        fi
    else
        ok "All skills directories have .gitignore"
    fi

    echo ""
    if [[ $issues -eq 0 ]]; then
        ok "No critical issues found"
    else
        err "$issues issue(s) found"
        [[ "$auto_fix" == "false" ]] && echo "Run with --fix to auto-repair"
    fi
}

cmd_fix_inotify() {
    echo "Increasing inotify limits..."

    local current_watches=$(cat /proc/sys/fs/inotify/max_user_watches)
    local current_instances=$(cat /proc/sys/fs/inotify/max_user_instances)

    if [[ "$current_watches" -lt 1048576 ]]; then
        echo "Setting max_user_watches to 1048576 (was $current_watches)"
        echo "This requires sudo:"
        sudo sysctl -w fs.inotify.max_user_watches=1048576

        # Make permanent
        if ! grep -q "fs.inotify.max_user_watches" /etc/sysctl.conf 2>/dev/null; then
            echo "fs.inotify.max_user_watches=1048576" | sudo tee -a /etc/sysctl.conf
        fi
    fi

    if [[ "$current_instances" -lt 2048 ]]; then
        echo "Setting max_user_instances to 2048 (was $current_instances)"
        sudo sysctl -w fs.inotify.max_user_instances=2048

        if ! grep -q "fs.inotify.max_user_instances" /etc/sysctl.conf 2>/dev/null; then
            echo "fs.inotify.max_user_instances=2048" | sudo tee -a /etc/sysctl.conf
        fi
    fi

    ok "inotify limits updated"
}

cmd_fix_heap() {
    echo "Setting NODE_OPTIONS for larger heap..."

    local shell_rc=""
    if [[ -f "$HOME/.zshrc" ]]; then
        shell_rc="$HOME/.zshrc"
    elif [[ -f "$HOME/.bashrc" ]]; then
        shell_rc="$HOME/.bashrc"
    fi

    if [[ -n "$shell_rc" ]]; then
        if ! grep -q 'NODE_OPTIONS.*max-old-space-size' "$shell_rc" 2>/dev/null; then
            echo 'export NODE_OPTIONS="--max-old-space-size=8192"' >> "$shell_rc"
            ok "Added NODE_OPTIONS to $shell_rc"
            echo "Run: source $shell_rc"
        else
            ok "NODE_OPTIONS already set in $shell_rc"
        fi
    fi

    export NODE_OPTIONS="--max-old-space-size=8192"
    ok "NODE_OPTIONS set for current session"
}

cmd_clean_skills() {
    echo "Cleaning skills directories..."

    local removed_venv=0
    local removed_pycache=0
    local removed_pytest=0

    while IFS= read -r dir; do
        if [[ -d "$dir" ]]; then
            echo "  Cleaning $dir"

            # Remove .venv directories
            while IFS= read -r venv; do
                rm -rf "$venv" 2>/dev/null && removed_venv=$((removed_venv + 1))
            done < <(find "$dir" -name ".venv" -type d 2>/dev/null)

            # Remove __pycache__
            while IFS= read -r cache; do
                rm -rf "$cache" 2>/dev/null && removed_pycache=$((removed_pycache + 1))
            done < <(find "$dir" -name "__pycache__" -type d 2>/dev/null)

            # Remove .pytest_cache
            while IFS= read -r cache; do
                rm -rf "$cache" 2>/dev/null && removed_pytest=$((removed_pytest + 1))
            done < <(find "$dir" -name ".pytest_cache" -type d 2>/dev/null)
        fi
    done < <(find_skills_dirs)

    ok "Removed: $removed_venv .venv, $removed_pycache __pycache__, $removed_pytest .pytest_cache"
}

cmd_clean_cache() {
    echo "Cleaning Claude Code cache..."

    if [[ -d "$HOME/.claude/cache" ]]; then
        rm -rf "$HOME/.claude/cache"/*
        ok "Cleared ~/.claude/cache"
    fi

    if [[ -d "$HOME/.claude/_tmp" ]]; then
        rm -rf "$HOME/.claude/_tmp"/*
        ok "Cleared ~/.claude/_tmp"
    fi

    if [[ -d "$HOME/.claude/file-history" ]]; then
        # Keep recent, remove old
        find "$HOME/.claude/file-history" -type f -mtime +7 -delete 2>/dev/null
        ok "Cleaned old file-history entries"
    fi
}

cmd_clean_all() {
    cmd_clean_skills
    cmd_clean_cache
    ok "All caches cleaned"
}

cmd_gitignore() {
    echo "Adding .gitignore to skills directories..."

    local gitignore_content='# Python
__pycache__/
*.py[cod]
*$py.class
.venv/
venv/
*.egg-info/
.eggs/
dist/
build/

# Node
node_modules/

# IDE
.idea/
.vscode/
*.swp
*.swo

# Cache
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.log

# Data files
*.pdf
*.wav
*.mp3
*.mp4
*.zip
*.tar.gz
'

    local added=0
    while IFS= read -r dir; do
        if [[ -d "$dir" ]] && [[ ! -f "$dir/.gitignore" ]]; then
            echo "$gitignore_content" > "$dir/.gitignore"
            added=$((added + 1))
            echo "  Added: $dir/.gitignore"
        fi
    done < <(find_skills_dirs)

    ok "Added $added .gitignore files"
}

# Main dispatch
case "${1:-}" in
    diagnose)
        shift
        cmd_diagnose "$@"
        ;;
    status)
        cmd_status
        ;;
    fix-inotify)
        cmd_fix_inotify
        ;;
    fix-heap)
        cmd_fix_heap
        ;;
    clean-skills)
        cmd_clean_skills
        ;;
    clean-cache)
        cmd_clean_cache
        ;;
    clean-all)
        cmd_clean_all
        ;;
    gitignore)
        cmd_gitignore
        ;;
    -h|--help|help|"")
        show_help
        ;;
    *)
        echo "Unknown command: $1" >&2
        show_help
        exit 1
        ;;
esac
