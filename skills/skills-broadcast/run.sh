#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

# =============================================================================
# skills-broadcast: Symlink-based skill sharing
#
# The canonical source of truth is THIS project's .pi/skills/ directory.
# All other IDE/project skill directories become symlinks to canonical.
#
# This replaces the old rsync-based approach which:
#   - Duplicated ~300GB of data across targets
#   - Required complex exclusion lists
#   - Caused the 2026-02-11 deletion incident via --delete
#   - Required manual "push" to propagate changes
#
# With symlinks, changes are instant everywhere. No sync needed.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CANONICAL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REGISTRY_FILE="$HOME/.agent_skills_targets"

# Validate canonical has enough skills to be trustworthy
MIN_SKILLS=20

usage() {
    cat <<USAGE
Usage: ${0##*/} [link|status|info|cleanup|git-sync|register|unregister|targets|push|pull] [--dry-run]

Symlink-based skill sharing. Canonical source: $CANONICAL_DIR

Commands:
  link              Create symlinks at all targets (main operation)
  status            Show all targets and their link state
  info              Alias for status
  cleanup           Delete .pre-symlink-* backup directories to reclaim disk space
  git-sync          Commit and push canonical skills to agent-skills GitHub repo
  register [PATH]   Add a project to the target registry
  unregister [PATH] Remove a project from the target registry
  targets           List registered projects

Legacy aliases (map to 'link' for backwards compatibility):
  push              Same as 'link'
  pull              Same as 'link'

Options:
  --dry-run, -n     Preview what would be done
  -h, --help        Show this help
USAGE
}

MODE="link"
DRY_RUN=0

if [[ $# -gt 0 ]]; then
    case "$1" in
        link|status|info|find|cleanup|git-sync|register|unregister|targets)
            MODE="$1"
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

# ── Git Sync to agent-skills repo ────────────────────────────────────────────

if [[ "$MODE" == "git-sync" ]]; then
    UPSTREAM_DIR="$HOME/workspace/experiments/agent-skills"
    UPSTREAM_SKILLS="$UPSTREAM_DIR/skills"

    echo "=== Skills Broadcast: Git Sync ==="
    echo ""
    echo "Canonical: $CANONICAL_DIR"
    echo "Target:    $UPSTREAM_DIR (github.com/grahama1970/agent-skills)"
    echo ""

    # Validate
    if [[ ! -d "$UPSTREAM_DIR/.git" ]]; then
        echo "[ABORT] agent-skills repo not found at $UPSTREAM_DIR" >&2
        exit 1
    fi

    skill_count=$(find -L "$CANONICAL_DIR" -maxdepth 2 -name "SKILL.md" 2>/dev/null | wc -l || true)
    if [[ "$skill_count" -lt "$MIN_SKILLS" ]]; then
        echo "[ABORT] Canonical has only $skill_count skills (min: $MIN_SKILLS)" >&2
        exit 1
    fi

    # Track whether git-sync succeeded — only restore symlink on failure
    GIT_SYNC_OK=0
    restore_symlink_on_failure() {
        if [[ "$GIT_SYNC_OK" -eq 0 && -d "$UPSTREAM_SKILLS" && ! -L "$UPSTREAM_SKILLS" ]]; then
            rm -rf "$UPSTREAM_SKILLS"
            ln -sfn "$CANONICAL_DIR" "$UPSTREAM_SKILLS"
            echo "  Symlink restored (git-sync failed): $UPSTREAM_SKILLS -> $CANONICAL_DIR"
        fi
    }
    trap restore_symlink_on_failure EXIT

    # Step 1: Remove symlink (or stale real dir) if present
    if [[ -L "$UPSTREAM_SKILLS" ]]; then
        echo "Removing symlink..."
        rm "$UPSTREAM_SKILLS"
    elif [[ -d "$UPSTREAM_SKILLS" ]]; then
        echo "Clearing old skills dir..."
        rm -rf "$UPSTREAM_SKILLS"
    fi

    # Clean up any stale backup dirs from prior runs
    for stale in "$UPSTREAM_DIR"/skills.old-*; do
        [[ -d "$stale" ]] && rm -rf "$stale"
    done

    # Step 2: Copy canonical content (cp -a preserves internal symlinks to 12TB)
    echo "Copying $skill_count skills from canonical..."
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "[DRY RUN] Would copy $CANONICAL_DIR -> $UPSTREAM_SKILLS"
        echo "[DRY RUN] Would commit and push to origin"
        # Restore symlink for dry-run (no real copy was made)
        ln -sfn "$CANONICAL_DIR" "$UPSTREAM_SKILLS"
        GIT_SYNC_OK=1  # not a failure — skip trap
        exit 0
    fi

    # Step 2: Whitelist-copy source files only. Never follow symlinks.
    # This prevents secrets in session logs, Rust build artifacts, .venv,
    # models, and other heavy/sensitive content from reaching GitHub.
    mkdir -p "$UPSTREAM_SKILLS"
    # Directory excludes MUST come before --include='*/' (rsync processes in order)
    rsync -a --no-links --delete \
        --exclude='.venv*/' \
        --exclude='__pycache__/' \
        --exclude='.ruff_cache/' \
        --exclude='.pytest_cache/' \
        --exclude='node_modules/' \
        --exclude='target/' \
        --exclude='.git/' \
        --exclude='worktrees/' \
        --exclude='designs/' \
        --exclude='references/' \
        --exclude='.artifacts/' \
        --exclude='models/' \
        --exclude='.system/' \
        --exclude='structured/' \
        --exclude='state/' \
        --exclude='checkpoints/' \
        --exclude='*.pre-symlink-*' \
        --include='*/' \
        --include='*.py' \
        --include='*.sh' \
        --include='*.md' \
        --include='*.yaml' \
        --include='*.yml' \
        --include='*.toml' \
        --include='*.txt' \
        --include='*.html' \
        --include='*.css' \
        --include='*.js' \
        --include='*.ts' \
        --include='*.tsx' \
        --include='*.jsx' \
        --include='*.rs' \
        --include='*.go' \
        --include='*.cfg' \
        --include='*.ini' \
        --include='*.conf' \
        --include='*.svg' \
        --include='*.png' \
        --include='Makefile' \
        --include='Dockerfile' \
        --include='Dockerfile.*' \
        --include='docker-compose.yml' \
        --include='docker-compose.yaml' \
        --exclude='*' \
        "$CANONICAL_DIR/" "$UPSTREAM_SKILLS/"

    # Safety: remove any file >50MB that slipped through
    find "$UPSTREAM_SKILLS" -type f -size +50M -delete 2>/dev/null || true
    # Safety: remove any .env or secret-bearing files
    find "$UPSTREAM_SKILLS" -name '.env' -delete 2>/dev/null || true
    # Clean empty directories left by exclusions
    find "$UPSTREAM_SKILLS" -type d -empty -delete 2>/dev/null || true

    # Step 4: Commit and push
    cd "$UPSTREAM_DIR"
    git add -A

    # Check if there are actual changes
    if git diff --cached --quiet; then
        echo ""
        echo "No changes to commit. Agent-skills is up to date."
        GIT_SYNC_OK=1  # not a failure — skip trap
        cd "$OLDPWD"
        exit 0
    fi

    # Show summary
    echo ""
    echo "Changes:"
    git diff --cached --stat | tail -5
    echo ""

    timestamp="$(date +%Y-%m-%d)"
    git commit -m "sync: $skill_count skills from canonical ($timestamp)"
    git push origin "$(git branch --show-current)" --force-with-lease

    echo ""
    echo "Pushed to github.com/grahama1970/agent-skills"

    # Mark success — trap will NOT restore symlink, keeping real files in working tree
    GIT_SYNC_OK=1
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

    # Also check agent-skills repo
    UPSTREAM="$HOME/workspace/experiments/agent-skills/skills"
    if [[ -d "$UPSTREAM" ]]; then
        echo "Legacy upstream: $UPSTREAM"
        if [[ -L "$UPSTREAM" ]]; then
            echo "  SYMLINK -> $(readlink "$UPSTREAM")"
        else
            count=$(find "$UPSTREAM" -maxdepth 2 -name "SKILL.md" 2>/dev/null | wc -l || true)
            size=$(du -sh "$UPSTREAM" 2>/dev/null | cut -f1)
            echo "  DIR ($count skills, $size) — consider making this a symlink too"
        fi
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

# Handle the legacy agent-skills upstream repo
UPSTREAM="$HOME/workspace/experiments/agent-skills/skills"
if [[ -d "$UPSTREAM" && ! -L "$UPSTREAM" ]]; then
    echo "Legacy upstream: $UPSTREAM"
    create_link "$UPSTREAM"
    echo ""
fi

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
