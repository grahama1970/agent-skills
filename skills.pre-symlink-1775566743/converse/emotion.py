"""Emotional state machine for real-time conversation.

Tracks persona emotional state across conversation turns with decay,
trigger detection, and register selection. Bridge attributes weight
transitions based on persona baseline.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EmotionState(str, Enum):
    CURIOUS = "curious"
    FOCUSED = "focused"
    FRUSTRATED = "frustrated"
    CONFUSED = "confused"
    PLEASED = "pleased"
    OVERWHELMED = "overwhelmed"
    MELANCHOLIC = "melancholic"
    PLAYFUL = "playful"
    WEARY = "weary"
    ANXIOUS = "anxious"
    NEUTRAL = "neutral"


# Bridge attribute baselines per persona
PERSONA_BASELINES = {
    "embry": {
        "Precision": 0.85,
        "Loyalty": 0.90,
        "Resilience": 0.80,
        "Fragility": 0.55,
        "Stealth": 0.35,
        "Corruption": 0.10,
    },
}

# Emotion → bridge attribute influence (positive = intensifies, negative = dampens)
EMOTION_BRIDGE_MODIFIERS = {
    EmotionState.CURIOUS: {"Precision": 0.1, "Stealth": -0.1},
    EmotionState.FOCUSED: {"Precision": 0.15, "Resilience": 0.1},
    EmotionState.FRUSTRATED: {"Fragility": 0.15, "Corruption": 0.05, "Resilience": -0.1},
    EmotionState.CONFUSED: {"Precision": -0.2, "Fragility": 0.1},
    EmotionState.PLEASED: {"Loyalty": 0.1, "Resilience": 0.05},
    EmotionState.OVERWHELMED: {"Fragility": 0.25, "Precision": -0.15, "Resilience": -0.15},
    EmotionState.MELANCHOLIC: {"Fragility": 0.2, "Stealth": 0.1, "Corruption": 0.05},
    EmotionState.PLAYFUL: {"Loyalty": 0.05, "Fragility": -0.1, "Stealth": -0.05},
    EmotionState.WEARY: {"Resilience": -0.2, "Precision": -0.1},
    EmotionState.ANXIOUS: {"Fragility": 0.2, "Stealth": 0.15, "Precision": -0.1},
    EmotionState.NEUTRAL: {},
}


@dataclass
class TriggerResult:
    """Result of scanning text for avoidance/trauma triggers."""
    has_avoidance_trigger: bool = False
    hard_triggers: list[str] = field(default_factory=list)
    soft_triggers: list[str] = field(default_factory=list)
    suggested_state: Optional[EmotionState] = None

    @property
    def severity(self) -> str:
        if self.hard_triggers:
            return "hard"
        if self.soft_triggers:
            return "soft"
        return "none"


@dataclass
class EmotionSnapshot:
    """Point-in-time capture of emotional state."""
    state: EmotionState
    intensity: float  # 0.0-1.0
    bridge_scores: dict[str, float]
    timestamp: float
    trigger: Optional[str] = None


class EmotionStateMachine:
    """Tracks emotional state with trigger detection and gradual decay.

    Designed around persona-specific avoidance triggers and bridge
    attribute modifiers. State decays toward NEUTRAL over time.
    """

    # Per-persona avoidance triggers
    AVOIDANCE_TRIGGERS: dict[str, dict[str, list[str]]] = {
        "embry": {
            "hard": [
                "james", "december 2023", "ku'uipo", "aloha au",
                "kamakawiwoole", "over the rainbow",
            ],
            "soft": [
                "cabernet", "steak salad", "knitted blanket",
                "new haven winter", "snow", "christmas lights",
                "late night drive",
            ],
        },
    }

    # Keyword → emotion mapping for automatic detection
    KEYWORD_EMOTIONS: dict[str, EmotionState] = {
        "confused": EmotionState.CONFUSED,
        "don't understand": EmotionState.CONFUSED,
        "what do you mean": EmotionState.CONFUSED,
        "frustrated": EmotionState.FRUSTRATED,
        "annoying": EmotionState.FRUSTRATED,
        "broken": EmotionState.FRUSTRATED,
        "doesn't work": EmotionState.FRUSTRATED,
        "amazing": EmotionState.PLEASED,
        "great job": EmotionState.PLEASED,
        "love it": EmotionState.PLEASED,
        "thank you": EmotionState.PLEASED,
        "interesting": EmotionState.CURIOUS,
        "tell me more": EmotionState.CURIOUS,
        "how does": EmotionState.CURIOUS,
        "why": EmotionState.CURIOUS,
        "too much": EmotionState.OVERWHELMED,
        "slow down": EmotionState.OVERWHELMED,
        "wait": EmotionState.OVERWHELMED,
        "miss": EmotionState.MELANCHOLIC,
        "used to": EmotionState.MELANCHOLIC,
        "remember when": EmotionState.MELANCHOLIC,
        "tired": EmotionState.WEARY,
        "exhausting": EmotionState.WEARY,
        "long day": EmotionState.WEARY,
    }

    DECAY_RATE = 0.02  # intensity drops per second
    DECAY_INTERVAL = 30.0  # seconds between decay ticks

    def __init__(self, persona: str = "embry"):
        self.persona = persona
        self.state = EmotionState.NEUTRAL
        self.intensity = 0.3  # start low-neutral
        self.baseline = PERSONA_BASELINES.get(persona, PERSONA_BASELINES["embry"])
        self.bridge_scores = dict(self.baseline)
        self.history: list[EmotionSnapshot] = []
        self._running = False

    def check_triggers(self, text: str) -> TriggerResult:
        """Scan text for persona-specific avoidance triggers."""
        text_lower = text.lower()
        triggers = self.AVOIDANCE_TRIGGERS.get(self.persona, {"hard": [], "soft": []})

        result = TriggerResult()
        for trigger in triggers["hard"]:
            if trigger in text_lower:
                result.hard_triggers.append(trigger)
                result.has_avoidance_trigger = True
        for trigger in triggers["soft"]:
            if trigger in text_lower:
                result.soft_triggers.append(trigger)

        if result.hard_triggers:
            result.suggested_state = EmotionState.ANXIOUS
        elif result.soft_triggers:
            result.suggested_state = EmotionState.MELANCHOLIC

        return result

    def detect_from_text(self, text: str) -> Optional[EmotionState]:
        """Detect emotional state from user input keywords."""
        text_lower = text.lower()
        for keyword, state in self.KEYWORD_EMOTIONS.items():
            if keyword in text_lower:
                return state
        return None

    def update(self, new_state: EmotionState, intensity: float = 0.7, trigger: Optional[str] = None) -> EmotionState:
        """Transition to new emotional state, updating bridge scores."""
        self.state = new_state
        self.intensity = min(1.0, max(0.0, intensity))
        self._apply_bridge_modifiers()

        self.history.append(EmotionSnapshot(
            state=self.state,
            intensity=self.intensity,
            bridge_scores=dict(self.bridge_scores),
            timestamp=time.time(),
            trigger=trigger,
        ))

        return self.state

    def update_from_context(self, user_text: str, consecutive_failures: int = 0) -> EmotionState:
        """Convenience: detect emotion from text + context and transition."""
        # Check triggers first
        trigger_result = self.check_triggers(user_text)
        if trigger_result.suggested_state:
            intensity = 0.9 if trigger_result.severity == "hard" else 0.6
            return self.update(trigger_result.suggested_state, intensity, trigger=trigger_result.severity)

        # Detect from keywords
        detected = self.detect_from_text(user_text)
        if detected:
            return self.update(detected, 0.6, trigger="keyword")

        # Context-based: consecutive failures increase frustration
        if consecutive_failures >= 3:
            return self.update(EmotionState.FRUSTRATED, 0.5 + consecutive_failures * 0.1, trigger="failures")

        return self.state

    def _apply_bridge_modifiers(self):
        """Apply current emotion's modifiers to bridge scores."""
        modifiers = EMOTION_BRIDGE_MODIFIERS.get(self.state, {})
        for attr, base in self.baseline.items():
            mod = modifiers.get(attr, 0.0) * self.intensity
            self.bridge_scores[attr] = max(0.0, min(1.0, base + mod))

    def decay_tick(self):
        """Gradual return toward neutral baseline."""
        if self.state == EmotionState.NEUTRAL and self.intensity <= 0.3:
            return

        self.intensity = max(0.1, self.intensity - self.DECAY_RATE * self.DECAY_INTERVAL)
        if self.intensity <= 0.15:
            self.state = EmotionState.NEUTRAL
            self.intensity = 0.3
        self._apply_bridge_modifiers()

    async def decay_loop(self):
        """Async loop: gradual return to baseline. Cancel to stop."""
        self._running = True
        try:
            while self._running:
                await asyncio.sleep(self.DECAY_INTERVAL)
                self.decay_tick()
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False

    def stop(self):
        self._running = False

    def snapshot(self) -> EmotionSnapshot:
        return EmotionSnapshot(
            state=self.state,
            intensity=self.intensity,
            bridge_scores=dict(self.bridge_scores),
            timestamp=time.time(),
        )

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "intensity": round(self.intensity, 3),
            "bridge_scores": {k: round(v, 3) for k, v in self.bridge_scores.items()},
            "history_len": len(self.history),
        }
