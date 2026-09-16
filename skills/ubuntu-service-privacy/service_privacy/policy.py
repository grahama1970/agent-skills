"""Pure renderer for default-deny AppArmor and systemd defense in depth.

It never grants unconfined execution, policy-management capabilities or blanket
filesystem access. Public egress is IP filtering, not hostname authentication.
"""
from __future__ import annotations

import ipaddress
from pathlib import Path

from .core import Blocked, sha
from .models import LOCAL_NETWORKS, Policy, literal_path


def apparmor(policy: Policy, probe_executable: str | None = None,
             probe_name: str | None = None) -> str:
    name = probe_name or policy.profile_name
    if probe_name and not probe_name.startswith(policy.profile_name + '-probe-'):
        raise Blocked('INVALID_PROBE_PROFILE_NAME')
    lines = [
        '# Generated owner policy. Default deny; no abstractions or unconfined transitions.',
        '# Denials can break Device Trust. No result or inventory is falsified.',
        f'profile {name} flags=(mediate_deleted) {{',
        '  audit deny capability,',
        '  audit deny ptrace,',
        '  audit deny mount,',
        '  audit deny umount,',
        '  audit deny dbus,',
        # io_uring: seccomp denying io_uring_setup does not cover a ring fd
        # acquired by other means; AppArmor 4 mediates io_uring directly.
        '  audit deny io_uring,',
        '  signal (receive) peer=unconfined,',
        f'  signal (send, receive) peer={name},',
        '  /dev/null rw,', '  /dev/zero r,', '  /dev/random r,', '  /dev/urandom r,',
        '  /etc/ld.so.cache r,',
        '  /{,usr/}lib{,32,64}/**.so* mr,',
        '  /usr/lib/locale/** r,',
        '  /usr/share/zoneinfo/** r,',
        '  /etc/localtime r,',
        '  /etc/ssl/certs/** r,',
        '  /proc/[0-9]*/attr/current r,',
        # Go-runtime/osquery self-introspection reads (maps, cgroup). With zero
        # capabilities the confined process cannot pass DAC on other users' proc
        # entries, so the glob is effectively self-only. Observed 2026-09-16 audit.
        '  /proc/[0-9]*/maps r,',
        '  /proc/[0-9]*/cgroup r,',
        '  /sys/kernel/mm/transparent_hugepage/hpage_pmd_size r,',
        '  /proc/self/attr/current r,',
        '  /run/systemd/notify w,',
        '  unix (create, bind, listen, accept, getattr, getopt, setopt),',
        f'  unix (connect, send, receive) peer=(label={name}),',
    ]
    # Explicit denies are audited instead of silently suppressing deny messages.
    for root in policy.protected_roots:
        lines += [f'  audit deny "{root}" rwklmx,', f'  audit deny "{root}/**" rwklmx,']
    for path in ['/run/docker.sock', '/run/containerd/**', '/run/dbus/**', '/run/systemd/private',
                 '/run/user/**', '/usr/lib/snapd/snap-confine',
                 '/dev/mem', '/dev/kmem', '/dev/kmsg', '/sys/kernel/security/**']:
        lines.append(f'  audit deny "{path}" rwklmx,')
    for path in policy.read_files:
        lines.append(f'  "{path}" r,')
    for root in policy.read_roots:
        lines += [f'  "{root}/" r,', f'  "{root}/**" r,']
    for root in policy.write_roots:
        lines += [f'  "{root}/" rw,', f'  "{root}/**" rwk,']
    # PrivateTmp gives these permissions a separate mount namespace in deployment.
    lines += ['  /tmp/ rw,', '  /tmp/** rwk,', '  /var/tmp/ rw,', '  /var/tmp/** rwk,']
    for path in policy.executables:
        lines.append(f'  "{path}" rix,')
    if probe_executable:
        literal_path(probe_executable)
        lines.append(f'  "{probe_executable}" rix,')
    if policy.network_mode == 'PUBLIC_EGRESS_LOCAL_DENY':
        lines += ['  /etc/resolv.conf r,',
                  '  network inet stream,', '  network inet6 stream,',
                  '  network inet dgram,', '  network inet6 dgram,']
    lines.append('}')
    return '\n'.join(lines) + '\n'


