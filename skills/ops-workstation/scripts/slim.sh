#!/usr/bin/env bash
# Identify opportunities to reclaim storage space.
# Checks: media quality, duplicates, caches, unused files, ML models.
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options] [path]

Identify opportunities to reclaim storage space.

Options:
  --media          Find lower quality versions of same media content
  --duplicates     Find exact file duplicates
  --caches         Find cleanable caches (pip, npm, docker, conda)
  --unused         Find large files not accessed in 6+ months
  --models         Find duplicate/old ML model weights
  --all            Run all checks (default if no option specified)
  --min-size <MB>  Minimum file size for media/duplicates (default: 100)
  --json           Output as JSON
  --help           Show this message

Paths:
  Default media path: /mnt/storage12tb
  Default model path: ~/.cache/huggingface

Examples:
  $(basename "$0")                    # Overview of all opportunities
  $(basename "$0") --media            # Media quality analysis
  $(basename "$0") --caches           # Cache cleanup opportunities
  $(basename "$0") --media /path/to   # Scan specific path
USAGE
}

# Defaults
SCAN_PATH="/mnt/storage12tb"
MIN_SIZE_MB=100
CHECK_MEDIA=false
CHECK_DUPLICATES=false
CHECK_CACHES=false
CHECK_UNUSED=false
CHECK_MODELS=false
CHECK_ALL=true
OUTPUT_JSON=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --media) CHECK_MEDIA=true; CHECK_ALL=false; shift;;
    --duplicates) CHECK_DUPLICATES=true; CHECK_ALL=false; shift;;
    --caches) CHECK_CACHES=true; CHECK_ALL=false; shift;;
    --unused) CHECK_UNUSED=true; CHECK_ALL=false; shift;;
    --models) CHECK_MODELS=true; CHECK_ALL=false; shift;;
    --all) CHECK_ALL=true; shift;;
    --min-size) MIN_SIZE_MB="$2"; shift 2;;
    --json) OUTPUT_JSON=true; shift;;
    --help|-h) usage; exit 0;;
    -*) echo "Unknown option: $1" >&2; usage; exit 1;;
    *) SCAN_PATH="$1"; shift;;
  esac
done

# If --all, enable everything
if [[ "$CHECK_ALL" == "true" ]]; then
  CHECK_MEDIA=true
  CHECK_DUPLICATES=true
  CHECK_CACHES=true
  CHECK_UNUSED=true
  CHECK_MODELS=true
fi

# Results storage
declare -A RESULTS
RESULTS[media_bytes]=0
RESULTS[media_count]=0
RESULTS[duplicates_bytes]=0
RESULTS[duplicates_count]=0
RESULTS[caches_bytes]=0
RESULTS[unused_bytes]=0
RESULTS[unused_count]=0
RESULTS[models_bytes]=0
RESULTS[models_count]=0

