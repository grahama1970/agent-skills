#!/usr/bin/env python3
"""
Narration engine for surf-qml scenarios.

Two voice modes:
  - LIVE: PersonaPlex (Moshi-based streaming TTS with emotional state)
          Used for real-time collaboration where the human monitors Embry.
  - RECORDED: Qwen3-TTS (high-quality offline synthesis with instruct control)
              Used for post-hoc review and archival.

Each narration is tagged with Federated Taxonomy bridge attributes.
All artifacts persist to /mnt/storage12tb/surf-qml-sessions/.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from loguru import logger

# Taxonomy: keyword extraction (~1ms) + trained DistilBERT bridge classifier (~10ms)
TAXONOMY_DIR = Path(__file__).parent.parent / "taxonomy"
BRIDGE_CLASSIFIER_DIR = Path(__file__).parent.parent / "create-classifier"
BRIDGE_INFERENCE_SCRIPT = BRIDGE_CLASSIFIER_DIR / "scripts" / "bridge_inference.py"

# Qwen3-TTS paths (recorded mode)
TTS_SKILL_DIR = Path(__file__).parent.parent / "tts-train"
TTS_RUN_SH = TTS_SKILL_DIR / "run.sh"
TTS_SERVER_URL = os.environ.get("HORUS_TTS_URL", "http://localhost:8000/v1/tts")

# PersonaPlex paths (live mode)
OVERLAY_SRC = Path(os.environ.get(
    "HORUS_OVERLAY_SRC",
    Path(__file__).resolve().parent.parent.parent.parent / "horus" / "apps" / "horus-overlay" / "src",
))
MEMORY_PROJECT_ROOT = Path(os.environ.get(
    "MEMORY_PROJECT_ROOT",
    Path(__file__).resolve().parent.parent.parent.parent / "memory",
))

# Persistent storage on 12TB drive
STORAGE_ROOT = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "surf-qml-sessions"

# Persona voice configurations
PERSONA_VOICES = {
    "embry": {
        # Qwen3-TTS instruct (recorded mode)
        "instruct": "Warm, friendly, expressive female voice. Educational and encouraging. "
                     "React naturally to what you see - show genuine emotion.",
        "speaker": "embry",
        # PersonaPlex emotional default (live mode)
        "emotional_state": "curious",
    },
    "brandon_bailey": {
        "instruct": "Professional, authoritative male voice. Direct and efficient. "
                     "Military precision in observations, impatient with poor UX.",
        "speaker": "brandon",
        "emotional_state": "focused",
    },
    "default": {
        "instruct": "Clear, neutral voice describing user interface observations.",
        "speaker": "default",
        "emotional_state": "neutral",
    },
}

# Auto-narration templates keyed by (step_type, outcome)
AUTO_REACTIONS = {
    ("find", "ok"): "Found the window. Let me take a look.",
    ("focus", "ok"): "Okay, I've got focus. Let's see what we're working with.",
    ("type", "ok"): "Typed that in. Let's see what comes up.",
    ("key", "ok"): None,  # Too frequent to narrate every key
    ("snap", "ok"): "Captured that.",
    ("verify", "ok"): "Good, that checks out.",
    ("record", "ok"): "Got the recording.",
    ("read", "ok"): None,  # Tree reads are internal

    ("find", "fail"): "I can't find that window. That's a problem.",
    ("focus", "fail"): "Hmm, I can't seem to focus that window. Where is it?",
    ("type", "fail"): "The text didn't go in. Something's blocking input.",
    ("key", "fail"): "That key press didn't work. Is something intercepting it?",
    ("snap", "fail"): "Screenshot failed. That's unexpected.",
    ("verify", "fail"): "That's not right. The element doesn't match what I expected.",
    ("record", "fail"): "Recording failed. Check if ffmpeg has display access.",
    ("click", "fail"): "I can't click that element. Is it actually there?",
}

# Richer contextual reactions
CONTEXTUAL_REACTIONS = {
    "verify_focus_fail": "Wait, where did the focus go? I expected to see a focused element but there's nothing. That's confusing.",
    "verify_role_fail": "I'm looking for a {role} element but I can't find one. Is it missing from the interface?",
    "slow_results": "That took a while. If I'm under time pressure, that delay would be frustrating.",
    "no_elements": "There's nothing here. Empty screen. That can't be right.",
    "many_elements": "Wow, there's a lot going on here. {count} elements. Let me focus on what matters.",
}


class NarrationEngine:
    """
    Generates persona voice narration with taxonomy tagging.

    Live mode (PersonaPlex):  real-time streaming TTS, human can hear and interrupt.
    Recorded mode (Qwen3-TTS): high-quality synthesis for archival and review.
    """

    def __init__(
        self,
        persona: str = "embry",
        mode: str = "live",  # "live" (PersonaPlex) or "recorded" (Qwen3-TTS)
        output_dir: Optional[Path] = None,
        session_name: Optional[str] = None,
    ):
        self.persona = persona
        self.mode = mode
        self.voice_config = PERSONA_VOICES.get(persona, PERSONA_VOICES["default"])
        self._taxonomy_available = self._check_taxonomy()
        self._bridge_classifier = None  # Lazy-loaded DistilBERT classifier
        self._narration_count = 0
        self._personaplex = None  # Lazy-loaded HorusVoiceOutput

        # Persistent storage on 12TB drive
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = session_name or f"{persona}_{timestamp}"
        self.storage_dir = STORAGE_ROOT / name
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Symlink from scenario output dir for convenience
        self.output_dir = output_dir
        if output_dir:
            narration_link = output_dir / "narration"
            if not narration_link.exists():
                try:
                    narration_link.symlink_to(self.storage_dir)
                except OSError:
                    pass

        self.session_log: list[dict] = []

        print(f"    [narration] Mode: {mode} | Persona: {persona}")
        print(f"    [narration] Storage: {self.storage_dir}")

    # ── Initialization ──────────────────────────────────────────────

    def _check_taxonomy(self) -> bool:
        if TAXONOMY_DIR.exists():
            if str(TAXONOMY_DIR) not in sys.path:
                sys.path.insert(0, str(TAXONOMY_DIR))
            try:
                from taxonomy import extract_taxonomy
                return True
            except ImportError:
                pass
        return False

    def _init_bridge_classifier(self):
        """Load DistilBERT bridge classifier for scored taxonomy (~10ms per call)."""
        if self._bridge_classifier is not None:
            return
        try:
            scripts_dir = str(BRIDGE_CLASSIFIER_DIR / "scripts")
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)
            from bridge_inference import BridgeClassifier
            self._bridge_classifier = BridgeClassifier()
            print(f"    [narration] Bridge classifier loaded (DistilBERT)")
        except Exception as e:
            print(f"    [narration] Bridge classifier unavailable: {e}")
            self._bridge_classifier = None

    def _init_personaplex(self) -> bool:
        """Lazy-load PersonaPlex for live mode."""
        if self._personaplex is not None:
            return True
        try:
            # Add overlay src to path for HorusVoiceOutput import
            if str(OVERLAY_SRC) not in sys.path:
                sys.path.insert(0, str(OVERLAY_SRC))
            # PersonaPlex needs its own path additions
            moshi_path = MEMORY_PROJECT_ROOT / "third_party" / "personaplex" / "moshi"
            if moshi_path.exists() and str(moshi_path) not in sys.path:
                sys.path.insert(0, str(moshi_path))
            if str(MEMORY_PROJECT_ROOT) not in sys.path:
                sys.path.insert(0, str(MEMORY_PROJECT_ROOT))

            from voice import HorusVoiceOutput, VoiceConfig
            config = VoiceConfig(
                voice_library_path=MEMORY_PROJECT_ROOT / "persona" / "voices",
                fallback_to_espeak=True,
            )
            self._personaplex = HorusVoiceOutput(config)
            return True
        except Exception as e:
            print(f"    [narration] PersonaPlex init failed: {e}")
            print(f"    [narration] Falling back to recorded mode")
            self.mode = "recorded"
            return False

    # ── Public API ──────────────────────────────────────────────────

    def speak(
        self,
        text: str,
        step_num: Optional[int] = None,
        context: Optional[dict] = None,
        emotional_state: Optional[str] = None,
    ) -> dict:
        """
        Generate TTS, play audio aloud, extract taxonomy tags.
        Returns metadata dict with paths and taxonomy.
        """
        self._narration_count += 1
        idx = step_num or self._narration_count
        prefix = f"{idx:02d}_narration"

        wav_path = self.storage_dir / f"{prefix}.wav"
        meta_path = self.storage_dir / f"{prefix}.json"

        emotion = emotional_state or self.voice_config.get("emotional_state", "neutral")

        # 1. Synthesize + play
        if self.mode == "live":
            tts_ok = self._speak_live(text, wav_path, emotion)
        else:
            tts_ok = self._speak_recorded(text, wav_path)
            if tts_ok and wav_path.exists():
                self._play(wav_path)

        # 2. Extract taxonomy tags
        tags = self._extract_taxonomy(text)

        # 3. Persist metadata
        meta = {
            "step": idx,
            "persona": self.persona,
            "mode": self.mode,
            "text": text,
            "emotional_state": emotion,
            "timestamp": datetime.now().isoformat(),
            "audio": str(wav_path) if tts_ok else None,
            "taxonomy": tags,
            "context": context or {},
        }

        meta_path.write_text(json.dumps(meta, indent=2))
        self.session_log.append(meta)

        return meta

    def react(
        self,
        step_type: str,
        outcome: str,
        step_num: Optional[int] = None,
        context: Optional[dict] = None,
    ) -> Optional[dict]:
        """
        Auto-generate contextual narration based on step outcome.
        Returns metadata dict or None if no narration warranted.
        """
        ctx = context or {}
        text = None
        emotion = None

        # Contextual reactions (richer than templates)
        if step_type == "verify" and outcome == "fail":
            emotion = "frustrated"
            role = ctx.get("role", "")
            state = ctx.get("state", "")
            if state == "focused":
                text = CONTEXTUAL_REACTIONS["verify_focus_fail"]
            elif role:
                text = CONTEXTUAL_REACTIONS["verify_role_fail"].format(role=role)

        if step_type == "read" and outcome == "ok":
            count = ctx.get("element_count", 0)
            if count == 0:
                text = CONTEXTUAL_REACTIONS["no_elements"]
                emotion = "confused"
            elif count > 30:
                text = CONTEXTUAL_REACTIONS["many_elements"].format(count=count)
                emotion = "overwhelmed"

        # Template reactions
        if text is None:
            text = AUTO_REACTIONS.get((step_type, outcome))
            if outcome == "fail" and emotion is None:
                emotion = "frustrated"

        if text is None:
            return None

        return self.speak(text, step_num=step_num, context=ctx, emotional_state=emotion)

    def save_session(self) -> Path:
        """Write full session log to persistent storage."""
        log_path = self.storage_dir / "session.json"
        summary = {
            "persona": self.persona,
            "mode": self.mode,
            "voice_config": self.voice_config,
            "narration_count": self._narration_count,
            "timestamp": datetime.now().isoformat(),
            "storage_dir": str(self.storage_dir),
            "taxonomy_summary": self._summarize_taxonomy(),
            "entries": self.session_log,
        }
        log_path.write_text(json.dumps(summary, indent=2))
        print(f"    [narration] Session saved: {log_path}")
        return log_path

    # ── Live Mode (PersonaPlex) ─────────────────────────────────────

    def _speak_live(self, text: str, save_path: Path, emotion: str) -> bool:
        """
        Live TTS via PersonaPlex. Streams audio to speakers in real-time
        AND saves to file for archival.
        """
        if not self._init_personaplex():
            # Fallback: use recorded mode for this utterance
            ok = self._speak_recorded(text, save_path)
            if ok and save_path.exists():
                self._play(save_path)
            return ok

        try:
            import asyncio

            # Map emotion string to PersonaPlex EmotionalState
            from voice import EmotionalState
            emotion_map = {
                "curious": EmotionalState.CURIOUS,
                "frustrated": EmotionalState.FRUSTRATED,
                "confused": EmotionalState.CONFUSED,
                "pleased": EmotionalState.PLEASED,
                "focused": EmotionalState.FOCUSED,
                "overwhelmed": EmotionalState.OVERWHELMED,
                "neutral": EmotionalState.NEUTRAL,
            }
            pp_emotion = emotion_map.get(emotion, EmotionalState.NEUTRAL)

            loop = asyncio.new_event_loop()
            try:
                # speak() plays aloud via sounddevice, synthesize_to_file() saves
                loop.run_until_complete(self._personaplex.speak(text, pp_emotion))
                # Also save a copy for archival
                loop.run_until_complete(
                    self._personaplex.synthesize_to_file(text, pp_emotion, output_path=str(save_path))
                )
            finally:
                loop.close()
            return True
        except Exception as e:
            print(f"    [narration] PersonaPlex speak failed: {e}")
            # Fallback to recorded
            ok = self._speak_recorded(text, save_path)
            if ok and save_path.exists():
                self._play(save_path)
            return ok

    # ── Recorded Mode (Qwen3-TTS) ──────────────────────────────────

    def _speak_recorded(self, text: str, output_path: Path) -> bool:
        """Generate speech via Qwen3-TTS server or CLI."""
        # Try HTTP server first (model already loaded, fast)
        try:
            import urllib.request
            payload = json.dumps({
                "text": text,
                "instruct": self.voice_config["instruct"],
                "speaker": self.voice_config["speaker"],
            }).encode()
            req = urllib.request.Request(
                TTS_SERVER_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=30)
            output_path.write_bytes(resp.read())
            return True
        except Exception as e:
            logger.debug("file read failed: {}", e)

        # CLI fallback (loads model each time, slower)
        if TTS_RUN_SH.exists():
            try:
                result = subprocess.run(
                    [str(TTS_RUN_SH), "synthesize",
                     "--text", text,
                     "--output", str(output_path)],
                    capture_output=True,
                    timeout=90,
                    cwd=str(TTS_SKILL_DIR),
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
                return result.returncode == 0 and output_path.exists()
            except Exception as e:
                logger.debug("result extraction failed: {}", e)

        # Last resort: espeak-ng
        try:
            subprocess.run(
                ["espeak-ng", "-w", str(output_path), text],
                capture_output=True, timeout=10,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            return output_path.exists()
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

        print(f"    [narration] TTS unavailable, text only: {text}")
        return False

    # ── Playback ────────────────────────────────────────────────────

    def _play(self, wav_path: Path) -> None:
        """Play audio aloud. Blocks until complete (recorded mode only)."""
        try:
            subprocess.run(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
                 str(wav_path)],
                timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
        except Exception:
            try:
                subprocess.run(["aplay", "-q", str(wav_path)], timeout=30,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
            except Exception as e:
                logger.debug("subprocess call failed: {}", e)

    # ── Taxonomy ────────────────────────────────────────────────────

    def _extract_taxonomy(self, text: str) -> dict:
        """
        Extract Federated Taxonomy bridge attributes from narration text.
        Tries DistilBERT bridge classifier first (scored), falls back to keywords.
        """
        result = {"bridge_tags": [], "method": "unavailable"}

        # Try trained classifier first (~10ms, returns confidence scores)
        if BRIDGE_INFERENCE_SCRIPT.exists():
            self._init_bridge_classifier()
            if self._bridge_classifier is not None:
                try:
                    scores = self._bridge_classifier.predict(text)
                    result = {
                        "bridge_tags": list(scores.keys()),
                        "bridge_scores": scores,
                        "method": "bridge_classifier",
                    }
                    # Also get keyword-based collection tags
                    if self._taxonomy_available:
                        from taxonomy import extract_taxonomy
                        kw_result = extract_taxonomy(text, collection="behavioral", fast=True)
                        result["collection_tags"] = kw_result.get("collection_tags", {})
                    return result
                except Exception as e:
                    logger.debug("result extraction failed: {}", e)

        # Fallback to keyword extraction (~1ms)
        if self._taxonomy_available:
            try:
                from taxonomy import extract_taxonomy
                result = extract_taxonomy(text, collection="behavioral", fast=True)
                return result
            except Exception as e:
                return {"bridge_tags": [], "method": "error", "error": str(e)}

        return result

    def _summarize_taxonomy(self) -> dict:
        """Aggregate taxonomy tags across all narrations in this session."""
        tag_counts: dict[str, int] = {}
        total_intensity = {"Low": 0, "Moderate": 0, "High": 0, "Extreme": 0}

        for entry in self.session_log:
            tags = entry.get("taxonomy", {})
            for tag in tags.get("bridge_tags", []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
            ei = tags.get("collection_tags", {}).get("emotional_intensity")
            if ei and ei in total_intensity:
                total_intensity[ei] += 1

        return {
            "bridge_tag_counts": tag_counts,
            "emotional_intensity_distribution": total_intensity,
            "dominant_bridge": max(tag_counts, key=tag_counts.get) if tag_counts else None,
        }
