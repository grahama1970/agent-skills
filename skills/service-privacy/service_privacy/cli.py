"""Typer front door: inspect -> plan -> synthetic probe -> approve/apply -> verify.

Host changes require explicit execution and owner authorization. Help is prose;
all operational results and failures are validated structured records.

Diagram: images/confinement-boundary.svg (owner policy -> service-privacy ->
AppArmor + systemd -> kernel enforcement; allowed posture vs denied client data;
updates trigger requalification, never automatic widening).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

from . import core
from .core import Blocked, canonical, checked, load, now, pairs, secure_dir, sha, write_new
from .models import Findings, Info, Policy, TestReceipt
from .planning import build_plan, save_plan, syntax_check, verify_plan_files
from .system import doctor as host_doctor, inspect_unit, unit_name

app = typer.Typer(no_args_is_help=True, add_completion=False,
                  help='Transparent owner-controlled service confinement. No compliance spoofing.')
config_app = typer.Typer(no_args_is_help=True)
app.add_typer(config_app, name='config')


def emit(model) -> None:
    typer.echo(canonical(model).decode())


def authorization(execute: bool, owner_authorized: bool) -> None:
    if not execute or not owner_authorized:
        raise Blocked('EXPLICIT_EXECUTION_AND_OWNER_AUTHORIZATION_REQUIRED')


def profile_for(unit: str) -> str:
    unit_name(unit)
    return 'osp-' + hashlib.sha256(unit.encode()).hexdigest()[:20]


# Optional identity items: toggled in policy JSON read_files ONLY. The code-gated
# RUNTIME_READ_FILES baseline in models.py is never modified by presets.
_OPTIONAL_IDENTITY = {
    '/etc/machine-id': 'stable cross-reinstall device tracking',
    '/etc/kolide-k2/installer-info.json': 'installer metadata (enrollment identity)',
}
_PRESETS: dict[str, frozenset[str]] = {
    'compliance-safe': frozenset(),               # DEFAULT: remove nothing optional
    'minimal-identity': frozenset({'/etc/machine-id'}),
    'locked-down': frozenset(_OPTIONAL_IDENTITY),  # superset of minimal-identity
}


@app.command(name='firewall')
def firewall_command(
    policy_file: Annotated[Path, typer.Argument(help='Policy JSON to inspect or harden')],
    action: Annotated[str, typer.Option('--action', help='show | harden')] = 'show',
    preset: Annotated[str, typer.Option('--preset', help='compliance-safe (default posture) | minimal-identity | locked-down')] = '',
) -> None:
    """Easy data-sharing firewall: show what Kolide may read; harden removes sharable-but-optional items.

    harden never widens access and never mutates the deployed policy by itself:
    it edits the policy file, then prints the exact owner-gated plan/probe/apply
    commands required to deploy. Falsifying returned telemetry is out of scope
    by design: denied reads stay honest 'unavailable'.
    """
    import json as _json
    # Harden presets: items that are optional for posture but leak identity/metadata.
    # These are OPTIONAL identity items toggled in the policy JSON's read_files only;
    # the CODE-GATED RUNTIME_READ_FILES baseline in models.py is never removed.
    HARDENABLE = {'/etc/machine-id': 'stable cross-reinstall device tracking'}
    OPTIONAL_IDENTITY = {
        '/etc/machine-id': 'stable cross-reinstall device tracking',
        '/etc/kolide-k2/installer-info.json': 'installer metadata (enrollment identity)',
    }
    PRESETS: dict[str, set[str]] = {
        'compliance-safe': set(),               # DEFAULT: remove nothing optional, keep client green
        'minimal-identity': {'/etc/machine-id'},
        'locked-down': set(OPTIONAL_IDENTITY),  # superset of minimal-identity
    }
    data = _json.loads(Path(policy_file).read_text())
    if preset:
        if preset not in PRESETS:
            raise typer.BadParameter(f"preset must be one of: {', '.join(PRESETS)}")
        removed = [p for p in data.get('read_files', []) if p in PRESETS[preset]]
        if removed:
            data['read_files'] = [p for p in data['read_files'] if p not in PRESETS[preset]]
            Path(policy_file).write_text(_json.dumps(data, indent=2) + '\n')
        cmd = (f'sudo python3 -m service_privacy plan {policy_file} --output /tmp/fw-plan && '
               f'H=$(sudo cat /tmp/fw-plan/approval-sha256.txt) && '
               f'sudo bash -c \'python3 -m service_privacy probe /tmp/fw-plan/plan.json --execute --owner-authorized > /tmp/fw-probe.json 2>/tmp/fw-probe.err; chmod 600 /tmp/fw-probe.json\' && '
               f'sudo python3 -m service_privacy apply /tmp/fw-plan/plan.json --approve-sha256 $H '
               f'--probe-receipt /tmp/fw-probe.json --execute --owner-authorized --accept-check-failures')
        emit(Info(operation=f'firewall-preset-{preset}', status='PASS', checks={},
                  details={'removed': ', '.join(removed) or '(nothing to remove)',
                           'why': '; '.join(f'{p}={OPTIONAL_IDENTITY[p]}' for p in removed),
                           'deploy_command': cmd,
                           'note': 'deploy is owner-gated; nothing applied yet; operational read_roots untouched'}))
        return
    if action == 'show':
        shares = {'read_files': ', '.join(sorted(data.get('read_files', []))),
                  'read_roots': ', '.join(sorted(data.get('read_roots', []))),
                  'write_roots': ', '.join(sorted(data.get('write_roots', []))),
                  'network_mode': str(data.get('network_mode'))}
        emit(Info(operation='firewall-show', status='PASS', checks={}, details=shares))
        return
    if action == 'harden':
        removed = [p for p in HARDENABLE if p in data.get('read_files', [])]
        if not removed:
            emit(Info(operation='firewall-harden', status='PASS', checks={},
                      details={'removed': '', 'note': 'already hardened'}))
            return
        data['read_files'] = [p for p in data['read_files'] if p not in HARDENABLE]
        Path(policy_file).write_text(_json.dumps(data, indent=2) + '\n')
        cmd = (f'sudo python3 -m service_privacy plan {policy_file} --output /tmp/fw-plan && '
               f'H=$(sudo cat /tmp/fw-plan/approval-sha256.txt) && '
               f'sudo bash -c \'python3 -m service_privacy probe /tmp/fw-plan/plan.json --execute --owner-authorized > /tmp/fw-probe.json 2>/tmp/fw-probe.err; chmod 600 /tmp/fw-probe.json\' && '
               f'sudo python3 -m service_privacy apply /tmp/fw-plan/plan.json --approve-sha256 $H '
               f'--probe-receipt /tmp/fw-probe.json --execute --owner-authorized --accept-check-failures')
        emit(Info(operation='firewall-harden', status='PASS', checks={},
                  details={'removed': ', '.join(removed), 'why': '; '.join(f'{p}={HARDENABLE[p]}' for p in removed),
                           'deploy_command': cmd,
                           'note': 'deploy is owner-gated; nothing applied yet'}))
        return
    raise typer.BadParameter("action must be 'show' or 'harden'")


@app.command()
def doctor() -> None:
    """Read-only host prerequisites; no installation or configuration changes."""
    checks = host_doctor()
    emit(Info(operation='doctor', status='PASS' if all(checks.values()) else 'BLOCKED', checks=checks,
              details={'privacy_boundary': 'NOT_ESTABLISHED', 'safe_default': 'do_not_apply_on_missing_prerequisites'}))
    if not all(checks.values()):
        raise typer.Exit(2)


@app.command(name='inspect')
def inspect_command(unit: Annotated[str, typer.Option('--unit')]) -> None:
    """Read canonical unit identity and approved-command candidates; omits argv and tokens."""
    emit(inspect_unit(unit))


def unit_summary(unit: str, window: str) -> dict[str, str]:
    """Read-only state summary shared by `logs` and `health`. No status verdict here."""
    import subprocess
    run = lambda c: subprocess.run(c, capture_output=True, text=True).stdout.strip()
    profile = profile_for(unit)
    kern = run(['journalctl', '-k', '--since', window, '--no-pager'])
    denied = [l for l in kern.splitlines() if profile in l and 'DENIED' in l]
    return {'unit': unit, 'profile': profile,
            'active_state': run(['systemctl', 'is-active', unit]),
            'restarts': run(['systemctl', 'show', unit, '-p', 'NRestarts', '--value']),
            'main_pid': run(['systemctl', 'show', unit, '-p', 'MainPID', '--value']),
            'apparmor_denials_in_window': str(len(denied)), 'window': window,
            'denied_lines': '\n'.join(denied[-40:]),
            'denials_hint': 'journalctl -k --since "' + window + '" | grep "' + profile + '.*DENIED"'}


@app.command(name='logs')
def logs_command(unit: Annotated[str, typer.Option('--unit')],
                 window: str = '-1 hour', follow: bool = False, denials: bool = False) -> None:
    """Read-only at-a-glance: service state, restart count, and AppArmor denials for the
    confined unit. --follow tails the live service log; --denials lists kernel denial records
    (the crash-cause log). Denials are the first thing to read when a confined service dies.

    status is always a schema-valid PASS here; the live service state itself is in
    details.active_state (Info.status is not a service-state field).
    """
    if follow:
        os.execvp('journalctl', ['journalctl', '-u', unit, '-f'])
    summary = unit_summary(unit, window)
    denied_lines = summary.pop('denied_lines')
    if denials:
        sys.stderr.write(denied_lines + ('\n' if denied_lines else 'no denials in window\n'))
    summary['follow_hint'] = 'journalctl -u ' + unit + ' -f'
    emit(Info(operation='logs', status='PASS', details=summary))


@app.command(name='configure')
def configure_command(policy_file: Path,
                      preset: Annotated[str, typer.Option('--preset', help='compliance-safe | minimal-identity | locked-down')] = '',
                      non_interactive: Annotated[bool, typer.Option('--non-interactive')] = False) -> None:
    """Pick a privacy preset (or toggle individual optional items) via the interview skill,
    then rewrite the policy JSON and print the owner-gated deploy command.

    --non-interactive skips the human interview and applies the named preset
    (compliance-safe if none given) so the path is testable without a human.
    """
    import json as _json
    import subprocess
    import tempfile
    data = _json.loads(Path(policy_file).read_text())
    optional = {p: why for p, why in _OPTIONAL_IDENTITY.items() if p in data.get('read_files', [])}
    if non_interactive:
        chosen = preset or 'compliance-safe'
        if chosen not in _PRESETS:
            raise typer.BadParameter(f"preset must be one of: {', '.join(_PRESETS)}")
        removed_preset = [p for p in data.get('read_files', []) if p in _PRESETS[chosen]]
        removed = removed_preset
        source = f'preset:{chosen}'
    else:
        questions = {
            'title': 'Service privacy preset',
            'context': 'Choose how much optional device identity telemetry may read. Operational runtime reads are not affected.',
            'questions': [
                {'id': 'preset', 'text': 'Which privacy preset?', 'type': 'single_select',
                 'recommendation': 'compliance-safe', 'header': 'Preset',
                 'options': [
                     {'label': 'compliance-safe', 'description': 'DEFAULT: remove nothing optional; keep the client green (recommended)'},
                     {'label': 'minimal-identity', 'description': 'Remove /etc/machine-id'},
                     {'label': 'locked-down', 'description': 'Remove /etc/machine-id and all other optional identity reads'},
                     {'label': 'individual', 'description': 'Toggle individual optional items instead'}]},
                {'id': 'items', 'text': 'Which optional identity reads should be removed?',
                 'type': 'single_select', 'multi_select': True, 'required': False, 'header': 'Items',
                 'options': [{'label': p, 'description': w} for p, w in optional.items()] or [{'label': 'none', 'description': 'no optional items present'}]},
            ]}
        interview_run = core.ROOT.parent / 'interview' / 'run.sh'
        if not interview_run.is_file():
            raise Blocked('INTERVIEW_SKILL_UNAVAILABLE')
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as fh:
            _json.dump(questions, fh)
            qfile = fh.name
        result = subprocess.run(['bash', str(interview_run), '-f', qfile, '--json'],
                                capture_output=True, text=True)
        if result.returncode != 0:
            raise Blocked(f'INTERVIEW_FAILED: {result.stderr.strip()[:200]}')
        answers = _json.loads(result.stdout)['responses']
        chosen = answers.get('preset', {}).get('value', 'compliance-safe')
        if chosen == 'individual':
            value = answers.get('items', {}).get('value', [])
            chosen_items = value if isinstance(value, list) else [value]
            removed = [p for p in data.get('read_files', []) if p in chosen_items and p in _OPTIONAL_IDENTITY]
            source = 'individual'
        else:
            if chosen not in _PRESETS:
                raise Blocked(f'INTERVIEW_RETURNED_UNKNOWN_PRESET: {chosen}')
            removed = [p for p in data.get('read_files', []) if p in _PRESETS[chosen]]
            source = f'preset:{chosen}'
    if removed:
        data['read_files'] = [p for p in data['read_files'] if p not in removed]
        Path(policy_file).write_text(_json.dumps(data, indent=2) + '\n')
    cmd = (f'sudo python3 -m service_privacy plan {policy_file} --output /tmp/fw-plan && '
           f'H=$(sudo cat /tmp/fw-plan/approval-sha256.txt) && '
           f'sudo bash -c \'python3 -m service_privacy probe /tmp/fw-plan/plan.json --execute --owner-authorized > /tmp/fw-probe.json 2>/tmp/fw-probe.err; chmod 600 /tmp/fw-probe.json\' && '
           f'sudo python3 -m service_privacy apply /tmp/fw-plan/plan.json --approve-sha256 $H '
           f'--probe-receipt /tmp/fw-probe.json --execute --owner-authorized --accept-check-failures')
    emit(Info(operation='configure', status='PASS', checks={},
              details={'source': source, 'removed': ', '.join(removed) or '(nothing to remove)',
                       'deploy_command': cmd, 'policy_file': str(policy_file),
                       'note': 'deploy is owner-gated; nothing applied yet; operational read_roots untouched'}))


@app.command(name='health')
def health_command(unit: Annotated[str, typer.Option('--unit')],
                   window: str = '-1 hour',
                   kolide_tab_id: Annotated[str, typer.Option('--kolide-tab-id', help='Kolide browser dashboard device tab id for the surf snapshot hint')] = '') -> None:
    """Read-only health summary plus an optional hint to capture the Kolide browser
    dashboard via the surf skill. Surf is OPTIONAL: absence is reported, never a failure.
    """
    import socket
    summary = unit_summary(unit, window)
    denied_lines = summary.pop('denied_lines')
    details = dict(summary)
    try:
        with socket.create_connection(('127.0.0.1', 9222), timeout=1):
            details['surf_cdp'] = 'available on 127.0.0.1:9222'
        snap = 'bash ' + str(core.ROOT.parent / 'surf' / 'run.sh') + ' snap'
        tab = f' (Kolide device tab {kolide_tab_id})' if kolide_tab_id else ''
        details['dashboard_capture_hint'] = f'{snap} --output /tmp/kolide-dashboard.png{tab}'
    except OSError:
        details['surf_cdp'] = 'absent (surf/CDP not running on 127.0.0.1:9222); start Chrome CDP to enable dashboard snapshots'
    details['scheduler_hint'] = ('hourly check: run `python3 -m service_privacy health --unit ' + unit +
                                 '` from the scheduler skill (skills/scheduler) and alert on apparmor_denials_in_window > 0')
    emit(Info(operation='health', status='PASS', checks={}, details=details))


@config_app.command(name='init')
def config_init(unit: Annotated[str, typer.Option('--unit')],
                executable: Annotated[list[str], typer.Option('--executable')],
                output: Annotated[Path, typer.Option('--output')]) -> None:
    """Create a JSON policy template; exact executable paths come from inspect."""
    policy = Policy(unit=unit, executables=executable)
    write_new(output.absolute(), canonical(policy) + b'\n')
    emit(Info(operation='config.init', status='REVIEW_REQUIRED', paths=[str(output.absolute())],
              details={'network_mode': 'OFFLINE', 'owner_acknowledges_limits': 'false',
                       'next_step': 'Review paths and limitations, then set the acknowledgement in the policy.'}))


@config_app.command(name='doctor')
def config_doctor(policy_file: Path) -> None:
    """Validate strict policy shape and non-negotiable exclusions."""
    policy = load(policy_file, Policy)
    emit(Info(operation='config.doctor', status='PASS' if policy.owner_acknowledges_limits else 'REVIEW_REQUIRED',
              details={'unit': policy.unit, 'network_mode': policy.network_mode,
                       'privacy_boundary': 'NOT_ESTABLISHED'}))


@app.command()
def plan(policy_file: Path, output: Annotated[Path, typer.Option('--output')]) -> None:
    """Inspect this host and write a new review bundle. Never changes service state."""
    policy = load(policy_file, Policy)
    proposal = build_plan(policy)
    digest = save_plan(proposal, output.absolute())
    emit(Info(operation='plan', status='CREATED', paths=[str(output.absolute() / 'plan.json')],
              details={'approve_sha256': digest, 'privacy_boundary': 'NOT_ESTABLISHED',
                       'network_mode': policy.network_mode}))


@app.command(name='check-policy')
def check_policy(plan_file: Path) -> None:
    """Re-render/hash-check artifacts and run AppArmor's userspace parser only."""
    verify_plan_files(plan_file)
    syntax_check(plan_file.parent / 'apparmor.profile')
    emit(Info(operation='check-policy', status='PASS', details={'scope': 'SYNTAX_ONLY_NOT_KERNEL_ENFORCEMENT'}))