# ============================================================================
# MEDIA QUALITY ANALYSIS
# Parse filenames to find same content at different quality levels
# ============================================================================
analyze_media() {
  local path="$1"
  [[ ! -d "$path" ]] && return

  echo "### Media Quality Analysis"
  echo ""
  echo "Scanning for lower quality versions of same content..."
  echo ""

  # Find video files
  local -A episodes  # key: normalized name, value: list of files
  local -A episode_info  # key: filepath, value: "resolution|codec|source|size"

  while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    local basename
    basename=$(basename "$file")
    local size
    size=$(stat -c%s "$file" 2>/dev/null || echo 0)

    # Extract show info: normalize to "ShowName.S01E01" format
    local normalized=""
    # Match patterns like "Show.Name.S01E01" or "Show Name - S01E01" or "Show.Name.1x01"
    if [[ "$basename" =~ ([A-Za-z0-9._-]+)[._-][Ss]([0-9]+)[Ee]([0-9]+) ]]; then
      local show="${BASH_REMATCH[1]}"
      local season="${BASH_REMATCH[2]}"
      local ep="${BASH_REMATCH[3]}"
      # Normalize show name (replace dots/underscores with spaces, lowercase)
      show=$(echo "$show" | tr '._' ' ' | tr '[:upper:]' '[:lower:]' | sed 's/  */ /g' | xargs)
      normalized="${show}|s${season}e${ep}"
    elif [[ "$basename" =~ ([A-Za-z0-9._-]+)[._-]([0-9]+)x([0-9]+) ]]; then
      local show="${BASH_REMATCH[1]}"
      local season="${BASH_REMATCH[2]}"
      local ep="${BASH_REMATCH[3]}"
      show=$(echo "$show" | tr '._' ' ' | tr '[:upper:]' '[:lower:]' | sed 's/  */ /g' | xargs)
      normalized="${show}|s${season}e${ep}"
    fi

    [[ -z "$normalized" ]] && continue

    # Extract quality info
    local resolution="unknown"
    local codec="unknown"
    local source="unknown"

    # Resolution
    if [[ "$basename" =~ 2160[pP] ]] || [[ "$basename" =~ 4[kK] ]]; then
      resolution="2160p"
    elif [[ "$basename" =~ 1080[pP] ]]; then
      resolution="1080p"
    elif [[ "$basename" =~ 720[pP] ]]; then
      resolution="720p"
    elif [[ "$basename" =~ 480[pP] ]] || [[ "$basename" =~ [Dd][Vv][Dd] ]]; then
      resolution="480p"
    fi

    # Codec (x265/HEVC is better than x264)
    if [[ "$basename" =~ [xX]265 ]] || [[ "$basename" =~ [Hh][Ee][Vv][Cc] ]]; then
      codec="x265"
    elif [[ "$basename" =~ [xX]264 ]] || [[ "$basename" =~ [Aa][Vv][Cc] ]]; then
      codec="x264"
    fi

    # Source
    if [[ "$basename" =~ [Bb]lu[Rr]ay ]] || [[ "$basename" =~ [Bb][Dd][Rr]ip ]]; then
      source="bluray"
    elif [[ "$basename" =~ [Ww][Ee][Bb]-?[Dd][Ll] ]] || [[ "$basename" =~ [Ww][Ee][Bb]-?[Hh][Dd] ]]; then
      source="web"
    elif [[ "$basename" =~ [Hh][Dd][Tt][Vv] ]]; then
      source="hdtv"
    fi

    # Store info
    if [[ -z "${episodes[$normalized]:-}" ]]; then
      episodes[$normalized]="$file"
    else
      episodes[$normalized]+=$'\n'"$file"
    fi
    episode_info["$file"]="${resolution}|${codec}|${source}|${size}"

  done < <(find "$path" -type f \( -iname "*.mkv" -o -iname "*.mp4" -o -iname "*.avi" -o -iname "*.m4v" \) -size "+${MIN_SIZE_MB}M" 2>/dev/null)

  # Quality scoring function (higher = better)
  score_quality() {
    local info="$1"
    local res codec src size
    IFS='|' read -r res codec src size <<< "$info"
    local score=0

    case "$res" in
      2160p) score=$((score + 400));;
      1080p) score=$((score + 300));;
      720p)  score=$((score + 200));;
      480p)  score=$((score + 100));;
    esac

    case "$codec" in
      x265) score=$((score + 20));;  # x265 preferred (better compression)
      x264) score=$((score + 10));;
    esac

    case "$src" in
      bluray) score=$((score + 3));;
      web)    score=$((score + 2));;
      hdtv)   score=$((score + 1));;
    esac

    echo "$score"
  }

  # Find episodes with multiple versions
  local total_recoverable=0
  local total_files=0
  local recommendations=""

  for key in "${!episodes[@]}"; do
    local files="${episodes[$key]}"
    local count
    count=$(echo "$files" | wc -l)
    [[ $count -le 1 ]] && continue

    # Score each version
    local best_file=""
    local best_score=0
    local best_info=""

    while IFS= read -r file; do
      [[ -z "$file" ]] && continue
      local info="${episode_info[$file]}"
      local score
      score=$(score_quality "$info")
      if [[ $score -gt $best_score ]]; then
        best_score=$score
        best_file="$file"
        best_info="$info"
      fi
    done <<< "$files"

    # List files to delete (not the best)
    while IFS= read -r file; do
      [[ -z "$file" ]] && continue
      [[ "$file" == "$best_file" ]] && continue

      local info="${episode_info[$file]}"
      local size
      size=$(echo "$info" | cut -d'|' -f4)
      total_recoverable=$((total_recoverable + size))
      total_files=$((total_files + 1))

      local size_human
      size_human=$(numfmt --to=iec-i --suffix=B "$size" 2>/dev/null || echo "${size}B")
      local basename
      basename=$(basename "$file")
      local best_basename
      best_basename=$(basename "$best_file")

      recommendations+="| $size_human | ${basename:0:45}... | Keep: ${best_basename:0:30}... |"$'\n'
    done <<< "$files"
  done

  if [[ $total_files -gt 0 ]]; then
    echo "| Size | Delete (Lower Quality) | Recommendation |"
    echo "|------|------------------------|----------------|"
    echo "$recommendations" | head -20

    if [[ $total_files -gt 20 ]]; then
      echo "| ... | $((total_files - 20)) more files | ... |"
    fi
    echo ""
  else
    echo "No lower quality duplicates found."
    echo ""
  fi

  local total_human
  total_human=$(numfmt --to=iec-i --suffix=B "$total_recoverable" 2>/dev/null || echo "${total_recoverable}B")
  echo "**Recoverable:** $total_human ($total_files files)"
  echo ""

  RESULTS[media_bytes]=$total_recoverable
  RESULTS[media_count]=$total_files
}

