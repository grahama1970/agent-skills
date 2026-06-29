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

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import BATTLES_DIR, REPORTS_DIR, OVERNIGHT_ROUNDS, OVERNIGHT_CHECKPOINT_INTERVAL
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


@app.command()
def battle(
    target: str = typer.Argument(".", help="Target directory, firmware file, or Docker image"),
    rounds: int = typer.Option(100, help="Maximum number of rounds"),
    overnight: bool = typer.Option(False, help="Run as overnight job (1000 rounds, checkpoints every 50)"),
    checkpoint_interval: int = typer.Option(10, help="Checkpoint every N rounds"),
    mode: str = typer.Option(None, help="Digital twin mode: git_worktree, docker, qemu, copy"),
    docker_image: str = typer.Option(None, help="Docker image for container battles (e.g., nginx:latest)"),
    qemu_machine: str = typer.Option(None, help="QEMU machine type (e.g., arm, riscv64, x86_64)"),
    chaos: bool = typer.Option(False, "--chaos", help="Enable novel exploit brainstorming (Red Team)"),
    profile: str = typer.Option("hobbyist", help="Threat profile: script-kiddie, hobbyist, organized-crime, state-actor"),
    model: str = typer.Option("gpt-5.2-codex", help="AI model to use for research and brainstorming"),
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
        console.print(f"[yellow]Overnight mode: {rounds} rounds, checkpoints every {checkpoint_interval}[/yellow]")

    # Parse mode
    twin_mode = None
    if mode:
        try:
            twin_mode = TwinMode(mode)
        except ValueError:
            console.print(f"[red]Invalid mode: {mode}[/red]")
            console.print(f"[yellow]Valid modes: {', '.join(m.value for m in TwinMode)}[/yellow]")
            raise typer.Exit(1)

    # Handle Docker image as target
    if docker_image and target == ".":
        target_path = Path.cwd()
    else:
        target_path = Path(target).resolve()
        if not target_path.exists():
            console.print(f"[red]Target not found: {target}[/red]")
            raise typer.Exit(1)

    # Pre-hook: Recall prior battle findings for this target
    if _HAS_MEMORY_INTEGRATION:
        try:
            prior = recall_prior_battles(str(target_path))
            if prior:
                console.print(f"[dim]Recalled prior battle context ({len(prior)} chars)[/dim]")
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
        model=model
    )
    state = orchestrator.run(checkpoint_interval)

    # Post-hook: Learn battle outcome
    if _HAS_MEMORY_INTEGRATION:
        try:
            learn_battle(
                target=str(target_path),
                red_findings=[f.description if hasattr(f, 'description') else str(f) for f in (state.all_findings or [])[:10]],
                blue_defenses=[p.description if hasattr(p, 'description') else str(p) for p in (state.all_patches or []) if hasattr(p, 'verified') and p.verified][:10],
                winner="Red Team" if state.red_total_score > state.blue_total_score else "Blue Team",
                lessons=[],
                battle_id=state.battle_id,
                rounds=state.current_round,
                red_score=state.red_total_score,
                blue_score=state.blue_total_score,
                tdsr=state.tdsr if hasattr(state, 'tdsr') else 0.0,
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
    fixture: str = typer.Argument("battle-001", help="Fixture name under skills/battle/fixtures/"),
    out: Optional[Path] = typer.Option(None, help="Artifact output directory"),
):
    """Run one deterministic Battle fixture with Red/Blue/Judge receipts."""
    run_battle_fixture_command(fixture, out)


@app.command("subagent-smoke")
def subagent_smoke(
    fixture: str = typer.Argument("battle-002", help="Fixture name under skills/battle/fixtures/"),
    out: Optional[Path] = typer.Option(None, help="Artifact output directory"),
    red_persona: str = typer.Option("brandon-bailey", help="Red team persona id"),
    blue_persona: str = typer.Option("coder", help="Blue team persona id"),
    fast_scan: bool = typer.Option(
        False,
        "--fast-scan",
        help="Run bounded Red reconnaissance through $hack audit before the fixture attack.",
    ),
):
    """Run one Red/Blue Tau-shaped subagent smoke around a deterministic fixture."""
    from .config import ARTIFACTS_DIR, SKILL_DIR
    from .subagent_smoke import run_subagent_smoke

    fixture_dir = SKILL_DIR / "fixtures" / fixture
    if not fixture_dir.exists():
        console.print(f"[red]Fixture not found: {fixture_dir}[/red]")
        raise typer.Exit(1)

    out_dir = out or (ARTIFACTS_DIR / fixture / "subagent-smoke")
    result = run_subagent_smoke(
        fixture_dir=fixture_dir,
        out_dir=out_dir,
        red_persona=red_persona,
        blue_persona=blue_persona,
        fast_scan=fast_scan,
    )
    console.print_json(data=result)

    if result.get("status") != "PASS":
        raise typer.Exit(1)


