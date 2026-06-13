"""Shared constants for voice-segment-selector."""

from __future__ import annotations

SAMPLE_RATE = 16000
MERGE_GAP_SEC = 0.45
VAD_TOP_DB = 24
MALE_F0_HZ = 165.0
HF_MODEL = "norwoodsystems/norwood-maleVSfemale"
HF_MIN_SCORE = 0.55
DEFAULT_MIN_CLIP_SEC = 6.0
DEFAULT_MAX_CLIP_SEC = 18.0
DEFAULT_MIN_SCORE = 0.85
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".m4b", ".flac", ".ogg", ".aac"}