# ============================================================================
# EXACT DUPLICATES
# Files with same size and checksum
# ============================================================================
analyze_duplicates() {
  local path="$1"
  [[ ! -d "$path" ]] && return

  echo "### Exact Duplicates"
  echo ""
  echo "Finding files with identical size (quick scan)..."
  echo ""

  local -A size_groups
  local -A size_files

  while IFS= read -r file; do
    local size
    size=$(stat -c%s "$file" 2>/dev/null || echo 0)
    [[ $size -lt $((MIN_SIZE_MB * 1024 * 1024)) ]] && continue

    if [[ -z "${size_groups[$size]:-}" ]]; then
      size_groups[$size]=1
      size_files[$size]="$file"
    else
      size_groups[$size]=$((size_groups[$size] + 1))
      size_files[$size]+=$'\n'"$file"
    fi
  done < <(find "$path" -type f -size "+${MIN_SIZE_MB}M" 2>/dev/null)

  # Calculate totals
  local potential_dupes=0
  local potential_size=0

  for size in "${!size_groups[@]}"; do
    local count=${size_groups[$size]}
    if [[ $count -gt 1 ]]; then
      potential_dupes=$((potential_dupes + count - 1))
      potential_size=$((potential_size + size * (count - 1)))
    fi
  done

  local size_human
  size_human=$(numfmt --to=iec-i --suffix=B "$potential_size" 2>/dev/null || echo "${potential_size}B")
  echo "**Potential duplicates:** $potential_dupes files (~$size_human)"
  echo ""
  echo "*Run \`./run.sh duplicates\` for full checksum verification.*"
  echo ""

  RESULTS[duplicates_bytes]=$potential_size
  RESULTS[duplicates_count]=$potential_dupes
}

