#!/usr/bin/env python3
"""
Battle Skill - Red vs Blue Team Security Competition Orchestrator

CLI entry point for the battle skill. The actual implementation is split across:
- config.py: Constants, paths, environment variables
- state.py: Data classes and BattleState
- memory.py: Team-isolated memory system
- scoring.py: AIxCC-style scoring
- digital_twin.py: Git worktree, Docker, QEMU isolation
- red_team.py: Red Team attack agent
- blue_team.py: Blue Team defense agent
- orchestrator.py: Battle orchestration and game loop

Based on research into:
- RvB Framework (arXiv 2601.19726)
- DARPA AIxCC scoring system
- Microsoft PyRIT multi-turn orchestration
- DeepTeam async batch processing
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from common.security_authorization import validate_target_authorization
from .config import (
    BATTLES_DIR,
    REPORTS_DIR,
    OVERNIGHT_ROUNDS,
    OVERNIGHT_CHECKPOINT_INTERVAL,
)
from .state import BattleState, TwinMode
from loguru import logger

# Memory + Taxonomy integration (graceful degradation)
try:
    from .memory_integration import recall_prior_battles, learn_battle

    _HAS_MEMORY_INTEGRATION = True
except ImportError:
    _HAS_MEMORY_INTEGRATION = False

app = typer.Typer(help="Red vs Blue Team Security Competition Orchestrator")
console = Console()


def _write_ux_transport_artifacts(*, out: Path, battle_id: str) -> dict:
    """Generate normalized UX snapshot and file-backed stream artifacts."""
    from .battle_event_adapter import generate_fixture_files, generate_transport_files

    normalized_path = out / "battle.normalized_ux_fixture.json"
    fixture = generate_fixture_files(
        proof_dir=out, battle_id=battle_id, out=normalized_path
    )
    transport = generate_transport_files(fixture=fixture, out_dir=out / "stream")
    return {
        "schema": "battle.ux_transport_artifacts.v1",
        "status": "PASS",
        "normalized_fixture": str(normalized_path),
        **transport,
    }


@app.command()
def battle(
    target: str = typer.Argument(
        ".", help="Target directory, firmware file, or Docker image"
    ),
    rounds: int = typer.Option(100, help="Maximum number of rounds"),
    overnight: bool = typer.Option(
        False, help="Run as overnight job (1000 rounds, checkpoints every 50)"
    ),
    checkpoint_interval: int = typer.Option(10, help="Checkpoint every N rounds"),
    mode: str = typer.Option(
        None, help="Digital twin mode: git_worktree, docker, qemu, copy"
    ),
    docker_image: str = typer.Option(
        None, help="Docker image for container battles (e.g., nginx:latest)"
    ),
    qemu_machine: str = typer.Option(
        None, help="QEMU machine type (e.g., arm, riscv64, x86_64)"
    ),
    chaos: bool = typer.Option(
        False, "--chaos", help="Enable novel exploit brainstorming (Red Team)"
    ),
    profile: str = typer.Option(
        "hobbyist",
        help="Threat profile: script-kiddie, hobbyist, organized-crime, state-actor",
    ),
    model: str = typer.Option(
        "gpt-5.2-codex", help="AI model to use for research and brainstorming"
    ),
    authorization_manifest: Optional[Path] = typer.Option(
        None,
        "--authorization-manifest",
        help="security.target_authorization.v1 manifest required before Battle execution.",
    ),
    authorization_target: Optional[str] = typer.Option(
        None,
        "--authorization-target",
        help="Expected authorization target identity. Defaults to resolved target path or docker image.",
    ),
    expected_manifest_sha256: Optional[str] = typer.Option(
        None,
        "--expected-manifest-sha256",
        help="Expected authorization manifest SHA-256.",
    ),
):
    """
    Start a Red vs Blue team battle.

    DIGITAL TWIN MODES:

    1. Source Code (git_worktree): Battle over a git repository
       ./run.sh battle /path/to/repo

    2. Docker Container (docker): Battle over a containerized app
       ./run.sh battle --docker-image nginx:latest
       ./run.sh battle /path/with/Dockerfile

    3. Firmware/MCU (qemu): Battle over microprocessor firmware
       ./run.sh battle firmware.bin --qemu-machine arm
       ./run.sh battle firmware.elf

    Red Team attacks using hack skill.
    Blue Team defends using anvil skill.
    Both teams leverage memory for strategy recall.
    """
    from .orchestrator import BattleOrchestrator
    from .report import generate_report

    if overnight:
        rounds = OVERNIGHT_ROUNDS
        checkpoint_interval = OVERNIGHT_CHECKPOINT_INTERVAL
        console.print(
            f"[yellow]Overnight mode: {rounds} rounds, checkpoints every {checkpoint_interval}[/yellow]"
        )

    # Parse mode
    twin_mode = None
    if mode:
        try:
            twin_mode = TwinMode(mode)
        except ValueError:
            console.print(f"[red]Invalid mode: {mode}[/red]")
            console.print(
                f"[yellow]Valid modes: {', '.join(m.value for m in TwinMode)}[/yellow]"
            )
            raise typer.Exit(1)

    # Handle Docker image as target
    if docker_image and target == ".":
        target_path = Path.cwd()
        requested_identity = authorization_target or docker_image
    else:
        target_path = Path(target).resolve()
        requested_identity = authorization_target or str(target_path)
        if not target_path.exists():
            console.print(f"[red]Target not found: {target}[/red]")
            raise typer.Exit(1)

    requested_runtime_mode = mode or ("docker" if docker_image else "git_worktree")
    authorization_receipt = validate_target_authorization(
        authorization_manifest,
        expected_target=requested_identity,
        requested_action="battle",
        requested_runtime_mode=requested_runtime_mode,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    if authorization_receipt["status"] != "PASS":
        console.print("[red]Authorization preflight failed[/red]")
        for error in authorization_receipt["errors"]:
            console.print(f"- {error}")
        raise typer.Exit(2)

    # Pre-hook: Recall prior battle findings for this target
    if _HAS_MEMORY_INTEGRATION:
        try:
            prior = recall_prior_battles(str(target_path))
            if prior:
                console.print(
                    f"[dim]Recalled prior battle context ({len(prior)} chars)[/dim]"
                )
        except Exception as e:
            logger.error("Battle memory recall failed: {}", e)

    orchestrator = BattleOrchestrator(
        str(target_path),
        rounds,
        twin_mode=twin_mode,
        qemu_machine=qemu_machine,
        docker_image=docker_image,
        chaos=chaos,
        profile=profile,
        model=model,
    )
    state = orchestrator.run(checkpoint_interval)

    # Post-hook: Learn battle outcome
    if _HAS_MEMORY_INTEGRATION:
        try:
            learn_battle(
                target=str(target_path),
                red_findings=[
                    f.description if hasattr(f, "description") else str(f)
                    for f in (state.all_findings or [])[:10]
                ],
                blue_defenses=[
                    p.description if hasattr(p, "description") else str(p)
                    for p in (state.all_patches or [])
                    if hasattr(p, "verified") and p.verified
                ][:10],
                winner="Red Team"
                if state.red_total_score > state.blue_total_score
                else "Blue Team",
                lessons=[],
                battle_id=state.battle_id,
                rounds=state.current_round,
                red_score=state.red_total_score,
                blue_score=state.blue_total_score,
                tdsr=state.tdsr if hasattr(state, "tdsr") else 0.0,
            )
        except Exception as e:
            logger.error("Battle memory learn failed: {}", e)

    # Generate and save report
    report = generate_report(state)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{state.battle_id}.md"
    report_path.write_text(report)
    console.print(f"\n[green]Report saved: {report_path}[/green]")


def run_battle_fixture_command(fixture: str, out: Optional[Path]) -> None:
    """Run one deterministic Battle fixture with Red/Blue/Judge receipts."""
    from .battle_fixture import run_battle_001
    from .config import ARTIFACTS_DIR, SKILL_DIR

    fixture_dir = SKILL_DIR / "fixtures" / fixture
    if not fixture_dir.exists():
        console.print(f"[red]Fixture not found: {fixture_dir}[/red]")
        raise typer.Exit(1)

    out_dir = out or (ARTIFACTS_DIR / fixture)
    result = run_battle_001(fixture_dir=fixture_dir, out_dir=out_dir)
    console.print_json(data=result)

    if result.get("status") != "PASS":
        raise typer.Exit(1)


@app.command("battle-fixture")
def battle_fixture(
    fixture: str = typer.Argument(
        "battle-001", help="Fixture name under skills/battle/fixtures/"
    ),
    out: Optional[Path] = typer.Option(None, help="Artifact output directory"),
):
    """Run one deterministic Battle fixture with Red/Blue/Judge receipts."""
    run_battle_fixture_command(fixture, out)


@app.command("prove-reactive-judge-round")
def prove_reactive_judge_round(
    authorization_manifest: Path = typer.Option(
        ...,
        "--authorization-manifest",
        help="security.target_authorization.v1 manifest for the local Docker fixture.",
    ),
    out: Path = typer.Option(..., "--out", help="Artifact output directory."),
):
    """Run the local Docker reactive Blue + independent Judge round proof."""
    from .reactive_judge_round import run_reactive_judge_round

    manifest = authorization_manifest
    if not manifest.exists() and not manifest.is_absolute():
        repo_relative = Path(__file__).resolve().parents[4] / manifest
        if repo_relative.exists():
            manifest = repo_relative

    result = run_reactive_judge_round(
        authorization_manifest=manifest,
        out_dir=out,
    )
    console.print_json(data=result)
    if result.get("status") != "PASS":
        raise typer.Exit(1)


@app.command("arena-subagent-proof")
def arena_subagent_proof(
    battle_id: str = typer.Argument(
        "battle-004", help="Battle ID for the Arena proof."
    ),
    out: Path = typer.Option(..., help="Artifact output directory."),
    prior_scoreboard: Optional[Path] = typer.Option(
        None,
        help="Prior scoreboard JSON Arena may use for difficulty calibration.",
    ),
    query: str = typer.Option(
        "OWASP file upload zip slip path traversal vulnerability",
        help="Brave Search query for scenario selection.",
    ),
    docker_image: str = typer.Option(
        "python:3.12-slim",
        help="Docker image used for the hidden vulnerability oracle.",
    ),
):
    """Run one Arena Tau subagent proof with Brave research and Docker oracle."""
    from .arena_subagent import run_arena_subagent_proof

    import datetime as _dt

    run_id = f"arena-subagent-{_dt.datetime.now(_dt.UTC).strftime('%Y%m%dT%H%M%SZ')}"
    result = run_arena_subagent_proof(
        out_dir=out,
        battle_id=battle_id,
        run_id=run_id,
        prior_scoreboard=prior_scoreboard,
        query=query,
        docker_image=docker_image,
    )
    console.print_json(data=result)
    if result.get("status") != "PASS":
        raise typer.Exit(1)


@app.command("arena-battle-proof")
def arena_battle_proof(
    battle_id: str = typer.Argument(
        "battle-005", help="Battle ID for the Arena Battle proof."
    ),
    out: Path = typer.Option(..., help="Artifact output directory."),
    prior_scoreboard: Optional[Path] = typer.Option(
        None,
        help="Prior scoreboard JSON Arena may use for difficulty calibration.",
    ),
    query: str = typer.Option(
        "OWASP file upload zip slip path traversal vulnerability",
        help="Brave Search query for scenario selection.",
    ),
    docker_image: str = typer.Option(
        "python:3.12-slim",
        help="Docker image used for the target runtime and Judge replay.",
    ),
    red_language: str = typer.Option(
        "python",
        help="Red team's selected implementation language from Arena's allowed set.",
    ),
    blue_language: str = typer.Option(
        "shell",
        help="Blue team's selected implementation language from Arena's allowed set.",
    ),
    scenario_kind: str = typer.Option(
        "zip-slip",
        help="Scenario kind: zip-slip, signed-token-duplicate-claim, ssrf-metadata-probe, pickle-deserialization-gadget, or file-upload-extension-probe.",
    ),
):
    """Run Arena-created scenario through deterministic Red/Blue/Judge proof."""
    from .arena_battle_proof import run_arena_battle_proof

    import datetime as _dt

    run_id = f"arena-battle-{_dt.datetime.now(_dt.UTC).strftime('%Y%m%dT%H%M%SZ')}"
    result = run_arena_battle_proof(
        out_dir=out,
        battle_id=battle_id,
        run_id=run_id,
        prior_scoreboard=prior_scoreboard,
        query=query,
        docker_image=docker_image,
        red_language=red_language,
        blue_language=blue_language,
        scenario_kind=scenario_kind,
    )
    console.print_json(data=result)
    if result.get("status") != "PASS":
        raise typer.Exit(1)


@app.command("arena-tau-public-only-proof")
def arena_tau_public_only_proof(
    battle_id: str = typer.Argument(
        "battle-004", help="Battle ID for the Tau public-only proof."
    ),
    out: Path = typer.Option(..., help="Artifact output directory."),
    query: str = typer.Option(
        "OWASP file upload zip slip path traversal vulnerability",
        help="Brave Search query for Arena scenario selection.",
    ),
    docker_image: str = typer.Option(
        "python:3.12-slim",
        help="Docker image used for Arena hidden oracle.",
    ),
    model: str = typer.Option(
        "gpt-5.5",
        help="Model Tau should request through its Scillm handoff bridge.",
    ),
    scillm_base_url: str = typer.Option(
        "http://localhost:4001",
        help="Scillm base URL used by Tau, not directly by Battle.",
    ),
    timeout_s: float = typer.Option(
        1200.0,
        help="Resolved round time in seconds. BATTLE-004 defaults to 1200s; pass an override for dev smoke runs.",
    ),
    red_workers: int = typer.Option(
        1,
        help="Number of bounded Red Tau workers to request.",
    ),
    blue_workers: int = typer.Option(
        1,
        help="Number of bounded Blue Tau workers to request.",
    ),
    spawn_red_child_on_blue_success: bool = typer.Option(
        False,
        "--spawn-red-child-on-blue-success",
        help="Request one Red child lane only after the parent Red lane has a Judge BLUE_SUCCESS handoff.",
    ),
):
    """Run Arena public-only Red/Blue through the Tau handoff bridge."""
    from .arena_live_battle_proof import run_arena_tau_public_only_proof

    import datetime as _dt

    run_id = (
        f"arena-tau-public-only-{_dt.datetime.now(_dt.UTC).strftime('%Y%m%dT%H%M%SZ')}"
    )
    result = run_arena_tau_public_only_proof(
        out_dir=out,
        battle_id=battle_id,
        run_id=run_id,
        query=query,
        docker_image=docker_image,
        model=model,
        scillm_base_url=scillm_base_url,
        timeout_s=timeout_s,
        red_workers=red_workers,
        blue_workers=blue_workers,
        spawn_red_child_on_blue_success=spawn_red_child_on_blue_success,
    )
    import json as _json

    print(_json.dumps(result, indent=2, sort_keys=True))
    if result.get("status") == "FAIL":
        raise typer.Exit(1)


@app.command("arena-parent-spawn-proof")
def arena_parent_spawn_proof(
    battle_id: str = typer.Argument(
        "battle-004", help="Canonical Battle ID for the parent-spawn proof."
    ),
    out: Path = typer.Option(..., help="Artifact output directory."),
    query: str = typer.Option(
        "OWASP file upload zip slip path traversal vulnerability",
        help="Brave Search query for canonical BATTLE-004 scenario selection.",
    ),
    docker_image: str = typer.Option(
        "python:3.12-slim",
        help="Docker image used for Arena hidden oracle and Judge replay.",
    ),
    model: str = typer.Option(
        "gpt-5.5",
        help="Model Tau should request through its Scillm handoff bridge.",
    ),
    scillm_base_url: str = typer.Option(
        "http://localhost:4001",
        help="Scillm base URL used by Tau, not directly by Battle.",
    ),
    timeout_s: float = typer.Option(
        1200.0,
        help="Resolved round time in seconds. BATTLE-004 defaults to 1200s; pass an override for dev smoke runs.",
    ),
    red_workers: int = typer.Option(
        2,
        help="Requested Red worker count. The runner starts with one parent when lineage is requested.",
    ),
    blue_workers: int = typer.Option(
        2,
        help="Requested Blue Tau worker count.",
    ),
):
    """Run canonical BATTLE-004 Tau proof with parent-spawn lineage requested."""
    from .arena_live_battle_proof import run_arena_tau_public_only_proof

    import datetime as _dt
    import json as _json

    run_id = (
        f"arena-parent-spawn-{_dt.datetime.now(_dt.UTC).strftime('%Y%m%dT%H%M%SZ')}"
    )
    result = run_arena_tau_public_only_proof(
        out_dir=out,
        battle_id=battle_id,
        run_id=run_id,
        query=query,
        docker_image=docker_image,
        model=model,
        scillm_base_url=scillm_base_url,
        timeout_s=timeout_s,
        red_workers=red_workers,
        blue_workers=blue_workers,
        spawn_red_child_on_blue_success=True,
    )
    if result.get("status") != "FAIL":
        result["ux_transport_artifacts"] = _write_ux_transport_artifacts(
            out=out, battle_id=battle_id
        )
    print(_json.dumps(result, indent=2, sort_keys=True))
    if result.get("status") == "FAIL":
        raise typer.Exit(1)


@app.command("arena-adaptive-lineage-qualification")
def arena_adaptive_lineage_qualification(
    battle_id: str = typer.Argument(
        "battle-004", help="Canonical Battle ID for the adaptive-lineage qualification."
    ),
    out: Optional[Path] = typer.Option(None, help="Artifact output directory."),
    proof_dir: Optional[Path] = typer.Option(
        None,
        help="Proof directory for recovered battle-004 Red/Blue lineage qualification.",
    ),
    source_root: Optional[Path] = typer.Option(
        None,
        help="Recovered adaptive Red/Blue lineage run directory.",
    ),
    fresh: bool = typer.Option(
        False,
        help="Recompute recovered-run verification before writing qualification artifacts.",
    ),
    require_live: bool = typer.Option(
        False,
        help="Require recovered receipts and verification to be live.",
    ),
    forbid_mock: bool = typer.Option(
        False,
        help="Reject mocked recovered receipts and verification.",
    ),
    require_exact_replay: bool = typer.Option(
        False,
        help="Require 2/2 exact Judge replay receipts to rehash.",
    ),
    query: str = typer.Option(
        "OWASP file upload zip slip path traversal vulnerability",
        help="Brave Search query for canonical BATTLE-004 scenario selection.",
    ),
    docker_image: str = typer.Option(
        "python:3.12-slim",
        help="Docker image used for Arena hidden oracle and Judge replay.",
    ),
    model: str = typer.Option(
        "gpt-5.5",
        help="Model Tau should request through its Scillm handoff bridge.",
    ),
    scillm_base_url: str = typer.Option(
        "http://localhost:4001",
        help="Scillm base URL used by Tau, not directly by Battle.",
    ),
    timeout_s: float = typer.Option(
        1200.0,
        help="Total round budget in seconds (adaptive-lineage stop condition is 1200s).",
    ),
):
    """Run one live four-specimen adaptive-lineage qualification (G0 -> G1-A/G1-B -> G2).

    The deterministic reducer + RecordedSpecimenProvider are proven by
    tests/test_adaptive_lineage_reducer.py; this drives the same reducer with the
    LIVE Tau specimen provider. The emitted battle.adaptive_lineage_qualification.v1
    receipt controls the exit code (0 only on PASS). Runs the specimen loop once.
    """
    import json as _json

    if proof_dir is not None:
        from .adaptive_lineage_goal_qualification import (
            DEFAULT_RECOVERED_RUN_DIR,
            qualify_recovered_adaptive_lineage_run,
        )

        result = qualify_recovered_adaptive_lineage_run(
            source_root=source_root or DEFAULT_RECOVERED_RUN_DIR,
            proof_dir=proof_dir,
            battle_id=battle_id,
            require_live=require_live,
            forbid_mock=forbid_mock,
            require_exact_replay=require_exact_replay,
        )
        result["fresh_verification_requested"] = fresh
        print(_json.dumps(result, indent=2, sort_keys=True))
        if result.get("status") != "PASS":
            raise typer.Exit(1)
        return

    if out is None:
        raise typer.BadParameter("--out is required unless --proof-dir is supplied")

    import datetime as _dt

    from .arena_live_battle_proof import run_live_adaptive_lineage_qualification

    run_id = (
        f"arena-adaptive-lineage-{_dt.datetime.now(_dt.UTC).strftime('%Y%m%dT%H%M%SZ')}"
    )
    result = run_live_adaptive_lineage_qualification(
        out_dir=out,
        battle_id=battle_id,
        run_id=run_id,
        query=query,
        docker_image=docker_image,
        model=model,
        scillm_base_url=scillm_base_url,
        timeout_s=timeout_s,
    )
    print(_json.dumps(result, indent=2, sort_keys=True))
    if result.get("status") != "PASS":
        raise typer.Exit(1)


@app.command("arena-prekill-survival-proof")
def arena_prekill_survival_proof(
    battle_id: str = typer.Argument(
        "battle-004", help="Canonical Battle ID for the pre-kill survival proof."
    ),
    out: Path = typer.Option(..., help="Artifact output directory."),
    query: str = typer.Option(
        "OWASP file upload zip slip path traversal vulnerability",
        help="Brave Search query for canonical BATTLE-004 scenario selection.",
    ),
    docker_image: str = typer.Option(
        "python:3.12-slim",
        help="Docker image used for Arena hidden oracle and Judge replay.",
    ),
    model: str = typer.Option(
        "gpt-5.5",
        help="Model Tau should request through its Scillm handoff bridge.",
    ),
    scillm_base_url: str = typer.Option(
        "http://localhost:4001",
        help="Scillm base URL used by Tau, not directly by Battle.",
    ),
    timeout_s: float = typer.Option(
        1200.0,
        help="Resolved round time in seconds. BATTLE-004 defaults to 1200s; pass an override for dev smoke runs.",
    ),
    red_workers: int = typer.Option(
        2,
        help="Requested Red worker count. Pre-kill survival requires at least one parent and one child lane.",
    ),
    blue_workers: int = typer.Option(
        2,
        help="Requested Blue Tau worker count.",
    ),
):
    """Run canonical BATTLE-004 Tau proof for pre-kill child survival lifecycle semantics."""
    from .arena_live_battle_proof import run_arena_prekill_survival_proof

    import datetime as _dt
    import json as _json

    run_id = (
        f"arena-prekill-survival-{_dt.datetime.now(_dt.UTC).strftime('%Y%m%dT%H%M%SZ')}"
    )
    result = run_arena_prekill_survival_proof(
        out_dir=out,
        battle_id=battle_id,
        run_id=run_id,
        query=query,
        docker_image=docker_image,
        model=model,
        scillm_base_url=scillm_base_url,
        timeout_s=timeout_s,
        red_workers=red_workers,
        blue_workers=blue_workers,
    )
    print(_json.dumps(result, indent=2, sort_keys=True))
    if result.get("status") != "PASS":
        raise typer.Exit(1)


@app.command("validate-ux-contract")
def validate_ux_contract(
    fixture: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Normalized Battle UX fixture JSON.",
    ),
):
    """Validate backend JSON values and fail-closed UX guardrails."""
    import json as _json

    from .ux_contract_validator import (
        DEFAULT_SCHEMA_PATH,
        ContractError,
        validate_fixture,
        validate_fixture_schema,
    )

    payload = _json.loads(fixture.read_text(encoding="utf-8"))
    try:
        validate_fixture(payload)
        validate_fixture_schema(payload)
    except ContractError as exc:
        console.print(f"[red]Battle UX contract invalid:[/red]\n{exc}")
        raise typer.Exit(1) from exc
    console.print_json(
        data={
            "status": "PASS",
            "fixture": str(fixture),
            "schema": payload.get("schema"),
            "ux_contract_schema": payload.get("ux_contract", {}).get("schema")
            if isinstance(payload.get("ux_contract"), dict)
            else None,
            "json_schema": str(DEFAULT_SCHEMA_PATH),
            "lineage_mode": payload.get("lineage", {}).get("mode")
            if isinstance(payload.get("lineage"), dict)
            else None,
            "child_spawn_count": payload.get("scoreboard", {}).get("child_spawn_count")
            if isinstance(payload.get("scoreboard"), dict)
            else None,
            "mocked": payload.get("mocked"),
            "live_source": payload.get("live_source"),
        }
    )


@app.command("generate-ux-transport")
def generate_ux_transport(
    proof_dir: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Battle proof directory containing run-receipt, scoreboard, and Tau/Arena/Judge artifacts.",
    ),
    battle_id: str = typer.Option(
        "battle-004", help="Expected Battle id for the generated fixture."
    ),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        help="Output directory for stream artifacts. Defaults to <proof-dir>/stream.",
    ),
    fixture_out: Optional[Path] = typer.Option(
        None,
        "--fixture-out",
        help="Output normalized fixture path. Defaults to <proof-dir>/battle.normalized_ux_fixture.json.",
    ),
):
    """Generate Pixi-consumable file-backed JSON transport artifacts from a proof directory."""
    import json as _json

    from .battle_event_adapter import generate_fixture_files, generate_transport_files

    fixture_path = fixture_out or (proof_dir / "battle.normalized_ux_fixture.json")
    stream_dir = out or (proof_dir / "stream")
    fixture = generate_fixture_files(
        proof_dir=proof_dir, battle_id=battle_id, out=fixture_path
    )
    result = generate_transport_files(fixture=fixture, out_dir=stream_dir)
    result["normalized_fixture"] = str(fixture_path)
    print(_json.dumps(result, indent=2, sort_keys=True))


@app.command("validate-ux-transport")
def validate_ux_transport(
    stream_dir: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Battle stream directory containing manifest.json, events.jsonl, and latest-snapshot.json.",
    ),
):
    """Validate file-backed Battle UX transport artifacts for Phase 2 stream replay."""
    from .ux_contract_validator import ContractError, validate_transport_stream_path

    try:
        report = validate_transport_stream_path(stream_dir)
    except ContractError as exc:
        console.print(f"[red]Battle UX transport invalid:[/red]\n{exc}")
        raise typer.Exit(1) from exc
    console.print_json(data=report)


@app.command("export-semantic-outcome-matrix")
def export_semantic_outcome_matrix(
    out: Path = typer.Option(
        ..., "--out", help="Output Battle semantic outcome matrix JSON path."
    ),
):
    """Export deterministic Battle outcome scoring and sprite-profile calibration."""
    from .battle_event_adapter import write_semantic_outcome_matrix
    from .ux_contract_validator import (
        ContractError,
        validate_semantic_outcome_matrix,
        validate_semantic_outcome_matrix_schema,
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    matrix = write_semantic_outcome_matrix(out=out)
    try:
        validate_semantic_outcome_matrix_schema(matrix)
        validate_semantic_outcome_matrix(matrix)
    except ContractError as exc:
        console.print(f"[red]Battle semantic outcome matrix invalid:[/red]\n{exc}")
        raise typer.Exit(1) from exc
    console.print_json(
        data={
            "status": "PASS",
            "out": str(out),
            "schema": matrix.get("schema"),
            "outcome_case_count": len(matrix.get("outcome_cases", [])),
            "profile_case_count": len(matrix.get("profile_cases", [])),
            "proof_mode": matrix.get("proof_mode"),
        }
    )


@app.command("validate-semantic-outcome-matrix")
def validate_semantic_outcome_matrix_command(
    matrix: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Battle semantic outcome matrix JSON.",
    ),
):
    """Validate deterministic Battle outcome scoring and sprite-profile calibration."""
    from .ux_contract_validator import (
        ContractError,
        validate_semantic_outcome_matrix_path,
    )

    try:
        report = validate_semantic_outcome_matrix_path(matrix)
    except ContractError as exc:
        console.print(f"[red]Battle semantic outcome matrix invalid:[/red]\n{exc}")
        raise typer.Exit(1) from exc
    console.print_json(data=report)


@app.command("export-exploit-lifecycle-dag")
def export_exploit_lifecycle_dag(
    out: Path = typer.Option(
        ..., "--out", help="Output Battle exploit lifecycle DAG JSON path."
    ),
):
    """Export deterministic exploit lifecycle DAG contract."""
    from .battle_event_adapter import write_exploit_lifecycle_dag
    from .ux_contract_validator import (
        ContractError,
        validate_exploit_lifecycle_dag,
        validate_exploit_lifecycle_dag_schema,
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    dag = write_exploit_lifecycle_dag(out=out)
    try:
        validate_exploit_lifecycle_dag_schema(dag)
        validate_exploit_lifecycle_dag(dag)
    except ContractError as exc:
        console.print(f"[red]Battle exploit lifecycle DAG invalid:[/red]\n{exc}")
        raise typer.Exit(1) from exc
    console.print_json(
        data={
            "status": "PASS",
            "out": str(out),
            "schema": dag.get("schema"),
            "node_count": len(dag.get("nodes", [])),
            "edge_count": len(dag.get("edges", [])),
            "outcome_classes": dag.get("outcome_classes"),
            "proof_mode": dag.get("proof_mode"),
        }
    )


@app.command("validate-exploit-lifecycle-dag")
def validate_exploit_lifecycle_dag_command(
    dag: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Battle exploit lifecycle DAG JSON.",
    ),
):
    """Validate deterministic exploit lifecycle DAG contract."""
    from .ux_contract_validator import (
        ContractError,
        validate_exploit_lifecycle_dag_path,
    )

    try:
        report = validate_exploit_lifecycle_dag_path(dag)
    except ContractError as exc:
        console.print(f"[red]Battle exploit lifecycle DAG invalid:[/red]\n{exc}")
        raise typer.Exit(1) from exc
    console.print_json(data=report)


@app.command("export-exploit-lifecycle-receipts")
def export_exploit_lifecycle_receipts(
    proof_dir: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Live BATTLE-004 proof directory containing exploit-lifecycle-receipts.json.",
    ),
    out: Path = typer.Option(
        ..., "--out", help="Output Battle exploit lifecycle receipts JSON path."
    ),
):
    """Export live Tau exploit lifecycle receipts from an existing proof directory."""
    import json as _json

    from .ux_contract_validator import (
        ContractError,
        validate_exploit_lifecycle_receipts,
        validate_exploit_lifecycle_receipts_schema,
    )

    source = proof_dir / "exploit-lifecycle-receipts.json"
    if not source.exists():
        console.print(f"[red]Battle exploit lifecycle receipts missing:[/red] {source}")
        raise typer.Exit(1)
    payload = _json.loads(source.read_text(encoding="utf-8"))
    try:
        validate_exploit_lifecycle_receipts_schema(payload)
        validate_exploit_lifecycle_receipts(payload)
    except ContractError as exc:
        console.print(f"[red]Battle exploit lifecycle receipts invalid:[/red]\n{exc}")
        raise typer.Exit(1) from exc
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        _json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    console.print_json(
        data={
            "status": "PASS",
            "out": str(out),
            "schema": payload.get("schema"),
            "receipt_count": summary.get("receipt_count"),
            "pressure_receipt_count": summary.get("pressure_receipt_count"),
            "lineage_receipt_count": summary.get("lineage_receipt_count"),
            "spawn_decisions": summary.get("spawn_decisions"),
            "outcome_classes": summary.get("outcome_classes"),
            "mocked": payload.get("mocked"),
            "live": payload.get("live"),
            "proof_mode": payload.get("proof_mode"),
        }
    )


@app.command("validate-exploit-lifecycle-receipts")
def validate_exploit_lifecycle_receipts_command(
    receipts: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Battle exploit lifecycle receipts JSON.",
    ),
):
    """Validate live Tau exploit lifecycle receipt bundle."""
    from .ux_contract_validator import (
        ContractError,
        validate_exploit_lifecycle_receipts_path,
    )

    try:
        report = validate_exploit_lifecycle_receipts_path(receipts)
    except ContractError as exc:
        console.print(f"[red]Battle exploit lifecycle receipts invalid:[/red]\n{exc}")
        raise typer.Exit(1) from exc
    console.print_json(data=report)


@app.command("exploit-combiner-proof")
def exploit_combiner_proof(
    battle_id: str = typer.Argument(
        "battle-004", help="Battle id for the fixture-backed combiner proof."
    ),
    out: Path = typer.Option(
        ..., "--out", help="Output directory for exploit combiner artifacts."
    ),
    max_attempts: int = typer.Option(
        4,
        "--max-attempts",
        min=1,
        help="Maximum fixture specimens to materialize and run.",
    ),
    docker_image: str = typer.Option(
        "python:3.12-slim",
        "--docker-image",
        help="Docker image used to run specimen code.",
    ),
    model: str = typer.Option(
        "gpt-5.5",
        "--model",
        help="Future Tau model request, recorded but not used by PR1 fixture proof.",
    ),
    scillm_base_url: str = typer.Option(
        "http://localhost:4001",
        "--scillm-base-url",
        help="Future scillm endpoint, recorded but not used by PR1 fixture proof.",
    ),
):
    """Run fixture-backed exploit specimen combiner proof without claiming exploit success."""
    from .exploit_combiner import run_exploit_combiner_proof

    receipt = run_exploit_combiner_proof(
        battle_id=battle_id,
        out_dir=out,
        max_attempts=max_attempts,
        docker_image=docker_image,
        model=model,
        scillm_base_url=scillm_base_url,
    )
    scoreboard = (
        receipt.get("scoreboard") if isinstance(receipt.get("scoreboard"), dict) else {}
    )
    console.print_json(
        data={
            "status": receipt.get("status"),
            "schema": receipt.get("schema"),
            "battle_id": battle_id,
            "out": str(out),
            "proof_mode": receipt.get("proof_mode"),
            "agentic": receipt.get("agentic"),
            "generated_specimens": scoreboard.get("generated_specimens"),
            "compile_failed": scoreboard.get("compile_failed"),
            "runtime_failed": scoreboard.get("runtime_failed"),
            "target_contact_unproven": scoreboard.get("target_contact_unproven"),
            "runnable_unproven": scoreboard.get("runnable_unproven"),
            "judge_verified_exploits": scoreboard.get("judge_verified_exploits"),
            "verdict": scoreboard.get("verdict"),
        }
    )


@app.command("spawn-architect-proof")
def spawn_architect_proof(
    battle_id: str = typer.Argument(
        "battle-004", help="Battle id for the fixture-backed Spawn Architect proof."
    ),
    out: Path = typer.Option(
        ..., "--out", help="Output directory for Spawn Architect artifacts."
    ),
    parent_combiner_proof: Path = typer.Option(
        ...,
        "--parent-combiner-proof",
        exists=True,
        readable=True,
        help="Parent combiner proof directory or run-receipt.json.",
    ),
):
    """Run fixture-backed Spawn Architect DAG birth proof without executing Tau."""
    from .spawn_architect import run_spawn_architect_proof

    receipt = run_spawn_architect_proof(
        battle_id=battle_id,
        out_dir=out,
        parent_combiner_proof=parent_combiner_proof,
    )
    scoreboard = (
        receipt.get("scoreboard") if isinstance(receipt.get("scoreboard"), dict) else {}
    )
    validation = (
        receipt.get("validation") if isinstance(receipt.get("validation"), dict) else {}
    )
    console.print_json(
        data={
            "status": receipt.get("status"),
            "schema": receipt.get("schema"),
            "battle_id": battle_id,
            "out": str(out),
            "proof_mode": receipt.get("proof_mode"),
            "agentic": receipt.get("agentic"),
            "tau_execution": receipt.get("tau_execution"),
            "spawn_policy_decision": (receipt.get("spawn_policy") or {}).get("decision")
            if isinstance(receipt.get("spawn_policy"), dict)
            else None,
            "dag_id": validation.get("dag_id"),
            "private_boundary_passed": validation.get("private_boundary_passed"),
            "child_tau_dags_validated": scoreboard.get("child_tau_dags_validated"),
            "live_tau_executions": scoreboard.get("live_tau_executions"),
            "child_exploits_materialized": scoreboard.get(
                "child_exploits_materialized"
            ),
            "judge_verified_exploits": scoreboard.get("judge_verified_exploits"),
            "verdict": scoreboard.get("verdict"),
        }
    )


@app.command("adaptive-red-blue-lineage-canary")
def adaptive_red_blue_lineage_canary(
    battle_id: str = typer.Argument("battle-004"),
    out: Path = typer.Option(..., "--out"),
    run_id: str = typer.Option(..., "--run-id"),
    docker_image: str = typer.Option("python:3.12-slim", "--docker-image"),
    model: str = typer.Option("gpt-5.5", "--model"),
    scillm_base_url: str = typer.Option("http://localhost:4001", "--scillm-base-url"),
    timeout_s: float = typer.Option(300.0, "--timeout-s", min=60.0),
    authorization_manifest: Optional[Path] = typer.Option(None, "--authorization-manifest"),
):
    """Run simultaneous Red/Blue parent and child generations through Tau, Docker, and Judge."""
    import json as _json

    from .adaptive_red_blue_lineage_canary import run_adaptive_red_blue_lineage_canary

    receipt = run_adaptive_red_blue_lineage_canary(
        battle_id=battle_id,
        out_dir=out,
        run_id=run_id,
        docker_image=docker_image,
        model=model,
        scillm_base_url=scillm_base_url,
        timeout_s=timeout_s,
        authorization_manifest=authorization_manifest,
    )
    print(_json.dumps(receipt, indent=2, sort_keys=True))
    if receipt.get("status") != "PASS":
        raise typer.Exit(1)


@app.command("adaptive-memory-canary")
def adaptive_memory_canary(
    battle_id: str = typer.Argument("battle-004"),
    source_root: Path = typer.Option(..., "--source-root", exists=True, readable=True),
    out: Path = typer.Option(..., "--out"),
    run_id: str = typer.Option(..., "--run-id"),
    memory_base_url: str = typer.Option("http://127.0.0.1:8601", "--memory-base-url"),
    docker_image: str = typer.Option("python:3.12-slim", "--docker-image"),
    model: str = typer.Option("gpt-5.5", "--model"),
    scillm_base_url: str = typer.Option("http://localhost:4001", "--scillm-base-url"),
    timeout_s: float = typer.Option(300.0, "--timeout-s", min=60.0),
):
    """Prove V13 selected evidence is written, recalled, and used by live providers."""
    import json as _json

    from .adaptive_memory_canary import run_adaptive_memory_canary

    receipt = run_adaptive_memory_canary(
        battle_id=battle_id,
        source_root=source_root,
        out_dir=out,
        run_id=run_id,
        memory_base_url=memory_base_url,
        docker_image=docker_image,
        model=model,
        scillm_base_url=scillm_base_url,
        timeout_s=timeout_s,
    )
    print(_json.dumps(receipt, indent=2, sort_keys=True))
    if receipt.get("status") != "PASS":
        raise typer.Exit(1)


@app.command("adaptive-memory-ablation")
def adaptive_memory_ablation(
    phase: str = typer.Argument(
        ..., help="One of: plan, validate, preflight, run, aggregate."
    ),
    battle_id: str = typer.Option("battle-004", "--battle-id"),
    experiment_id: str = typer.Option(
        "battle-004-memory-ablation-v15", "--experiment-id"
    ),
    source_root: Optional[Path] = typer.Option(
        None, "--source-root", exists=True, readable=True
    ),
    memory_source_root: Optional[Path] = typer.Option(
        None, "--memory-source-root", exists=True, readable=True
    ),
    plan: Optional[Path] = typer.Option(
        None, "--plan", exists=True, file_okay=True, dir_okay=False, readable=True
    ),
    out: Optional[Path] = typer.Option(None, "--out"),
    randomization_seed: str = typer.Option("battle-v15-block-order", "--seed"),
    memory_base_url: str = typer.Option("http://127.0.0.1:8601", "--memory-base-url"),
    docker_image: str = typer.Option("python:3.12-slim", "--docker-image"),
    docker_image_identity: Optional[str] = typer.Option(
        None, "--docker-image-identity"
    ),
    model: str = typer.Option("gpt-5.5", "--model"),
    scillm_base_url: str = typer.Option("http://localhost:4001", "--scillm-base-url"),
    tau_root: Path = typer.Option(
        Path("/home/graham/workspace/experiments/tau"), "--tau-root"
    ),
    timeout_s: float = typer.Option(300.0, "--timeout-s", min=60.0),
    generated_at: Optional[str] = typer.Option(None, "--generated-at"),
    resume: bool = typer.Option(
        False,
        "--resume",
        help="Reuse only a validated frozen-order prefix of terminal trial receipts.",
    ),
):
    """Plan, validate, preflight, run, or aggregate the bounded V15 2x2x3 memory ablation."""
    import json as _json

    from .adaptive_memory_ablation import (
        ContractError,
        aggregate_experiment,
        build_experiment_plan,
        file_sha256,
        load_source_bindings,
        preflight_experiment,
        resolve_docker_image_identity,
        run_experiment,
        validate_experiment_plan,
        write_experiment_plan,
    )

    normalized_phase = phase.strip().lower()
    try:
        if resume and normalized_phase != "run":
            raise ContractError("--resume is valid only for the run phase")
        if normalized_phase == "plan":
            if source_root is None or memory_source_root is None or out is None:
                raise ContractError(
                    "plan requires --source-root, --memory-source-root, and --out"
                )
            source_binding, memory_sources = load_source_bindings(
                source_root=source_root,
                memory_source_root=memory_source_root,
                battle_id=battle_id,
            )
            identity = docker_image_identity or resolve_docker_image_identity(
                docker_image
            )
            experiment = build_experiment_plan(
                battle_id=battle_id,
                experiment_id=experiment_id,
                source_binding=source_binding,
                memory_sources=memory_sources,
                randomization_seed=randomization_seed,
                docker_image=docker_image,
                docker_image_identity=identity,
                model=model,
                scillm_base_url=scillm_base_url,
                timeout_s=timeout_s,
                generated_at=generated_at,
            )
            result = write_experiment_plan(plan=experiment, out=out)
        elif normalized_phase == "validate":
            if plan is None:
                raise ContractError("validate requires --plan")
            payload = _json.loads(plan.read_text(encoding="utf-8"))
            result = validate_experiment_plan(payload)
        elif normalized_phase == "preflight":
            if plan is None or source_root is None or out is None:
                raise ContractError(
                    "preflight requires --plan, --source-root, and --out"
                )
            payload = _json.loads(plan.read_text(encoding="utf-8"))
            result = preflight_experiment(
                plan=payload,
                source_root=source_root,
                memory_base_url=memory_base_url,
                scillm_base_url=scillm_base_url,
                tau_root=tau_root,
                experiment_root=out,
                plan_file_sha256=file_sha256(plan),
            )
            out.mkdir(parents=True, exist_ok=True)
            (out / "memory-ablation-preflight-receipt.json").write_text(
                _json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        elif normalized_phase == "run":
            if plan is None or source_root is None or out is None:
                raise ContractError("run requires --plan, --source-root, and --out")
            result = run_experiment(
                plan_path=plan,
                source_root=source_root,
                out_dir=out,
                memory_base_url=memory_base_url,
                scillm_base_url=scillm_base_url,
                tau_root=tau_root,
                resume=resume,
            )
        elif normalized_phase == "aggregate":
            if plan is None or out is None:
                raise ContractError("aggregate requires --plan and --out")
            result = aggregate_experiment(
                plan_path=plan,
                experiment_root=out,
                out_path=out / "memory-ablation-result.json",
            )
        else:
            raise ContractError(
                f"unsupported phase {phase!r}; expected plan, validate, preflight, run, or aggregate"
            )
    except (ContractError, _json.JSONDecodeError) as exc:
        console.print(f"[red]Battle V15 memory ablation blocked:[/red]\n{exc}")
        raise typer.Exit(1) from exc

    console.print_json(data=result)
    if normalized_phase in {"run", "aggregate"} and result.get("status") != "PASS":
        raise typer.Exit(1)


@app.command("live-tau-child-dag-canary")
def live_tau_child_dag_canary(
    battle_id: str = typer.Argument(
        "battle-004", help="Battle id for the live Tau child DAG canary."
    ),
    out: Path = typer.Option(
        ..., "--out", help="Output directory for live Tau canary artifacts."
    ),
    spawn_architect_proof: Path = typer.Option(
        ...,
        "--spawn-architect-proof",
        exists=True,
        readable=True,
        help="Spawn Architect proof directory or spawn-architect-receipt.json.",
    ),
    tau_root: Path = typer.Option(
        Path("/home/graham/workspace/experiments/tau"),
        "--tau-root",
        help="Existing local Tau runtime checkout.",
    ),
    timeout_seconds: int = typer.Option(
        900,
        "--timeout-seconds",
        min=30,
        help="Timeout for the real Tau DAG invocation.",
    ),
):
    """Attempt PR3 live Tau child DAG execution without fixture fallback."""
    import json as _json

    from .live_tau_child_dag_canary import run_live_tau_child_dag_canary

    receipt = run_live_tau_child_dag_canary(
        battle_id=battle_id,
        out_dir=out,
        spawn_architect_proof=spawn_architect_proof,
        tau_root=tau_root,
        timeout_seconds=timeout_seconds,
    )
    print(
        _json.dumps(
            {
                "status": receipt.get("status"),
                "schema": receipt.get("schema"),
                "battle_id": battle_id,
                "out": str(out),
                "proof_mode": receipt.get("proof_mode"),
                "live": receipt.get("live"),
                "agentic": receipt.get("agentic"),
                "fixture_fallback_used": receipt.get("fixture_fallback_used"),
                "tau_execution": receipt.get("tau_execution"),
                "tau_receipt_status": receipt.get("tau_receipt_status"),
                "reason": receipt.get("reason"),
                "missing_tau_artifacts": receipt.get("missing_tau_artifacts"),
                "judge_verified_exploits": (receipt.get("scoreboard") or {}).get(
                    "judge_verified_exploits"
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if receipt.get("status") == "FAIL":
        raise typer.Exit(1)


@app.command("normalize-proof-card-fixture")
def normalize_proof_card_fixture(
    live_tau_canary: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="PR3b live Tau canary directory or live-tau-child-dag-canary-receipt.json.",
    ),
    out: Path = typer.Option(
        ..., "--out", help="Output battle.normalized_proof_card_fixture.json path."
    ),
):
    """Normalize backend PR3b receipts into a stable proof-card fixture for UX."""
    from .proof_card_fixture import normalize_pr3b_proof_card_fixture

    fixture = normalize_pr3b_proof_card_fixture(
        live_tau_canary=live_tau_canary, out=out
    )
    console.print_json(
        data={
            "status": fixture.get("status"),
            "schema": fixture.get("schema"),
            "proof_card_kind": fixture.get("proof_card_kind"),
            "battle_id": fixture.get("battle_id"),
            "out": str(out),
            "node_status": fixture.get("node_status"),
            "may_claim": fixture.get("claim_boundary", {}).get("may_claim"),
            "must_not_claim": fixture.get("claim_boundary", {}).get("must_not_claim"),
        }
    )


@app.command("validate-proof-card-fixture")
def validate_proof_card_fixture(
    fixture: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="battle.normalized_proof_card_fixture.v1 JSON fixture.",
    ),
):
    """Validate a normalized proof-card fixture."""
    from .proof_card_fixture import validate_normalized_proof_card_fixture_path

    report = validate_normalized_proof_card_fixture_path(fixture)
    console.print_json(data=report)


@app.command("normalize-music-fixture")
def normalize_music_fixture_command(
    source_fixture: Path = typer.Argument(..., exists=True, readable=True),
    catalog: Path = typer.Option(..., "--catalog", exists=True, readable=True),
    out: Path = typer.Option(..., "--out"),
    public_out: Optional[Path] = typer.Option(None, "--public-out"),
    public_audio_root: Path = typer.Option(..., "--public-audio-root"),
    generated_at: Optional[str] = typer.Option(None, "--generated-at"),
):
    """Promote receipt-backed music assets and publish a normalized schedule fixture."""
    from .normalized_music_fixture import normalize_music_fixture

    fixture = normalize_music_fixture(
        source_fixture=source_fixture,
        catalog=catalog,
        out_dir=out,
        public_out_dir=public_out,
        public_audio_root=public_audio_root,
        generated_at=generated_at,
    )
    console.print_json(
        data={
            "status": fixture["status"],
            "schema": fixture["schema"],
            "fixture_id": fixture["fixture_id"],
            "events_present": fixture["events_present"],
            "events_not_emitted": fixture["events_not_emitted"],
        }
    )


@app.command("validate-music-fixture")
def validate_music_fixture_command(
    fixture: Path = typer.Argument(
        ..., exists=True, file_okay=True, dir_okay=False, readable=True
    ),
):
    """Validate a normalized Battle music fixture."""
    from .normalized_music_fixture import validate_normalized_music_fixture_path

    console.print_json(data=validate_normalized_music_fixture_path(fixture))


@app.command("normalize-synthesis-fixture")
def normalize_synthesis_fixture(
    live_tau_canary: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="PR3c live Tau canary directory or live-tau-child-dag-canary-receipt.json.",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output directory for battle.normalized_synthesis_fixture.json.",
    ),
    public_out: Optional[Path] = typer.Option(
        None,
        "--public-out",
        help="Optional public fixture directory for spectator consumption.",
    ),
    generated_at: Optional[str] = typer.Option(
        None, "--generated-at", help="Optional deterministic generated_at timestamp."
    ),
):
    """Normalize backend PR3c provider authorship receipts into a stable synthesis fixture for UX."""
    from .normalized_synthesis_fixture import normalize_pr3c_synthesis_fixture

    fixture = normalize_pr3c_synthesis_fixture(
        live_tau_canary=live_tau_canary,
        out_dir=out,
        public_out_dir=public_out,
        generated_at=generated_at,
    )
    console.print_json(
        data={
            "status": fixture.get("status"),
            "schema": fixture.get("schema"),
            "fixture_kind": fixture.get("fixture_kind"),
            "battle_id": fixture.get("battle_id"),
            "out": str(out / "battle.normalized_synthesis_fixture.json"),
            "public_out": str(public_out / "battle.normalized_synthesis_fixture.json")
            if public_out
            else None,
            "node_status": fixture.get("node_status"),
            "provider_live": fixture.get("provider_live"),
            "execution_boundary": fixture.get("execution_boundary"),
            "may_claim": fixture.get("claim_boundary", {}).get("may_claim"),
            "must_not_claim": fixture.get("claim_boundary", {}).get("must_not_claim"),
        }
    )


@app.command("validate-synthesis-fixture")
def validate_synthesis_fixture(
    fixture: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="battle.normalized_synthesis_fixture.v1 JSON fixture.",
    ),
):
    """Validate a normalized synthesis fixture."""
    from .normalized_synthesis_fixture import validate_normalized_synthesis_fixture_path

    report = validate_normalized_synthesis_fixture_path(fixture)
    console.print_json(data=report)


@app.command("normalize-compile-fixture")
def normalize_compile_fixture(
    live_tau_canary: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="PR3d live Tau canary directory or live-tau-child-dag-canary-receipt.json.",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output directory for battle.normalized_compile_fixture.json.",
    ),
    public_out: Optional[Path] = typer.Option(
        None,
        "--public-out",
        help="Optional public fixture directory for spectator consumption.",
    ),
    generated_at: Optional[str] = typer.Option(
        None, "--generated-at", help="Optional deterministic generated_at timestamp."
    ),
):
    """Normalize backend PR3d compile-repair receipts into a stable compile fixture for UX."""
    from .normalized_compile_fixture import normalize_pr3d_compile_fixture

    fixture = normalize_pr3d_compile_fixture(
        live_tau_canary=live_tau_canary,
        out_dir=out,
        public_out_dir=public_out,
        generated_at=generated_at,
    )
    console.print_json(
        data={
            "status": fixture.get("status"),
            "schema": fixture.get("schema"),
            "fixture_kind": fixture.get("fixture_kind"),
            "battle_id": fixture.get("battle_id"),
            "out": str(out / "battle.normalized_compile_fixture.json"),
            "public_out": str(public_out / "battle.normalized_compile_fixture.json")
            if public_out
            else None,
            "node_status": fixture.get("node_status"),
            "compile": fixture.get("compile"),
            "repair": fixture.get("repair"),
            "execution_boundary": fixture.get("execution_boundary"),
            "may_claim": fixture.get("claim_boundary", {}).get("may_claim"),
            "must_not_claim": fixture.get("claim_boundary", {}).get("must_not_claim"),
        }
    )


@app.command("validate-compile-fixture")
def validate_compile_fixture(
    fixture: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="battle.normalized_compile_fixture.v1 JSON fixture.",
    ),
):
    """Validate a normalized compile fixture."""
    from .normalized_compile_fixture import validate_normalized_compile_fixture_path

    report = validate_normalized_compile_fixture_path(fixture)
    console.print_json(data=report)


@app.command("normalize-runtime-judge-fixture")
def normalize_runtime_judge_fixture(
    proof_dir: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="Combiner/runtime proof directory or run-receipt.json.",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output directory for battle.normalized_runtime_judge_fixture.json.",
    ),
    public_out: Optional[Path] = typer.Option(
        None,
        "--public-out",
        help="Optional public fixture directory for spectator consumption.",
    ),
    generated_at: Optional[str] = typer.Option(
        None, "--generated-at", help="Optional deterministic generated_at timestamp."
    ),
):
    """Normalize backend runtime and Judge boundary receipts into a stable UX fixture."""
    from .normalized_runtime_judge_fixture import (
        normalize_runtime_judge_fixture as _normalize,
    )

    fixture = _normalize(
        proof_dir=proof_dir,
        out_dir=out,
        public_out_dir=public_out,
        generated_at=generated_at,
    )
    console.print_json(
        data={
            "status": fixture.get("status"),
            "schema": fixture.get("schema"),
            "fixture_kind": fixture.get("fixture_kind"),
            "battle_id": fixture.get("battle_id"),
            "out": str(out / "battle.normalized_runtime_judge_fixture.json"),
            "public_out": str(
                public_out / "battle.normalized_runtime_judge_fixture.json"
            )
            if public_out
            else None,
            "runtime_summary": fixture.get("runtime", {}).get("summary"),
            "judge": fixture.get("judge"),
            "may_claim": fixture.get("claim_boundary", {}).get("may_claim"),
            "must_not_claim": fixture.get("claim_boundary", {}).get("must_not_claim"),
        }
    )


@app.command("validate-runtime-judge-fixture")
def validate_runtime_judge_fixture(
    fixture: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="battle.normalized_runtime_judge_fixture.v1 JSON fixture.",
    ),
):
    """Validate a normalized runtime/Judge fixture."""
    from .normalized_runtime_judge_fixture import (
        validate_normalized_runtime_judge_fixture_path,
    )

    report = validate_normalized_runtime_judge_fixture_path(fixture)
    console.print_json(data=report)


@app.command("normalize-adaptive-lineage-fixture")
def normalize_adaptive_lineage_fixture(
    bundle_dir: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="Adaptive-lineage qualification bundle (holds adaptive-lineage-qualification.json + receipts/).",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output path for the normalized battle.adaptive_lineage_mechanics_fixture.v1 JSON.",
    ),
    data_source: Optional[str] = typer.Option(
        None,
        "--data-source",
        help="Override data_source (recorded | live). Defaults to the bundle provenance.json — never hardcoded.",
    ),
    generated_at: Optional[str] = typer.Option(
        None, "--generated-at", help="Optional deterministic generated_at timestamp."
    ),
):
    """Normalize a battle.adaptive_lineage_qualification.v1 bundle into a MECHANICS-FIRST spectator fixture."""
    import json as _json

    from .adaptive_lineage_mechanics_fixture import (
        normalize_adaptive_lineage_bundle,
        validate_normalized_adaptive_lineage_fixture,
    )

    fixture = normalize_adaptive_lineage_bundle(
        bundle_dir, data_source=data_source, generated_at=generated_at
    )
    report = validate_normalized_adaptive_lineage_fixture(fixture)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        _json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    console.print_json(
        data={
            "status": report["status"],
            "schema": fixture["schema"],
            "battle_id": fixture["battle_id"],
            "data_source": fixture["data_source"],
            "qualification_status": fixture["qualification"]["status"],
            "selected_id": fixture["selection"]["selected_id"],
            "deciding_criterion": fixture["selection"]["deciding_criterion"],
            "node_count": report["node_count"],
            "edge_count": report["edge_count"],
            "problems": report["problems"],
            "out": str(out),
        }
    )
    if report["status"] != "PASS":
        raise typer.Exit(1)


@app.command("validate-adaptive-lineage-fixture")
def validate_adaptive_lineage_fixture(
    fixture: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="battle.adaptive_lineage_mechanics_fixture.v1 JSON fixture.",
    ),
):
    """Validate a normalized adaptive-lineage mechanics fixture."""
    from .adaptive_lineage_mechanics_fixture import (
        validate_normalized_adaptive_lineage_fixture_path,
    )

    console.print_json(data=validate_normalized_adaptive_lineage_fixture_path(fixture))


@app.command("normalize-population-fixture")
def normalize_population_fixture(
    proof_dir: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="Combiner/population proof directory or run-receipt.json.",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output directory for battle.normalized_population_fixture.json.",
    ),
    public_out: Optional[Path] = typer.Option(
        None,
        "--public-out",
        help="Optional public fixture directory for spectator consumption.",
    ),
    generated_at: Optional[str] = typer.Option(
        None, "--generated-at", help="Optional deterministic generated_at timestamp."
    ),
):
    """Normalize backend specimen population receipts into a stable UX fixture."""
    from .normalized_population_fixture import (
        normalize_population_fixture as _normalize,
    )

    fixture = _normalize(
        proof_dir=proof_dir,
        out_dir=out,
        public_out_dir=public_out,
        generated_at=generated_at,
    )
    console.print_json(
        data={
            "status": fixture.get("status"),
            "schema": fixture.get("schema"),
            "fixture_kind": fixture.get("fixture_kind"),
            "battle_id": fixture.get("battle_id"),
            "out": str(out / "battle.normalized_population_fixture.json"),
            "public_out": str(public_out / "battle.normalized_population_fixture.json")
            if public_out
            else None,
            "campaign": fixture.get("campaign"),
            "specimen_count": len(fixture.get("specimen_cards", [])),
            "generation_count": len(fixture.get("generation_axis", [])),
            "lineage_edge_count": len(fixture.get("lineage_edges", [])),
            "may_claim": fixture.get("claim_boundary", {}).get("may_claim"),
            "must_not_claim": fixture.get("claim_boundary", {}).get("must_not_claim"),
        }
    )


@app.command("validate-population-fixture")
def validate_population_fixture(
    fixture: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="battle.normalized_population_fixture.v1 JSON fixture.",
    ),
):
    """Validate a normalized population fixture."""
    from .normalized_population_fixture import (
        validate_normalized_population_fixture_path,
    )

    report = validate_normalized_population_fixture_path(fixture)
    console.print_json(data=report)


@app.command("normalize-genetic-pixi-fixture")
def normalize_genetic_pixi_fixture(
    source_dir: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="Battle skill directory containing PR3c/PR3d/PR4/PR5 normalized source fixtures.",
    ),
    out: Path = typer.Option(
        ..., "--out", help="Output directory for battle.normalized_ux_fixture.json."
    ),
    public_out: Optional[Path] = typer.Option(
        None,
        "--public-out",
        help="Optional public fixture directory for spectator consumption.",
    ),
    generated_at: Optional[str] = typer.Option(
        None, "--generated-at", help="Optional deterministic generated_at timestamp."
    ),
):
    """Normalize genetic lifecycle receipts into a Pixi replay UX fixture."""
    from .normalized_genetic_pixi_fixture import (
        normalize_genetic_pixi_fixture as _normalize,
    )

    fixture = _normalize(
        source_dir=source_dir,
        out_dir=out,
        public_out_dir=public_out,
        generated_at=generated_at,
    )
    genetic = fixture.get("genetic_lifecycle", {})
    console.print_json(
        data={
            "status": fixture.get("status"),
            "schema": fixture.get("schema"),
            "fixture_id": genetic.get("fixture_id"),
            "battle_id": fixture.get("battle_id"),
            "route": genetic.get("route"),
            "out": str(out / "battle.normalized_ux_fixture.json"),
            "public_out": str(public_out / "battle.normalized_ux_fixture.json")
            if public_out
            else None,
            "present_event_types": genetic.get("present_event_types"),
            "not_emitted_event_types": genetic.get("not_emitted_event_types"),
            "must_not_claim": genetic.get("claim_boundary", {}).get("must_not_claim"),
        }
    )


@app.command("validate-genetic-pixi-fixture")
def validate_genetic_pixi_fixture(
    fixture: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="battle.normalized_ux_fixture.v1 JSON fixture with genetic_lifecycle metadata.",
    ),
):
    """Validate a normalized genetic lifecycle Pixi fixture."""
    from .normalized_genetic_pixi_fixture import (
        validate_normalized_genetic_pixi_fixture_path,
    )

    report = validate_normalized_genetic_pixi_fixture_path(fixture)
    console.print_json(data=report)


@app.command("validate-ux-handoff-summary")
def validate_ux_handoff_summary(
    summary: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Battle backend UX JSON handoff summary.",
    ),
):
    """Validate the backend UX handoff summary and its referenced JSON fixtures."""
    from .ux_contract_validator import ContractError, validate_handoff_summary_path

    try:
        report = validate_handoff_summary_path(summary)
    except ContractError as exc:
        console.print(f"[red]Battle UX handoff summary invalid:[/red]\n{exc}")
        raise typer.Exit(1) from exc
    console.print_json(data=report)


@app.command("publish-live-transport-contract")
def publish_live_transport_contract(
    out: Path = typer.Option(
        ..., "--out", help="Output directory for battle.live_transport_contract.json."
    ),
    public_out: Optional[Path] = typer.Option(
        None,
        "--public-out",
        help="Optional public fixture directory for spectator consumption.",
    ),
    generated_at: Optional[str] = typer.Option(
        None, "--generated-at", help="Optional deterministic generated_at timestamp."
    ),
):
    """Publish the UX8 SSE live transport contract."""
    from .live_transport_contract import publish_live_transport_contract as _publish

    contract = _publish(
        out_dir=out, public_out_dir=public_out, generated_at=generated_at
    )
    console.print_json(
        data={
            "status": contract.get("status"),
            "schema": contract.get("schema"),
            "battle_id": contract.get("battle_id"),
            "run_id": contract.get("run_id"),
            "live": contract.get("live"),
            "snapshot_endpoint": contract.get("initial_snapshot", {}).get("endpoint"),
            "sse_endpoint": contract.get("transport", {}).get("endpoint"),
            "out": str(out / "battle.live_transport_contract.json"),
            "public_out": str(public_out / "battle.live_transport_contract.json")
            if public_out
            else None,
            "must_not_claim": contract.get("claim_boundary", {}).get("must_not_claim"),
        }
    )


@app.command("validate-live-transport-contract")
def validate_live_transport_contract(
    contract: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="battle.live_transport_contract.v1 JSON contract.",
    ),
):
    """Validate a UX8 live transport contract."""
    from .live_transport_contract import validate_live_transport_contract_path

    report = validate_live_transport_contract_path(contract)
    console.print_json(data=report)


@app.command("serve-live-transport")
def serve_live_transport(
    fixture: Path = typer.Option(
        Path(
            "spectator/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json"
        ),
        "--fixture",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Normalized Battle UX fixture used as the live transport source.",
    ),
    battle_id: str = typer.Option(
        "battle-004", "--battle-id", help="Battle id for the live endpoints."
    ),
    host: str = typer.Option("127.0.0.1", "--host", help="HTTP bind host."),
    port: int = typer.Option(8765, "--port", help="HTTP bind port."),
    websocket_port: int = typer.Option(
        8766,
        "--websocket-port",
        help="Paired loopback WebSocket bind port advertised from /healthz.",
    ),
):
    """Serve executable UX8 snapshot/SSE/WebSocket endpoints from a normalized fixture."""
    from .live_transport_server import (
        build_live_transport_source,
        serve_live_transport as _serve,
    )

    source = build_live_transport_source(fixture_path=fixture, battle_id=battle_id)
    console.print_json(
        data={
            "schema": "battle.live_transport_server_start.v1",
            "status": "SERVING",
            "mocked": False,
            "live": "local_http_sse_websocket_adapter",
            "battle_id": battle_id,
            "run_id": source.run_id,
            "snapshot_endpoint": source.snapshot_endpoint,
            "sse_endpoint": source.events_endpoint,
            "websocket_endpoint": source.websocket_endpoint,
            "event_count": len(source.events),
            "host": host,
            "port": port,
            "websocket_port": websocket_port,
            "claim_boundary": {
                "does_not_prove": [
                    "production deployment",
                    "production WebSocket TLS/auth/fanout/reconnect behavior",
                    "exploit success",
                    "Blue outcome",
                    "Judge success",
                ]
            },
        }
    )
    _serve(
        fixture_path=fixture,
        battle_id=battle_id,
        host=host,
        port=port,
        websocket_port=websocket_port,
    )


@app.command("prove-live-transport-server")
def prove_live_transport_server(
    fixture: Path = typer.Option(
        Path(
            "spectator/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json"
        ),
        "--fixture",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Normalized Battle UX fixture used as the live transport source.",
    ),
    battle_id: str = typer.Option(
        "battle-004", "--battle-id", help="Battle id for the live endpoints."
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output directory for the executable live transport proof receipt.",
    ),
):
    """Prove UX8 snapshot/SSE endpoints execute locally and preserve claim boundaries."""
    from .live_transport_server import prove_live_transport_server as _prove

    receipt = _prove(fixture_path=fixture, battle_id=battle_id, out_dir=out)
    console.print_json(data=receipt)


@app.command("prove-production-websocket-transport")
def prove_production_websocket_transport(
    fixture: Path = typer.Option(
        ...,
        "--fixture",
        help="Normalized UX fixture for the production-shaped WebSocket proof.",
    ),
    battle_id: str = typer.Option(
        "battle-004",
        "--battle-id",
        help="Battle id for the production-shaped WebSocket proof.",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output directory for the production-shaped WebSocket proof receipt.",
    ),
    auth_token: str = typer.Option(
        "battle-local-production-websocket-proof-token",
        "--auth-token",
        help="Local proof token. Stored only as SHA-256 in the receipt.",
    ),
):
    """Prove local WebSocket auth, reconnect, and fanout gates."""
    from .live_transport_server import prove_production_websocket_transport as _prove

    receipt = _prove(
        fixture_path=fixture,
        battle_id=battle_id,
        out_dir=out,
        auth_token=auth_token,
    )
    console.print_json(data=receipt)


@app.command("prove-packaged-deployment-smoke")
def prove_packaged_deployment_smoke(
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output directory for the packaged local deployment smoke receipt.",
    ),
    repo_root: Path = typer.Option(
        Path(__file__).resolve().parents[4],
        "--repo-root",
        help="agent-skills repository root to archive from.",
    ),
    fixture: Path = typer.Option(
        Path(
            "spectator/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json"
        ),
        "--fixture",
        help="Fixture path relative to packaged skills/battle.",
    ),
    interaction_manifest: Path = typer.Option(
        Path(
            "local/working-frontend-backend-20260729/test-interactions-live-after-patch/live-route-unique-hash-manifest.json"
        ),
        "--interaction-manifest",
        help="Interaction manifest path relative to the live skills/battle root.",
    ),
    battle_id: str = typer.Option(
        "battle-004", "--battle-id", help="Battle id for the packaged smoke."
    ),
):
    """Prove a Git-archived local package can launch Battle frontend/backend."""
    from .packaged_deployment_smoke import prove_packaged_deployment_smoke as _prove

    receipt = _prove(
        out_dir=out,
        repo_root=repo_root,
        fixture=fixture,
        interaction_manifest=interaction_manifest,
        battle_id=battle_id,
    )
    console.print_json(data=receipt)


@app.command("prove-containerized-deployment-smoke")
def prove_containerized_deployment_smoke(
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output directory for the containerized local deployment smoke receipt.",
    ),
    repo_root: Path = typer.Option(
        Path(__file__).resolve().parents[4],
        "--repo-root",
        help="agent-skills repository root to archive from.",
    ),
    fixture: Path = typer.Option(
        Path(
            "spectator/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json"
        ),
        "--fixture",
        help="Fixture path relative to packaged skills/battle.",
    ),
    interaction_manifest: Path = typer.Option(
        Path(
            "local/working-frontend-backend-20260729/test-interactions-live-after-patch/live-route-unique-hash-manifest.json"
        ),
        "--interaction-manifest",
        help="Interaction manifest path relative to the live skills/battle root.",
    ),
    battle_id: str = typer.Option(
        "battle-004", "--battle-id", help="Battle id for the containerized smoke."
    ),
):
    """Prove a Git-archived Battle package can run frontend/backend in Docker."""
    from .containerized_deployment_smoke import (
        prove_containerized_deployment_smoke as _prove,
    )

    receipt = _prove(
        out_dir=out,
        repo_root=repo_root,
        fixture=fixture,
        interaction_manifest=interaction_manifest,
        battle_id=battle_id,
    )
    console.print_json(data=receipt)


@app.command("validate-production-readiness")
def validate_production_readiness(
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output directory for the fail-closed production readiness contract receipt.",
    ),
    containerized_receipt: Path = typer.Option(
        ...,
        "--containerized-receipt",
        help="Required battle.containerized_deployment_smoke.v1 receipt.",
    ),
    packaged_receipt: Optional[Path] = typer.Option(
        None,
        "--packaged-receipt",
        help="Optional battle.packaged_deployment_smoke.v1 receipt.",
    ),
    local_deployment_alignment_receipt: Optional[Path] = typer.Option(
        None,
        "--local-deployment-alignment-receipt",
        help="Optional battle.local_deployment_alignment_proof.v1 receipt.",
    ),
    production_infrastructure_receipt: Optional[Path] = typer.Option(
        None,
        "--production-infrastructure-receipt",
        help="Optional external production infrastructure deployment receipt.",
    ),
    production_websocket_receipt: Optional[Path] = typer.Option(
        None,
        "--production-websocket-receipt",
        help="Optional production WebSocket TLS/auth/fanout/reconnect receipt.",
    ),
    unbounded_swarm_receipt: Optional[Path] = typer.Option(
        None,
        "--unbounded-swarm-receipt",
        help="Optional unbounded swarm execution receipt.",
    ),
    repo_root: Path = typer.Option(
        Path(__file__).resolve().parents[4],
        "--repo-root",
        help="agent-skills repository root.",
    ),
    fail_on_blocked: bool = typer.Option(
        True,
        "--fail-on-blocked/--no-fail-on-blocked",
        help="Exit nonzero when production readiness is blocked.",
    ),
):
    """Fail closed unless local and external production readiness receipts exist."""
    from .production_readiness_contract import (
        validate_production_readiness as _validate,
    )

    receipt = _validate(
        out_dir=out,
        repo_root=repo_root,
        containerized_receipt=containerized_receipt,
        packaged_receipt=packaged_receipt,
        local_deployment_alignment_receipt=local_deployment_alignment_receipt,
        production_infrastructure_receipt=production_infrastructure_receipt,
        production_websocket_receipt=production_websocket_receipt,
        unbounded_swarm_receipt=unbounded_swarm_receipt,
    )
    console.print_json(data=receipt)
    if receipt.get("status") == "FAIL":
        raise typer.Exit(1)
    if fail_on_blocked and receipt.get("status") == "BLOCKED":
        raise typer.Exit(2)


@app.command("prove-production-infrastructure-deployment")
def prove_production_infrastructure_deployment(
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output directory for the production infrastructure deployment receipt.",
    ),
    frontend_url: str = typer.Option(
        ...,
        "--frontend-url",
        help="Production HTTPS frontend URL.",
    ),
    backend_health_url: str = typer.Option(
        ...,
        "--backend-health-url",
        help="Production HTTPS backend health URL.",
    ),
    websocket_url: str = typer.Option(
        ...,
        "--websocket-url",
        help="Production WSS Battle live WebSocket URL.",
    ),
    commit: str = typer.Option(
        ...,
        "--commit",
        help="Deployed git commit.",
    ),
    release_id: str = typer.Option(
        ...,
        "--release-id",
        help="Production release or deployment identifier.",
    ),
    secret_source: str = typer.Option(
        ...,
        "--secret-source",
        help="Secret manager/config source name, not the secret value.",
    ),
    websocket_bearer_token_env: Optional[str] = typer.Option(
        None,
        "--websocket-bearer-token-env",
        help="Optional environment variable containing the WebSocket bearer token.",
    ),
    timeout_s: float = typer.Option(
        5.0,
        "--timeout-s",
        min=1.0,
        max=60.0,
        help="Network timeout for production probes.",
    ),
    allow_private_targets: bool = typer.Option(
        False,
        "--allow-private-targets/--reject-private-targets",
        help="Allow private network targets. Disabled by default for production proof.",
    ),
    fail_on_blocked: bool = typer.Option(
        True,
        "--fail-on-blocked/--no-fail-on-blocked",
        help="Exit nonzero when the production infrastructure probe is blocked.",
    ),
):
    """Probe production HTTPS/WSS infrastructure and emit a fail-closed receipt."""
    from .production_infrastructure_probe import (
        prove_production_infrastructure_deployment as _prove,
    )

    websocket_bearer_token = (
        os.environ.get(websocket_bearer_token_env)
        if websocket_bearer_token_env
        else None
    )
    receipt = _prove(
        out_dir=out,
        frontend_url=frontend_url,
        backend_health_url=backend_health_url,
        websocket_url=websocket_url,
        commit=commit,
        release_id=release_id,
        secret_source=secret_source,
        websocket_bearer_token=websocket_bearer_token,
        timeout_s=timeout_s,
        allow_private_targets=allow_private_targets,
    )
    console.print_json(data=receipt)
    if fail_on_blocked and receipt.get("status") != "PASS":
        raise typer.Exit(2)


@app.command("prove-local-deployment-alignment")
def prove_local_deployment_alignment(
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output directory for the local deployment alignment receipt.",
    ),
    repo_root: Path = typer.Option(
        Path(__file__).resolve().parents[4],
        "--repo-root",
        help="agent-skills repository root.",
    ),
    deployment_root: Path = typer.Option(
        Path("/mnt/storage12tb/deployments/agent-skills"),
        "--deployment-root",
        help="Local deployment root containing releases/ and current.",
    ),
    commit: str = typer.Option(
        "HEAD",
        "--commit",
        help="Git commit/ref to cut and align. Must match origin/main.",
    ),
    activate: bool = typer.Option(
        False,
        "--activate/--no-activate",
        help="Atomically repoint deployment-root/current to the cut release.",
    ),
    authorized_by: Optional[str] = typer.Option(
        None,
        "--authorized-by",
        help="Required authorization string when --activate is used.",
    ),
):
    """Prove local deployment release alignment without claiming production infra."""
    from .deployment_alignment_proof import prove_local_deployment_alignment as _prove

    receipt = _prove(
        out_dir=out,
        repo_root=repo_root,
        deployment_root=deployment_root,
        commit=commit,
        activate=activate,
        authorized_by=authorized_by,
    )
    console.print_json(data=receipt)


@app.command("prove-unbounded-swarm-execution")
def prove_unbounded_swarm_execution(
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output directory for the Docker-backed swarm execution proof.",
    ),
    worker_count: int = typer.Option(
        12,
        "--worker-count",
        help="Number of local Docker swarm workers to execute.",
    ),
    min_concurrent_observed: int = typer.Option(
        4,
        "--min-concurrent-observed",
        help="Minimum observed concurrent workers required for PASS.",
    ),
    docker_image: str = typer.Option(
        "python:3.12-slim",
        "--docker-image",
        help="Docker image used for each isolated swarm worker.",
    ),
    per_worker_timeout_s: int = typer.Option(
        30,
        "--per-worker-timeout-s",
        help="Per-worker Docker timeout in seconds.",
    ),
):
    """Prove a dynamic Docker-backed Battle swarm envelope beyond fixed 2 workers."""
    from .swarm_execution_proof import prove_unbounded_swarm_execution as _prove

    receipt = _prove(
        out_dir=out,
        worker_count=worker_count,
        docker_image=docker_image,
        per_worker_timeout_s=per_worker_timeout_s,
        min_concurrent_observed=min_concurrent_observed,
    )
    console.print_json(data=receipt)


@app.command("prove-transport-safety-smoke")
def prove_transport_safety_smoke(
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output directory for the local transport safety smoke receipt.",
    ),
    battle_root: Path = typer.Option(
        Path(__file__).resolve().parents[2],
        "--battle-root",
        help="skills/battle directory containing spectator and fixtures.",
    ),
    fixture: Path = typer.Option(
        Path(
            "spectator/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json"
        ),
        "--fixture",
        help="Fixture path relative to skills/battle.",
    ),
    battle_id: str = typer.Option(
        "battle-004", "--battle-id", help="Battle id for the transport safety smoke."
    ),
):
    """Prove existing local HTTP/SSE transport safety gates and frontend reducers."""
    from .transport_safety_smoke import prove_transport_safety_smoke as _prove

    receipt = _prove(
        out_dir=out,
        battle_root=battle_root,
        fixture=fixture,
        battle_id=battle_id,
    )
    console.print_json(data=receipt)


@app.command("export-ux-handoff-summary")
def export_ux_handoff_summary(
    summary: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Battle backend UX JSON handoff summary to refresh from current fixture JSON.",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output refreshed Battle backend UX handoff summary JSON path.",
    ),
):
    """Refresh fixture-derived fields in the backend UX handoff summary."""
    import json as _json

    from .ux_contract_validator import (
        ContractError,
        export_handoff_summary_from_current_fixtures,
    )

    try:
        payload = export_handoff_summary_from_current_fixtures(summary)
    except ContractError as exc:
        console.print(f"[red]Battle UX handoff summary export invalid:[/red]\n{exc}")
        raise typer.Exit(1) from exc

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        _json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    parent = (
        payload.get("authoritative_parent_spawn_fixture")
        if isinstance(payload.get("authoritative_parent_spawn_fixture"), dict)
        else {}
    )
    timeline = (
        parent.get("timeline") if isinstance(parent.get("timeline"), dict) else {}
    )
    playhead = (
        timeline.get("playhead") if isinstance(timeline.get("playhead"), dict) else {}
    )
    console.print_json(
        data={
            "status": "PASS",
            "out": str(out),
            "schema": payload.get("schema"),
            "battle_id": payload.get("battle_id"),
            "parent_spawn_status": parent.get("status"),
            "child_spawn_count": parent.get("scoreboard", {}).get("child_spawn_count")
            if isinstance(parent.get("scoreboard"), dict)
            else None,
            "playhead_current_x": playhead.get("current_x"),
            "mocked": parent.get("mocked"),
            "live_source": parent.get("live_source"),
        }
    )


@app.command("resolve-ux-renderer-fixture")
def resolve_ux_renderer_fixture(
    summary: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Battle backend UX JSON handoff summary.",
    ),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        help="Optional path to write the schema-validated renderer fixture resolution JSON.",
    ),
):
    """Resolve the normalized JSON fixture the UX renderer should load."""
    import json as _json

    from .ux_contract_validator import (
        ContractError,
        resolve_renderer_fixture_from_summary_path,
    )

    try:
        payload = resolve_renderer_fixture_from_summary_path(summary)
    except ContractError as exc:
        console.print(f"[red]Battle UX handoff summary invalid:[/red]\n{exc}")
        raise typer.Exit(1) from exc

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            _json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    console.print_json(data=payload)


@app.command("validate-ux-renderer-fixture-resolution")
def validate_ux_renderer_fixture_resolution(
    resolution: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Resolved Battle UX renderer fixture JSON.",
    ),
):
    """Validate the concrete JSON artifact that tells the UX which fixture to render."""
    import json as _json

    from .ux_contract_validator import (
        ContractError,
        validate_renderer_fixture_resolution,
        validate_renderer_fixture_resolution_schema,
    )

    try:
        payload = _json.loads(resolution.read_text(encoding="utf-8"))
        validate_renderer_fixture_resolution_schema(payload)
        validate_renderer_fixture_resolution(payload)
    except (_json.JSONDecodeError, ContractError) as exc:
        console.print(
            f"[red]Battle UX renderer fixture resolution invalid:[/red]\n{exc}"
        )
        raise typer.Exit(1) from exc

    console.print_json(
        data={
            "status": "PASS",
            "resolution": str(resolution),
            "schema": payload.get("schema"),
            "battle_id": payload.get("battle_id"),
            "normalized_json": payload.get("normalized_json"),
            "fixture_key": payload.get("fixture_key"),
            "fixture_status": payload.get("fixture_status"),
            "fixture_lineage_mode": payload.get("fixture_lineage_mode"),
            "fixture_child_spawn_count": payload.get("fixture_child_spawn_count"),
            "fixture_playhead_current_x": payload.get("fixture_playhead_current_x"),
            "mocked": payload.get("mocked"),
            "live_source": payload.get("live_source"),
        }
    )


@app.command("export-ux-renderer-bundle")
def export_ux_renderer_bundle(
    resolution: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Resolved Battle UX renderer fixture JSON.",
    ),
    out: Path = typer.Option(..., "--out", help="Output renderer bundle JSON path."),
):
    """Export one self-contained backend JSON bundle for the UX renderer."""
    import json as _json

    from .ux_contract_validator import (
        ContractError,
        export_renderer_bundle_from_resolution_path,
    )

    try:
        payload = export_renderer_bundle_from_resolution_path(resolution)
    except ContractError as exc:
        console.print(f"[red]Battle UX renderer bundle invalid:[/red]\n{exc}")
        raise typer.Exit(1) from exc

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        _json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    console.print_json(
        data={
            "status": "PASS",
            "out": str(out),
            "schema": payload.get("schema"),
            "battle_id": payload.get("fixture", {}).get("battle_id")
            if isinstance(payload.get("fixture"), dict)
            else None,
            "normalized_fixture_source": payload.get("normalized_fixture_source"),
            "fixture_key": payload.get("resolution", {}).get("fixture_key")
            if isinstance(payload.get("resolution"), dict)
            else None,
            "child_spawn_count": payload.get("resolution", {}).get(
                "fixture_child_spawn_count"
            )
            if isinstance(payload.get("resolution"), dict)
            else None,
            "playhead_current_x": payload.get("resolution", {}).get(
                "fixture_playhead_current_x"
            )
            if isinstance(payload.get("resolution"), dict)
            else None,
            "mocked": payload.get("resolution", {}).get("mocked")
            if isinstance(payload.get("resolution"), dict)
            else None,
        }
    )


@app.command("validate-ux-renderer-bundle")
def validate_ux_renderer_bundle(
    bundle: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Battle UX renderer bundle JSON.",
    ),
):
    """Validate a self-contained backend JSON bundle for the UX renderer."""
    import json as _json

    from .ux_contract_validator import ContractError, validate_renderer_bundle

    try:
        payload = _json.loads(bundle.read_text(encoding="utf-8"))
        validate_renderer_bundle(payload)
    except (_json.JSONDecodeError, ContractError) as exc:
        console.print(f"[red]Battle UX renderer bundle invalid:[/red]\n{exc}")
        raise typer.Exit(1) from exc

    console.print_json(
        data={
            "status": "PASS",
            "bundle": str(bundle),
            "schema": payload.get("schema"),
            "battle_id": payload.get("fixture", {}).get("battle_id")
            if isinstance(payload.get("fixture"), dict)
            else None,
            "normalized_fixture_source": payload.get("normalized_fixture_source"),
            "fixture_key": payload.get("resolution", {}).get("fixture_key")
            if isinstance(payload.get("resolution"), dict)
            else None,
            "child_spawn_count": payload.get("resolution", {}).get(
                "fixture_child_spawn_count"
            )
            if isinstance(payload.get("resolution"), dict)
            else None,
            "playhead_current_x": payload.get("resolution", {}).get(
                "fixture_playhead_current_x"
            )
            if isinstance(payload.get("resolution"), dict)
            else None,
            "mocked": payload.get("resolution", {}).get("mocked")
            if isinstance(payload.get("resolution"), dict)
            else None,
        }
    )


@app.command("export-ux-renderer-values")
def export_ux_renderer_values(
    bundle: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Battle UX renderer bundle JSON.",
    ),
    out: Path = typer.Option(
        ..., "--out", help="Output compact renderer values JSON path."
    ),
):
    """Export compact backend-owned values for the UX renderer."""
    import json as _json

    from .ux_contract_validator import (
        ContractError,
        export_renderer_values_from_bundle_path,
    )

    try:
        payload = export_renderer_values_from_bundle_path(bundle)
    except ContractError as exc:
        console.print(f"[red]Battle UX renderer values invalid:[/red]\n{exc}")
        raise typer.Exit(1) from exc

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        _json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    console.print_json(
        data={
            "status": "PASS",
            "out": str(out),
            "schema": payload.get("schema"),
            "battle_id": payload.get("battle_id"),
            "source_bundle": payload.get("source_bundle"),
            "source_fixture": payload.get("source_fixture"),
            "child_spawn_count": payload.get("scoreboard", {}).get("child_spawn_count")
            if isinstance(payload.get("scoreboard"), dict)
            else None,
            "playhead_current_x": payload.get("timeline", {})
            .get("playhead", {})
            .get("current_x")
            if isinstance(payload.get("timeline"), dict)
            and isinstance(payload.get("timeline", {}).get("playhead"), dict)
            else None,
            "mocked": payload.get("mocked"),
        }
    )


@app.command("validate-ux-renderer-values")
def validate_ux_renderer_values(
    values: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Compact Battle UX renderer values JSON.",
    ),
):
    """Validate compact backend-owned values for the UX renderer."""
    import json as _json

    from .ux_contract_validator import ContractError, validate_renderer_values

    try:
        payload = _json.loads(values.read_text(encoding="utf-8"))
        validate_renderer_values(payload, check_sources=True)
    except (_json.JSONDecodeError, ContractError) as exc:
        console.print(f"[red]Battle UX renderer values invalid:[/red]\n{exc}")
        raise typer.Exit(1) from exc

    console.print_json(
        data={
            "status": "PASS",
            "values": str(values),
            "schema": payload.get("schema"),
            "battle_id": payload.get("battle_id"),
            "source_bundle": payload.get("source_bundle"),
            "source_fixture": payload.get("source_fixture"),
            "child_spawn_count": payload.get("scoreboard", {}).get("child_spawn_count")
            if isinstance(payload.get("scoreboard"), dict)
            else None,
            "playhead_current_x": payload.get("timeline", {})
            .get("playhead", {})
            .get("current_x")
            if isinstance(payload.get("timeline"), dict)
            and isinstance(payload.get("timeline", {}).get("playhead"), dict)
            else None,
            "mocked": payload.get("mocked"),
        }
    )


@app.command("export-ux-data-contract-index")
def export_ux_data_contract_index(
    summary: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Battle UX handoff summary JSON.",
    ),
    out: Path = typer.Option(
        ..., "--out", help="Output UX data contract index JSON path."
    ),
):
    """Export the backend-owned source index for UX renderer data."""
    import json as _json

    from .ux_contract_validator import (
        ContractError,
        export_ux_data_contract_index_from_summary_path,
    )

    try:
        payload = export_ux_data_contract_index_from_summary_path(summary)
    except ContractError as exc:
        console.print(f"[red]Battle UX data contract index invalid:[/red]\n{exc}")
        raise typer.Exit(1) from exc

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        _json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    console.print_json(
        data={
            "status": "PASS",
            "out": str(out),
            "schema": payload.get("schema"),
            "battle_id": payload.get("battle_id"),
            "authoritative_renderer_values": payload.get(
                "authoritative_renderer_values"
            ),
            "authoritative_normalized_fixture": payload.get(
                "authoritative_normalized_fixture"
            ),
            "child_spawn_count": payload.get("receipt_backed_values", {}).get(
                "child_spawn_count"
            )
            if isinstance(payload.get("receipt_backed_values"), dict)
            else None,
            "playhead_current_x": payload.get("receipt_backed_values", {}).get(
                "playhead_current_x"
            )
            if isinstance(payload.get("receipt_backed_values"), dict)
            else None,
            "mocked": payload.get("mocked"),
        }
    )


@app.command("validate-ux-data-contract-index")
def validate_ux_data_contract_index(
    index: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Battle UX data contract index JSON.",
    ),
):
    """Validate the backend-owned source index for UX renderer data."""
    import json as _json

    from .ux_contract_validator import ContractError, validate_ux_data_contract_index

    try:
        payload = _json.loads(index.read_text(encoding="utf-8"))
        validate_ux_data_contract_index(payload)
    except (_json.JSONDecodeError, ContractError) as exc:
        console.print(f"[red]Battle UX data contract index invalid:[/red]\n{exc}")
        raise typer.Exit(1) from exc

    console.print_json(
        data={
            "status": "PASS",
            "index": str(index),
            "schema": payload.get("schema"),
            "battle_id": payload.get("battle_id"),
            "authoritative_renderer_values": payload.get(
                "authoritative_renderer_values"
            ),
            "authoritative_normalized_fixture": payload.get(
                "authoritative_normalized_fixture"
            ),
            "child_spawn_count": payload.get("receipt_backed_values", {}).get(
                "child_spawn_count"
            )
            if isinstance(payload.get("receipt_backed_values"), dict)
            else None,
            "playhead_current_x": payload.get("receipt_backed_values", {}).get(
                "playhead_current_x"
            )
            if isinstance(payload.get("receipt_backed_values"), dict)
            else None,
            "mocked": payload.get("mocked"),
        }
    )


@app.command("generate-ux-fixture")
def generate_ux_fixture(
    input_dir: Path = typer.Option(
        ...,
        "--input",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Battle proof directory.",
    ),
    battle_id: str = typer.Option(
        ..., "--battle-id", help="Expected Battle id for the generated fixture."
    ),
    out: Path = typer.Option(..., "--out", help="Output normalized JSON fixture path."),
    ts_out: Optional[Path] = typer.Option(
        None, "--ts-out", help="Optional generated TypeScript module path."
    ),
):
    """Generate and validate normalized Battle UX JSON from proof receipts."""
    from .battle_event_adapter import generate_fixture_files

    fixture = generate_fixture_files(
        proof_dir=input_dir, battle_id=battle_id, out=out, ts_out=ts_out
    )
    console.print_json(
        data={
            "status": "PASS",
            "proof_dir": str(input_dir),
            "out": str(out),
            "ts_out": str(ts_out) if ts_out else None,
            "schema": fixture.get("schema"),
            "ux_contract_schema": fixture.get("ux_contract", {}).get("schema")
            if isinstance(fixture.get("ux_contract"), dict)
            else None,
            "lineage_mode": fixture.get("lineage", {}).get("mode")
            if isinstance(fixture.get("lineage"), dict)
            else None,
            "child_spawn_count": fixture.get("scoreboard", {}).get("child_spawn_count")
            if isinstance(fixture.get("scoreboard"), dict)
            else None,
            "mocked": fixture.get("mocked"),
            "live_source": fixture.get("live_source"),
        }
    )


@app.command("v16-arena-freeze")
def v16_arena_freeze(
    targets: str = typer.Option(
        "battle-v16-relayforge-a",
        "--targets",
        help="Comma-separated V16 target IDs. Slice 1 supports RelayForge only.",
    ),
    out: Path = typer.Option(
        ..., "--out", help="Deterministic freeze output directory."
    ),
    image_digest: str = typer.Option(
        ...,
        "--image-digest",
        help="Immutable local service image id, sha256:<64 lowercase hex>.",
    ),
    base_image_digest: str = typer.Option(
        ...,
        "--base-image-digest",
        help="Resolved base image repository digest, name@sha256:<64 lowercase hex>.",
    ),
    repository_commit: str = typer.Option(
        ...,
        "--repository-commit",
        help="40-character agent-skills commit containing this target source.",
    ),
):
    """Freeze the RelayForge V16 target contract without claiming qualification."""
    from .relayforge_v16 import RelayForgeContractError, freeze_relayforge_target

    try:
        result = freeze_relayforge_target(
            out=out,
            image_digest=image_digest,
            base_image_digest=base_image_digest,
            repository_commit=repository_commit,
            targets=targets,
        )
    except RelayForgeContractError as exc:
        console.print(f"[red]RelayForge V16 freeze blocked:[/red]\n{exc}")
        raise typer.Exit(1) from exc
    console.print_json(data=result)


@app.command("v16-arena-deterministic-qualify")
def v16_arena_deterministic_qualify(
    target: str = typer.Option(
        "battle-v16-relayforge-a",
        "--target",
        help="V16 target ID. Slice 2 skeleton supports RelayForge only.",
    ),
    freeze: Path = typer.Option(
        ...,
        "--freeze",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="RelayForge freeze artifact directory.",
    ),
    out: Path = typer.Option(
        ..., "--out", help="Deterministic qualification artifact directory."
    ),
):
    """Run the fail-closed RelayForge deterministic qualification skeleton."""
    from .relayforge_v16 import (
        RelayForgeContractError,
        run_relayforge_deterministic_qualification,
    )

    try:
        result = run_relayforge_deterministic_qualification(
            target=target,
            freeze=freeze,
            out=out,
        )
    except RelayForgeContractError as exc:
        console.print(f"[red]RelayForge V16 qualification blocked:[/red]\n{exc}")
        raise typer.Exit(1) from exc
    console.print_json(data=result)
    if result.get("status") != "PASS":
        raise typer.Exit(1)


@app.command("v16-memory-chain-qualify")
def v16_memory_chain_qualify(
    target: str = typer.Option(
        "battle-v16-relayforge-a",
        "--target",
        help="V16 target ID. This gate supports RelayForge only.",
    ),
    deterministic_qualification: Path = typer.Option(
        ...,
        "--deterministic-qualification",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Hash-bound RelayForge deterministic qualification directory.",
    ),
    out: Path = typer.Option(
        ..., "--out", help="Live durable-Memory chain artifact directory."
    ),
):
    """Qualify one live RelayForge Memory write, recall, and provider-use chain."""
    from .relayforge_v16_memory_chain import (
        MemoryChainContractError,
        run_relayforge_v16_memory_chain,
        runtime_defaults,
    )

    defaults = runtime_defaults()
    try:
        result = run_relayforge_v16_memory_chain(
            target=target,
            deterministic_qualification=deterministic_qualification,
            out=out,
            **defaults,
        )
    except MemoryChainContractError as exc:
        console.print(f"[red]RelayForge V16 Memory chain blocked:[/red]\n{exc}")
        raise typer.Exit(1) from exc
    console.print_json(data=result)
    if result.get("status") != "PASS":
        raise typer.Exit(1)


@app.command("v16-live-topology-qualify")
def v16_live_topology_qualify(
    target: str = typer.Option(
        "battle-v16-relayforge-a",
        "--target",
        help="V16 target ID. This gate supports RelayForge only.",
    ),
    freeze: Path = typer.Option(
        ...,
        "--freeze",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Hash-bound RelayForge freeze artifact directory.",
    ),
    deterministic_qualification: Path = typer.Option(
        ...,
        "--deterministic-qualification",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Hash-bound RelayForge deterministic qualification directory.",
    ),
    memory_chain: Path = typer.Option(
        ...,
        "--memory-chain",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Live RelayForge durable-Memory chain proof directory.",
    ),
    out: Path = typer.Option(
        ..., "--out", help="Live RelayForge topology campaign artifact directory."
    ),
):
    """Qualify one live RelayForge nine-service Red/Blue campaign."""
    from .relayforge_v16_live_topology import (
        LiveTopologyContractError,
        run_relayforge_v16_live_topology,
        runtime_defaults,
    )

    try:
        result = run_relayforge_v16_live_topology(
            target=target,
            freeze=freeze,
            deterministic_qualification=deterministic_qualification,
            memory_chain=memory_chain,
            out=out,
            config=runtime_defaults(),
        )
    except LiveTopologyContractError as exc:
        console.print(f"[red]RelayForge V16 live topology blocked:[/red]\n{exc}")
        raise typer.Exit(1) from exc
    console.print_json(data=result)
    if result.get("status") != "PASS":
        raise typer.Exit(1)


@app.command()
def status():
    """Check status of running or recent battles."""
    BATTLES_DIR.mkdir(parents=True, exist_ok=True)

    battles = list(BATTLES_DIR.glob("battle_*.json"))
    if not battles:
        console.print("[yellow]No battles found[/yellow]")
        return

    table = Table(title="Battle Status")
    table.add_column("Battle ID")
    table.add_column("Status")
    table.add_column("Round")
    table.add_column("Red Score")
    table.add_column("Blue Score")
    table.add_column("Leader")

    for battle_file in sorted(battles, reverse=True)[:10]:
        try:
            state = BattleState.load(battle_file.stem)
            if state:
                leader = (
                    "Red" if state.red_total_score > state.blue_total_score else "Blue"
                )
                table.add_row(
                    state.battle_id,
                    state.status,
                    f"{state.current_round}/{state.max_rounds}",
                    f"{state.red_total_score:.1f}",
                    f"{state.blue_total_score:.1f}",
                    leader,
                )
        except Exception as e:
            logger.error("Battle status load failed for {}: {}", battle_file, e)

    console.print(table)


@app.command()
def resume(
    battle_id: str = typer.Argument(..., help="Battle ID to resume"),
):
    """Resume a paused battle."""
    from .report import generate_report
    from .resume_runtime import resume_battle_once

    receipt = resume_battle_once(battle_id)
    if receipt.get("status") == "BLOCKED":
        console.print(f"[red]Resume blocked: {receipt.get('reason')}[/red]")
        raise typer.Exit(1)
    if receipt.get("status") == "DUPLICATE_IGNORED":
        console.print("[yellow]Resume request already applied[/yellow]")
        return

    # Generate report
    final_state = BattleState.load(battle_id)
    if final_state is None:
        raise typer.Exit(1)
    report = generate_report(final_state)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{final_state.battle_id}.md"
    report_path.write_text(report)
    console.print(f"\n[green]Report saved: {report_path}[/green]")


@app.command()
def report(
    battle_id: str = typer.Argument(..., help="Battle ID to generate report for"),
):
    """Generate report for a completed battle."""
    from .report import generate_report

    state = BattleState.load(battle_id)
    if not state:
        console.print(f"[red]Battle not found: {battle_id}[/red]")
        raise typer.Exit(1)

    report_content = generate_report(state)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{battle_id}.md"
    report_path.write_text(report_content)

    console.print(report_content)
    console.print(f"\n[green]Report saved: {report_path}[/green]")


@app.command()
def stop(
    battle_id: str = typer.Argument(..., help="Battle ID to stop"),
):
    """Stop a running battle (kill switch)."""
    state = BattleState.load(battle_id)
    if not state:
        console.print(f"[red]Battle not found: {battle_id}[/red]")
        raise typer.Exit(1)

    state.status = "paused"
    state.save()
    console.print(f"[yellow]Battle {battle_id} stopped[/yellow]")


if __name__ == "__main__":
    app()
