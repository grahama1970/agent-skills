"""Local denial/evidence sanitizer (#1744).

The single rule: raw AppArmor denial lines contain real client paths (e.g.
/home/graham/<client>/src/x.py). They must be redacted at this deterministic
boundary so the non-root agent — and anything downstream toward a model — only
ever receives resource_class + operation + count. The raw path is DROPPED,
never truncated or masked.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from typing import Iterable, Literal

from pydantic import Field, model_validator

from .models import DEFAULT_PROTECTED, RUNTIME_READ_FILES, Strict, contained, overlaps_protected

# Per-run salt: bucket ids are non-reversible and not comparable across runs,
# so a leaked bucket id cannot be dictionary-matched against path guesses later.
_SALT = secrets.token_hex(16)

ResourceClass = Literal['PROTECTED_CLIENT_DATA', 'OS_POSTURE', 'AGENT_STATE', 'NETWORK', 'UNKNOWN']

_NETWORK_OPERATIONS = frozenset({'create', 'bind', 'connect', 'listen', 'accept', 'sendmsg', 'recvmsg', 'setsockopt', 'getsockopt'})
# The service's own writable state (Policy write_roots); a denial here names no client data.
_SERVICE_STATE_ROOTS = ('/var/kolide-k2', '/var/lib/ubuntu-service-privacy-data')
# Recursive approved read class roots whose members are OS posture, not client data.
_OS_POSTURE_ROOTS = ('/sys/devices/system/cpu/', '/proc/', '/sys/kernel/mm/')

# journalctl -k AppArmor record fields, e.g.:
# kernel: apparmor="DENIED" operation="open" profile="osp-..." name="/home/g/c/src/x.py" pid=...
_OPERATION_RE = re.compile(r'\boperation="([^"]+)"')
_NAME_RE = re.compile(r'\bname="([^"]+)"')


class SanitizedDenial(Strict):
    """What crosses the model boundary. NO path, filename, or parent dir — ever."""
    schema_version: Literal['ubuntu_service_privacy.sanitized_denial.v1'] = 'ubuntu_service_privacy.sanitized_denial.v1'
    resource_class: ResourceClass
    operation: str
    denied: bool
    count: int = Field(ge=1)
    # Salted-per-run hash prefix of the raw path: stable within a run (repeated
    # same-path denials aggregate), non-reversible and unlinkable across runs.
    bucket: str = Field(pattern=r'^[a-f0-9]{12}$')

    @model_validator(mode='after')
    def no_path_fragments(self) -> 'SanitizedDenial':
        # Hard invariant: no field may carry '/', a path, or any path segment.
        for value in self.model_dump(exclude={'schema_version'}).values():
            assert '/' not in str(value), 'path fragment leaked into sanitized denial'
        return self


def classify(path: str | None, operation: str = '') -> ResourceClass:
    """Deterministic path->resource_class. Reuses overlaps_protected (the
    single source of truth) and the RUNTIME_READ_FILES vocabulary; no second
    protected-root list. Unclassifiable input is UNKNOWN (count only), never a
    best-guess label with path content."""
    if path is None or not path.startswith('/'):
        # Network records carry a sock family, not a filesystem path.
        if path is None and operation in _NETWORK_OPERATIONS:
            return 'NETWORK'
        return 'UNKNOWN'
    if any(contained(path, root) for root in DEFAULT_PROTECTED) or overlaps_protected(path):
        return 'PROTECTED_CLIENT_DATA'
    if any(contained(path, root) for root in _SERVICE_STATE_ROOTS):
        return 'AGENT_STATE'
    if path in RUNTIME_READ_FILES or any(contained(path, root) for root in _OS_POSTURE_ROOTS):
        return 'OS_POSTURE'
    if operation in _NETWORK_OPERATIONS:
        return 'NETWORK'
    return 'UNKNOWN'


def _bucket(path: str | None, operation: str) -> str:
    material = '' if path is None else path
    return hashlib.sha256((_SALT + material + operation).encode()).hexdigest()[:12]


def parse_denial_line(line: str) -> tuple[str | None, str] | None:
    """Extract (path, operation) from a journalctl kernel AppArmor line.
    Returns None for lines that are not denial records."""
    if 'DENIED' not in line:
        return None
    op_match = _OPERATION_RE.search(line)
    name_match = _NAME_RE.search(line)
    operation = op_match.group(1) if op_match else 'unknown'
    return (name_match.group(1) if name_match else None), operation


def sanitize(raw_denials: Iterable[str | dict]) -> list[SanitizedDenial]:
    """Aggregate raw denial lines (or {'path','operation'} dicts) into
    sanitized (resource_class, operation) counts. Fail-closed leak check: if
    any serialized output contains '/', the original path, or any path
    segment, raise rather than emit."""
    aggregate: dict[tuple[ResourceClass, str, str], int] = {}
    for raw in raw_denials:
        if isinstance(raw, dict):
            path, operation = raw.get('path'), raw.get('operation', 'unknown')
        else:
            parsed = parse_denial_line(raw)
            if parsed is None:
                continue
            path, operation = parsed
        key = (classify(path, operation), operation, _bucket(path, operation))
        aggregate[key] = aggregate.get(key, 0) + 1
    sanitized = [SanitizedDenial(resource_class=cls, operation=operation, denied=True, count=count, bucket=bucket)
                 for (cls, operation, bucket), count in sorted(aggregate.items())]
    # ponytail: whole-record scan, fine for tens of denial lines per window.
    blob = repr([s.model_dump() for s in sanitized])
    assert '/' not in blob, 'sanitizer leak: path fragment in output'
    return sanitized
