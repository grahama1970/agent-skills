"""End-to-end containerized /hack session audit workflow."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import typer
from rich.console import Console

from hack.self_improve_loop import ARTIFACT_ROOT

console = Console()

DEFAULT_NUCLEI_VERSION = "3.4.10"


@dataclass(frozen=True)
class SessionPaths:
    """Artifact layout for one /hack session."""

    session_dir: Path
    scanner_dir: Path
    target_dir: Path
    repo_dir: Path
    reports_dir: Path
    logs_dir: Path
    templates_dir: Path


@dataclass(frozen=True)
class CommandResult:
    """Captured subprocess result persisted to logs."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class DockerToolPlan:
    """Plan-selected Docker toolchain for one /hack session."""

    base_image: str
    apt_packages: tuple[str, ...]
    pip_packages: tuple[str, ...]
    nuclei_version: str
    include_nuclei: bool
    semgrep_config: str
    nmap_scan_types: tuple[str, ...]


@dataclass(frozen=True)
class ProbeRunConfig:
    """Configuration for opt-in exploit proof probe orchestration."""

    enabled: bool
    code_runner_run: Path
    max_rounds: int


@dataclass(frozen=True)
class TargetLaunchPlan:
    """Resolved target runtime launch contract for one /hack session."""

    compose_path: Path
    target_url: str
    port: str
    source: str
    reason: str


def create_session_audit_command() -> Callable[..., None]:
    """Create the Typer command for complete containerized session audits."""

    def session_audit(
        repo_url: str = typer.Argument(..., help="Authorized target Git repository URL"),
        target_url: str = typer.Option(
            "http://127.0.0.1",
            help="URL to scan after launching the target Docker compose stack",
        ),
        compose_file: str = typer.Option(
            "docker-compose.without_llm.yml",
            help="Compose file inside the cloned target repository",
        ),
        port: str = typer.Option("80", help="Target TCP port list for nmap"),
        session_root: str = typer.Option(
            ARTIFACT_ROOT,
            help="Artifact root for /hack session-* directories",
        ),
        keep_running: bool = typer.Option(
            False,
            "--keep-running",
            help="Leave the target compose stack running after the audit",
        ),
        nuclei: bool = typer.Option(
            True,
            "--nuclei/--no-nuclei",
            help="Run Nuclei after nmap if templates can be updated",
        ),
        plan_file: str | None = typer.Option(
            None,
            "--plan-file",
            help="JSON file that determines scanner Docker contents and scan lanes",
        ),
        apt_package: list[str] | None = typer.Option(
            None,
            "--apt-package",
            help="Additional apt package to install in the generated scanner image",
        ),
        pip_package: list[str] | None = typer.Option(
            None,
            "--pip-package",
            help="Additional pip package to install in the generated scanner image",
        ),
        nuclei_version: str = typer.Option(
            DEFAULT_NUCLEI_VERSION,
            help="Pinned ProjectDiscovery Nuclei version for the generated scanner image",
        ),
        probe_exploits: bool = typer.Option(
            False,
            "--probe-exploits/--no-probe-exploits",
            help="Generate bounded proof probes with /code-runner and execute them through /hack Docker",
        ),
        code_runner_run: str = typer.Option(
            str(Path(__file__).resolve().parents[1] / "code-runner" / "run.sh"),
            help="Path to the /code-runner run.sh used only for bounded probe generation",
        ),
        probe_max_rounds: int = typer.Option(
            3,
            help="Maximum /code-runner rounds for each generated probe",
        ),
    ) -> None:
        """Clone, launch, scan, and report on an authorized target in containers."""

        report = run_session_audit(
            repo_url=repo_url,
            target_url=target_url,
            compose_file=compose_file,
            port=port,
            session_root=Path(session_root),
            keep_running=keep_running,
            run_nuclei=nuclei,
            plan_file=Path(plan_file) if plan_file else None,
            extra_apt_packages=tuple(apt_package or ()),
            extra_pip_packages=tuple(pip_package or ()),
            nuclei_version=nuclei_version,
            probe_config=ProbeRunConfig(
                enabled=probe_exploits,
                code_runner_run=Path(code_runner_run),
                max_rounds=probe_max_rounds,
            ),
        )
        console.print(f"[green]Report written:[/green] {report}")

    return session_audit


def run_session_audit(
    *,
    repo_url: str,
    target_url: str,
    compose_file: str,
    port: str,
    session_root: Path,
    keep_running: bool,
    run_nuclei: bool,
    plan_file: Path | None = None,
    extra_apt_packages: tuple[str, ...] = (),
    extra_pip_packages: tuple[str, ...] = (),
    nuclei_version: str = DEFAULT_NUCLEI_VERSION,
    probe_config: ProbeRunConfig | None = None,
) -> Path:
    """Run the complete /hack session workflow and return the report path."""

    if not shutil.which("docker"):
        raise RuntimeError("Docker is required for /hack session-audit")

    session_id = "session-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    session_id += "-" + safe_slug(repo_url)
    compose_project = safe_slug(session_id)
    paths = create_session_paths(session_root, session_id)
    docker_plan = load_docker_tool_plan(
        plan_file=plan_file,
        extra_apt_packages=extra_apt_packages,
        extra_pip_packages=extra_pip_packages,
        nuclei_version=nuclei_version,
        include_nuclei=run_nuclei,
    )
    materialize_scanner(paths, docker_plan)
    image = f"hack-session-scanner:{safe_slug(session_id).lower()}"

    console.print(f"[bold]Session:[/bold] {paths.session_dir}")
    build_result = run_logged(
        [
            "docker",
            "build",
            "-t",
            image,
            "-f",
            str(paths.scanner_dir / "Dockerfile"),
            str(paths.scanner_dir),
        ],
        paths.logs_dir / "scanner-build.log",
    )
    require_success(build_result, "scanner image build failed")

    clone_result = run_logged(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{paths.target_dir}:/target",
            "-w",
            "/target",
            image,
            "git",
            "clone",
            "--depth",
            "1",
            repo_url,
            "repo",
        ],
        paths.logs_dir / "clone.log",
    )
    require_success(clone_result, "target clone failed")

    metadata = collect_repo_metadata(paths, image, repo_url)
    semgrep_result = run_semgrep(paths, image)

    compose_up_result: CommandResult | None = None
    service_scan_result: CommandResult | None = None
    vuln_scan_result: CommandResult | None = None
    nuclei_result: CommandResult | None = None
    compose_down_result: CommandResult | None = None
    launch_plan = resolve_target_launch_plan(
        paths=paths,
        requested_compose_file=compose_file,
        requested_target_url=target_url,
        requested_port=port,
    )
    target_url = launch_plan.target_url
    port = launch_plan.port
    write_target_launch_plan(paths, launch_plan)
    target_compose_env = materialize_target_compose_env(
        paths=paths,
        launch_plan=launch_plan,
    )
    compose_path = launch_plan.compose_path
    probe_config = probe_config or ProbeRunConfig(
        enabled=False,
        code_runner_run=Path(__file__).resolve().parents[1] / "code-runner" / "run.sh",
        max_rounds=3,
    )

    try:
        if compose_path.exists():
            compose_up_result = run_logged(
                [
                    "docker",
                    "compose",
                    "-p",
                    compose_project,
                    "-f",
                    str(compose_path),
                    "up",
                    "-d",
                ],
                paths.logs_dir / "compose-up.log",
                env=target_compose_env,
            )
            if compose_up_result.returncode == 0:
                wait_for_http(target_url, paths.logs_dir / "target-smoke.log")
                if "service" in docker_plan.nmap_scan_types:
                    service_scan_result = run_nmap(paths, image, target_url, port, "service")
                if "vuln" in docker_plan.nmap_scan_types:
                    vuln_scan_result = run_nmap(paths, image, target_url, port, "vuln")
                if docker_plan.include_nuclei:
                    nuclei_result = run_nuclei_scan(paths, image, target_url)
                if probe_config.enabled:
                    run_exploit_probes(
                        paths=paths,
                        image=image,
                        target_url=target_url,
                        probe_config=probe_config,
                    )
        else:
            (paths.logs_dir / "compose-up.log").write_text(
                f"Compose file not found: {compose_path}\n"
            )
    finally:
        if compose_path.exists() and not keep_running:
            compose_down_result = run_logged(
                [
                    "docker",
                    "compose",
                    "-p",
                    compose_project,
                    "-f",
                    str(compose_path),
                    "down",
                ],
                paths.logs_dir / "compose-down.log",
                check=False,
                env=target_compose_env,
            )

    report = write_report(
        paths=paths,
        repo_url=repo_url,
        target_url=target_url,
        metadata=metadata,
        semgrep_result=semgrep_result,
        compose_up_result=compose_up_result,
        service_scan_result=service_scan_result,
        vuln_scan_result=vuln_scan_result,
        nuclei_result=nuclei_result,
        compose_down_result=compose_down_result,
        docker_plan=docker_plan,
    )
    write_memory_payload(paths, report)
    return report


