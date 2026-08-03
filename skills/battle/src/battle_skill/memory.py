"""
Battle Skill - Team Memory System
Team-isolated learning system for accumulating knowledge across rounds.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import subprocess
import time
from datetime import datetime
from typing import Any, Callable, Iterable

from rich.console import Console

from .config import (
    MEMORY_SKILL,
    DOGPILE_SKILL,
    TAXONOMY_SKILL,
    DEFAULT_RESEARCH_BUDGET,
    DEFAULT_RESEARCH_DEADLINE_S,
    TEAM_DOGPILE_PRESETS,
)

console = Console()

# Dogpile emits one JSON progress event per line on stderr (see dogpile
# cli.py PartialResultsPublisher.emit). stderr is per-process, so it is safe to
# read concurrently; the dogpile_partial_results.json file is NOT — it is a
# single fixed path shared by every dogpile run, so concurrent Red/Blue
# searches would clobber each other's copy. Never read that file from here.
DOGPILE_EVENT_PREFIX = "[dogpile-event] "


def _console_print(message: str) -> None:
    """Progress logging must not make research fail."""

    try:
        console.print(message)
    except ModuleNotFoundError:
        print(re.sub(r"\[[^\]]+\]", "", message))


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
            _console_print("[yellow]Memory skill not available[/yellow]")
            return {"found": False, "items": [], "confidence": 0.0}

        try:
            result = subprocess.run(
                [str(self.memory_script), "recall",
                 "--q", query,
                 "--scope", self.scope,
                 "--k", str(k),
                 "--threshold", str(threshold)],
                capture_output=True, text=True, timeout=30,
                env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
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
            _console_print("[yellow]Memory skill not available[/yellow]")
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
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            return result.returncode == 0
        except Exception as e:
            _console_print(f"[red]Failed to store learning: {e}[/red]")
            return False

    def start_new_round(self, round_num: int) -> None:
        """
        Start a new round - reset research budget.

        Args:
            round_num: The new round number
        """
        self.current_round = round_num
        self.research_calls_this_round = 0
        _console_print(f"[cyan]Round {round_num}: Research budget reset ({self.max_research_calls} calls)[/cyan]")

    def get_research_budget_remaining(self) -> int:
        """Get remaining research calls for this round."""
        return max(0, self.max_research_calls - self.research_calls_this_round)

    @property
    def dogpile_preset(self) -> str | None:
        """Curated dogpile source preset for this team, if any."""
        return TEAM_DOGPILE_PRESETS.get(self.team)

    def _spend_budget(self, query: str, force: bool) -> tuple[bool, int]:
        """Charge one research call. Returns (allowed, budget_remaining)."""
        if not force and self.research_calls_this_round >= self.max_research_calls:
            _console_print(f"[yellow]Research budget exceeded ({self.max_research_calls} calls/round)[/yellow]")
            _console_print(f"[dim]Query '{query}' not executed. Use force=True to override.[/dim]")
            return False, 0
        self.research_calls_this_round += 1
        remaining = self.get_research_budget_remaining()
        _console_print(
            f"[dim]Research call {self.research_calls_this_round}/{self.max_research_calls} "
            f"({remaining} remaining)[/dim]"
        )
        return True, remaining

    def _build_command(self, query: str, dogpile_script: Any) -> list[str]:
        """Build a bounded, non-interactive dogpile invocation for this team.

        --no-interactive is mandatory: with the interactive default, dogpile
        routes queries under 5 words through a Codex ambiguity check that can
        print clarifications and exit 0 WITHOUT searching. A returncode-only
        caller would score that as success and store the clarification prompt
        as research.
        """
        cmd = [str(dogpile_script), "search", query, "--no-interactive"]
        preset = self.dogpile_preset
        if preset:
            cmd += ["--preset", preset]
        return cmd

    @staticmethod
    async def _pump(stream: Any, on_line: Callable[[str], None]) -> None:
        """Consume a subprocess stream line-by-line as it is produced."""
        while True:
            raw = await stream.readline()
            if not raw:
                return
            on_line(raw.decode("utf-8", errors="replace").rstrip("\n"))

    @staticmethod
    async def _terminate(proc: Any) -> None:
        """Stop a dogpile child that overran its deadline.

        dogpile is a process tree (``run.sh`` -> ``uv run`` -> ``.venv``
        python). Signalling only the direct child leaves the grandchild doing
        the real work orphaned, so the whole process group is signalled. The
        child is spawned with ``start_new_session=True`` so its pgid == pid.
        """
        if proc.returncode is not None:
            return

        def _signal_group(sig: int) -> bool:
            try:
                os.killpg(os.getpgid(proc.pid), sig)
                return True
            except (ProcessLookupError, PermissionError):
                return False

        if not _signal_group(signal.SIGTERM):
            try:
                proc.terminate()
            except ProcessLookupError:
                return
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except (asyncio.TimeoutError, ProcessLookupError):
            if not _signal_group(signal.SIGKILL):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                pass

    async def research_async(
        self,
        query: str,
        force: bool = False,
        deadline_s: int = DEFAULT_RESEARCH_DEADLINE_S,
    ) -> dict[str, Any]:
        """
        Research a topic using dogpile, bounded by a wall-clock deadline.

        Speed of research against knowledge attained decides rounds, so this
        harvests dogpile's incremental stderr event stream while the search is
        still running. When the deadline expires the child is stopped and
        whatever providers already landed are returned, rather than throwing a
        partially-complete search away.

        Args:
            query: Research query
            force: If True, bypass budget check (use sparingly)
            deadline_s: Wall-clock budget for this search

        Returns:
            Dict with per-provider outcomes, harvested text, and timing.
        """
        allowed, remaining = self._spend_budget(query, force)
        if not allowed:
            return {"success": False, "error": "budget_exceeded", "budget_remaining": 0, "query": query}

        dogpile_script = DOGPILE_SKILL / "run.sh"
        if not dogpile_script.exists():
            _console_print("[yellow]Dogpile skill not available[/yellow]")
            return {"success": False, "error": "dogpile not available", "budget_remaining": remaining}

        cmd = self._build_command(query, dogpile_script)
        started = time.time()
        providers: dict[str, Any] = {}
        stdout_chunks: list[str] = []
        finish_status: str | None = None
        model_synthesis_present = False

        def on_stderr(line: str) -> None:
            if not line.startswith(DOGPILE_EVENT_PREFIX):
                return
            try:
                event = json.loads(line[len(DOGPILE_EVENT_PREFIX):])
            except json.JSONDecodeError:
                return
            name = event.get("event")
            if name == "partial_result":
                provider = event.get("provider")
                if provider:
                    summary = event.get("summary") or {}
                    providers[provider] = summary
                    nonlocal model_synthesis_present
                    model_synthesis_present = model_synthesis_present or bool(summary.get("model_synthesis_present"))
            elif name == "search_finished":
                nonlocal finish_status
                finish_status = event.get("status")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(DOGPILE_SKILL),
                start_new_session=True,  # own process group so the deadline can reap the whole tree
            )
        except Exception as e:
            return {"success": False, "error": f"spawn failed: {e}", "budget_remaining": remaining}

        pumps = asyncio.gather(
            self._pump(proc.stdout, stdout_chunks.append),
            self._pump(proc.stderr, on_stderr),
        )
        timed_out = False
        try:
            await asyncio.wait_for(asyncio.shield(pumps), timeout=deadline_s)
            await proc.wait()
        except asyncio.TimeoutError:
            timed_out = True
            await self._terminate(proc)
            pumps.cancel()
        finally:
            try:
                await pumps
            except (asyncio.CancelledError, Exception):
                pass

        elapsed = round(time.time() - started, 2)
        # A provider can be productive without being source-bearing. Battle may
        # read model synthesis only when at least one source-bearing item landed.
        productive = sorted(p for p, s in providers.items() if isinstance(s, dict) and s.get("ok"))
        source_bearing = sorted(
            p
            for p, s in providers.items()
            if isinstance(s, dict) and int(s.get("source_bearing_evidence_count") or 0) > 0
        )
        source_bearing_evidence_count = sum(
            int(s.get("source_bearing_evidence_count") or 0)
            for s in providers.values()
            if isinstance(s, dict)
        )
        knowledge = "\n".join(stdout_chunks)
        research_evidence_sufficient = source_bearing_evidence_count > 0

        result: dict[str, Any] = {
            "success": research_evidence_sufficient,
            "query": query,
            "preset": self.dogpile_preset,
            "results": knowledge,
            "providers": providers,
            "productive_providers": productive,
            "provider_count": len(productive),
            "productive_provider_count": len(productive),
            "source_bearing_providers": source_bearing,
            "source_bearing_provider_count": len(source_bearing),
            "source_bearing_evidence_count": source_bearing_evidence_count,
            "model_synthesis_present": model_synthesis_present,
            "research_evidence_sufficient": research_evidence_sufficient,
            "complete": finish_status == "completed" and not timed_out,
            "timed_out": timed_out,
            "returncode": proc.returncode,
            "elapsed_s": elapsed,
            "budget_remaining": remaining,
        }
        if not research_evidence_sufficient:
            result["error"] = (
                "research_degraded_no_sources"
                if not timed_out
                else f"deadline {deadline_s}s hit before any source-bearing provider landed"
            )

        _console_print(
            f"[dim]Research {'partial' if timed_out else 'complete'} in {elapsed}s — "
            f"{len(productive)} productive provider(s), "
            f"{len(source_bearing)} source-bearing provider(s): {', '.join(source_bearing) or 'none'}[/dim]"
        )
        return result

    def research(
        self,
        query: str,
        force: bool = False,
        deadline_s: int = DEFAULT_RESEARCH_DEADLINE_S,
    ) -> dict[str, Any]:
        """Synchronous wrapper around :meth:`research_async`.

        Battle rounds run in worker threads, so each call gets its own loop.
        """
        return asyncio.run(self.research_async(query, force=force, deadline_s=deadline_s))

    async def research_many_async(
        self,
        queries: Iterable[str],
        force: bool = False,
        deadline_s: int = DEFAULT_RESEARCH_DEADLINE_S,
    ) -> list[dict[str, Any]]:
        """Run several bounded searches concurrently under one shared deadline.

        Each query still costs one budget call. Total wall-clock is the slowest
        single search rather than their sum.
        """
        queries = list(queries)
        tasks = [self.research_async(q, force=force, deadline_s=deadline_s) for q in queries]
        settled = await asyncio.gather(*tasks, return_exceptions=True)
        out: list[dict[str, Any]] = []
        for query, item in zip(queries, settled):
            if isinstance(item, BaseException):
                out.append({"success": False, "error": str(item), "query": query})
            else:
                out.append(item)
        return out

    def research_many(
        self,
        queries: Iterable[str],
        force: bool = False,
        deadline_s: int = DEFAULT_RESEARCH_DEADLINE_S,
    ) -> list[dict[str, Any]]:
        """Synchronous wrapper around :meth:`research_many_async`."""
        queries = list(queries)
        return asyncio.run(self.research_many_async(queries, force=force, deadline_s=deadline_s))

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
            _console_print("[yellow]Taxonomy skill not available[/yellow]")
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
        if last_n_rounds <= 0 or self.current_round <= 0:
            return episodes
        start_round = max(1, self.current_round - last_n_rounds + 1)
        for round_num in range(self.current_round, start_round - 1, -1):
            round_query = f"Round {round_num} {self.team} team"
            result = self.recall(round_query, k=1, threshold=0.1)
            if result.get("found"):
                episodes.append(result)

        return episodes
