"""Containerized SAST and SCA commands for Hack."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

import typer
from rich.console import Console

from hack.audit_receipts import (
    build_audit_receipt,
    memory_document,
    parse_bandit,
    parse_semgrep,
    write_receipt,
)
from hack.config import BANDIT_SEVERITY_FLAGS, THREAT_PROFILES
from hack.container_manager import require_docker_image, run_in_docker
from hack.utils import add_task_accomplishment, end_task_session, memory_recall, memory_store_document, show_memory_context, start_task_session

console = Console()


def _scan_paths(target_path: Path) -> tuple[Path, str]:
    if target_path.is_file():
        return target_path.parent, f"/scan/{target_path.name}"
    return target_path, "/scan"


def _run_tool(name: str, cmd: list[str], mount_path: Path, network: str = "none") -> tuple[subprocess.CompletedProcess, dict[str, object]]:
    result = run_in_docker(cmd, target_path=str(mount_path), network=network)
    record = {
        "tool": name,
        "argv": result.args,
        "returncode": result.returncode,
        "network": network,
        "stdout_tail": (result.stdout or "")[-4000:],
        "stderr_tail": (result.stderr or "")[-4000:],
    }
    return result, record


def audit_command(
    target: str,
    tool: str = "all",
    severity: str = "medium",
    profile: str = "hobbyist",
    output: str | None = None,
    recall: bool = True,
    receipt_out: str | None = None,
    memory_store: bool = True,
    memory_collection: str = "hack_audit_summaries",
) -> dict[str, object]:
    """Run SAST in Docker and emit a typed Hack audit receipt."""
    target_path = Path(target).resolve()
    console.print(f"[bold red]Starting security audit for:[/bold red] {target_path}")
    console.print(f"[dim]Profile: {profile}[/dim]")
    console.print("[dim]Running in isolated Docker container...[/dim]")
    add_task_accomplishment(f"Starting SAST audit on {target_path.name} ({profile})")

    recall_packet = None
    if recall:
        recall_query = f"SAST security vulnerabilities {tool} Python code audit"
        recall_packet = memory_recall(recall_query, scope="hack_skill", k=3)
        show_memory_context(recall_query)

    require_docker_image()
    mount_path, scan_target = _scan_paths(target_path)
    profile_cfg = THREAT_PROFILES.get(profile, THREAT_PROFILES["hobbyist"])
    results: dict[str, str | None | int] = {"semgrep": None, "bandit": None, "total_findings": 0}
    tool_results: list[dict[str, object]] = []
    findings: list[dict[str, object]] = []

    if tool in ("all", "semgrep"):
        console.print("\n[cyan]Running Semgrep (SAST)...[/cyan]")
        severity_flags: list[str] = []
        for sev in profile_cfg["semgrep_severity"]:
            severity_flags.extend(["--severity", sev])
        cmd = ["semgrep", "scan", "--json", "--config", "/opt/hack-rules/offline-security.yml", *severity_flags, scan_target]
        try:
            result, record = _run_tool("semgrep", cmd, mount_path)
            tool_results.append(record)
            if result.stdout:
                results["semgrep"] = result.stdout
                findings.extend(parse_semgrep(result.stdout))
                console.print(result.stdout)
            if result.returncode != 0 and result.stderr:
                console.print(f"[dim]{result.stderr}[/dim]")
        except subprocess.TimeoutExpired:
            console.print("[yellow]Semgrep timed out[/yellow]")
            tool_results.append({"tool": "semgrep", "returncode": -1, "network": "none", "stderr_tail": "TIMEOUT"})
        except Exception as exc:
            console.print(f"[yellow]Semgrep error: {exc}[/yellow]")
            tool_results.append({"tool": "semgrep", "returncode": -2, "network": "none", "stderr_tail": str(exc)})

    if tool in ("all", "bandit"):
        console.print("\n[cyan]Running Bandit (Python SAST)...[/cyan]")
        cmd = ["bandit", "-r", scan_target, BANDIT_SEVERITY_FLAGS.get(severity.lower(), "-ll"), "-f", "txt"]
        try:
            result, record = _run_tool("bandit", cmd, mount_path)
            tool_results.append(record)
            if result.stdout:
                results["bandit"] = result.stdout
                findings.extend(parse_bandit(result.stdout))
                console.print(result.stdout)
            if result.returncode != 0 and result.stderr and "No issues" not in result.stderr:
                console.print(f"[dim]{result.stderr}[/dim]")
        except subprocess.TimeoutExpired:
            console.print("[yellow]Bandit timed out[/yellow]")
            tool_results.append({"tool": "bandit", "returncode": -1, "network": "none", "stderr_tail": "TIMEOUT"})
        except Exception as exc:
            console.print(f"[yellow]Bandit error: {exc}[/yellow]")
            tool_results.append({"tool": "bandit", "returncode": -2, "network": "none", "stderr_tail": str(exc)})

    results["total_findings"] = len(findings)
    if output:
        Path(output).write_text(json.dumps(results, indent=2))
        console.print(f"\n[green]Results saved to: {output}[/green]")

    receipt = build_audit_receipt(
        target=str(target_path),
        tool=tool,
        severity=severity,
        profile=profile,
        mount_path=str(mount_path),
        scan_target=scan_target,
        tool_results=tool_results,
        findings=findings,
        memory_recall=recall_packet,
    )
    receipt_path = write_receipt(receipt_out or Path(output or "/tmp/hack-audit.json").with_suffix(".receipt.json"), receipt)
    if memory_store:
        doc = memory_document(receipt, str(receipt_path))
        memory_ref = memory_store_document(doc, collection=memory_collection)
        receipt["memory"]["store_ref"] = memory_ref
        receipt["memory"]["store_error"] = None if memory_ref else "memory_store_failed"
        write_receipt(receipt_path, receipt)

    console.print(f"\n[green]Audit receipt saved to: {receipt_path}[/green]")
    console.print(json.dumps({"schema": "hack.audit_summary.v1", "status": receipt["status"], "receipt": str(receipt_path), "finding_count": len(findings)}))
    console.print("\n[bold green]Audit complete.[/bold green]")
    return receipt


def sca_command(target: str = ".", tool: str = "pip-audit", output: str | None = None) -> None:
    """Run Python dependency scanning in Docker."""
    target_path = Path(target).resolve()
    console.print(f"[bold blue]Scanning dependencies in:[/bold blue] {target_path}")
    console.print("[dim]Running in isolated Docker container...[/dim]")
    add_task_accomplishment(f"Starting SCA scan on {target_path.name}")
    require_docker_image()

    req_file = target_path / "requirements.txt"
    pyproject = target_path / "pyproject.toml"
    if not req_file.exists() and not pyproject.exists():
        console.print("[yellow]No requirements.txt or pyproject.toml found[/yellow]")

    if tool == "pip-audit":
        cmd = ["pip-audit"]
        if req_file.exists():
            cmd.extend(["-r", "/scan/requirements.txt"])
        console.print(f"[dim]Command: {' '.join(cmd)}[/dim]")
        try:
            result = run_in_docker(cmd, target_path=str(target_path), network="bridge")
            console.print("[green]No vulnerabilities found![/green]" if result.returncode == 0 else result.stdout)
            if result.returncode != 0 and result.stderr:
                console.print(f"[dim]{result.stderr}[/dim]")
            if output:
                Path(output).write_text(result.stdout or "")
                console.print(f"[dim]Results saved to: {output}[/dim]")
        except subprocess.TimeoutExpired:
            console.print("[red]Scan timed out[/red]")
            sys.exit(1)
    elif tool == "safety":
        cmd = ["safety", "check"]
        if req_file.exists():
            cmd.extend(["-r", "/scan/requirements.txt"])
        console.print(f"[dim]Command: {' '.join(cmd)}[/dim]")
        try:
            result = run_in_docker(cmd, target_path=str(target_path), network="bridge")
            console.print(result.stdout)
            if result.returncode != 0 and result.stderr:
                console.print(f"[dim]{result.stderr}[/dim]")
            if output:
                Path(output).write_text(result.stdout or "")
                console.print(f"[dim]Results saved to: {output}[/dim]")
        except subprocess.TimeoutExpired:
            console.print("[red]Scan timed out[/red]")
            sys.exit(1)


def create_audit_typer_command() -> Callable[..., None]:
    """Create the Typer audit command."""

    def audit(
        target: str = typer.Argument(..., help="Directory or file to audit"),
        tool: str = typer.Option("all", help="Tool to use: all, semgrep, bandit"),
        severity: str = typer.Option("medium", help="Minimum severity: low, medium, high"),
        profile: str = typer.Option("hobbyist", help="Threat profile: script-kiddie, hobbyist, organized-crime, state-actor"),
        output: str = typer.Option(None, help="Raw tool output JSON path"),
        receipt_out: str = typer.Option(None, "--receipt-out", help="Typed hack.audit_receipt.v1 output path"),
        recall: bool = typer.Option(True, help="Query Memory for prior audit knowledge before scanning"),
        memory_store: bool = typer.Option(True, "--memory-store/--no-memory-store", help="Store distilled audit summary through Memory /store"),
        memory_collection: str = typer.Option("hack_audit_summaries", help="Memory collection for distilled audit summaries"),
    ) -> None:
        """Run static application security testing in Docker and write receipts."""
        start_task_session(project=f"audit-{Path(target).name}")
        try:
            audit_command(target, tool, severity, profile, output, recall, receipt_out, memory_store, memory_collection)
            end_task_session(notes=f"Audit complete for {target}")
        except Exception as exc:
            end_task_session(notes=f"Audit failed: {exc}")
            raise

    return audit


def create_sca_typer_command() -> Callable[..., None]:
    """Create the Typer SCA command."""

    def sca(
        target: str = typer.Argument(".", help="Directory to scan for dependencies"),
        tool: str = typer.Option("pip-audit", help="Tool: pip-audit, safety"),
        output: str = typer.Option(None, help="Output file (JSON)"),
    ) -> None:
        """Software Composition Analysis in Docker."""
        start_task_session(project=f"sca-{Path(target).name}")
        try:
            sca_command(target, tool, output)
            end_task_session(notes=f"SCA scan complete for {target}")
        except Exception as exc:
            end_task_session(notes=f"SCA scan failed: {exc}")
            raise

    return sca


__all__ = ["audit_command", "sca_command", "create_audit_typer_command", "create_sca_typer_command"]
