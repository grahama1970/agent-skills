"""ConversationOrchestrator — main event loop for real-time two-way voice.

Wires together: Listener (VAD+Whisper), Thinker (LLM+Memory+Mood),
Speaker (PersonaPlex TTS), Idler (humming+backchannels), EmotionStateMachine,
AudioMixer, and SurfaceAdapter into a concurrent async pipeline.

State machine:
  IDLE → LISTENING → THINKING → SPEAKING → IDLE
  SPEAKING → INTERRUPTED → LISTENING (barge-in)
  IDLE (>5s) → idler kicks in
"""

from __future__ import annotations

import asyncio
import os
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np

from loguru import logger as log

from emotion import EmotionState, EmotionStateMachine
from idler import Idler, IdleResult
from listener import Listener, TranscriptionResult
from mixer import AudioMixer
from speaker import Speaker, SpeakChunk
from surfaces import SurfaceAdapter
from thinker import Thinker, ThinkResult
from scenario_bridge import AsyncScenarioExecutor, ScenarioStepResult
from traverser import TaxonomyTraverser


class ConversationState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"


@dataclass
class ConversationTurn:
    """A single conversation turn for the session log."""
    role: str  # "user" or "persona"
    text: str
    timestamp: float
    emotion: str = ""
    register: str = ""
    taxonomy: dict = field(default_factory=dict)
    was_interrupted: bool = False
    idle_behavior: str = ""
    latency_ms: int = 0


@dataclass
class SessionConfig:
    """Configuration for a conversation session."""
    persona: str = "embry"
    surface: str = "kde"
    mode: str = "live"  # "live" (PersonaPlex) or "recorded" (Qwen3-TTS)
    user_id: str = "default"
    duration: Optional[float] = None  # max duration in seconds, None = infinite
    scenario: Optional[str] = None  # path to surf-qml scenario YAML
    session_dir: Optional[Path] = None  # override session storage path


# Default session storage
SESSION_BASE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "converse-sessions"


