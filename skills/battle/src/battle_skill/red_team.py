"""
Battle Skill - Red Team Agent
Attacks using hack skill with learning loop.
"""
from __future__ import annotations
import os

import subprocess
from pathlib import Path
from typing import Any

from loguru import logger
from rich.console import Console

from .config import HACK_SKILL, CODE_RUNNER_SKILL
from .state import BattleState, Finding, AttackType
from .memory import BattleMemory

console = Console()


class RedAgent:
    """
    Red Team agent - attacks using hack skill with learning loop.

    Learning Loop:
    1. RECALL: Query team memory for prior attack strategies
    2. RESEARCH: Use dogpile to find new attack techniques (budget limited)
    3. ATTACK: Execute attacks against the target
    4. REFLECT: Analyze what worked and what didn't
    5. STORE: Save learnings to team memory for future rounds
    """

    def __init__(self, target_path: str, state: BattleState, battle_id: str, chaos: bool = False, model: str = "gpt-5.2-codex"):
        self.target_path = target_path
        self.state = state
        self.chaos = chaos
        self.model = model
        self.hack_script = HACK_SKILL / "run.sh"

        # Team-isolated memory
        self.memory = BattleMemory(
            battle_id=battle_id,
            team="red",
            max_research_calls_per_round=3
        )

        # Round tracking
        self.current_round = 0
        self.round_actions: list[str] = []
        self.round_outcomes: list[str] = []
        self.round_learnings: list[str] = []

    def start_round(self, round_number: int) -> None:
        """Start a new attack round - reset tracking and budget."""
        self.current_round = round_number
        self.round_actions = []
        self.round_outcomes = []
        self.round_learnings = []
        self.memory.start_new_round(round_number)
        console.print(f"[red]Red Team: Starting round {round_number} (Profile: {self.state.threat_profile})[/red]")

    def recall_phase(self) -> dict[str, Any]:
        """
        Phase 1: RECALL - Query memory for prior attack strategies.

        Returns context from past successful attacks.
        """
        console.print("[red]Red Team: RECALL phase - checking prior strategies[/red]")

        result = self.memory.recall(
            "successful attack strategies security vulnerabilities exploits",
            k=5, threshold=0.3
        )

        if result.get("found"):
            self.round_actions.append("Recalled prior attack strategies")
            return result
        else:
            self.round_actions.append("No prior strategies found")
            return {"found": False, "items": []}

    def _research_query(self) -> str:
        """Build a technique-focused query from findings, not the target path.

        The old query interpolated ``self.target_path`` (a local filesystem
        path) into a web search, so dogpile searched for a path that exists on
        no public source. Prior finding types/severities are the real signal
        for what attack families to scout next.
        """
        recent = self.state.all_findings[-3:] if self.state.all_findings else []
        descriptors: list[str] = []
        for f in recent:
            vuln_type = getattr(f.type, "value", str(f.type))
            descriptors.append(f"{f.severity} {vuln_type}")
        focus = ", ".join(dict.fromkeys(descriptors))  # dedupe, keep order
        if focus:
            return f"exploit techniques and payloads for {focus} vulnerabilities"
        # Round 1: no findings yet — scout for the threat profile's typical TTPs.
        profile = getattr(self.state, "threat_profile", "hobbyist")
        return f"common software exploit techniques and privilege escalation {profile} attacker"

    def research_phase(self, target_info: str = "") -> dict[str, Any]:
        """
        Phase 2: RESEARCH - Use dogpile to find new attack techniques.

        Subject to per-round budget limits. ``target_info`` is accepted for
        backward compatibility but is no longer interpolated into the web query.
        """
        if self.memory.get_research_budget_remaining() <= 0:
            console.print("[yellow]Red Team: Research budget exhausted[/yellow]")
            self.round_actions.append("Research skipped - budget exhausted")
            return {"success": False, "error": "budget_exhausted"}

        console.print("[red]Red Team: RESEARCH phase - finding attack techniques[/red]")

        query = self._research_query()
        result = self.memory.research(query)

        if result.get("success"):
            source_bearing = result.get("source_bearing_providers") or []
            note = f"Researched ({result.get('elapsed_s')}s, {len(source_bearing)} source-bearing providers"
            if result.get("timed_out"):
                note += ", partial"
            self.round_actions.append(f"{note}): {query}")
            self.memory.learn(
                problem=f"Research for round {self.current_round}: {query}",
                solution=result.get("results", "")[:2000],
                tags=["research", f"round_{self.current_round}"] + source_bearing
            )
        else:
            self.round_actions.append(f"Research failed: {result.get('error')}")

        return result

    def attack_phase(self, round_number: int, prior_context: dict | None = None) -> list[Finding]:
        """
        Phase 3: ATTACK - Execute attacks against the target.
        """
        console.print("[red]Red Team: ATTACK phase - executing attacks[/red]")
        findings = []
        profile = self.state.threat_profile

        if self.hack_script.exists():
            # Step A: Audit/Scan for vulnerabilities
            try:
                self.round_actions.append(f"Running security audit (Profile: {profile})")
                audit_cmd = [
                    str(self.hack_script), "audit", self.target_path,
                    "--tool", "all", "--profile", profile
                ]
                result = subprocess.run(audit_cmd, capture_output=True, text=True, timeout=300,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )

                if "Issue:" in result.stdout or "Severity:" in result.stdout:
                    finding = Finding(
                        id=f"finding_{round_number}_{len(findings)}",
                        type=AttackType.AUDIT,
                        severity="medium",
                        description=result.stdout[:1000],
                        file_path=self.target_path,
                    )
                    findings.append(finding)
                    self.round_outcomes.append(f"Found vulnerability via audit: {finding.id}")

                    # Step B: If findings found, generate exploit via code-runner
                    if self.chaos:
                        self.round_outcomes.append(
                            "Chaos exploit generation requires Tau/$hack delegation; "
                            "direct hack.exploit_writer imports are disabled."
                        )

                    classification = self.memory.classify(finding.description)
                    if classification.get("success"):
                        finding.tags = classification.get("tags", [])
                        finding.vulnerability_id = finding.tags[0] if finding.tags else None

            except subprocess.TimeoutExpired:
                console.print("[yellow]Red Team: Attack timed out[/yellow]")
                self.round_outcomes.append("Attack timed out")
            except Exception as e:
                console.print(f"[red]Red Team error: {e}[/red]")
                self.round_outcomes.append(f"Error: {e}")
        else:
            self.round_actions.append("Hack skill not available")
            self.round_outcomes.append("No attacks executed")

        return findings

    def reflect_phase(self, findings: list[Finding]) -> None:
        """
        Phase 4: REFLECT - Analyze what worked and what didn't.
        """
        console.print("[red]Red Team: REFLECT phase - analyzing results[/red]")

        if findings:
            for finding in findings:
                self.round_learnings.append(
                    f"Attack {finding.type.value} succeeded: {finding.description[:100]}"
                )
        else:
            self.round_learnings.append("No vulnerabilities found this round")
            self.round_learnings.append("Consider: different attack vectors, deeper fuzzing")

    def store_phase(self, findings: list[Finding]) -> None:
        """
        Phase 5: STORE - Save learnings to team memory for future rounds.
        """
        console.print("[red]Red Team: STORE phase - saving learnings[/red]")

        for finding in findings:
            tags = ["attack", "success", f"round_{self.current_round}"]
            if finding.tags:
                tags.extend(finding.tags)

            self.memory.learn(
                problem=f"Attack in round {self.current_round}",
                solution=f"{finding.type.value}: {finding.description}",
                tags=tags
            )

        self.memory.store_round_episode(
            round_num=self.current_round,
            actions=self.round_actions,
            outcomes=self.round_outcomes,
            learnings=self.round_learnings,
            taxonomy_tags=[f"round_{self.current_round}", "red_team"]
        )

    def execute_learning_loop(self, round_number: int) -> list[Finding]:
        """
        Execute full learning loop for a round.

        Sequence: recall -> research -> attack -> reflect -> store
        """
        self.start_round(round_number)

        prior_context = self.recall_phase()
        research_context = self.research_phase(target_info=self.target_path)
        findings = self.attack_phase(round_number, prior_context)
        self.reflect_phase(findings)
        self.store_phase(findings)

        console.print(f"[red]Red Team: Round {round_number} complete - {len(findings)} findings[/red]")
        return findings

    # --- Swarm + Cascade integration ---

    def swarm_attack(self, targets: list[str], max_workers: int = 10) -> list[Finding]:
        """Parallel GPT-driven attack probing.

        Each GPT instance probes a different file/function simultaneously.
        Classifiers do fast severity triage. Brandon validates novel findings only.
        """
        console.print(f"[red]Red Team: SWARM ATTACK ({max_workers} workers)[/red]")
        self.round_outcomes.append(
            "Swarm attack requires Tau/$hack delegation; direct hack.cascade_integration imports are disabled."
        )
        return []

    def validate_finding_cascade(self, finding: Finding) -> Finding:
        """Validate finding through Three-Tier Cascade before scoring."""
        logger.error(
            "Finding cascade validation requires Tau/$hack delegation; returning unmodified finding {}.",
            finding.id,
        )
        return finding

    # Backwards compatibility methods
    def recall_strategies(self) -> str | None:
        """Recall prior attack strategies from memory (legacy method)."""
        result = self.memory.recall(
            "successful attack strategies security vulnerabilities exploits"
        )
        if result.get("found"):
            return str(result.get("items", []))
        return None

    def attack(self, round_number: int) -> list[Finding]:
        """Execute attack phase (legacy method - use execute_learning_loop instead)."""
        return self.execute_learning_loop(round_number)

    def store_successful_attack(self, finding: Finding):
        """Store successful attack in memory (legacy method)."""
        self.memory.learn(
            problem=f"Successful attack: {finding.type.value}",
            solution=finding.description,
            tags=["attack", "success"]
        )
