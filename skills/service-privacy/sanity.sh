#!/usr/bin/env bash
set -euo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
PYTHON="${SERVICE_PRIVACY_PYTHON:-python3}"
exec "$PYTHON" -B -m pytest -q tests "$@"
