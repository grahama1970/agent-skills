"""YouTube transcripts skill package.

This package provides a modular YouTube transcript extraction tool with:
- Three-tier fallback: direct API -> proxy -> Whisper
- Batch processing with exponential backoff
- Interactive search
"""

from youtube_transcripts.config import (
    load_proxy_settings,
    get_openai_api_key,
    SKILLS_DIR,
)
from youtube_transcripts.utils import (
    extract_video_id,
    is_retriable_error,
    is_rate_limit_error,
)
from youtube_transcripts.downloader import (
    fetch_video_metadata,
    search_videos,
    download_audio,
)
from youtube_transcripts.transcriber import (
    fetch_transcript_with_retry,
    transcribe_whisper_api,
    transcribe_whisper_local,
)
from youtube_transcripts.formatter import (
    build_result,
    print_json,
    save_json,
)

__all__ = [
    # Config
    "load_proxy_settings",
    "get_openai_api_key",
    "SKILLS_DIR",
    # Utils
    "extract_video_id",
    "is_retriable_error",
    "is_rate_limit_error",
    # Downloader
    "fetch_video_metadata",
    "search_videos",
    "download_audio",
    # Transcriber
    "fetch_transcript_with_retry",
    "transcribe_whisper_api",
    "transcribe_whisper_local",
    # Formatter
    "build_result",
    "print_json",
    "save_json",
]