def run_exploit_probes(
    *,
    paths: SessionPaths,
    image: str,
    target_url: str,
    probe_config: ProbeRunConfig,
) -> list[Path]:
    """Generate supported bounded probes with /code-runner and execute through Docker."""

    semgrep_findings = parse_semgrep_findings(paths.reports_dir / "semgrep.json")
    if not has_command_injection_candidate(semgrep_findings):
        (paths.logs_dir / "probe-skip.log").write_text(
            "No supported exploit probe candidates found.\n"
        )
        return []
    if not probe_config.code_runner_run.exists():
        raise RuntimeError(f"/code-runner run.sh not found: {probe_config.code_runner_run}")

    workspace = prepare_attack_workspace(paths, target_url)
    task_path = write_command_injection_probe_task(
        paths=paths,
        workspace=workspace,
        probe_config=probe_config,
    )
    code_runner_result = run_logged(
        [
            "bash",
            str(probe_config.code_runner_run),
            "run",
            str(task_path),
        ],
        paths.logs_dir / "code-runner-probe-command-injection.log",
        check=False,
    )
    if code_runner_result.returncode != 0:
        return []

    patch_path = paths.session_dir / "code-runner" / "probe-command-injection.patch"
    if patch_path.exists():
        run_logged(
            ["git", "apply", str(patch_path)],
            paths.logs_dir / "probe-command-injection-apply.log",
            check=False,
            cwd=workspace,
        )
    probe_path = workspace / "attacks" / "probe_command_injection.py"
    if not probe_path.exists():
        (paths.logs_dir / "probe-command-injection-missing.log").write_text(
            f"Probe file missing after /code-runner run: {probe_path}\n"
        )
        return []

    paths.session_dir.joinpath("attacks").mkdir(parents=True, exist_ok=True)
    proof_path = paths.session_dir / "attacks" / "proof.command-injection.json"
    result = run_probe_in_docker(
        paths=paths,
        image=image,
        target_url=target_url,
        proof_path=proof_path,
    )
    return [proof_path] if result.returncode == 0 and proof_path.exists() else []


def resolve_target_launch_plan(
    *,
    paths: SessionPaths,
    requested_compose_file: str,
    requested_target_url: str,
    requested_port: str,
) -> TargetLaunchPlan:
    """Resolve or synthesize a target launch plan before DAST/probe stages."""

    requested_compose_path = paths.repo_dir / requested_compose_file
    if requested_compose_path.exists():
        inferred_port = infer_compose_port(requested_compose_path, fallback=requested_port)
        return TargetLaunchPlan(
            compose_path=requested_compose_path,
            target_url=normalize_target_url_for_port(requested_target_url, inferred_port),
            port=inferred_port,
            source="requested-compose",
            reason=f"requested compose file exists: {requested_compose_file}",
        )

    discovered_compose = discover_compose_file(paths.repo_dir)
    if discovered_compose is not None:
        inferred_port = infer_compose_port(discovered_compose, fallback=requested_port)
        return TargetLaunchPlan(
            compose_path=discovered_compose,
            target_url=normalize_target_url_for_port(requested_target_url, inferred_port),
            port=inferred_port,
            source="discovered-compose",
            reason=f"discovered compose file: {discovered_compose.relative_to(paths.repo_dir)}",
        )

    dockerfile = paths.repo_dir / "Dockerfile"
    if dockerfile.exists():
        inferred_port = infer_target_port(paths.repo_dir, fallback=requested_port)
        target_url = normalize_target_url_for_port(requested_target_url, inferred_port)
        compose_path = materialize_dockerfile_target_compose(
            paths=paths,
            target_port=inferred_port,
        )
        return TargetLaunchPlan(
            compose_path=compose_path,
            target_url=target_url,
            port=inferred_port,
            source="generated-dockerfile-compose",
            reason="requested compose file missing; generated host-network compose from root Dockerfile",
        )

    return TargetLaunchPlan(
        compose_path=requested_compose_path,
        target_url=requested_target_url,
        port=requested_port,
        source="missing",
        reason="no requested compose file, discovered compose file, or root Dockerfile found",
    )


def discover_compose_file(repo_dir: Path) -> Path | None:
    """Return the first likely compose file in a deterministic preference order."""

    names = (
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    )
    for name in names:
        candidate = repo_dir / name
        if candidate.exists():
            return candidate
    ignored_dirs = {
        ".git",
        "node_modules",
        "dist",
        "build",
        "target",
        ".artifacts",
        ".next",
        "coverage",
    }
    checked = 0
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = sorted(directory for directory in dirs if directory not in ignored_dirs)
        for filename in sorted(files):
            checked += 1
            if filename in names:
                return Path(root) / filename
            if checked >= 5000:
                return None
    return None


