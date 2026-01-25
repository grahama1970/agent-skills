#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

# Smart LOCAL_DIR detection: find the NEWEST skills directory
detect_local_skills_dir() {
    local candidates=(
        "${PROJECT_ROOT}/.pi/skills"
        "${PROJECT_ROOT}/.agent/skills"
        "${PROJECT_ROOT}/.codex/skills"
        "${PROJECT_ROOT}/.claude/skills"
        "${PROJECT_ROOT}/.agents/skills"
        "${PROJECT_ROOT}/.kilocode/skills"
    )
    local best_dir=""
    local best_time=0

    for dir in "${candidates[@]}"; do
        if [[ -d "$dir" ]]; then
            # Get modification time of the newest file in the directory
            # If directory is empty, latest will be empty/0
            local latest
            latest=$(find "$dir" -type f -printf '%T@\n' 2>/dev/null | sort -n | tail -1)
            
            # Truncate to integer for simple comparison
            latest=${latest%.*}
            [[ -z "$latest" ]] && latest=0

            # Winner takes all:Strictly greater than current best
            # (First one found wins ties, preserving configured priority order for simultaneous edits)
            if [[ "$latest" -gt "$best_time" ]]; then
                best_time=$latest
                best_dir=$dir
            fi
            
            # If this is the first existence check, set as default fallback
            if [[ -z "$best_dir" ]]; then
                best_dir=$dir
            fi
        fi
    done

    # Fallback to legacy if nothing found
    if [[ -z "$best_dir" ]]; then
        echo "${PROJECT_ROOT}/.agents/skills"
    else
        echo "$best_dir"
    fi
}

LOCAL_DIR="${SKILLS_LOCAL_DIR:-$(detect_local_skills_dir)}"
UPSTREAM_REPO="${SKILLS_UPSTREAM_REPO:-$HOME/workspace/experiments/agent-skills}"
UPSTREAM_DIR="${UPSTREAM_REPO}/skills"

usage() {
    cat <<USAGE
Usage: ${0##*/} [push|pull|info] [--dry-run] [--fanout] [--fanout-targets PATHS]
  push      Local -> Upstream (default)
  pull      Upstream -> Local
  info      Show current paths and fanout configuration (alias: find)
Options:
  --dry-run           Preview rsync operations
  --fanout            When pushing, also copy skills into fanout projects
  --fanout-targets X  Colon-separated list of project roots (overrides env)
  -h, --help          Show this help
USAGE
}

MODE="push"
DRY_RUN=0
FANOUT=0
FANOUT_TARGETS=""
AUTOCOMMIT_ENV="${SKILLS_SYNC_AUTOCOMMIT:-1}"
AUTOCOMMIT_OVERRIDE=""

resolve_fanout_targets() {
    if [[ -n "$FANOUT_TARGETS" ]]; then
        echo "$FANOUT_TARGETS"
    elif [[ -n "${SKILLS_FANOUT_PROJECTS:-}" ]]; then
        echo "$SKILLS_FANOUT_PROJECTS"
    else
        echo ""
    fi
}

if [[ $# -gt 0 ]]; then
    case "$1" in
        push|pull|info|find)
            MODE="$1"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --dry-run|-n)
            DRY_RUN=1
            shift
            ;;
        *)
            usage
            exit 1
            ;;
    esac
fi

# parse remaining opts
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run|-n)
            DRY_RUN=1
            ;;
        --fanout)
            FANOUT=1
            ;;
        --fanout-targets)
            shift
            FANOUT_TARGETS="$1"
            ;;
        --no-autocommit)
            AUTOCOMMIT_OVERRIDE="off"
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            exit 1
            ;;
    esac
    shift
done

