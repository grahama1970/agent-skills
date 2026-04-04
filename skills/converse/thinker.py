"""Response generation pipeline for real-time conversation.

Orchestrates: D-Bus agent (primary) + EmbrySPARTAIntern (fallback) +
memory recall + mood + steering presets + trigger handling +
interruption weaving. Produces a ThinkResult that Speaker consumes.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from loguru import logger as log

from emotion import EmotionState, EmotionStateMachine, TriggerResult
from traverser import TaxonomyTraverser

# Skill roots for imports
SKILLS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILLS_ROOT / "common"))
sys.path.insert(0, str(SKILLS_ROOT / "train-convo-steering"))


@dataclass
class ThinkResult:
    """Output from the thinking pipeline, consumed by Speaker."""
    text: str
    register: str  # voice register: "confident", "uncertain", "tired", etc.
    preset: Optional[str] = None  # steering preset id
    mood: str = ""  # mood context string
    emotion: EmotionState = EmotionState.NEUTRAL
    bridge_scores: dict[str, float] = field(default_factory=dict)
    taxonomy: dict[str, Any] = field(default_factory=dict)
    interrupted: bool = False
    latency_ms: int = 0


# Deflection templates for avoidance triggers
DEFLECTION_TEMPLATES = {
    "hard": [
        "I... let's talk about something else.",
        "Hmm. Yeah. Anyway—what were you working on?",
        "*goes quiet for a moment* ...So, um. Different topic?",
        "I don't really want to go there right now.",
    ],
    "soft": [
        "That's... yeah. *shifts slightly* What else is going on?",
        "Mmm. *pause* I was actually thinking about something else.",
        "Right. *trails off briefly* Hey, did you see—never mind. What's up?",
    ],
}

# Interruption acknowledgment fragments
INTERRUPTION_ACKS = [
    "Oh—sorry, go ahead.",
    "Wait, yeah—what?",
    "Oh, you were saying—",
    "Mm, sorry. What?",
    "—oh. Go on.",
]


class Thinker:
    """Response generation pipeline with memory, mood, and steering.

    Produces ThinkResult from user text + emotional context.
    Uses D-Bus agent (primary) with EmbrySPARTAIntern fallback,
    plus memory recall, persona journal mood, and conversation
    steering presets.
    """

    def __init__(self, persona: str = "embry", user_id: str = "default"):
        self.persona = persona
        self.user_id = user_id
        self.session_id = f"converse-{persona}-{int(time.time())}"
        self.consecutive_failures = 0
        self.turn_count = 0

        # Graph traverser — the standard OS operation
        self.traverser = TaxonomyTraverser()

        # Lazy-loaded components
        self._intern = None
        self._memory = None
        self._tom_memory = None

    def _get_intern(self):
        """Lazy-load EmbrySPARTAIntern."""
        if self._intern is None:
            try:
                from brandon_simulacrum import EmbrySPARTAIntern
                self._intern = EmbrySPARTAIntern()
                log.info("Loaded EmbrySPARTAIntern")
            except Exception as e:
                log.warning(f"EmbrySPARTAIntern unavailable: {e}")
        return self._intern

    def _get_memory(self):
        """Lazy-load MemoryClient for persona scope."""
        if self._memory is None:
            try:
                from memory_client import MemoryClient, MemoryScope
                self._memory = MemoryClient(scope=MemoryScope.PERSONA)
                log.info("Loaded MemoryClient (persona)")
            except Exception as e:
                log.warning(f"MemoryClient unavailable: {e}")
        return self._memory

    def _get_tom_memory(self):
        """Lazy-load MemoryClient for Theory of Mind scope."""
        if self._tom_memory is None:
            try:
                from memory_client import MemoryClient, MemoryScope
                self._tom_memory = MemoryClient(scope=MemoryScope.TOM)
                log.info("Loaded MemoryClient (ToM)")
            except Exception as e:
                log.warning(f"ToM MemoryClient unavailable: {e}")
        return self._tom_memory

    async def think(
        self,
        user_text: str,
        emotion: EmotionStateMachine,
        interrupted_context: Optional[str] = None,
    ) -> ThinkResult:
        """Generate persona response with full context pipeline.

        Steps:
        1. Get current mood from persona journal
        2. Get conversation steering preset
        3. Recall relevant memories (persona + ToM)
        4. Check for avoidance triggers
        5. Generate response via D-Bus agent or fallbacks
        6. Handle interruption weaving
        7. Detect voice register
        8. Extract taxonomy tags
        """
        t0 = time.time()
        self.turn_count += 1

        # 1. Mood context from persona journal
        mood = self._get_mood()

        # 2. Steering preset
        preset = await self._get_steering_preset(user_text)

        # 3. Graph traversal — the standard OS operation
        # Multihop through Federated Taxonomy for full context
        bridges = self.traverser.extract_bridges(user_text)
        work_context = await self.traverser.find_work_context(user_text, limit=5)
        episodes = await self.traverser.find_episodes(user_text, limit=3)
        memories = work_context.to_context(3)
        tom = episodes.to_context(2)

        # 4. Trigger check
        trigger_result = emotion.check_triggers(user_text)

        # 5. Generate response
        if trigger_result.has_avoidance_trigger:
            response = self._generate_deflection(trigger_result, emotion)
            if trigger_result.suggested_state:
                emotion.update(trigger_result.suggested_state, 0.85, trigger="avoidance")
        else:
            response = await self._generate_response(user_text, mood, memories, tom, preset)

        # 6. Interruption handling
        if interrupted_context:
            response = self._handle_interruption(response, interrupted_context)

        # 7. Detect register
        register = self._detect_register(response, emotion)

        # Update emotion from user text context
        emotion.update_from_context(user_text, self.consecutive_failures)

        # 8. Taxonomy extraction
        taxonomy = self._extract_taxonomy(response)

        latency_ms = int((time.time() - t0) * 1000)
        log.info(f"Think completed in {latency_ms}ms: register={register}, preset={preset}")

        return ThinkResult(
            text=response,
            register=register,
            preset=preset,
            mood=mood,
            emotion=emotion.state,
            bridge_scores=dict(emotion.bridge_scores),
            taxonomy=taxonomy,
            interrupted=interrupted_context is not None,
            latency_ms=latency_ms,
        )

    def _get_mood(self) -> str:
        """Get persona mood context from journal."""
        try:
            from persona_journal import get_mood_for_response
            return get_mood_for_response(self.persona)
        except Exception as e:
            log.debug(f"Mood unavailable: {e}")
            return ""

    async def _get_steering_preset(self, user_text: str) -> Optional[str]:
        """Get conversation steering preset via CLI."""
        try:
            steering_script = SKILLS_ROOT / "train-convo-steering" / "run.sh"
            if not steering_script.exists():
                return None
            proc = await asyncio.create_subprocess_exec(
                str(steering_script), "runtime-step",
                "--user-id", self.user_id,
                "--channel", "voice",
                "--user-text", user_text,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=str(steering_script.parent),
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            if proc.returncode == 0 and stdout:
                # Parse preset from output (expected: preset_id on first line)
                return stdout.decode().strip().split("\n")[0].strip()
        except Exception as e:
            log.debug(f"Steering unavailable: {e}")
        return None

    def _recall_memories(self, query: str) -> str:
        """Recall relevant persona memories."""
        mem = self._get_memory()
        if not mem:
            return ""
        try:
            result = mem.recall(query, k=3)
            if result.found:
                return result.to_context(max_items=3)
        except Exception as e:
            log.debug(f"Memory recall failed: {e}")
        return ""

    def _recall_tom(self, query: str) -> str:
        """Recall Theory of Mind observations about user."""
        mem = self._get_tom_memory()
        if not mem:
            return ""
        try:
            result = mem.recall(f"user preferences {self.user_id}: {query}", k=2)
            if result.found:
                return result.to_context(max_items=2)
        except Exception as e:
            log.debug(f"ToM recall failed: {e}")
        return ""

    async def _generate_response(
        self,
        user_text: str,
        mood: str,
        memories: str,
        tom: str,
        preset: Optional[str],
    ) -> str:
        """Generate response via D-Bus agent (primary) or fallbacks."""
        # Primary: D-Bus agent — persona-aware via ask_as
        prompt = self._build_dbus_prompt(user_text, mood, memories)
        try:
            from embry_agent_client import EmbryAgentClient
            async with EmbryAgentClient() as client:
                response = await asyncio.wait_for(
                    client.ask_as("embry", prompt), timeout=30.0
                )
                if response.strip():
                    self.consecutive_failures = 0
                    return response.strip()
        except Exception as e:
            log.debug(f"D-Bus agent primary failed: {e}")

        # Fallback 1: EmbrySPARTAIntern (local, no D-Bus)
        intern = self._get_intern()
        if intern:
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, intern.respond, user_text, self.user_id,
                )
                if result.get("response"):
                    self.consecutive_failures = 0
                    return result["response"]
            except Exception as e:
                log.warning(f"Intern response failed: {e}")
                self.consecutive_failures += 1

        # Fallback 2: Ollama direct
        return await self._ollama_fallback(prompt)

    def _build_dbus_prompt(self, user_text: str, mood: str, memories: str) -> str:
        """Build the persona prompt used for D-Bus and Ollama fallback."""
        return f"""You are Embry, a sharp, warm persona who code-switches between
