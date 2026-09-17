"""Strict contracts for owner-approved, bounded Linux service confinement.

All JSON/YAML boundaries reject extra fields and implicit scalar coercion.
Paths are intentionally a restricted literal subset, never policy-language input.
"""
from __future__ import annotations

import hashlib
import ipaddress
import os
import re
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

UNIT_RE = r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,180}\.service"
PATH_RE = r"/[A-Za-z0-9_./+-]+"
DEFAULT_PROTECTED = ['/home', '/root', '/mnt', '/media', '/srv', '/run/user']
# Reviewed harmless read-only OS-posture classes. Rule: sensitive roots
# (/home /root /mnt /media /srv /run/user) are unconditional denies and are
# NEVER part of any read class; new files are NOT auto-added from denials —
# adding a path is a reviewed code change.
OS_IDENTITY = frozenset({
    '/etc/os-release', '/usr/lib/os-release', '/etc/machine-id',
    '/proc/sys/kernel/osrelease', '/etc/nsswitch.conf', '/etc/hosts',
})
CPU_TOPOLOGY = frozenset({
    '/proc/cpuinfo', '/proc/stat', '/sys/devices/system/cpu/online',
    '/sys/kernel/mm/transparent_hugepage/hpage_pmd_size',
})
# Runtime needs observed on a live Kolide launcher (2026-09-16 crash-loop,
# kernel audit: nsswitch x2, /proc/stat x3, cpu-online, cgroup per start):
# glibc NSS init, osquery CPU tables, topology. Posture-class only.
PACKAGE_METADATA: frozenset[str] = frozenset()
AGENT_STATE: frozenset[str] = frozenset()
PROC_STATUS = frozenset({'/proc/meminfo', '/proc/uptime'})
RUNTIME_READ_FILES = sorted(
    OS_IDENTITY | CPU_TOPOLOGY | PROC_STATUS | PACKAGE_METADATA | AGENT_STATE)
LOCAL_NETWORKS = [
    '0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8',
    '169.254.0.0/16', '172.16.0.0/12', '192.168.0.0/16',
    '224.0.0.0/4', '240.0.0.0/4', '::/128', '::1/128',
    'fc00::/7', 'fe80::/10', 'ff00::/8',
]


def literal_path(value: str) -> str:
    if not re.fullmatch(PATH_RE, value) or value == '/' or value.endswith('/'):
        raise ValueError('path must be absolute, literal, non-root, without spaces or a trailing slash')
    if str(PurePosixPath(value)) != value or '..' in PurePosixPath(value).parts:
        raise ValueError('path must be normalized and cannot traverse')
    return value


def contained(path: str, root: str) -> bool:
    prefix = '/' if root == '/' else root + '/'
    return path == root or path.startswith(prefix)


def overlaps_protected(path: str, protected_roots: list[str] | None = None) -> bool:
    """SINGLE SOURCE OF TRUTH for protected-root overlap, shared by the
    apply-time Policy validator AND validate_delta. Canonicalizes first
    (os.path.realpath resolves symlinks and normalization tricks), rejects
    '..' traversal, and checks overlap in both directions so a grant that
    contains a protected root (e.g. '/') is caught too."""
    roots = protected_roots if protected_roots is not None else DEFAULT_PROTECTED
    if '..' in PurePosixPath(path).parts:
        return True
    resolved = os.path.realpath(path)
    if '..' in PurePosixPath(resolved).parts:
        return True
    return any(contained(resolved, root) or contained(root, resolved) for root in roots)


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, validate_assignment=True)


class Seam(Strict):
    kind: Literal['pydantic'] = 'pydantic'
    status: Literal['PASS'] = 'PASS'


