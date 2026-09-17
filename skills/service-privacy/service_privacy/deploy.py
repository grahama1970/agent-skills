"""Owner-authorized apply/verify/rollback transactions with an explicit OFF hold.

A failed installation never intentionally restarts the original unconfined
service. Rollback restores the absence of our policy but retains an OFF hold;
only a subsequent approved installation or explicit owner removal releases it.
"""
from __future__ import annotations

import fcntl
import ipaddress
import os
import stat
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .core import (Blocked, STATE, canonical, checked, host_binding, load, now, read_private,
                   replace_private, root_required, secure_dir, sha, tool, write_new)
from .models import Plan, ProbeReceipt, Registry, Verification
from .planning import revalidate_host, syntax_check, verify_plan_files
from .policy import destinations, loaded_profile_hash_path, rendered
from .system import (apparmor_ready, cgroup_pids, digest_executable, host_addresses, inspect_unit,
                     loaded_profile, loaded_profile_block, outsiders, process_proof, service)

HOLD = (b'# Explicit owner-held OFF. Visible in systemctl cat/status; not a health spoof.\n'
        b'# / always exists, so this condition prevents future starts, including at boot.\n'
        b'[Unit]\nConditionPathExists=!/\n')


@contextmanager
def lock() -> Iterator[None]:
    root_required()
    secure_dir(STATE, require_root=True)
    path = STATE / 'operator.lock'
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or info.st_mode & 0o077:
            raise Blocked('UNSAFE_LOCK_FILE')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def trusted_parent(path: Path) -> None:
    cursor = Path('/')
    for part in path.parts[1:]:
        cursor /= part
        if not cursor.exists() and not cursor.is_symlink():
            cursor.mkdir(mode=0o755)
        info = cursor.lstat()
        if not stat.S_ISDIR(info.st_mode) or cursor.is_symlink() or info.st_uid != 0 or info.st_mode & 0o022:
            raise Blocked('POLICY_PARENT_NOT_ROOT_CONTROLLED')


def registry_path(profile: str) -> Path:
    directory = STATE / profile
    secure_dir(directory, require_root=True)
    return directory / 'registry.json'


def hold_path(plan: Plan) -> Path:
    return destinations(plan.policy)['90-owner-privacy.conf'].parent / '99-owner-privacy-hold.conf'


def hold_on(plan: Plan) -> None:
    path = hold_path(plan)
    trusted_parent(path.parent)
    if path.exists() or path.is_symlink():
        if read_private(path, True) != HOLD:
            raise Blocked('FOREIGN_OR_CHANGED_HOLD')
    else:
        write_new(path, HOLD)


def hold_off(plan: Plan) -> None:
    path = hold_path(plan)
    if read_private(path, True) != HOLD:
        raise Blocked('HOLD_TAMPERED')
    path.unlink()


def reload_systemd() -> None:
    checked([tool('systemctl'), 'daemon-reload'])


def stopped(plan: Plan) -> None:
    info = inspect_unit(plan.policy.unit)
    if info.active_state not in ['inactive', 'failed'] or info.main_pid != 0:
        raise Blocked('SERVICE_DID_NOT_STOP')
    groups = {group for group in [plan.source_unit.control_group, info.control_group] if group}
    if any(cgroup_pids(group) for group in groups):
        raise Blocked('SERVICE_CGROUP_NOT_EMPTY')
    if outsiders(plan.policy.executables, ''):
        raise Blocked('RELATED_PROCESSES_REMAIN_AFTER_STOP')


def save_registry(path: Path, record: Registry) -> None:
    # Preserve each transition; current registry is only a projection.
    history = path.parent / 'history'
    secure_dir(history, require_root=True)
    import uuid
    write_new(history / (uuid.uuid4().hex + '.json'), canonical(record) + b'\n')
    replace_private(path, canonical(record) + b'\n')


def probe_is_current(plan: Plan, receipt: ProbeReceipt) -> None:
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(receipt.created_at)).total_seconds()
    if not 0 <= age <= 3600:
        raise Blocked('PROBE_EXPIRED_OR_FUTURE_DATED')
    if (receipt.status != 'PASS' or not receipt.results.all_pass()
            or receipt.plan_sha256 != sha(canonical(plan)) or receipt.host_binding != host_binding()
            or receipt.production_profile_sha256 != plan.rendered_sha256['apparmor.profile']):
        raise Blocked('PROBE_DOES_NOT_AUTHORIZE_THIS_PLAN')


