#!/usr/bin/env bash
# Sync vendored surf-cli from the Embry fork (git remote or local checkout).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=scripts/lib/surf-cli-path.sh
source "${SKILL_DIR}/scripts/lib/surf-cli-path.sh"

FORK_JSON="${SKILL_DIR}/vendor/fork.json"
VENDOR_DIR="${SURF_CLI_PATH}"
LOCK_FILE="${VENDOR_DIR}/VENDOR.lock.json"
CACHE_DIR="${SKILL_DIR}/.vendor-cache/surf-cli"

FROM=""
REF=""
JSON=false
BUILD=false
RELOAD=false
DRY_RUN=false

usage() {
  cat <<EOF
Usage: surf vendor.sync [options]

Sync vendor/surf-cli from the Embry fork.

Options:
  --from PATH     Local fork checkout (default: fork.json local_dev_path if present)
  --ref REF       Git ref when syncing from remote (default: fork.json default_ref)
  --git           Force sync from fork_repo via shallow clone cache
  --build         Run extension.build after sync
  --reload        Run extension.reload after build (implies --build)
  --dry-run       Show rsync plan without copying
  --json          Emit lock metadata as JSON on stdout
  -h, --help      Show this help

Examples:
  surf vendor.sync --from ~/workspace/experiments/surf-cli --build --reload
  surf vendor.sync --git --ref main --build
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from) FROM="$2"; shift 2 ;;
    --ref) REF="$2"; shift 2 ;;
    --git) FROM="__git__"; shift ;;
    --build) BUILD=true; shift ;;
    --reload) BUILD=true; RELOAD=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --json) JSON=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ ! -f "$FORK_JSON" ]]; then
  echo "Error: missing $FORK_JSON" >&2
  exit 1
fi

read_config() {
  python3 - "$FORK_JSON" "$1" << 'PY'
import json, sys
cfg = json.load(open(sys.argv[1]))
key = sys.argv[2]
print(cfg.get(key, ""))
PY
}

FORK_REPO="$(read_config fork_repo)"
DEFAULT_REF="$(read_config default_ref)"
LOCAL_DEV="$(read_config local_dev_path)"
[[ -n "$REF" ]] || REF="$DEFAULT_REF"

if [[ -z "$FROM" ]]; then
  if [[ -n "$LOCAL_DEV" && -d "$LOCAL_DEV" ]]; then
    FROM="$LOCAL_DEV"
  else
    FROM="__git__"
  fi
fi

SOURCE_KIND="local"
SOURCE_PATH=""
SOURCE_REF=""
SOURCE_COMMIT=""

if [[ "$FROM" == "__git__" ]]; then
  SOURCE_KIND="git"
  SOURCE_PATH="$FORK_REPO"
  mkdir -p "$(dirname "$CACHE_DIR")"
  if [[ -d "$CACHE_DIR/.git" ]]; then
    echo "Fetching $FORK_REPO ($REF)..." >&2
    git -C "$CACHE_DIR" fetch --depth 1 origin "$REF" >&2
    git -C "$CACHE_DIR" checkout FETCH_HEAD >&2
  else
    echo "Cloning $FORK_REPO ($REF)..." >&2
    rm -rf "$CACHE_DIR"
    git clone --depth 1 --branch "$REF" "$FORK_REPO" "$CACHE_DIR" >&2
  fi
  FROM="$CACHE_DIR"
  SOURCE_REF="$REF"
  SOURCE_COMMIT="$(git -C "$CACHE_DIR" rev-parse HEAD)"
else
  FROM="$(cd "$FROM" && pwd)"
  if [[ ! -f "$FROM/package.json" ]]; then
    echo "Error: $FROM does not look like surf-cli (no package.json)" >&2
    exit 1
  fi
  if [[ -d "$FROM/.git" ]]; then
    SOURCE_COMMIT="$(git -C "$FROM" rev-parse HEAD)"
    SOURCE_REF="$(git -C "$FROM" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  fi
  SOURCE_PATH="$FROM"
fi

EXCLUDES=()
while IFS= read -r line; do
  [[ -n "$line" ]] && EXCLUDES+=(--exclude "$line")
done < <(python3 - "$FORK_JSON" << 'PY'
import json, sys
for item in json.load(open(sys.argv[1])).get("rsync_excludes", []):
    print(item)
PY
)

mkdir -p "$VENDOR_DIR"
RSYNC_FLAGS=(-a --delete "${EXCLUDES[@]}")
if $DRY_RUN; then
  RSYNC_FLAGS+=(--dry-run --itemize-changes)
fi

echo "Syncing surf-cli → ${VENDOR_DIR}" >&2
echo "  source: ${SOURCE_PATH} (${SOURCE_KIND})" >&2
[[ -n "$SOURCE_COMMIT" ]] && echo "  commit: ${SOURCE_COMMIT}" >&2

rsync "${RSYNC_FLAGS[@]}" "${FROM}/" "${VENDOR_DIR}/"

if ! $DRY_RUN; then
  RECORDED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  VERSION="$(python3 - <<PY
import json
try:
    print(json.load(open("${VENDOR_DIR}/package.json")).get("version", ""))
except Exception:
    print("")
PY
)"
  python3 - "$LOCK_FILE" "$VENDOR_DIR" "$FORK_JSON" << PY
import hashlib, json, pathlib, sys

lock_path = pathlib.Path(sys.argv[1])
vendor = pathlib.Path(sys.argv[2])
fork_json = pathlib.Path(sys.argv[3])
excludes = ["VENDOR.lock.json"]
try:
    cfg = json.loads(fork_json.read_text())
    excludes.extend(cfg.get("rsync_excludes") or [])
except Exception:
    pass

def is_excluded(path):
    rel = path.relative_to(vendor).as_posix()
    for item in excludes:
        item = str(item).strip().rstrip("/")
        if not item:
            continue
        if rel == item or rel.startswith(item + "/"):
            return True
    return False

digest = hashlib.sha256()
files = sorted(
    path for path in vendor.rglob("*")
    if path.is_file() and not is_excluded(path)
)
for path in files:
    data = path.read_bytes()
    digest.update(path.relative_to(vendor).as_posix().encode())
    digest.update(b"\0")
    digest.update(str(len(data)).encode())
    digest.update(b"\0")
    digest.update(data)
lock = {
    "recorded_at": "${RECORDED_AT}",
    "source_kind": "${SOURCE_KIND}",
    "source_path": "${SOURCE_PATH}",
    "source_ref": "${SOURCE_REF}",
    "source_repository": "${FORK_REPO}",
    "upstream_base_commit": "${SOURCE_COMMIT}",
    "clean_upstream_copy": False,
    "package_version": "${VERSION}",
    "content_identity": {
        "algorithm": "sha256(relative_path_nul_size_nul_content)",
        "excludes": sorted(set(excludes)),
        "file_count": len(files),
        "sha256": digest.hexdigest(),
    },
}
lock_path.write_text(json.dumps(lock, indent=2) + "\n")
print(json.dumps(lock, indent=2))
PY
fi

if $BUILD && ! $DRY_RUN; then
  "${SKILL_DIR}/scripts/ensure-surf-cli.sh"
fi

if $RELOAD && ! $DRY_RUN; then
  "${SKILL_DIR}/scripts/extension-reload.sh"
fi

if $JSON && [[ -f "$LOCK_FILE" ]]; then
  cat "$LOCK_FILE"
fi
