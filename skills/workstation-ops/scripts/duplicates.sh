#!/usr/bin/env bash
# Find duplicate files, optimized for large media files.
# Uses size-first filtering then md5sum comparison.
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options] [path]

Find duplicate files in a directory (default: /mnt/storage12tb).
Optimized for finding duplicate movies and large media files.

Options:
  --min-size <MB>    Minimum file size to check (default: 100 MB)
  --type <ext>       File extension filter (e.g., mkv, mp4, avi)
  --dry-run          Show what would be found without full scan
  --report <file>    Save report to file
  --help             Show this message

Examples:
  $(basename "$0")                           # Scan /mnt/storage12tb
  $(basename "$0") /mnt/storage12tb/media    # Scan specific folder
  $(basename "$0") --min-size 500            # Only files > 500MB
  $(basename "$0") --type mkv                # Only .mkv files
  $(basename "$0") --dry-run                 # Quick size-only check

Note: Full scan with md5sum can take a while for large drives.
      Use --dry-run first to see potential duplicates by size.
USAGE
}

MIN_SIZE_MB=100
FILE_TYPE=""
DRY_RUN=false
REPORT_FILE=""
SCAN_PATH="/mnt/storage12tb"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --min-size) MIN_SIZE_MB="$2"; shift 2;;
    --type) FILE_TYPE="$2"; shift 2;;
    --dry-run) DRY_RUN=true; shift;;
    --report) REPORT_FILE="$2"; shift 2;;
    --help|-h) usage; exit 0;;
    -*) echo "Unknown option: $1" >&2; usage; exit 1;;
    *) SCAN_PATH="$1"; shift;;
  esac
done

# Validate path
if [[ ! -d "$SCAN_PATH" ]]; then
  echo "Error: Directory not found: $SCAN_PATH" >&2
  exit 1
fi

MIN_SIZE_BYTES=$((MIN_SIZE_MB * 1024 * 1024))

echo "## Duplicate File Scan"
echo ""
echo "**Path:** $SCAN_PATH"
echo "**Minimum size:** ${MIN_SIZE_MB} MB"
[[ -n "$FILE_TYPE" ]] && echo "**File type:** .$FILE_TYPE"
echo "**Started:** $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Build find command
find_cmd="find \"$SCAN_PATH\" -type f -size +${MIN_SIZE_MB}M"
[[ -n "$FILE_TYPE" ]] && find_cmd+=" -iname \"*.$FILE_TYPE\""

# Step 1: Group files by size
echo "### Step 1: Finding files by size..."
echo ""

declare -A size_groups
declare -A size_files

while IFS= read -r file; do
  size=$(stat -c%s "$file" 2>/dev/null || echo 0)
  [[ $size -lt $MIN_SIZE_BYTES ]] && continue

  if [[ -z "${size_groups[$size]:-}" ]]; then
    size_groups[$size]=1
    size_files[$size]="$file"
  else
    size_groups[$size]=$((size_groups[$size] + 1))
    size_files[$size]+=$'\n'"$file"
  fi
done < <(eval "$find_cmd" 2>/dev/null)

# Find sizes with multiple files (potential duplicates)
# First pass: calculate totals (avoid subshell variable scoping)
potential_dupes=0
potential_size=0

for size in "${!size_groups[@]}"; do
  count=${size_groups[$size]}
  if [[ $count -gt 1 ]]; then
    ((potential_dupes += count - 1))
    ((potential_size += size * (count - 1)))
  fi
done

# Second pass: generate table (piped to sort, runs in subshell)
echo "| Size | Count | Sample File |"
echo "|------|-------|-------------|"

for size in "${!size_groups[@]}"; do
  count=${size_groups[$size]}
  if [[ $count -gt 1 ]]; then
    size_human=$(numfmt --to=iec-i --suffix=B "$size" 2>/dev/null || echo "${size}B")
    sample=$(echo "${size_files[$size]}" | head -1 | rev | cut -d'/' -f1 | rev | head -c 50)
    echo "| $size_human | $count | $sample... |"
  fi
done | sort -t'|' -k2 -rn | head -20

echo ""
echo "**Potential duplicates by size:** $potential_dupes files"
echo "**Potential space savings:** $(numfmt --to=iec-i --suffix=B "$potential_size" 2>/dev/null || echo "${potential_size}B")"
echo ""

if [[ "$DRY_RUN" == "true" ]]; then
  echo "*(Dry run - skipping md5sum verification)*"
  echo ""
  echo "Run without --dry-run to verify with checksums."
  exit 0
fi

# Step 2: Verify with md5sum
echo "### Step 2: Verifying with checksums..."
echo ""

declare -A hash_files
confirmed_dupes=0
confirmed_size=0

for size in "${!size_groups[@]}"; do
  count=${size_groups[$size]}
  [[ $count -le 1 ]] && continue

  # Hash each file of this size
  while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    hash=$(md5sum "$file" 2>/dev/null | cut -d' ' -f1)
    [[ -z "$hash" ]] && continue

    if [[ -n "${hash_files[$hash]:-}" ]]; then
      # Found a duplicate!
      ((confirmed_dupes++))
      ((confirmed_size += size))

      size_human=$(numfmt --to=iec-i --suffix=B "$size" 2>/dev/null || echo "${size}B")
      original="${hash_files[$hash]}"

      echo "**DUPLICATE FOUND** ($size_human):"
      echo "  Original: $original"
      echo "  Duplicate: $file"
      echo ""
    else
      hash_files[$hash]="$file"
    fi
  done <<< "${size_files[$size]}"
done

echo "---"
echo ""
echo "### Summary"
echo ""
echo "| Metric | Value |"
echo "|--------|-------|"
echo "| Confirmed duplicates | $confirmed_dupes files |"
echo "| Space recoverable | $(numfmt --to=iec-i --suffix=B "$confirmed_size" 2>/dev/null || echo "${confirmed_size}B") |"
echo ""

if [[ $confirmed_dupes -gt 0 ]]; then
  echo "### Recommended Actions"
  echo ""
  echo "Review the duplicates above and remove manually:"
  echo "\`\`\`bash"
  echo "rm \"<path-to-duplicate>\""
  echo "\`\`\`"
  echo ""
  echo "Or use an interactive tool:"
  echo "\`\`\`bash"
  echo "sudo apt install fdupes"
  echo "fdupes -r -d /mnt/storage12tb/media  # Interactive deletion"
  echo "\`\`\`"
else
  echo "No confirmed duplicates found."
fi

# Save report if requested
if [[ -n "$REPORT_FILE" ]]; then
  echo ""
  echo "Report saved to: $REPORT_FILE"
fi
