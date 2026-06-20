"""Hum cache: stores and indexes persona-voiced audio with taxonomy metadata."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .defaults import (
    DEFAULT_DIFFUSION_STEPS,
    DEFAULT_F0_METHOD,
    DEFAULT_PIPELINE,
    DEFAULT_SOURCE_HUM_RENDERER,
)

STORAGE_ROOT = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media" / "personas"


@dataclass
class HumTrack:
    """Metadata for a single cached hum."""

    id: str
    title: str
    artist: str = ""
    source_url: str = ""
    source_video_id: str = ""
    bridge_attributes: list[str] = field(default_factory=list)
    mood: list[str] = field(default_factory=list)
    persona_connection: str = ""
    duration_s: Optional[float] = None
    pitch_shift: int = 0
    f0_method: str = DEFAULT_F0_METHOD
    pipeline: str = DEFAULT_PIPELINE
    melody_source: str = DEFAULT_SOURCE_HUM_RENDERER
    source_hum_renderer: str = DEFAULT_SOURCE_HUM_RENDERER
    diffusion_steps: int = DEFAULT_DIFFUSION_STEPS
    created: str = ""
    forbidden: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> HumTrack:
        fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        if "pipeline" not in data:
            fields["pipeline"] = "rvc_v1"
        return cls(**fields)


class HumCache:
    """Manage persona hum cache on disk."""

    def __init__(self, persona: str = "embry"):
        self.persona = persona
        self.cache_dir = STORAGE_ROOT / persona / "hum-cache"
        self.manifest_path = self.cache_dir / "manifest.json"

    def ensure_dir(self) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        return self.cache_dir

    def get_audio_path(self, track_id: str) -> Path:
        return self.cache_dir / f"{track_id}.wav"

    def get_metadata_path(self, track_id: str) -> Path:
        return self.cache_dir / f"{track_id}.json"

    def list_tracks(self) -> list[HumTrack]:
        manifest = self._load_manifest()
        return [HumTrack.from_dict(t) for t in manifest.get("tracks", [])]

    def get_track(self, track_id: str) -> Optional[HumTrack]:
        for track in self.list_tracks():
            if track.id == track_id:
                return track
        return None

    def add_track(self, track: HumTrack, audio_path: Path) -> Path:
        import shutil

        self.ensure_dir()

        dest = self.get_audio_path(track.id)
        if audio_path != dest:
            shutil.copy2(audio_path, dest)

        meta_path = self.get_metadata_path(track.id)
        meta_path.write_text(json.dumps(track.to_dict(), indent=2))

        manifest = self._load_manifest()
        tracks = [t for t in manifest.get("tracks", []) if t["id"] != track.id]
        tracks.append(track.to_dict())
        manifest["tracks"] = tracks
        manifest["persona"] = self.persona
        manifest["updated"] = datetime.now().isoformat()
        self.manifest_path.write_text(json.dumps(manifest, indent=2))

        return dest

    def select(
        self,
        mood: Optional[str] = None,
        bridges: Optional[list[str]] = None,
    ) -> Optional[HumTrack]:
        tracks = [t for t in self.list_tracks() if not t.forbidden]

        if not tracks:
            return None

        def score(t: HumTrack) -> int:
            s = 0
            if mood and mood in t.mood:
                s += 2
            if bridges:
                s += sum(1 for b in bridges if b in t.bridge_attributes)
            return s

        tracks.sort(key=score, reverse=True)
        return tracks[0]

    def _load_manifest(self) -> dict:
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text())
        return {"persona": self.persona, "tracks": [], "updated": ""}
