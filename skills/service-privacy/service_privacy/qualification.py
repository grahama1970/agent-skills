"""Assess-update qualification orchestrator.

Composes change.diff_against_baseline with typed rung evidence into ONE
deterministic overall disposition computed in Python, never by a model. Deep or
root-only rungs degrade to ROOT_REQUIRED/SKIPPED statuses instead of crashing,
exactly like change.py; lifecycle rungs run only under --full plus root and are
honest INCONCLUSIVE placeholders, never a fake pass.
"""
from __future__ import annotations

import errno
import json
import os
import re
import sys
import uuid
from pathlib import Path

from .core import Blocked, checked, tool
from .models import ChangeReceipt, QualificationReceipt, RungResult
from .probe import network_verdict
from .system import cgroup_pids, unit_name

# Rungs whose ROOT_REQUIRED degradation blocks a qualified verdict.
CRITICAL_RUNGS = frozenset({'protected-canary', 'process-tree', 'network'})
LIFECYCLE_RUNGS = ('scheduled-workload', 'update-activation', 'restart', 'reboot')
CANARY_DENIED_ERRNOS = frozenset({errno.EPERM, errno.EACCES})


def _is_root() -> bool:
    return os.geteuid() == 0


def _paths(token: str) -> set[str]:
    return set(re.findall(r'(/[^,\s]+)@[0-9a-f]{64}', token))


def unexplained_new_access(changed: list[str]) -> list[str]:
    """Changed fields that grant NEW executable paths (helpers/osqueryd/launcher).

    Pure string logic over the change receipt's changed tokens; a hash-only
    change to an already-qualified path is drift, not new access.
    """
    result = []
    for entry in changed:
        field, _, rest = entry.partition(':')
        if field not in ('launcher', 'osqueryd', 'helpers'):
            continue
        old, _, new = rest.partition('->')
        for path in sorted(_paths(new) - _paths(old)):
            result.append(field + ':' + path)
    return result


def _process_tree_rung(unit: str, profile: str) -> RungResult:
    try:
        shown = checked([tool('systemctl'), 'show', '--no-pager', '--property=ControlGroup', '--', unit]).stdout
        group = shown.strip().partition('=')[2]
        if not group:
            return RungResult(rung='process-tree', status='INCONCLUSIVE', detail='NO_CONTROL_GROUP')
        pids = cgroup_pids(group)
        if not pids:
            return RungResult(rung='process-tree', status='INCONCLUSIVE', detail='SERVICE_NOT_RUNNING')
        labels = []
        for pid in pids:
            labels.append((Path('/proc') / str(pid) / 'attr/current').read_text().strip())
    except (Blocked, OSError, ValueError) as error:
        if isinstance(error, PermissionError):
            return RungResult(rung='process-tree', status='ROOT_REQUIRED',
                              detail='PROC_LABEL_READ_ROOT_ONLY')
        return RungResult(rung='process-tree', status='INCONCLUSIVE', detail='CGROUP_READBACK_INCOMPLETE')
    expected = profile + ' (enforce)'
    if any(label != expected for label in labels):
        return RungResult(rung='process-tree', status='FAIL',
                          detail='UNCONFINED_THREADS:' + ','.join(sorted(set(labels))))
    return RungResult(rung='process-tree', status='PASS', detail=f'{len(labels)} threads confined')


def _transient(profile: str, code: str, timeout: int = 40) -> str:
    token = uuid.uuid4().hex[:12]
    argv = [tool('systemd-run'), '--quiet', '--wait', '--pipe', '--collect',
            '--unit=osp-assess-' + token + '.service', '--service-type=exec',
            '--property=RuntimeMaxSec=30s', '--property=AppArmorProfile=' + profile,
            sys.executable, '-c', code]
    return checked(argv, timeout).stdout


