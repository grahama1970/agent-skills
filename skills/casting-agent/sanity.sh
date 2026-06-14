#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/run.sh" sanity
ARTIFACT_ROOT="${CASTING_AGENT_SANITY_ROOT:-/mnt/storage12tb/skills/casting-agent/outputs/sanity-e2e/latest}"
rm -rf "$ARTIFACT_ROOT"
mkdir -p "$ARTIFACT_ROOT"
"$SCRIPT_DIR/run.sh" sanity-e2e --artifact-root "$ARTIFACT_ROOT"
