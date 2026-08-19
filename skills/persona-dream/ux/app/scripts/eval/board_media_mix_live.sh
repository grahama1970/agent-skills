#!/usr/bin/env bash
# Live probe: recall + hydrate against http://127.0.0.1:3001 (memory daemon via
# explorer API), then assert the stratified 12-card board keeps image, video,
# and audio. See board_media_mix_live.probe.ts.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
exec node board_media_mix_live.mjs "$@"