def capture_loaded_profile_hash(profile: str) -> str:
    """Hash of the loaded-profile readback stanza, captured right after the
    kernel load. The watchdog compares later readbacks against it, so a
    same-name profile replacement (the CrackArmor readback window) is detected
    even though the profile NAME still reads back as enforcing."""
    block = loaded_profile_block(profile)
    if block is None:
        raise Blocked('INSTALLED_PROFILE_NOT_ENFORCING')
    # Mirror the watchdog's awk paragraph output: record text + newline.
    return sha((block + '\n').encode())


def loaded_profile_matches(policy) -> bool:
    try:
        block = loaded_profile_block(policy.profile_name)
        expected = read_private(loaded_profile_hash_path(policy), True).decode().strip()
        return block is not None and expected == sha((block + '\n').encode())
    except (Blocked, OSError, ValueError):
        return False


def verify_record(record: Registry) -> Verification:
    plan = record.plan
    failures = []
    proofs = []
    try:
        apparmor_ready()
        if not loaded_profile(plan.policy.profile_name):
            failures.append('PROFILE_NOT_ENFORCING')
        if not loaded_profile_matches(plan.policy):
            failures.append('LOADED_PROFILE_CONTENT_DRIFT')
        if record.phase not in ['APPLIED', 'FILES_INSTALLED']:
            failures.append('REGISTRY_NOT_APPLIED')
        actual_unit = inspect_unit(plan.policy.unit)
        if actual_unit.unit_text_sha256 != record.installed_unit_sha256:
            failures.append('UNIT_CONFIG_DRIFT')
        for name, data in rendered(plan.policy, plan.host_addresses).items():
            if read_private(destinations(plan.policy)[name], True) != data:
                failures.append('INSTALLED_POLICY_FILE_DRIFT')
        expected_properties = {
            'AppArmorProfile': plan.policy.profile_name, 'NoNewPrivileges': 'yes',
            'CapabilityBoundingSet': '', 'AmbientCapabilities': '', 'ProtectSystem': 'strict',
            'ProtectHome': 'yes', 'PrivateTmp': 'yes', 'PrivateDevices': 'yes',
            'PrivateIPC': 'yes', 'KillMode': 'control-group', 'Delegate': 'no',
            'PrivateNetwork': 'yes' if plan.policy.network_mode == 'OFFLINE' else 'no',
        }
        for key, value in expected_properties.items():
            if actual_unit.properties.get(key) != value:
                failures.append('EFFECTIVE_PROPERTY_DRIFT_' + key.upper())
        if plan.policy.network_mode == 'PUBLIC_EGRESS_LOCAL_DENY':
            # The Device Trust loopback allow is the one sanctioned override
            # (browser must reach the agent's local /v1/cmd server). Anything
            # else — or a widened form — is an unauthorized policy weakening.
            # systemd canonicalizes (127.0.0.1/8 -> 127.0.0.0/8) and reorders
            # (reports '::1/128 127.0.0.0/8'), so a raw string compare always
            # mis-fires. Normalize both sides to a network set, exactly like the
            # IPAddressDeny check below. Empirically verified via systemd-run.
            sanctioned_allow = {str(ipaddress.ip_network(i, strict=False)) for i in '127.0.0.1/8 ::1/128'.split()}
            effective_allow = {str(ipaddress.ip_network(i, strict=False)) for i in actual_unit.properties.get('IPAddressAllow', '').split()}
            if effective_allow != sanctioned_allow:
                failures.append('IP_ALLOW_OVERRIDE_PRESENT')
            from .policy import properties
            intended = dict(properties(plan.policy, plan.host_addresses))['IPAddressDeny']
            expected_deny = {str(ipaddress.ip_network(item)) for item in intended.split()}
            effective_deny = {str(ipaddress.ip_network(item)) for item in actual_unit.properties.get('IPAddressDeny', '').split()}
            if not expected_deny.issubset(effective_deny):
                failures.append('IP_DENY_EFFECTIVE_CONFIG_DRIFT')
        if host_addresses() != plan.host_addresses:
            failures.append('HOST_ADDRESS_DRIFT')
        for expected in plan.executables:
            if digest_executable(expected.path) != expected:
                failures.append('EXECUTABLE_HASH_DRIFT')
        if actual_unit.active_state != 'active' or not actual_unit.main_pid or not actual_unit.control_group:
            return Verification(unit=plan.policy.unit, status='STOPPED_NO_RUNNING_PROOF', checked_at=now(),
                                failures=failures + ['SERVICE_NOT_RUNNING'], processes=[],
                                network_assertion=('SEPARATE_NETWORK_NAMESPACE' if plan.policy.network_mode == 'OFFLINE'
                                                   else 'CONFIGURATION_MATCH'))
        pids = cgroup_pids(actual_unit.control_group)
        if actual_unit.main_pid not in pids:
            failures.append('MAINPID_NOT_IN_CGROUP')
        for pid in pids:
            proof = process_proof(pid, plan.policy.profile_name, actual_unit.control_group)
            proofs.append(proof)
            if proof.executable not in plan.policy.executables:
                failures.append('UNAPPROVED_EXECUTABLE_RUNNING')
            if not proof.zero_capabilities or not proof.no_new_privileges:
                failures.append('PROCESS_PRIVILEGE_BOUNDARY_FAILED')
            if plan.policy.network_mode == 'OFFLINE' and not proof.private_network:
                failures.append('PROCESS_NETWORK_NAMESPACE_NOT_PRIVATE')
        if pids != cgroup_pids(actual_unit.control_group):
            failures.append('PROCESS_SET_CHANGED_DURING_VERIFICATION')
        if outsiders(plan.policy.executables, actual_unit.control_group):
            failures.append('RELATED_PROCESS_OUTSIDE_UNIT')
    except Blocked as error:
        failures.append(error.reason)
    except (OSError, ValueError, KeyError):
        failures.append('RUNTIME_READBACK_INCOMPLETE')
    return Verification(unit=plan.policy.unit, status='FAIL' if failures or not proofs else 'RUNTIME_CHECKS_PASS',
                        checked_at=now(), failures=sorted(set(failures)), processes=proofs,
                        network_assertion=('SEPARATE_NETWORK_NAMESPACE' if plan.policy.network_mode == 'OFFLINE'
                                           else 'CONFIGURATION_MATCH'))