class ConversationOrchestrator:
    """Main orchestrator for real-time two-way voice conversation.

    Runs four concurrent coroutines:
    1. _listen_loop: VAD + transcription
    2. _idle_loop: humming, backchannels, self-talk
    3. _emotion_decay_loop: gradual return to baseline
    4. _process_loop: think + speak pipeline
    """

    def __init__(self, config: SessionConfig):
        self.config = config
        self.session_id = f"{config.persona}-{int(time.time())}"
        self.state = ConversationState.IDLE
        self._last_state_change = time.time()
        self._last_speech_time = time.time()

        # Standard OS operation: Federated Taxonomy graph traverser
        self.traverser = TaxonomyTraverser()

        # Core components
        self.emotion = EmotionStateMachine(persona=config.persona)
        self.listener = Listener(
            on_speech=self._on_speech,
            on_barge_in=self._on_barge_in,
        )
        self.thinker = Thinker(persona=config.persona, user_id=config.user_id)
        self.speaker = Speaker(persona=config.persona, mode=config.mode)
        self.idler = Idler(persona=config.persona)
        self.mixer = AudioMixer(sample_rate=48000)
        self.surface = SurfaceAdapter.create(config.surface)

        # Mixer channels
        self.mixer.add_channel("speech", volume=1.0)
        self.mixer.add_channel("humming", volume=0.6)
        self.mixer.add_channel("background", volume=0.2)

        # Session state
        self.turns: list[ConversationTurn] = []
        self._speech_queue: asyncio.Queue[TranscriptionResult] = asyncio.Queue()
        self._interrupted_context: Optional[str] = None
        self._running = False
        self._start_time = 0.0

        # Session storage
        self._session_dir = config.session_dir or (SESSION_BASE / config.persona / self.session_id)

        # Scenario runner attachment
        self._scenario_runner = None
        self._scenario_executor: Optional[AsyncScenarioExecutor] = None

    async def run(self):
        """Main entry point: connect to surface and run concurrent loops."""
        self._running = True
        self._start_time = time.time()
        self._session_dir.mkdir(parents=True, exist_ok=True)

        log.info(f"Starting conversation: persona={self.config.persona}, "
                 f"surface={self.config.surface}, mode={self.config.mode}, "
                 f"session={self.session_id}")

        try:
            async with self.surface.connect():
                tasks = {
                    asyncio.create_task(self._idle_loop(), name="idle"),
                    asyncio.create_task(self._emotion_decay_loop(), name="emotion_decay"),
                    asyncio.create_task(self._output_loop(), name="output"),
                }

                # Scenario mode: Embry works and talks solo
                # Conversation mode: full listen + process pipeline
                if self._scenario_executor:
                    tasks.add(asyncio.create_task(self._scenario_loop(), name="scenario"))
                tasks.add(asyncio.create_task(self._listen_loop(), name="listen"))
                tasks.add(asyncio.create_task(self._process_loop(), name="process"))

                if self.config.duration:
                    tasks.add(asyncio.create_task(self._duration_watchdog()))

                # Wait for tasks — scenario loop sets _running=False when done
                while self._running and tasks:
                    done, tasks = await asyncio.wait(
                        tasks, return_when=asyncio.FIRST_COMPLETED, timeout=2.0,
                    )
                    for task in done:
                        if task.exception():
                            log.error(f"Task {task.get_name()} failed: {task.exception()}")
                            self._running = False

                # Cancel remaining tasks
                for task in tasks:
                    task.cancel()
        except asyncio.CancelledError:
            log.info("Conversation cancelled")
        finally:
            self._running = False
            self.emotion.stop()
            await self._save_session()
            log.info(f"Conversation ended: {len(self.turns)} turns, "
                     f"duration={time.time() - self._start_time:.0f}s")

    async def _listen_loop(self):
        """Continuously listen to audio from surface, run VAD + STT."""
        audio_stream = self.surface.read_audio()
        await self.listener.listen(audio_stream)

    async def _process_loop(self):
        """Process speech transcriptions: think + speak."""
        while self._running:
            try:
                result = await asyncio.wait_for(self._speech_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            self._set_state(ConversationState.THINKING)

            # Log user turn — extract taxonomy and store in graph
            user_bridges = self.traverser.extract_bridges(result.text)
            user_taxonomy = {"bridge_tags": user_bridges, "method": "traverser"}
            self.turns.append(ConversationTurn(
                role="user",
                text=result.text,
                timestamp=result.timestamp,
                taxonomy=user_taxonomy,
            ))
            log.info(f"User: {result.text}")
            # Store utterance in ArangoDB graph, connected by Federated Taxonomy
            await self.traverser.log_utterance(
                result.text, "user", user_bridges,
                emotion=self.emotion.state.value, session_id=self.session_id,
            )

            # Think
            think_result = await self.thinker.think(
                result.text,
                self.emotion,
                interrupted_context=self._interrupted_context,
            )
            self._interrupted_context = None

            # Speak
            self._set_state(ConversationState.SPEAKING)
            self.listener.is_playing = True
            self.mixer.duck("speech")

            chunks = await self.speaker.speak(
                think_result.text,
                register=think_result.register,
                emotion=think_result.emotion,
                on_chunk=self._on_speak_chunk,
            )

            self.listener.is_playing = False
            self.mixer.unduck()

            # Log persona turn
            self.turns.append(ConversationTurn(
                role="persona",
                text=think_result.text,
                timestamp=time.time(),
                emotion=think_result.emotion.value,
                register=think_result.register,
                taxonomy=think_result.taxonomy,
                was_interrupted=think_result.interrupted,
                latency_ms=think_result.latency_ms,
            ))
            log.info(f"Embry [{think_result.register}]: {think_result.text}")
            # Store persona utterance in graph
            await self.traverser.log_utterance(
                think_result.text, "persona",
                think_result.taxonomy.get("bridge_tags", []),
                emotion=think_result.emotion.value, session_id=self.session_id,
            )

            self._set_state(ConversationState.IDLE)
            self._last_speech_time = time.time()

    async def _idle_loop(self):
        """Run idle behaviors during conversation pauses."""
        while self._running:
            await asyncio.sleep(3.0)

            if self.state != ConversationState.IDLE:
                continue

            silence_duration = time.time() - self._last_speech_time
            result = await self.idler.idle_tick(self.emotion, silence_duration)

            if result is None:
                continue

            # Handle idle output
            if result.audio_path and result.audio_path.exists():
                # Play pre-generated audio (RVC humming)
                audio = self._load_audio_file(result.audio_path)
                if audio is not None:
                    self.mixer.duck("humming")
                    self.mixer.write("humming", audio)
            elif result.should_speak:
                # Use Speaker for vocal idle behaviors (backchannels, self-talk)
                # Use special Moshi tokens for non-verbal sounds
                speak_text = self._prepare_idle_text(result)
                chunks = await self.speaker.speak(
                    speak_text,
                    register=result.register,
                    emotion=self.emotion.state,
                )
                for chunk in chunks:
                    self.mixer.write("humming", chunk.audio)

            # Log idle behavior
            if result.behavior != "silence":
                self.turns.append(ConversationTurn(
                    role="persona",
                    text=result.text,
                    timestamp=time.time(),
                    emotion=self.emotion.state.value,
                    idle_behavior=result.behavior,
                ))
                log.debug(f"Idle [{result.behavior}]: {result.text}")

    async def _emotion_decay_loop(self):
        """Gradual emotional return to baseline."""
        await self.emotion.decay_loop()

    async def _output_loop(self):
        """Mix all audio channels and write to surface."""
        frame_size = 960  # 20ms at 48kHz
        while self._running:
            if self.mixer.any_active:
                mixed = self.mixer.mix_fast(frame_size)
                await self.surface.write_audio(mixed)
            else:
                await asyncio.sleep(0.01)  # 10ms idle

    async def _duration_watchdog(self):
        """Stop conversation after configured duration."""
        await asyncio.sleep(self.config.duration)
        log.info(f"Duration limit reached ({self.config.duration}s)")
        self._running = False

    # -- Callbacks --

    def _on_speech(self, result: TranscriptionResult):
        """Callback from Listener when speech is transcribed."""
        self._set_state(ConversationState.LISTENING)
        self._speech_queue.put_nowait(result)

    def _on_barge_in(self):
        """Callback from Listener when user interrupts persona."""
        if self.state == ConversationState.SPEAKING:
            log.info("Barge-in: interrupting persona speech")
            # Save what we were saying as interrupted context
            if self.turns and self.turns[-1].role == "persona":
                self._interrupted_context = self.turns[-1].text
            self._set_state(ConversationState.INTERRUPTED)
            self.listener.is_playing = False
            # Duck everything immediately
            self.mixer.duck("barge_in", fade_ms=50)
            # Clear speech channel
            self.mixer.clear("speech")

    def _on_speak_chunk(self, chunk: SpeakChunk):
        """Callback from Speaker for each generated audio chunk."""
        self.mixer.write("speech", chunk.audio)

    # -- Helpers --

    def _set_state(self, new_state: ConversationState):
        if self.state != new_state:
            log.debug(f"State: {self.state.value} → {new_state.value}")
            self.state = new_state
            self._last_state_change = time.time()

    def _prepare_idle_text(self, result: IdleResult) -> str:
        """Prepare idle text with Moshi-compatible special tokens for non-verbal sounds."""
        # Use labeled tokens that Moshi fine-tuning can learn
        behavior_tokens = {
            "backchannel": "[mm-hmm]",
            "sigh": "[sigh]",
            "hum_tune": "[soft hum]",
            "self_talk": "",  # self-talk uses natural text
        }
        token = behavior_tokens.get(result.behavior, "")
        if token and result.text.startswith("*"):
            # Replace stage directions with Moshi tokens
            return f"{token} {result.text.strip('*')}"
        return result.text

    def _load_audio_file(self, path: Path) -> Optional[np.ndarray]:
        """Load audio file as int16 numpy array."""
        try:
            import wave
            with wave.open(str(path), "rb") as wf:
                raw = wf.readframes(wf.getnframes())
                return np.frombuffer(raw, dtype=np.int16)
        except Exception as e:
            logger.debug("file read failed: {}", e)
        # Fallback: try ffmpeg
        try:
            import subprocess
            result = subprocess.run(
                ["ffmpeg", "-i", str(path), "-f", "s16le", "-ar", "48000",
                 "-ac", "1", "-"],
                capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                return np.frombuffer(result.stdout, dtype=np.int16)
        except Exception as e:
            logger.debug("result extraction failed: {}", e)
        return None

    # -- Scenario Integration --

    async def attach_scenario(self, scenario_path: str):
        """Wire surf-qml scenario execution into the conversation loop.

        Creates an AsyncScenarioExecutor that runs AT-SPI steps in a thread
        and emits ScenarioStepResult events. The _scenario_loop() coroutine
        consumes these events and has Embry speak about each step through
        her thinker → speaker → mixer pipeline.
        """
        log.info(f"Attaching scenario: {scenario_path}")
        self._scenario_executor = AsyncScenarioExecutor(scenario_path)
        self._scenario_runner = scenario_path

    async def _scenario_loop(self):
        """Execute scenario steps and narrate through the conversation pipeline.

        For each step:
        1. Wait for step result from executor
        2. Update emotion based on outcome
        3. Speak narration through speaker → mixer → surface
        4. Between steps, idle loop can still fire (humming)
        """
        executor = self._scenario_executor
        if not executor:
            return

        # Start scenario execution as a concurrent task
        exec_task = asyncio.create_task(executor.run(), name="scenario_exec")

        try:
            while self._running:
                try:
                    result: ScenarioStepResult = await asyncio.wait_for(
                        executor.queue.get(), timeout=2.0,
                    )
                except asyncio.TimeoutError:
                    # Check if executor finished
                    if exec_task.done():
                        break
                    continue

                # Update emotion from step outcome
                if result.emotion_hint:
                    self.emotion.update(result.emotion_hint, 0.7, trigger=f"scenario_{result.action}")

                # Speak narration if there is one
                if result.narration:
                    self._set_state(ConversationState.SPEAKING)
                    self.listener.is_playing = True
                    self.mixer.duck("speech")

                    log.info(f"Embry [scenario]: {result.narration}")

                    chunks = await self.speaker.speak(
                        result.narration,
                        register=self._scenario_register(),
                        emotion=self.emotion.state,
                        on_chunk=self._on_speak_chunk,
                    )

                    self.listener.is_playing = False
                    self.mixer.unduck()

                    # Log as persona turn
                    bridges = self.traverser.extract_bridges(result.narration)
                    self.turns.append(ConversationTurn(
                        role="persona",
                        text=result.narration,
                        timestamp=time.time(),
                        emotion=self.emotion.state.value,
                        register=self._scenario_register(),
                        taxonomy={"bridge_tags": bridges, "source": "scenario",
                                  "step": result.step_num, "action": result.action},
                    ))

                    # Store in graph
                    await self.traverser.log_utterance(
                        result.narration, "persona", bridges,
                        emotion=self.emotion.state.value, session_id=self.session_id,
                    )

                    self._set_state(ConversationState.IDLE)
                    self._last_speech_time = time.time()

                    # Pause between steps so idle loop can hum
                    if not result.is_final:
                        await asyncio.sleep(1.5)
                else:
                    # Silent step — still update last speech time
                    # so idle behaviors stay active
                    pass

                if result.is_final:
                    log.info("Scenario complete")
                    # Final summary narration
                    await self._narrate_scenario_complete(result)
                    break

        except asyncio.CancelledError:
            executor.stop()
            raise
        finally:
            if not exec_task.done():
                exec_task.cancel()
            # In solo scenario mode (no duration set), end session when scenario finishes
            if not self.config.duration:
                log.info("Scenario finished — ending session")
                self._running = False

    async def _narrate_scenario_complete(self, last_result: ScenarioStepResult):
        """Embry speaks a brief summary at the end of a scenario run."""
        total = last_result.total_steps
        summary = f"Okay, that's all {total} steps done."
        if last_result.status == "ok":
            summary += " Everything looked good."
            self.emotion.update(EmotionState.PLEASED, 0.6, trigger="scenario_complete")
        else:
            summary += " There were some issues I need to flag."
            self.emotion.update(EmotionState.FOCUSED, 0.5, trigger="scenario_issues")

        self._set_state(ConversationState.SPEAKING)
        self.listener.is_playing = True
        self.mixer.duck("speech")

        await self.speaker.speak(
            summary,
            register=self._scenario_register(),
            emotion=self.emotion.state,
            on_chunk=self._on_speak_chunk,
        )

        self.listener.is_playing = False
        self.mixer.unduck()
        self._set_state(ConversationState.IDLE)
        self._last_speech_time = time.time()

        self.turns.append(ConversationTurn(
            role="persona", text=summary, timestamp=time.time(),
            emotion=self.emotion.state.value, register=self._scenario_register(),
            taxonomy={"bridge_tags": ["Precision"], "source": "scenario_summary"},
        ))

    def _scenario_register(self) -> str:
        """Pick voice register based on current emotion during scenario."""
        state = self.emotion.state
        if state in (EmotionState.FRUSTRATED,):
            return "tense"
        if state in (EmotionState.CONFUSED, EmotionState.ANXIOUS):
            return "uncertain"
        if state in (EmotionState.WEARY,):
            return "tired"
        return "confident"

    # -- Session Persistence --

    async def _save_session(self):
        """Save session transcript and metadata."""
        if not self.turns:
            return

        try:
            # Transcript
            transcript_path = self._session_dir / "transcript.jsonl"
            with open(transcript_path, "w") as f:
                for turn in self.turns:
                    f.write(json.dumps({
                        "role": turn.role,
                        "text": turn.text,
                        "timestamp": turn.timestamp,
                        "emotion": turn.emotion,
                        "register": turn.register,
                        "taxonomy": turn.taxonomy,
                        "was_interrupted": turn.was_interrupted,
                        "idle_behavior": turn.idle_behavior,
                        "latency_ms": turn.latency_ms,
                    }) + "\n")

            # Emotion log
            emotion_path = self._session_dir / "emotion_log.json"
            emotion_path.write_text(json.dumps([
                {
                    "state": s.state.value,
                    "intensity": round(s.intensity, 3),
                    "bridge_scores": {k: round(v, 3) for k, v in s.bridge_scores.items()},
                    "timestamp": s.timestamp,
                    "trigger": s.trigger,
                }
                for s in self.emotion.history
            ], indent=2))

            # Session summary
            summary = {
                "session_id": self.session_id,
                "persona": self.config.persona,
                "surface": self.config.surface,
                "mode": self.config.mode,
                "duration_s": round(time.time() - self._start_time, 1),
                "turn_count": len(self.turns),
                "user_turns": sum(1 for t in self.turns if t.role == "user"),
                "persona_turns": sum(1 for t in self.turns if t.role == "persona"),
                "idle_behaviors": sum(1 for t in self.turns if t.idle_behavior),
                "interruptions": sum(1 for t in self.turns if t.was_interrupted),
                "emotion_transitions": len(self.emotion.history),
                "final_emotion": self.emotion.state.value,
            }
            summary_path = self._session_dir / "session_summary.json"
            summary_path.write_text(json.dumps(summary, indent=2))

            log.info(f"Session saved to {self._session_dir}")
        except Exception as e:
            log.error(f"Failed to save session: {e}")


# -- CLI Entry Point --

def main(
    persona: str = typer.Option("embry", help="Persona name"),
    surface: str = typer.Option("kde", help="Audio surface (discord, kde, horus)"),
    mode: str = typer.Option("live", help="TTS mode: live (PersonaPlex) or recorded (Qwen3-TTS)"),
    user_id: str = typer.Option("default", help="User identifier"),
    duration: Optional[float] = typer.Option(None, help="Max conversation duration in seconds"),
    scenario: Optional[str] = typer.Option(None, help="Path to surf-qml scenario YAML"),
) -> None:
    """Real-time two-way voice conversation."""
    config = SessionConfig(
        persona=persona,
        surface=surface,
        mode=mode,
        user_id=user_id,
        duration=duration,
        scenario=scenario,
    )

    orchestrator = ConversationOrchestrator(config)

    async def _run():
        if scenario:
            await orchestrator.attach_scenario(scenario)
        await orchestrator.run()

    asyncio.run(_run())


if __name__ == "__main__":
    import typer
    typer.run(main)