# ============================================================================
# CACHE ANALYSIS
# pip, npm, docker, conda, huggingface
# ============================================================================
analyze_caches() {
  echo "### Cache Analysis"
  echo ""
  echo "| Cache | Size | Command to Clean |"
  echo "|-------|------|------------------|"

  local total=0

  # pip cache
  if command -v pip &>/dev/null; then
    local pip_size
    pip_size=$(pip cache info 2>/dev/null | grep "Location:" -A1 | tail -1 | grep -oE "[0-9.]+ [GMK]B" || echo "0")
    local pip_path
    pip_path=$(pip cache dir 2>/dev/null || echo "")
    if [[ -d "$pip_path" ]]; then
      local pip_bytes
      pip_bytes=$(du -sb "$pip_path" 2>/dev/null | cut -f1 || echo 0)
      local pip_human
      pip_human=$(numfmt --to=iec-i --suffix=B "$pip_bytes" 2>/dev/null || echo "0B")
      echo "| pip | $pip_human | \`pip cache purge\` |"
      total=$((total + pip_bytes))
    fi
  fi

  # npm cache
  if command -v npm &>/dev/null; then
    local npm_path
    npm_path=$(npm config get cache 2>/dev/null || echo "$HOME/.npm")
    if [[ -d "$npm_path" ]]; then
      local npm_bytes
      npm_bytes=$(du -sb "$npm_path" 2>/dev/null | cut -f1 || echo 0)
      local npm_human
      npm_human=$(numfmt --to=iec-i --suffix=B "$npm_bytes" 2>/dev/null || echo "0B")
      echo "| npm | $npm_human | \`npm cache clean --force\` |"
      total=$((total + npm_bytes))
    fi
  fi

  # Docker
  if command -v docker &>/dev/null; then
    local docker_info
    docker_info=$(docker system df 2>/dev/null | tail -n +2 || echo "")
    if [[ -n "$docker_info" ]]; then
      local docker_reclaimable
      docker_reclaimable=$(docker system df 2>/dev/null | awk 'NR>1 {gsub(/[^0-9.]/,"",$5); sum+=$5} END {print sum"GB"}' || echo "0GB")
      echo "| Docker | ~$docker_reclaimable reclaimable | \`docker system prune -a\` |"
    fi
  fi

  # Conda
  if [[ -d "$HOME/.conda/pkgs" ]]; then
    local conda_bytes
    conda_bytes=$(du -sb "$HOME/.conda/pkgs" 2>/dev/null | cut -f1 || echo 0)
    local conda_human
    conda_human=$(numfmt --to=iec-i --suffix=B "$conda_bytes" 2>/dev/null || echo "0B")
    echo "| Conda | $conda_human | \`conda clean --all\` |"
    total=$((total + conda_bytes))
  fi

  # uv cache
  if [[ -d "$HOME/.cache/uv" ]]; then
    local uv_bytes
    uv_bytes=$(du -sb "$HOME/.cache/uv" 2>/dev/null | cut -f1 || echo 0)
    local uv_human
    uv_human=$(numfmt --to=iec-i --suffix=B "$uv_bytes" 2>/dev/null || echo "0B")
    echo "| uv | $uv_human | \`uv cache clean\` |"
    total=$((total + uv_bytes))
  fi

  # Yarn
  if [[ -d "$HOME/.yarn/cache" ]]; then
    local yarn_bytes
    yarn_bytes=$(du -sb "$HOME/.yarn/cache" 2>/dev/null | cut -f1 || echo 0)
    local yarn_human
    yarn_human=$(numfmt --to=iec-i --suffix=B "$yarn_bytes" 2>/dev/null || echo "0B")
    echo "| Yarn | $yarn_human | \`yarn cache clean\` |"
    total=$((total + yarn_bytes))
  fi

  # Go modules
  if [[ -d "$HOME/go/pkg/mod" ]]; then
    local go_bytes
    go_bytes=$(du -sb "$HOME/go/pkg/mod" 2>/dev/null | cut -f1 || echo 0)
    local go_human
    go_human=$(numfmt --to=iec-i --suffix=B "$go_bytes" 2>/dev/null || echo "0B")
    echo "| Go modules | $go_human | \`go clean -modcache\` |"
    total=$((total + go_bytes))
  fi

  # Cargo
  if [[ -d "$HOME/.cargo/registry" ]]; then
    local cargo_bytes
    cargo_bytes=$(du -sb "$HOME/.cargo/registry" 2>/dev/null | cut -f1 || echo 0)
    local cargo_human
    cargo_human=$(numfmt --to=iec-i --suffix=B "$cargo_bytes" 2>/dev/null || echo "0B")
    echo "| Cargo | $cargo_human | \`cargo cache --autoclean\` |"
    total=$((total + cargo_bytes))
  fi

  echo ""
  local total_human
  total_human=$(numfmt --to=iec-i --suffix=B "$total" 2>/dev/null || echo "0B")
  echo "**Total cache:** ~$total_human"
  echo ""

  RESULTS[caches_bytes]=$total
}