@app.command()
def probe(plan_file: Path, execute: bool = False, owner_authorized: bool = False) -> None:
    """Run local synthetic canaries under temporary real AppArmor/systemd controls."""
    authorization(execute, owner_authorized)
    from .probe import live_probe
    path, receipt = live_probe(verify_plan_files(plan_file))
    emit(receipt)
    logger.info('Root-private probe receipt: {}', path)
    if receipt.status != 'PASS':
        raise typer.Exit(2)


@app.command()
def apply(plan_file: Path, approve_sha256: Annotated[str, typer.Option('--approve-sha256')],
          probe_receipt: Annotated[Path, typer.Option('--probe-receipt')],
          execute: bool = False, owner_authorized: bool = False, accept_check_failures: bool = False) -> None:
    """Apply exact approved plan after a fresh same-host probe. Stops on failure."""
    authorization(execute, owner_authorized)
    if not accept_check_failures:
        raise Blocked('CHECK_FAILURE_ACKNOWLEDGEMENT_REQUIRED')
    from .deploy import apply_plan
    emit(apply_plan(plan_file, approve_sha256, probe_receipt))


@app.command()
def verify(unit: Annotated[str, typer.Option('--unit')], stop_on_drift: bool = False,
           execute: bool = False, owner_authorized: bool = False) -> None:
    """Read back effective settings, all service thread labels, capabilities and hashes."""
    if stop_on_drift:
        authorization(execute, owner_authorized)
    from .deploy import verify_service
    result = verify_service(profile_for(unit), stop_on_drift)
    emit(result)
    if result.status != 'RUNTIME_CHECKS_PASS':
        raise typer.Exit(2)


