#!/usr/bin/env bash
set -euo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
# Dependencies are provisioned explicitly as the owner, never downloaded with sudo.
PYTHON="${SERVICE_PRIVACY_PYTHON:-python3}"
exec "$PYTHON" -B -m service_privacy "$@"
