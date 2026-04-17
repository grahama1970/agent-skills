#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

# =============================================================================
# skills-broadcast: Symlink-based skill sharing
#
# CANONICAL SOURCE: ~/workspace/experiments/agent-skills/skills (GitHub repo)
# All IDE/project skill directories become symlinks pointing TO canonical.
#
# To edit skills: edit directly in agent-skills repo, then git commit/push.
# Changes propagate instantly to all projects via symlinks.
#
# This replaces the old rsync-based approach which:
#   - Duplicated ~300GB of data across targets
#   - Required complex exclusion lists
#   - Caused the 2026-02-11 deletion incident via --delete
#   - Required manual "push" to propagate changes
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Canonical is the agent-skills GitHub repo
CANONICAL_DIR="$HOME/workspace/experiments/agent-skills/skills"
REGISTRY_FILE="$HOME/.agent_skills_targets"

# Validate canonical has enough skills to be trustworthy
MIN_SKILLS=20

usage() {
    cat <<USAGE
Usage: ${0##*/} [link|status|info|cleanup|git-commit|register|unregister|targets|push|pull] [--dry-run]

Symlink-based skill sharing. Canonical source: $CANONICAL_DIR (GitHub repo)

Commands:
  link              Create symlinks at all targets (main operation)
  status            Show all targets and their link state
  info              Alias for status
  cleanup           Delete .pre-symlink-* backup directories to reclaim disk space
  git-commit        Commit and push changes in canonical agent-skills repo
  register [PATH]   Add a project to the target registry
  unregister [PATH] Remove a project from the target registry
  targets           List registered projects

Legacy aliases (map to 'link' for backwards compatibility):
  push              Same as 'link'
  pull              Same as 'link'
  git-sync          Same as 'git-commit' (deprecated name)

Options:
  --dry-run, -n     Preview what would be done
  -h, --help        Show this help
USAGE
}

MODE="link"
DRY_RUN=0

if [[ $# -gt 0 ]]; then
    case "$1" in
        link|status|info|find|cleanup|register|unregister|targets)
            MODE="$1"
            shift ;;
        git-commit|git-sync)
            # git-sync is deprecated name for git-commit
            MODE="git-commit"
            shift ;;
        push|pull)
            # Backwards compat: push/pull now just create symlinks
            MODE="link"
            shift ;;
        -h|--help)
            usage; exit 0 ;;
        --dry-run|-n)
            DRY_RUN=1; shift ;;
        *) usage; exit 1 ;;
    esac
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run|-n) DRY_RUN=1 ;;
        -h|--help) usage; exit 0 ;;
        -*) echo "Unknown option: $1" >&2; usage; exit 1 ;;
        *) break ;;
    esac
    shift
done

# ── Register / Unregister ────────────────────────────────────────────────────

if [[ "$MODE" == "register" ]]; then
    target="${1:-.}"
    abs_target=$(cd "$target" && pwd)
    touch "$REGISTRY_FILE"
    if grep -Fxq "$abs_target" "$REGISTRY_FILE"; then
        echo "Already registered: $abs_target"
    else
        echo "$abs_target" >> "$REGISTRY_FILE"
        sort -u "$REGISTRY_FILE" -o "$REGISTRY_FILE"
        echo "Registered: $abs_target"
    fi
    exit 0
fi

if [[ "$MODE" == "unregister" ]]; then
    target="${1:-.}"
    abs_target=$(cd "$target" 2>/dev/null && pwd || realpath -m "$target")
    if [[ -f "$REGISTRY_FILE" ]] && grep -Fxq "$abs_target" "$REGISTRY_FILE"; then
        grep -Fvx "$abs_target" "$REGISTRY_FILE" > "${REGISTRY_FILE}.tmp"
        mv "${REGISTRY_FILE}.tmp" "$REGISTRY_FILE"
        echo "Unregistered: $abs_target"
    else
        echo "Not in registry: $abs_target"
    fi
    exit 0
fi

if [[ "$MODE" == "targets" ]]; then
    if [[ -f "$REGISTRY_FILE" ]]; then
        cat "$REGISTRY_FILE"
    else
        echo "No registered projects."
    fi
    exit 0
fi

# ── Cleanup ─────────────────────────────────────────────────────────────────

