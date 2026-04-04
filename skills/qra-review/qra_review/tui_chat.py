"""Embry chat handler for /qra-review TUI.

Dispatches:
  /dogpile <query>     → subprocess to dogpile skill
  /create-figure <args> → subprocess to create-figure skill
  /memory recall <q>   → graph_memory.agent_cli recall
  /taxonomy extract <t> → taxonomy extraction
  Free text            → /scillm with QRA context

PersonaPlex voice (graceful fallback):
  D-Bus org.embry.Voice.Speak when available, text-only otherwise.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from loguru import logger

# Paths
_PI_SKILLS = Path(__file__).parent.parent.parent
_MEMORY_SRC = str(Path(__file__).parent.parent.parent.parent.parent.parent / "memory" / "src")


class EmbryChatHandler:
    """Handles chat input from the TUI right pane."""

    def handle(self, text: str, qra_doc: dict) -> str:
        """Route user input to appropriate handler. Returns formatted response."""
        text = text.strip()
        if not text:
            return ""

        if text.startswith("/dogpile "):
            return self._dogpile(text[9:].strip(), qra_doc)
        elif text.startswith("/create-figure "):
            return self._create_figure(text[15:].strip())
        elif text.startswith("/memory recall "):
            return self._memory_recall(text[15:].strip())
        elif text.startswith("/memory "):
            return self._memory_recall(text[8:].strip())
        elif text.startswith("/taxonomy extract "):
            return self._taxonomy_extract(text[18:].strip())
        elif text.startswith("/taxonomy "):
            return self._taxonomy_extract(text[10:].strip())
        else:
            return self._embry_chat(text, qra_doc)

    def _dogpile(self, query: str, qra_doc: dict) -> str:
        """Run /dogpile via subprocess."""
        control = qra_doc.get("control_id", "")
        full_query = f"{control} {query}" if control else query
        try:
            skill_dir = _PI_SKILLS / "dogpile"
            run_sh = skill_dir / "run.sh"
            if not run_sh.exists():
                return "[dim]dogpile skill not found[/dim]"
            result = subprocess.run(
                [str(run_sh), full_query],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                # Truncate for TUI display
                output = result.stdout.strip()[:1000]
                return f"[#3b82f6]Dogpile:[/#3b82f6]\n{output}"
            return f"[red]dogpile error: {result.stderr[:200]}[/red]"
        except subprocess.TimeoutExpired:
            return "[yellow]dogpile timed out (60s)[/yellow]"
        except Exception as e:
            return f"[red]dogpile failed: {e}[/red]"

    def _create_figure(self, args: str) -> str:
        """Run /create-figure via subprocess."""
        try:
            skill_dir = _PI_SKILLS / "create-figure"
            run_sh = skill_dir / "run.sh"
            if not run_sh.exists():
                return "[dim]create-figure skill not found[/dim]"
            result = subprocess.run(
                [str(run_sh)] + args.split(),
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return f"[#22c55e]Figure:[/#22c55e]\n{result.stdout.strip()[:500]}"
            return f"[red]create-figure error: {result.stderr[:200]}[/red]"
        except Exception as e:
            return f"[red]create-figure failed: {e}[/red]"

    def _memory_recall(self, query: str) -> str:
        """Run /memory recall via agent_cli."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "graph_memory.agent_cli", "recall", "--query", query, "--limit", "3"],
                capture_output=True, text=True, timeout=15,
                env={**__import__("os").environ, "PYTHONPATH": _MEMORY_SRC},
            )
            if result.returncode == 0:
                return f"[#3b82f6]Memory:[/#3b82f6]\n{result.stdout.strip()[:800]}"
            return f"[dim]No recall results[/dim]"
        except Exception as e:
            return f"[red]memory recall failed: {e}[/red]"

    def _taxonomy_extract(self, text: str) -> str:
        """Run /taxonomy extract via agent_cli."""
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m", "graph_memory.agent_cli",
                    "taxonomy-extract", "--text", text[:500], "--vocabulary", "sparta",
                ],
                capture_output=True, text=True, timeout=10,
                env={**__import__("os").environ, "PYTHONPATH": _MEMORY_SRC},
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                conceptual = data.get("conceptual_tags", [])
                tactical = data.get("tactical_tags", [])
                return (
                    f"[#3b82f6]Taxonomy:[/#3b82f6]\n"
                    f"  Tier 0: {conceptual}\n"
                    f"  Tier 1: {tactical}"
                )
            return "[dim]No taxonomy tags extracted[/dim]"
        except Exception as e:
            return f"[red]taxonomy failed: {e}[/red]"

    def _embry_chat(self, text: str, qra_doc: dict) -> str:
        """Free-text chat with Embry persona via /scillm."""
        control = qra_doc.get("control_id", "?")
        grade = qra_doc.get("assessment_grade", "?")
        notes = qra_doc.get("assessment_notes", [])
        question = qra_doc.get("question", "")[:200]
        answer = qra_doc.get("answer", "")[:300]

        system_prompt = (
            "You are Embry, a quality assessment assistant for SPARTA QRAs. "
            f"Current QRA: control={control}, grade={grade}, notes={notes}. "
            f"Question: {question}. Answer excerpt: {answer}. "
            "Help the reviewer understand whether to accept, reject, or amend this QRA. "
            "Be concise and direct."
        )

        try:
            # Try /scillm via subprocess
            skill_dir = _PI_SKILLS / "scillm"
            run_sh = skill_dir / "run.sh"
            if run_sh.exists():
                result = subprocess.run(
                    [str(run_sh), "complete", "--system", system_prompt, "--prompt", text],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    return result.stdout.strip()[:600]

            # Fallback: just echo context
            return (
                f"[dim]Embry (offline): {control} is {grade}. "
                f"Notes: {'; '.join(notes[:3])}. "
                f"Connect /scillm for live chat.[/dim]"
            )
        except Exception as e:
            return f"[dim]Embry unavailable: {e}[/dim]"

    @staticmethod
    def try_voice(text: str, emotion: str = "embry_confident") -> None:
        """Attempt PersonaPlex voice via D-Bus (graceful fallback)."""
        try:
            import dbus
            bus = dbus.SessionBus()
            voice = bus.get_object("org.embry.Voice", "/org/embry/Voice")
            iface = dbus.Interface(voice, "org.embry.Voice")
            iface.Speak(text, emotion)
        except Exception:
            pass  # Voice unavailable — text-only, no error
