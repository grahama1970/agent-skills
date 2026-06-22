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

SCILLM_URL = "http://localhost:4001/v1/chat/completions"
SCILLM_AUTH = "Bearer sk-dev-proxy-123"
SCILLM_TAG_MODEL = "chutes-deepseek"
SCILLM_TAG_AUDIO_MODEL = "gemini-flash"

ORPHEUS_EVENT_TAGS = (
    "<laugh>",
    "<chuckle>",
    "<sigh>",
    "<cough>",
    "<sniffle>",
    "<groan>",
    "<yawn>",
    "<gasp>",
)
TAG_AUTO_INSERT_MIN_CONFIDENCE = 0.85

PROSODY_AUTO_INSERT_MIN_CONFIDENCE = 0.85

def resolve_torch_device(device: str = "auto") -> str:
    """Return cuda when available and device is auto; otherwise pass through."""
    if device != "auto":
        return device
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def whisperx_compute_type(device: str) -> str:
    return "float16" if device == "cuda" else "int8"