if [[ "$MODE" == "cleanup" ]]; then
    echo "=== Skills Broadcast Cleanup ==="
    echo ""
    echo "Scanning for .pre-symlink-* backup directories..."
    echo ""

    total_bytes=0
    count=0
    declare -a BACKUP_DIRS=()

    # Scan home dir patterns
    while IFS= read -r bdir; do
        [[ -z "$bdir" ]] && continue
        size_mb=$(du -sm "$bdir" 2>/dev/null | cut -f1)
        echo "  ${size_mb}MB  $bdir"
        total_bytes=$((total_bytes + size_mb))
        count=$((count + 1))
        BACKUP_DIRS+=("$bdir")
    done < <(find "$HOME" -maxdepth 5 -name "*.pre-symlink-*" -type d 2>/dev/null)

    echo ""
    if [[ $count -eq 0 ]]; then
        echo "No backup directories found. Nothing to clean up."
        exit 0
    fi

    total_gb=$(awk "BEGIN {printf \"%.1f\", $total_bytes / 1024}")
    echo "Found $count backup dirs totaling ${total_gb}GB"
    echo ""

    if [[ $DRY_RUN -eq 1 ]]; then
        echo "[DRY RUN] Would delete $count backup dirs to reclaim ${total_gb}GB."
        exit 0
    fi

    echo "Deleting backups..."
    failed=0
    for bdir in "${BACKUP_DIRS[@]}"; do
        if rm -rf "$bdir" 2>/dev/null; then
            echo "  Deleted: $bdir"
        else
            # Try with sudo for root-owned files (e.g. Docker outputs)
            echo "  Permission denied on $bdir — trying with sudo..."
            if sudo rm -rf "$bdir" 2>/dev/null; then
                echo "  Deleted (sudo): $bdir"
            else
                echo "  FAILED: $bdir"
                failed=$((failed + 1))
            fi
        fi
    done

    echo ""
    if [[ $failed -eq 0 ]]; then
        echo "Done. Reclaimed ${total_gb}GB from $count backup dirs."
    else
        echo "Done with $failed failures. Most backups deleted."
    fi
    exit 0
fi

# ── Git Commit in canonical agent-skills repo ────────────────────────────────

if [[ "$MODE" == "git-commit" ]]; then
    REPO_DIR="$HOME/workspace/experiments/agent-skills"

    echo "=== Skills Broadcast: Git Commit ==="
    echo ""
    echo "Canonical: $CANONICAL_DIR (agent-skills/skills)"
    echo ""

    # Validate
    if [[ ! -d "$REPO_DIR/.git" ]]; then
        echo "[ABORT] agent-skills repo not found at $REPO_DIR" >&2
        exit 1
    fi

    if [[ ! -d "$CANONICAL_DIR" ]]; then
        echo "[ABORT] Canonical skills dir not found at $CANONICAL_DIR" >&2
        exit 1
    fi

    skill_count=$(find "$CANONICAL_DIR" -maxdepth 2 -name "SKILL.md" 2>/dev/null | wc -l || true)
    if [[ "$skill_count" -lt "$MIN_SKILLS" ]]; then
        echo "[ABORT] Canonical has only $skill_count skills (min: $MIN_SKILLS)" >&2
        exit 1
    fi

    cd "$REPO_DIR"

    # Check for changes
    if git diff --quiet && git diff --cached --quiet; then
        echo "No changes to commit. Agent-skills is up to date."
        cd "$OLDPWD"
        exit 0
    fi

    if [[ $DRY_RUN -eq 1 ]]; then
        echo "[DRY RUN] Would commit and push changes in $REPO_DIR"
        echo ""
        echo "Changes:"
        git status --short | head -20
        cd "$OLDPWD"
        exit 0
    fi

    # Stage and commit
    git add -A

    if git diff --cached --quiet; then
        echo "No staged changes to commit."
        cd "$OLDPWD"
        exit 0
    fi

    echo "Changes:"
    git diff --cached --stat | tail -10
    echo ""

    timestamp="$(date +%Y-%m-%d)"
    git commit -m "update: $skill_count skills ($timestamp)"
    git push origin "$(git branch --show-current)" --force-with-lease

    echo ""
    echo "Pushed to github.com/grahama1970/agent-skills"
    cd "$OLDPWD"
    exit 0
fi

# ── Validate canonical ───────────────────────────────────────────────────────

skill_count=$(find -L "$CANONICAL_DIR" -maxdepth 2 -name "SKILL.md" 2>/dev/null | wc -l || true)
if [[ "$skill_count" -lt "$MIN_SKILLS" ]]; then
    echo "[skills-broadcast] ABORT: Canonical has only $skill_count skills (min: $MIN_SKILLS)" >&2
    echo "[skills-broadcast] Canonical: $CANONICAL_DIR" >&2
    exit 1