class Policy(Strict):
    schema_version: Literal['ubuntu_service_privacy.policy.v1'] = 'ubuntu_service_privacy.policy.v1'
    unit: str
    executables: list[str] = Field(min_length=1, max_length=24)
    # Default deny is the authority; these explicit paths additionally provide named denials.
    protected_roots: list[str] = Field(default_factory=lambda: DEFAULT_PROTECTED.copy(), max_length=64)
    read_files: list[str] = Field(default_factory=lambda: RUNTIME_READ_FILES.copy(), max_length=128)
    read_roots: list[str] = Field(default_factory=list, max_length=24)
    write_roots: list[str] = Field(default_factory=lambda: ['/var/kolide-k2'], min_length=1, max_length=8)
    network_mode: Literal['OFFLINE', 'PUBLIC_EGRESS_LOCAL_DENY'] = 'OFFLINE'
    public_dns: list[str] = Field(default_factory=list, max_length=3)
    owner_acknowledges_limits: bool = False

    @field_validator('unit')
    @classmethod
    def unit_name(cls, value: str) -> str:
        if not re.fullmatch(UNIT_RE, value):
            raise ValueError('an exact canonical system service name is required')
        return value

    @field_validator('executables', 'protected_roots', 'read_files', 'read_roots', 'write_roots')
    @classmethod
    def paths(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError('duplicate paths are rejected')
        return [literal_path(item) for item in value]

    @field_validator('public_dns')
    @classmethod
    def public_resolvers(cls, value: list[str]) -> list[str]:
        for address in value:
            parsed = ipaddress.ip_address(address)
            if not parsed.is_global or parsed.is_multicast or '%' in address:
                raise ValueError('DNS resolvers must be explicit globally routable literal addresses')
        return value

    @model_validator(mode='after')
    def permissions(self) -> 'Policy':
        if not set(DEFAULT_PROTECTED).issubset(self.protected_roots):
            raise ValueError('baseline protected roots cannot be removed')
        # Single source of truth: the same canonicalized overlap check the
        # delta validator uses, so a proposal can never pass validate_delta
        # but violate apply (or vice versa).
        for path in [*self.executables, *self.read_files, *self.read_roots, *self.write_roots]:
            if overlaps_protected(path, self.protected_roots):
                raise ValueError('an allowed resource overlaps a protected root')
        # No writable cron/systemd/database directories or arbitrary host state.
        for root in self.write_roots:
            if root != '/var/kolide-k2' and not contained(root, '/var/lib/ubuntu-service-privacy-data'):
                raise ValueError('writable roots must be Kolide state or a dedicated service-privacy-data subdirectory')
            if root == '/var/lib/ubuntu-service-privacy-data':
                raise ValueError('select an individual state subdirectory')
        for path in self.executables:
            if any(contained(path, root) for root in self.write_roots):
                raise ValueError('executables must not be in an allowed writable root')
            if not any(contained(path, root) for root in ['/usr/bin', '/usr/sbin', '/usr/local/kolide-k2', '/opt']):
                raise ValueError('use an approved canonical code path')
        for path in self.read_files:
            if path not in RUNTIME_READ_FILES and not contained(path, '/etc/kolide-k2'):
                raise ValueError('extra readable files require a reviewed code change, not an arbitrary grant')
        for root in self.read_roots:
            if not any(contained(root, base) for base in ['/etc/kolide-k2', '/usr/local/kolide-k2', '/opt/kolide']):
                raise ValueError('recursive reads are limited to explicit Kolide configuration/code roots')
        if self.network_mode == 'OFFLINE' and self.public_dns:
            raise ValueError('offline mode cannot specify DNS servers')
        if self.network_mode == 'PUBLIC_EGRESS_LOCAL_DENY' and not self.public_dns:
            raise ValueError('public egress requires owner-selected public DNS resolvers')
        return self

    @property
    def profile_name(self) -> str:
        return 'osp-' + hashlib.sha256(self.unit.encode()).hexdigest()[:20]


class CommandResult(Strict):
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


class Executable(Strict):
    path: str
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class UnitSnapshot(Strict):
    unit: str
    fragment_path: str
    unit_text_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    exec_paths: list[str]
    runtime_executable_paths: list[str] = Field(default_factory=list)
    active_state: str
    unit_file_state: str
    control_group: str
    main_pid: int = Field(ge=0)
    properties: dict[str, str]


class Plan(Strict):
    schema_version: Literal['ubuntu_service_privacy.plan.v1'] = 'ubuntu_service_privacy.plan.v1'
    policy: Policy
    created_at: str
    host_binding: str
    source_unit: UnitSnapshot
    executables: list[Executable]
    host_addresses: list[str]
    rendered_sha256: dict[str, str]
    seam_validation: Seam = Field(default_factory=Seam)
    privacy_boundary: Literal['NOT_ESTABLISHED'] = 'NOT_ESTABLISHED'
    itar_compliance: Literal['NOT_ASSESSED'] = 'NOT_ASSESSED'
    device_trust_compatibility: Literal['NOT_TESTED'] = 'NOT_TESTED'

    @model_validator(mode='after')
    def coherent(self) -> 'Plan':
        if self.source_unit.unit != self.policy.unit:
            raise ValueError('plan service identity mismatch')
        if sorted(e.path for e in self.executables) != sorted(self.policy.executables):
            raise ValueError('every approved executable must be pinned exactly once')
        if not set(self.source_unit.exec_paths + self.source_unit.runtime_executable_paths).issubset(self.policy.executables):
            raise ValueError('a unit command is not in the approved executable list')
        for address in self.host_addresses:
            ipaddress.ip_address(address)
        return self


NetworkDenial = Literal['ENFORCED', 'INCONCLUSIVE_FOR_FILTER_ENFORCEMENT', 'NOT_DENIED']


class ProbeResults(Strict):
    schema_version: Literal['ubuntu_service_privacy.probe_result.v1']
    allowed_read: bool
    denied_read: bool
    denied_proc: bool
    denied_unix: bool
    # ENETUNREACH/EHOSTUNREACH/ECONNREFUSED/EINPROGRESS on a DENIED address prove
    # unreachability, not that the IPAddressDeny filter dropped the packet.
    denied_ipv4: NetworkDenial
    denied_ipv6: NetworkDenial
    no_capabilities: bool
    no_new_privileges: bool
    profile_attached: bool
    child_inherits: bool

    def all_pass(self) -> bool:
        # Network denial is a verdict string, not a bool: INCONCLUSIVE_FOR_FILTER_ENFORCEMENT is not a pass.
        for key, value in self.model_dump().items():
            if key == 'schema_version':
                continue
            if key in ('denied_ipv4', 'denied_ipv6'):
                if value != 'ENFORCED':
                    return False
            elif value is not True:
                return False
        return True


class ProbeReceipt(Strict):
    schema_version: Literal['ubuntu_service_privacy.probe.v1'] = 'ubuntu_service_privacy.probe.v1'
    plan_sha256: str
    host_binding: str
    created_at: str
    production_profile_sha256: str
    results: ProbeResults
    status: Literal['PASS', 'FAIL']
    live: Literal[True] = True
    mocked: Literal[False] = False
    proof_scope: Literal['synthetic_canaries_same_rendered_controls_extra_probe_executable'] = 'synthetic_canaries_same_rendered_controls_extra_probe_executable'
    seam_validation: Seam = Field(default_factory=Seam)

    @model_validator(mode='after')
    def pass_truth(self) -> 'ProbeReceipt':
        if (self.status == 'PASS') != self.results.all_pass():
            raise ValueError('probe status contradicts assertions')
        return self


class Registry(Strict):
    schema_version: Literal['ubuntu_service_privacy.registry.v1'] = 'ubuntu_service_privacy.registry.v1'
    plan: Plan
    plan_sha256: str
    phase: Literal['PREPARED', 'FILES_INSTALLED', 'APPLIED', 'STOPPED_AFTER_FAILURE', 'FAILURE_STATE_UNKNOWN', 'ROLLED_BACK_STOPPED']
    installed_unit_sha256: str | None = None
    changed_at: str
    failure_code: str | None = None


class ProcessProof(Strict):
    pid: int
    start_ticks: int
    executable: str
    label: str
    thread_count: int
    zero_capabilities: bool
    no_new_privileges: bool
    private_network: bool


class Verification(Strict):
    schema_version: Literal['ubuntu_service_privacy.verification.v1'] = 'ubuntu_service_privacy.verification.v1'
    unit: str
    status: Literal['RUNTIME_CHECKS_PASS', 'FAIL', 'STOPPED_NO_RUNNING_PROOF']
    checked_at: str
    failures: list[str]
    processes: list[ProcessProof]
    # Config readback proves the unit file agrees with intent, not that the kernel filter executes.
    network_assertion: Literal['SEPARATE_NETWORK_NAMESPACE', 'CONFIGURATION_MATCH']
    effective_filesystem_access: Literal['SYNTHETIC_PROBES_ONLY_NOT_EXHAUSTIVE'] = 'SYNTHETIC_PROBES_ONLY_NOT_EXHAUSTIVE'
    privacy_boundary: Literal['NOT_ESTABLISHED'] = 'NOT_ESTABLISHED'
    itar_compliance: Literal['NOT_ASSESSED'] = 'NOT_ASSESSED'
    seam_validation: Seam = Field(default_factory=Seam)

    @model_validator(mode='after')
    def truth(self) -> 'Verification':
        if self.status == 'RUNTIME_CHECKS_PASS' and (self.failures or not self.processes):
            raise ValueError('runtime pass requires running-process evidence and no failures')
        return self


Disposition = Literal['NO_CHANGE', 'REQUALIFICATION_REQUIRED', 'NO_BASELINE', 'INCONCLUSIVE']


class QualifiedSnapshot(Strict):
    """Last-qualified binary/unit/profile identity bound to one host.

    Root-only observations degrade to a typed status instead of crashing;
    the paired sha256 is None exactly when the status is not HASHED.
    """
    schema_version: Literal['ubuntu_service_privacy.qualified_snapshot.v1'] = 'ubuntu_service_privacy.qualified_snapshot.v1'
    unit: str
    launcher: Executable
    osqueryd: Executable | None = None
    helper_executables: list[Executable] = Field(default_factory=list)
    helpers_status: Literal['OBSERVED', 'ROOT_REQUIRED'] = 'OBSERVED'
    unit_text_sha256: str | None = None
    unit_text_status: Literal['HASHED', 'ROOT_REQUIRED'] = 'HASHED'
    profile_sha256: str | None = None
    profile_status: Literal['HASHED', 'ROOT_REQUIRED', 'NOT_PRESENT'] = 'HASHED'
    host_binding: str
    created_at: str

    @model_validator(mode='after')
    def hashes_match_status(self) -> 'QualifiedSnapshot':
        if (self.unit_text_sha256 is None) != (self.unit_text_status == 'ROOT_REQUIRED'):
            raise ValueError('unit text hash must be present exactly when hashed')
        if self.profile_status == 'HASHED' and not self.profile_sha256:
            raise ValueError('a hashed profile requires its sha256')
        if self.profile_status != 'HASHED' and self.profile_sha256:
            raise ValueError('an unhashable profile cannot carry a sha256')
        if self.helpers_status != 'OBSERVED' and self.helper_executables:
            raise ValueError('root-required observation cannot list helpers')
        return self


class ChangeReceipt(Strict):
    schema_version: Literal['ubuntu_service_privacy.change_receipt.v1'] = 'ubuntu_service_privacy.change_receipt.v1'
    unit: str
    disposition: Disposition
    changed: list[str] = Field(default_factory=list)
    baseline_sha256: str | None = None
    snapshot_sha256: str
    host_binding: str
    created_at: str
    seam_validation: Seam = Field(default_factory=Seam)

    @model_validator(mode='after')
    def truth(self) -> 'ChangeReceipt':
        # Fail-closed core: a positive verdict requires a comparable baseline
        # and no degraded observation behind it.
        if self.disposition == 'NO_CHANGE' and (self.changed or not self.baseline_sha256):
            raise ValueError('no-change requires a baseline and an empty diff')
        if self.disposition == 'REQUALIFICATION_REQUIRED' and not self.changed:
            raise ValueError('requalification requires named changes')
        if self.disposition == 'NO_BASELINE' and (self.baseline_sha256 or self.changed):
            raise ValueError('no-baseline cannot carry a baseline or a diff')
        return self


QualificationDisposition = Literal[
    'NO_CHANGE', 'REQUALIFICATION_REQUIRED', 'REQUALIFIED_UNCHANGED', 'POLICY_CHANGE_PROPOSED',
    'PRIVACY_BOUNDARY_VIOLATION', 'INCONCLUSIVE', 'NEEDS_HUMAN', 'FAILED']


class RungResult(Strict):
    """One named qualification rung; deep/long rungs degrade to typed statuses."""
    rung: str
    status: Literal['PASS', 'FAIL', 'INCONCLUSIVE', 'ROOT_REQUIRED', 'SKIPPED']
    detail: str


class QualificationReceipt(Strict):
    """Assess-update orchestration: a change diff plus typed rung evidence plus
    ONE deterministic overall disposition. Never a generic PASS."""
    schema_version: Literal['ubuntu_service_privacy.qualification_receipt.v1'] = 'ubuntu_service_privacy.qualification_receipt.v1'
    unit: str
    change: ChangeReceipt | None = None
    rungs: list[RungResult] = Field(default_factory=list)
    disposition: QualificationDisposition
    unexplained_new_access: list[str] = Field(default_factory=list)
    created_at: str
    seam_validation: Seam = Field(default_factory=Seam)

    @model_validator(mode='after')
    def truth(self) -> 'QualificationReceipt':
        if self.change is None and self.disposition != 'FAILED':
            raise ValueError('a missing change receipt means the assessment failed')
        if self.change is not None and self.change.disposition == 'NO_BASELINE' and self.disposition != 'NEEDS_HUMAN':
            raise ValueError('a missing baseline always requires a human to qualify it')
        if self.disposition == 'PRIVACY_BOUNDARY_VIOLATION' and not any(r.status == 'FAIL' for r in self.rungs):
            raise ValueError('a violation claim requires a failing rung')
        if self.disposition == 'POLICY_CHANGE_PROPOSED' and not self.unexplained_new_access:
            raise ValueError('a proposed policy change must name the unexplained access')
        return self


class ValidationIssue(Strict):
    type: str
    loc: list[str | int]
    msg: str
    ctx: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class TriageResult(Strict):
    code: str
    layer: str | None = None
    cause: str | None = None
    next_command: str | None = None
    recoverable: bool | None = None
    not_this: list[str] = Field(default_factory=list)
    ambiguous: bool
    matched_tokens: list[str] = Field(default_factory=list)
    aliased_from: str | None = None


class Failure(Strict):
    schema_version: Literal['ubuntu_service_privacy.error.v1'] = 'ubuntu_service_privacy.error.v1'
    status: Literal['BLOCKED'] = 'BLOCKED'
    reason: str
    validation_errors: list[ValidationIssue]
    triage_status: Literal['CLASSIFIED', 'UNAVAILABLE', 'CONTRACT_REJECTED', 'CALL_FAILED']
    triage_errors: list[TriageResult]
    recovery_argv: list[str]
    next_command_execution: Literal['NEVER_AUTOMATIC'] = 'NEVER_AUTOMATIC'
    seam_validation: Seam = Field(default_factory=Seam)


class Info(Strict):
    schema_version: Literal['ubuntu_service_privacy.info.v1'] = 'ubuntu_service_privacy.info.v1'
    operation: str
    status: Literal['PASS', 'BLOCKED', 'REVIEW_REQUIRED', 'CREATED', 'NOT_ESTABLISHED']
    checks: dict[str, bool] = Field(default_factory=dict)
    details: dict[str, str] = Field(default_factory=dict)
    paths: list[str] = Field(default_factory=list)
    seam_validation: Seam = Field(default_factory=Seam)


class Finding(Strict):
    rule: str
    severity: Literal['error', 'warning', 'info']
    message: str
    skill: str


class Findings(Strict):
    findings: list[Finding]


class TestReceipt(Strict):
    schema_version: Literal['ubuntu_service_privacy.tests.v1'] = 'ubuntu_service_privacy.tests.v1'
    timestamp: str
    status: Literal['PASS', 'FAIL']
    tests: int
    failures: int
    errors: int
    skipped: int
    returncode: int
    live: Literal[False] = False
    mocked: Literal[True] = True
    proof_scope: Literal['local_tests_with_native_parser_and_synthetic_fault_injection_not_live_confinement'] = 'local_tests_with_native_parser_and_synthetic_fault_injection_not_live_confinement'
    claims_proves: list[str]
    claims_does_not_prove: list[str]
    release_readiness: Literal['NOT_ESTABLISHED'] = 'NOT_ESTABLISHED'
    seam_validation: Seam = Field(default_factory=Seam)

    @model_validator(mode='after')
    def counted(self) -> 'TestReceipt':
        passed = self.tests > 0 and self.failures == self.errors == self.skipped == self.returncode == 0
        if (self.status == 'PASS') != passed:
            raise ValueError('test verdict contradicts actual counts')
        return self
