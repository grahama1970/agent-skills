"""Read-only systemd/procfs identity checks and explicit service operations.

Unit command arguments are never returned or retained. Canonical executable
paths and content hashes bind plans to the host actually inspected.
"""
from __future__ import annotations

import hashlib
import os
import re
import socket
import stat
from pathlib import Path

import psutil

from .core import Blocked, checked, command, host_binding, read_private, sha, tool
from .models import Executable, ProcessProof, UNIT_RE, UnitSnapshot, contained, literal_path

EXEC_KEYS = ['ExecCondition', 'ExecStartPre', 'ExecStart', 'ExecStartPost', 'ExecReload', 'ExecStop', 'ExecStopPost']
SAFE_KEYS = ['Id', 'LoadState', 'FragmentPath', 'ActiveState', 'SubState', 'MainPID', 'ControlGroup',
             'UnitFileState', 'Type', 'User', 'Group', 'AppArmorProfile', 'NoNewPrivileges',
             'CapabilityBoundingSet', 'AmbientCapabilities', 'ProtectSystem', 'ProtectHome',
             'PrivateTmp', 'PrivateDevices', 'PrivateNetwork', 'PrivateIPC', 'KillMode', 'Delegate',
             'TriggeredBy', 'Triggers', 'Sockets', 'RootDirectory', 'RootImage', 'JoinsNamespaceOf',
             'LoadCredential', 'ImportCredential', 'OpenFile', 'FileDescriptorStoreMax',
             'IPAddressAllow', 'IPAddressDeny', 'BindPaths', 'BindReadOnlyPaths',
             'NetworkNamespacePath', 'RestrictNamespaces', 'StandardInput', 'StandardOutput',
             'StandardError', 'PermissionsStartOnly', 'RemainAfterExit', 'OnFailure', 'OnSuccess']


def unit_name(unit: str) -> str:
    if not re.fullmatch(UNIT_RE, unit):
        raise Blocked('INVALID_UNIT_NAME')
    return unit


def native_properties(stdout: str, permitted: set[str]) -> dict[str, str]:
    result = {}
    for line in stdout.splitlines():
        key, separator, value = line.partition('=')
        if not separator or key not in permitted or key in result:
            raise Blocked('SYSTEMD_PROPERTY_GRAMMAR_REJECTED')
        result[key] = value
    return result


def inspect_unit(unit: str) -> UnitSnapshot:
    unit_name(unit)
    keys = SAFE_KEYS + EXEC_KEYS
    result = checked([tool('systemctl'), 'show', '--no-pager', '--property=' + ','.join(keys), '--', unit])
    values = native_properties(result.stdout, set(keys))
    if values.get('Id') != unit or values.get('LoadState') != 'loaded':
        raise Blocked('CANONICAL_LOADED_UNIT_REQUIRED')
    text = checked([tool('systemctl'), 'cat', '--no-pager', '--', unit]).stdout
    joined = re.sub(r'\\\n[ \t]*', '', text)
    for line in joined.splitlines():
        key, separator, value = line.strip().partition('=')
        if separator and key in EXEC_KEYS and value:
            prefix = re.match(r'^[-@:+!|]*', value.strip()).group(0)
            if any(ch in prefix for ch in '+!|') or '%' in value:
                raise Blocked('UNREVIEWED_EXEC_PREFIX_OR_SPECIFIER')
    paths = set()
    for key in EXEC_KEYS:
        value = values.get(key, '')
        if value:
            found = re.findall(r'(?:^|\{\s*)path=([^ ;]+)\s*;', value)
            if not found:
                raise Blocked('EXECUTABLE_IDENTITY_UNPARSABLE')
            for raw in found:
                literal_path(raw)
                paths.add(str(Path(raw).resolve(strict=True)))
    if not values.get('ExecStart') or not paths:
        raise Blocked('MISSING_EXECSTART')
    # Namespace/socket/credential handoffs complicate the boundary. No guessed handling.
    for key in ['TriggeredBy', 'Triggers', 'Sockets', 'RootDirectory', 'RootImage', 'JoinsNamespaceOf',
                'LoadCredential', 'ImportCredential', 'OpenFile', 'NetworkNamespacePath',
                'OnFailure', 'OnSuccess']:
        value = values.get(key, '')
        if value == '[unprintable]' and key in ('LoadCredential', 'ImportCredential') and not re.search(
                r'(?mi)^\s*(LoadCredential|LoadCredentialEncrypted|SetCredential|SetCredentialEncrypted|ImportCredential)\s*=\s*\S',
                joined):
            # systemd 255 renders unset credential properties as [unprintable].
            # Downgrade to empty ONLY when no directive of the whole credential
            # family appears in the unit text (unit + drop-ins via systemctl cat).
            # Transient/D-Bus-set credentials or a pre-daemon-reload skew still
            # fail closed because the show value stays non-empty for them.
            value = ''
        if value:
            raise Blocked('UNSUPPORTED_UNIT_HANDOFF_' + key.upper())
    if values.get('FileDescriptorStoreMax', '0') != '0':
        raise Blocked('FD_STORE_UNSUPPORTED')
    if values.get('PermissionsStartOnly', 'no') == 'yes':
        raise Blocked('PERMISSIONS_START_ONLY_UNSUPPORTED')
    if values.get('Type') not in ['simple', 'exec', 'notify'] or values.get('RemainAfterExit', 'no') != 'no':
        raise Blocked('UNSUPPORTED_SERVICE_TYPE')
    if values.get('User', '') not in ['', 'root', '0']:
        raise Blocked('THIS_RELEASE_REQUIRES_ROOT_SERVICE_FOR_ZERO_CAP_PROOF')
    # Raw Exec* strings can contain enrollment tokens; never emit them.
    safe = {key: values.get(key, '') for key in SAFE_KEYS}
    running_paths = set()
    group = values.get('ControlGroup', '')
    if group and values.get('ActiveState') == 'active':
        for pid in cgroup_pids(group):
            executable = os.readlink(Path('/proc') / str(pid) / 'exe')
            literal_path(executable)
            running_paths.add(executable)
    return UnitSnapshot(unit=unit, fragment_path=values.get('FragmentPath', ''),
                        unit_text_sha256=sha(text.encode()), exec_paths=sorted(paths),
                        runtime_executable_paths=sorted(running_paths),
                        active_state=values.get('ActiveState', 'unknown'),
                        unit_file_state=values.get('UnitFileState', 'unknown'),
                        control_group=values.get('ControlGroup', ''),
                        main_pid=int(values.get('MainPID', '0')), properties=safe)