@app.command("tau-agentic-smoke")
def tau_agentic_smoke(
    fixture: str = typer.Argument("battle-002", help="Fixture name under skills/battle/fixtures/"),
    out: Optional[Path] = typer.Option(None, help="Artifact output directory"),
    red_persona: str = typer.Option("brandon-bailey", help="Red team persona id"),
    blue_persona: str = typer.Option("coder", help="Blue team persona id"),
    fast_scan: bool = typer.Option(
        False,
        "--fast-scan",
        help="Run bounded Red reconnaissance through $hack audit before the fixture attack.",
    ),
):
    """Run one Red/Blue smoke through Tau AgentHarness and deterministic scorekeeper."""
    from .config import ARTIFACTS_DIR, SKILL_DIR
    from .subagent_smoke import run_subagent_smoke

    fixture_dir = SKILL_DIR / "fixtures" / fixture
    if not fixture_dir.exists():
        console.print(f"[red]Fixture not found: {fixture_dir}[/red]")
        raise typer.Exit(1)

    out_dir = out or (ARTIFACTS_DIR / fixture / "tau-agentic-smoke")
    result = run_subagent_smoke(
        fixture_dir=fixture_dir,
        out_dir=out_dir,
        red_persona=red_persona,
        blue_persona=blue_persona,
        fast_scan=fast_scan,
        agentic=True,
    )
    console.print_json(data=result)

    if result.get("status") != "PASS":
        raise typer.Exit(1)


@app.command("arena-docker-smoke")
def arena_docker_smoke(
    fixture: str = typer.Argument("battle-003", help="Fixture name under skills/battle/fixtures/"),
    out: Optional[Path] = typer.Option(None, help="Artifact output directory"),
    red_persona: str = typer.Option("brandon-bailey", help="Red team persona id"),
    blue_persona: str = typer.Option("coder", help="Blue team persona id"),
    agentic: bool = typer.Option(
        False,
        "--agentic",
        help="Run Red and Blue action selection through Tau AgentHarness before the Docker race.",
    ),
    scillm_plan: bool = typer.Option(
        False,
        "--scillm-plan",
        help="Run Red and Blue action selection through live Scillm chat before Tau/Docker.",
    ),
    scillm_model: str = typer.Option(
        "opencode/kimi-k2.6",
        help="Scillm model selector used when --scillm-plan is enabled.",
    ),
    context_receipts: bool = typer.Option(
        False,
        "--context-receipts",
        help="Record memory recall/store, code-context, and research seed receipts.",
    ),
):
    """Run one Arena hidden-vulnerability race with Docker-contained commands."""
    from .arena_docker_smoke import run_arena_docker_smoke
    from .config import ARTIFACTS_DIR, SKILL_DIR

    fixture_dir = SKILL_DIR / "fixtures" / fixture
    if not fixture_dir.exists():
        console.print(f"[red]Fixture not found: {fixture_dir}[/red]")
        raise typer.Exit(1)

    out_dir = out or (ARTIFACTS_DIR / fixture / "arena-docker-smoke")
    result = run_arena_docker_smoke(
        fixture_dir=fixture_dir,
        out_dir=out_dir,
        red_persona=red_persona,
        blue_persona=blue_persona,
        agentic=agentic,
        scillm_plan=scillm_plan,
        scillm_model=scillm_model,
        context_receipts=context_receipts,
    )
    console.print_json(data=result)

    if result.get("status") != "PASS":
        raise typer.Exit(1)


