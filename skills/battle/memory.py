"""
Battle Skill - Team Memory System
Team-isolated learning system for accumulating knowledge across rounds.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from typing import Any

from rich.console import Console

from config import MEMORY_SKILL, DOGPILE_SKILL, TAXONOMY_SKILL, DEFAULT_RESEARCH_BUDGET

console = Console()


class BattleMemory:
    """
    Team-specific memory system for accumulating learnings across rounds.

    Each team (Red, Blue) gets an isolated memory collection that the opponent
    cannot access. This enables:
    - Strategic knowledge accumulation
    - Learning from past attacks/defenses
    - Cross-round strategy evolution

    Uses the memory skill with team-specific scopes:
    - battle_red_{battle_id}: Red team learnings
    - battle_blue_{battle_id}: Blue team learnings
    """

    def __init__(
        self,
        battle_id: str,
        team: str,
        max_research_calls_per_round: int = DEFAULT_RESEARCH_BUDGET
    ):
        """
        Initialize team-specific memory.

        Args:
            battle_id: Unique battle identifier
            team: Team name ('red' or 'blue')
            max_research_calls_per_round: Research budget per round (default: 3)
        """
        self.battle_id = battle_id
        self.team = team.lower()
        self.scope = f"battle_{self.team}_{battle_id}"
        self.memory_script = MEMORY_SKILL / "run.sh"

        # Research budget tracking
        self.max_research_calls = max_research_calls_per_round
        self.research_calls_this_round = 0
        self.current_round = 0

    def recall(self, query: str, k: int = 5, threshold: float = 0.3) -> dict[str, Any]:
        """
        Query team memory for prior learnings.

        Args:
            query: The problem/task to search for
            k: Number of results to return
            threshold: Minimum confidence threshold

        Returns:
            Dict with 'found', 'items', 'confidence' keys
        """
        if not self.memory_script.exists():
            console.print("[yellow]Memory skill not available[/yellow]")
            return {"found": False, "items": [], "confidence": 0.0}

        try:
            result = subprocess.run(
                [str(self.memory_script), "recall",
                 "--q", query,
                 "--scope", self.scope,
                 "--k", str(k),
                 "--threshold", str(threshold)],
                capture_output=True, text=True, timeout=30
            )

            if result.returncode == 0:
                # Parse JSON output from memory skill
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    # Non-JSON output, check for found/not found
                    if "found=true" in result.stdout.lower():
                        return {"found": True, "items": [result.stdout], "confidence": 0.5}
                    return {"found": False, "items": [], "confidence": 0.0}
            else:
                return {"found": False, "items": [], "confidence": 0.0, "error": result.stderr}

        except subprocess.TimeoutExpired:
            return {"found": False, "items": [], "confidence": 0.0, "error": "timeout"}
        except Exception as e:
            return {"found": False, "items": [], "confidence": 0.0, "error": str(e)}

    def learn(
        self,
        problem: str,
        solution: str,
        tags: list[str] | None = None
    ) -> bool:
        """
        Store a new learning in team memory.

        Args:
            problem: The problem that was encountered
            solution: How it was solved
            tags: Optional tags for classification (CWE numbers, attack types, etc.)

        Returns:
            True if learning was stored successfully
        """
        if not self.memory_script.exists():
            console.print("[yellow]Memory skill not available[/yellow]")
            return False

        cmd = [
            str(self.memory_script), "learn",
            "--problem", problem,
            "--solution", solution,
            "--scope", self.scope,
        ]

        # Add tags
        if tags:
            for tag in tags:
                cmd.extend(["--tag", tag])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.returncode == 0
        except Exception as e:
            console.print(f"[red]Failed to store learning: {e}[/red]")
            return False

    def start_new_round(self, round_num: int) -> None:
        """
        Start a new round - reset research budget.

        Args:
            round_num: The new round number
        """
        self.current_round = round_num
        self.research_calls_this_round = 0
        console.print(f"[cyan]Round {round_num}: Research budget reset ({self.max_research_calls} calls)[/cyan]")

    def get_research_budget_remaining(self) -> int:
        """Get remaining research calls for this round."""
        return max(0, self.max_research_calls - self.research_calls_this_round)

    def research(self, query: str, force: bool = False) -> dict[str, Any]:
        """
        Research a topic using dogpile (multi-source search).

        Subject to per-round budget limits to prevent infinite loops.

        Args:
            query: Research query
            force: If True, bypass budget check (use sparingly)

        Returns:
            Dict with research results from multiple sources
        """
        # Check budget
        if not force and self.research_calls_this_round >= self.max_research_calls:
            console.print(f"[yellow]Research budget exceeded ({self.max_research_calls} calls/round)[/yellow]")
            console.print(f"[dim]Query '{query}' not executed. Use force=True to override.[/dim]")
            return {
                "success": False,
                "error": "budget_exceeded",
                "budget_remaining": 0,
                "query": query
            }

        dogpile_script = DOGPILE_SKILL / "run.sh"
        if not dogpile_script.exists():
            console.print("[yellow]Dogpile skill not available[/yellow]")
            return {"success": False, "error": "dogpile not available"}

        # Increment counter BEFORE the call
        self.research_calls_this_round += 1
        remaining = self.get_research_budget_remaining()
        console.print(f"[dim]Research call {self.research_calls_this_round}/{self.max_research_calls} ({remaining} remaining)[/dim]")

        try:
            result = subprocess.run(
                [str(dogpile_script), "search", query],
                capture_output=True, text=True, timeout=300  # 5 min timeout for research
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "results": result.stdout,
                    "budget_remaining": remaining
                }
            else:
                return {"success": False, "error": result.stderr, "budget_remaining": remaining}

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "research timeout", "budget_remaining": remaining}
        except Exception as e:
            return {"success": False, "error": str(e), "budget_remaining": remaining}

    def classify(self, finding: str) -> dict[str, Any]:
        """
        Classify a finding using taxonomy skill.

        Returns CWE, severity, mitigation type tags.

        Args:
            finding: The finding to classify

        Returns:
            Dict with classification tags
        """
        taxonomy_script = TAXONOMY_SKILL / "run.sh"
        if not taxonomy_script.exists():
            console.print("[yellow]Taxonomy skill not available[/yellow]")
            return {"success": False, "tags": []}

        try:
            result = subprocess.run(
                [str(taxonomy_script), "classify", finding],
                capture_output=True, text=True, timeout=60
            )

            if result.returncode == 0:
                # Parse taxonomy output
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    return {"success": True, "tags": result.stdout.strip().split("\n")}
            else:
                return {"success": False, "tags": [], "error": result.stderr}

        except Exception as e:
            return {"success": False, "tags": [], "error": str(e)}

    def store_round_episode(
        self,
        round_num: int,
        actions: list[str],
        outcomes: list[str],
        learnings: list[str],
        taxonomy_tags: list[str] | None = None
    ) -> bool:
        """
        Archive a complete round episode for semantic recall.

        This implements the episodic archiver pattern:
        - Full round transcript with embeddings
        - Queryable for "what worked", "what failed", etc.

        Args:
            round_num: The round number
            actions: List of actions taken this round
            outcomes: Results of each action
            learnings: Key learnings from the round
            taxonomy_tags: Classification tags

        Returns:
            True if episode was stored successfully
        """
        # Format episode as a structured learning
        episode_problem = f"Round {round_num} for {self.team} team"
        episode_solution = json.dumps({
            "round": round_num,
            "actions": actions,
            "outcomes": outcomes,
            "learnings": learnings,
            "timestamp": datetime.now().isoformat()
        }, indent=2)

        tags = [f"round_{round_num}", f"team_{self.team}"]
        if taxonomy_tags:
            tags.extend(taxonomy_tags)

        return self.learn(
            problem=episode_problem,
            solution=episode_solution,
            tags=tags
        )

    def query_strategy_evolution(self, last_n_rounds: int = 3) -> list[dict]:
        """
        Query past rounds to understand strategy evolution.

        Used for cross-round learning:
        - "last 3 rounds, buffer overflows failed - try format strings"

        Args:
            last_n_rounds: Number of recent rounds to analyze

        Returns:
            List of round episodes with analysis
        """
        episodes = []
        for i in range(last_n_rounds):
            round_query = f"Round {i} {self.team} team"
            result = self.recall(round_query, k=1, threshold=0.1)
            if result.get("found"):
                episodes.append(result)

        return episodes
