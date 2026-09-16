"""Plan creation and revalidation without mutating the selected service."""
from __future__ import annotations

from pathlib import Path

from .core import Blocked, canonical, checked, host_binding, load, now, secure_dir, sha, tool, write_new
from .models import Plan, Policy
from .policy import hashes, rendered
from .system import digest_executable, host_addresses, inspect_unit, outsiders


def build_plan(policy: Policy) -> Plan:
    for root in policy.read_roots + policy.write_roots:
        path = Path(root)
        if not path.is_dir() or str(path.resolve()) != root:
            raise Blocked('RESOURCE_ROOT_MUST_EXIST_AND_BE_CANONICAL')
        if path.stat().st_uid != 0 or path.stat().st_mode & 0o022:
            raise Blocked('RESOURCE_ROOT_NOT_ROOT_CONTROLLED')
    snapshot = inspect_unit(policy.unit)
    if not set(snapshot.exec_paths + snapshot.runtime_executable_paths).issubset(policy.executables):
        raise Blocked('UNIT_EXECUTABLES_NOT_APPROVED')
    if snapshot.properties.get('AppArmorProfile'):
        raise Blocked('EXISTING_APPARMOR_PROFILE_REQUIRES_MANUAL_COMPOSITION')
    if snapshot.properties.get('BindPaths') or snapshot.properties.get('BindReadOnlyPaths'):
        raise Blocked('EXISTING_BIND_MOUNTS_REQUIRE_MANUAL_REVIEW')
    if outsiders(policy.executables, snapshot.control_group):
        raise Blocked('RELATED_PROCESS_OUTSIDE_SELECTED_UNIT')
    addresses = host_addresses()
    return Plan(policy=policy, created_at=now(), host_binding=host_binding(), source_unit=snapshot,
                executables=[digest_executable(path) for path in policy.executables],
                host_addresses=addresses, rendered_sha256=hashes(rendered(policy, addresses)))


def save_plan(plan: Plan, directory: Path) -> str:
    if directory.exists() or directory.is_symlink():
        raise Blocked('PLAN_DIRECTORY_MUST_BE_NEW')
    secure_dir(directory)
    payload = canonical(plan)
    files = rendered(plan.policy, plan.host_addresses)
    for name, contents in files.items():
        write_new(directory / name, contents)
    write_new(directory / 'plan.json', payload + b'\n')
    write_new(directory / 'approval-sha256.txt', (sha(payload) + '\n').encode())
    return sha(payload)


def verify_plan_files(path: Path) -> Plan:
    plan = load(path, Plan)
    files = rendered(plan.policy, plan.host_addresses)
    if hashes(files) != plan.rendered_sha256:
        raise Blocked('PLAN_RENDER_HASH_MISMATCH')
    from .core import read_private
    for name, content in files.items():
        if read_private(path.parent / name) != content:
            raise Blocked('PLAN_FILE_TAMPERED')
    return plan


def revalidate_host(plan: Plan, unit_unchanged: bool = True) -> None:
    if plan.host_binding != host_binding():
        raise Blocked('PLAN_WRONG_HOST_OR_BOOT')
    if unit_unchanged and inspect_unit(plan.policy.unit).unit_text_sha256 != plan.source_unit.unit_text_sha256:
        raise Blocked('UNIT_CHANGED_SINCE_APPROVAL')
    if host_addresses() != plan.host_addresses:
        raise Blocked('HOST_ADDRESSES_CHANGED_REPLAN_REQUIRED')
    for expected in plan.executables:
        if digest_executable(expected.path) != expected:
            raise Blocked('EXECUTABLE_CHANGED_SINCE_APPROVAL')


def syntax_check(path: Path) -> None:
    # --skip-kernel-load, --skip-read-cache, --skip-write-cache: parser only.
    checked([tool('apparmor_parser'), '-Q', '-T', '-K', str(path)])
