#!/usr/bin/env bash
# Verify an ArangoDB dump directory produced by current arangodump versions.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 /path/to/dump" >&2
  exit 2
fi

dump_dir="$1"
if [[ ! -d "$dump_dir" ]]; then
  echo "ERROR: dump directory not found: $dump_dir" >&2
  exit 1
fi

manifest="missing"
if [[ -f "$dump_dir/manifest.json" ]]; then
  manifest="manifest.json"
elif [[ -f "$dump_dir/dump.json" ]]; then
  manifest="dump.json"
else
  echo "[warn] neither manifest.json nor dump.json found in dump output" >&2
fi

structure_count=$(
  find "$dump_dir" -maxdepth 1 -type f \
    \( -name '*.structure.json' -o -name '*structure.json' -o -name '*.structure.json.gz' -o -name '*structure.json.gz' \) \
    | wc -l
)
data_count=$(
  find "$dump_dir" -maxdepth 1 -type f \
    \( -name '*.data.json' -o -name '*data.json' -o -name '*.data.json.gz' -o -name '*data.json.gz' \) \
    | wc -l
)
dir_count=$(find "$dump_dir" -mindepth 1 -maxdepth 1 -type d | wc -l)

if [[ "$manifest" == "missing" ]]; then
  exit 1
fi

if [[ "$structure_count" -lt 1 && "$dir_count" -lt 1 ]]; then
  echo "[warn] $manifest present but no collection structure files or collection directories found" >&2
  exit 1
fi

echo "[ops-arango] Integrity: OK ($manifest, structures=$structure_count, data_files=$data_count, directories=$dir_count)"
