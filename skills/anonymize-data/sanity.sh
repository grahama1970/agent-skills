#!/usr/bin/env bash
# Exercise the real project matrix THROUGH this wrapper; no copied engine/tests.
# Includes real READY-release relative/symlink rejection and private work controls.
set -euo pipefail
unset VIRTUAL_ENV PYTHONPATH
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="${ANONYMIZE_DATA_ROOT:-${HOME}/workspace/experiments/oai-trial}"
export ANONYMIZE_DATA_ROOT="$ROOT"
export ANONYMIZE_DATA_TEST_RUNNER="$HERE/run.sh"
export TMPDIR="${ANONYMIZE_DATA_WORK_DIR:-/mnt/storage12tb/skills/anonymize-data/work}"
mkdir -p "$TMPDIR"
uv run --project "$ROOT" --extra dev --extra discovery python -m pytest -q \
  "$ROOT/tests/test_discovery.py" "$ROOT/tests/test_discovery_boundaries.py" "$@"
# Wrapper-specific negative control: an installed package from another project
# must be refused even when a lookalike checkout contains an entrypoint marker.
python3 - <<'PY'
import os, pathlib, subprocess, tempfile
root = pathlib.Path(os.environ['ANONYMIZE_DATA_ROOT']).resolve()
runner = os.environ['ANONYMIZE_DATA_TEST_RUNNER']
with tempfile.TemporaryDirectory(prefix='wrong-install-') as directory:
    fake = pathlib.Path(directory)
    (fake/'src/anonymization_trial').mkdir(parents=True)
    (fake/'src/anonymization_trial/__main__.py').write_text('# marker only\n')
    (fake/'.venv').symlink_to(root/'.venv', target_is_directory=True)
    result = subprocess.run([runner, '--help'], capture_output=True, text=True,
                            env={**os.environ, 'ANONYMIZE_DATA_ROOT': str(fake)}, timeout=30)
    if result.returncode == 0 or 'anonymize_data_wrong_install' not in result.stderr:
        raise SystemExit('wrong installed project was not refused')
print('WRAPPER_BOUNDARY_PASS')
PY