def apply_plan(path: Path, approval: str, probe_path: Path) -> Verification:
    root_required(); apparmor_ready()
    plan = verify_plan_files(path)
    if not plan.policy.owner_acknowledges_limits:
        raise Blocked('OWNER_ACKNOWLEDGEMENT_REQUIRED')
    if approval != sha(canonical(plan)):
        raise Blocked('EXACT_PLAN_APPROVAL_REQUIRED')
    receipt = load(probe_path, ProbeReceipt, require_root=True)
    probe_is_current(plan, receipt)
    revalidate_host(plan)
    with lock():
        record_path = registry_path(plan.policy.profile_name)
        if record_path.exists():
            previous = load(record_path, Registry, True)
            if previous.phase != 'ROLLED_BACK_STOPPED':
                raise Blocked('EXISTING_DEPLOYMENT_REQUIRES_REVIEW_OR_ROLLBACK')
        if loaded_profile(plan.policy.profile_name):
            raise Blocked('PROFILE_NAME_ALREADY_LOADED')
        paths = destinations(plan.policy)
        files = rendered(plan.policy, plan.host_addresses)
        for name, target in paths.items():
            trusted_parent(target.parent)
            if target.exists() or target.is_symlink():
                raise Blocked('REFUSE_OVERWRITE_EXISTING_POLICY')
        # Parser success is necessary but is not a kernel enforcement proof.
        syntax_check(path.parent / 'apparmor.profile')
        record = Registry(plan=plan, plan_sha256=approval, phase='PREPARED', changed_at=now())
        save_registry(record_path, record)
        try:
            hold_on(plan); reload_systemd()
            service('stop', plan.policy.unit); stopped(plan)
            # Stop any previously running agent BEFORE installing the policy.
            for name, content in files.items():
                write_new(paths[name], content)
            checked([tool('apparmor_parser'), '-a', '-T', '-K', str(paths['apparmor.profile'])])
            profile_hash = capture_loaded_profile_hash(plan.policy.profile_name)
            hash_target = loaded_profile_hash_path(plan.policy)
            trusted_parent(hash_target.parent)
            if hash_target.exists() or hash_target.is_symlink():
                raise Blocked('REFUSE_OVERWRITE_EXISTING_POLICY')
            write_new(hash_target, (profile_hash + '\n').encode())
            record.phase = 'FILES_INSTALLED'; record.changed_at = now()
            save_registry(record_path, record)
            hold_off(plan); reload_systemd()
            record.installed_unit_sha256 = inspect_unit(plan.policy.unit).unit_text_sha256
            save_registry(record_path, record)
            service('start', plan.policy.unit)
            # The kernel stamps the AppArmor label during exec; a verify issued in
            # the same millisecond reads pre-exec threads as unconfined (observed:
            # THREAD_PROFILE_MISMATCH on systemd 255). Poll until stable or budget
            # exhausted; never widen permissions to pass.
            for attempt in range(5):
                time.sleep(2)
                verification = verify_record(record)
                if verification.status == 'RUNTIME_CHECKS_PASS':
                    break
            if verification.status != 'RUNTIME_CHECKS_PASS':
                write_new(record_path.parent / ('failed-verify-' + approval[:12] + '.json'), canonical(verification))
                raise Blocked('POST_START_RUNTIME_VERIFICATION_FAILED')
            record.phase = 'APPLIED'; record.changed_at = now(); save_registry(record_path, record)
            write_new(record_path.parent / ('applied-' + approval[:12] + '.json'), canonical(verification))
            return verification
        except BaseException as error:
            # Never restore an unconfined running state as an automatic recovery.
            try:
                hold_on(plan); reload_systemd(); service('stop', plan.policy.unit); stopped(plan)
                record.failure_code = error.reason if isinstance(error, Blocked) else ('OPERATOR_INTERRUPTED' if isinstance(error, KeyboardInterrupt) else 'APPLY_OPERATION_FAILED')
                record.phase = 'STOPPED_AFTER_FAILURE'
            except BaseException:
                record.failure_code = 'FAILURE_CONTAINMENT_NOT_VERIFIED'
                record.phase = 'FAILURE_STATE_UNKNOWN'
            record.changed_at = now()
            save_registry(record_path, record)
            raise Blocked(record.failure_code) from None


