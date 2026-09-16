"""Positive, negative and adversarial policy/receipt boundary cases."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from service_privacy.core import Blocked, canonical, parse_json, sha
from service_privacy.models import Plan, Policy, ProbeReceipt, ProbeResults, Verification
from service_privacy.policy import apparmor, dropin, hashes, rendered


@pytest.mark.parametrize('path', ['/home/graham/client', '/root/.ssh', '/mnt/storage12tb/client', '/srv/client', '/run/user/1000/key'])
def test_protected_read_rejected(policy, path):
    data=policy.model_dump();data['read_files'].append(path)
    with pytest.raises(ValidationError):Policy.model_validate(data)


@pytest.mark.parametrize('path', ['/etc/shadow', '/etc/gshadow', '/proc/123/environ', '/proc/123/mem', '/var/lib/postgresql/data'])
def test_sensitive_extra_grant_rejected(policy, path):
    data=policy.model_dump();data['read_files'].append(path)
    with pytest.raises(ValidationError):Policy.model_validate(data)


@pytest.mark.parametrize('path', ['/etc/foo\n  file,', '/etc/*', '/etc/{a,b}', '/etc/%n', '/etc/../root', '/etc//x', '/etc/x"', '/etc/x y', '/etc/é', '/', '/etc/', '/etc/x\\y'])
def test_policy_language_injection_rejected(policy, path):
    data=policy.model_dump();data['read_roots']=[path]
    with pytest.raises(ValidationError):Policy.model_validate(data)


@pytest.mark.parametrize('unit', ['--help', 'foo.service\n[Service]', '../foo.service', 'foo*.service', 'foo.socket'])
def test_unit_injection_rejected(policy, unit):
    data=policy.model_dump();data['unit']=unit
    with pytest.raises(ValidationError):Policy.model_validate(data)


def test_extra_field_and_bool_coercion(policy):
    data=policy.model_dump();data['owner_acknowledges_limits']='true'
    with pytest.raises(ValidationError):Policy.model_validate(data)
    data=policy.model_dump();data['allow_root']=True
    with pytest.raises(ValidationError):Policy.model_validate(data)


def test_missing_protection_rejected(policy):
    data=policy.model_dump();data['protected_roots']=[]
    with pytest.raises(ValidationError):Policy.model_validate(data)


@pytest.mark.parametrize('root', ['/var/lib', '/var/lib/systemd', '/var/spool/cron', '/var/log', '/tmp', '/var/lib/ubuntu-service-privacy-data'])
def test_broad_write_rejected(policy, root):
    data=policy.model_dump();data['write_roots']=[root]
    with pytest.raises(ValidationError):Policy.model_validate(data)


def test_no_executable_in_writable_state(policy):
    data=policy.model_dump();data['executables']=['/var/kolide-k2/launcher'];data['write_roots']=['/var/kolide-k2']
    with pytest.raises(ValidationError):Policy.model_validate(data)


@pytest.mark.parametrize('address', ['127.0.0.53', '10.0.0.1', '::1', 'fe80::1', '224.0.0.1', 'not-a-dns-name'])
def test_resolver_local_bypass_rejected(policy, address):
    data=policy.model_dump();data.update(network_mode='PUBLIC_EGRESS_LOCAL_DENY',public_dns=[address])
    with pytest.raises(ValidationError):Policy.model_validate(data)


def test_public_policy_positive_and_host_conflict(policy):
    data=policy.model_dump();data.update(network_mode='PUBLIC_EGRESS_LOCAL_DENY',public_dns=['1.1.1.1'])
    public=Policy.model_validate(data)
    output=rendered(public,['127.0.0.1','::1','203.0.113.5'])
    assert 'resolv.conf' in output
    assert b'IPAddressDeny=' in output['90-owner-privacy.conf']
    assert b'203.0.113.5/32' in output['90-owner-privacy.conf']
    with pytest.raises(Blocked,match='RESOLVER_CONFLICTS'):rendered(public,['1.1.1.1'])


def test_default_offline_and_no_claimed_compliance(policy):
    text=apparmor(policy)
    assert 'network inet' not in text
    assert 'PrivateNetwork=yes' in dropin(policy,[])
    assert 'ProtectHome=yes' in dropin(policy,[])
    assert 'CapabilityBoundingSet=\n' in dropin(policy,[])
    assert 'AppArmorProfile=-' not in dropin(policy,[])
    assert 'ux,' not in text and 'Ux,' not in text and 'px,' not in text
    assert 'attach_disconnected' not in text
    assert '#include' not in text
    assert 'audit deny ptrace,' in text


def test_render_is_deterministic_and_profile_inherits(policy):
    assert rendered(policy,[]) == rendered(policy,[])
    assert '"/usr/bin/sleep" rix,' in apparmor(policy)
    assert 'audit deny "/home/**"' in apparmor(policy)


def test_duplicate_json_rejected(policy):
    text=canonical(policy).decode().replace('"unit":', '"unit":"bad.service","unit":',1)
    with pytest.raises(Blocked,match='DUPLICATE'):parse_json(text,Policy)


def test_nonfinite_rejected():
    with pytest.raises(Blocked,match='NONFINITE'):parse_json('{"owner_acknowledges_limits":NaN}',Policy)


def test_plan_incoherence_rejected(plan):
    data=plan.model_dump();data['executables']=[]
    with pytest.raises(ValidationError):Plan.model_validate(data)
    data=plan.model_dump();data['privacy_boundary']='READY'
    with pytest.raises(ValidationError):Plan.model_validate(data)


def test_false_runtime_pass_rejected():
    with pytest.raises(ValidationError):Verification(unit='foo.service',status='RUNTIME_CHECKS_PASS',checked_at='now',failures=[],processes=[],network_assertion='SEPARATE_NETWORK_NAMESPACE')


def test_probe_cannot_lie(plan):
    data={'schema_version':'ubuntu_service_privacy.probe_result.v1', **{k: True for k in ProbeResults.model_fields if k != 'schema_version'}}
    data['denied_read']=False
    results=ProbeResults.model_validate(data)
    with pytest.raises(ValidationError):ProbeReceipt(plan_sha256=sha(canonical(plan)),host_binding=plan.host_binding,created_at=plan.created_at,
        production_profile_sha256=plan.rendered_sha256['apparmor.profile'],results=results,status='PASS')
