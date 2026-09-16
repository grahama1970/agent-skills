"""Real parsers, real file permissions, and a real unconfined probe negative control."""
from __future__ import annotations

import ast
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from service_privacy.core import Blocked, ROOT, canonical, load, read_private, secure_dir, write_new
from service_privacy.models import Plan, Policy, ProbeResults
from service_privacy.planning import save_plan, verify_plan_files
from service_privacy.policy import apparmor, dropin


def test_private_artifact_roundtrip(plan, tmp_path):
    directory=tmp_path/'plan';save_plan(plan,directory)
    assert verify_plan_files(directory/'plan.json') == plan
    assert directory.stat().st_mode & 0o777 == 0o700
    assert all(file.stat().st_mode & 0o777 == 0o600 for file in directory.iterdir())


def test_tamper_rejected(plan,tmp_path):
    directory=tmp_path/'plan';save_plan(plan,directory)
    (directory/'apparmor.profile').write_text('profile unsafe { file, }')
    with pytest.raises(Blocked,match='TAMPERED'):verify_plan_files(directory/'plan.json')


def test_symlink_and_overwrite_rejected(tmp_path):
    target=tmp_path/'target';write_new(target,b'secret')
    link=tmp_path/'link';link.symlink_to(target)
    with pytest.raises(Blocked):read_private(link)
    with pytest.raises(FileExistsError):write_new(target,b'overwrite')
    assert target.read_bytes()==b'secret'


def test_hardlinked_input_rejected(tmp_path):
    target=tmp_path/'x';write_new(target,b'{}')
    os.link(target,tmp_path/'y')
    with pytest.raises(Blocked):read_private(target)


def test_symlink_directory_rejected(tmp_path):
    real=tmp_path/'real';real.mkdir(mode=0o700)
    link=tmp_path/'alias';link.symlink_to(real,target_is_directory=True)
    with pytest.raises(Blocked):secure_dir(link/'new')


@pytest.mark.parametrize('mode',['OFFLINE','PUBLIC_EGRESS_LOCAL_DENY'])
def test_real_apparmor_parser(policy,tmp_path,mode):
    data=policy.model_dump();data.update(network_mode=mode,public_dns=['1.1.1.1'] if mode!='OFFLINE' else [])
    policy=Policy.model_validate(data)
    file=tmp_path/'profile';file.write_text(apparmor(policy))
    result=subprocess.run(['/usr/sbin/apparmor_parser','-Q','-T','-K',str(file)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_real_systemd_unit_parser(policy,tmp_path):
    unit=tmp_path/'syntax-test.service'
    unit.write_text('[Service]\nExecStart=/usr/bin/sleep 1\n'+dropin(policy,[]))
    result=subprocess.run(['/usr/bin/systemd-analyze','verify',str(unit)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert 'Unknown' not in result.stderr and 'Failed to parse' not in result.stderr


def test_real_probe_does_not_pass_unconfined(tmp_path):
    exe=tmp_path/'probe'
    subprocess.run(['/usr/bin/cc','-Wall','-Wextra','-Werror',str(ROOT/'scripts/probe.c'),'-o',str(exe)],check=True,capture_output=True)
    allowed=tmp_path/'allowed';allowed.write_text('synthetic')
    denied=tmp_path/'denied';denied.write_text('synthetic')
    sockpath=tmp_path/'socket'
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
        server.bind(str(sockpath));server.listen(4)
        result=subprocess.run([str(exe),str(allowed),str(denied),'/proc/1/environ',str(sockpath),'9','9','not-this-profile (enforce)'],
                              capture_output=True,text=True,timeout=10)
    data=ProbeResults.model_validate_json(result.stdout)
    assert data.allowed_read is True
    assert data.denied_read is False
    assert data.denied_unix is False
    assert data.profile_attached is False
    assert not data.all_pass()


def test_no_shell_true_or_dynamic_exec():
    for file in (ROOT/'service_privacy').glob('*.py'):
        tree=ast.parse(file.read_text())
        assert len(file.read_text().splitlines()) < 800
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                assert not (isinstance(node.func,ast.Name) and node.func.id in ['eval','exec'])
                assert not any(k.arg=='shell' and isinstance(k.value,ast.Constant) and k.value.value is True for k in node.keywords)


def test_frontdoor_rejects_mutation_without_flags(tmp_path):
    env = {**os.environ, 'SERVICE_PRIVACY_PYTHON': sys.executable}
    result=subprocess.run([str(ROOT/'run.sh'),'apply',str(tmp_path/'absent.json'),'--approve-sha256','bad','--probe-receipt','/absent'],
                          capture_output=True,text=True,env=env)
    assert result.returncode==2
    data=json.loads(result.stdout)
    assert data['reason']=='EXPLICIT_EXECUTION_AND_OWNER_AUTHORIZATION_REQUIRED'
    assert 'Traceback' not in result.stderr


def test_rejected_input_not_echoed(tmp_path):
    env = {**os.environ, 'SERVICE_PRIVACY_PYTHON': sys.executable}
    file=tmp_path/'bad.json';file.write_text('{"credential":"SYNTHETIC-SECRET-DO-NOT-ECHO"}')
    result=subprocess.run([str(ROOT/'run.sh'),'config','doctor',str(file)],capture_output=True,text=True,env=env)
    assert result.returncode==2
    assert 'SYNTHETIC-SECRET-DO-NOT-ECHO' not in result.stdout+result.stderr
    assert json.loads(result.stdout)['validation_errors']


def test_frontmatter_and_eval_posture():
    import yaml
    text=(ROOT/'SKILL.md').read_text()
    assert text.startswith('---\n')
    front=yaml.safe_load(text.split('---',2)[1])
    assert front['name']==ROOT.name
    assert 'description: >\n' in text
    assert front['triggers'] and front['provides']
    assert 'agentic-evals' in front['composes'] and 'triage-error' in front['composes']
    assert 'best-practices-skills' in front['complies']
    fixture=json.loads((ROOT/'fixtures/agentic_eval.json').read_text())
    assert fixture['trials']>=3
    assert {case['type'] for case in fixture['cases']}=={'positive','negative','adversarial'}
    privacy=next(c for c in fixture['capability_claims'] if c['id']=='service_privacy.owner_confidentiality')
    assert privacy['evidence_required']['live_e2e'] is True


def test_native_parser_rejects_broken_policy(tmp_path):
    file=tmp_path/'broken';file.write_text('profile broken { THIS IS NOT A VALID RULE }')
    result=subprocess.run(['/usr/sbin/apparmor_parser','-Q','-T','-K',str(file)],capture_output=True,text=True)
    assert result.returncode != 0


def test_manual_check_does_not_claim_continuous_supervision():
    text=(ROOT/'README.md').read_text()
    assert 'snapshot, not continuous supervision' in text
    assert 'This is not an ITAR' in text
