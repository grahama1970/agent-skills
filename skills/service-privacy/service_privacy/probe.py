"""Opt-in live synthetic probes in a transient unit; no vendor execution.

Loads a unique temporary AppArmor profile with the same production controls and
one extra probe executable. Retains a root-owned typed receipt. No input data is
transmitted; positive network controls use only loopback listeners.
"""
from __future__ import annotations

import errno
import json
import os
import socket
import uuid
from contextlib import ExitStack
from pathlib import Path

from .core import (Blocked, ROOT, STATE, canonical, checked, host_binding, now, parse_json,
                   root_required, secure_dir, sha, tool, write_new)
from .models import Plan, ProbeReceipt, ProbeResults
from .planning import revalidate_host, syntax_check
from .policy import apparmor, properties
from .system import apparmor_ready, loaded_profile

# Only these errnos on a connect() to a DENIED address prove the filter dropped the packet.
FILTER_ENFORCED_ERRNOS = frozenset({errno.EPERM, errno.EACCES})


def network_verdict(connect_failed: bool, error_number: int) -> str:
    """Classify a failed connect() to a DENIED address: only EPERM/EACCES prove enforcement."""
    if not connect_failed:
        return 'NOT_DENIED'
    return 'ENFORCED' if error_number in FILTER_ENFORCED_ERRNOS else 'INCONCLUSIVE_FOR_FILTER_ENFORCEMENT'


def network_status_from_probe_bool(value: bool) -> str:
    """probe.c collapses errnos to a bool over a superset acceptance set (unchanged per #1734):
    a 'denied' connect may be EPERM (filter) or ENETUNREACH/EHOSTUNREACH/ECONNREFUSED/EINPROGRESS
    (plain unreachability, no filter) — ambiguous, so never an enforcement pass."""
    return 'NOT_DENIED' if not value else 'INCONCLUSIVE_FOR_FILTER_ENFORCEMENT'


def live_probe(plan: Plan) -> tuple[Path, ProbeReceipt]:
    root_required(); apparmor_ready(); revalidate_host(plan)
    token = uuid.uuid4().hex[:12]
    directory = STATE / 'probes' / token
    secure_dir(directory, require_root=True)
    executable = directory / 'probe'
    checked([tool('cc'), '-O2', '-Wall', '-Wextra', '-Werror', str(ROOT / 'scripts/probe.c'), '-o', str(executable)])
    executable.chmod(0o700)
    profile_name = plan.policy.profile_name + '-probe-' + token
    profile_path = directory / 'apparmor.profile'
    write_new(profile_path, apparmor(plan.policy, str(executable), profile_name).encode())
    syntax_check(profile_path)
    # Use /run rather than PrivateTmp; denial must be EACCES/EPERM, not a missing file.
    denied_file = Path('/run') / ('osp-denied-' + token)
    socket_path = Path('/run') / ('osp-socket-' + token)
    allowed_file = Path(plan.policy.read_files[0]) if plan.policy.read_files else Path('/etc/ld.so.cache')
    proc_file = Path('/proc') / str(os.getpid()) / 'environ'
    write_new(denied_file, b'SYNTHETIC-NON-SENSITIVE-CANARY\n')
    profile_added = False
    unit = 'osp-probe-' + token + '.service'
    try:
        # Unconfined positive controls prove real resources exist and are reachable.
        for item in [allowed_file, denied_file, proc_file]:
            fd = os.open(item, os.O_RDONLY); os.close(fd)
        with ExitStack() as stack:
            listeners = []
            for family, address in [(socket.AF_INET, '127.0.0.1'), (socket.AF_INET6, '::1')]:
                server = stack.enter_context(socket.socket(family, socket.SOCK_STREAM))
                server.bind((address, 0)); server.listen(8)
                with socket.socket(family, socket.SOCK_STREAM) as client:
                    client.settimeout(2); client.connect(server.getsockname())
                connection, _ = server.accept(); connection.close()
                listeners.append(server)
            server_unix = stack.enter_context(socket.socket(socket.AF_UNIX, socket.SOCK_STREAM))
            server_unix.bind(str(socket_path)); server_unix.listen(8)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(str(socket_path))
            connection, _ = server_unix.accept(); connection.close()
            checked([tool('apparmor_parser'), '-a', '-T', '-K', str(profile_path)])
            profile_added = True
            if not loaded_profile(profile_name):
                raise Blocked('PROBE_PROFILE_NOT_ENFORCING')
            argv = [tool('systemd-run'), '--quiet', '--wait', '--pipe', '--collect',
                    '--unit=' + unit, '--service-type=exec', '--property=RuntimeMaxSec=30s']
            for key, value in properties(plan.policy, plan.host_addresses):
                if key in ['StandardInput', 'StandardOutput', 'StandardError', 'BindReadOnlyPaths']:
                    continue
                if key == 'AppArmorProfile':
                    value = profile_name
                # No network resolution is used by probes, so a not-yet-installed DNS file is unnecessary.
                argv += ['--property=' + key + '=' + value]
            argv += [str(executable), str(allowed_file), str(denied_file), str(proc_file), str(socket_path),
                     str(listeners[0].getsockname()[1]), str(listeners[1].getsockname()[1]),
                     profile_name + ' (enforce)']
            result = checked(argv, 40)
            raw = json.loads(result.stdout)
            for key in ('denied_ipv4', 'denied_ipv6'):
                raw[key] = network_status_from_probe_bool(bool(raw[key]))
            probe_results = parse_json(json.dumps(raw), ProbeResults)
            receipt = ProbeReceipt(plan_sha256=sha(canonical(plan)), host_binding=host_binding(), created_at=now(),
                                   production_profile_sha256=plan.rendered_sha256['apparmor.profile'],
                                   results=probe_results, status='PASS' if probe_results.all_pass() else 'FAIL')
            receipt_path = directory / 'receipt.json'
            write_new(receipt_path, canonical(receipt) + b'\n')
            return receipt_path, receipt
    finally:
        # Never leave the temporary test process alive after a failed test.
        from .core import command
        command([tool('systemctl'), 'stop', '--', unit], 35)
        if profile_added:
            checked([tool('apparmor_parser'), '-R', '-T', '-K', str(profile_path)])
        for item in [denied_file, socket_path]:
            if item.exists() or item.is_symlink():
                item.unlink()