if [[ "$MODE" == "info" || "$MODE" == "find" ]]; then
    echo "[skills-sync] Local skills dir : $LOCAL_DIR"
    if [[ -d "$LOCAL_DIR" ]]; then
        echo "  status: exists"
    else
        echo "  status: missing"
    fi
    echo "[skills-sync] Upstream repo    : $UPSTREAM_REPO"
    echo "[skills-sync] Upstream skills : $UPSTREAM_DIR"
    if [[ -d "$UPSTREAM_DIR" ]]; then
        echo "  status: exists"
    else
        echo "  status: missing"
    fi
    ft="$(resolve_fanout_targets)"
    if [[ -z "$ft" ]]; then
        echo "[skills-sync] Fanout targets  : (none configured)"
    else
        echo "[skills-sync] Fanout targets  :"
        IFS=":" read -r -a info_arr <<< "$ft"
        for target in "${info_arr[@]}"; do
            printf '  - %s %s\n' "$target" "$( [[ -d "$target/.agents/skills" ]] && echo '(skills dir present)' || echo '(skills dir missing)' )"
        done
    fi
    echo "[skills-sync] To run fanout: export SKILLS_FANOUT_PROJECTS=... or use --fanout-targets"
    exit 0
fi

if [[ ! -d "$LOCAL_DIR" ]]; then
    echo "Local skills directory not found: $LOCAL_DIR" >&2
    exit 1
fi
if [[ ! -d "$UPSTREAM_DIR" ]]; then
    echo "Upstream skills directory not found: $UPSTREAM_DIR" >&2
    exit 1
fi

if [[ "$MODE" == "push" ]]; then
    SRC="$LOCAL_DIR/"
    DEST="$UPSTREAM_DIR/"
    SUMMARY="Pushed local skills to $UPSTREAM_DIR"
elif [[ "$MODE" == "pull" ]]; then
    SRC="$UPSTREAM_DIR/"
    DEST="$LOCAL_DIR/"
    SUMMARY="Pulled upstream skills into $LOCAL_DIR"
else
    echo "Unknown mode $MODE" >&2
    exit 1
fi

RSYNC_OPTS=(
    "-av" "--delete" "--update" # --update prevents overwriting newer destination files
    "--exclude" ".venv"
    "--exclude" "node_modules"
    "--exclude" "__pycache__"
    "--exclude" ".git"
    "--exclude" ".DS_Store"
    "--exclude" ".idea"
    "--exclude" ".vscode"
)
if [[ $DRY_RUN -eq 1 ]]; then
    RSYNC_OPTS+=("--dry-run")
fi

echo "[skills-sync] Mode: $MODE"
echo "[skills-sync] Source: $SRC"
echo "[skills-sync] Dest:   $DEST"
echo "[skills-sync] Running: rsync ${RSYNC_OPTS[*]}"
rsync "${RSYNC_OPTS[@]}" "$SRC" "$DEST"

# ---------------------------------------------------------
# Unified Broadcast (Smart Sync)
# Sync to all targets (Fanout + Local Hub-and-Spoke)
# ---------------------------------------------------------
echo "[skills-sync] Starting Smart Broadcast to all registered targets..."

# 1. Collect all Unique Project Roots
#    - Current Project Root
#    - SKILLS_FANOUT_PROJECTS (from env)
#    - Home Directory (for global agent configs)
#    - Registry File (~/.agent_skills_targets)
declare -A TARGET_PROJECTS
TARGET_PROJECTS["$PROJECT_ROOT"]=1
TARGET_PROJECTS["$HOME"]=1

