"""Typer front door: inspect -> plan -> synthetic probe -> approve/apply -> verify.

Host changes require explicit execution and owner authorization. Help is prose;
all operational results and failures are validated structured records.
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
        app(standalone_mode=False)
    except typer.Exit as error:
        raise SystemExit(error.exit_code) from None
    except KeyboardInterrupt:
        emit(core.make_failure(Blocked('OPERATOR_INTERRUPTED')))
        raise SystemExit(130) from None
    except Exception as error:
        emit(core.make_failure(error))
        raise SystemExit(2) from None