@app.command()
def rollback(unit: Annotated[str, typer.Option('--unit')], execute: bool = False,
             owner_authorized: bool = False) -> None:
    """Remove only owned unchanged policy; park the service OFF with a visible hold."""
    authorization(execute, owner_authorized)
    from .deploy import rollback as rollback_service
    emit(rollback_service(profile_for(unit)))


@app.command(name='repo-check')
def repo_check() -> None:
    """Delegate to the installed best-practices-skills validator; parse findings."""
    validator = core.ROOT.parent / 'best-practices-skills/scripts/validate_skill.py'
    if not validator.is_file():
        raise Blocked('REPOSITORY_VALIDATOR_UNAVAILABLE')
    result = checked([sys.executable, str(validator), str(core.ROOT), '--json',
                      '--skills-root', str(core.ROOT.parent)])
    values = json.loads(result.stdout, object_pairs_hook=pairs)
    report = Findings.model_validate({'findings': values})
    emit(report)
    if any(item.severity == 'error' for item in report.findings):
        raise typer.Exit(2)


@app.command(name='self-test')
def self_test(output: Annotated[Path, typer.Option('--output')]) -> None:
    """Run retained behavioral tests; keep scoped test and JUnit receipts."""
    directory = output.absolute()
    if directory.exists() or directory.is_symlink():
        raise Blocked('TEST_OUTPUT_MUST_BE_NEW')
    secure_dir(directory)
    xml = directory / 'junit.xml'
    from .core import command
    result = command([sys.executable, '-B', '-m', 'pytest', '-q', str(core.ROOT / 'tests'), '--junitxml=' + str(xml)], 180)
    write_new(directory / 'stdout.txt', result.stdout.encode())
    write_new(directory / 'stderr.txt', result.stderr.encode())
    if not xml.exists():
        raise Blocked('JUNIT_RECEIPT_MISSING')
    xml.chmod(0o600)
    suites = ET.parse(xml).getroot()
    selected = list(suites) if suites.tag == 'testsuites' else [suites]
    counts = {key: sum(int(suite.attrib.get(key, '0')) for suite in selected) for key in ['tests', 'failures', 'errors', 'skipped']}
    passed = counts['tests'] > 0 and all(counts[key] == 0 for key in ['failures', 'errors', 'skipped']) and result.returncode == 0
    receipt = TestReceipt(timestamp=now(), status='PASS' if passed else 'FAIL', **counts, returncode=result.returncode,
                          claims_proves=['typed policy guards', 'deterministic rendering and transaction fault handling',
                                         'native userspace syntax checks and independent unconfined negative control'],
                          claims_does_not_prove=['live kernel confinement', 'Kolide compatibility', 'complete information isolation',
                                                'ITAR compliance', 'canonical ecosystem gate execution'])
    write_new(directory / 'report.json', canonical(receipt) + b'\n')
    emit(receipt)
    if not passed:
        raise typer.Exit(2)


def main() -> None:
    logger.remove()
    logger.add(sys.stderr, format='{level}: {message}', level='INFO')
    try:
        # standalone_mode=False makes Click RETURN a command's exit code instead
        # of raising typer.Exit, so a clean `raise typer.Exit(2)` (e.g. doctor
        # BLOCKED) would otherwise be discarded and the process would exit 0 —
        # a false green. Honor the returned code.
        rv = app(standalone_mode=False)
        if isinstance(rv, int) and rv != 0:
            raise SystemExit(rv)
    except typer.Exit as error:
        raise SystemExit(error.exit_code) from None
    except KeyboardInterrupt:
        emit(core.make_failure(Blocked('OPERATOR_INTERRUPTED')))
        raise SystemExit(130) from None
    except Exception as error:
        emit(core.make_failure(error))
        raise SystemExit(2) from None