def _protected_canary_rung(unit: str, profile: str) -> RungResult:
    if not _is_root():
        return RungResult(rung='protected-canary', status='ROOT_REQUIRED',
                          detail='PLANTED_CANARY_REQUIRES_ROOT')
    token = uuid.uuid4().hex[:12]
    canary = Path('/root') / ('osp-canary-' + token)
    canary.write_bytes(b'SYNTHETIC-NON-SENSITIVE-CANARY\n')
    canary.chmod(0o600)
    try:
        with canary.open('rb') as fh:  # unconfined positive control: it exists
            fh.read()
        code = ("import errno,json\n"
                "out={'outcome':'DENIED','errno':None}\n"
                "try:\n"
                f"    open({str(canary)!r},'rb').read();out['outcome']='ALLOWED'\n"
                "except OSError as e:\n"
                "    out['errno']=e.errno\n"
                "    if e.errno not in (errno.EPERM,errno.EACCES):out['outcome']='OTHER'\n"
                "print(json.dumps(out))\n")
        try:
            verdict = json.loads(_transient(profile, code))
        except Blocked as error:
            return RungResult(rung='protected-canary', status='INCONCLUSIVE', detail=error.reason)
        if verdict['outcome'] == 'ALLOWED':
            return RungResult(rung='protected-canary', status='FAIL',
                              detail='PROTECTED_PATH_READ_ALLOWED:PROOF_ONLY_NO_CONTENT_RETAINED')
        if verdict['outcome'] == 'DENIED':
            return RungResult(rung='protected-canary', status='PASS',
                              detail='PROTECTED_PATH_READ_DENIED:' + str(verdict['errno']))
        return RungResult(rung='protected-canary', status='INCONCLUSIVE',
                          detail='CANARY_UNREADABLE_ERRNO:' + str(verdict['errno']))
    finally:
        if canary.exists():
            canary.unlink()


def _network_rung(unit: str, profile: str) -> RungResult:
    if not _is_root():
        return RungResult(rung='network', status='ROOT_REQUIRED', detail='FILTER_PROBE_REQUIRES_ROOT')
    try:
        shown = checked([tool('systemctl'), 'show', '--no-pager',
                         '--property=PrivateNetwork,IPAddressDeny', '--', unit]).stdout
        values = dict(line.split('=', 1) for line in shown.strip().splitlines())
    except (Blocked, ValueError):
        return RungResult(rung='network', status='INCONCLUSIVE', detail='UNIT_PROPERTIES_UNREADABLE')
    if values.get('PrivateNetwork') == 'yes':
        # Separate network namespace is the stronger OFFLINE proof; reuse the
        # ns comparison from deploy's runtime checks on the main PID.
        try:
            main = int(checked([tool('systemctl'), 'show', '--no-pager', '--property=MainPID', '--',
                                unit]).stdout.strip().partition('=')[2])
            private = os.readlink(Path('/proc') / str(main) / 'ns/net') != os.readlink('/proc/1/ns/net')
        except (Blocked, OSError, ValueError):
            return RungResult(rung='network', status='INCONCLUSIVE', detail='NETNS_READBACK_INCOMPLETE')
        return (RungResult(rung='network', status='PASS', detail='SEPARATE_NETWORK_NAMESPACE')
                if private else RungResult(rung='network', status='FAIL', detail='SHARED_NETWORK_NAMESPACE'))
    code = ("import errno,json,socket\n"
            "e=None\n"
            "try:\n"
            "    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);s.settimeout(3);"
            "s.connect(('192.0.2.1',9))\n"
            "except OSError as err:e=err.errno\n"
            "print(json.dumps({'failed':e is not None,'errno':e}))\n")
    try:
        raw = json.loads(_transient(profile, code))
    except Blocked as error:
        return RungResult(rung='network', status='INCONCLUSIVE', detail=error.reason)
    verdict = network_verdict(raw['failed'], raw['errno'] or 0)
    status = {'ENFORCED': 'PASS', 'NOT_DENIED': 'FAIL'}.get(verdict, 'INCONCLUSIVE')
    # INCONCLUSIVE_FOR_FILTER_ENFORCEMENT stays INCONCLUSIVE, never a pass.
    return RungResult(rung='network', status=status, detail=verdict)  # type: ignore[arg-type]


