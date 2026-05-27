"""Configuration commands for /ask release readiness."""

from __future__ import annotations

from .env import load_dotenv_once

load_dotenv_once()

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import typer
import yaml

from .ask_config import SKILLS_DIR, default_config, load_config, run_config_doctor, write_default_config

app = typer.Typer(help="/ask config - initialize and validate release configuration")


@app.command("doctor")
def doctor(
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
    profile: str = typer.Option("release", "--profile", help="Readiness profile: smoke, core-live, or release"),
    path: str | None = typer.Option(None, "--path", help="Config path, defaults to ASK_CONFIG or ask.config.yml"),
) -> None:
    result = run_config_doctor(path, profile=profile)
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"/ask config doctor: {result['status']}")
        print(f"profile: {result['profile']}")
        print(f"config: {result['config_path']}")
        for check in result["checks"]:
            mark = "ok" if check["ok"] else check["severity"]
            print(f"  {mark:7} {check['name']}: {check['detail']}")
        if result.get("needs_attention"):
            print(f"needs_attention: {result['needs_attention']['resume_hint']}")
    raise typer.Exit(0 if result["status"] == "pass" else 2)


@app.command("init")
def init(
    path: str | None = typer.Option(None, "--path", help="Config path, defaults to ASK_CONFIG or ask.config.yml"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing config"),
    defaults: bool = typer.Option(False, "--defaults", help="Write recommended defaults without launching /interview"),
    mode: str = typer.Option("auto", "--mode", help="/interview mode: auto, html, or tui"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    config = default_config()
    interview_result: dict[str, Any] | None = None
    if not defaults:
        interview_result = run_interview(config, mode=mode)
        apply_interview(config, interview_result)

    written = write_default_config(path, force=force)
    if config != default_config():
        written.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = {
        "schema": "ask.config_init.v1",
        "status": "written",
        "config_path": str(written),
        "used_interview": not defaults,
        "interview_completed": bool(interview_result and interview_result.get("completed")),
    }
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"wrote {written}")
        if not defaults:
            print("configuration was collected through /interview")



@app.command("setup")
def setup(
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Always launch /interview for high-level setup choices"),
    profile: str | None = typer.Option(None, "--profile", help="Setup profile: local-dev or shared-stack"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview setup decisions without writing config or starting services"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Accept inferred defaults without prompting"),
    start_missing: bool = typer.Option(False, "--start-missing", help="Explicitly consent to start missing services"),
    path: str | None = typer.Option(None, "--path", help="Config path, defaults to ASK_CONFIG or ask.config.yml"),
    mode: str = typer.Option("auto", "--mode", help="/interview mode: auto, html, or tui"),
) -> None:
    config, resolved, exists = load_config(path)
    inferred = infer_setup_answers(config, profile=profile, start_missing=start_missing)
    missing = required_setup_questions(inferred)
    used_interview = interactive or bool(missing and not yes)
    interview_result: dict[str, Any] | None = None
    if used_interview:
        interview_result = run_setup_interview(config, inferred, mode=mode)
        merge_setup_interview(inferred, interview_result)

    apply_setup_answers(config, inferred)
    would_start = bool(inferred.get("start_missing_services"))
    explicit_start_consent = bool(start_missing or (used_interview and would_start))
    actions = []
    if would_start and explicit_start_consent:
        actions.append("start_missing_services")
    if not dry_run:
        if exists:
            resolved.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        else:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = {
        "schema": "ask.setup.v1",
        "status": "dry-run" if dry_run else "configured",
        "config_path": str(resolved),
        "profile": inferred.get("deployment_profile"),
        "used_interview": used_interview,
        "start_missing_requested": bool(start_missing),
        "start_missing_services": would_start and explicit_start_consent,
        "explicit_start_consent": explicit_start_consent,
        "actions": actions,
        "dry_run": dry_run,
    }
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"/ask setup: {result['status']}")
        print(f"config: {resolved}")
        print(f"profile: {result['profile']}")
        print(f"used_interview: {used_interview}")
        if would_start:
            print("explicit consent recorded for starting missing services")
        else:
            print("will not start containers without --start-missing or interview consent")


def infer_setup_answers(config: dict[str, Any], *, profile: str | None, start_missing: bool) -> dict[str, Any]:
    deployment_profile = profile or config.get("setup", {}).get("deployment_profile") or config.get("profile")
    if deployment_profile in {"release", "core-live", "smoke"}:
        deployment_profile = "shared-stack" if deployment_profile == "release" else "local-dev"
    storage_root = os.environ.get("ASK_STORAGE_ROOT") or config.get("docker", {}).get("storage_root")
    isolation = os.environ.get("ASK_MEMORY_SCOPE_ISOLATION") or config.get("setup", {}).get("memory_scope_isolation")
    creds_available = os.environ.get("ASK_PROVIDER_CREDENTIALS")
    if not creds_available:
        if not config.get("release", {}).get("require_oauth_credentials", True):
            creds_available = "not-required"
        elif any(Path(str(item)).expanduser().exists() for item in config.get("release", {}).get("required_credentials", [])):
            creds_available = "available"
    return {
        "deployment_profile": deployment_profile,
        "start_missing_services": bool(start_missing),
        "storage_root": storage_root,
        "memory_scope_isolation": isolation,
        "provider_credentials": creds_available,
    }


def required_setup_questions(answers: dict[str, Any]) -> list[str]:
    required = []
    for key in ("deployment_profile", "storage_root", "memory_scope_isolation", "provider_credentials"):
        if answers.get(key) in (None, ""):
            required.append(key)
    return required


def run_setup_interview(config: dict[str, Any], answers: dict[str, Any], *, mode: str) -> dict[str, Any]:
    interview_run = SKILLS_DIR / "interview" / "run.sh"
    if not interview_run.exists():
        raise typer.BadParameter(f"/interview run.sh not found at {interview_run}")
    questions = {
        "title": "Ask Setup Wizard",
        "context": "Choose only high-level deployment options. Arango collections, Qdrant indexes, and embedding dimensions are bootstrapped idempotently.",
        "questions": [
            {
                "id": "deployment_profile",
                "header": "Deployment",
                "text": "How will /ask run?",
                "recommendation": answers.get("deployment_profile") or "local-dev",
                "options": [
                    {"label": "local-dev", "description": "Single developer machine with local service defaults."},
                    {"label": "shared-stack", "description": "Shared services or release-like team stack."},
                ],
            },
            {
                "id": "start_missing_services",
                "header": "Start Services",
                "text": "May setup start missing containers/services now?",
                "recommendation": "no",
                "options": [
                    {"label": "no", "description": "Safe default: do not start containers."},
                    {"label": "yes", "description": "Explicit consent to start missing services."},
                ],
            },
            {
                "id": "storage_root",
                "header": "Storage",
                "text": "Persistent volume root for service data?",
                "type": "text",
                "recommendation": str(answers.get("storage_root") or config["docker"]["storage_root"]),
            },
            {
                "id": "memory_scope_isolation",
                "header": "Memory Scope",
                "text": "How should memory scopes be isolated?",
                "recommendation": answers.get("memory_scope_isolation") or "per-project",
                "options": [
                    {"label": "per-project", "description": "Separate scopes per project/skill."},
                    {"label": "shared", "description": "Shared memory scope across users/projects."},
                ],
            },
            {
                "id": "provider_credentials",
                "header": "Provider Credentials",
                "text": "Are model provider credentials available on this machine?",
                "recommendation": answers.get("provider_credentials") or "available",
                "options": [
                    {"label": "available", "description": "Credentials are present or will be mounted."},
                    {"label": "missing", "description": "Credentials are not available yet."},
                    {"label": "not-required", "description": "This setup should not require provider credentials."},
                ],
            },
        ],
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(questions, handle, indent=2)
        questions_path = Path(handle.name)
    try:
        proc = subprocess.run(
            [str(interview_run), "--file", str(questions_path), "--mode", mode, "--json"],
            capture_output=True,
            text=True,
            timeout=900,
        )
    finally:
        questions_path.unlink(missing_ok=True)
    if proc.returncode != 0:
        typer.echo(f"/interview failed: {proc.stderr.strip() or proc.stdout.strip()}", err=True)
        raise typer.Exit(1)
    return json.loads(proc.stdout)


def merge_setup_interview(answers: dict[str, Any], result: dict[str, Any]) -> None:
    responses = result.get("responses") or {}

    def response_value(key: str) -> Any:
        response = responses.get(key) or {}
        return response.get("value")

    for key in ("deployment_profile", "storage_root", "memory_scope_isolation", "provider_credentials"):
        if response_value(key):
            answers[key] = response_value(key)
    if response_value("start_missing_services") in {"yes", True}:
        answers["start_missing_services"] = True
    elif response_value("start_missing_services") in {"no", False}:
        answers["start_missing_services"] = False


def apply_setup_answers(config: dict[str, Any], answers: dict[str, Any]) -> None:
    config.setdefault("setup", {})
    config["setup"]["deployment_profile"] = answers.get("deployment_profile") or "local-dev"
    config["setup"]["memory_scope_isolation"] = answers.get("memory_scope_isolation") or "per-project"
    config["setup"]["start_missing_services"] = bool(answers.get("start_missing_services"))
    if answers.get("storage_root"):
        config.setdefault("docker", {})["storage_root"] = str(answers["storage_root"])
    if answers.get("provider_credentials") == "not-required":
        config.setdefault("release", {})["require_oauth_credentials"] = False
    elif answers.get("provider_credentials") == "available":
        config.setdefault("release", {})["require_oauth_credentials"] = True

def run_interview(config: dict[str, Any], *, mode: str) -> dict[str, Any]:
    interview_run = SKILLS_DIR / "interview" / "run.sh"
    if not interview_run.exists():
        raise typer.BadParameter(f"/interview run.sh not found at {interview_run}")
    questions = {
        "title": "Ask Release Configuration",
        "context": "Collect /ask release-readiness configuration. CI uses config doctor and never prompts.",
        "questions": [
            {
                "id": "profile",
                "header": "Profile",
                "text": "Which readiness profile should this config target?",
                "recommendation": "release",
                "reason": "Release is the truth target; smaller profiles are diagnostics.",
                "options": [
                    {"label": "release", "description": "Full release readiness with no skipped required checks."},
                    {"label": "core-live", "description": "Interactive use paths only; release may remain unestablished."},
                    {"label": "smoke", "description": "Fast local sanity with expensive checks disabled."},
                ],
            },
            {
                "id": "credential_policy",
                "header": "Creds",
                "text": "Should Docker release checks require host-mounted OAuth/provider credentials?",
                "recommendation": "required",
                "reason": "Full release should fail closed when provider credentials are absent.",
                "options": [
                    {"label": "required", "description": "Missing credentials are release blockers."},
                    {"label": "warn", "description": "Missing credentials are warnings only."},
                ],
            },
            {
                "id": "scillm_repo",
                "header": "scillm",
                "text": "Where is the scillm repository for Docker compose builds?",
                "type": "text",
                "recommendation": str(config["docker"]["scillm_repo"]),
            },
            {
                "id": "memory_repo",
                "header": "Memory",
                "text": "Where is the memory repository for Docker compose builds?",
                "type": "text",
                "recommendation": str(config["docker"]["memory_repo"]),
            },
        ],
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(questions, handle, indent=2)
        questions_path = Path(handle.name)
    try:
        proc = subprocess.run(
            [str(interview_run), "--file", str(questions_path), "--mode", mode, "--json"],
            capture_output=True,
            text=True,
            timeout=900,
        )
    finally:
        questions_path.unlink(missing_ok=True)
    if proc.returncode != 0:
        typer.echo(f"/interview failed: {proc.stderr.strip() or proc.stdout.strip()}", err=True)
        raise typer.Exit(1)
    return json.loads(proc.stdout)


def apply_interview(config: dict[str, Any], result: dict[str, Any]) -> None:
    responses = result.get("responses") or {}

    def value(key: str) -> Any:
        response = responses.get(key) or {}
        return response.get("value")

    if value("profile"):
        config["profile"] = value("profile")
    if value("credential_policy") == "warn":
        config["release"]["require_oauth_credentials"] = False
    if value("scillm_repo"):
        config["docker"]["scillm_repo"] = value("scillm_repo")
    if value("memory_repo"):
        config["docker"]["memory_repo"] = value("memory_repo")


if __name__ == "__main__":
    app()