# ============================================================================
# UNUSED FILES
# Large files not accessed recently
# ============================================================================
analyze_unused() {
  local path="$1"
  [[ ! -d "$path" ]] && return

  echo "### Unused Large Files"
  echo ""
  echo "Files over ${MIN_SIZE_MB}MB not accessed in 6+ months:"
  echo ""

  local total=0
  local count=0

  echo "| Size | Last Access | File |"
  echo "|------|-------------|------|"

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local file="$line"
    local size
    size=$(stat -c%s "$file" 2>/dev/null || echo 0)
    local atime
    atime=$(stat -c%X "$file" 2>/dev/null || echo 0)
    local atime_human
    atime_human=$(date -d "@$atime" '+%Y-%m-%d' 2>/dev/null || echo "unknown")
    local size_human
    size_human=$(numfmt --to=iec-i --suffix=B "$size" 2>/dev/null || echo "${size}B")
    local basename
    basename=$(basename "$file")

    echo "| $size_human | $atime_human | ${basename:0:50} |"
    total=$((total + size))
    count=$((count + 1))
  done < <(find "$path" -type f -size "+${MIN_SIZE_MB}M" -atime +180 2>/dev/null | head -20)

  echo ""
  local total_human
  total_human=$(numfmt --to=iec-i --suffix=B "$total" 2>/dev/null || echo "0B")
  echo "**Recoverable:** $total_human ($count files shown, may be more)"
  echo ""

  RESULTS[unused_bytes]=$total
  RESULTS[unused_count]=$count
}

# ============================================================================
# ML MODELS
# Find duplicate or old model weights
# ============================================================================
analyze_models() {
  echo "### ML Model Weights"
  echo ""

  local hf_cache="$HOME/.cache/huggingface"
  local torch_cache="$HOME/.cache/torch"

  local total=0

  # HuggingFace cache
  if [[ -d "$hf_cache" ]]; then
    local hf_bytes
    hf_bytes=$(du -sb "$hf_cache" 2>/dev/null | cut -f1 || echo 0)
    local hf_human
    hf_human=$(numfmt --to=iec-i --suffix=B "$hf_bytes" 2>/dev/null || echo "0B")
    echo "**HuggingFace cache:** $hf_human"
    echo "  Path: $hf_cache"
    echo "  Clean: \`huggingface-cli delete-cache\`"
    echo ""
    total=$((total + hf_bytes))

    # List largest models
    echo "Largest cached models:"
    echo ""
    du -sh "$hf_cache"/hub/models--* 2>/dev/null | sort -rh | head -5 | while read -r size path; do
      local model
      model=$(basename "$path" | sed 's/models--//' | sed 's/--/\//g')
      echo "- $size : $model"
    done
    echo ""
  fi

  # PyTorch cache
  if [[ -d "$torch_cache" ]]; then
    local torch_bytes
    torch_bytes=$(du -sb "$torch_cache" 2>/dev/null | cut -f1 || echo 0)
    local torch_human
    torch_human=$(numfmt --to=iec-i --suffix=B "$torch_bytes" 2>/dev/null || echo "0B")
    echo "**PyTorch cache:** $torch_human"
    echo "  Path: $torch_cache"
    echo ""
    total=$((total + torch_bytes))
  fi

  # Find .gguf files (llama.cpp models)
  local gguf_files
  gguf_files=$(find "$HOME" -name "*.gguf" -size +100M 2>/dev/null | head -10)
  if [[ -n "$gguf_files" ]]; then
    echo "**GGUF models found:**"
    echo ""
    while IFS= read -r file; do
      local size
      size=$(du -sh "$file" 2>/dev/null | cut -f1)
      echo "- $size : $file"
    done <<< "$gguf_files"
    echo ""
  fi

  local total_human
  total_human=$(numfmt --to=iec-i --suffix=B "$total" 2>/dev/null || echo "0B")
  echo "**Total model cache:** $total_human"
  echo ""

  RESULTS[models_bytes]=$total
}