@app.command("battle-v1-operational")
def battle_v1_operational(
    fixture: str = typer.Argument("battle-003", help="Fixture name under skills/battle/fixtures/"),
    out: Optional[Path] = typer.Option(None, help="Artifact output directory"),
    red_persona: str = typer.Option("brandon-bailey", help="Red team persona id"),
    blue_persona: str = typer.Option("coder", help="Blue team persona id"),
    red_workers: int = typer.Option(2, min=1, max=64, help="Bounded Red worker pool size"),
    blue_workers: int = typer.Option(2, min=1, max=64, help="Bounded Blue worker pool size"),
    max_attempts: int = typer.Option(4, min=1, max=128, help="Maximum warm-pond combinations to replay"),
    tau_live: bool = typer.Option(
        False,
        "--tau-live/--tau-deterministic",
        help="Call the Tau live Scillm handoff bridge for one Red and one Blue receipt.",
    ),
    tau_live_model: str = typer.Option(
        "gpt-5.5",
        help="Scillm model/group for --tau-live Red/Blue handoff calls.",
    ),
    memory_required: bool = typer.Option(
        True,
        "--require-memory/--memory-optional",
        help="Require $memory recall and mutation promotion for PASS.",
    ),
    memory_base_url: Optional[str] = typer.Option(
        None,
        help="$memory HTTP base URL; defaults to BATTLE_MEMORY_BASE_URL / BATTLE_MEMORY default.",
    ),
    research_broker: bool = typer.Option(
        True,
        "--research-broker/--no-research-broker",
        help="Run bounded live Brave/GitHub/Dogpile research lanes before warm-pond selection.",
    ),
):
    """Run the Battle v1 four-party Docker-only operational proof.

    This command advances beyond battle-003 by producing first-class Arena,
    Red Team, Blue Team, Scorekeeper, memory-promotion, scoreboard, monitor,
    and run receipts. Red and Blue run bounded worker pools asynchronously;
    Scorekeeper derives outcome from Docker replay, not Blue self-certification.
    """
    from .arena_docker_smoke import MEMORY_BASE_URL
    from .battle_v1_operational import run_battle_v1_operational
    from .config import ARTIFACTS_DIR, SKILL_DIR

    fixture_dir = SKILL_DIR / "fixtures" / fixture
    if not fixture_dir.exists():
        console.print(f"[red]Fixture not found: {fixture_dir}[/red]")
        raise typer.Exit(1)

    out_dir = out or (ARTIFACTS_DIR / fixture / "battle-v1-operational")
    result = run_battle_v1_operational(
        fixture_dir=fixture_dir,
        out_dir=out_dir,
        red_persona=red_persona,
        blue_persona=blue_persona,
        red_workers=red_workers,
        blue_workers=blue_workers,
        max_attempts=max_attempts,
        tau_live=tau_live,
        tau_live_model=tau_live_model,
        memory_required=memory_required,
        memory_base_url=memory_base_url or MEMORY_BASE_URL,
        research_broker=research_broker,
    )
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
                leader = "Red" if state.red_total_score > state.blue_total_score else "Blue"
                table.add_row(
                    state.battle_id,
                    state.status,
                    f"{state.current_round}/{state.max_rounds}",
                    f"{state.red_total_score:.1f}",
                    f"{state.blue_total_score:.1f}",
                    leader
                )
        except Exception as e:
            logger.error("Battle status load failed for {}: {}", battle_file, e)

    console.print(table)


@app.command()
def resume(
    battle_id: str = typer.Argument(..., help="Battle ID to resume"),
):
    """Resume a paused battle."""
    from .orchestrator import BattleOrchestrator
    from .report import generate_report

    state = BattleState.load(battle_id)
    if not state:
        console.print(f"[red]Battle not found: {battle_id}[/red]")
        raise typer.Exit(1)

    if state.status == "completed":
        console.print(f"[yellow]Battle already completed[/yellow]")
        return

    console.print(f"[green]Resuming battle from round {state.current_round}[/green]")

    # Recreate orchestrator with existing state
    orchestrator = BattleOrchestrator(
        state.target_path,
        state.max_rounds,
        concurrent=state.concurrent,
        twin_mode=state.twin_mode,
        qemu_machine=state.qemu_machine,
        docker_image=state.docker_image,
        chaos=state.chaos,
        profile=state.threat_profile,
        model=state.model,
    )
    orchestrator.state = state
    orchestrator.battle_id = state.battle_id

    # Continue battle
    final_state = orchestrator.run()

    # Generate report
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
