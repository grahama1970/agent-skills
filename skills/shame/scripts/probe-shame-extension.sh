#!/usr/bin/env bash
set -euo pipefail
cd /home/graham/workspace/experiments/agent-skills
node skills/shame/scripts/probe-shame-extension.mjs "$@"