def infer_target_port(repo_dir: Path, *, fallback: str) -> str:
    """Infer the target HTTP port from Dockerfile and common project metadata."""

    candidates: list[str] = []
    for relative in ("Dockerfile", "README.md", ".env.example"):
        path = repo_dir / relative
        if path.exists():
            text = path.read_text(errors="replace")
            candidates.extend(re.findall(r"\b(18[0-9]{3}|[1-9][0-9]{3,4})\b", text))
    package_json = repo_dir / "package.json"
    if package_json.exists():
        try:
            data = json.loads(package_json.read_text(errors="replace"))
        except json.JSONDecodeError:
            data = {}
        candidates.extend(re.findall(r"\b(18[0-9]{3}|[1-9][0-9]{3,4})\b", json.dumps(data)))
    if "18789" in candidates:
        return "18789"
    for candidate in candidates:
        if candidate not in {"30000", "50000"}:
            return candidate
    return fallback


def infer_compose_port(compose_path: Path, *, fallback: str) -> str:
    """Infer the host HTTP port from a Docker compose file."""

    text = compose_path.read_text(errors="replace")
    if fallback != "80" and re.fullmatch(r"[1-9][0-9]{1,4}", fallback):
        return fallback
    host_port_matches = re.findall(r'["\']?\$?\{?[A-Z0-9_:-]*?([1-9][0-9]{1,4})\}?:(18[0-9]{3}|[1-9][0-9]{3,4})["\']?', text)
    for host_port, container_port in host_port_matches:
        if container_port == "18789" or host_port == "18789":
            return "18789"
    for host_port, _container_port in host_port_matches:
        if host_port not in {"80", "443"}:
            return host_port
    if "18789" in text:
        return "18789"
    return fallback


def normalize_target_url_for_port(target_url: str, port: str) -> str:
    """Add an inferred port to a URL when the caller supplied only a host."""

    parsed = urlparse(target_url)
    if parsed.scheme and parsed.hostname and parsed.port is None:
        default_port = "443" if parsed.scheme == "https" else "80"
        if port != default_port:
            return f"{parsed.scheme}://{parsed.hostname}:{port}"
    return target_url


def materialize_dockerfile_target_compose(
    *,
    paths: SessionPaths,
    target_port: str,
) -> Path:
    """Write a host-network compose file for repos that ship a root Dockerfile."""

    launch_dir = paths.session_dir / "target-launch"
    launch_dir.mkdir(parents=True, exist_ok=True)
    compose_path = launch_dir / "docker-compose.generated.yml"
    compose_path.write_text(
        f"""services:
  target:
    build:
      context: {paths.repo_dir}
      dockerfile: Dockerfile
    network_mode: host
    environment:
      OPENCLAW_GATEWAY_PORT: "{target_port}"
      OPENCLAW_GATEWAY_HOST: "127.0.0.1"
      OPENCLAW_HACK_HARDENING_VALIDATION: "1"
    volumes:
      - {paths.session_dir / "target-state"}:/home/node/.openclaw:rw
"""
    )
    return compose_path


def write_target_launch_plan(paths: SessionPaths, launch_plan: TargetLaunchPlan) -> None:
    """Persist the resolved target launch plan for reports and plan revision."""

    payload = {
        "compose_path": str(launch_plan.compose_path),
        "target_url": launch_plan.target_url,
        "port": launch_plan.port,
        "source": launch_plan.source,
        "reason": launch_plan.reason,
    }
    (paths.reports_dir / "target-launch-plan.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )


def materialize_target_compose_env(
    *,
    paths: SessionPaths,
    launch_plan: TargetLaunchPlan,
) -> dict[str, str]:
    """Create a sanitized compose environment with per-session target state."""

    target_state = paths.session_dir / "target-state"
    home_dir = target_state / "home"
    config_dir = target_state / "config"
    workspace_dir = target_state / "workspace"
    for directory in (home_dir, config_dir, workspace_dir):
        directory.mkdir(parents=True, exist_ok=True)
    seed_openclaw_hardening_config(config_dir, workspace_dir, gateway_port=launch_plan.port)

    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"VIRTUAL_ENV", "HOME"}
    }
    env.update(
        {
            "HOME": str(home_dir),
            "OPENCLAW_CONFIG_DIR": str(config_dir),
            "OPENCLAW_WORKSPACE_DIR": str(workspace_dir),
            "OPENCLAW_GATEWAY_PORT": launch_plan.port,
            "OPENCLAW_BRIDGE_PORT": str(int(launch_plan.port) + 1) if launch_plan.port.isdigit() else "18790",
            "OPENCLAW_GATEWAY_HOST": "127.0.0.1",
            "OPENCLAW_GATEWAY_BIND": "lan",
            "OPENCLAW_HACK_HARDENING_VALIDATION": "1",
        }
    )
    write_target_compose_env_report(paths, env)
    return env