fi

# ── Collect all target directories ───────────────────────────────────────────

# Agent skill path patterns within a project
PATTERNS=(
    ".agent/skills"
    ".pi/skills"
    ".github/skills"
    ".codex/skills"
    ".claude/skills"
    ".agents/skills"
    ".kilocode/skills"
)

# Collect unique project roots
declare -A PROJECTS
PROJECTS["$HOME"]=1

# From registry file
if [[ -f "$REGISTRY_FILE" ]]; then
    while IFS= read -r line; do
        [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
        target="${line/#\~/$HOME}"
        [[ -d "$target" ]] && PROJECTS["$target"]=1
    done < "$REGISTRY_FILE"
fi

# ── Create symlink helper ────────────────────────────────────────────────────

is_curated_skills_dir() {
    # A curated skills dir is a real directory containing symlinks to individual
    # skills (not a blanket symlink to canonical). Projects use this to limit
    # which skills Claude Code injects into context, avoiding the 200+ skill
    # token overhead that degrades session quality.
    local dir="$1"
    [[ -d "$dir" && ! -L "$dir" ]] || return 1
    # Check if it contains at least one symlink pointing into canonical
    local has_skill_symlinks=0
    for entry in "$dir"/*/; do
        [[ -L "${entry%/}" ]] && has_skill_symlinks=1 && break
    done
    [[ $has_skill_symlinks -eq 1 ]] || return 1
    # Confirm at least one symlink targets canonical
    for entry in "$dir"/*/; do
        local link_target
        link_target="$(readlink "${entry%/}" 2>/dev/null)" || continue
        if [[ "$link_target" == "$CANONICAL_DIR"/* ]]; then
            return 0
        fi
    done
    return 1
}

create_link() {
    local target_path="$1"
    local parent_dir
    parent_dir="$(dirname "$target_path")"

    # Skip if this IS the canonical dir
    if [[ "$(realpath "$target_path" 2>/dev/null)" == "$(realpath "$CANONICAL_DIR")" ]]; then
        return 0
    fi

    # Skip curated skills directories — these are intentionally NOT blanket
    # symlinks. Projects use per-skill symlinks to control which skills get
    # injected into LLM context (Claude Code, Codex, etc.)
    if is_curated_skills_dir "$target_path"; then
        local curated_count
        curated_count=$(ls -1 "$target_path" 2>/dev/null | wc -l)
        echo "  CURATED $target_path ($curated_count skills — preserved)"
        return 0
    fi

    # Already a correct symlink?
    if [[ -L "$target_path" ]]; then
        local current_target
        current_target="$(readlink "$target_path")"
        if [[ "$current_target" == "$CANONICAL_DIR" ]]; then
            echo "  OK  $target_path -> $CANONICAL_DIR"
            return 0
        else
            echo "  FIX $target_path (was -> $current_target)"
            if [[ $DRY_RUN -eq 0 ]]; then
                rm "$target_path"
                ln -sfn "$CANONICAL_DIR" "$target_path"
            fi
            return 0
        fi
    fi

    # It's a real directory — replace with symlink
    if [[ -d "$target_path" ]]; then
        local old_count
        old_count=$(find "$target_path" -maxdepth 2 -name "SKILL.md" 2>/dev/null | wc -l || true)
        local old_size
        old_size=$(du -sh "$target_path" 2>/dev/null | cut -f1)
        echo "  NEW $target_path (replacing ${old_count}-skill ${old_size} dir)"

        if [[ $DRY_RUN -eq 0 ]]; then
            # Back up the old directory name, then replace
            local backup="${target_path}.pre-symlink-$(date +%s)"
            mv "$target_path" "$backup"
            ln -sfn "$CANONICAL_DIR" "$target_path"
            echo "      Backed up old dir to: $backup"
            echo "      Delete backup when satisfied: rm -rf '$backup'"
        fi
        return 0
    fi

    # Doesn't exist — create parent and symlink
    if [[ -d "$parent_dir" ]]; then
        echo "  NEW $target_path (creating symlink)"
        if [[ $DRY_RUN -eq 0 ]]; then
            ln -sfn "$CANONICAL_DIR" "$target_path"
        fi
    fi
}

# ── Status / Info ────────────────────────────────────────────────────────────

if [[ "$MODE" == "status" || "$MODE" == "info" || "$MODE" == "find" ]]; then
    echo "=== Skills Broadcast Status ==="
    echo ""
    echo "Canonical: $CANONICAL_DIR ($skill_count skills)"
    echo ""

    for proj in "${!PROJECTS[@]}"; do
        echo "Project: $proj"
        found=0
        for pattern in "${PATTERNS[@]}"; do
            tp="$proj/$pattern"
            if [[ -L "$tp" ]]; then
                link_target="$(readlink "$tp")"
                if [[ "$link_target" == "$CANONICAL_DIR" ]]; then
                    echo "  OK      $pattern -> canonical"
                else
                    echo "  STALE   $pattern -> $link_target (should be canonical)"
                fi
                found=1
            elif [[ -d "$tp" ]]; then
                count=$(find "$tp" -maxdepth 2 -name "SKILL.md" 2>/dev/null | wc -l || true)
                size=$(du -sh "$tp" 2>/dev/null | cut -f1)
                if [[ "$(realpath "$tp")" == "$(realpath "$CANONICAL_DIR")" ]]; then
                    echo "  CANON   $pattern ($count skills, $size) [this IS canonical]"
                elif is_curated_skills_dir "$tp"; then
                    curated=$(ls -1 "$tp" 2>/dev/null | wc -l)
                    echo "  CURATED $pattern ($curated skills) [per-project filter — preserved]"
                else
                    echo "  COPY    $pattern ($count skills, $size) [should be symlink]"
                fi
                found=1
            fi
        done
        [[ $found -eq 0 ]] && echo "  (no skill dirs found)"
        echo ""
    done

    # Show canonical status
    echo "Canonical: $CANONICAL_DIR"
    if [[ -d "$CANONICAL_DIR" && ! -L "$CANONICAL_DIR" ]]; then
        count=$(find "$CANONICAL_DIR" -maxdepth 2 -name "SKILL.md" 2>/dev/null | wc -l || true)
        size=$(du -sh "$CANONICAL_DIR" 2>/dev/null | cut -f1)
        echo "  DIR ($count skills, $size) — this is the source of truth"
    elif [[ -L "$CANONICAL_DIR" ]]; then
        echo "  ERROR: Canonical should be a real directory, not a symlink!"
    else
        echo "  ERROR: Canonical directory not found!"
    fi
    exit 0
fi

# ── Link (main operation) ────────────────────────────────────────────────────

echo "=== Skills Broadcast: Symlink Mode ==="
echo "Canonical: $CANONICAL_DIR ($skill_count skills)"
echo ""

if [[ $DRY_RUN -eq 1 ]]; then
    echo "[DRY RUN] No changes will be made."
    echo ""
fi

    # IDE patterns whose parent dirs are safe to auto-create.
    # Excludes .github (used by GitHub Actions) and .agents (ambiguous plural).
    AUTOCREATE_PATTERNS=(".agent/skills" ".pi/skills" ".codex/skills" ".claude/skills" ".kilocode/skills")

for proj in "${!PROJECTS[@]}"; do
    echo "Project: $proj"
    for pattern in "${PATTERNS[@]}"; do
        tp="$proj/$pattern"
        parent="$(dirname "$tp")"

        # Auto-create parent IDE directories if they don't exist
        # Only for known-safe IDE patterns (not .github, .agents)
        if [[ ! -d "$parent" && ! -L "$tp" && ! -d "$tp" ]]; then
            should_create=0
            for ac in "${AUTOCREATE_PATTERNS[@]}"; do
                [[ "$pattern" == "$ac" ]] && should_create=1 && break
            done
            if [[ $should_create -eq 1 ]]; then
                if [[ $DRY_RUN -eq 0 ]]; then
                    mkdir -p "$parent"
                fi
                echo "  MKDIR $parent"
            else
                continue
            fi
        fi

        # Process if dir/link exists or parent now exists
        if [[ -d "$tp" || -L "$tp" || -d "$parent" ]]; then
            create_link "$tp"
        fi
    done
    echo ""
done

# Note: agent-skills/skills IS the canonical source now. No symlink needed there.

if [[ $DRY_RUN -eq 1 ]]; then
    echo "[DRY RUN] Rerun without --dry-run to apply changes."
else
    echo "Done. All targets now symlink to canonical."
    # Post-hook: refresh skill registry in /memory after symlink update
    if command -v memory-agent &>/dev/null; then
        echo "Refreshing skill registry in /memory..."
        memory-agent ingest-skills "$CANONICAL_DIR" 2>/dev/null || true
    fi
fi
