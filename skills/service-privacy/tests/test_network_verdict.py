"""Regression tests for ticket #1734: unreachable-target connect failures must
never be promoted to a filter-enforcement PASS. Pure classification checks;
deterministic, unprivileged, no sockets or root required.
"""
from __future__ import annotations

import errno
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from service_privacy.models import ProbeResults
from service_privacy.probe import (FILTER_ENFORCED_ERRNOS, network_status_from_probe_bool,
                                   network_verdict)

PASSING = {'schema_version': 'ubuntu_service_privacy.probe_result.v1', 'allowed_read': True,
           'denied_read': True, 'denied_proc': True, 'denied_unix': True,
           'denied_ipv4': 'ENFORCED', 'denied_ipv6': 'ENFORCED', 'no_capabilities': True,
           'no_new_privileges': True, 'profile_attached': True, 'child_inherits': True}


def test_only_eperm_eacces_prove_enforcement():
    assert network_verdict(True, errno.EPERM) == 'ENFORCED'
    assert network_verdict(True, errno.EACCES) == 'ENFORCED'
    assert FILTER_ENFORCED_ERRNOS == {errno.EPERM, errno.EACCES}


@pytest.mark.parametrize('error', [errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ECONNREFUSED,
                                   errno.EINPROGRESS, errno.ETIMEDOUT, errno.EACCES + 0])
def test_unreachable_errnos_are_inconclusive(error):
    if error in FILTER_ENFORCED_ERRNOS:
        pytest.skip('not an unreachable errno on this platform')
    assert network_verdict(True, error) == 'INCONCLUSIVE_FOR_FILTER_ENFORCEMENT'
    assert network_verdict(True, error) != 'ENFORCED'


def test_successful_connect_is_not_denied():
    assert network_verdict(False, 0) == 'NOT_DENIED'


def test_inconclusive_network_is_not_pass():
    for key in ('denied_ipv4', 'denied_ipv6'):
        data = dict(PASSING, **{key: 'INCONCLUSIVE_FOR_FILTER_ENFORCEMENT'})
        assert ProbeResults.model_validate(data).all_pass() is False, key


def test_enforced_network_can_pass():
    assert ProbeResults.model_validate(PASSING).all_pass() is True


def test_not_denied_network_is_not_pass():
    for key in ('denied_ipv4', 'denied_ipv6'):
        data = dict(PASSING, **{key: 'NOT_DENIED'})
        assert ProbeResults.model_validate(data).all_pass() is False, key


def test_probe_c_bool_never_claims_enforcement():
    # probe.c (unchanged in #1734) collapses errnos to a bool over a superset set:
    # a "denied" true is ambiguous (EPERM or plain unreachability), so never ENFORCED.
    assert network_status_from_probe_bool(True) == 'INCONCLUSIVE_FOR_FILTER_ENFORCEMENT'
    assert network_status_from_probe_bool(False) == 'NOT_DENIED'
    data = dict(PASSING, denied_ipv4=network_status_from_probe_bool(True),
                denied_ipv6=network_status_from_probe_bool(True))
    assert ProbeResults.model_validate(data).all_pass() is False


def test_bool_no_longer_accepted_for_network_fields():
    with pytest.raises(Exception):
        ProbeResults.model_validate(dict(PASSING, denied_ipv4=True))


if __name__ == '__main__':
    test_only_eperm_eacces_prove_enforcement()
    for error in [errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ECONNREFUSED, errno.EINPROGRESS,
                  errno.ETIMEDOUT]:
        assert network_verdict(True, error) == 'INCONCLUSIVE_FOR_FILTER_ENFORCEMENT'
    test_successful_connect_is_not_denied()
    test_inconclusive_network_is_not_pass()
    test_enforced_network_can_pass()
    test_not_denied_network_is_not_pass()
    test_probe_c_bool_never_claims_enforcement()
    test_bool_no_longer_accepted_for_network_fields()
    print('all network verdict regression assertions passed')
