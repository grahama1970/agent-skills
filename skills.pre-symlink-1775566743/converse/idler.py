"""Idle behaviors: humming, self-talk, backchannels, ambient sounds.

Makes Embry feel real during conversation pauses. Song selection for
humming uses Federated Taxonomy multihop graph traversal from /memory,
cross-referencing persona preferences (/consume-music), current mood,
episodic memory (/episodic-archiver), and dream motifs (/create-movie).
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from loguru import logger as log

from emotion import EmotionState, EmotionStateMachine
from traverser import TaxonomyTraverser, NodeType

SKILLS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILLS_ROOT / "common"))

# Hum cache: pre-generated melodic fragments run through Embry's RVC model
HUM_CACHE_BASE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media/personas/embry/hum-cache"

# Music registry from /consume-music
MUSIC_REGISTRY_PATH = Path.home() / ".pi" / "consume-music" / "registry.json"

# Persona profile from /ingest-yt-history
MUSIC_PROFILE_PATH = Path.home() / ".pi" / "ingest-yt-history" / "profile.json"

# Bridge attribute → mood mapping for music selection
BRIDGE_TO_MOOD = {
    "Fragility": ["melancholic", "anxious", "overwhelmed"],
    "Resilience": ["focused", "pleased", "curious"],
    "Precision": ["focused", "curious"],
    "Corruption": ["frustrated", "weary"],
    "Loyalty": ["pleased", "playful", "neutral"],
    "Stealth": ["melancholic", "weary", "anxious"],
}

# Reverse: mood → preferred bridge attributes for music
MOOD_TO_BRIDGES: dict[str, list[str]] = {}
for bridge, moods in BRIDGE_TO_MOOD.items():
    for mood in moods:
        MOOD_TO_BRIDGES.setdefault(mood, []).append(bridge)

# Hard-forbidden music (persona-specific trauma triggers)
FORBIDDEN_MUSIC = {
    "embry": {
        "artists": ["israel kamakawiwoole", "iz"],
        "tracks": ["over the rainbow", "somewhere over the rainbow"],
        "keywords": ["rainbow", "ku'uipo"],
    },
}


@dataclass
class IdleBehavior:
    """A weighted idle behavior with cooldown."""
    name: str
    weight: float
    cooldown: float  # seconds between occurrences
    last_fired: float = 0.0

    @property
    def available(self) -> bool:
        return (time.time() - self.last_fired) >= self.cooldown

    def fire(self):
        self.last_fired = time.time()


@dataclass
class HumSelection:
    """A selected song/fragment for humming."""
    title: str
    artist: str
    bridge_attributes: list[str]
    source: str  # "registry", "dream", "episodic", "cache"
    audio_path: Optional[Path] = None
    mood_match: float = 0.0  # 0.0-1.0 relevance score


class MusicSelector:
    """Select contextually appropriate music for humming via Federated Taxonomy.

    Uses multihop graph traversal through the memory system:
    current emotion → bridge attributes → episodic context →
    dream motifs → consume-music registry → specific tracks.
    """

    def __init__(self, persona: str = "embry"):
        self.persona = persona
        self._registry: Optional[dict] = None
        self._profile: Optional[dict] = None
        self._forbidden = FORBIDDEN_MUSIC.get(persona, {})
        # Standard OS operation: graph traversal via Federated Taxonomy
        self.traverser = TaxonomyTraverser()

    def _load_registry(self) -> dict:
        """Load music registry from /consume-music."""
        if self._registry is None:
            try:
                if MUSIC_REGISTRY_PATH.exists():
                    self._registry = json.loads(MUSIC_REGISTRY_PATH.read_text())
                else:
                    self._registry = {"contents": {}}
            except Exception as e:
                log.warning(f"Failed to load music registry: {e}")
                self._registry = {"contents": {}}
        return self._registry

    def _load_profile(self) -> dict:
        """Load persona music taste profile."""
        if self._profile is None:
            try:
                if MUSIC_PROFILE_PATH.exists():
                    self._profile = json.loads(MUSIC_PROFILE_PATH.read_text())
                else:
                    self._profile = {}
            except Exception as e:
                log.warning(f"Failed to load music profile: {e}")
                self._profile = {}
        return self._profile

    def _is_forbidden(self, title: str, artist: str) -> bool:
        """Check if track is forbidden for this persona."""
        title_lower = title.lower()
        artist_lower = artist.lower()
        if artist_lower in self._forbidden.get("artists", []):
            return True
        if any(t in title_lower for t in self._forbidden.get("tracks", [])):
            return True
        if any(kw in title_lower or kw in artist_lower for kw in self._forbidden.get("keywords", [])):
            return True
        return False

    async def select(self, emotion: EmotionStateMachine) -> Optional[HumSelection]:
        """Select a song for humming via multihop taxonomy traversal.

        Traversal path:
        1. Current emotion state → active bridge attributes
        2. Bridge attributes → query episodic memory for resonant past experiences
        3. Bridge attributes → query dream motifs for subconscious associations
        4. All of the above → filter consume-music registry for matching tracks
        5. Score and rank candidates, respecting forbidden list
        """
        # Step 1: Emotion → bridge attributes
        active_bridges = self._emotion_to_bridges(emotion)
        log.debug(f"Humming selection: bridges={active_bridges} for emotion={emotion.state.value}")

        # Step 2+3: Query episodic memory and dreams in parallel
        loop = asyncio.get_event_loop()
        episodic_task = loop.run_in_executor(None, self._query_episodic_context, active_bridges)
        dream_task = loop.run_in_executor(None, self._query_dream_motifs, active_bridges)
        episodic_context, dream_motifs = await asyncio.gather(episodic_task, dream_task)

        # Step 4: Search consume-music registry
        candidates = self._search_registry(active_bridges, episodic_context, dream_motifs)

        # Step 5: Score and select
        if not candidates:
            return self._select_from_cache(emotion.state)

        # Weight by mood relevance
        for c in candidates:
            c.mood_match = self._score_candidate(c, emotion, episodic_context, dream_motifs)

        candidates.sort(key=lambda c: c.mood_match, reverse=True)
        # Weighted random from top candidates (not always the #1 pick)
        top = candidates[:5]
        weights = [c.mood_match + 0.1 for c in top]
        selected = random.choices(top, weights=weights, k=1)[0]

        log.info(f"Selected hum: {selected.artist} - {selected.title} "
                 f"(bridges={selected.bridge_attributes}, score={selected.mood_match:.2f})")
        return selected

    def _emotion_to_bridges(self, emotion: EmotionStateMachine) -> list[str]:
        """Map current emotion to active bridge attributes."""
        mood = emotion.state.value
        bridges = MOOD_TO_BRIDGES.get(mood, ["Resilience"])

        # Also include bridges with high scores from emotion state
        for attr, score in emotion.bridge_scores.items():
            if score >= 0.7 and attr not in bridges:
                bridges.append(attr)

        return bridges

    def _query_episodic_context(self, bridges: list[str]) -> list[str]:
        """Query episodic memory via Federated Taxonomy graph traversal.

        Multihop: bridges → connected episodes → thematic keywords.
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(
                self.traverser.find_episodes(
                    f"emotional experiences {' '.join(bridges)}", limit=3,
                )
            )
            return [n.content[:200] for n in result.nodes if n.content]
        except Exception as e:
            log.debug(f"Episodic traversal failed: {e}")
            return []

    def _query_dream_motifs(self, bridges: list[str]) -> list[str]:
        """Query dream motifs via Federated Taxonomy graph traversal.

        Multihop: bridges → connected dreams → audio/music textures.
        Dreams from /create-movie inform what Embry unconsciously hums.
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(
                self.traverser.find_dreams(bridges, limit=3),
            )
            motifs = []
            for node in result.nodes:
                if any(kw in node.content.lower() for kw in
                       ["music", "hum", "melody", "song", "audio", "sound", "atmosphere"]):
                    motifs.append(node.content[:200])
            return motifs
        except Exception as e:
            log.debug(f"Dream traversal failed: {e}")
            return []

    def _search_registry(
        self,
        bridges: list[str],
        episodic_context: list[str],
        dream_motifs: list[str],
    ) -> list[HumSelection]:
        """Search consume-music registry for tracks matching taxonomy."""
        registry = self._load_registry()
        profile = self._load_profile()
        candidates = []

        # Get persona's top bridge preferences
        persona_bridges = set(profile.get("top_bridge_attributes", []))

        for _cid, entry in registry.get("contents", {}).items():
            meta = entry.get("metadata", {})
            title = meta.get("track", entry.get("title", ""))
            artist = meta.get("artist", "")
            track_bridges = meta.get("bridge_attributes", [])
            domain = meta.get("domain", "")

            if not title or not artist:
                continue
            if self._is_forbidden(title, artist):
                continue

            # Match: track bridges overlap with active emotion bridges
            bridge_overlap = set(track_bridges) & set(bridges)
            # Bonus: track also matches persona's baseline preferences
            persona_overlap = set(track_bridges) & persona_bridges

            if bridge_overlap or persona_overlap:
                candidates.append(HumSelection(
                    title=title,
                    artist=artist,
                    bridge_attributes=track_bridges,
                    source="registry",
                ))

        return candidates

    def _score_candidate(
        self,
        candidate: HumSelection,
        emotion: EmotionStateMachine,
        episodic_context: list[str],
        dream_motifs: list[str],
    ) -> float:
        """Score a candidate track for contextual relevance."""
        score = 0.0

        # Bridge attribute match with current emotion
        active_bridges = self._emotion_to_bridges(emotion)
        overlap = set(candidate.bridge_attributes) & set(active_bridges)
        score += len(overlap) * 0.3

        # Episodic resonance: does the track's artist/title appear in memories?
        for ctx in episodic_context:
            ctx_lower = ctx.lower()
            if candidate.artist.lower() in ctx_lower or candidate.title.lower() in ctx_lower:
                score += 0.4

        # Dream resonance: does the track connect to dream motifs?
        for motif in dream_motifs:
            motif_lower = motif.lower()
            if candidate.artist.lower() in motif_lower or candidate.title.lower() in motif_lower:
                score += 0.3

        return min(1.0, score)

    def _select_from_cache(self, emotion_state: EmotionState) -> Optional[HumSelection]:
        """Fallback: select from pre-generated hum cache."""
        if not HUM_CACHE_BASE.exists():
            return None

        # Map emotion to cache subdirectory
        mood_dir_map = {
            EmotionState.MELANCHOLIC: "melancholic",
            EmotionState.ANXIOUS: "melancholic",
            EmotionState.WEARY: "calm",
            EmotionState.NEUTRAL: "calm",
            EmotionState.CURIOUS: "calm",
            EmotionState.FOCUSED: "calm",
            EmotionState.PLEASED: "upbeat",
            EmotionState.PLAYFUL: "upbeat",
        }
        mood_dir = mood_dir_map.get(emotion_state, "calm")
        cache_dir = HUM_CACHE_BASE / mood_dir

        if not cache_dir.exists():
            cache_dir = HUM_CACHE_BASE  # flat fallback

        wavs = list(cache_dir.glob("*.wav")) + list(cache_dir.glob("*.mp3"))
        if not wavs:
            return None

        chosen = random.choice(wavs)
        return HumSelection(
            title=chosen.stem,
            artist="embry",
            bridge_attributes=[],
            source="cache",
            audio_path=chosen,
        )


class Idler:
    """Idle behavior engine for natural conversation pauses.

    Runs when orchestrator state is IDLE for >5 seconds. Produces
    audio (humming, backchannels, self-talk) mixed into the output
    stream at appropriate volumes.
    """

    def __init__(self, persona: str = "embry"):
        self.persona = persona
        self.music_selector = MusicSelector(persona=persona)

        self.behaviors = [
            IdleBehavior("backchannel", weight=0.30, cooldown=8),
            IdleBehavior("self_talk", weight=0.20, cooldown=15),
            IdleBehavior("hum_tune", weight=0.15, cooldown=30),
            IdleBehavior("sigh", weight=0.10, cooldown=20),
            IdleBehavior("ambient", weight=0.05, cooldown=60),
            IdleBehavior("silence", weight=0.20, cooldown=0),
        ]

    async def idle_tick(
        self,
        emotion: EmotionStateMachine,
        silence_duration: float,
    ) -> Optional[IdleResult]:
        """Called every ~3s during idle. Returns audio/text to emit, or None.

        Selection is weighted by behavior probability + cooldown. Longer
        silence durations shift weights toward humming and self-talk.
        """
        if silence_duration < 5.0:
            return None

        # Build available behavior pool
        available = [b for b in self.behaviors if b.available]
        if not available:
            return None

        # Adjust weights based on silence duration
        weights = []
        for b in available:
            w = b.weight
            if silence_duration > 15 and b.name == "hum_tune":
                w *= 2.0  # more likely to hum after long silence
            if silence_duration > 10 and b.name == "self_talk":
                w *= 1.5
            weights.append(w)

        chosen = random.choices(available, weights=weights, k=1)[0]
        chosen.fire()

        if chosen.name == "silence":
            return None

        if chosen.name == "backchannel":
            return await self._backchannel(emotion)
        if chosen.name == "self_talk":
            return await self._self_talk(emotion)
        if chosen.name == "hum_tune":
            return await self._hum_tune(emotion)
        if chosen.name == "sigh":
            return await self._sigh(emotion)
        if chosen.name == "ambient":
            return await self._ambient()

        return None

    async def _backchannel(self, emotion: EmotionStateMachine) -> IdleResult:
        """Short vocal backchannel: 'mm-hmm', 'hmm', etc."""
        phrases = {
            EmotionState.CURIOUS: ["hmm...", "mm-hmm", "huh"],
            EmotionState.FOCUSED: ["mm", "right...", "yeah"],
            EmotionState.FRUSTRATED: ["*exhales*", "ugh...", "hmph"],
            EmotionState.MELANCHOLIC: ["mm...", "*soft sigh*", "yeah..."],
            EmotionState.PLEASED: ["mm!", "heh", "yeah"],
        }
        defaults = ["mm-hmm", "hmm", "mm"]
        options = phrases.get(emotion.state, defaults)
        return IdleResult(
            behavior="backchannel",
            text=random.choice(options),
            should_speak=True,
            register="uncertain",
        )

    async def _self_talk(self, emotion: EmotionStateMachine) -> IdleResult:
        """Thinking aloud: short self-directed utterances."""
        phrases = {
            EmotionState.CURIOUS: [
                "I wonder...", "What if...", "That's interesting actually...",
            ],
            EmotionState.FOCUSED: [
                "Okay so...", "Right, right...", "Let me think...",
            ],
            EmotionState.FRUSTRATED: [
                "Come on...", "This is...", "Why does it always...",
            ],
            EmotionState.MELANCHOLIC: [
                "Sometimes I think...", "It's funny how...", "I used to...",
            ],
            EmotionState.WEARY: [
                "*yawns softly*", "Long day...", "Where was I...",
            ],
        }
        defaults = ["Hmm, let me think...", "So...", "Okay..."]
        options = phrases.get(emotion.state, defaults)
        return IdleResult(
            behavior="self_talk",
            text=random.choice(options),
            should_speak=True,
            register="uncertain",
        )

    async def _hum_tune(self, emotion: EmotionStateMachine) -> IdleResult:
        """Hum a song selected via Federated Taxonomy graph traversal."""
        selection = await self.music_selector.select(emotion)

        if selection and selection.audio_path and selection.audio_path.exists():
            # Pre-generated RVC fragment: play directly
            return IdleResult(
                behavior="hum_tune",
                text=f"*hums {selection.artist} - {selection.title}*",
                audio_path=selection.audio_path,
                should_speak=False,
                metadata={"artist": selection.artist, "title": selection.title,
                          "bridges": selection.bridge_attributes, "source": selection.source},
            )

        if selection:
            # No cached audio: use PersonaPlex voice-prompt humming
            # with text describing the song
            return IdleResult(
                behavior="hum_tune",
                text=f"*softly hums a melody that sounds like {selection.artist}*",
                should_speak=True,
                register="humming",
                metadata={"artist": selection.artist, "title": selection.title,
                          "bridges": selection.bridge_attributes, "source": selection.source},
            )

        # No selection available: generic humming
        return IdleResult(
            behavior="hum_tune",
            text="*hums quietly*",
            should_speak=True,
            register="humming",
        )

    async def _sigh(self, emotion: EmotionStateMachine) -> IdleResult:
        """Emotional release sigh, weighted by current state."""
        sighs = {
            EmotionState.WEARY: "*long, tired sigh*",
            EmotionState.FRUSTRATED: "*sharp exhale*",
            EmotionState.MELANCHOLIC: "*quiet, wistful sigh*",
            EmotionState.OVERWHELMED: "*deep breath*",
            EmotionState.PLEASED: "*contented sigh*",
        }
        text = sighs.get(emotion.state, "*soft sigh*")
        return IdleResult(
            behavior="sigh",
            text=text,
            should_speak=True,
            register="tired",
        )

    async def _ambient(self) -> IdleResult:
        """Ambient background: typing sounds, shifting, etc."""
        sounds = [
            "*shuffles papers*", "*taps pen*", "*shifts in chair*",
            "*typing quietly*", "*takes a sip of coffee*",
        ]
        return IdleResult(
            behavior="ambient",
            text=random.choice(sounds),
            should_speak=False,  # text-only annotation
        )

    async def test_hum(self, mood: str = "calm"):
        """Test: select and describe a hum for the given mood."""
        from emotion import EmotionStateMachine
        emo = EmotionStateMachine(persona=self.persona)
        state_map = {"calm": EmotionState.NEUTRAL, "sad": EmotionState.MELANCHOLIC,
                     "happy": EmotionState.PLEASED, "focused": EmotionState.FOCUSED}
        emo.update(state_map.get(mood, EmotionState.NEUTRAL))
        result = await self.idle_tick(emo, silence_duration=10.0)
        if result:
            log.info(f"Idle result: {result}")
        else:
            log.info("No idle behavior triggered (try again)")
        return result


@dataclass
class IdleResult:
    """Output from an idle behavior tick."""
    behavior: str
    text: str
    should_speak: bool = False  # if True, send text to Speaker
    audio_path: Optional[Path] = None  # if set, play this audio file directly
    register: str = "uncertain"
    metadata: dict = field(default_factory=dict)