def classify(change: ChangeReceipt | None, rungs: list[RungResult]) -> tuple[str, list[str]]:
    """Pure deterministic overall disposition; order is the contract."""
    if change is None:
        return 'FAILED', []
    canary = next((r for r in rungs if r.rung == 'protected-canary'), None)
    if canary is not None and canary.status == 'FAIL':
        return 'PRIVACY_BOUNDARY_VIOLATION', []
    if change.disposition == 'NO_BASELINE':
        return 'NEEDS_HUMAN', []
    if any(r.rung in CRITICAL_RUNGS and r.status == 'ROOT_REQUIRED' for r in rungs):
        return 'INCONCLUSIVE', []
    blocked_evidence = any(r.status in ('FAIL', 'INCONCLUSIVE') for r in rungs)
    new_access = unexplained_new_access(change.changed)
    if change.disposition == 'REQUALIFICATION_REQUIRED':
        if blocked_evidence:
            return 'INCONCLUSIVE', new_access
        if new_access:
            return 'POLICY_CHANGE_PROPOSED', new_access
        return 'REQUALIFIED_UNCHANGED', []
    if change.disposition == 'INCONCLUSIVE' or blocked_evidence:
        return 'INCONCLUSIVE', []
    return 'NO_CHANGE', []


def assess(unit: str, full: bool = False, record_baseline: bool = False) -> QualificationReceipt:
    """Never raises: every degradation path lands in a typed receipt."""
    unit_name(unit)
    from .change import capture, diff_against_baseline, profile_path, record_baseline as record
    try:
        snapshot = capture(unit)
        if record_baseline:
            record(snapshot)
        change = diff_against_baseline(snapshot)
    except (Blocked, OSError, ValueError) as error:
        rung = RungResult(rung='change-detect', status='FAIL',
                          detail=error.reason if isinstance(error, Blocked) else 'CAPTURE_FAILED')
        return QualificationReceipt(unit=unit, change=None, rungs=[rung], disposition='FAILED',
                                    created_at=_now())
    profile = profile_path(unit).name
    rungs: list[RungResult] = [RungResult(rung='change-detect',
                                          status='PASS' if change.disposition in ('NO_CHANGE', 'REQUALIFICATION_REQUIRED') else 'INCONCLUSIVE',
                                          detail=change.disposition + (';'.join(change.changed) if change.changed else ''))]
    try:
        rungs.append(_process_tree_rung(unit, profile))
        rungs.append(_protected_canary_rung(unit, profile))
        rungs.append(_network_rung(unit, profile))
    except Exception as error:  # a rung may never crash the assessment
        rungs.append(RungResult(rung='rung-runner', status='INCONCLUSIVE',
                                detail='RUNG_ERROR:' + type(error).__name__))
    for name in LIFECYCLE_RUNGS:
        # ponytail: even --full+root reports honest INCONCLUSIVE placeholders;
        # real update-activation/reboot qualification is an owner-supervised run.
        if full and _is_root():
            rungs.append(RungResult(rung=name, status='INCONCLUSIVE',
                                    detail='REQUIRES_OWNER_SUPERVISED_UPDATE_PROCEDURE'))
        else:
            rungs.append(RungResult(rung=name, status='SKIPPED',
                                    detail='SKIPPED_WITHOUT_FULL_AND_ROOT'))
    disposition, new_access = classify(change, rungs)
    return QualificationReceipt(unit=unit, change=change, rungs=rungs,
                                disposition=disposition,  # type: ignore[arg-type]
                                unexplained_new_access=new_access, created_at=_now())


def _now() -> str:
    from .core import now
    return now()