def properties(policy: Policy, host_addresses: list[str]) -> list[tuple[str, str]]:
    items = [
        ('AppArmorProfile', policy.profile_name),
        ('NoNewPrivileges', 'yes'), ('CapabilityBoundingSet', ''), ('AmbientCapabilities', ''),
        ('ProtectSystem', 'strict'), ('ProtectHome', 'yes'), ('PrivateTmp', 'yes'),
        ('PrivateDevices', 'yes'), ('PrivateIPC', 'yes'),
        ('ProtectKernelTunables', 'yes'), ('ProtectKernelModules', 'yes'),
        ('ProtectKernelLogs', 'yes'), ('ProtectControlGroups', 'yes'),
        ('ProtectClock', 'yes'), ('ProtectHostname', 'yes'),
        ('RestrictNamespaces', 'yes'), ('RestrictSUIDSGID', 'yes'),
        ('LockPersonality', 'yes'), ('KeyringMode', 'private'),
        ('UMask', '0077'), ('LimitCORE', '0'), ('KillMode', 'control-group'), ('Delegate', 'no'),
        # memfd_create: path-based exec allowlists don't cover anonymous exec; keyring
        # syscalls: AppArmor does not mediate add_key/request_key/keyctl (KeyringMode=private
        # plus deny closes the cross-process stash channel).
        # perf_event_open/process_vm_readv/userfaultfd: AppArmor does not mediate
        # perf_event_open, so with kernel.perf_event_paranoid <= 2 unprivileged
        # cross-process sampling/reads would leak data across the unit's file-policy
        # boundary; userfaultfd enables same-class cross-process memory manipulation.
        ('SystemCallFilter', '~@mount @reboot @swap @raw-io @module @debug io_uring_setup memfd_create add_key request_key keyctl perf_event_open process_vm_readv userfaultfd'),
        ('MemoryDenyWriteExecute', 'yes'),
        ('RestrictAddressFamilies', 'AF_UNIX AF_INET AF_INET6'),
        ('StandardInput', 'null'), ('StandardOutput', 'journal'), ('StandardError', 'journal'),
        ('ReadWritePaths', ''), ('ReadWritePaths', ' '.join(policy.write_roots)),
        ('InaccessiblePaths', ' '.join('-' + root for root in policy.protected_roots)),
    ]
    if policy.network_mode == 'OFFLINE':
        items += [('PrivateNetwork', 'yes')]
    else:
        denied = list(LOCAL_NETWORKS)
        ranges = [ipaddress.ip_network(net) for net in LOCAL_NETWORKS]
        for value in host_addresses:
            address = ipaddress.ip_address(value)
            # A host address already inside a denied range is covered by that range;
            # emitting it again inflates the list past what systemd keeps, causing
            # silent entry loss and effective-config drift (observed on systemd 255).
            if any(address in net for net in ranges):
                continue
            denied.append(f'{address}/{address.max_prefixlen}')
        if any(ipaddress.ip_address(server) in ipaddress.ip_network(net) for server in policy.public_dns for net in denied):
            raise Blocked('RESOLVER_CONFLICTS_WITH_LOCAL_DENY')
        resolver = f'/etc/ubuntu-service-privacy/{policy.profile_name}/resolv.conf'
        items += [
            ('PrivateNetwork', 'no'), ('IPAccounting', 'yes'),
            ('IPAddressAllow', ''), ('IPAddressDeny', ' '.join(sorted(set(denied)))),
            ('BindReadOnlyPaths', f'{resolver}:/etc/resolv.conf'),
        ]
    return items


def dropin(policy: Policy, host_addresses: list[str]) -> str:
    lines = ['# Owner-controlled service confinement; not an ITAR certification.',
             '[Unit]', 'Requires=apparmor.service', 'After=apparmor.service',
             'AssertSecurity=apparmor', '', '[Service]']
    lines += [f'{key}={value}' for key, value in properties(policy, host_addresses)]
    return '\n'.join(lines) + '\n'


