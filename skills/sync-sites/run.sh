#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UV="${UV:-uv}"

# Default OSTree repo path
OSTREE_REPO="${OSTREE_REPO:-/ostree/repo}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

usage() {
    cat <<'EOF'
Usage: run.sh <subcommand> [options]

Subcommands:
  status                Show current OSTree deployment status
  generate-delta        Generate a static delta between two commits
  apply-delta           Apply a static delta from removable media
  verify-signature      Verify GPG/ed25519 signature on a delta file

Global options:
  --dry-run             Simulate without requiring ostree/rpm-ostree
  -h, --help            Show this help message
EOF
    exit 0
}

require_tool() {
    local tool="$1"
    if ! command -v "$tool" &>/dev/null; then
        echo "ERROR: '$tool' is not installed or not in PATH." >&2
        echo "This command requires '$tool' to run in real mode." >&2
        echo "Use --dry-run to simulate on systems without '$tool'." >&2
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

cmd_status() {
    local dry_run=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run) dry_run=true; shift ;;
            -h|--help)
                echo "Usage: run.sh status [--dry-run]"
                exit 0
                ;;
            *) echo "Unknown option: $1" >&2; exit 1 ;;
        esac
    done

    if $dry_run; then
        cat <<'EOF'
{
  "deployments": [
    {
      "hash": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
      "origin": "embry-os:fedora/41/x86_64/kinoite",
      "refspec": "embry-os:fedora/41/x86_64/kinoite",
      "version": "41.20260219.0",
      "booted": true,
      "staged": false
    }
  ]
}
EOF
        return 0
    fi

    require_tool rpm-ostree
    rpm-ostree status --json
}

# ---------------------------------------------------------------------------
# generate-delta
# ---------------------------------------------------------------------------

cmd_generate_delta() {
    local from_commit=""
    local to_commit=""
    local output=""
    local dry_run=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --from) from_commit="$2"; shift 2 ;;
            --to) to_commit="$2"; shift 2 ;;
            --output) output="$2"; shift 2 ;;
            --dry-run) dry_run=true; shift ;;
            -h|--help)
                echo "Usage: run.sh generate-delta --from COMMIT --to COMMIT [--output PATH] [--dry-run]"
                exit 0
                ;;
            *) echo "Unknown option: $1" >&2; exit 1 ;;
        esac
    done

    if [[ -z "$from_commit" || -z "$to_commit" ]]; then
        echo "ERROR: --from and --to are required." >&2
        echo "Usage: run.sh generate-delta --from COMMIT --to COMMIT [--output PATH] [--dry-run]" >&2
        exit 1
    fi

    if $dry_run; then
        echo "DRY-RUN: Would generate static delta:"
        echo "  From: $from_commit"
        echo "  To:   $to_commit"
        echo "  Repo: $OSTREE_REPO"
        [[ -n "$output" ]] && echo "  Output: $output"
        echo "  Command: ostree static-delta generate --repo=$OSTREE_REPO --from=$from_commit --to=$to_commit"
        return 0
    fi

    require_tool ostree

    local cmd=(ostree static-delta generate "--repo=$OSTREE_REPO" "--from=$from_commit" "--to=$to_commit")
    [[ -n "$output" ]] && cmd+=(--inline --to-file="$output")

    echo "Generating static delta..."
    echo "  From: $from_commit"
    echo "  To:   $to_commit"
    "${cmd[@]}"
    echo "Static delta generated successfully."
}

# ---------------------------------------------------------------------------
# apply-delta
# ---------------------------------------------------------------------------

cmd_apply_delta() {
    local delta_file=""
    local dry_run=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run) dry_run=true; shift ;;
            -h|--help)
                echo "Usage: run.sh apply-delta DELTA_FILE [--dry-run]"
                exit 0
                ;;
            -*)  echo "Unknown option: $1" >&2; exit 1 ;;
            *)   delta_file="$1"; shift ;;
        esac
    done

    if [[ -z "$delta_file" ]]; then
        echo "ERROR: DELTA_FILE is required." >&2
        echo "Usage: run.sh apply-delta DELTA_FILE [--dry-run]" >&2
        exit 1
    fi

    if $dry_run; then
        echo "DRY-RUN: Would apply static delta:"
        echo "  Delta file: $delta_file"
        echo "  Step 1: ostree static-delta apply-offline --repo=$OSTREE_REPO $delta_file"
        echo "  Step 2: rpm-ostree upgrade --cache-only"
        echo "  Step 3: Reboot to activate new deployment"
        return 0
    fi

    if [[ ! -f "$delta_file" ]]; then
        echo "ERROR: Delta file not found: $delta_file" >&2
        exit 1
    fi

    require_tool ostree
    require_tool rpm-ostree

    echo "Applying static delta: $delta_file"
    echo "Step 1: Ingesting delta into local repo..."
    ostree static-delta apply-offline --repo="$OSTREE_REPO" "$delta_file"

    echo "Step 2: Upgrading via rpm-ostree..."
    rpm-ostree upgrade --cache-only

    echo "Static delta applied successfully."
    echo "Reboot to activate the new deployment."
}

# ---------------------------------------------------------------------------
# verify-signature
# ---------------------------------------------------------------------------

cmd_verify_signature() {
    local delta_file=""
    local dry_run=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run) dry_run=true; shift ;;
            -h|--help)
                echo "Usage: run.sh verify-signature DELTA_FILE [--dry-run]"
                exit 0
                ;;
            -*)  echo "Unknown option: $1" >&2; exit 1 ;;
            *)   delta_file="$1"; shift ;;
        esac
    done

    if [[ -z "$delta_file" ]]; then
        echo "ERROR: DELTA_FILE is required." >&2
        echo "Usage: run.sh verify-signature DELTA_FILE [--dry-run]" >&2
        exit 1
    fi

    if $dry_run; then
        cat <<EOF
SIGNATURE VERIFICATION: PASS
  Delta file: $delta_file
  Signature type: ed25519
  Key ID: embry-os-release-2026
  Fingerprint: SHA256:a1b2c3d4e5f6...7890abcdef
  Signed by: Embry OS Build System <build@embry-os.local>
  Signed at: 2026-02-19T12:00:00Z
  Trust level: FULL (key in local trusted keyring)
EOF
        return 0
    fi

    if [[ ! -f "$delta_file" ]]; then
        echo "ERROR: Delta file not found: $delta_file" >&2
        exit 1
    fi

    require_tool ostree

    echo "Verifying signature on: $delta_file"
    ostree gpg-sign --verify --repo="$OSTREE_REPO" "$delta_file"
    echo "Signature verification complete."
}

# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

if [[ $# -eq 0 ]]; then
    usage
fi

case "$1" in
    status)           shift; cmd_status "$@" ;;
    generate-delta)   shift; cmd_generate_delta "$@" ;;
    apply-delta)      shift; cmd_apply_delta "$@" ;;
    verify-signature) shift; cmd_verify_signature "$@" ;;
    -h|--help)        usage ;;
    *)
        echo "Unknown subcommand: $1" >&2
        usage
        ;;
esac
