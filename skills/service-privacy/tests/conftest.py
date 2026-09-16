"""Synthetic fixtures; none represent a real Kolide installation."""
from __future__ import annotations

import pytest

from service_privacy.core import now
from service_privacy.models import Executable, Plan, Policy, UnitSnapshot
from service_privacy.policy import hashes, rendered


@pytest.fixture
def policy():
    return Policy(unit='osp-fixture-test.service', executables=['/usr/bin/sleep'],
                  write_roots=['/var/lib/ubuntu-service-privacy-data/test'], owner_acknowledges_limits=True)


@pytest.fixture
def plan(policy):
    unit = UnitSnapshot(unit=policy.unit, fragment_path='/usr/lib/systemd/system/osp-fixture-test.service',
                        unit_text_sha256='a' * 64, exec_paths=policy.executables,
                        active_state='active', unit_file_state='enabled', control_group='/system.slice/osp-fixture-test.service',
                        main_pid=1234, properties={})
    return Plan(policy=policy, created_at=now(), host_binding='synthetic-not-a-real-host', source_unit=unit,
                executables=[Executable(path='/usr/bin/sleep', sha256='b'*64)], host_addresses=['127.0.0.1', '::1'],
                rendered_sha256=hashes(rendered(policy, ['127.0.0.1', '::1'])))
