"""Fault-injected transactions using only a temporary filesystem.

All systemd/kernel changes are replaced by explicit fakes here. These tests
prove ordering/refusal/recovery logic, never live confinement.
"""
from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from service_privacy import deploy
from service_privacy.core import Blocked, canonical, load, sha
from service_privacy.models import ProbeReceipt, ProbeResults, Registry, Verification
from service_privacy.planning import save_plan


def good_probe(plan):
    values={'schema_version':'ubuntu_service_privacy.probe_result.v1',
            **{k:True for k in ProbeResults.model_fields if k!='schema_version'}}
    return ProbeReceipt(plan_sha256=sha(canonical(plan)),host_binding=plan.host_binding,created_at=plan.created_at,
                        production_profile_sha256=plan.rendered_sha256['apparmor.profile'],
                        results=ProbeResults.model_validate(values),status='PASS')


def test_expired_probe_rejected(plan,monkeypatch):
    monkeypatch.setattr(deploy,'host_binding',lambda: plan.host_binding)
    receipt=good_probe(plan);receipt.created_at=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
    with pytest.raises(Blocked,match='EXPIRED'):deploy.probe_is_current(plan,receipt)


def test_wrong_plan_probe_rejected(plan,monkeypatch):
    monkeypatch.setattr(deploy,'host_binding',lambda:plan.host_binding)
    receipt=good_probe(plan);receipt.plan_sha256='f'*64
    with pytest.raises(Blocked,match='AUTHORIZE'):deploy.probe_is_current(plan,receipt)


def test_wrong_host_probe_rejected(plan,monkeypatch):
    monkeypatch.setattr(deploy,'host_binding',lambda:'another-host')
    with pytest.raises(Blocked,match='AUTHORIZE'):deploy.probe_is_current(plan,good_probe(plan))


@pytest.fixture
def fake_deployment(plan,tmp_path,monkeypatch):
    bundle=tmp_path/'bundle';save_plan(plan,bundle)
    state=tmp_path/'state';state.mkdir(mode=0o700)
    reg=state/'registry.json';probe=state/'probe.json';probe.write_bytes(canonical(good_probe(plan)));probe.chmod(0o600)
    targets={name:state/name for name in plan.rendered_sha256}
    monkeypatch.setattr(deploy,'root_required',lambda:None)
    monkeypatch.setattr(deploy,'apparmor_ready',lambda:None)
    monkeypatch.setattr(deploy,'revalidate_host',lambda *a,**kw:None)
    monkeypatch.setattr(deploy,'probe_is_current',lambda *a:None)
    monkeypatch.setattr(deploy,'lock',lambda:nullcontext())
    monkeypatch.setattr(deploy,'registry_path',lambda profile:reg)
    monkeypatch.setattr(deploy,'destinations',lambda policy:targets)
    monkeypatch.setattr(deploy,'trusted_parent',lambda path:None)
    monkeypatch.setattr(deploy,'syntax_check',lambda path:None)
    monkeypatch.setattr(deploy,'secure_dir',lambda path,**kw:path.mkdir(mode=0o700,parents=True,exist_ok=True))
    monkeypatch.setattr(deploy,'hold_path',lambda plan:state/'hold.conf')
    actions=[];kernel={'loaded':False}
    monkeypatch.setattr(deploy,'loaded_profile',lambda profile:kernel['loaded'])
    def checked(argv,*args):
        actions.append(('command',tuple(argv)))
        if '-a' in argv:kernel['loaded']=True
    monkeypatch.setattr(deploy,'checked',checked)
    monkeypatch.setattr(deploy,'reload_systemd',lambda:actions.append(('reload',)))
    monkeypatch.setattr(deploy,'stopped',lambda plan:actions.append(('stopped_verified',)))
    def service(action,unit):actions.append((action,unit))
    monkeypatch.setattr(deploy,'service',service)
    snapshot=plan.source_unit.model_copy(deep=True)
    monkeypatch.setattr(deploy,'inspect_unit',lambda unit:snapshot)
    return bundle/'plan.json',probe,reg,actions,targets,state


@pytest.mark.parametrize('failure',['verification','start','interrupt'])
def test_failed_apply_never_restarts_unconfined(plan,fake_deployment,monkeypatch,failure):
    path,probe,reg,actions,targets,state=fake_deployment
    if failure=='verification':
        monkeypatch.setattr(deploy,'verify_record',lambda record:Verification(unit=plan.policy.unit,status='FAIL',checked_at=plan.created_at,
            failures=['SYNTHETIC_FAILURE'],processes=[],network_assertion='SEPARATE_NETWORK_NAMESPACE'))
    else:
        def fail_service(action,unit):
            actions.append((action,unit))
            if action=='start':
                if failure=='interrupt':raise KeyboardInterrupt()
                raise Blocked('SYNTHETIC_START_FAILURE')
        monkeypatch.setattr(deploy,'service',fail_service)
    with pytest.raises(Blocked):deploy.apply_plan(path,sha(canonical(plan)),probe)
    record=load(reg,Registry)
    assert record.phase=='STOPPED_AFTER_FAILURE'
    assert (state/'hold.conf').read_bytes()==deploy.HOLD
    assert actions[-1][0]=='stopped_verified'
    assert [a[0] for a in actions].count('start')==1
    # The restricted profile was installed before any attempt to start.
    first_start=next(i for i,a in enumerate(actions) if a[0]=='start')
    assert any(a[0]=='command' and '-a' in a[1] for a in actions[:first_start])