def write_target_compose_env_report(paths: SessionPaths, env: dict[str, str]) -> None:
    """Persist non-secret target compose environment details for auditability."""

    tracked_keys = (
        "HOME",
        "OPENCLAW_CONFIG_DIR",
        "OPENCLAW_WORKSPACE_DIR",
        "OPENCLAW_GATEWAY_PORT",
        "OPENCLAW_BRIDGE_PORT",
        "OPENCLAW_GATEWAY_HOST",
        "OPENCLAW_GATEWAY_BIND",
        "OPENCLAW_HACK_HARDENING_VALIDATION",
    )
    payload = {
        "purpose": "per-session target compose isolation",
        "environment": {key: env[key] for key in tracked_keys if key in env},
    }
    (paths.reports_dir / "target-compose-env.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )


def seed_openclaw_hardening_config(config_dir: Path, workspace_dir: Path, *, gateway_port: str = "18789") -> None:
    """Seed minimal OpenClaw local config so Docker hardening sessions can boot."""

    config_path = config_dir / "openclaw.json"
    if config_path.exists():
        return
    payload = {
        "gateway": {
            "mode": "local",
            "port": int(gateway_port) if gateway_port.isdigit() else 18789,
        },
        "agents": {
            "defaults": {
                "workspace": str(workspace_dir),
            },
        },
    }
    config_path.write_text(json.dumps(payload, indent=2) + "\n")


def has_command_injection_candidate(findings: list[dict[str, str]]) -> bool:
    """Return whether Semgrep found a supported command-injection candidate."""

    return any("runtime-exec" in finding.get("check_id", "") for finding in findings)


def prepare_attack_workspace(paths: SessionPaths, target_url: str) -> Path:
    """Create a disposable git workspace where /code-runner can author probes."""

    workspace = paths.session_dir / "attack-workspace"
    attacks_dir = workspace / "attacks"
    attacks_dir.mkdir(parents=True, exist_ok=True)
    context = build_command_injection_probe_context(paths, target_url)
    workspace.joinpath("README.md").write_text(
        "# /hack attack workspace\n\nDisposable workspace for bounded proof probes.\n"
    )
    workspace.joinpath("CONTEXT.md").write_text(context)
    if not (workspace / ".git").exists():
        run_logged(["git", "init", "-q"], paths.logs_dir / "attack-workspace-git-init.log", cwd=workspace)
        run_logged(
            [
                "git",
                "-c",
                "user.email=hack@example.invalid",
                "-c",
                "user.name=hack",
                "add",
                "README.md",
                "CONTEXT.md",
            ],
            paths.logs_dir / "attack-workspace-git-add.log",
            cwd=workspace,
        )
        run_logged(
            [
                "git",
                "-c",
                "user.email=hack@example.invalid",
                "-c",
                "user.name=hack",
                "commit",
                "-q",
                "-m",
                "init attack workspace",
            ],
            paths.logs_dir / "attack-workspace-git-commit.log",
            cwd=workspace,
        )
    return workspace


def build_command_injection_probe_context(paths: SessionPaths, target_url: str) -> str:
    """Return sanitized probe-generation context for the supported command-injection lane."""

    return "\n".join(
        [
            "# Authorized Probe Context",
            "",
            "This workspace is for a bounded local proof probe against an authorized target launched by `/hack`.",
            "",
            f"- Target URL: `{target_url}`",
            "- Candidate class: command injection",
            "- Source evidence: Semgrep found Java command-execution sinks in the cloned target.",
            "- Route family to test for SasanLabs VulnerableApp: `/VulnerableApp/CommandInjection/LEVEL_{level}`",
            "- Query parameter: `ipaddress`",
            "",
            "Probe contract:",
            "",
            "- Write exactly one Python file at `attacks/probe_command_injection.py`.",
            "- Use only the Python standard library.",
            "- Accept `--target-url` and `--proof-path`.",
            "- Restrict execution to loopback/local target URLs.",
            "- Try a small deterministic set of non-destructive identity/read-only checks.",
            "- Do not open shells, create persistence, write to the target, or write outside `--proof-path`.",
            "- Exit `0` only when deterministic reflected command-output proof is found.",
            "- On success, write compact JSON proof to `--proof-path` with `status`, `indicator`, `url`, and `evidence_excerpt`.",
            f"- Source repo artifact: `{paths.repo_dir}`",
            "",
        ]
    )


def write_command_injection_probe_task(
    *,
    paths: SessionPaths,
    workspace: Path,
    probe_config: ProbeRunConfig,
) -> Path:
    """Write a /code-runner task spec for bounded command-injection probe generation."""

    output_dir = paths.session_dir / "code-runner"
    output_dir.mkdir(parents=True, exist_ok=True)
    task_path = output_dir / "probe-command-injection.task.json"
    task = {
        "task_id": "probe-command-injection",
        "title": "Generate bounded command-injection proof probe",
        "prompt": (
            "Implement attacks/probe_command_injection.py using CONTEXT.md. "
            "Keep it bounded, local-only, non-destructive, standard-library-only, "
            "and make it exit 0 only when reflected command-output proof is found."
        ),
        "backend": "codex",
        "cwd": str(workspace),
        "output_dir": str(output_dir),
        "allowlist": ["attacks/probe_command_injection.py"],
        "read_context": ["CONTEXT.md"],
        "definition_of_done": {
            "command": (
                "python3 -m py_compile attacks/probe_command_injection.py "
                "&& python3 attacks/probe_command_injection.py --help"
            ),
            "assertion": "target-url",
        },
        "dirty_worktree_policy": "isolated_worktree",
        "max_rounds": probe_config.max_rounds,
        "apply_to_source": False,
    }
    task_path.write_text(json.dumps(task, indent=2) + "\n")
    return task_path


def run_probe_in_docker(
    *,
    paths: SessionPaths,
    image: str,
    target_url: str,
    proof_path: Path,
) -> CommandResult:
    """Execute the generated probe through the scanner Docker image."""

    command = [
        "docker",
        "run",
        "--rm",
        "--network=host",
        "-v",
        f"{paths.session_dir / 'attack-workspace' / 'attacks'}:/attacks:ro",
        "-v",
        f"{proof_path.parent}:/proof:rw",
        image,
        "python",
        "/attacks/probe_command_injection.py",
        "--target-url",
        target_url,
        "--proof-path",
        f"/proof/{proof_path.name}",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    (paths.logs_dir / "probe-command-injection.stdout.log").write_text(result.stdout)
    (paths.logs_dir / "probe-command-injection.stderr.log").write_text(result.stderr)
    (paths.logs_dir / "probe-command-injection.exit-code").write_text(
        f"{result.returncode}\n"
    )
    return CommandResult(
        command=tuple(command),
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def safe_slug(value: str) -> str:
    """Return a conservative Docker/session-safe slug."""

    parsed = urlparse(value)
    source = parsed.path or parsed.netloc or value
    source = source.removesuffix(".git").strip("/") or "target"
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", source).strip("-._").lower()
    return slug or "target"


def create_session_paths(session_root: Path, session_id: str) -> SessionPaths:
    """Create the session artifact directory layout."""

    session_dir = session_root / session_id
    paths = SessionPaths(
        session_dir=session_dir,
        scanner_dir=session_dir / "scanner",
        target_dir=session_dir / "target",
        repo_dir=session_dir / "target" / "repo",
        reports_dir=session_dir / "reports",
        logs_dir=session_dir / "logs",
        templates_dir=session_dir / "nuclei-templates",
    )
    for directory in (
        paths.scanner_dir,
        paths.target_dir,
        paths.reports_dir,
        paths.logs_dir,
        paths.templates_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return paths


def load_docker_tool_plan(
    *,
    plan_file: Path | None,
    extra_apt_packages: tuple[str, ...],
    extra_pip_packages: tuple[str, ...],
    nuclei_version: str,
    include_nuclei: bool,
) -> DockerToolPlan:
    """Load and merge the plan that determines scanner Docker contents."""

    plan = default_docker_tool_plan(
        nuclei_version=nuclei_version,
        include_nuclei=include_nuclei,
    )
    if plan_file is not None:
        raw = json.loads(plan_file.read_text())
        plan = DockerToolPlan(
            base_image=str(raw.get("base_image", plan.base_image)),
            apt_packages=merge_packages(
                plan.apt_packages,
                tuple_of_strings(raw.get("apt_packages", ())),
            ),
            pip_packages=merge_packages(
                plan.pip_packages,
                tuple_of_strings(raw.get("pip_packages", ())),
            ),
            nuclei_version=str(raw.get("nuclei_version", plan.nuclei_version)),
            include_nuclei=bool(raw.get("include_nuclei", plan.include_nuclei)),
            semgrep_config=str(raw.get("semgrep_config", plan.semgrep_config)),
            nmap_scan_types=tuple_of_strings(
                raw.get("nmap_scan_types", plan.nmap_scan_types)
            ),
        )
    return DockerToolPlan(
        base_image=plan.base_image,
        apt_packages=merge_packages(plan.apt_packages, extra_apt_packages),
        pip_packages=merge_packages(plan.pip_packages, extra_pip_packages),
        nuclei_version=plan.nuclei_version,
        include_nuclei=plan.include_nuclei,
        semgrep_config=plan.semgrep_config,
        nmap_scan_types=plan.nmap_scan_types,
    )


def default_docker_tool_plan(
    *, nuclei_version: str, include_nuclei: bool
) -> DockerToolPlan:
    """Return the default plan-selected scanner toolchain."""

    return DockerToolPlan(
        base_image="python:3.11-slim",
        apt_packages=(
            "ca-certificates",
            "curl",
            "git",
            "iputils-ping",
            "nmap",
            "unzip",
            "wget",
        ),
        pip_packages=(
            "bandit==1.9.4",
            "pip-audit==2.9.0",
            "requests==2.32.5",
            "rich==14.2.0",
            "safety==3.7.0",
            "semgrep==1.161.0",
            "typer==0.20.0",
        ),
        nuclei_version=nuclei_version,
        include_nuclei=include_nuclei,
        semgrep_config="/opt/hack-rules/offline-security.yml",
        nmap_scan_types=("service", "vuln"),
    )


def merge_packages(first: tuple[str, ...], second: tuple[str, ...]) -> tuple[str, ...]:
    """Merge package tuples while preserving order."""

    packages: list[str] = []
    for package in first + second:
        value = package.strip()
        if value and value not in packages:
            packages.append(value)
    return tuple(packages)


def tuple_of_strings(value: object) -> tuple[str, ...]:
    """Coerce JSON list-ish values to a tuple of strings."""

    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return ()


def materialize_scanner(paths: SessionPaths, docker_plan: DockerToolPlan) -> None:
    """Write the per-session scanner Dockerfile, compose file, and offline rules."""

    paths.scanner_dir.joinpath("Dockerfile").write_text(
        build_session_dockerfile(docker_plan)
    )
    paths.scanner_dir.joinpath("docker-compose.yml").write_text(
        build_session_compose(paths.session_dir)
    )
    paths.scanner_dir.joinpath("plan.json").write_text(
        json.dumps(
            {
                "base_image": docker_plan.base_image,
                "apt_packages": list(docker_plan.apt_packages),
                "pip_packages": list(docker_plan.pip_packages),
                "nuclei_version": docker_plan.nuclei_version,
                "include_nuclei": docker_plan.include_nuclei,
                "semgrep_config": docker_plan.semgrep_config,
                "nmap_scan_types": list(docker_plan.nmap_scan_types),
            },
            indent=2,
        )
    )
    source_rules = Path(__file__).resolve().parent / "docker" / "offline-security.yml"
    paths.scanner_dir.joinpath("offline-security.yml").write_text(
        source_rules.read_text()
    )


def build_session_dockerfile(docker_plan: DockerToolPlan) -> str:
    """Return the generated scanner Dockerfile content."""

    apt_packages = " \\\n+    ".replace("+", "").join(docker_plan.apt_packages)
    pip_packages = " \\\n+    ".replace("+", "").join(docker_plan.pip_packages)
    nuclei_block = ""
    if docker_plan.include_nuclei:
        nuclei_block = f"""
RUN set -eux; \\
    wget -O /tmp/nuclei.zip "https://github.com/projectdiscovery/nuclei/releases/download/v${{NUCLEI_VERSION}}/nuclei_${{NUCLEI_VERSION}}_linux_amd64.zip"; \\
    unzip -p /tmp/nuclei.zip nuclei > /usr/local/bin/nuclei; \\
    chmod +x /usr/local/bin/nuclei; \\
    rm -f /tmp/nuclei.zip; \\
    nuclei -version
"""

    return f"""FROM {docker_plan.base_image}

LABEL org.agent-skills.skill="hack"
LABEL org.agent-skills.session-scanner="true"
LABEL org.agent-skills.plan-driven-docker="true"

ARG NUCLEI_VERSION={docker_plan.nuclei_version}

RUN apt-get update && apt-get install -y --no-install-recommends \\
    {apt_packages} \\
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \\
    {pip_packages}
{nuclei_block}

COPY offline-security.yml /opt/hack-rules/offline-security.yml
COPY plan.json /opt/hack-plan/plan.json

WORKDIR /workspace
CMD ["bash", "-lc", "cat /opt/hack-plan/plan.json && semgrep --version && nmap --version"]
"""


def build_session_compose(session_dir: Path) -> str:
    """Return a per-session compose manifest for the scanner container."""

    return f"""services:
  scanner:
    build:
      context: {session_dir / "scanner"}
      dockerfile: Dockerfile
    image: hack-session-scanner
    network_mode: host
    volumes:
      - {session_dir / "target"}:/target:rw
      - {session_dir / "reports"}:/reports:rw
      - {session_dir / "logs"}:/logs:rw
      - {session_dir / "nuclei-templates"}:/root/nuclei-templates:rw
"""


def collect_repo_metadata(
    paths: SessionPaths, image: str, fallback_url: str
) -> dict[str, str]:
    """Collect target repository metadata inside the scanner container."""

    head = run_logged(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{paths.repo_dir}:/repo:ro",
            "-w",
            "/repo",
            image,
            "git",
            "rev-parse",
            "HEAD",
        ],
        paths.logs_dir / "target-head.log",
    )
    origin = run_logged(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{paths.repo_dir}:/repo:ro",
            "-w",
            "/repo",
            image,
            "git",
            "remote",
            "get-url",
            "origin",
        ],
        paths.logs_dir / "target-origin.log",
    )
    return {
        "head": head.stdout.strip() or "unknown",
        "origin": origin.stdout.strip() or fallback_url,
    }


def run_semgrep(paths: SessionPaths, image: str) -> CommandResult:
    """Run offline Semgrep rules in the generated scanner container."""

    return run_logged(
        [
            "docker",
            "run",
            "--rm",
            "--network=none",
            "-v",
            f"{paths.repo_dir}:/scan:ro",
            "-v",
            f"{paths.reports_dir}:/reports:rw",
            image,
            "semgrep",
            "scan",
            "--config",
            "/opt/hack-rules/offline-security.yml",
            "--json",
            "--output",
            "/reports/semgrep.json",
            "/scan",
        ],
        paths.logs_dir / "semgrep.log",
        check=False,
    )


def run_nmap(
    paths: SessionPaths, image: str, target_url: str, port: str, scan_type: str
) -> CommandResult:
    """Run nmap service or vulnerability scan from the scanner container."""

    host = urlparse(target_url).hostname or target_url
    if scan_type == "vuln":
        command = [
            "nmap",
            "-sV",
            "--script",
            "vuln",
            "-p",
            port,
            "-oX",
            "/reports/nmap-vuln.xml",
            host,
        ]
        log_name = "nmap-vuln.log"
    else:
        command = [
            "nmap",
            "-sV",
            "-sC",
            "-p",
            port,
            "-oX",
            "/reports/nmap-service.xml",
            host,
        ]
        log_name = "nmap-service.log"
    return run_logged(
        [
            "docker",
            "run",
            "--rm",
            "--network=host",
            "-v",
            f"{paths.reports_dir}:/reports:rw",
            image,
            *command,
        ],
        paths.logs_dir / log_name,
        check=False,
    )


def run_nuclei_scan(paths: SessionPaths, image: str, target_url: str) -> CommandResult:
    """Run Nuclei with per-session templates from the generated scanner image."""

    script = (
        "nuclei -update-templates -silent || true; "
        "nuclei -u \"$TARGET_URL\" -jsonl -silent "
        "-severity low,medium,high,critical -o /reports/nuclei.jsonl"
    )
    return run_logged(
        [
            "docker",
            "run",
            "--rm",
            "--network=host",
            "-e",
            f"TARGET_URL={target_url}",
            "-v",
            f"{paths.reports_dir}:/reports:rw",
            "-v",
            f"{paths.templates_dir}:/root/nuclei-templates:rw",
            image,
            "bash",
            "-lc",
            script,
        ],
        paths.logs_dir / "nuclei.log",
        check=False,
    )


def wait_for_http(target_url: str, log_path: Path, attempts: int = 20) -> None:
    """Poll the target URL from a curl container before DAST scans."""

    lines: list[str] = []
    for attempt in range(1, attempts + 1):
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network=host",
                "curlimages/curl:latest",
                "-sS",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                target_url,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        code = result.stdout.strip()
        lines.append(f"attempt={attempt} code={code} stderr={result.stderr.strip()}")
        if code in {"200", "301", "302", "401", "403"}:
            log_path.write_text("\n".join(lines) + "\n")
            return
        time.sleep(3)
    log_path.write_text("\n".join(lines) + "\n")


def run_logged(
    command: list[str],
    log_path: Path,
    *,
    check: bool = True,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Run a command, write stdout/stderr to a log, and optionally fail."""

    command_env = env or {
        key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"
    }
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=command_env,
        cwd=str(cwd) if cwd is not None else None,
        check=False,
    )
    log_path.write_text(
        "$ " + " ".join(command) + "\n\n"
        + "## stdout\n"
        + result.stdout
        + "\n## stderr\n"
        + result.stderr
        + f"\n## exit_code\n{result.returncode}\n"
    )
    command_result = CommandResult(
        command=tuple(command),
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
    if check:
        require_success(command_result, f"command failed: {' '.join(command)}")
    return command_result


def require_success(result: CommandResult, message: str) -> None:
    """Raise RuntimeError if a command failed."""

    if result.returncode != 0:
        raise RuntimeError(f"{message}; see command log")


def write_report(
    *,
    paths: SessionPaths,
    repo_url: str,
    target_url: str,
    metadata: dict[str, str],
    semgrep_result: CommandResult,
    compose_up_result: CommandResult | None,
    service_scan_result: CommandResult | None,
    vuln_scan_result: CommandResult | None,
    nuclei_result: CommandResult | None,
    compose_down_result: CommandResult | None,
    docker_plan: DockerToolPlan,
) -> Path:
    """Write a Markdown report from session artifacts."""

    semgrep_findings = parse_semgrep_findings(paths.reports_dir / "semgrep.json")
    nmap_summary = parse_nmap_text(vuln_scan_result.stdout if vuln_scan_result else "")
    nuclei_count = count_jsonl(paths.reports_dir / "nuclei.jsonl")
    exploit_status = summarize_exploit_status(paths)
    code_runner_runs = summarize_code_runner_runs(paths)
    probe_execution = summarize_probe_execution(paths)
    proof_summary = summarize_proof_artifact(paths)
    target_launch = summarize_target_launch_plan(paths)
    agent_outcome = (
        "bounded exploit probe produced deterministic proof."
        if exploit_status["proven"]
        else "scanner evidence found candidate vulnerabilities; no exploit proof was produced in this run."
    )
    next_step = (
        "preserve proof artifacts, prioritize remediation of the command-execution path, then rerun the same probe to verify the fix."
        if exploit_status["proven"]
        else "generate and run a bounded local proof probe for the command-execution candidate, or explicitly mark exploit probing out of scope."
    )
    report_classification = (
        "successful exploitation proof report"
        if exploit_status["proven"]
        else "vulnerability assessment report"
    )
    plan_revision = (
        "remediation and fix-verification"
        if exploit_status["proven"]
        else "exploit validation"
    )
    critical_findings = summarize_critical_findings(
        semgrep_findings=semgrep_findings,
        nmap_summary=nmap_summary,
        nuclei_count=nuclei_count,
    )
    report = paths.reports_dir / "HACK_REPORT.md"
    lines = [
        "# /hack Exploit Proof Report",
        "",
        "## Answer",
        f"- Was an exploit proven? `{str(exploit_status['proven']).lower()}`",
        f"- Proven exploit found: `{str(exploit_status['proven']).lower()}`",
        f"- Exploit proof status: `{exploit_status['status']}`",
        "- Did `$code-runner` run the exploit? `false` — it generated and verified bounded probe code only.",
        f"- Did `$hack` run the exploit in Docker? `{str(probe_execution['executed']).lower()}`",
        f"- What did the exploit find? {proof_summary['finding']}",
        f"- What should happen next? {next_step}",
        "",
        "## Project-Agent Summary",
        f"- Outcome: {agent_outcome}",
        f"- Interpretation: {report_classification}.",
        f"- Plan implication: next plan should focus on {plan_revision}.",
        f"- Primary vulnerability: {critical_findings[0] if critical_findings else 'none parsed'}",
        f"- Proof artifact: `{exploit_status['artifact']}`",
        f"- Proof indicator: `{proof_summary['indicator']}`",
        f"- Proof evidence summary: {proof_summary['evidence_summary']}",
        "",
        "## What Code-Runner Did",
    ]
    if code_runner_runs:
        for run in code_runner_runs:
            lines.extend(
                [
                    f"- Task: `{run['task_id']}`",
                    f"  - Purpose: {run['title']}",
                    f"  - Backend: `{run['backend']}`",
                    f"  - Result: `{run['status']}`",
                    f"  - DoD passed: `{str(run['dod_passed']).lower()}`",
                    f"  - Rounds: `{run['rounds']}`",
                    f"  - Score: `{run['best_score']}`",
                    f"  - Patch: `{run['patch']}`",
                    f"  - Review: `{run['hunk']}`",
                ]
            )
    else:
        lines.append("- No `/code-runner` probe-generation result artifacts found.")
    lines.extend(
        [
            "",
            "## What Hack Executed",
            "- Executor: `$hack`, not `$code-runner`.",
            "- Boundary: generated scanner Docker image with host networking to the authorized local target.",
            f"- Probe executed: `{str(probe_execution['executed']).lower()}`",
            f"- Exit code: `{probe_execution['exit_code']}`",
            f"- Result: {probe_execution['result']}",
            f"- Proof target: {proof_summary['target_summary']}",
            f"- Proof artifact: `{probe_execution['proof_artifact']}`",
            f"- Stderr log: `{probe_execution['stderr_log']}`",
            "",
            "## Exploit Finding",
            f"- Status: `{exploit_status['status']}`",
            f"- Finding: {proof_summary['finding']}",
            f"- Evidence summary: {proof_summary['evidence_summary']}",
            f"- Reason: {exploit_status['reason']}",
            "",
            "## Decision",
            f"- Treat this as a {report_classification}.",
            "- Scanner findings are leads until a bounded probe executes against the local authorized target and records deterministic proof.",
            f"- The current session supports a next plan revision focused on {plan_revision}.",
            "",
            "## Scope",
            f"- Target repository: `{metadata.get('origin') or repo_url}`",
            f"- Target commit: `{metadata.get('head', 'unknown')}`",
            f"- Target URL: `{target_url}`",
            f"- Target launch source: `{target_launch['source']}`",
            f"- Target launch reason: {target_launch['reason']}",
            f"- Session directory: `{paths.session_dir}`",
            "- Safety boundary: scanner image, target clone, target runtime, SAST, and DAST all run through Docker.",
            "",
            "## Generated Docker",
            f"- Scanner Dockerfile: `{paths.scanner_dir / 'Dockerfile'}`",
            f"- Scanner compose: `{paths.scanner_dir / 'docker-compose.yml'}`",
            f"- Scanner plan: `{paths.scanner_dir / 'plan.json'}`",
            f"- Base image: `{docker_plan.base_image}`",
            f"- Apt packages: `{', '.join(docker_plan.apt_packages)}`",
            f"- Pip packages: `{', '.join(docker_plan.pip_packages)}`",
            f"- Nuclei enabled: `{docker_plan.include_nuclei}`.",
            "",
            "## Findings Summary",
        ]
    )
    if critical_findings:
        lines.extend(f"- {finding}" for finding in critical_findings)
    else:
        lines.append("- No candidate vulnerabilities were parsed from scanner outputs.")
    lines.extend(
        [
            "",
            "## Evidence Details",
        "",
        "### Semgrep Offline SAST",
        ]
    )
    if semgrep_findings:
        for finding in semgrep_findings:
            lines.append(
                f"- `{finding.get('check_id', 'unknown')}` "
                f"({finding.get('severity', 'unknown')}) in `{finding.get('path', 'unknown')}`"
            )
            if finding.get("line"):
                lines.append(f"  - line {finding['line']}: {finding.get('message', '')}")
    else:
        lines.append(f"- No parsed Semgrep findings. Exit code: `{semgrep_result.returncode}`.")
    lines.extend(["", "### Nmap DAST"])
    lines.extend(nmap_summary or ["- No Nmap vulnerability summary parsed."])
    lines.extend(["", "### Nuclei"])
    if nuclei_result is None:
        lines.append("- Nuclei was disabled or skipped.")
    else:
        lines.append(f"- Nuclei exit code: `{nuclei_result.returncode}`.")
        lines.append(f"- JSONL findings parsed: `{nuclei_count}`.")
    lines.extend(
        [
            "",
            "## Runtime Status",
            f"- Compose up exit code: `{compose_up_result.returncode if compose_up_result else 'not-run'}`",
            f"- Service scan exit code: `{service_scan_result.returncode if service_scan_result else 'not-run'}`",
            f"- Vuln scan exit code: `{vuln_scan_result.returncode if vuln_scan_result else 'not-run'}`",
            f"- Compose down exit code: `{compose_down_result.returncode if compose_down_result else 'not-run'}`",
            "",
            "## Artifacts",
        ]
    )
    artifact_paths = (
        sorted(paths.logs_dir.glob("*"))
        + sorted(paths.reports_dir.glob("*"))
        + sorted((paths.session_dir / "attacks").glob("**/*"))
        + sorted((paths.session_dir / "code-runner").glob("*"))
    )
    for artifact in artifact_paths:
        if artifact.is_dir():
            continue
        lines.append(f"- `{artifact}`")
    report.write_text("\n".join(lines) + "\n")
    return report


def parse_semgrep_findings(path: Path) -> list[dict[str, str]]:
    """Parse Semgrep JSON findings into report rows."""

    if not path.exists() or not path.read_text().strip():
        return []
    data = json.loads(path.read_text())
    findings: list[dict[str, str]] = []
    for result in data.get("results", []):
        extra = result.get("extra", {})
        findings.append(
            {
                "check_id": str(result.get("check_id", "")),
                "path": str(result.get("path", "")).removeprefix("/scan/"),
                "line": str(result.get("start", {}).get("line", "")),
                "severity": str(extra.get("severity", "")),
                "message": str(extra.get("message", "")),
            }
        )
    return findings


def parse_nmap_text(output: str) -> list[str]:
    """Extract compact report lines from nmap stdout."""

    lines: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("80/tcp") or "VULNERABLE:" in stripped:
            lines.append(f"- `{stripped}`")
        elif "Internal IP Leaked:" in stripped:
            lines.append(f"- `{stripped}`")
        elif "CVE:" in stripped:
            lines.append(f"- `{stripped}`")
    return lines


def count_jsonl(path: Path) -> int:
    """Count non-empty JSONL rows."""

    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(errors="replace").splitlines() if line.strip())


def summarize_target_launch_plan(paths: SessionPaths) -> dict[str, str]:
    """Return report-safe target launch-plan fields."""

    path = paths.reports_dir / "target-launch-plan.json"
    if not path.exists():
        return {
            "source": "unknown",
            "reason": "target launch plan artifact was not written",
        }
    data = json.loads(path.read_text(errors="replace"))
    return {
        "source": str(data.get("source", "unknown")),
        "reason": str(data.get("reason", "unknown")),
    }


def summarize_exploit_status(paths: SessionPaths) -> dict[str, object]:
    """Summarize whether this session produced deterministic exploit proof."""

    proof_candidates = sorted((paths.session_dir / "attacks").glob("**/proof.*"))
    if proof_candidates:
        return {
            "status": "attempted_success",
            "proven": True,
            "artifact": str(proof_candidates[0]),
            "reason": "A bounded exploit probe produced a proof artifact under the session attacks directory.",
        }
    attack_outputs = sorted((paths.session_dir / "attacks").glob("**/*"))
    if attack_outputs:
        return {
            "status": "attempted_no_proof",
            "proven": False,
            "artifact": "none",
            "reason": "Exploit probe artifacts exist, but no deterministic proof artifact was found.",
        }
    return {
        "status": "not_attempted",
        "proven": False,
        "artifact": "none",
        "reason": "This session ran scanner lanes only; no bounded exploit probe was generated or executed.",
    }


def summarize_code_runner_runs(paths: SessionPaths) -> list[dict[str, object]]:
    """Summarize `/code-runner` result artifacts for exploit probe generation."""

    code_runner_dir = paths.session_dir / "code-runner"
    runs: list[dict[str, object]] = []
    result_paths = sorted(
        code_runner_dir.glob("*.result.json"),
        key=lambda path: (
            0 if path.name == "probe-command-injection.result.json" else 1,
            path.name,
        ),
    )
    for result_path in result_paths:
        data = json.loads(result_path.read_text(errors="replace"))
        task_id = str(data.get("task_id", result_path.stem.removesuffix(".result")))
        runs.append(
            {
                "task_id": task_id,
                "title": str(data.get("title", "")),
                "backend": str(data.get("backend", "")),
                "status": str(data.get("status", "")),
                "dod_passed": bool(data.get("dod_passed", False)),
                "rounds": data.get("rounds", ""),
                "best_score": data.get("best_score", ""),
                "patch": str(code_runner_dir / f"{task_id}.patch"),
                "hunk": str(code_runner_dir / f"{task_id}.hunk.md"),
            }
        )
    return runs


def summarize_probe_execution(paths: SessionPaths) -> dict[str, object]:
    """Summarize Docker-contained probe execution logs and proof artifact."""

    exit_code_path = paths.logs_dir / "probe-command-injection.exit-code"
    stderr_log = paths.logs_dir / "probe-command-injection.stderr.log"
    proof_candidates = sorted((paths.session_dir / "attacks").glob("**/proof.*"))
    exit_code = exit_code_path.read_text(errors="replace").strip() if exit_code_path.exists() else "not-run"
    result = "not run"
    if exit_code != "not-run":
        result = "proof found" if exit_code == "0" and proof_candidates else "no proof found"
    return {
        "executed": exit_code != "not-run",
        "exit_code": exit_code,
        "result": result,
        "proof_artifact": str(proof_candidates[0]) if proof_candidates else "none",
        "stderr_log": str(stderr_log) if stderr_log.exists() else "none",
    }


def summarize_proof_artifact(paths: SessionPaths) -> dict[str, str]:
    """Summarize the exploit proof payload in report-oriented language."""

    proof_candidates = sorted((paths.session_dir / "attacks").glob("**/proof.*"))
    if not proof_candidates:
        return {
            "finding": "no exploit proof artifact was produced",
            "indicator": "none",
            "target_summary": "none",
            "evidence_summary": "none",
        }
    data = json.loads(proof_candidates[0].read_text(errors="replace"))
    indicator = str(data.get("indicator", "unknown"))
    url = str(data.get("url", ""))
    target_summary = "authorized local VulnerableApp command-injection endpoint"
    if "/LEVEL_" in url:
        level_match = re.search(r"/LEVEL_([0-9]+)", url)
        if level_match:
            target_summary += f" at level {level_match.group(1)}"
    finding = (
        "command injection is exploitable; the target reflected operating-system "
        "command output from the vulnerable process"
    )
    evidence_summary = (
        "the HTTP response contained operating-system identity output from the "
        "target process; raw proof is stored only in the proof artifact"
    )
    return {
        "finding": finding,
        "indicator": indicator,
        "target_summary": target_summary,
        "evidence_summary": evidence_summary,
    }


def summarize_critical_findings(
    *,
    semgrep_findings: list[dict[str, str]],
    nmap_summary: list[str],
    nuclei_count: int,
) -> list[str]:
    """Return agent-readable findings that separate leads from proof."""

    summary: list[str] = []
    command_exec = [
        finding
        for finding in semgrep_findings
        if "runtime-exec" in finding.get("check_id", "")
    ]
    if command_exec:
        first = command_exec[0]
        summary.append(
            "Command execution candidate from Semgrep "
            f"at `{first.get('path', 'unknown')}` line `{first.get('line', 'unknown')}`; "
            "requires bounded exploit validation before calling it exploited."
        )
    file_path = [
        finding
        for finding in semgrep_findings
        if "file-path" in finding.get("check_id", "")
    ]
    if file_path:
        first = file_path[0]
        summary.append(
            "File path handling candidate from Semgrep "
            f"at `{first.get('path', 'unknown')}` line `{first.get('line', 'unknown')}`; "
            "review for traversal or unsafe file access."
        )
    if nmap_summary:
        summary.append(
            "Nmap produced service/vulnerability leads; treat CVE script output as leads until manually confirmed against the observed service."
        )
    if nuclei_count:
        summary.append(
            f"Nuclei produced `{nuclei_count}` JSONL finding rows; triage details in `reports/nuclei.jsonl`."
        )
    return summary


def write_memory_payload(paths: SessionPaths, report: Path) -> None:
    """Write a distilled memory payload artifact for the caller to ingest."""

    exploit_status = summarize_exploit_status(paths)
    payload = {
        "problem": "containerized /hack session audit completed",
        "solution": (
            "Generated a per-session scanner Dockerfile/compose, cloned the target "
            "repository in Docker, ran SAST/DAST in containers, optionally generated "
            "bounded proof probes with /code-runner, executed probes through /hack "
            "Docker, and wrote an executive report."
        ),
        "exploit_proven": bool(exploit_status["proven"]),
        "exploit_status": exploit_status["status"],
        "artifacts": [
            str(report),
            str(paths.scanner_dir / "Dockerfile"),
            str(paths.session_dir / "attacks"),
            str(paths.session_dir / "code-runner"),
        ],
    }
    (paths.reports_dir / "memory-payload.json").write_text(json.dumps(payload, indent=2))


__all__ = [
    "DEFAULT_NUCLEI_VERSION",
    "CommandResult",
    "DockerToolPlan",
    "ProbeRunConfig",
    "SessionPaths",
    "TargetLaunchPlan",
    "build_command_injection_probe_context",
    "build_session_compose",
    "build_session_dockerfile",
    "create_session_audit_command",
    "create_session_paths",
    "default_docker_tool_plan",
    "has_command_injection_candidate",
    "load_docker_tool_plan",
    "materialize_target_compose_env",
    "resolve_target_launch_plan",
    "parse_nmap_text",
    "parse_semgrep_findings",
    "run_exploit_probes",
    "summarize_critical_findings",
    "summarize_exploit_status",
    "write_command_injection_probe_task",
    "run_session_audit",
    "safe_slug",
]