def watchdog_check_script(policy: Policy) -> str:
    """Fail-closed check script. Beyond the profile-name readback (which a
    same-name replacement survives for a polling interval, the CrackArmor
    window), it compares the LOADED PROFILE CONTENT hash against the apply-time
    captured reference and re-checks effective systemd directives each tick."""
    props = dict(properties(policy, []))
    watch = ['AppArmorProfile', 'NoNewPrivileges', 'ProtectSystem', 'ProtectHome',
             'PrivateTmp', 'PrivateDevices', 'PrivateIPC', 'PrivateNetwork']
    lines = [
        '#!/bin/sh',
        '# Owner-generated confinement watchdog check; any mismatch stops the service.',
        f"name='{policy.profile_name}'",
        f"unit='{policy.unit}'",
        'profiles=/sys/kernel/security/apparmor/profiles',
        f"expected=/etc/ubuntu-service-privacy/{policy.profile_name}/loaded-profile-sha256.txt",
        f"lasttick=/etc/ubuntu-service-privacy/{policy.profile_name}/last-tick",
        'fail_closed() { systemctl stop -- "$unit"; exit 0; }',
        '[ -s "$expected" ] || fail_closed',
        'grep -qx "$name (enforce)" "$profiles" || fail_closed',
        "got=$(awk -v RS= -v n=\"$name\" -v m='(enforce)' '$1 == n && $2 == m' \"$profiles\" | sha256sum | cut -c1-64)",
        '[ "$got" = "$(cat "$expected")" ] || fail_closed',
        'out=$(systemctl show --no-pager ' + ' '.join('-p ' + key for key in watch) + ' -- \"$unit\") || fail_closed',
    ]
    for key in watch:
        lines.append(f"printf '%s\\n' \"$out\" | grep -Fxq '{key}={props[key]}' || fail_closed")
    # Tamper/blindness signal: audited AppArmor DENIED events for this profile
    # since the last tick are consumed, not merely emitted. A DENIED hit means
    # the confined process attempted a denied action; unreadable telemetry
    # (journalctl missing/failing) is itself treated as a failure so a missing
    # signal becomes an alert instead of silence.
    lines += [
        '[ -x /usr/bin/journalctl ] || fail_closed',
        'since=$(cat "$lasttick" 2>/dev/null || printf -- "-5min")',
        'log=$(journalctl -kq --since="$since" 2>&1) || fail_closed',
        'case "$log" in *\'apparmor="DENIED"\'*"$name"*) fail_closed ;; esac',
        'date -u +%Y-%m-%dT%H:%M:%SZ > "$lasttick"',
    ]
    return '\n'.join(lines) + '\n'


def watchdog(policy: Policy) -> dict[str, bytes]:
    """Detect profile-unload/replacement windows and effective-directive drift
    between verify ticks, and fail closed by stopping it. Owner enables it:
    systemctl enable --now <name>-watchdog.timer"""
    check_path = f'/etc/ubuntu-service-privacy/{policy.profile_name}/watchdog-check.sh'
    service = (
        '# Owner-controlled confinement watchdog; fail closed on profile unload or drift.\n'
        '[Unit]\n'
        f'Description=Confinement watchdog for {policy.unit}\n'
        'ConditionPathExists=/sys/kernel/security/apparmor/profiles\n'
        f'ConditionPathExists={check_path}\n\n'
        '[Service]\n'
        'Type=oneshot\n'
        f'ExecStart=/bin/sh {check_path}\n'
    )
    timer = (
        f'[Unit]\nDescription=Periodic confinement watchdog for {policy.unit}\n\n'
        '[Timer]\nOnBootSec=2min\nOnUnitActiveSec=5min\nAccuracySec=30s\nPersistent=yes\n\n'
        '[Install]\nWantedBy=timers.target\n'
    )
    return {'watchdog.service': service.encode(), 'watchdog.timer': timer.encode(),
            'watchdog-check.sh': watchdog_check_script(policy).encode()}


def rendered(policy: Policy, host_addresses: list[str]) -> dict[str, bytes]:
    files = {
        'apparmor.profile': apparmor(policy).encode(),
        '90-owner-privacy.conf': dropin(policy, host_addresses).encode(),
    }
    if policy.network_mode == 'PUBLIC_EGRESS_LOCAL_DENY':
        files['resolv.conf'] = ('# Owner-selected DNS; loopback resolver is intentionally unavailable.\n' +
                                ''.join('nameserver ' + value + '\n' for value in policy.public_dns) +
                                'options timeout:2 attempts:2\n').encode()
    files.update(watchdog(policy))
    return files


def hashes(files: dict[str, bytes]) -> dict[str, str]:
    return {name: sha(data) for name, data in files.items()}


def destinations(policy: Policy) -> dict[str, Path]:
    result = {
        'apparmor.profile': Path('/etc/apparmor.d') / policy.profile_name,
        '90-owner-privacy.conf': Path('/etc/systemd/system') / (policy.unit + '.d') / '90-owner-privacy.conf',
    }
    if policy.network_mode == 'PUBLIC_EGRESS_LOCAL_DENY':
        result['resolv.conf'] = Path('/etc/ubuntu-service-privacy') / policy.profile_name / 'resolv.conf'
    result.update({'watchdog.service': Path('/etc/systemd/system') / (policy.profile_name + '-watchdog.service'),
                   'watchdog.timer': Path('/etc/systemd/system') / (policy.profile_name + '-watchdog.timer'),
                   'watchdog-check.sh': Path('/etc/ubuntu-service-privacy') / policy.profile_name / 'watchdog-check.sh'})
    return result


def loaded_profile_hash_path(policy: Policy) -> Path:
    return Path('/etc/ubuntu-service-privacy') / policy.profile_name / 'loaded-profile-sha256.txt'
