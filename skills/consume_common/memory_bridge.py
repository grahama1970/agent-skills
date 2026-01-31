"""MemoryBridge - Integration with /memory skill for knowledge storage."""

import subprocess
import json
from pathlib import Path
from typing import Any, Optional


class MemoryBridge:
    """Bridge to the memory skill for storing consumption insights."""

    def __init__(
        self,
        memory_skill_path: Optional[Path] = None,
        dry_run: bool = False
    ):
        """Initialize the memory bridge.

        Args:
            memory_skill_path: Path to memory skill run.sh (auto-detected if None)
            dry_run: If True, don't actually call memory (for testing)
        """
        self.dry_run = dry_run

        if memory_skill_path:
            self.memory_script = Path(memory_skill_path)
        else:
            # Auto-detect from common locations
            possible_paths = [
                Path.home() / "workspace" / "experiments" / "pi-mono" / ".pi" / "skills" / "memory" / "run.sh",
                Path.home() / ".pi" / "skills" / "memory" / "run.sh",
                Path(".pi/skills/memory/run.sh"),
            ]
            self.memory_script = None
            for path in possible_paths:
                if path.exists():
                    self.memory_script = path
                    break

    def _run_memory_command(self, *args: str) -> tuple[bool, str]:
        """Run a memory skill command.

        Args:
            *args: Command arguments

        Returns:
            (success, output) tuple
        """
        if self.dry_run:
            return True, f"[DRY RUN] Would execute: {' '.join(args)}"

        if not self.memory_script or not self.memory_script.exists():
            return False, "Memory skill script not found"

        cmd = [str(self.memory_script)] + list(args)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    def learn(
        self,
        problem: str,
        solution: str,
        category: str = "general",
        tags: Optional[list[str]] = None
    ) -> tuple[bool, str]:
        """Store a lesson in memory.

        Args:
            problem: Description of what was encountered
            solution: The insight or learning
            category: Category of learning (emotional_learning, approach, etc.)
            tags: Optional list of tags

        Returns:
            (success, message) tuple
        """
        cmd_parts = [
            "learn",
            "--problem", problem,
            "--solution", solution,
            "--category", category
        ]

        if tags:
            cmd_parts.extend(["--tags", ",".join(tags)])

        return self._run_memory_command(*cmd_parts)

    def recall(self, query: str, limit: int = 5) -> tuple[bool, list[dict[str, Any]]]:
        """Recall lessons from memory.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            (success, results) tuple where results is a list of lesson dicts
        """
        success, output = self._run_memory_command(
            "recall",
            "--q", query,
            "--limit", str(limit)
        )

        if not success:
            return False, []

        # Try to parse JSON output
        try:
            results = json.loads(output)
            if isinstance(results, list):
                return True, results
            elif isinstance(results, dict) and "results" in results:
                return True, results["results"]
            else:
                return True, [results]
        except json.JSONDecodeError:
            # Return raw output as single result
            return True, [{"raw": output}]

    def build_learn_command(
        self,
        problem: str,
        solution: str,
        category: str = "general",
        tags: Optional[list[str]] = None
    ) -> str:
        """Build the learn command string (for display/debugging).

        Args:
            problem: Description of what was encountered
            solution: The insight or learning
            category: Category of learning
            tags: Optional list of tags

        Returns:
            Command string
        """
        cmd = f"./memory/run.sh learn --problem \"{problem}\" --solution \"{solution}\" --category {category}"
        if tags:
            cmd += f" --tags {','.join(tags)}"
        return cmd

    def build_recall_command(self, query: str, limit: int = 5) -> str:
        """Build the recall command string (for display/debugging).

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            Command string
        """
        return f"./memory/run.sh recall --q \"{query}\" --limit {limit}"

    def store_consumption_insight(
        self,
        content_type: str,
        content_title: str,
        insight: str,
        agent_id: str = "horus_lupercal",
        emotional_reaction: Optional[dict[str, Any]] = None
    ) -> tuple[bool, str]:
        """Store a consumption insight in memory.

        Args:
            content_type: Type of content (movie, book, youtube)
            content_title: Title of the content
            insight: The insight gained
            agent_id: Agent storing the insight
            emotional_reaction: Optional emotional response

        Returns:
            (success, message) tuple
        """
        problem = f"Consumed {content_type}: {content_title}"
        if emotional_reaction:
            valence = emotional_reaction.get("valence", 0)
            arousal = emotional_reaction.get("arousal", 0)
            problem += f" [emotional: valence={valence:.2f}, arousal={arousal:.2f}]"

        tags = [content_type, agent_id]
        if emotional_reaction:
            valence = emotional_reaction.get("valence", 0)
            if valence < -0.5:
                tags.append("negative_valence")
            elif valence > 0.5:
                tags.append("positive_valence")

        return self.learn(
            problem=problem,
            solution=insight,
            category="emotional_learning",
            tags=tags
        )