def verify_service(profile: str, stop_on_drift: bool = False) -> Verification:
    with lock():
        path = registry_path(profile)
        record = load(path, Registry, True)
        result = verify_record(record)
        if stop_on_drift and result.status != 'RUNTIME_CHECKS_PASS':
            hold_on(record.plan); reload_systemd(); service('stop', record.plan.policy.unit); stopped(record.plan)
            record.phase = 'STOPPED_AFTER_FAILURE'; record.failure_code = 'DRIFT_OPERATOR_STOP'
            record.changed_at = now(); save_registry(path, record)
        return result


def rollback(profile: str) -> Registry:
    with lock():
        path = registry_path(profile)
        record = load(path, Registry, True)
        plan = record.plan
        hold_on(plan); reload_systemd(); service('stop', plan.policy.unit); stopped(plan)
        # Only remove files we created, and only when their bytes still match.
        paths = destinations(plan.policy)
        files = rendered(plan.policy, plan.host_addresses)
        for name, target in paths.items():
            if target.exists() or target.is_symlink():
                if read_private(target, True) != files[name]:
                    raise Blocked('ROLLBACK_REFUSES_CHANGED_POLICY_FILE')
        aa_path = paths['apparmor.profile']
        if loaded_profile(plan.policy.profile_name):
            # Refuse to unload a label still attached anywhere, even outside the selected unit.
            for item in Path('/proc').iterdir():
                if not item.name.isdigit():
                    continue
                try:
                    if (item / 'attr/current').read_text().strip() == plan.policy.profile_name + ' (enforce)':
                        raise Blocked('PROFILE_STILL_IN_USE')
                except FileNotFoundError:
                    pass
            if not aa_path.exists():
                raise Blocked('CANNOT_REMOVE_PROFILE_WITHOUT_OWNED_SOURCE')
            checked([tool('apparmor_parser'), '-R', '-T', '-K', str(aa_path)])
        for target in paths.values():
            if target.exists():
                target.unlink()
        hash_target = loaded_profile_hash_path(plan.policy)
        if hash_target.is_symlink():
            raise Blocked('ROLLBACK_REFUSES_CHANGED_POLICY_FILE')
        if hash_target.exists():
            hash_target.unlink()
        reload_systemd()
        record.phase = 'ROLLED_BACK_STOPPED'; record.changed_at = now(); record.failure_code = None
        save_registry(path, record)
        return record
