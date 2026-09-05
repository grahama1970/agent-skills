"""Read-only Meet composition: inspect owning skills, never replace their runtimes."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4

import typer
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

load_dotenv(override=False)

ROOT = Path(__file__).resolve().parent
SKILLS = ROOT.parent
OUTPUTS = Path('/mnt/storage12tb/skills/ops-google-meet/outputs')
app = typer.Typer(no_args_is_help=True)


class MeetTarget(BaseModel):
    model_config = ConfigDict(extra='forbid')
    url: str

    @field_validator('url')
    @classmethod
    def meet_only(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or parsed.hostname != 'meet.google.com'
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            raise ValueError('Use an HTTPS meet.google.com URL without embedded credentials')
        return value


class Probe(BaseModel):
    model_config = ConfigDict(extra='forbid')
    owner: str
    argv: list[str]
    exit_code: int | None = None
    payload: dict[str, Any] | list[dict[str, Any]] | None = None
    error: str | None = None

    @model_validator(mode='after')
    def owner_contract(self):
        if self.payload is None:
            if self.error is None:
                raise ValueError('missing payload requires an error')
            return self
        if self.owner == 'surf':
            if not isinstance(self.payload, list) or any(
                not isinstance(tab.get('id'), int) or not isinstance(tab.get('url'), str)
                or not isinstance(tab.get('windowId'), int) for tab in self.payload
            ):
                raise ValueError('Surf tab identity fields missing')
        elif self.owner == 'live-evidence':
            if (not isinstance(self.payload, dict)
                    or not isinstance(self.payload.get('health'), dict)
                    or not isinstance(self.payload.get('state'), dict)
                    or self.payload['state'].get('schema') != 'live_evidence.app_snapshot.v1'):
                raise ValueError('Live Evidence status envelope missing')
        else:
            schemas = {'ops-google-calendar': 'ops_google_calendar.status.v1',
                       'ops-workstation': 'ops_workstation.audio_switch.v1',
                       'ops-chatterbox': 'ops_chatterbox.doctor_receipt.v1'}
            if not isinstance(self.payload, dict) or self.payload.get('schema') != schemas.get(self.owner):
                raise ValueError('owning skill receipt schema mismatch')
            if not isinstance(self.payload.get('status'), str):
                raise ValueError('owning skill status missing')
        return self


class Report(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_id: Literal['ops_google_meet.preflight.v1'] = Field(default='ops_google_meet.preflight.v1', serialization_alias='schema')
    command: str
    status: Literal['OBSERVED', 'PLAN_ONLY', 'NEEDS_ATTENTION']
    release_readiness: Literal['NOT_ESTABLISHED'] = 'NOT_ESTABLISHED'
    read_only: Literal[True] = True
    capture_started: Literal[False] = False
    meeting_joined: Literal[False] = False
    probes: list[Probe] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    plan: list[dict[str, Any]] = Field(default_factory=list)
    seam_validation: dict[str, str] = Field(default_factory=lambda: {'kind': 'pydantic', 'status': 'PASS'})


def probe(owner: str, *args: str) -> Probe:
    runner = SKILLS / owner / 'run.sh'
    command = [str(runner), *args]
    if not runner.is_file() or not os.access(runner, os.X_OK):
        return Probe(owner=owner, argv=command, error='owning_skill_runner_unavailable')
    env = {k: v for k, v in os.environ.items() if k not in {'VIRTUAL_ENV', 'UV_PROJECT_ENVIRONMENT'}}
    env['OUTPUT'] = 'json'
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60, cwd=SKILLS.parent)
        try:
            payload = json.loads(result.stdout)
            if not isinstance(payload, (dict, list)):
                raise ValueError('Expected JSON object or array')
            if owner == 'live-evidence' and isinstance(payload, dict) and isinstance(payload.get('state'), dict):
                state = payload['state']
                payload = {'health': payload.get('health'), 'state': {
                    'schema': state.get('schema'), 'session': state.get('session'),
                    'listener': state.get('listener'), 'card_count': len(state.get('cards', [])),
                    'ask_lane': [lane for lane in state.get('lanes', []) if lane.get('lane') == 'ask'],
                }}
            return Probe(owner=owner, argv=command, exit_code=result.returncode, payload=payload)
        except (ValueError, ValidationError):
            return Probe(owner=owner, argv=command, exit_code=result.returncode, error='owning_skill_output_not_structured')
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Probe(owner=owner, argv=command, error=type(exc).__name__)


def emit(report: Report, output: Path | None) -> None:
    # Validate before emission and atomically replace only the requested receipt.
    text = Report.model_validate(report.model_dump()).model_dump_json(by_alias=True, indent=2)
    path = output or OUTPUTS / f'{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}' / 'report.json'
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    temporary.write_text(text + '\n'); temporary.chmod(0o600); temporary.replace(path)
    typer.echo(text)
    typer.echo(f'Receipt: {path}', err=True)


@app.command()
def doctor(output: Path | None = None):
    """Compose read-only Calendar, audio, TTS and Surf probes. Never join or record."""
    probes = [probe('ops-google-calendar', 'status', '--json'),
              probe('ops-workstation', 'audio-switch', 'status'),
              probe('ops-chatterbox', 'doctor', '--json'),
              probe('surf', 'tab.list', '--json'),
              probe('live-evidence', 'status')]
    findings = []
    calendar, audio, tts, browser, companion = probes
    for item in probes:
        if item.error or item.exit_code != 0:
            findings.append(f'{item.owner}: {item.error or "diagnostic_nonzero_exit"}')
    if not isinstance(calendar.payload, dict) or calendar.payload.get('authenticated') is not True:
        findings.append('calendar_oauth_required: use ops-google-calendar auth setup')
    targets = audio.payload.get('targets', {}) if isinstance(audio.payload, dict) else {}
    jabra = targets.get('jabra-bt') or {}
    if not jabra.get('sink') or not jabra.get('source'):
        findings.append('jabra_bluetooth_input_or_output_unavailable')
    if not isinstance(tts.payload, dict) or tts.payload.get('ok') is not True:
        findings.append('chatterbox_not_ready: use ops-chatterbox diagnostics')
    if not isinstance(companion.payload, dict) or companion.payload.get('health', {}).get('status') != 'ok':
        findings.append('live_evidence_service_unavailable')
    findings.extend(['monitor_bindings_required: center teleprompter and right display identities are not configured',
                     'automatic_companion_launch_not_implemented',
                     'real_meet_audio_video_acceptance_not_run'])
    emit(Report(command='doctor', status='NEEDS_ATTENTION', probes=probes, findings=findings), output)
    raise typer.Exit(1)


@app.command()
def observe(output: Path | None = None):
    """Inventory manually opened Meet tabs and pair each with a mandatory companion requirement."""
    tabs = probe('surf', 'tab.list', '--json')
    if tabs.error or tabs.exit_code != 0 or not isinstance(tabs.payload, list):
        emit(Report(command='observe', status='NEEDS_ATTENTION', probes=[tabs], findings=['meet_tab_inventory_unavailable']), output)
        raise typer.Exit(1)
    plan = []
    for tab in tabs.payload:
        url = tab.get('url', '')
        if isinstance(url, str) and urlsplit(url).hostname == 'meet.google.com':
            plan.append({'meet_tab_id': tab.get('id'), 'meet_window_id': tab.get('windowId'),
                         'companion_required': True, 'companion_readiness': 'NOT_ESTABLISHED',
                         'meet_display_role': 'center-teleprompter', 'companion_display_role': 'right',
                         'action': 'ensure_live_evidence_after_verified_display_binding'})
    emit(Report(command='observe', status='NEEDS_ATTENTION' if plan else 'OBSERVED', probes=[tabs], plan=plan,
                findings=['Inventory only; no continuous monitor or automatic launcher is installed.']), output)
    if plan:
        raise typer.Exit(1)


@app.command()
def plan(url: str, output: Path | None = None):
    """Validate a Meet destination and emit the required composition; no execution."""
    try:
        target = MeetTarget(url=url)
    except ValidationError as exc:
        typer.echo(exc.json(include_url=False, include_input=False), err=True)
        raise typer.Exit(2)
    steps = [
        {'owner': 'surf', 'action': 'open_or_reuse_meet', 'url': target.url, 'display': 'center-teleprompter'},
        {'owner': 'live-evidence', 'action': 'ensure_companion_service', 'required': True},
        {'owner': 'surf', 'action': 'open_or_reuse_companion', 'display': 'right'},
        {'owner': 'ops-workstation', 'action': 'verify_separate_remote_output_and_local_mic'},
        {'owner': 'live-evidence', 'action': 'capture_only_after_consent_and_policy_validation'},
    ]
    emit(Report(command='plan', status='PLAN_ONLY', plan=steps, findings=[
        'Monitor identity/enabled-state verification is required before positioning.',
        'Opening applications does not authorize joining, microphone/camera activation or transcription.',
        'Plan is not execution; recurring calendar and manual-tab launch enforcement remain unimplemented.',
    ]), output)


if __name__ == '__main__':
    app()
