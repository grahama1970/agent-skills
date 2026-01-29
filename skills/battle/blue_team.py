"""
Battle Skill - Blue Team Agent
Defends using anvil skill with learning loop.
"""
from __future__ import annotations

import subprocess
from typing import Any

from rich.console import Console

from config import ANVIL_SKILL
from state import BattleState, Finding, Patch, DefenseType
from memory import BattleMemory

console = Console()


class BlueAgent:
    """
    Blue Team agent - defends using anvil skill with learning loop.

    Learning Loop:
    1. RECALL: Query team memory for prior defense strategies
    2. RESEARCH: Use dogpile to find patching/hardening techniques
    3. DEFEND: Generate and apply patches for findings
    4. REFLECT: Analyze patch effectiveness
    5. STORE: Save learnings to team memory for future rounds
    """

    def __init__(self, target_path: str, state: BattleState, battle_id: str):
        self.target_path = target_path
        self.state = state
        self.anvil_script = ANVIL_SKILL / "run.sh"

        # Team-isolated memory
        self.memory = BattleMemory(
            battle_id=battle_id,
            team="blue",
            max_research_calls_per_round=3
        )

        # Round tracking
        self.current_round = 0
        self.round_actions: list[str] = []
        self.round_outcomes: list[str] = []
        self.round_learnings: list[str] = []

    def start_round(self, round_number: int) -> None:
        """Start a new defense round - reset tracking and budget."""
        self.current_round = round_number
        self.round_actions = []
        self.round_outcomes = []
        self.round_learnings = []
        self.memory.start_new_round(round_number)
        console.print(f"[blue]Blue Team: Starting round {round_number}[/blue]")

    def recall_phase(self, findings: list[Finding]) -> dict[str, Any]:
        """
        Phase 1: RECALL - Query memory for prior defense strategies.

        Returns context from past successful patches.
        """
        console.print("[blue]Blue Team: RECALL phase - checking prior defenses[/blue]")

        finding_types = set(f.type.value for f in findings) if findings else {"vulnerability"}
        query = f"successful patches security fixes defense strategies {' '.join(finding_types)}"

        result = self.memory.recall(query, k=5, threshold=0.3)

        if result.get("found"):
            self.round_actions.append("Recalled prior defense strategies")
            return result
        else:
            self.round_actions.append("No prior defenses found")
            return {"found": False, "items": []}

    def research_phase(self, findings: list[Finding]) -> dict[str, Any]:
        """
        Phase 2: RESEARCH - Use dogpile to find patching techniques.

        Subject to per-round budget limits.
        """
        if self.memory.get_research_budget_remaining() <= 0:
            console.print("[yellow]Blue Team: Research budget exhausted[/yellow]")
            self.round_actions.append("Research skipped - budget exhausted")
            return {"success": False, "error": "budget_exhausted"}

        console.print("[blue]Blue Team: RESEARCH phase - finding defense techniques[/blue]")

        if findings:
            finding_desc = findings[0].description[:100]
            query = f"patch fix mitigate {finding_desc}"
        else:
            query = "software hardening security best practices"

        result = self.memory.research(query)

        if result.get("success"):
            self.round_actions.append(f"Researched: {query}")
            self.memory.learn(
                problem=f"Defense research for round {self.current_round}",
                solution=result.get("results", "")[:2000],
                tags=["research", "defense", f"round_{self.current_round}"]
            )
        else:
            self.round_actions.append(f"Research failed: {result.get('error')}")

        return result

    def defend_phase(self, findings: list[Finding], round_number: int) -> list[Patch]:
        """
        Phase 3: DEFEND - Generate and apply patches for findings.
        """
        console.print("[blue]Blue Team: DEFEND phase - generating patches[/blue]")
        patches = []

        for finding in findings:
            self.round_actions.append(f"Patching: {finding.id}")

            if self.anvil_script.exists():
                try:
                    result = subprocess.run(
                        [str(self.anvil_script), "debug", "run",
                         "--issue", finding.description[:200]],
                        capture_output=True, text=True, timeout=300,
                        cwd=self.target_path
                    )

                    classification = self.memory.classify(finding.description)
                    fix_tags = classification.get("tags", []) if classification.get("success") else []

                    patch = Patch(
                        id=f"patch_{round_number}_{finding.id}",
                        finding_id=finding.id,
                        type=DefenseType.PATCH,
                        diff=result.stdout[:1000] if result.returncode == 0 else "",
                        verified=result.returncode == 0,
                        functionality_preserved=True,
                    )
                    patches.append(patch)

                    if patch.verified:
                        self.round_outcomes.append(f"Patched {finding.id} successfully")
                    else:
                        self.round_outcomes.append(f"Patch for {finding.id} needs verification")

                except subprocess.TimeoutExpired:
                    console.print("[yellow]Blue Team: Patch generation timed out[/yellow]")
                    self.round_outcomes.append(f"Patch timeout for {finding.id}")
                except Exception as e:
                    console.print(f"[red]Blue Team error: {e}[/red]")
                    self.round_outcomes.append(f"Error patching {finding.id}: {e}")
            else:
                patch = Patch(
                    id=f"patch_{round_number}_{finding.id}",
                    finding_id=finding.id,
                    type=DefenseType.PATCH,
                    diff="",
                    verified=False,
                )
                patches.append(patch)
                self.round_outcomes.append(f"Placeholder patch for {finding.id}")

        return patches

    def reflect_phase(self, patches: list[Patch]) -> None:
        """
        Phase 4: REFLECT - Analyze patch effectiveness.
        """
        console.print("[blue]Blue Team: REFLECT phase - analyzing patches[/blue]")

        verified_count = sum(1 for p in patches if p.verified)
        total = len(patches)

        self.round_learnings.append(f"Verified {verified_count}/{total} patches")

        if verified_count < total:
            self.round_learnings.append("Some patches need manual review")
            self.round_learnings.append("Consider: better test coverage, more research")
        else:
            self.round_learnings.append("All patches verified successfully")

    def store_phase(self, patches: list[Patch], findings: list[Finding]) -> None:
        """
        Phase 5: STORE - Save learnings to team memory for future rounds.
        """
        console.print("[blue]Blue Team: STORE phase - saving learnings[/blue]")

        for patch in patches:
            if patch.verified:
                tags = ["defense", "success", f"round_{self.current_round}"]
                self.memory.learn(
                    problem=f"Vulnerability patched: {patch.finding_id}",
                    solution=f"Patch applied: {patch.diff[:500]}",
                    tags=tags
                )

        self.memory.store_round_episode(
            round_num=self.current_round,
            actions=self.round_actions,
            outcomes=self.round_outcomes,
            learnings=self.round_learnings,
            taxonomy_tags=[f"round_{self.current_round}", "blue_team"]
        )

    def execute_learning_loop(self, findings: list[Finding], round_number: int) -> list[Patch]:
        """
        Execute full learning loop for a round.

        Sequence: recall -> research -> defend -> reflect -> store
        """
        self.start_round(round_number)

        prior_context = self.recall_phase(findings)
        research_context = self.research_phase(findings)
        patches = self.defend_phase(findings, round_number)
        self.reflect_phase(patches)
        self.store_phase(patches, findings)

        verified = sum(1 for p in patches if p.verified)
        console.print(f"[blue]Blue Team: Round {round_number} complete - {verified}/{len(patches)} patches verified[/blue]")
        return patches

    # Backwards compatibility methods
    def recall_defenses(self) -> str | None:
        """Recall prior defense strategies from memory (legacy method)."""
        result = self.memory.recall(
            "successful patches security fixes defense strategies"
        )
        if result.get("found"):
            return str(result.get("items", []))
        return None

    def defend(self, findings: list[Finding], round_number: int) -> list[Patch]:
        """Generate patches for findings (legacy method - use execute_learning_loop instead)."""
        return self.execute_learning_loop(findings, round_number)

    def store_successful_defense(self, patch: Patch):
        """Store successful defense in memory (legacy method)."""
        self.memory.learn(
            problem=f"Successful defense: {patch.finding_id}",
            solution=f"Patch: {patch.diff[:500]}",
            tags=["defense", "success"]
        )
