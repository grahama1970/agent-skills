"""Fulfill explicit cockpit intents through the owning debugger skill.

The bridge is opt-in, loopback-only, single-worker and revision fenced. It
never executes an imported runtime_launch command or watch expression. Watch
mode fulfills reveal/prepare only; a named VS Code launch requires a separate
one-shot --run-breakpoint invocation. Native results are read from artifacts.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Literal
from uuid import uuid4

import httpx
from loguru import logger
from pydantic import Field, TypeAdapter
import typer

from .models import (AdapterReceipt, BootstrapResponse, DebuggerProofReference,
                     DebuggerRevealStatus, StrictModel)

DEBUGGER = Path(__file__).resolve().parents[3] / 'debugger' / 'run.sh'


class PendingStatus(StrictModel):
    id: str
    requestHash: str
    status: Literal['pending']
    updatedAt: str


class AddedBreakpoint(StrictModel):
    file: str
    line: int = Field(ge=1)
    enabled: Literal[True]
    adapterVerification: Literal['unavailable-vscode-api']


class PreparedStatus(StrictModel):
    id: str
    requestHash: str
    status: Literal['breakpoints-added']
    proofValid: Literal[False]
    addedBreakpoints: list[AddedBreakpoint] = Field(min_length=1)
    adapterBreakpointVerification: Literal['unavailable-vscode-api']
    authority: dict
    artifactLocations: dict[str, str]
    updatedAt: str


STATUS = TypeAdapter(PendingStatus | DebuggerRevealStatus | PreparedStatus)


class ExecutionResult(StrictModel):
    schema_: Literal['explain_project.execution_result.v1'] = Field(
        alias='schema', default='explain_project.execution_result.v1')
    status: Literal['IDLE', 'DRY_RUN', 'APPLIED', 'STALE', 'BLOCKED', 'REFUSED']
    request_revision: int
    command: list[str] = Field(default_factory=list)
    receipt: AdapterReceipt | None = None
    status_path: str | None = None
    detail: str | None = None


def contained_file(repo: Path, value: str) -> Path:
    path = (repo / value).resolve(strict=True)
    if not path.is_relative_to(repo) or not path.is_file():
        raise ValueError('Source target must be a file within --repo')
    return path


def command_output(command: list[str], repo: Path, out: Path, name: str) -> str:
    result = subprocess.run(command, cwd=repo, capture_output=True, text=True, timeout=30)
    (out / f'{name}.stdout').write_text(result.stdout)
    (out / f'{name}.stderr').write_text(result.stderr)
    if result.returncode:
        raise RuntimeError(f'Debugger command exited {result.returncode}; see {out / (name + ".stderr")}')
    return result.stdout


def fulfill(client: httpx.Client, repo: Path, out_dir: Path, execute: bool,
            launch_config: str | None = None) -> ExecutionResult:
    response = client.get('/api/cockpit/bootstrap')
    response.raise_for_status()
    state = BootstrapResponse.model_validate(response.json()).state
    intent = state.source.reveal_intent or state.debugger.prepare_intent
    if state.selection is None or (intent is None and launch_config is None):
        return ExecutionResult(status='IDLE', request_revision=state.revision)
    adapter = ('debugger_proof' if launch_config is not None else
               'source_reveal' if state.source.reveal_intent else 'debugger_prepare')
    target = state.debugger.target if adapter != 'source_reveal' else state.source.location
    request_id = 'cockpit-' + uuid4().hex
    out = out_dir / request_id
    out.mkdir(parents=True, exist_ok=False)
    result = ExecutionResult(status='REFUSED', request_revision=state.revision)
    receipt = AdapterReceipt(receipt_id=request_id, adapter=adapter,
                             request_revision=state.revision,
                             feature_id=state.selection.feature_id,
                             step_id=state.selection.step_id, status='REFUSED')
    try:
        if target is None:
            raise ValueError('No debugger target on the selected step')
        path = contained_file(repo, target.file)
        line = target.start_line if adapter == 'source_reveal' else target.line
        end = target.end_line if adapter == 'source_reveal' else line
        if path.stat().st_size > 2_000_000 or end > len(path.read_text().splitlines()):
            raise ValueError('Target range is outside the bounded source file')
        source_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        action = ('start' if launch_config else 'reveal' if adapter == 'source_reveal' else 'addBreakpoints')
        command = [str(DEBUGGER), 'request', '--workspace', str(repo), '--action', action,
                   '--id', request_id, '--expect-extension-host-kind', 'ui',
                   '--keep-breakpoints', '--no-save-before-start']
        if adapter == 'source_reveal':
            command += ['--reveal', f'{path}:{line}:1:{end}:1']
        else:
            command += ['--break', f'{path}:{line}']
        if launch_config:
            if not (repo / '.vscode' / 'launch.json').is_file():
                raise ValueError('Trusted workspace has no launch.json')
            # VS Code owns JSONC parsing and named configuration resolution.
            command += ['--launch-config-name', launch_config]
            for name in target.locals:
                command += ['--local', name]
        result.command = command
        if not execute:
            result.status = 'DRY_RUN'
            return result
        # Read again immediately before an external effect, without replaying a
        # request when another question/step has superseded the clicked intent.
        fresh = client.get('/api/cockpit/bootstrap')
        fresh.raise_for_status()
        if BootstrapResponse.model_validate(fresh.json()).state.revision != state.revision:
            result.status = 'STALE'
            result.detail = 'Revision changed before dispatch; no external effect requested'
            return result
        lines = command_output(command, repo, out, 'request').strip().splitlines()
        if len(lines) != 2:
            raise RuntimeError('Debugger request did not return its two artifact paths')
        request_path, status_path = map(Path, lines)
        request = json.loads(request_path.read_text())
        expected_root = Path(os.environ.get('XDG_RUNTIME_DIR') or tempfile.gettempdir()) / 'agent-skills-debugger'
        if (request['id'] != request_id or request['workspace'] != str(repo)
                or status_path.name != f'status.{request_id}.json'
                or not status_path.resolve().is_relative_to(expected_root.resolve())
                or str(status_path) != request['output']):
            raise ValueError('Debugger artifact ownership mismatch')
        result.status_path = str(status_path)
        (out / 'request.json').write_text(json.dumps(request, indent=2))
        deadline = time.monotonic() + (40 if launch_config else 10)
        while True:
            raw = status_path.read_text()
            data = json.loads(raw)
            # Pending/start states are transport observations, never proof.
            if data.get('status') not in ('pending', 'starting'):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(f'Debugger bridge did not settle; inspect {status_path}')
            time.sleep(.2)
        (out / 'native-status.json').write_text(raw)
        if data.get('id') != request_id or data.get('requestHash') != request['requestHash']:
            raise ValueError('Debugger result belongs to another request')
        if source_digest != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError('Source bytes changed during the adapter request')
        if launch_config:
            canonical = out / 'debugger.proof.json'
            command_output([str(DEBUGGER), 'validate', str(status_path), '--expect-valid',
                            '--canonical-out', str(canonical)], repo, out, 'validate')
            proof = json.loads(canonical.read_text())
            frame = proof['stopped']['frame']
            if Path(frame['file']).resolve() != path or frame['line'] != line:
                raise ValueError('Debugger stopped outside the selected breakpoint')
            if any(name not in proof['captures']['locals'] for name in target.locals):
                raise ValueError('Debugger proof lacks requested locals')
            receipt.status = 'PROOF_RECEIVED'
            receipt.proof = DebuggerProofReference(proof_path=str(canonical),
                sha256='sha256:' + hashlib.sha256(canonical.read_bytes()).hexdigest(), proves=target.proves)
        else:
            status = STATUS.validate_python(data)
            if adapter == 'source_reveal':
                if not isinstance(status, DebuggerRevealStatus) or (
                        Path(status.reveal.file).resolve() != path or status.reveal.line != line
                        or status.reveal.endLine != end):
                    raise ValueError('Source reveal does not match the selected range')
                receipt.status = 'REVEALED'
            else:
                if not isinstance(status, PreparedStatus) or not any(
                        Path(bp.file).resolve() == path and bp.line == line for bp in status.addedBreakpoints):
                    raise ValueError('Prepared breakpoint does not match the selected target')
                receipt.status = 'PREPARED'
        receipt.detail = f'{receipt.status}; native readback {out / "native-status.json"}; source sha256:{source_digest}'
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        logger.error('Debugger adapter failed: {}', error)
        receipt.status = 'BLOCKED'
        receipt.proof = None
        receipt.detail = str(error)
        result.detail = str(error)
    finally:
        # Even blocked/stale dispatches retain a local artifact. Only a matching
        # live revision can admit the result back into the cockpit below.
        (out / 'execution.json').write_text(result.model_dump_json(by_alias=True, indent=2))
    result.receipt = receipt
    if not execute:
        result.status = 'REFUSED'
    else:
        posted = client.post('/api/cockpit/event', json={
            'schema': 'explain_project.cockpit_event.v1', 'event_id': request_id,
            'expected_revision': state.revision, 'type': 'adapter.receipt',
            'payload': {'receipt': receipt.model_dump(by_alias=True, mode='json')}})
        if posted.status_code == 409:
            result.status = 'STALE'
            result.detail = 'Native result retained, but not applied to a newer cockpit revision'
        else:
            posted.raise_for_status()
            readback = client.get('/api/cockpit/bootstrap')
            readback.raise_for_status()
            observed = BootstrapResponse.model_validate(readback.json()).state
            if not any(r == receipt for r in observed.adapter_receipts):
                result.status = 'BLOCKED'
                result.detail = 'Cockpit receipt absent from independent readback'
            else:
                result.status = 'BLOCKED' if receipt.status == 'BLOCKED' else 'APPLIED'
    (out / 'execution.json').write_text(result.model_dump_json(by_alias=True, indent=2))
    return result


def bridge_command(
    repo: Path = typer.Option(..., '--repo', exists=True, file_okay=False),
    base_url: str = typer.Option('http://127.0.0.1:15174', '--base-url'),
    out_dir: Path = typer.Option(..., '--out-dir'),
    execute: bool = typer.Option(False, '--execute'),
    watch: bool = typer.Option(False, '--watch'),
    run_breakpoint: str | None = typer.Option(None, '--run-breakpoint', help='One-shot named VS Code launch; never taken from imported JSON.'),
) -> None:
    """Fulfill explicit reveal/prepare intents; runtime launch is one-shot only."""
    url = httpx.URL(base_url)
    if (url.scheme != 'http' or url.host not in {'127.0.0.1', 'localhost', '::1'}
            or url.path not in ('', '/') or url.userinfo or url.query or url.fragment):
        raise typer.BadParameter('--base-url must be a loopback HTTP origin')
    if run_breakpoint is not None and not run_breakpoint.strip():
        raise typer.BadParameter('--run-breakpoint requires a nonempty configuration name')
    if watch and (not execute or run_breakpoint):
        raise typer.BadParameter('--watch requires --execute and forbids --run-breakpoint')
    repo = repo.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    lock_name = hashlib.sha256(str(url).encode()).hexdigest()[:20]
    fd = os.open(Path(tempfile.gettempdir()) / f'explain-bridge-{os.getuid()}-{lock_name}.lock',
                 os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with httpx.Client(base_url=str(url), timeout=5, trust_env=False) as client:
            while True:
                result = fulfill(client, repo, out_dir, execute, run_breakpoint)
                if result.status != 'IDLE' or not watch:
                    typer.echo(result.model_dump_json(by_alias=True))
                if not watch:
                    if result.status in {'BLOCKED', 'REFUSED', 'STALE'}:
                        raise typer.Exit(1)
                    return
                time.sleep(.5)
    finally:
        os.close(fd)


if __name__ == '__main__':
    typer.run(bridge_command)