def test_failed_stop_is_not_called_stopped(plan,fake_deployment,monkeypatch):
    path,probe,reg,actions,targets,state=fake_deployment
    def never_stops(*args):raise Blocked('SYNTHETIC_STOP_FAILURE')
    monkeypatch.setattr(deploy,'service',never_stops)
    with pytest.raises(Blocked,match='CONTAINMENT_NOT_VERIFIED'):deploy.apply_plan(path,sha(canonical(plan)),probe)
    record=load(reg,Registry)
    assert record.phase=='FAILURE_STATE_UNKNOWN'
    assert record.failure_code=='FAILURE_CONTAINMENT_NOT_VERIFIED'


def test_no_overwrite_of_existing_policy(plan,fake_deployment):
    path,probe,reg,actions,targets,state=fake_deployment
    targets['apparmor.profile'].write_text('foreign')
    with pytest.raises(Blocked,match='OVERWRITE'):deploy.apply_plan(path,sha(canonical(plan)),probe)
    assert targets['apparmor.profile'].read_text()=='foreign'
    assert not any(a[0]=='stop' for a in actions)


def test_wrong_approval_before_mutation(plan,fake_deployment):
    path,probe,reg,actions,targets,state=fake_deployment
    with pytest.raises(Blocked,match='EXACT_PLAN'):deploy.apply_plan(path,'0'*64,probe)
    assert actions==[]


def test_hold_is_explicit_and_impossible_condition():
    assert b'ConditionPathExists=!/' in deploy.HOLD
    assert Path('/').exists()
    assert b'Owner' in deploy.HOLD or b'owner' in deploy.HOLD


def test_hold_refuses_foreign_content(plan,tmp_path,monkeypatch):
    path=tmp_path/'hold';path.write_text('foreign');path.chmod(0o600)
    monkeypatch.setattr(deploy,'hold_path',lambda plan:path)
    monkeypatch.setattr(deploy,'trusted_parent',lambda path:None)
    with pytest.raises(Blocked,match='FOREIGN'):deploy.hold_on(plan)
    assert path.read_text()=='foreign'


def test_successful_apply_order_and_readback(plan,fake_deployment,monkeypatch):
    from service_privacy.models import ProcessProof
    path,probe,reg,actions,targets,state=fake_deployment
    proof=ProcessProof(pid=1234,start_ticks=1,executable='/usr/bin/sleep',label=plan.policy.profile_name+' (enforce)',
                       thread_count=1,zero_capabilities=True,no_new_privileges=True,private_network=True)
    expected=Verification(unit=plan.policy.unit,status='RUNTIME_CHECKS_PASS',checked_at=plan.created_at,
                          failures=[],processes=[proof],network_assertion='SEPARATE_NETWORK_NAMESPACE')
    monkeypatch.setattr(deploy,'verify_record',lambda record:expected)
    result=deploy.apply_plan(path,sha(canonical(plan)),probe)
    assert result==expected
    assert load(reg,Registry).phase=='APPLIED'
    assert not (state/'hold.conf').exists()
    assert all(target.exists() for target in targets.values())
    names=[a[0] for a in actions]
    assert names.index('stop') < names.index('stopped_verified') < names.index('start')
    assert len(list((state/'history').glob('*.json'))) >= 3


def test_rollback_refuses_changed_file_and_preserves_hold(plan,fake_deployment,monkeypatch):
    from service_privacy.policy import rendered
    path,probe,reg,actions,targets,state=fake_deployment
    record=Registry(plan=plan,plan_sha256=sha(canonical(plan)),phase='APPLIED',installed_unit_sha256='c'*64,changed_at=plan.created_at)
    reg.write_bytes(canonical(record));reg.chmod(0o600)
    for name, data in rendered(plan.policy,plan.host_addresses).items():
        targets[name].write_bytes(data);targets[name].chmod(0o600)
    targets['90-owner-privacy.conf'].write_text('administrator edited')
    with pytest.raises(Blocked,match='ROLLBACK_REFUSES_CHANGED'):deploy.rollback(plan.policy.profile_name)
    assert targets['90-owner-privacy.conf'].read_text()=='administrator edited'
    assert (state/'hold.conf').read_bytes()==deploy.HOLD
    assert not any(a[0]=='start' for a in actions)


def test_rollback_keeps_off_hold(plan,fake_deployment,monkeypatch):
    from service_privacy.policy import rendered
    path,probe,reg,actions,targets,state=fake_deployment
    record=Registry(plan=plan,plan_sha256=sha(canonical(plan)),phase='APPLIED',installed_unit_sha256='c'*64,changed_at=plan.created_at)
    reg.write_bytes(canonical(record));reg.chmod(0o600)
    for name,data in rendered(plan.policy,plan.host_addresses).items():
        targets[name].write_bytes(data);targets[name].chmod(0o600)
    # The fake profile is not loaded: no actual host policy is touched.
    result=deploy.rollback(plan.policy.profile_name)
    assert result.phase=='ROLLED_BACK_STOPPED'
    assert not any(target.exists() for target in targets.values())
    assert (state/'hold.conf').read_bytes()==deploy.HOLD
    assert not any(a[0]=='start' for a in actions)
