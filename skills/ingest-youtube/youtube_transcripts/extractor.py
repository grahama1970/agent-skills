"""YouTube transcripts public API aggregator — re-exports from all submodules."""
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
    search_videos_via_brave,
    search_videos,
    video_ids_from_text,
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
    "load_proxy_settings",
    "get_openai_api_key",
    "SKILLS_DIR",
    "extract_video_id",
    "is_retriable_error",
    "is_rate_limit_error",
    "fetch_video_metadata",
    "search_videos_via_brave",
    "search_videos",
    "video_ids_from_text",
    "download_audio",
    "fetch_transcript_with_retry",
    "transcribe_whisper_api",
    "transcribe_whisper_local",
    "build_result",
    "print_json",
    "save_json",
]
