"""
Battle Skill - Orchestrator
Main game loop orchestrator with concurrent Red/Blue team execution.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import queue
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live

from config import BATTLES_DIR, TASK_MONITOR_SKILL, NULL_ROUND_THRESHOLD, STABLE_ROUND_THRESHOLD
from state import BattleState, TwinMode, Finding, Patch, RoundResult
from digital_twin import DigitalTwin
from red_team import RedAgent
from blue_team import BlueAgent
from scoring import Scorer, score_round

console = Console()


class TaskMonitor:
    """Integration with task-monitor skill."""

    def __init__(self, battle_id: str, total_rounds: int):
        self.battle_id = battle_id
        self.total_rounds = total_rounds
        self.monitor_script = TASK_MONITOR_SKILL / "run.sh"
        self.state_file = BATTLES_DIR / f"{battle_id}_progress.json"

    def register(self) -> bool:
        if not self.monitor_script.exists():
            return False
        try:
            result = subprocess.run(
                [str(self.monitor_script), "register", "--name", f"battle:{self.battle_id}",
                 "--total", str(self.total_rounds), "--state", str(self.state_file)],
                capture_output=True, text=True, timeout=30)
            return result.returncode == 0
        except Exception:
            return False

    def update(self, current_round: int, red_score: float, blue_score: float) -> None:
        BATTLES_DIR.mkdir(parents=True, exist_ok=True)
        state = {"current": current_round, "total": self.total_rounds, "red_score": red_score,
                 "blue_score": blue_score, "leader": "Red" if red_score > blue_score else "Blue",
                 "updated": datetime.now().isoformat()}
        self.state_file.write_text(json.dumps(state))


class BattleOrchestrator:
    """Main game loop orchestrator with concurrent Red/Blue team execution."""

    def __init__(self, target_path: str, max_rounds: int = 1000, concurrent: bool = True,
                 twin_mode: TwinMode | None = None, qemu_machine: str | None = None, docker_image: str | None = None):
        self.battle_id = f"battle_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.target_path = str(Path(target_path).resolve())
        self.max_rounds = max_rounds
        self.concurrent = concurrent
        self.state = BattleState(battle_id=self.battle_id, target_path=self.target_path, max_rounds=max_rounds)
        self.digital_twin = DigitalTwin(self.target_path, self.battle_id, mode=twin_mode,
                                         qemu_machine=qemu_machine, docker_image=docker_image)
        self.red_agent: RedAgent | None = None
        self.blue_agent: BlueAgent | None = None
        self.monitor = TaskMonitor(self.battle_id, max_rounds)
        self.null_rounds = 0
        self.stable_rounds = 0
        self.last_scores = (0.0, 0.0)
        self.finding_queue: queue.Queue[Finding] = queue.Queue()
        self.patch_queue: queue.Queue[Patch] = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_timeout = int(os.environ.get("BATTLE_WORKER_TIMEOUT_SECONDS", "300"))

    def setup_digital_twin(self) -> bool:
        if not self.digital_twin.setup():
            console.print("[red]Failed to create digital twin[/red]")
            return False
        red_target = str(self.digital_twin.get_red_target())
        blue_workspace = str(self.digital_twin.get_blue_workspace())
        self.red_agent = RedAgent(red_target, self.state, self.battle_id)
        self.blue_agent = BlueAgent(blue_workspace, self.state, self.battle_id)
        console.print(f"[green]Digital twin ready[/green]")
        return True

    def save_full_checkpoint(self, round_num: int) -> bool:
        console.print(f"[cyan]Creating checkpoint at round {round_num}...[/cyan]")
        self.state.save()
        checkpoint_meta = {"battle_id": self.battle_id, "round": round_num, "timestamp": datetime.now().isoformat(),
                          "mode": self.digital_twin.mode.value, "red_score": self.state.red_total_score,
                          "blue_score": self.state.blue_total_score}
        checkpoint_file = BATTLES_DIR / f"{self.battle_id}_checkpoint_{round_num}.json"
        checkpoint_file.write_text(json.dumps(checkpoint_meta, indent=2))
        return True

    def should_terminate(self) -> tuple[bool, str]:
        if self.null_rounds >= NULL_ROUND_THRESHOLD:
            return True, f"Null production (no findings for {NULL_ROUND_THRESHOLD} rounds)"
        if self.state.current_round >= self.max_rounds:
            return True, "Maximum rounds reached"
        if self.stable_rounds >= STABLE_ROUND_THRESHOLD:
            return True, f"Metric convergence (stable for {STABLE_ROUND_THRESHOLD} rounds)"
        return False, ""

    def red_team_worker(self, round_num: int) -> list[Finding]:
        """Worker thread for Red team; always resets state flags."""
        with self.state._lock:
            self.state.red_active = True
            self.state.red_action = "scanning"
        try:
            findings = self.red_agent.attack(round_num)
            with self.state._lock:
                self.state.red_action = f"found {len(findings)} vulns"
                self.state.all_findings.extend(findings)
            return findings
        finally:
            with self.state._lock:
                self.state.red_active = False
                self.state.red_action = "idle"

    def blue_team_worker(self, findings: list[Finding], round_num: int) -> list[Patch]:
        """Worker thread for Blue team; always resets state flags."""
        with self.state._lock:
            self.state.blue_active = True
            self.state.blue_action = "analyzing"
        try:
            patches = self.blue_agent.defend(findings, round_num)
            with self.state._lock:
                self.state.blue_action = f"patched {len([p for p in patches if p.verified])}"
                self.state.all_patches.extend(patches)
            return patches
        finally:
            with self.state._lock:
                self.state.blue_active = False
                self.state.blue_action = "idle"

    def run_round_concurrent(self, round_num: int) -> RoundResult:
        start_time = time.time()
        with cf.ThreadPoolExecutor(max_workers=2, thread_name_prefix="battle") as executor:
            red_future = executor.submit(self.red_team_worker, round_num)
            try:
                findings = red_future.result(timeout=self.worker_timeout)
            except cf.TimeoutError:
                console.print(f"[yellow]Red team timed out after {self.worker_timeout}s[/yellow]")
                findings = []
            except Exception as e:
                console.print(f"[red]Red team error: {e}[/red]")
                findings = []

            if findings:
                blue_future = executor.submit(self.blue_team_worker, findings, round_num)
                try:
                    patches = blue_future.result(timeout=self.worker_timeout)
                except cf.TimeoutError:
                    console.print(f"[yellow]Blue team timed out after {self.worker_timeout}s[/yellow]")
                    patches = []
                except Exception as e:
                    console.print(f"[red]Blue team error: {e}[/red]")
                    patches = []
            else:
                patches = []

            if patches:
                try:
                    self.digital_twin.sync_blue_to_arena()
                except Exception as e:
                    console.print(f"[yellow]Sync to arena failed: {e}[/yellow]")

        red_score, blue_score = score_round(findings, patches, round_num)
        with self.state._lock:
            self.state.red_total_score += red_score
            self.state.blue_total_score += blue_score
            self.state.current_round = round_num
        self._update_termination_tracking(findings, red_score, blue_score)
        result = RoundResult(round_number=round_num, red_findings=findings, blue_patches=patches,
                             red_score=red_score, blue_score=blue_score, duration_seconds=time.time() - start_time)
        with self.state._lock:
            self.state.rounds.append(result)
        return result

    def run_round_sequential(self, round_num: int) -> RoundResult:
        start_time = time.time()
        findings = self.red_agent.attack(round_num)
        self.state.all_findings.extend(findings)
        patches = self.blue_agent.defend(findings, round_num)
        self.state.all_patches.extend(patches)
        red_score, blue_score = score_round(findings, patches, round_num)
        self.state.red_total_score += red_score
        self.state.blue_total_score += blue_score
        self.state.current_round = round_num
        self._update_termination_tracking(findings, red_score, blue_score)
        result = RoundResult(round_number=round_num, red_findings=findings, blue_patches=patches,
                             red_score=red_score, blue_score=blue_score, duration_seconds=time.time() - start_time)
        self.state.rounds.append(result)
        return result

    def _update_termination_tracking(self, findings: list[Finding], red_score: float, blue_score: float) -> None:
        self.null_rounds = self.null_rounds + 1 if not findings else 0
        if abs(red_score - self.last_scores[0]) < 0.01 and abs(blue_score - self.last_scores[1]) < 0.01:
            self.stable_rounds += 1
        else:
            self.stable_rounds = 0
        self.last_scores = (red_score, blue_score)

    def generate_live_display(self) -> Table:
        table = Table(title=f"Battle: {self.battle_id}", expand=True)
        table.add_column("Team", style="bold")
        table.add_column("Status")
        table.add_column("Action")
        table.add_column("Score", justify="right")
        table.add_row("[red]Red Team[/red]", "[green]ACTIVE[/green]" if self.state.red_active else "[dim]idle[/dim]",
                      self.state.red_action, f"{self.state.red_total_score:.1f}")
        table.add_row("[blue]Blue Team[/blue]", "[green]ACTIVE[/green]" if self.state.blue_active else "[dim]idle[/dim]",
                      self.state.blue_action, f"{self.state.blue_total_score:.1f}")
        return table

    def run(self, checkpoint_interval: int = 10) -> BattleState:
        console.print(Panel(f"[bold]Battle: {self.battle_id}[/bold]\nTarget: {self.target_path}\n"
                            f"Max Rounds: {self.max_rounds}\nTwin Mode: {self.digital_twin.mode.value}",
                            title="Battle Starting"))
        if not self.setup_digital_twin():
            self.state.status = "failed"
            self.state.save()
            return self.state
        self.monitor.register()
        self.state.started_at = datetime.now().isoformat()
        self.state.status = "running"
        self.state.save()
        try:
            with Live(self.generate_live_display(), refresh_per_second=2, console=console) as live:
                while True:
                    should_stop, reason = self.should_terminate()
                    if should_stop:
                        live.stop()
                        console.print(f"\n[yellow]Battle ending: {reason}[/yellow]")
                        break
                    round_num = self.state.current_round + 1
                    result = self.run_round_concurrent(round_num) if self.concurrent else self.run_round_sequential(round_num)
                    live.update(self.generate_live_display())
                    console.print(f"[dim]Round {round_num}: Red +{result.red_score:.1f} ({len(result.red_findings)} finds) | "
                                  f"Blue +{result.blue_score:.1f} ({len(result.blue_patches)} patches)[/dim]")
                    self.monitor.update(self.state.current_round, self.state.red_total_score, self.state.blue_total_score)
                    if self.state.current_round % checkpoint_interval == 0:
                        self.save_full_checkpoint(self.state.current_round)
        except KeyboardInterrupt:
            console.print("\n[yellow]Battle paused by user[/yellow]")
            self.state.status = "paused"
            self.state.save()
            return self.state
        except Exception as e:
            console.print(f"\n[red]Battle failed: {e}[/red]")
            self.state.status = "failed"
            self.state.save()
            self.digital_twin.cleanup()
            return self.state
        self.state.status = "completed"
        self.state.completed_at = datetime.now().isoformat()
        metrics = Scorer.calculate_metrics(self.state)
        self.state.tdsr = metrics["tdsr"]
        self.state.fdsr = metrics["fdsr"]
        self.state.asc = metrics["asc"]
        self.state.save()
        winner = "Red Team" if self.state.red_total_score > self.state.blue_total_score else "Blue Team"
        margin = abs(self.state.red_total_score - self.state.blue_total_score)
        console.print(Panel(f"[bold green]Winner: {winner}[/bold green] (margin: {margin:.1f})\n\n"
                            f"[red]Red Total: {self.state.red_total_score:.1f}[/red]\n"
                            f"[blue]Blue Total: {self.state.blue_total_score:.1f}[/blue]\n\n"
                            f"TDSR: {self.state.tdsr:.1%}\nFindings: {len(self.state.all_findings)}\n"
                            f"Verified Patches: {len([p for p in self.state.all_patches if p.verified])}\n"
                            f"Rounds: {self.state.current_round}", title="Battle Complete"))
        self.digital_twin.cleanup()
        return self.state
