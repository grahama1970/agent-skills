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

from .config import (
    BATTLES_DIR,
    TASK_MONITOR_SKILL,
    NULL_ROUND_THRESHOLD,
    STABLE_ROUND_THRESHOLD,
    DEFAULT_MODEL,
    SUCCESSFUL_PATCH_SCORE,
    TIME_DECAY_FACTOR,
    SEVERITY_MULTIPLIERS,
)
from .state import BattleState, TwinMode, Finding, FunctionalEvidenceStatus, Patch, RoundResult
from .digital_twin import DigitalTwin
from .red_team import RedAgent
from .blue_team import BlueAgent
from .scoring import Scorer
from .human_interjection import apply_pending_pause_after_round
from .orchestrator_judge import (
    BlueCandidateRef,
    FailClosedJudgeBoundary,
    JudgeBoundary,
    JudgeFindingOutcome,
    JudgePatchOutcome,
    RoundJudgeContext,
    source_identity,
    wrap_blue_candidates,
)

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=False)

console = Console()


class TaskMonitor:
    """Integration with task-monitor skill."""

    def __init__(self, battle_id: str, total_rounds: int):
        self.battle_id = battle_id
        self.total_rounds = total_rounds
        self.monitor_script = TASK_MONITOR_SKILL / "run.sh"
        self.state_file = BATTLES_DIR / f"{battle_id}_progress.json"

    def register(self, profile: str = "hobbyist", chaos: bool = False, model: str = DEFAULT_MODEL) -> bool:
        if not self.monitor_script.exists():
            return False
        try:
            desc = f"profile:{profile} chaos:{chaos} model:{model}"
            result = subprocess.run(
                [str(self.monitor_script), "register", "--name", f"battle:{self.battle_id}",
                 "--total", str(self.total_rounds), "--state", str(self.state_file),
                 "--summary", desc],
                capture_output=True, text=True, timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
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
                 twin_mode: TwinMode | None = None, qemu_machine: str | None = None,
                 docker_image: str | None = None, chaos: bool = False,
                 profile: str = "hobbyist", model: str = "gpt-5.2-codex",
                 judge_boundary: JudgeBoundary | None = None):
        self.battle_id = f"battle_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.target_path = str(Path(target_path).resolve())
        self.max_rounds = max_rounds
        self.concurrent = concurrent
        self.chaos = chaos
        self.model = model
        self.state = BattleState(
            battle_id=self.battle_id,
            target_path=self.target_path,
            max_rounds=max_rounds,
            threat_profile=profile,
            twin_mode=twin_mode,
            docker_image=docker_image,
            qemu_machine=qemu_machine,
            chaos=chaos,
            model=model,
            concurrent=concurrent,
        )
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
        self.control_dir = BATTLES_DIR / f"{self.battle_id}_control"
        self.judge_boundary = judge_boundary or FailClosedJudgeBoundary()

    def _round_judge_context(self, round_num: int) -> RoundJudgeContext:
        source_commit, source_tree = source_identity()
        receipt_root = getattr(
            self,
            "control_dir",
            BATTLES_DIR / f"{self.battle_id}_control",
        )
        return RoundJudgeContext(
            battle_id=self.battle_id,
            run_id=self.battle_id,
            round_number=round_num,
            receipt_dir=receipt_root / "judge" / f"round-{round_num:04d}",
            source_commit=source_commit,
            source_tree=source_tree,
        )

    def setup_digital_twin(self) -> bool:
        if not self.digital_twin.setup():
            console.print("[red]Failed to create digital twin[/red]")
            return False
        self.state.twin_mode = self.digital_twin.mode
        self.state.docker_image = self.digital_twin.docker_image
        self.state.qemu_machine = self.digital_twin.qemu_machine
        red_target = str(self.digital_twin.get_red_target())
        blue_workspace = str(self.digital_twin.get_blue_workspace())
        self.red_agent = RedAgent(red_target, self.state, self.battle_id, chaos=self.chaos, model=self.model)
        self.blue_agent = BlueAgent(blue_workspace, self.state, self.battle_id, model=self.model)
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

    def judge_red_findings(self, findings: list[Finding], round_num: int) -> list[JudgeFindingOutcome]:
        """Return immutable Red finding outcomes from the Battle Judge boundary."""
        boundary = getattr(self, "judge_boundary", FailClosedJudgeBoundary())
        return boundary.judge_findings(self._round_judge_context(round_num), findings)

    def judge_patch_verdicts(
        self,
        candidates: list[BlueCandidateRef],
        patches: list[Patch],
        confirmed_findings: list[Finding],
        round_num: int,
    ) -> list[JudgePatchOutcome]:
        """Return immutable Blue patch outcomes from the Battle Judge boundary."""
        boundary = getattr(self, "judge_boundary", FailClosedJudgeBoundary())
        return boundary.judge_patches(
            self._round_judge_context(round_num),
            candidates,
            patches,
            confirmed_findings,
        )

    def score_judged_round(
        self,
        findings: list[Finding],
        finding_outcomes: list[JudgeFindingOutcome],
        patches: list[Patch],
        patch_outcomes: list[JudgePatchOutcome],
        round_num: int,
    ) -> tuple[float, float]:
        """Score only immutable Judge-confirmed findings and successful patches."""
        confirmed_ids = {
            outcome.finding_id
            for outcome in finding_outcomes
            if outcome.verdict == "CONFIRMED"
        }
        confirmed_findings = [
            finding for finding in findings if finding.id in confirmed_ids
        ]
        red_score = sum(Scorer.score_finding(f, round_num) for f in confirmed_findings)
        blue_score = 0.0
        if confirmed_findings:
            finding_by_id = {finding.id: finding for finding in confirmed_findings}
            for patch in patches:
                accepted = [
                    outcome
                    for outcome in patch_outcomes
                    if outcome.patch_id == patch.id
                    and outcome.verdict == "BLUE_SUCCESS"
                    and outcome.functional_evidence_status is FunctionalEvidenceStatus.PASS
                ]
                if not accepted:
                    continue
                matching_finding = finding_by_id.get(patch.finding_id)
                if not matching_finding:
                    continue
                blue_score += self._score_judge_accepted_patch(patch, matching_finding, round_num)
        self._write_scorekeeper_receipt(
            round_num=round_num,
            findings=findings,
            patches=patches,
            finding_outcomes=finding_outcomes,
            patch_outcomes=patch_outcomes,
            red_score=red_score,
            blue_score=blue_score,
        )
        return red_score, blue_score

    def _score_judge_accepted_patch(self, patch: Patch, finding: Finding, round_num: int) -> float:
        base = SUCCESSFUL_PATCH_SCORE
        mult = SEVERITY_MULTIPLIERS.get(finding.severity, 1.0)
        base *= 1.2
        decay = 1.0 / (1.0 + TIME_DECAY_FACTOR * round_num)
        return base * mult * decay

    def _write_scorekeeper_receipt(
        self,
        *,
        round_num: int,
        findings: list[Finding],
        patches: list[Patch],
        finding_outcomes: list[JudgeFindingOutcome],
        patch_outcomes: list[JudgePatchOutcome],
        red_score: float,
        blue_score: float,
    ) -> Path:
        receipt_path = self.control_dir / "judge" / f"round-{round_num:04d}" / "scorekeeper-receipt.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt = {
            "schema": "battle.orchestrator_scorekeeper_receipt.v1",
            "status": "PASS",
            "mocked": False,
            "live": True,
            "battle_id": self.battle_id,
            "run_id": self.battle_id,
            "round_number": round_num,
            "score_authority": "judge_receipts_only",
            "red_score": red_score,
            "blue_score": blue_score,
            "finding_ids": [finding.id for finding in findings],
            "patch_ids": [patch.id for patch in patches],
            "accepted_red_finding_ids": [
                outcome.finding_id
                for outcome in finding_outcomes
                if outcome.verdict == "CONFIRMED"
            ],
            "accepted_blue_candidate_ids": [
                outcome.candidate_id
                for outcome in patch_outcomes
                if outcome.verdict == "BLUE_SUCCESS"
                and outcome.functional_evidence_status is FunctionalEvidenceStatus.PASS
            ],
            "finding_outcome_receipts": [
                outcome.receipt.path for outcome in finding_outcomes
            ],
            "patch_outcome_receipts": [
                outcome.receipt.path for outcome in patch_outcomes
            ],
            "created_at": datetime.now().isoformat(),
        }
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return receipt_path

    def run_round_concurrent(self, round_num: int) -> RoundResult:
        start_time = time.time()
        executor = cf.ThreadPoolExecutor(max_workers=2, thread_name_prefix="battle")
        try:
            red_future = executor.submit(self.red_team_worker, round_num)
            blue_future = executor.submit(self.blue_team_worker, [], round_num)
            try:
                findings = red_future.result(timeout=self.worker_timeout)
            except cf.TimeoutError:
                console.print(f"[yellow]Red team timed out after {self.worker_timeout}s[/yellow]")
                red_future.cancel()
                findings = []
            except Exception as e:
                console.print(f"[red]Red team error: {e}[/red]")
                findings = []

            # Cascade validation: filter false positives
            if findings:
                validated_findings = []
                for f in findings:
                    try:
                        f = self.red_agent.validate_finding_cascade(f)
                        if "cascade:false_positive" not in f.tags:
                            validated_findings.append(f)
                    except Exception:
                        validated_findings.append(f)
                findings = validated_findings
                console.print(f"[dim]Cascade: {len(findings)} findings after FP filter[/dim]")

            try:
                patches = blue_future.result(timeout=self.worker_timeout)
            except cf.TimeoutError:
                console.print(f"[yellow]Blue team timed out after {self.worker_timeout}s[/yellow]")
                blue_future.cancel()
                patches = []
            except Exception as e:
                console.print(f"[red]Blue team error: {e}[/red]")
                patches = []

            finding_outcomes = self.judge_red_findings(findings, round_num)
            confirmed_ids = {
                outcome.finding_id
                for outcome in finding_outcomes
                if outcome.verdict == "CONFIRMED"
            }
            confirmed_findings = [
                finding for finding in findings if finding.id in confirmed_ids
            ]
            reactive_patches: list[Patch] = []
            if confirmed_findings:
                try:
                    reactive_patches = self.blue_team_worker(confirmed_findings, round_num)
                except Exception as e:
                    console.print(f"[red]Reactive Blue team error: {e}[/red]")
                    reactive_patches = []

            proactive_candidates = wrap_blue_candidates(patches, phase="proactive")
            reactive_candidates = wrap_blue_candidates(reactive_patches, phase="reactive")
            patches = patches + reactive_patches
            candidates = proactive_candidates + reactive_candidates
            patch_outcomes = self.judge_patch_verdicts(
                candidates,
                patches,
                confirmed_findings,
                round_num,
            )

            if patches and any(outcome.verdict == "BLUE_SUCCESS" for outcome in patch_outcomes):
                try:
                    self.digital_twin.sync_blue_to_arena()
                except Exception as e:
                    console.print(f"[yellow]Sync to arena failed: {e}[/yellow]")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        red_score, blue_score = self.score_judged_round(
            findings,
            finding_outcomes,
            patches,
            patch_outcomes,
            round_num,
        )
        with self.state._lock:
            self.state.red_total_score += red_score
            self.state.blue_total_score += blue_score
            self.state.current_round = round_num
        self._update_termination_tracking(confirmed_findings, red_score, blue_score)
        result = RoundResult(round_number=round_num, red_findings=confirmed_findings, blue_patches=patches,
                             red_score=red_score, blue_score=blue_score, duration_seconds=time.time() - start_time)
        with self.state._lock:
            self.state.rounds.append(result)
        return result

    def run_round_sequential(self, round_num: int) -> RoundResult:
        start_time = time.time()
        findings = self.red_agent.attack(round_num)
        self.state.all_findings.extend(findings)
        finding_outcomes = self.judge_red_findings(findings, round_num)
        confirmed_ids = {
            outcome.finding_id
            for outcome in finding_outcomes
            if outcome.verdict == "CONFIRMED"
        }
        confirmed_findings = [
            finding for finding in findings if finding.id in confirmed_ids
        ]
        patches = self.blue_agent.defend(confirmed_findings, round_num)
        self.state.all_patches.extend(patches)
        candidates = wrap_blue_candidates(patches, phase="reactive")
        patch_outcomes = self.judge_patch_verdicts(
            candidates,
            patches,
            confirmed_findings,
            round_num,
        )
        red_score, blue_score = self.score_judged_round(
            findings,
            finding_outcomes,
            patches,
            patch_outcomes,
            round_num,
        )
        self.state.red_total_score += red_score
        self.state.blue_total_score += blue_score
        self.state.current_round = round_num
        self._update_termination_tracking(confirmed_findings, red_score, blue_score)
        result = RoundResult(round_number=round_num, red_findings=confirmed_findings, blue_patches=patches,
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

    def _write_round_boundary_receipt(self, result: RoundResult) -> Path:
        """Persist completed round state before applying an interjection."""
        state_path = self.state.save()
        round_dir = self.control_dir / "round-boundaries"
        round_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = round_dir / f"round-{result.round_number:04d}.json"
        receipt = {
            "schema": "battle.round_boundary.v1",
            "status": "PASS",
            "mocked": False,
            "live": True,
            "battle_id": self.battle_id,
            "run_id": self.battle_id,
            "round_number": result.round_number,
            "red_score": result.red_score,
            "blue_score": result.blue_score,
            "red_finding_count": len(result.red_findings),
            "blue_patch_count": len(result.blue_patches),
            "state_checkpoint": str(state_path),
            "state_status": self.state.status,
            "created_at": datetime.now().isoformat(),
        }
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        return receipt_path

    def _apply_pause_after_round(self, result: RoundResult) -> bool:
        """Apply one accepted request or stop fail-closed on control errors."""
        round_receipt = self._write_round_boundary_receipt(result)
        try:
            scan = apply_pending_pause_after_round(
                control_dir=self.control_dir,
                active_run_id=self.battle_id,
                round_receipt=round_receipt,
            )
        except Exception as e:
            error_dir = self.control_dir / "errors"
            error_dir.mkdir(parents=True, exist_ok=True)
            error_path = error_dir / f"round-{result.round_number:04d}.json"
            error_path.write_text(json.dumps({
                "schema": "battle.human_interjection_control_error.v1",
                "status": "BLOCKED",
                "mocked": False,
                "live": True,
                "battle_id": self.battle_id,
                "run_id": self.battle_id,
                "round_number": result.round_number,
                "round_receipt": str(round_receipt),
                "error_type": type(e).__name__,
                "error": str(e),
                "created_at": datetime.now().isoformat(),
            }, indent=2, sort_keys=True) + "\n")
            self.state.status = "paused"
            self.state.save()
            return True

        application = scan.get("application")
        if scan.get("status") != "APPLIED" or not isinstance(application, dict):
            return False
        if application.get("pause_next_round") is not True:
            return False
        self.state.status = "paused"
        self.state.save()
        return True

    def generate_live_display(self) -> Table:
        title = f"Battle: {self.battle_id} [bold yellow]Profile: {self.state.threat_profile}[/bold yellow]"
        if self.chaos:
            title += " [bold purple](CHAOS ENABLED)[/bold purple]"
        table = Table(title=title, expand=True)
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
        self.monitor.register(profile=self.state.threat_profile, chaos=self.chaos, model=self.model)
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
                    if self._apply_pause_after_round(result):
                        live.stop()
                        console.print("\n[yellow]Battle paused at the after-round control boundary[/yellow]")
                        return self.state
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
