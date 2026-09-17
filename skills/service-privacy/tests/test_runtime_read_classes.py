"""Anti-loosening guard: named read classes must equal the pinned old baseline.

Representation-only refactor of RUNTIME_READ_FILES in models.py.
The union of classes must be byte-identical to the pre-refactor flat list.
Sensitive roots are unconditional denies and must never appear in any class.
"""
import sys

from service_privacy.models import (
    AGENT_STATE,
    CPU_TOPOLOGY,
    OS_IDENTITY,
    PACKAGE_METADATA,
    PROC_STATUS,
    RUNTIME_READ_FILES,
)

OLD_FLAT_BASELINE = [
    '/etc/os-release', '/usr/lib/os-release', '/etc/machine-id',
    '/proc/sys/kernel/osrelease', '/proc/cpuinfo', '/proc/meminfo', '/proc/uptime',
    '/etc/nsswitch.conf', '/etc/hosts', '/proc/stat', '/sys/devices/system/cpu/online',
    '/sys/kernel/mm/transparent_hugepage/hpage_pmd_size',
]

CLASSES = [OS_IDENTITY, CPU_TOPOLOGY, PROC_STATUS, PACKAGE_METADATA, AGENT_STATE]
SENSITIVE_ROOTS = ['/home', '/root', '/mnt', '/media', '/srv', '/run/user']


def test_union_equals_pinned_old_set() -> None:
    assert sorted(RUNTIME_READ_FILES) == sorted(OLD_FLAT_BASELINE)
    # every class path lives in the union (no orphaned paths)
    union = set().union(*CLASSES)
    assert union == set(RUNTIME_READ_FILES)


def test_no_sensitive_root_in_any_class() -> None:
    for cls in CLASSES:
        for path in cls:
            assert not any(
                path == root or path.startswith(root + '/')
                for root in SENSITIVE_ROOTS
            ), f'sensitive path {path} in a read class'


if __name__ == '__main__':
    test_union_equals_pinned_old_set()
    test_no_sensitive_root_in_any_class()
    print('runtime read classes OK:', len(RUNTIME_READ_FILES), 'paths')
    sys.exit(0)