Charleston charm, Hawaiian warmth, and Yale precision. Keep responses
conversational and natural for voice — short sentences, contractions,
natural pauses marked with '...'.

{mood}

{f'Relevant context: {memories}' if memories else ''}

User said: {user_text}

Embry's response (conversational, 1-3 sentences):"""

    async def _ollama_fallback(self, prompt: str) -> str:
        """Last-resort response via local Ollama."""
        try:
            import httpx
            resp = httpx.post(
                "http://127.0.0.1:11434/api/generate",
                json={"model": "llama3.1:8b", "prompt": prompt, "stream": False},
                timeout=15.0,
            )
            if resp.status_code == 200:
                return resp.json().get("response", "").strip()
        except Exception as e:
            log.warning(f"Ollama fallback failed: {e}")

        self.consecutive_failures += 1
        return "Hmm... I lost my train of thought. What were you saying?"

    def _generate_deflection(self, trigger: TriggerResult, emotion: EmotionStateMachine) -> str:
        """Generate avoidance deflection for trauma triggers."""
        import random
        templates = DEFLECTION_TEMPLATES.get(trigger.severity, DEFLECTION_TEMPLATES["soft"])
        return random.choice(templates)

    def _handle_interruption(self, response: str, interrupted_context: str) -> str:
        """Weave interruption acknowledgment into response."""
        import random
        ack = random.choice(INTERRUPTION_ACKS)
        return f"{ack} {response}"

    def _detect_register(self, text: str, emotion: EmotionStateMachine) -> str:
        """Detect appropriate voice register from text + emotion."""
        try:
            from personaplex import detect_register, PersonaPlexConfig
            config_path = SKILLS_ROOT / "create-persona" / "src" / "personaplex.py"
            # Use the function with context dict
            return detect_register(text, {
                "time": time.localtime().tm_hour,
                "failure_count": self.consecutive_failures,
                "emotion": emotion.state.value,
            })
        except Exception as e:
            logger.debug("value extraction failed: {}", e)

        # Fallback heuristic
        state = emotion.state
        if state in (EmotionState.ANXIOUS, EmotionState.CONFUSED, EmotionState.OVERWHELMED):
            return "uncertain"
        if state in (EmotionState.WEARY, EmotionState.MELANCHOLIC):
            return "tired"
        if state in (EmotionState.FRUSTRATED,):
            return "tense"
        return "confident"

    def _extract_taxonomy(self, text: str) -> dict:
        """Extract Federated Taxonomy bridge attribute tags via traverser."""
        bridges = self.traverser.extract_bridges(text)
        return {"bridge_tags": bridges, "method": "traverser"}