# Load Registry File
REGISTRY_FILE="$HOME/.agent_skills_targets"
if [[ -f "$REGISTRY_FILE" ]]; then
    while IFS= read -r line; do
        # fast skip comments/empty
        [[ "$line" =~ ^#.*$ ]] && continue
        [[ -z "$line" ]] && continue
        # Expand ~ if present (simple unsafe eval capability or just assume full paths)
        # We'll assume full paths for safety, or simple expansion
        target="${line/#\~/$HOME}"
        if [[ -d "$target" ]]; then
            TARGET_PROJECTS["$target"]=1
        fi
    done < "$REGISTRY_FILE"
fi

# Add Fanout Projects (Env Var)
fanout_str="$(resolve_fanout_targets)"
if [[ -n "$fanout_str" ]]; then
    IFS=":" read -r -a f_arr <<< "$fanout_str"
    for p in "${f_arr[@]}"; do
        if [[ -d "$p" ]]; then
            TARGET_PROJECTS["$p"]=1
        else
             echo "[skills-sync] Warning: configured fanout target '$p' does not exist."
        fi
    done
fi

# 2. Define Agent Skill Path Patterns
#    Priority order matters.
PATTERNS=(
    ".agent/skills"    # Antigravity
    ".pi/skills"       # Pi
    ".codex/skills"    # Codex
    ".claude/skills"   # Claude
    ".gemini/skills"   # Antigravity (Global)
    ".agents/skills"   # Generic/Legacy
)

# Use UPSTREAM_DIR as source of truth
BROADCAST_SRC="$UPSTREAM_DIR/"

# 3. Iterate Projects and Sync to *ALL* matching subdirs
#    (A project might support multiple agents, so we sync to all found dirs)
for proj in "${!TARGET_PROJECTS[@]}"; do
    FOUND_ANY=0
    
    for relative_path in "${PATTERNS[@]}"; do
        target_path="$proj/$relative_path"
        
        # Determine if we should sync to this specific path
        SHOULD_SYNC=0
        
        # A. Path exists? Sync it.
        if [[ -d "$target_path" ]]; then
            SHOULD_SYNC=1
        fi
        
        # B. Does not exist, but valid for this project?
        #    Force create standard paths for known agents to ensure they have skills.
        if [[ "$proj" == "$HOME" ]]; then
             if [[ "$relative_path" == ".gemini/skills" ]]; then
                 mkdir -p "$target_path"
                 SHOULD_SYNC=1
             fi
        else
            # For any targeted project (Local or Fanout), ensure standard dirs exist
            if [[ "$relative_path" == ".agent/skills" || \
                  "$relative_path" == ".codex/skills" || \
                  "$relative_path" == ".claude/skills" || \
                  "$relative_path" == ".pi/skills" ]]; then
                mkdir -p "$target_path"
                SHOULD_SYNC=1
            fi
        fi

        if [[ $SHOULD_SYNC -eq 1 ]]; then
            # Skip if it's the same as the local dir we started with (redundant)
            if [[ "$target_path" == "$LOCAL_DIR" ]]; then
                continue
            fi
            
            echo "[skills-sync] Syncing -> $target_path"
            # Use RSYNC_OPTS to ensure excludes are applied during broadcast
            rsync "${RSYNC_OPTS[@]}" "$BROADCAST_SRC" "$target_path/"
            FOUND_ANY=1
        fi
    done
    
    if [[ $FOUND_ANY -eq 0 && "$proj" != "$HOME" ]]; then
         # Only warn for actual projects, not HOME (which might just be for global config)
         echo "[skills-sync] Note: No agent skill directories found in $proj"
    fi
done

echo "[skills-sync] Broadcast complete."

# ---------------------------------------------------------
# Git Commit & Push to Upstream Repo
# ---------------------------------------------------------
should_autocommit() {
    if [[ "$MODE" != "push" || $DRY_RUN -eq 1 ]]; then
        echo 0
        return
    fi
    if [[ "$AUTOCOMMIT_OVERRIDE" == "off" ]]; then
        echo 0
        return
    fi
    if [[ "$AUTOCOMMIT_ENV" == "1" ]]; then
        echo 1
    else
        echo 0
    fi
}

if [[ $(should_autocommit) -eq 1 ]]; then
    echo "[skills-sync] Auto-commit enabled (SKILLS_SYNC_AUTOCOMMIT=1)"
    pushd "$UPSTREAM_REPO" >/dev/null
    git add skills || true
    if git diff --cached --quiet; then
        echo "[skills-sync] No changes to commit in upstream repo."
    else
        ts=$(date +"%Y-%m-%d %H:%M:%S")
        commit_msg="Sync skills $(basename "$PROJECT_ROOT") @ $ts"
        git commit -m "$commit_msg" || true
        if git rev-parse --abbrev-ref --symbolic-full-name @{u} >/dev/null 2>&1; then
            git push || true
        else
            echo "[skills-sync] Upstream repo has no tracking branch; skipping push."
        fi
    fi
    popd >/dev/null
else
    echo "[skills-sync] Git auto-commit disabled. To enable: export SKILLS_SYNC_AUTOCOMMIT=1"
    echo "[skills-sync] Next steps: cd $UPSTREAM_REPO && git status"
fi
