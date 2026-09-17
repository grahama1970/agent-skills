#!/usr/bin/env bash
# Deterministic non-root drift self-test (#1746). Captures a LIVE
# QualifiedSnapshot, stores it as a TEMP baseline via SERVICE_PRIVACY_BASELINE,
# then (a) re-diffs an unchanged snapshot -> NO_CHANGE and (b) diffs a snapshot
# with a mutated launcher sha -> REQUALIFICATION_REQUIRED naming the launcher
# hash. Uses only capture + diff_against_baseline/diff_snapshots; the automatic
# path is notify-only, so this script must never apply/execute anything.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
PYTHON="${SERVICE_PRIVACY_PYTHON:-python3}"

TMPDIR_BASE="$(mktemp -d /tmp/1746-drift-selftest.XXXXXX)"
trap 'rm -rf "$TMPDIR_BASE"' EXIT

SERVICE_PRIVACY_BASELINE="$TMPDIR_BASE/baseline.json" "$PYTHON" -B - <<'PY'
import copy
import json
import os
import tempfile
from pathlib import Path

from service_privacy import change
from service_privacy.change import capture, diff_against_baseline, diff_snapshots

UNIT = 'launcher.kolide-k2.service'
baseline = capture(UNIT)

# 1. In-process: unchanged snapshot -> NO_CHANGE.
d, changed = diff_snapshots(baseline, baseline)
assert d == 'NO_CHANGE', f'unchanged snapshot gave {d}'
print('self-test unchanged (in-process): NO_CHANGE OK')

# 2. In-process: mutated launcher sha -> REQUALIFICATION_REQUIRED naming launcher.
mutated = copy.deepcopy(baseline)
mutated.launcher = mutated.launcher.model_copy(update={'sha256': 'f' * 64})
d2, changed2 = diff_snapshots(mutated, baseline)
assert d2 == 'REQUALIFICATION_REQUIRED', f'mutated snapshot gave {d2}'
assert any(c.startswith('launcher:') and baseline.launcher.sha256 in c and 'f' * 64 in c
           for c in changed2), f'changed did not name the launcher hash: {changed2}'
print(f'self-test mutated (in-process): REQUALIFICATION_REQUIRED OK changed={changed2}')

# 3. Temp-baseline path (SERVICE_PRIVACY_BASELINE): record -> replay through
#    diff_against_baseline, the same code path watch-detect uses.
Path(change.baseline_path()).parent.mkdir(parents=True, exist_ok=True)
change.baseline_path().write_bytes(change.canonical(baseline) + b'\n')
r_unchanged = diff_against_baseline(capture(UNIT))
assert r_unchanged.disposition == 'NO_CHANGE', r_unchanged.disposition
r_drift = diff_against_baseline(mutated)
assert r_drift.disposition == 'REQUALIFICATION_REQUIRED', r_drift.disposition
assert any('launcher:' in c for c in r_drift.changed), r_drift.changed
print(f'self-test temp baseline: NO_CHANGE OK then REQUALIFICATION_REQUIRED OK '
      f'changed={r_drift.changed}')

print('drift-selftest PASS: NO_CHANGE on unchanged, REQUALIFICATION_REQUIRED on '
      'mutated launcher, no apply/execute actions performed')
PY
