"""Auto-aggregated re-exports for the ingest-movie package."""
# Auto-aggregated re-exports for ingest_movie package.
# All public symbols are collected here so __init__.py stays thin.

# -- config --
from config import (
    VALID_EMOTIONS,
    VALID_TAGS,
    HORUS_ARCHETYPE_MAP,
    EMOTION_DIMENSIONS,
    EMOTION_TAG_MAP,
    TAG_TO_EMOTION,
    CUE_KEYWORDS,
    EMOTION_MOVIE_MAPPINGS,
    RADARR_HORUS_PRESET,
    SKILL_DIR,
    CLIPS_DIR,
    INVENTORY_FILE,
    DOGPILE_DIR,
    DEFAULT_MOVIE_LIBRARY,
    DEFAULT_TV_LIBRARY,
    SUBTITLE_HINT_KEYWORDS,
    validate_env,
)

# -- inventory --
from inventory import (
    load_inventory,
    save_inventory,
    add_clip_to_inventory,
    get_inventory_stats,
    get_clips_for_emotion,
    clear_inventory,
)

# -- utils --
from utils import (
    get_ffmpeg_bin,
    get_whisper_bin,
    get_whisper_model_chain,
    run_subprocess,
    get_requests_session,
    read_file_with_encoding_fallback,
    format_seconds,
    format_hms,
    format_srt_timestamp,
    parse_timestamp_to_seconds,
    find_media_file,
    find_subtitle_file,
    fuzzy_match_title,
    release_has_subtitle_hint,
)

# -- scenes --
from scenes import (
    parse_subtitle_file,
    collect_matches,
    extract_srt_window,
    infer_emotion_from_tags,
    tags_for_emotion,
    extract_subtitle_tags,
    attach_tags_to_segments,
    attach_audio_intensity_tags,
    write_subtitle_snippet,
)

# -- search --
from search import search_nzb, display_search_results

# -- extract --
from extract import extract_audio, extract_video_clip, get_video_duration, probe_media_info

# -- transcribe --
from transcribe import (
    run_whisper,
    create_persona_json,
    resolve_subtitle_file,
    compute_emotional_dimensions,
)

# -- subs --
from subs import download_subtitles, batch_download_subtitles, check_subtitle_availability

# -- batch --
from batch import batch_discover, batch_plan, batch_run, batch_status

# -- radarr --
from radarr import (
    check_radarr_connection,
    acquire_movies,
    show_preset_info,
    search_movie,
    add_movie_to_radarr,
    list_radarr_movies,
)

# -- agent --
from agent import (
    recommend_movies,
    quick_extract,
    discover_scenes,
    show_inventory,
    request_extraction,
)

# -- agent_integrations --
from agent_integrations import run_dogpile, send_to_inbox, recommend_books

# -- taxonomy --
from taxonomy import (
    extract_movie_taxonomy,
    get_bridges_from_tags,
    get_bridges_from_emotion,
    enrich_scene_with_taxonomy,
    scene_to_memory_format,
)

# -- ksml_bridge --
from ksml_bridge import KSMLBridge

__all__ = [
    # config
    "VALID_EMOTIONS",
    "VALID_TAGS",
    "HORUS_ARCHETYPE_MAP",
    "EMOTION_DIMENSIONS",
    "EMOTION_TAG_MAP",
    "TAG_TO_EMOTION",
    "CUE_KEYWORDS",
    "EMOTION_MOVIE_MAPPINGS",
    "RADARR_HORUS_PRESET",
    "SKILL_DIR",
    "CLIPS_DIR",
    "INVENTORY_FILE",
    "DOGPILE_DIR",
    "DEFAULT_MOVIE_LIBRARY",
    "DEFAULT_TV_LIBRARY",
    "SUBTITLE_HINT_KEYWORDS",
    "validate_env",
    # inventory
    "load_inventory",
    "save_inventory",
    "add_clip_to_inventory",
    "get_inventory_stats",
    "get_clips_for_emotion",
    "clear_inventory",
    # utils
    "get_ffmpeg_bin",
    "get_whisper_bin",
    "get_whisper_model_chain",
    "run_subprocess",
    "get_requests_session",
    "read_file_with_encoding_fallback",
    "format_seconds",
    "format_hms",
    "format_srt_timestamp",
    "parse_timestamp_to_seconds",
    "find_media_file",
    "find_subtitle_file",
    "fuzzy_match_title",
    "release_has_subtitle_hint",
    # scenes
    "parse_subtitle_file",
    "collect_matches",
    "extract_srt_window",
    "infer_emotion_from_tags",
    "tags_for_emotion",
    "extract_subtitle_tags",
    "attach_tags_to_segments",
    "attach_audio_intensity_tags",
    "write_subtitle_snippet",
    # search
    "search_nzb",
    "display_search_results",
    # extract
    "extract_audio",
    "extract_video_clip",
    "get_video_duration",
    "probe_media_info",
    # transcribe
    "run_whisper",
    "create_persona_json",
    "resolve_subtitle_file",
    "compute_emotional_dimensions",
    # subs
    "download_subtitles",
    "batch_download_subtitles",
    "check_subtitle_availability",
    # batch
    "batch_discover",
    "batch_plan",
    "batch_run",
    "batch_status",
    # radarr
    "check_radarr_connection",
    "acquire_movies",
    "show_preset_info",
    "search_movie",
    "add_movie_to_radarr",
    "list_radarr_movies",
    # agent
    "recommend_movies",
    "quick_extract",
    "discover_scenes",
    "show_inventory",
    "request_extraction",
    # agent_integrations
    "run_dogpile",
    "send_to_inbox",
    "recommend_books",
    # taxonomy
    "extract_movie_taxonomy",
    "get_bridges_from_tags",
    "get_bridges_from_emotion",
    "enrich_scene_with_taxonomy",
    "scene_to_memory_format",
    # ksml_bridge
    "KSMLBridge",
]