def host_addresses() -> list[str]:
    values = set()
    for addresses in psutil.net_if_addrs().values():
        for addr in addresses:
            if addr.family in (socket.AF_INET, socket.AF_INET6):
                values.add(addr.address.split('%', 1)[0])
    if not values:
        raise Blocked('HOST_ADDRESS_INVENTORY_EMPTY')
    return sorted(values)


def digest_executable(path: str) -> Executable:
    item = Path(path)
    if str(item.resolve(strict=True)) != path:
        raise Blocked('EXECUTABLE_NOT_CANONICAL')
    # A privileged operator must not rely on code replaceable by an unrelated user.
    for parent in [item, *item.parents]:
        info = parent.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise Blocked('EXECUTABLE_PATH_NOT_ROOT_CONTROLLED')
    fd = os.open(item, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not before.st_mode & 0o111 or before.st_size > 512_000_000:
            raise Blocked('INVALID_EXECUTABLE_FILE')
        hasher = hashlib.sha256()
        while block := os.read(fd, 1 << 20):
            hasher.update(block)
        after = os.fstat(fd)
        current = item.stat()
        if (before.st_ino, before.st_mtime_ns, before.st_size) != (after.st_ino, after.st_mtime_ns, after.st_size) or current.st_ino != before.st_ino:
            raise Blocked('EXECUTABLE_CHANGED_DURING_HASH')
        return Executable(path=path, sha256=hasher.hexdigest())
    finally:
        os.close(fd)


APPARMOR_MIN_VERSION_FILE = Path('/etc/ubuntu-service-privacy/apparmor-min-version')


def apparmor_userspace_patched() -> None:
    """CrackArmor-class confused-deputy flaws live in the apparmor userspace
    package: a profile can read back as loaded-and-enforcing while unprivileged
    profile-management is still possible. Version floor is owner-pinned from the
    Ubuntu security notice; absent/older pin fails closed."""
    try:
        minimum = read_private(APPARMOR_MIN_VERSION_FILE, True).decode().strip()
    except (OSError, Blocked):
        raise Blocked('APPARMOR_MIN_VERSION_UNSPECIFIED') from None
    if not re.fullmatch(r'[0-9][0-9A-Za-z.+~:-]*', minimum):
        raise Blocked('APPARMOR_MIN_VERSION_MALFORMED')
    version = checked([tool('dpkg-query'), '-W', '-f=${Version}', 'apparmor']).stdout.strip()
    checked([tool('dpkg'), '--compare-versions', version, 'ge', minimum])


def host_userns_restricted() -> None:
    """The host-wide sysctl CrackArmor bypassed. Service-side RestrictNamespaces
    alone does not remove the 3.4x unprivileged-userns kernel attack surface."""
    path = Path('/proc/sys/kernel/apparmor_restrict_unprivileged_userns')
    try:
        value = path.read_text().strip()
    except OSError:
        raise Blocked('UNPRIVILEGED_USERNS_SYSCTL_UNAVAILABLE') from None
    if value != '1':
        raise Blocked('UNPRIVILEGED_USERNS_UNRESTRICTED')


def apparmor_ready() -> None:
    if Path('/proc/1/comm').read_text().strip() != 'systemd':
        raise Blocked('SYSTEMD_PID1_REQUIRED')
    if Path('/sys/module/apparmor/parameters/enabled').read_text().strip() != 'Y':
        raise Blocked('APPARMOR_NOT_ENABLED')
    if not Path('/sys/fs/cgroup/cgroup.controllers').is_file():
        raise Blocked('CGROUP_V2_REQUIRED')
    if not Path('/sys/kernel/security/apparmor/profiles').is_file():
        raise Blocked('APPARMOR_POLICY_READBACK_UNAVAILABLE')
    apparmor_userspace_patched()
    host_userns_restricted()


def _soft(check) -> bool:
    try:
        check(); return True
    except Blocked:
        return False


def loaded_profile(name: str) -> bool:
    return name + ' (enforce)' in Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines()


def service(action: str, unit: str) -> None:
    if action not in ['stop', 'start']:
        raise Blocked('UNSUPPORTED_SERVICE_OPERATION')
    checked([tool('systemctl'), action, '--', unit_name(unit)], 45)


def cgroup_pids(group: str) -> list[int]:
    if not group or group == '/' or '..' in Path(group).parts or not group.startswith('/'):
        raise Blocked('UNSAFE_CGROUP')
    base = Path('/sys/fs/cgroup') / group.lstrip('/')
    if not base.exists():
        return []
    if base.resolve() != base:
        raise Blocked('CGROUP_SYMLINK')
    pids = set()
    groups = [base]
    seen = 0
    while groups:
        current = groups.pop()
        seen += 1
        if seen > 1024:
            raise Blocked('CGROUP_SCAN_LIMIT')
        for value in (current / 'cgroup.procs').read_text().split():
            pids.add(int(value))
        if len(pids) > 4096:
            raise Blocked('PROCESS_SCAN_LIMIT')
        groups.extend(item for item in current.iterdir() if item.is_dir() and not item.is_symlink())
    return sorted(pids)


def process_group(pid: int) -> str:
    lines = (Path('/proc') / str(pid) / 'cgroup').read_text().splitlines()
    groups = [line[3:] for line in lines if line.startswith('0::')]
    if len(groups) != 1:
        raise Blocked('PROCESS_CGROUP_AMBIGUOUS')
    return groups[0]


def start_ticks(pid: int) -> int:
    text = (Path('/proc') / str(pid) / 'stat').read_text()
    return int(text[text.rfind(')') + 2:].split()[19])


def outsiders(paths: list[str], unit_group: str) -> list[int]:
    matches = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            exe = os.readlink(entry / 'exe')
            related = exe in paths or contained(exe, '/usr/local/kolide-k2') or contained(exe, '/var/kolide-k2')
            if related:
                group = process_group(int(entry.name))
                if not unit_group or not contained(group, unit_group):
                    matches.append(int(entry.name))
        except FileNotFoundError:
            continue
        except PermissionError:
            raise Blocked('PROCESS_INVENTORY_PERMISSION_GAP') from None
    return matches


def process_proof(pid: int, expected_profile: str, group: str) -> ProcessProof:
    base = Path('/proc') / str(pid)
    before = start_ticks(pid)
    if not contained(process_group(pid), group):
        raise Blocked('PROCESS_CGROUP_RACE')
    exe = os.readlink(base / 'exe')
    tasks = sorted(item for item in (base / 'task').iterdir() if item.name.isdigit())
    labels = []
    no_caps = True
    no_privs = True
    for task in tasks:
        labels.append((task / 'attr/current').read_text().strip())
        status = dict(line.split(':', 1) for line in (task / 'status').read_text().splitlines() if ':' in line)
        no_caps &= all(int(status[key].strip(), 16) == 0 for key in ['CapEff', 'CapPrm', 'CapBnd', 'CapAmb', 'CapInh'])
        no_privs &= status['NoNewPrivs'].strip() == '1'
    if not tasks or any(label != expected_profile + ' (enforce)' for label in labels):
        raise Blocked('THREAD_PROFILE_MISMATCH')
    if [item.name for item in tasks] != sorted(item.name for item in (base / 'task').iterdir() if item.name.isdigit()):
        raise Blocked('THREAD_SET_CHANGED_DURING_VERIFICATION')
    if before != start_ticks(pid) or not contained(process_group(pid), group):
        raise Blocked('PROCESS_IDENTITY_CHANGED')
    return ProcessProof(pid=pid, start_ticks=before, executable=exe,
                        label=expected_profile + ' (enforce)', thread_count=len(tasks),
                        zero_capabilities=no_caps, no_new_privileges=no_privs,
                        private_network=os.readlink(base / 'ns/net') != os.readlink('/proc/1/ns/net'))


def doctor() -> dict[str, object]:
    checks = {
        'linux': Path('/proc').is_dir(),
        'systemd_pid1': Path('/proc/1/comm').read_text().strip() == 'systemd',
        'cgroup_v2': Path('/sys/fs/cgroup/cgroup.controllers').exists(),
        'apparmor_readback': Path('/sys/kernel/security/apparmor/profiles').is_file(),
        'apparmor_userspace_patched': _soft(apparmor_userspace_patched),
        'unprivileged_userns_restricted': _soft(host_userns_restricted),
    }
    for name in ['systemctl', 'systemd-run', 'apparmor_parser', 'cc']:
        try:
            tool(name); checks[name] = True
        except Blocked:
            checks[name] = False
    return checks