# ============================================================================
# MAIN
# ============================================================================

echo "## Storage Slim Report"
echo ""
echo "**Scan path:** $SCAN_PATH"
echo "**Min file size:** ${MIN_SIZE_MB} MB"
echo "**Generated:** $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

[[ "$CHECK_MEDIA" == "true" ]] && analyze_media "$SCAN_PATH"
[[ "$CHECK_DUPLICATES" == "true" ]] && analyze_duplicates "$SCAN_PATH"
[[ "$CHECK_CACHES" == "true" ]] && analyze_caches
[[ "$CHECK_UNUSED" == "true" ]] && analyze_unused "$SCAN_PATH"
[[ "$CHECK_MODELS" == "true" ]] && analyze_models

# Summary
echo "---"
echo ""
echo "## Summary"
echo ""
echo "| Category | Recoverable | Files |"
echo "|----------|-------------|-------|"

total_bytes=0

if [[ "$CHECK_MEDIA" == "true" ]]; then
  media_human=$(numfmt --to=iec-i --suffix=B "${RESULTS[media_bytes]}" 2>/dev/null || echo "0B")
  echo "| Media (lower quality) | $media_human | ${RESULTS[media_count]} |"
  total_bytes=$((total_bytes + RESULTS[media_bytes]))
fi

if [[ "$CHECK_DUPLICATES" == "true" ]]; then
  dup_human=$(numfmt --to=iec-i --suffix=B "${RESULTS[duplicates_bytes]}" 2>/dev/null || echo "0B")
  echo "| Exact duplicates | $dup_human | ${RESULTS[duplicates_count]} |"
  total_bytes=$((total_bytes + RESULTS[duplicates_bytes]))
fi

if [[ "$CHECK_CACHES" == "true" ]]; then
  cache_human=$(numfmt --to=iec-i --suffix=B "${RESULTS[caches_bytes]}" 2>/dev/null || echo "0B")
  echo "| Caches | $cache_human | - |"
  total_bytes=$((total_bytes + RESULTS[caches_bytes]))
fi

if [[ "$CHECK_UNUSED" == "true" ]]; then
  unused_human=$(numfmt --to=iec-i --suffix=B "${RESULTS[unused_bytes]}" 2>/dev/null || echo "0B")
  echo "| Unused (6+ months) | $unused_human | ${RESULTS[unused_count]}+ |"
  total_bytes=$((total_bytes + RESULTS[unused_bytes]))
fi

if [[ "$CHECK_MODELS" == "true" ]]; then
  models_human=$(numfmt --to=iec-i --suffix=B "${RESULTS[models_bytes]}" 2>/dev/null || echo "0B")
  echo "| ML model caches | $models_human | - |"
  total_bytes=$((total_bytes + RESULTS[models_bytes]))
fi

total_human=$(numfmt --to=iec-i --suffix=B "$total_bytes" 2>/dev/null || echo "0B")
echo "| **Total** | **$total_human** | |"
echo ""

echo "### Quick Actions"
echo ""
echo "\`\`\`bash"
echo "# Clean caches (safe)"
echo "pip cache purge"
echo "npm cache clean --force"
echo "docker system prune -a"
echo ""
echo "# Review media duplicates"
echo "./run.sh slim --media"
echo ""
echo "# Full duplicate verification"
echo "./run.sh duplicates"
echo "\`\`\`"
