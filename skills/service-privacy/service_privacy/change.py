"""Typed Kolide change snapshots and fail-closed diff receipts.

A snapshot binds the launcher, osqueryd, observed helper executables, unit
text and rendered AppArmor profile to one host. Root-only observations degrade
to a typed ROOT_REQUIRED status instead of crashing; an absent or unreadable
baseline is NO_BASELINE, never NO_CHANGE.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic import ValidationError

from .core import (Blocked, STATE, canonical, checked, host_binding, load, now, read_private,
                   replace_private, root_required, secure_dir, sha, tool)
from .models import ChangeReceipt, Executable, QualifiedSnapshot
from .system import cgroup_pids, digest_executable, native_properties, unit_name

BASELINE = STATE / 'qualified-snapshot.json'
SHOW_KEYS = ['Id', 'LoadState', 'ActiveState', 'ControlGroup', 'ExecStart']


def profile_path(unit: str) -> Path:
    return Path('/etc/apparmor.d') / ('osp-' + sha(unit.encode())[:20])


def _launcher_path(properties: dict[str, str]) -> str:
    found = re.findall(r'(?:^|\{\s*)path=([^ ;]+)\s*;', properties['ExecStart'])
    if not found:
        raise Blocked('EXECUTABLE_IDENTITY_UNPARSABLE')
    return str(Path(found[0]).resolve(strict=True))


def _observe_unit_text(unit: str) -> tuple[str, str | None]:
    try:
        text = checked([tool('systemctl'), 'cat', '--no-pager', '--', unit]).stdout
        return 'HASHED', sha(text.encode())
    except Blocked:
        # Non-root cannot read root-only drop-ins; degrade, never crash.
        return 'ROOT_REQUIRED', None


def _observe_profile(unit: str) -> tuple[str, str | None]:
    path = profile_path(unit)
    if not path.exists():
        return 'NOT_PRESENT', None
    try:
        return 'HASHED', sha(read_private(path))
    except (Blocked, OSError):
        return 'ROOT_REQUIRED', None


def _observe_helpers(control_group: str) -> tuple[str, list[Executable]]:
    try:
        paths = set()
        for pid in cgroup_pids(control_group):
            paths.add(os.readlink(Path('/proc') / str(pid) / 'exe'))
        return 'OBSERVED', [digest_executable(p) for p in sorted(paths)]
    except (Blocked, OSError):
        # /proc/<pid>/exe of root processes is root-only; degrade.
        return 'ROOT_REQUIRED', []


def capture(unit: str) -> QualifiedSnapshot:
    unit_name(unit)
    result = checked([tool('systemctl'), 'show', '--no-pager', '--property=' + ','.join(SHOW_KEYS), '--', unit])
    properties = native_properties(result.stdout, set(SHOW_KEYS))
    if properties.get('Id') != unit or properties.get('LoadState') != 'loaded':
        raise Blocked('CANONICAL_LOADED_UNIT_REQUIRED')
    launcher = digest_executable(_launcher_path(properties))
    helpers_status, helpers = _observe_helpers(properties.get('ControlGroup', ''))
    osqueryd = next((item for item in helpers if 'osqueryd' in Path(item.path).name), None)
    unit_text_status, unit_text_sha = _observe_unit_text(unit)
    profile_status, profile_sha = _observe_profile(unit)
    return QualifiedSnapshot(unit=unit, launcher=launcher, osqueryd=osqueryd,
                            helper_executables=[item for item in helpers if item is not osqueryd],
                            helpers_status=helpers_status,
                            unit_text_sha256=unit_text_sha, unit_text_status=unit_text_status,
                            profile_sha256=profile_sha, profile_status=profile_status,
                            host_binding=host_binding(), created_at=now())


def _compared(snapshot: QualifiedSnapshot) -> dict[str, str | None]:
    """Comparable field tokens; root-degraded observations are None."""
    launcher = snapshot.launcher.path + '@' + snapshot.launcher.sha256
    osqueryd = (snapshot.osqueryd.path + '@' + snapshot.osqueryd.sha256) if snapshot.osqueryd else 'ABSENT'
    helpers = (','.join(item.path + '@' + item.sha256 for item in snapshot.helper_executables
                        + ([snapshot.osqueryd] if snapshot.osqueryd else []))
               if snapshot.helpers_status == 'OBSERVED' else None)
    return {'launcher': launcher, 'osqueryd': osqueryd, 'helpers': helpers,
            'unit_text_sha256': snapshot.unit_text_sha256, 'profile_sha256': snapshot.profile_sha256,
            'host_binding': snapshot.host_binding}


def diff_snapshots(current: QualifiedSnapshot, baseline: QualifiedSnapshot) -> tuple[str, list[str]]:
    """Pure disposition logic: changed fields win, degraded fields stay INCONCLUSIVE."""
    if baseline.unit != current.unit:
        return 'INCONCLUSIVE', ['baseline_unit:' + baseline.unit + '->' + current.unit]
    changed: list[str] = []
    degraded = False
    for field, new in _compared(current).items():
        old = _compared(baseline)[field]
        if old is None or new is None:
            if old != new:
                degraded = True
            continue
        if old != new:
            changed.append(field + ':' + old + '->' + new)
    if changed:
        return 'REQUALIFICATION_REQUIRED', changed
    return 'INCONCLUSIVE' if degraded else 'NO_CHANGE', changed


def _receipt(snapshot: QualifiedSnapshot, disposition: str, changed: list[str],
             baseline_bytes: bytes | None) -> ChangeReceipt:
    return ChangeReceipt(unit=snapshot.unit, disposition=disposition, changed=changed,  # type: ignore[arg-type]
                         baseline_sha256=sha(baseline_bytes) if baseline_bytes else None,
                         snapshot_sha256=sha(canonical(snapshot)), host_binding=snapshot.host_binding,
                         created_at=now())


def diff_against_baseline(current: QualifiedSnapshot) -> ChangeReceipt:
    try:
        baseline_bytes = read_private(BASELINE)
    except (OSError, Blocked):
        # Absent or unreadable baseline fails closed; never a silent NO_CHANGE.
        return _receipt(current, 'NO_BASELINE', [], None)
    try:
        baseline = load(BASELINE, QualifiedSnapshot)
    except ValidationError:
        return _receipt(current, 'INCONCLUSIVE', ['baseline_schema_rejected'], baseline_bytes)
    disposition, changed = diff_snapshots(current, baseline)
    return _receipt(current, disposition, changed, baseline_bytes)


def record_baseline(snapshot: QualifiedSnapshot) -> None:
    root_required()
    secure_dir(STATE, require_root=True)
    replace_private(BASELINE, canonical(snapshot) + b'\n')
