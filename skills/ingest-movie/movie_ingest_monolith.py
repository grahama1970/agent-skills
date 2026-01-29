#!/usr/bin/env python3
"""
Movie Ingest Skill
Search NZBGeek and transcribe local video files using Whisper for PersonaPlex alignment.
"""
import os
import sys
import json
import re
import shutil
import subprocess
import requests
import typer
from pathlib import Path
from typing import Optional, Sequence, Dict, Any
from collections import Counter
from functools import lru_cache
from rich.console import Console
from rich.table import Table
from datetime import datetime, timezone
from urllib.parse import urlparse

# Optional: hook for JSON schema validation (PersonaPlex)
try:
    import jsonschema  # type: ignore
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False
    jsonschema = None  # type: ignore

app = typer.Typer(help="Movie Ingest & Transcription Skill")
scenes_app = typer.Typer(help="Transcript scene utilities")
batch_app = typer.Typer(help="Batch processing for automated pipelines")
subs_app = typer.Typer(help="Subtitle download and management")
app.add_typer(scenes_app, name="scenes")
app.add_typer(batch_app, name="batch")
app.add_typer(subs_app, name="subs")
console = Console()

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
NZB_API_KEY = os.environ.get("NZBD_GEEK_API_KEY") or os.environ.get("NZB_GEEK_API_KEY")
NZB_BASE_URL = (
    os.environ.get("NZBD_GEEK_BASE_URL")
    or os.environ.get("NZB_GEEK_BASE_URL")
    or "https://api.nzbgeek.info/"
)
WHISPER_BIN = os.environ.get("WHISPER_BIN", os.path.expanduser("~/.local/bin/whisper"))
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "/usr/bin/ffmpeg")

def sanitize_bin_path(path_str: str, default_name: str) -> str:
    """
    Ensure a safe binary path:
    - Require absolute path if provided via env.
    - Disallow shell metacharacters.
    - Fall back to default_name discovery.
    """
    if not path_str:
        return default_name
    p = Path(path_str)
    if p.is_absolute():
        s = str(p)
        # Disallow shell metacharacters but allow spaces (quoted in subprocess lists)
        if re.search(r'[`$|;&<>]', s):
            console.print(f"[yellow]Unsafe characters in {default_name} path; falling back to PATH.[/yellow]")
            return default_name
        return s
    # Not absolute: ignore env override
    return default_name


@lru_cache(maxsize=1)
def get_ffmpeg_bin() -> str:
    """Return ffmpeg path preferring env override but falling back to PATH."""
    configured = sanitize_bin_path(FFMPEG_BIN, default_name="ffmpeg")
    if configured and Path(configured).exists():
        return configured
    discovered = shutil.which("ffmpeg")
    return discovered or configured


@lru_cache(maxsize=1)
def get_whisper_bin() -> str:
    """Return whisper path preferring env override but falling back to PATH."""
    configured = sanitize_bin_path(WHISPER_BIN, default_name="whisper")
    if configured and Path(configured).exists():
        return configured
    discovered = shutil.which("whisper")
    return discovered or configured


def run_subprocess(cmd: Sequence[str], timeout_sec: int = 600, check: bool = True) -> subprocess.CompletedProcess:
    """
    Safe subprocess wrapper: list-args only, capture outputs, timeout.
    Raises typer.Exit on failure if check=True.
    """
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        console.print(f"[red]Command timed out after {timeout_sec}s: {' '.join(cmd[:3])}...[/red]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Subprocess error: {e}[/red]")
        raise typer.Exit(code=1)
    if check and result.returncode != 0:
        console.print(f"[red]Command failed ({result.returncode}): {' '.join(cmd[:5])}...[/red]")
        stderr_snippet = result.stderr.decode(errors='ignore')[:500]
        if stderr_snippet:
            console.print(f"[dim]{stderr_snippet}[/dim]")
        raise typer.Exit(code=result.returncode)
    return result


@lru_cache(maxsize=1)
def get_requests_session() -> requests.Session:
    """
    Configure a requests session with timeouts and basic retry/backoff.
    """
    from requests.adapters import HTTPAdapter
    try:
        from urllib3.util.retry import Retry  # type: ignore
        retry = Retry(
            total=3,
            read=3,
            connect=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST"]),
        )
    except ImportError:
        retry = None
    s = requests.Session()
    if retry:
        s.mount("http://", HTTPAdapter(max_retries=retry))
        s.mount("https://", HTTPAdapter(max_retries=retry))
    return s

# Audio intensity tagging thresholds (override via env)
RMS_THRESHOLD = float(os.environ.get("AUDIO_RMS_THRESHOLD", "0.2"))
RMS_WINDOW_SEC = float(os.environ.get("AUDIO_RMS_WINDOW_SEC", "0.5"))

CUE_KEYWORDS = {
    # Camaraderie indicators (Stilgar model)
    "laugh": "laugh",
    "laughs": "laugh",
    "chuckle": "laugh",
    "giggle": "laugh",
    "snicker": "laugh",
    # Sorrow indicators (Katsumoto model)
    "sob": "cry",
    "sobbing": "cry",
    "cry": "cry",
    "crying": "cry",
    "weep": "cry",
    "weeping": "cry",
    "mourn": "cry",
    "mourning": "cry",
    "grief": "cry",
    "sigh": "sigh",
    "sighing": "sigh",
    "breath": "breath",
    "breathing": "breath",
    "whisper": "whisper",
    "whispering": "whisper",
    # Anger indicators (Pacino model)
    "scream": "shout",
    "screaming": "shout",
    "shout": "shout",
    "shouting": "shout",
    "yell": "shout",
    "yelling": "shout",
    "angry": "anger",
    "anger": "anger",
    # Rage indicators (DDL model)
    "rage": "rage",
    "raging": "rage",
    "fury": "rage",
    "furious": "rage",
    "snarl": "rage",
    "snarling": "rage",
    "growl": "rage",
    "growling": "rage",
}

# Valid inputs for CLI validation
VALID_TAGS = set(CUE_KEYWORDS.values())  # Valid tag outputs (laugh, cry, shout, etc.)
# Horus ToM emotions aligned with PersonaPlex actor models
VALID_EMOTIONS = {
    "rage",        # Daniel Plainview - manic precision, mockery
    "anger",       # Michael Corleone - cold intensity, calculated fury
    "sorrow",      # Katsumoto/Maximus - stoic honor, duty-bound loss
    "regret",      # George Carlin - cynical deconstruction, strategic error
    "camaraderie", # Stilgar - fierce tribal loyalty, warrior bond
    "command",     # Pre-corruption Horus - affable warrior, inspiring leadership
}

EMOTION_TAG_MAP = {
    # Maps emotions to the subtitle tags that indicate them
    "rage": {"rage", "rage_candidate", "anger_candidate", "shout"},
    "anger": {"anger", "anger_candidate", "shout"},
    "sorrow": {"cry", "sob", "sigh", "whisper", "whisper_candidate", "breath"},
    "regret": {"sigh"},  # Regret often explicit in dialogue, not cues
    "camaraderie": {"laugh"},  # Shared laughter indicates bond
}

TAG_TO_EMOTION = {
    # Rage - explosive fury (DDL model)
    "rage": "rage",
    "rage_candidate": "rage",
    # Anger - cold calculated (Pacino model)
    "anger": "anger",
    "anger_candidate": "anger",
    "shout": "anger",
    # Sorrow - stoic loss (Katsumoto model)
    "cry": "sorrow",
    "sob": "sorrow",
    "sigh": "sorrow",
    "whisper": "sorrow",  # Quiet grief
    "whisper_candidate": "sorrow",
    "breath": "sorrow",  # Heavy breathing from grief
    # Regret - cynical reflection (Carlin model)
    # Note: regret is detected via explicit --emotion flag or text analysis
    # Camaraderie - warrior bond (Stilgar model)
    "laugh": "camaraderie",  # Shared laughter = bond
}

# ToM/BDI: Emotional dimensions for Horus persona training
# Based on Russell's Circumplex Model (valence, arousal) + dominance
# Aligned with Horus 6-emotion system and actor models
EMOTION_DIMENSIONS: Dict[str, Dict[str, float]] = {
    # Daniel Plainview - manic precision, competitive fury, mockery
    "rage": {"valence": -0.9, "arousal": 1.0, "dominance": 0.95},
    # Michael Corleone - cold intensity, deadly quiet, calculated fury
    "anger": {"valence": -0.7, "arousal": 0.6, "dominance": 0.85},
    # Katsumoto/Maximus/Tywin - stoic honor, weary dignity, duty-bound loss
    "sorrow": {"valence": -0.8, "arousal": 0.3, "dominance": 0.4},
    # George Carlin - cynical deconstruction of strategic error
    "regret": {"valence": -0.5, "arousal": 0.4, "dominance": 0.3},
    # Stilgar - fierce tribal loyalty, warrior bond, protective fury
    "camaraderie": {"valence": 0.6, "arousal": 0.7, "dominance": 0.6},
    # Pre-corruption Horus - affable warrior, inspiring leadership, personable
    "command": {"valence": 0.7, "arousal": 0.6, "dominance": 0.9},
}

# ToM/BDI: Archetype mapping for Horus lore transfer
# Maps movie emotions to Horus psychological archetypes
# Actor models: DDL (rage), Pacino (anger), Katsumoto (sorrow), Carlin (regret), Stilgar (camaraderie)
HORUS_ARCHETYPE_MAP: Dict[str, Dict[str, Any]] = {
    "rage": {
        "primary_archetype": "betrayal_fury",
        "actor_model": "Daniel Day-Lewis (Daniel Plainview)",
        "trauma_equivalent": "sanguinius",  # Brother-related trauma
        "belief_pattern": "perceived_betrayal_by_trusted_figure",
        "desire_pattern": "destroy_source_of_betrayal",
        "intention_pattern": "explosive_confrontation",
        "voice_tone": "manic_precision",
        # PersonaPlex voice prompt mapping
        "personaplex_voice": "horus_traumatized.pt",
        "personaplex_fallback": "horus_resentful.pt",
        "rhythm_target": {"wpm_range": [100, 180], "pause_pattern": "staccato"},
    },
    "anger": {
        "primary_archetype": "cold_wrath",
        "actor_model": "Al Pacino (Michael Corleone)",
        "trauma_equivalent": "emperor",  # Authority-related
        "belief_pattern": "injustice_demands_calculated_response",
        "desire_pattern": "assert_dominance_through_control",
        "intention_pattern": "deadly_quiet_correction",
        "voice_tone": "cold_intensity",
        # PersonaPlex voice prompt mapping
        "personaplex_voice": "horus_authoritative.pt",
        "personaplex_fallback": "horus_contemptuous.pt",
        "rhythm_target": {"wpm_range": [80, 120], "pause_pattern": "deliberate"},
    },
    "sorrow": {
        "primary_archetype": "stoic_grief",
        "actor_model": "Ken Watanabe (Katsumoto) / Russell Crowe (Maximus)",
        "trauma_equivalent": "sanguinius",  # Loss of beloved brother
        "belief_pattern": "duty_transcends_personal_pain",
        "desire_pattern": "honor_the_fallen_through_action",
        "intention_pattern": "dignified_acceptance",
        "voice_tone": "weary_dignity",
        # PersonaPlex voice prompt mapping
        "personaplex_voice": "horus_weary.pt",
        "personaplex_fallback": "horus_anguished.pt",
        "rhythm_target": {"wpm_range": [60, 100], "pause_pattern": "heavy_pauses"},
    },
    "regret": {
        "primary_archetype": "cynical_reflection",
        "actor_model": "George Carlin",
        "trauma_equivalent": "davin",  # Corruption-related mistake
        "belief_pattern": "strategic_error_cannot_be_undone",
        "desire_pattern": "deconstruct_failure_with_bitter_clarity",
        "intention_pattern": "sardonic_self_criticism",
        "voice_tone": "cynical_deconstruction",
        # PersonaPlex voice prompt mapping
        "personaplex_voice": "horus_contemptuous.pt",
        "personaplex_fallback": "horus_tactical.pt",
        "rhythm_target": {"wpm_range": [120, 160], "pause_pattern": "comedic_timing"},
    },
    "camaraderie": {
        "primary_archetype": "warrior_bond",
        "actor_model": "Javier Bardem (Stilgar)",
        "trauma_equivalent": None,  # Positive emotion, healing
        "belief_pattern": "brothers_stand_together",
        "desire_pattern": "protect_and_elevate_trusted_allies",
        "intention_pattern": "fierce_loyalty_declaration",
        "voice_tone": "tribal_intensity",
        # PersonaPlex voice prompt mapping
        "personaplex_voice": "horus_protective.pt",
        "personaplex_fallback": "horus_authoritative.pt",
        "rhythm_target": {"wpm_range": [90, 130], "pause_pattern": "emphatic"},
    },
    "command": {
        "primary_archetype": "affable_commander",
        "actor_model": "Gerard Butler (Leonidas) / Russell Crowe (Maximus)",
        "trauma_equivalent": None,  # Pre-corruption, positive leadership
        "belief_pattern": "lead_from_front_with_warmth",
        "desire_pattern": "inspire_through_example_and_presence",
        "intention_pattern": "charismatic_rallying_call",
        "voice_tone": "warm_authority",
        # PersonaPlex voice prompt mapping
        "personaplex_voice": "horus_authoritative.pt",
        "personaplex_fallback": "horus_protective.pt",
        "rhythm_target": {"wpm_range": [100, 140], "pause_pattern": "inspiring"},
    },
}


def compute_emotional_dimensions(
    emotion_tag: Optional[str],
    wpm: float,
    pause_count: int,
    tags: set[str],
) -> Dict[str, Any]:
    """
    Compute ToM-aligned emotional dimensions from rhythm and tags.
    Returns valence, arousal, dominance + archetype mapping for Horus.
    """
    # Base dimensions from emotion tag
    emotion = emotion_tag.lower() if emotion_tag else "anger"
    base_dims = EMOTION_DIMENSIONS.get(emotion, EMOTION_DIMENSIONS["anger"])

    # Adjust arousal based on WPM (faster speech = higher arousal)
    # Normal speech ~120-150 WPM; rage can hit 180+
    wpm_arousal_modifier = min(1.0, max(0.0, (wpm - 80) / 100))

    # Adjust dominance based on pause patterns
    # Few pauses = confident/dominant; many pauses = hesitant
    pause_dominance_modifier = max(0.0, 1.0 - (pause_count * 0.1))

    # Compute tag intensity boost
    intensity_tags = {"rage", "rage_candidate", "shout", "anger_candidate"}
    tag_intensity = len(tags & intensity_tags) / max(1, len(intensity_tags))

    # Final computed dimensions
    computed = {
        "emotional_valence": round(base_dims["valence"], 2),
        "emotional_arousal": round(
            min(1.0, base_dims["arousal"] * 0.6 + wpm_arousal_modifier * 0.4), 2
        ),
        "emotional_dominance": round(
            min(1.0, base_dims["dominance"] * 0.7 + pause_dominance_modifier * 0.3), 2
        ),
        "primary_emotion": emotion,
        "intensity_score": round(tag_intensity, 2),
    }

    # Add archetype mapping for Horus lore transfer
    archetype = HORUS_ARCHETYPE_MAP.get(emotion, HORUS_ARCHETYPE_MAP["anger"])
    computed["horus_archetype"] = {
        "primary": archetype["primary_archetype"],
        "actor_model": archetype.get("actor_model", "Unknown"),
        "voice_tone": archetype.get("voice_tone", "neutral"),
        "trauma_equivalent": archetype["trauma_equivalent"],
        "bdi_patterns": {
            "belief": archetype["belief_pattern"],
            "desire": archetype["desire_pattern"],
            "intention": archetype["intention_pattern"],
        },
    }

    return computed

SUBTITLE_HINT_KEYWORDS = (" subs", "subbed", "subtitle", "subtitles", ".srt", "cc", "sdh", "caption")
def _validate_env():
    if os.environ.get("NZBD_GEEK_API_KEY") and not os.environ.get("NZB_GEEK_API_KEY"):
        console.print("[yellow]Note: prefer NZB_GEEK_API_KEY (without the extra 'D').[/yellow]")
    if not NZB_API_KEY:
        console.print(
            "[yellow]Warning: NZB_GEEK_API_KEY not set. NZB search will fail.[/yellow]"
        )
    # Validate base URL
    try:
        parsed = urlparse(NZB_BASE_URL)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            console.print("[yellow]Invalid NZB_BASE_URL; expected http(s) URL.[/yellow]")
    except Exception:
        console.print("[yellow]Invalid NZB_BASE_URL; parsing failed.[/yellow]")
    # Validate binaries existence (non-fatal warnings)
    if not shutil.which("ffmpeg") and not Path(get_ffmpeg_bin()).exists():
        console.print("[yellow]ffmpeg not found; clipping will fail.[/yellow]")
    if not shutil.which("whisper") and not Path(get_whisper_bin()).exists():
        console.print("[yellow]whisper not found; transcription will fail.[/yellow]")


def release_has_subtitle_hint(item: dict) -> bool:
    haystack = " ".join(
        [
            str(item.get("title", "")),
            str(item.get("description", "")),
            str(item.get("attr", "")),
        ]
    ).lower()
    return any(keyword in haystack for keyword in SUBTITLE_HINT_KEYWORDS)


@scenes_app.command("find")
def find_scene_windows(
    subtitle_file: Path = typer.Option(..., "--subtitle", "-s", exists=True, help="Subtitle .srt to scan"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Case-insensitive text substring to find"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Filter by subtitle cue tag (e.g. laugh, shout)"),
    emotion: Optional[str] = typer.Option(None, "--emotion", "-e", help="Filter by canonical emotion (rage, anger, humor, respect, regret)"),
    window: float = typer.Option(15.0, help="Seconds of padding before/after the match for suggested clips"),
    max_matches: int = typer.Option(5, help="Maximum matches to display"),
    offset: float = typer.Option(0.0, help="Seconds to add when referencing the full movie (useful if .srt was trimmed)"),
    video_file: Optional[Path] = typer.Option(None, "--video", help="Optional video file path for ffmpeg command hints"),
):
    """Search subtitle text/tags to locate clip timestamps."""
    if not query and not tag and not emotion:
        raise typer.BadParameter("Provide at least --query, --tag, or --emotion to locate a scene")

    # Input validation
    if window <= 0 or window > 300:
        raise typer.BadParameter("window must be > 0 and <= 300 seconds")
    if max_matches <= 0 or max_matches > 100:
        raise typer.BadParameter("max_matches must be between 1 and 100")
    if offset < 0 or offset > 36000:
        raise typer.BadParameter("offset must be >= 0 and <= 10 hours")
    if tag:
        tag = tag.strip().lower()
        if tag not in VALID_TAGS:
            raise typer.BadParameter(f"Unknown tag '{tag}'. Allowed: {sorted(VALID_TAGS)}")
    if emotion:
        emotion = emotion.strip().lower()
        if emotion not in VALID_EMOTIONS:
            raise typer.BadParameter(f"Unknown emotion '{emotion}'. Allowed: {sorted(VALID_EMOTIONS)}")
    if query:
        query = query.strip()
        if not query:
            raise typer.BadParameter("query must not be empty")

    # Resolve and validate paths
    subtitle_file = subtitle_file.resolve()
    if video_file:
        video_file = video_file.resolve()

    entries = parse_subtitle_file(subtitle_file)
    if not entries:
        console.print("[red]No subtitle entries found; ensure the .srt has text lines.[/red]")
        raise typer.Exit(code=1)

    matches = collect_matches(entries, query, tag, emotion, max_matches, merge_adjacent=True)
    if not matches:
        console.print("[yellow]No matches found for the given query/tag.[/yellow]")
        raise typer.Exit()

    adjusted_video = str(video_file) if video_file else None
    console.print(f"[green]Found {len(matches)} match(es). Suggested clip windows with ±{window:.1f}s padding:[/green]")
    for idx, entry in enumerate(matches, 1):
        start = entry.get("start", 0.0)
        end = entry.get("end", start)
        clip_start = max(0.0, start - window) + offset
        clip_end = end + window + offset
        inferred = infer_emotion_from_tags(entry.get("tags", []), emotion)
        console.print(f"\n[bold]Match {idx}[/bold]")
        console.print(f"Subtitle window: {format_seconds(start+offset)} → {format_seconds(end+offset)}")
        console.print(f"Suggested clip: {format_seconds(clip_start)} → {format_seconds(clip_end)}")
        console.print(f"Text: {entry.get('text', '').strip()}")
        entry_tags = entry.get("tags") or []
        if entry_tags:
            console.print(f"Tags: {', '.join(entry_tags)}")
        if inferred:
            console.print(f"Inferred emotion: {inferred}")
        if adjusted_video:
            console.print(
                "{bin} -ss {start} -to {end} -i '{video}' -c copy clip_{idx}.mkv".format(
                    bin=get_ffmpeg_bin(),
                    start=format_hms(clip_start),
                    end=format_hms(clip_end),
                    video=adjusted_video,
                    idx=idx,
                )
            )


@scenes_app.command("quality")
def check_subtitle_quality(
    subtitle_file: Path = typer.Option(..., "--subtitle", "-s", exists=True, help="Subtitle .srt to validate"),
    strict: bool = typer.Option(False, "--strict", help="Fail on warnings (for CI/automated pipelines)"),
):
    """
    Validate subtitle quality for PersonaPlex ingestion.

    Checks:
    - File encoding and readability
    - Minimum entry count and coverage
    - Presence of emotion cue tags (stage directions)
    - Timing consistency (no inverted/overlapping)
    - Language detection hints
    """
    subtitle_file = subtitle_file.resolve()
    issues: list[tuple[str, str]] = []  # (severity, message)

    # 1. Check file readability and encoding
    try:
        content = subtitle_file.read_text(encoding="utf-8", errors="strict")
    except UnicodeDecodeError:
        try:
            content = subtitle_file.read_text(encoding="latin-1", errors="ignore")
            issues.append(("warning", "File is not UTF-8 encoded; falling back to latin-1"))
        except Exception as e:
            issues.append(("error", f"Cannot read file: {e}"))
            content = ""

    if not content.strip():
        issues.append(("error", "Subtitle file is empty"))
        _print_quality_report(subtitle_file, issues, strict)
        return

    # 2. Parse and check entry count
    entries = parse_subtitle_file(subtitle_file)
    if len(entries) < 10:
        issues.append(("error", f"Too few entries ({len(entries)}); expected at least 10 for usable subtitle"))
    elif len(entries) < 50:
        issues.append(("warning", f"Low entry count ({len(entries)}); may indicate partial or summary subtitles"))

    # 3. Check for emotion cues / stage directions
    entries_with_tags = [e for e in entries if e.get("tags")]
    tag_ratio = len(entries_with_tags) / len(entries) if entries else 0

    if not entries_with_tags:
        issues.append(("warning", "No emotion cue tags found; subtitle may lack stage directions (e.g., [laughs], [shouts])"))
    elif tag_ratio < 0.01:
        issues.append(("warning", f"Very few cue tags ({len(entries_with_tags)}/{len(entries)} = {tag_ratio:.1%}); consider using SDH subtitles"))

    # 4. Check timing consistency
    inverted_count = 0
    overlap_count = 0
    prev_end = 0.0
    for entry in entries:
        start, end = entry.get("start", 0.0), entry.get("end", 0.0)
        if end < start:
            inverted_count += 1
        if start < prev_end - 0.1:  # Allow 100ms tolerance
            overlap_count += 1
        prev_end = end

    if inverted_count > 0:
        issues.append(("error", f"Found {inverted_count} entries with inverted timestamps (end < start)"))
    if overlap_count > len(entries) * 0.1:
        issues.append(("warning", f"High overlap count ({overlap_count}); timestamps may be misaligned"))

    # 5. Coverage check (for movie subtitles, expect at least 1 hour coverage)
    if entries:
        total_duration = entries[-1].get("end", 0.0) - entries[0].get("start", 0.0)
        if total_duration < 1800:  # Less than 30 minutes
            issues.append(("warning", f"Short duration coverage ({format_seconds(total_duration)}); may be incomplete"))

    # 6. Emotion variety check
    all_tags = set()
    for entry in entries:
        all_tags.update(entry.get("tags", []))
    all_emotions = set(TAG_TO_EMOTION.get(t, None) for t in all_tags) - {None}

    if len(all_emotions) == 0:
        issues.append(("info", "No recognizable emotions detected"))
    elif len(all_emotions) == 1:
        issues.append(("info", f"Only one emotion type found: {list(all_emotions)[0]}"))
    else:
        issues.append(("ok", f"Multiple emotion types detected: {', '.join(sorted(all_emotions))}"))

    _print_quality_report(subtitle_file, issues, strict)


def _print_quality_report(subtitle_file: Path, issues: list[tuple[str, str]], strict: bool) -> None:
    """Print quality report and optionally exit with error."""
    errors = [i for i in issues if i[0] == "error"]
    warnings = [i for i in issues if i[0] == "warning"]
    infos = [i for i in issues if i[0] in ("info", "ok")]

    console.print(f"\n[bold]Subtitle Quality Report: {subtitle_file.name}[/bold]")

    for severity, msg in issues:
        if severity == "error":
            console.print(f"  [red]ERROR[/red]: {msg}")
        elif severity == "warning":
            console.print(f"  [yellow]WARNING[/yellow]: {msg}")
        elif severity == "ok":
            console.print(f"  [green]OK[/green]: {msg}")
        else:
            console.print(f"  [dim]INFO[/dim]: {msg}")

    # Summary
    if errors:
        console.print(f"\n[red]FAIL[/red]: {len(errors)} error(s), {len(warnings)} warning(s)")
        raise typer.Exit(code=1)
    elif warnings and strict:
        console.print(f"\n[yellow]FAIL (strict)[/yellow]: {len(warnings)} warning(s)")
        raise typer.Exit(code=1)
    elif warnings:
        console.print(f"\n[yellow]PASS with warnings[/yellow]: {len(warnings)} warning(s)")
    else:
        console.print(f"\n[green]PASS[/green]: Subtitle appears suitable for PersonaPlex ingestion")


@scenes_app.command("analyze")
def analyze_emotion_cues(
    subtitle_file: Path = typer.Option(..., "--subtitle", "-s", exists=True, help="Subtitle .srt to scan"),
    output_json: Optional[Path] = typer.Option(None, "--output-json", "-o", help="Output JSON report path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed cue locations"),
):
    """Scan subtitle file and report all emotion cues found, grouped by type."""
    subtitle_file = subtitle_file.resolve()
    entries = parse_subtitle_file(subtitle_file)
    if not entries:
        console.print("[red]No subtitle entries found.[/red]")
        raise typer.Exit(code=1)

    # Collect all tags and their locations
    tag_locations: Dict[str, list] = {}
    emotion_locations: Dict[str, list] = {}

    for entry in entries:
        tags = entry.get("tags", [])
        for tag in tags:
            if tag not in tag_locations:
                tag_locations[tag] = []
            tag_locations[tag].append({
                "start": entry["start"],
                "end": entry["end"],
                "text": entry.get("text", "").strip()[:80],
            })
            # Map to emotion
            emotion = TAG_TO_EMOTION.get(tag.lower())
            if emotion:
                if emotion not in emotion_locations:
                    emotion_locations[emotion] = []
                emotion_locations[emotion].append({
                    "tag": tag,
                    "start": entry["start"],
                    "end": entry["end"],
                    "text": entry.get("text", "").strip()[:80],
                })

    # Summary table
    table = Table(title=f"Emotion Cue Analysis: {subtitle_file.name}")
    table.add_column("Emotion", style="bold cyan")
    table.add_column("Count", style="green", justify="right")
    table.add_column("Tags Found", style="yellow")
    table.add_column("First Occurrence", style="dim")

    for emotion in sorted(VALID_EMOTIONS):
        locs = emotion_locations.get(emotion, [])
        if locs:
            tags_found = sorted(set(loc["tag"] for loc in locs))
            first = locs[0]
            table.add_row(
                emotion,
                str(len(locs)),
                ", ".join(tags_found),
                format_seconds(first["start"]),
            )
        else:
            table.add_row(emotion, "0", "-", "-")

    console.print(table)

    # Verbose output
    if verbose:
        console.print("\n[bold]Detailed Cue Locations:[/bold]")
        for emotion in sorted(emotion_locations.keys()):
            console.print(f"\n[cyan]{emotion.upper()}[/cyan] ({len(emotion_locations[emotion])} occurrences):")
            for loc in emotion_locations[emotion][:10]:  # Limit to first 10
                console.print(f"  {format_seconds(loc['start'])} [{loc['tag']}] {loc['text']}")
            if len(emotion_locations[emotion]) > 10:
                console.print(f"  ... and {len(emotion_locations[emotion]) - 10} more")

    # JSON output
    if output_json:
        report = {
            "source_subtitle": str(subtitle_file),
            "total_entries": len(entries),
            "summary": {
                emotion: {
                    "count": len(locs),
                    "tags": sorted(set(loc["tag"] for loc in locs)),
                }
                for emotion, locs in emotion_locations.items()
            },
            "cues_by_emotion": emotion_locations if verbose else None,
            "cues_by_tag": tag_locations if verbose else None,
        }
        output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        console.print(f"\n[green]Analysis saved to {output_json}[/green]")

    # Recommendations
    console.print("\n[bold]Recommendations for PersonaPlex:[/bold]")
    if emotion_locations.get("rage"):
        console.print(f"  - {len(emotion_locations['rage'])} rage sequences found. Use: ./run.sh scenes extract --subtitle {subtitle_file.name} --emotion rage")
    if emotion_locations.get("humor"):
        console.print(f"  - {len(emotion_locations['humor'])} humor sequences found. Use: ./run.sh scenes extract --subtitle {subtitle_file.name} --emotion humor")
    if not emotion_locations:
        console.print("  [yellow]No emotion cues detected. This subtitle may lack stage directions.[/yellow]")


@scenes_app.command("extract")
def extract_scene_manifest(
    subtitle_file: Path = typer.Option(..., "--subtitle", "-s", exists=True, help="Subtitle .srt to scan"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Case-insensitive text substring to find"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Filter by subtitle cue tag (e.g. laugh, shout)"),
    emotion: Optional[str] = typer.Option(None, "--emotion", "-e", help="Filter by canonical emotion (rage, anger, humor, respect, regret)"),
    window: float = typer.Option(12.0, help="Seconds of padding before/after matches when clipping"),
    max_matches: int = typer.Option(10, help="Maximum matches to process"),
    offset: float = typer.Option(0.0, help="Seconds to align subtitles with full movie timing"),
    video_file: Optional[Path] = typer.Option(None, "--video", help="Optional video file to auto-clip via ffmpeg"),
    clip_dir: Optional[Path] = typer.Option(None, "--clip-dir", help="Directory to write extracted clips (.mkv/.srt)"),
    output_json: Optional[Path] = typer.Option(None, "--output-json", help="Manifest path (defaults to <subtitle>.scenes.json)"),
    subtitle_only: bool = typer.Option(False, "--subtitle-only", help="Skip ffmpeg work and just emit manifest data"),
):
    """Generate a JSON manifest (and optional clips) for PersonaPlex ingestion."""
    if not query and not tag and not emotion:
        raise typer.BadParameter("Provide at least --query, --tag, or --emotion to extract scenes")
    if subtitle_only and clip_dir:
        raise typer.BadParameter("--subtitle-only cannot be combined with --clip-dir")
    if clip_dir and not video_file:
        raise typer.BadParameter("--clip-dir requires --video to read from")

    # Input validation
    if window <= 0 or window > 300:
        raise typer.BadParameter("window must be > 0 and <= 300 seconds")
    if max_matches <= 0 or max_matches > 100:
        raise typer.BadParameter("max_matches must be between 1 and 100")
    if offset < 0 or offset > 36000:
        raise typer.BadParameter("offset must be >= 0 and <= 10 hours")
    if tag:
        tag = tag.strip().lower()
        if tag not in VALID_TAGS:
            raise typer.BadParameter(f"Unknown tag '{tag}'. Allowed: {sorted(VALID_TAGS)}")
    if emotion:
        emotion = emotion.strip().lower()
        if emotion not in VALID_EMOTIONS:
            raise typer.BadParameter(f"Unknown emotion '{emotion}'. Allowed: {sorted(VALID_EMOTIONS)}")
    if query:
        query = query.strip()
        if not query:
            raise typer.BadParameter("query must not be empty")

    # Resolve and validate paths
    subtitle_file = subtitle_file.resolve()
    if video_file:
        video_file = video_file.resolve()
    if clip_dir:
        clip_dir = clip_dir.resolve()

    entries = parse_subtitle_file(subtitle_file)
    matches = collect_matches(entries, query, tag, emotion, max_matches, merge_adjacent=True)
    if not matches:
        console.print("[yellow]No matches found; nothing to extract.[/yellow]")
        raise typer.Exit()

    manifest_path = output_json or subtitle_file.with_suffix(".scenes.json")
    manifest: list[dict] = []
    clip_dir_path = Path(clip_dir) if clip_dir else None
    if clip_dir_path:
        clip_dir_path.mkdir(parents=True, exist_ok=True)

    console.print(f"[cyan]Processing {len(matches)} match(es) from {subtitle_file}[/cyan]")
    for idx, entry in enumerate(matches, 1):
        start = entry.get("start", 0.0)
        end = entry.get("end", start)
        clip_start = max(0.0, start - window) + offset
        clip_end = end + window + offset
        inferred = infer_emotion_from_tags(entry.get("tags", []), emotion)
        record = {
            "index": idx,
            "text": entry.get("text", "").strip(),
            "tags": entry.get("tags", []),
            "emotion": inferred,
            "subtitle_window": {
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
            },
            "movie_window": {
                "start_sec": round(clip_start, 3),
                "end_sec": round(clip_end, 3),
                "duration_sec": round(max(0.0, clip_end - clip_start), 3),
            },
        }
        if video_file:
            record["movie_window"]["ffmpeg_hint"] = (
                "{bin} -ss {start} -to {end} -i '{video}' -c copy clip_{idx:02d}.mkv".format(
                    bin=get_ffmpeg_bin(),
                    start=format_hms(clip_start),
                    end=format_hms(clip_end),
                    video=str(video_file),
                    idx=idx,
                )
            )

        clip_metadata = {}
        if clip_dir_path and not subtitle_only:
            clip_name = f"clip_{idx:02d}"
            clip_video_path = clip_dir_path / f"{clip_name}.mkv"
            cmd = [
                get_ffmpeg_bin(),
                "-y",
                "-ss",
                f"{clip_start:.3f}",
                "-to",
                f"{clip_end:.3f}",
                "-i",
                str(video_file),
                "-c",
                "copy",
                str(clip_video_path),
            ]
            # Use run_subprocess with check=False to continue on individual clip failures
            try:
                result = run_subprocess(cmd, timeout_sec=120, check=False)
                if result.returncode == 0:
                    clip_metadata["video"] = str(clip_video_path)
                    console.print(f"[green]Saved {clip_video_path}[/green]")
                else:
                    console.print(f"[yellow]ffmpeg failed for {clip_name} (exit {result.returncode})[/yellow]")
            except typer.Exit:
                console.print(f"[yellow]Skipping {clip_name} due to ffmpeg error[/yellow]")

            snippet_path = clip_dir_path / f"{clip_name}.srt"
            snippet = write_subtitle_snippet(entries, clip_start, clip_end, snippet_path, offset)
            if snippet:
                clip_metadata["subtitle"] = str(snippet)
            if inferred:
                clip_metadata["emotion"] = inferred
            if clip_metadata:
                record["clip_artifacts"] = clip_metadata

        manifest.append(record)

    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump({"scenes": manifest, "source_subtitle": str(subtitle_file)}, fh, indent=2)

    console.print(f"[green]Scene manifest saved to {manifest_path}[/green]")
    if clip_dir_path and not subtitle_only:
        console.print(f"[green]Clips available under {clip_dir_path}[/green]")
    console.print("Next: feed manifest rows into horus_lore_ingest emotion ingest.")

# -----------------------------------------------------------------------------
# NZB Search Logic
# -----------------------------------------------------------------------------
@app.command("search")
def search_nzb(
    term: str = typer.Argument(..., help="Movie title to search"),
    cat: str = typer.Option("2000", help="Category (2000=Movies, 5000=TV)"),
    limit: int = typer.Option(10, help="Max results to display")
):
    """Search NZBGeek for movie releases."""
    _validate_env()
    
    params = {
        "t": "search",
        "q": term,
        "cat": cat,
        "apikey": NZB_API_KEY,
        "o": "json"
    }
    
    url = f"{NZB_BASE_URL.rstrip('/')}/api"
    try:
        console.print(f"[cyan]Searching NZBGeek for '{term}'...[/cyan]")
        session = get_requests_session()
        resp = session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        
        data = resp.json()
        items = []
        
        # Handle XML-to-JSON quirks (single item vs list)
        if "channel" in data and "item" in data["channel"]:
            items = data["channel"]["item"]
            if isinstance(items, dict):
                items = [items]
        elif "item" in data:
            items = data["item"]
            
        if not items:
            console.print("[yellow]No results found.[/yellow]")
            return

        table = Table(title=f"Results for '{term}'")
        table.add_column("Title", style="green")
        table.add_column("Subs?", style="yellow", justify="center")
        table.add_column("Size", style="cyan")
        table.add_column("PubDate", style="dim")
        table.add_column("Link", style="blue")

        for item in items[:limit]:
            size = item.get("size", "0")
            try:
                size_mb = int(size) / (1024 * 1024)
                size_str = f"{size_mb:.1f} MB"
            except (ValueError, TypeError):
                size_str = str(size)
            subs_flag = "✅" if release_has_subtitle_hint(item) else ""
            table.add_row(
                item.get("title", "Unknown")[:60],
                subs_flag,
                size_str,
                item.get("pubDate", "")[:16],
                item.get("link", "")[:40] + "..."
            )
        console.print(table)

    except Exception as e:
        console.print(f"[red]Search failed: {e}[/red]")

# -----------------------------------------------------------------------------
# Transcription Logic
# -----------------------------------------------------------------------------
@app.command("transcribe")
def transcribe_video(
    input_file: Path = typer.Argument(..., exists=True, help="Video file path"),
    output_dir: Path = typer.Option(Path("./transcripts"), help="Directory for Whisper + persona JSON"),
    model: str = typer.Option("medium", help="Whisper model (base, small, medium, large)"),
    emotion: Optional[str] = typer.Option(None, help="Tag with emotion (e.g. rage, sorrow)"),
    movie_title: Optional[str] = typer.Option(None, help="Movie or benchmark title"),
    scene: Optional[str] = typer.Option(None, help="Scene description (e.g. 'Pacino warns Fredo')"),
    characters: Optional[str] = typer.Option(None, help="Comma-separated character list"),
    source_id: Optional[str] = typer.Option(None, help="Stable clip ID (defaults to filename stem)"),
    subtitle_file: Optional[Path] = typer.Option(None, help="Path to subtitle .srt with emotion cues"),
    output_json: Optional[Path] = typer.Option(None, help="Override for ingestion-ready JSON path"),
):
    """
    Transcribe a video file using local Whisper.
    Extracts audio -> Transcribes -> Calculates Rhythm.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = input_file.stem
    audio_file = output_dir / f"{stem}.wav"

    subtitle_path = resolve_subtitle_file(input_file, subtitle_file)
    subtitle_entries = parse_subtitle_file(subtitle_path)
    if not subtitle_entries:
        raise typer.BadParameter(
            f"No usable cues found in subtitle file {subtitle_path}. Provide a high-quality subtitle track with emotion annotations."
        )
    
    # 1. Extract Audio (using safe subprocess wrapper)
    console.print(f"[cyan]Extracting audio to {audio_file}...[/cyan]")
    cmd_ffmpeg = [
        get_ffmpeg_bin(), "-y",
        "-i", str(input_file),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(audio_file)
    ]
    run_subprocess(cmd_ffmpeg, timeout_sec=300)

    # 2. Run Whisper (using safe subprocess wrapper)
    console.print(f"[cyan]Running Whisper ({model})...[/cyan]")
    cmd_whisper = [
        get_whisper_bin(),
        str(audio_file),
        "--model", model,
        "--output_dir", str(output_dir),
        "--output_format", "json"
    ]
    # Whisper can take a long time for large files
    run_subprocess(cmd_whisper, timeout_sec=1800)

    # 3. Process JSON for PersonaPlex
    json_file = output_dir / f"{stem}.json"
    if not json_file.exists():
        console.print(f"[red]Whisper JSON not found at {json_file}[/red]")
        return

    with open(json_file) as f:
        transcript = json.load(f)

    segments = transcript.get("segments", []) or []
    formatted_segments = []
    full_text_parts = []
    last_end = 0.0
    pauses = 0
    for seg in segments:
        start = float(seg.get("start", 0))
        end = float(seg.get("end", start))
        duration = max(0.0, end - start)
        text = (seg.get("text") or "").strip()
        if start - last_end > 0.5:
            pauses += 1
        last_end = end
        formatted_segments.append({
            "text": text,
            "start": round(start, 3),
            "duration": round(duration, 3),
        })
        if text:
            full_text_parts.append(text)

    total_duration = float(transcript.get("duration", last_end))
    total_words = len((" ".join(full_text_parts)).split())
    wpm = (total_words / total_duration) * 60 if total_duration > 0 else 0.0

    clip_id = source_id or stem
    character_list = [c.strip() for c in (characters.split(",") if characters else []) if c.strip()]

    attach_tags_to_segments(formatted_segments, subtitle_entries)
    subtitle_tag_set = {tag for entry in subtitle_entries for tag in entry["tags"]}
    audio_tag_set = attach_audio_intensity_tags(audio_file, formatted_segments)
    aggregate_tags = sorted(subtitle_tag_set | audio_tag_set)

    # Compute ToM-aligned emotional dimensions for Horus training
    emotional_dims = compute_emotional_dimensions(
        emotion_tag=emotion,
        wpm=wpm,
        pause_count=pauses,
        tags=subtitle_tag_set | audio_tag_set,
    )

    meta = {
        "video_id": clip_id,
        "source": "movie",
        "movie_title": movie_title or stem,
        "scene": scene,
        "characters": character_list,
        "emotion_tag": emotion,
        "language": transcript.get("language"),
        "duration_sec": round(total_duration, 3),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(input_file),
        "subtitle_file": str(subtitle_path),
        "subtitle_tags": sorted(subtitle_tag_set),
        "audio_tags": sorted(audio_tag_set),
        "rhythm_metrics": {
            "wpm": round(wpm, 1),
            "pause_count": pauses,
            "duration_sec": round(total_duration, 2)
        }
    }

    persona_payload = {
        "meta": meta,
        "emotional_dimensions": emotional_dims,  # ToM/BDI: Horus emotion training
        "full_text": " ".join(full_text_parts),
        "transcript": formatted_segments,
    }

    enriched_file = output_json or (output_dir / f"{stem}_persona.json")
    with open(enriched_file, "w") as f:
        json.dump(persona_payload, f, indent=2)

    console.print(f"[green]Success! Persona JSON saved to {enriched_file}[/green]")
    console.print(f"Rhythm: {wpm:.1f} WPM, {pauses} significant pauses")
    if aggregate_tags:
        console.print(f"Detected cue tags: {', '.join(aggregate_tags)}")
    ingest_hint = emotion or "<emotion>"
    console.print(f"Next: `python horus_lore_ingest.py emotion --input {output_dir} --emotion {ingest_hint}` to ingest.")


def resolve_subtitle_file(input_file: Path, explicit: Optional[Path]) -> Path:
    if explicit:
        if not explicit.exists():
            raise typer.BadParameter(f"Subtitle file {explicit} does not exist")
        return explicit

    candidates = []
    for candidate in input_file.parent.glob(f"{input_file.stem}*.srt"):
        candidates.append(candidate)

    if not candidates:
        raise typer.BadParameter(
            "Subtitle .srt file not found. Provide --subtitle pointing to a release with emotion cues before ingesting."
        )

    return sorted(candidates, key=lambda p: len(p.name))[0]


def parse_subtitle_file(path: Path) -> list[dict]:
    if path.suffix.lower() != ".srt":
        raise typer.BadParameter("Only .srt subtitles are supported right now")

    content = path.read_text(encoding="utf-8", errors="ignore")
    entries: list[dict] = []
    malformed = inverted = total = 0

    def flush_block(block: list[str]):
        nonlocal malformed, inverted, total
        lines = [line.strip() for line in block if line.strip()]
        if len(lines) < 2:
            return
        time_line_idx = next((i for i, l in enumerate(lines[:3]) if "-->" in l), -1)
        if time_line_idx == -1:
            malformed += 1
            return
        time_line = lines[time_line_idx]
        text_lines = lines[time_line_idx + 1 :]
        if not text_lines:
            return
        parts = [part.strip() for part in time_line.split("-->")]
        if len(parts) != 2:
            malformed += 1
            return
        start_str, end_str = parts
        start = parse_timestamp(start_str)
        end = parse_timestamp(end_str)
        total += 1
        if start is None or end is None:
            malformed += 1
            return
        if end < start:
            inverted += 1
            return
        text = " ".join(text_lines)
        tags = extract_subtitle_tags(text)
        entries.append({"start": start, "end": end, "text": text, "tags": tags})

    buffer: list[str] = []
    for line in content.splitlines():
        if line.strip() == "":
            if buffer:
                flush_block(buffer)
                buffer = []
        else:
            buffer.append(line)
    if buffer:
        flush_block(buffer)

    console.print(
        f"[dim]Subtitle parse summary: total={total}, valid={len(entries)}, malformed={malformed}, inverted={inverted}[/dim]"
    )
    return entries


def parse_timestamp(raw: str) -> Optional[float]:
    raw = raw.strip()
    m = re.search(r"(\d{1,2}):(\d{2}):(\d{2})(?:[.,](\d{1,3}))?", raw)
    if not m:
        return None
    hours = int(m.group(1))
    minutes = int(m.group(2))
    seconds = int(m.group(3))
    millis_group = m.group(4)
    millis = int(millis_group) if millis_group is not None else 0
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def extract_subtitle_tags(text: str) -> list[str]:
    lowered = text.lower()
    raw_cues = (
        re.findall(r"\[(.*?)\]", lowered)
        + re.findall(r"\((.*?)\)", lowered)
        + re.findall(r"\{(.*?)\}", lowered)
    )
    dash_cues = re.findall(r"-\s*([a-z\s]+?)\s*-", lowered)
    caps_cues = [lowered] if text.isupper() and 1 <= len(text.split()) <= 3 else []
    tags = set()
    for cue in raw_cues + dash_cues + caps_cues:
        for keyword, tag in CUE_KEYWORDS.items():
            if keyword in cue:
                tags.add(tag)
    return sorted(tags)


def attach_tags_to_segments(segments: list[dict], entries: list[dict]) -> None:
    if not entries:
        return
    entries_sorted = sorted(entries, key=lambda e: e["start"])
    entry_idx = 0
    for seg in segments:
        seg_start = seg.get("start", 0.0)
        seg_end = seg_start + seg.get("duration", 0.0)
        seg_tags = set()

        while entry_idx < len(entries_sorted) and entries_sorted[entry_idx]["end"] < seg_start:
            entry_idx += 1

        probe = entry_idx
        while probe < len(entries_sorted) and entries_sorted[probe]["start"] <= seg_end:
            seg_tags.update(entries_sorted[probe]["tags"])
            probe += 1

        if seg_tags:
            seg.setdefault("tags", [])
            seg["tags"] = sorted(set(seg["tags"]) | seg_tags)


def attach_audio_intensity_tags(audio_file: Path, segments: list[dict]) -> set[str]:
    try:
        import soundfile as sf
        import numpy as np
    except ImportError:
        console.print("[yellow]soundfile or numpy not installed; skipping audio intensity tagging.[/yellow]")
        return set()

    if not audio_file.exists():
        return set()

    intensity_tags = set()
    try:
        data, sr = sf.read(audio_file)
    except Exception as e:
        console.print(f"[yellow]Failed to read audio for intensity tagging: {e}[/yellow]")
        return set()
    if getattr(data, "ndim", 1) > 1:
        data = data.mean(axis=1)

    window_size = int(sr * RMS_WINDOW_SEC)

    for seg in segments:
        start = seg.get("start", 0.0)
        end = start + seg.get("duration", 0.0)
        start_idx = max(0, int(start * sr))
        end_idx = min(len(data), int(end * sr))
        if end_idx <= start_idx:
            continue
        segment_audio = data[start_idx:end_idx]
        if len(segment_audio) <= window_size:
            rms = float(np.sqrt(np.mean(segment_audio ** 2))) if len(segment_audio) else 0.0
            rms_max = rms
        else:
            windows = [segment_audio[i:i+window_size] for i in range(0, len(segment_audio), window_size)]
            rms_max = max(float(np.sqrt(np.mean(w ** 2))) for w in windows if len(w))

        segment_tags = set()
        if rms_max > RMS_THRESHOLD * 2:
            segment_tags.add("rage_candidate")
        elif rms_max > RMS_THRESHOLD:
            segment_tags.add("anger_candidate")
        elif rms_max < 0.05:
            segment_tags.add("whisper_candidate")

        if segment_tags:
            intensity_tags.update(segment_tags)
            seg.setdefault("tags", [])
            seg["tags"] = sorted(set(seg["tags"]) | segment_tags)

    return intensity_tags


def tags_for_emotion(emotion: Optional[str]) -> set[str]:
    if not emotion:
        return set()
    return {tag.lower() for tag in EMOTION_TAG_MAP.get(emotion.lower(), set())}


def infer_emotion_from_tags(tags: list[str], fallback: Optional[str] = None) -> Optional[str]:
    if fallback:
        return fallback.lower()
    mapped = [TAG_TO_EMOTION.get(tag.lower()) for tag in tags]
    mapped = [m for m in mapped if m]
    if not mapped:
        return None
    counts = Counter(mapped)
    priority = ["rage", "anger", "humor", "regret", "respect"]
    sorted_emotions = sorted(
        counts.keys(),
        key=lambda e: (-counts[e], priority.index(e) if e in priority else len(priority)),
    )
    return sorted_emotions[0]


def collect_matches(
    entries: list[dict],
    query: Optional[str],
    tag: Optional[str],
    emotion: Optional[str],
    max_matches: int,
    merge_adjacent: bool = True,
) -> list[dict]:
    query_lower = query.lower() if query else None
    tag_filters = set()
    if tag:
        tag_filters.add(tag.lower())
    tag_filters |= tags_for_emotion(emotion)

    raw_matches: list[dict] = []
    prefetch = max_matches * (10 if merge_adjacent else 1)
    for entry in entries:
        text = entry.get("text", "")
        entry_tags = {t.lower() for t in entry.get("tags", [])}
        if query_lower and query_lower not in text.lower():
            continue
        if tag_filters and not (tag_filters & entry_tags):
            continue
        raw_matches.append(entry)
        if query_lower is None and tag_filters:
            # prefer cue-driven matches by not over-collecting
            if len(raw_matches) >= prefetch:
                break
        elif len(raw_matches) >= prefetch:
            break

    if not merge_adjacent:
        return raw_matches[:max_matches]

    merged: list[dict] = []
    for entry in raw_matches:
        if merged and entry["start"] - merged[-1]["end"] <= 2.0:
            merged[-1]["end"] = max(merged[-1]["end"], entry["end"])
            merged[-1]["text"] = (merged[-1].get("text", "") + " " + entry.get("text", "")).strip()
            merged[-1]["tags"] = sorted(set(merged[-1].get("tags", [])) | set(entry.get("tags", [])))
        else:
            merged.append(entry.copy())
        if len(merged) >= max_matches:
            break
    return merged


def write_subtitle_snippet(
    entries: list[dict],
    clip_start_global: float,
    clip_end_global: float,
    output_path: Path,
    offset: float,
) -> Optional[Path]:
    output_lines = []
    index = 1
    for entry in entries:
        entry_start_global = entry["start"] + offset
        entry_end_global = entry["end"] + offset
        if entry_end_global < clip_start_global or entry_start_global > clip_end_global:
            continue
        local_start = max(0.0, entry_start_global - clip_start_global)
        clip_duration_local = max(0.0, clip_end_global - clip_start_global)
        local_end = min(max(local_start, entry_end_global - clip_start_global), clip_duration_local)
        output_lines.append(
            f"{index}\n"
            f"{format_srt_timestamp(local_start)} --> {format_srt_timestamp(local_end)}\n"
            f"{entry.get('text', '').strip()}\n"
        )
        index += 1

    if not output_lines:
        return None

    output_path.write_text("\n".join(output_lines), encoding="utf-8")
    return output_path


def format_seconds(value: float) -> str:
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    seconds = value % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"
    return f"{minutes:02d}:{seconds:05.2f}"

def format_hms(value: float) -> str:
    value = max(0.0, value)
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    seconds = value % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"


def format_srt_timestamp(value: float) -> str:
    value = max(0.0, value)
    total_ms = int(round(value * 1000))
    hours = total_ms // 3_600_000
    rem = total_ms % 3_600_000
    minutes = rem // 60_000
    rem %= 60_000
    seconds = rem // 1000
    millis = rem % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


# -----------------------------------------------------------------------------
# Batch Processing Commands
# -----------------------------------------------------------------------------
# Default media directories to scan
DEFAULT_MEDIA_DIRS = [
    "/mnt/storage12tb/media/movies",
    "/mnt/storage12tb/media/shows",
]

# Movie title patterns for emotion mapping (based on dogpile research)
EMOTION_MOVIE_MAP: Dict[str, list[Dict[str, Any]]] = {
    "rage": [
        {"title": "There Will Be Blood", "scenes": ["I drink your milkshake", "Eli confrontation", "bowling alley"], "actor": "Daniel Day-Lewis"},
        {"title": "Sicario", "scenes": ["dinner scene", "border crossing"], "actor": "Benicio del Toro"},
        {"title": "No Country for Old Men", "scenes": ["coin toss", "hotel confrontation"], "actor": "Javier Bardem"},
        {"title": "Gangs of New York", "scenes": ["butcher shop", "Bill the Butcher"], "actor": "Daniel Day-Lewis"},
        {"title": "Full Metal Jacket", "scenes": ["major malfunction", "hard heart that kills"], "actor": "R. Lee Ermey"},
    ],
    "anger": [
        {"title": "The Godfather", "scenes": ["against the family", "Fredo warning", "baptism"], "actor": "Al Pacino"},
        {"title": "Heat", "scenes": ["face to face", "bank robbery"], "actor": "Al Pacino"},
        {"title": "Apocalypse Now", "scenes": ["Kurtz monologue", "horror"], "actor": "Marlon Brando"},
    ],
    "sorrow": [
        {"title": "Gladiator", "scenes": ["my name is", "Elysium", "family death"], "actor": "Russell Crowe"},
        {"title": "The Last Samurai", "scenes": ["final battle", "death of Katsumoto"], "actor": "Ken Watanabe"},
        {"title": "Schindler's List", "scenes": ["I could have done more", "one more person"], "actor": "Liam Neeson"},
        {"title": "Master and Commander", "scenes": ["burial at sea", "lesser of two weevils"], "actor": "Russell Crowe"},
        {"title": "Letters from Iwo Jima", "scenes": ["final letter", "soldier farewell"], "actor": "Ken Watanabe"},
    ],
    "regret": [
        {"title": "George Carlin", "scenes": ["dumb Americans", "soft language", "rights"], "actor": "George Carlin", "source": "youtube"},
        {"title": "Full Metal Jacket", "scenes": ["duality of man", "jungian thing", "born to kill"], "actor": "Matthew Modine"},
        {"title": "Network", "scenes": ["mad as hell", "I'm a human being"], "actor": "Peter Finch"},
        {"title": "Taxi Driver", "scenes": ["you talkin to me", "loneliness"], "actor": "Robert De Niro"},
    ],
    "camaraderie": [
        {"title": "Band of Brothers", "scenes": ["Easy Company", "Bastogne", "Christmas"], "actor": "Damian Lewis", "source": "tv"},
        {"title": "Saving Private Ryan", "scenes": ["Earn this", "brothers in arms"], "actor": "Tom Hanks"},
        {"title": "Fury", "scenes": ["best job", "tank crew"], "actor": "Brad Pitt"},
        {"title": "Dune", "scenes": ["Stilgar meets Paul", "Fremen loyalty", "desert power"], "actor": "Javier Bardem"},
        {"title": "Dune Part Two", "scenes": ["Stilgar", "warrior bond", "Fremen"], "actor": "Javier Bardem"},
    ],
    "command": [
        {"title": "300", "scenes": ["This is Sparta", "tonight we dine in hell", "give them nothing"], "actor": "Gerard Butler"},
        {"title": "Gladiator", "scenes": ["hold the line", "at my signal unleash hell", "strength and honor"], "actor": "Russell Crowe"},
        {"title": "Kingdom of Heaven", "scenes": ["defend this city", "what man is a man"], "actor": "Orlando Bloom"},
        {"title": "Braveheart", "scenes": ["freedom speech", "they may take our lives"], "actor": "Mel Gibson"},
        {"title": "Band of Brothers", "scenes": ["Winters rally", "move out"], "actor": "Damian Lewis", "source": "tv"},
    ],
}


def find_media_file(directory: Path, extensions: set[str] = {".mkv", ".mp4", ".avi", ".m4v"}) -> Optional[Path]:
    """Find the largest video file in a directory (likely the main feature)."""
    candidates = []
    for ext in extensions:
        candidates.extend(directory.glob(f"*{ext}"))
    if not candidates:
        return None
    # Return largest file (likely main feature, not extras)
    return max(candidates, key=lambda p: p.stat().st_size)


def find_subtitle_file(directory: Path, prefer_sdh: bool = True) -> Optional[Path]:
    """Find subtitle file, preferring SDH/CC versions."""
    candidates = list(directory.glob("*.srt"))
    if not candidates:
        return None

    # Prefer SDH/CC subtitles
    if prefer_sdh:
        for srt in candidates:
            name_lower = srt.name.lower()
            if any(tag in name_lower for tag in ["sdh", "cc", "hi.", "hearing"]):
                return srt

    # Fall back to English subtitles
    for srt in candidates:
        name_lower = srt.name.lower()
        if "eng" in name_lower or "english" in name_lower:
            return srt

    # Return first available
    return candidates[0]


def fuzzy_match_title(search: str, available: list[str], threshold: float = 0.6) -> Optional[str]:
    """Simple fuzzy matching for movie titles."""
    search_lower = search.lower()
    search_words = set(search_lower.split())

    best_match = None
    best_score = 0.0

    for title in available:
        title_lower = title.lower()
        title_words = set(title_lower.split())

        # Check direct substring match
        if search_lower in title_lower or title_lower in search_lower:
            return title

        # Word overlap score
        overlap = len(search_words & title_words)
        total = len(search_words | title_words)
        score = overlap / total if total > 0 else 0

        if score > best_score and score >= threshold:
            best_score = score
            best_match = title

    return best_match


@batch_app.command("discover")
def batch_discover(
    media_dirs: Optional[list[str]] = typer.Option(None, "--dir", "-d", help="Media directories to scan"),
    output_json: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSON inventory path"),
    show_subtitles: bool = typer.Option(False, "--subtitles", "-s", help="Check for subtitle availability"),
):
    """
    Scan media directories to discover available movies for batch processing.
    Creates an inventory of movies with their paths and subtitle status.
    """
    dirs_to_scan = [Path(d) for d in media_dirs] if media_dirs else [Path(d) for d in DEFAULT_MEDIA_DIRS]

    inventory: list[Dict[str, Any]] = []

    for media_dir in dirs_to_scan:
        if not media_dir.exists():
            console.print(f"[yellow]Directory not found: {media_dir}[/yellow]")
            continue

        console.print(f"[cyan]Scanning {media_dir}...[/cyan]")

        # Scan movie directories (one level deep)
        for item in sorted(media_dir.iterdir()):
            if not item.is_dir():
                continue

            video_file = find_media_file(item)
            if not video_file:
                continue

            entry: Dict[str, Any] = {
                "title": item.name,
                "path": str(item),
                "video_file": str(video_file),
                "video_size_gb": round(video_file.stat().st_size / (1024**3), 2),
            }

            if show_subtitles:
                srt = find_subtitle_file(item)
                entry["subtitle_file"] = str(srt) if srt else None
                entry["has_subtitle"] = srt is not None

                # Check for SDH
                if srt:
                    entry["is_sdh"] = any(
                        tag in srt.name.lower()
                        for tag in ["sdh", "cc", "hi.", "hearing"]
                    )

            inventory.append(entry)

    # Display summary
    table = Table(title="Media Inventory")
    table.add_column("Title", style="green", max_width=40)
    table.add_column("Size", style="cyan", justify="right")
    if show_subtitles:
        table.add_column("Subtitles", style="yellow", justify="center")

    for entry in inventory[:50]:  # Limit display
        cols = [entry["title"][:40], f"{entry['video_size_gb']:.1f} GB"]
        if show_subtitles:
            subs = "✓ SDH" if entry.get("is_sdh") else ("✓" if entry.get("has_subtitle") else "✗")
            cols.append(subs)
        table.add_row(*cols)

    console.print(table)
    console.print(f"\n[green]Found {len(inventory)} movies/shows[/green]")

    if output_json:
        output_json.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
        console.print(f"[green]Inventory saved to {output_json}[/green]")


@batch_app.command("plan")
def batch_plan(
    emotions: Optional[list[str]] = typer.Option(None, "--emotion", "-e", help="Emotions to plan for"),
    media_dirs: Optional[list[str]] = typer.Option(None, "--dir", "-d", help="Media directories to scan"),
    output_json: Path = typer.Option(Path("batch_manifest.json"), "--output", "-o", help="Output manifest path"),
    include_unavailable: bool = typer.Option(False, "--include-unavailable", help="Include movies not in library"),
):
    """
    Create a batch processing manifest from the Horus emotion-movie mappings.
    Uses dogpile research to map emotions to specific movie scenes.
    """
    dirs_to_scan = [Path(d) for d in media_dirs] if media_dirs else [Path(d) for d in DEFAULT_MEDIA_DIRS]
    emotions_to_plan = set(e.lower() for e in emotions) if emotions else set(VALID_EMOTIONS)

    # Build inventory of available movies
    available_movies: Dict[str, Dict[str, Any]] = {}
    for media_dir in dirs_to_scan:
        if not media_dir.exists():
            continue
        for item in media_dir.iterdir():
            if item.is_dir():
                video = find_media_file(item)
                if video:
                    available_movies[item.name] = {
                        "path": str(item),
                        "video_file": str(video),
                        "subtitle_file": str(find_subtitle_file(item)) if find_subtitle_file(item) else None,
                    }

    console.print(f"[cyan]Found {len(available_movies)} movies in library[/cyan]")

    # Build manifest
    manifest: Dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "media_dirs": [str(d) for d in dirs_to_scan],
        "jobs": [],
    }

    for emotion in sorted(emotions_to_plan):
        if emotion not in EMOTION_MOVIE_MAP:
            console.print(f"[yellow]No movie mappings for emotion: {emotion}[/yellow]")
            continue

        for movie_spec in EMOTION_MOVIE_MAP[emotion]:
            title = movie_spec["title"]

            # Try to find in library
            matched_title = fuzzy_match_title(title, list(available_movies.keys()))

            job: Dict[str, Any] = {
                "emotion": emotion,
                "movie_title": title,
                "scenes": movie_spec.get("scenes", []),
                "actor_model": movie_spec.get("actor", "Unknown"),
                "source_type": movie_spec.get("source", "movie"),
                "available": matched_title is not None,
            }

            if matched_title:
                library_entry = available_movies[matched_title]
                job["library_title"] = matched_title
                job["video_file"] = library_entry["video_file"]
                job["subtitle_file"] = library_entry["subtitle_file"]
                job["status"] = "ready" if library_entry["subtitle_file"] else "needs_subtitle"
            else:
                job["status"] = "not_in_library"

            if job["available"] or include_unavailable:
                manifest["jobs"].append(job)

    # Summary
    ready = sum(1 for j in manifest["jobs"] if j.get("status") == "ready")
    needs_sub = sum(1 for j in manifest["jobs"] if j.get("status") == "needs_subtitle")
    missing = sum(1 for j in manifest["jobs"] if j.get("status") == "not_in_library")

    console.print(f"\n[bold]Batch Plan Summary:[/bold]")
    console.print(f"  [green]Ready to process: {ready}[/green]")
    console.print(f"  [yellow]Needs subtitles: {needs_sub}[/yellow]")
    if include_unavailable:
        console.print(f"  [red]Not in library: {missing}[/red]")

    output_json.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    console.print(f"\n[green]Manifest saved to {output_json}[/green]")
    console.print(f"Next: ./run.sh batch run --manifest {output_json}")


@batch_app.command("run")
def batch_run(
    manifest_file: Path = typer.Option(..., "--manifest", "-m", exists=True, help="Batch manifest JSON"),
    output_dir: Path = typer.Option(Path("/mnt/storage12tb/media/persona_exemplars"), "--output-dir", "-o", help="Base output directory"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be done without executing"),
    max_jobs: int = typer.Option(0, "--max-jobs", help="Maximum jobs to process (0=all)"),
    emotions: Optional[list[str]] = typer.Option(None, "--emotion", "-e", help="Filter to specific emotions"),
    skip_existing: bool = typer.Option(True, "--skip-existing", help="Skip jobs that already have output"),
):
    """
    Execute batch processing from a manifest file.
    Processes each job: extract subtitles → find scenes → clip → transcribe → persona JSON.
    """
    manifest = json.loads(manifest_file.read_text())
    jobs = manifest.get("jobs", [])

    if emotions:
        emotion_filter = set(e.lower() for e in emotions)
        jobs = [j for j in jobs if j.get("emotion", "").lower() in emotion_filter]

    # Filter to ready jobs only
    ready_jobs = [j for j in jobs if j.get("status") == "ready"]

    if max_jobs > 0:
        ready_jobs = ready_jobs[:max_jobs]

    console.print(f"[cyan]Processing {len(ready_jobs)} jobs from manifest[/cyan]")

    results: list[Dict[str, Any]] = []

    for idx, job in enumerate(ready_jobs, 1):
        emotion = job["emotion"]
        title = job.get("library_title") or job["movie_title"]
        video_file = job.get("video_file")
        subtitle_file = job.get("subtitle_file")
        scenes = job.get("scenes", [])

        console.print(f"\n[bold][{idx}/{len(ready_jobs)}] {title} ({emotion})[/bold]")

        # Output paths
        emotion_dir = output_dir / emotion
        movie_slug = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_').lower()
        job_output_dir = emotion_dir / movie_slug

        if skip_existing and job_output_dir.exists() and list(job_output_dir.glob("*_persona.json")):
            console.print(f"  [dim]Skipping - output exists at {job_output_dir}[/dim]")
            results.append({"job": job, "status": "skipped", "reason": "exists"})
            continue

        if dry_run:
            console.print(f"  [dim]Would process: {video_file}[/dim]")
            console.print(f"  [dim]Scenes: {', '.join(scenes[:3])}[/dim]")
            console.print(f"  [dim]Output: {job_output_dir}[/dim]")
            results.append({"job": job, "status": "dry_run"})
            continue

        try:
            job_output_dir.mkdir(parents=True, exist_ok=True)
            clips_dir = job_output_dir / "clips"
            clips_dir.mkdir(exist_ok=True)

            # Step 1: Analyze subtitle for emotion cues
            console.print(f"  [cyan]Analyzing subtitles...[/cyan]")
            subtitle_path = Path(subtitle_file)
            entries = parse_subtitle_file(subtitle_path)

            if not entries:
                console.print(f"  [red]No subtitle entries found[/red]")
                results.append({"job": job, "status": "failed", "reason": "no_subtitles"})
                continue

            # Step 2: Find scenes matching emotion or query
            all_matches: list[dict] = []

            # First try emotion tag matching
            emotion_tags = EMOTION_TAG_MAP.get(emotion, set())
            if emotion_tags:
                matches = collect_matches(entries, None, None, emotion, max_matches=5, merge_adjacent=True)
                all_matches.extend(matches)

            # Then try scene-specific queries
            for scene_query in scenes[:3]:  # Limit to first 3 scenes
                scene_matches = collect_matches(entries, scene_query, None, None, max_matches=2, merge_adjacent=True)
                for m in scene_matches:
                    if m not in all_matches:
                        all_matches.append(m)

            if not all_matches:
                console.print(f"  [yellow]No matching scenes found[/yellow]")
                results.append({"job": job, "status": "no_matches"})
                continue

            console.print(f"  [green]Found {len(all_matches)} scene candidates[/green]")

            # Step 3: Extract clips
            video_path = Path(video_file)
            clip_count = 0

            for clip_idx, match in enumerate(all_matches[:5], 1):  # Limit to 5 clips
                start = match.get("start", 0.0)
                end = match.get("end", start + 10)
                clip_start = max(0.0, start - 12.0)
                clip_end = end + 12.0

                clip_path = clips_dir / f"clip_{clip_idx:02d}.mp4"

                console.print(f"  [dim]Extracting clip {clip_idx}: {format_seconds(clip_start)} - {format_seconds(clip_end)}[/dim]")

                cmd = [
                    get_ffmpeg_bin(), "-y",
                    "-ss", f"{clip_start:.3f}",
                    "-to", f"{clip_end:.3f}",
                    "-i", str(video_path),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k",
                    str(clip_path),
                ]

                try:
                    result = run_subprocess(cmd, timeout_sec=180, check=False)
                    if result.returncode == 0:
                        clip_count += 1

                        # Write clip subtitle snippet
                        snippet_path = clips_dir / f"clip_{clip_idx:02d}.srt"
                        write_subtitle_snippet(entries, clip_start, clip_end, snippet_path, 0.0)
                except Exception as e:
                    console.print(f"  [yellow]Clip {clip_idx} failed: {e}[/yellow]")

            if clip_count == 0:
                console.print(f"  [red]No clips extracted[/red]")
                results.append({"job": job, "status": "failed", "reason": "no_clips"})
                continue

            console.print(f"  [green]Extracted {clip_count} clips[/green]")

            # Step 4: Transcribe clips
            persona_count = 0
            for clip_file in sorted(clips_dir.glob("clip_*.mp4")):
                clip_srt = clip_file.with_suffix(".srt")

                console.print(f"  [dim]Transcribing {clip_file.name}...[/dim]")

                # Run transcribe command
                try:
                    # Extract audio
                    audio_file = job_output_dir / f"{clip_file.stem}.wav"
                    cmd_audio = [
                        get_ffmpeg_bin(), "-y",
                        "-i", str(clip_file),
                        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                        str(audio_file),
                    ]
                    run_subprocess(cmd_audio, timeout_sec=120, check=False)

                    # Run Whisper
                    cmd_whisper = [
                        get_whisper_bin(),
                        str(audio_file),
                        "--model", "base",  # Use base for speed in batch
                        "--output_dir", str(job_output_dir),
                        "--output_format", "json",
                    ]
                    run_subprocess(cmd_whisper, timeout_sec=300, check=False)

                    # Process transcript
                    whisper_json = job_output_dir / f"{clip_file.stem}.json"
                    if whisper_json.exists():
                        transcript = json.loads(whisper_json.read_text())
                        segments = transcript.get("segments", [])

                        formatted_segments = []
                        full_text_parts = []
                        pauses = 0
                        last_end = 0.0

                        for seg in segments:
                            seg_start = float(seg.get("start", 0))
                            seg_end = float(seg.get("end", seg_start))
                            text = (seg.get("text") or "").strip()
                            if seg_start - last_end > 0.5:
                                pauses += 1
                            last_end = seg_end
                            formatted_segments.append({
                                "text": text,
                                "start": round(seg_start, 3),
                                "duration": round(max(0, seg_end - seg_start), 3),
                            })
                            if text:
                                full_text_parts.append(text)

                        total_duration = float(transcript.get("duration", last_end))
                        total_words = len(" ".join(full_text_parts).split())
                        wpm = (total_words / total_duration) * 60 if total_duration > 0 else 0.0

                        # Compute emotional dimensions
                        emotional_dims = compute_emotional_dimensions(
                            emotion_tag=emotion,
                            wpm=wpm,
                            pause_count=pauses,
                            tags=set(),
                        )

                        # Build persona payload
                        persona_payload = {
                            "meta": {
                                "video_id": clip_file.stem,
                                "source": "movie",
                                "movie_title": title,
                                "scene": ", ".join(scenes[:2]) if scenes else None,
                                "characters": [job.get("actor_model", "Unknown")],
                                "emotion_tag": emotion,
                                "language": transcript.get("language"),
                                "duration_sec": round(total_duration, 3),
                                "created_at": datetime.now(timezone.utc).isoformat(),
                                "source_file": str(clip_file),
                                "rhythm_metrics": {
                                    "wpm": round(wpm, 1),
                                    "pause_count": pauses,
                                    "duration_sec": round(total_duration, 2),
                                },
                            },
                            "emotional_dimensions": emotional_dims,
                            "full_text": " ".join(full_text_parts),
                            "transcript": formatted_segments,
                        }

                        persona_file = job_output_dir / f"{clip_file.stem}_persona.json"
                        persona_file.write_text(json.dumps(persona_payload, indent=2), encoding="utf-8")
                        persona_count += 1
                        console.print(f"  [green]Created {persona_file.name}[/green]")

                except Exception as e:
                    console.print(f"  [yellow]Transcription failed: {e}[/yellow]")

            results.append({
                "job": job,
                "status": "completed",
                "clips": clip_count,
                "personas": persona_count,
                "output_dir": str(job_output_dir),
            })
            console.print(f"  [green]Completed: {persona_count} persona files[/green]")

        except Exception as e:
            console.print(f"  [red]Job failed: {e}[/red]")
            results.append({"job": job, "status": "failed", "reason": str(e)})

    # Summary
    console.print(f"\n[bold]Batch Run Summary:[/bold]")
    completed = sum(1 for r in results if r.get("status") == "completed")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    failed = sum(1 for r in results if r.get("status") == "failed")
    console.print(f"  [green]Completed: {completed}[/green]")
    console.print(f"  [dim]Skipped: {skipped}[/dim]")
    if failed:
        console.print(f"  [red]Failed: {failed}[/red]")

    # Save results
    results_file = output_dir / "batch_results.json"
    results_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    console.print(f"\n[green]Results saved to {results_file}[/green]")


@batch_app.command("status")
def batch_status(
    output_dir: Path = typer.Option(Path("/mnt/storage12tb/media/persona_exemplars"), "--output-dir", "-o", help="Base output directory"),
):
    """Show status of batch-processed emotion exemplars."""
    if not output_dir.exists():
        console.print(f"[yellow]Output directory not found: {output_dir}[/yellow]")
        return

    table = Table(title="Persona Exemplar Status")
    table.add_column("Emotion", style="bold cyan")
    table.add_column("Movies", style="green", justify="right")
    table.add_column("Clips", style="yellow", justify="right")
    table.add_column("Personas", style="magenta", justify="right")

    totals = {"movies": 0, "clips": 0, "personas": 0}

    for emotion in sorted(VALID_EMOTIONS):
        emotion_dir = output_dir / emotion
        if not emotion_dir.exists():
            table.add_row(emotion, "0", "0", "0")
            continue

        movie_count = sum(1 for d in emotion_dir.iterdir() if d.is_dir())
        clip_count = len(list(emotion_dir.glob("*/clips/*.mp4")))
        persona_count = len(list(emotion_dir.glob("*/*_persona.json")))

        totals["movies"] += movie_count
        totals["clips"] += clip_count
        totals["personas"] += persona_count

        table.add_row(emotion, str(movie_count), str(clip_count), str(persona_count))

    table.add_row("─" * 12, "─" * 6, "─" * 6, "─" * 8)
    table.add_row("[bold]TOTAL[/bold]", str(totals["movies"]), str(totals["clips"]), str(totals["personas"]))

    console.print(table)


# -----------------------------------------------------------------------------
# Subtitle Download Commands
# -----------------------------------------------------------------------------
# Try to import subliminal for subtitle downloads
try:
    from subliminal import download_best_subtitles, save_subtitles, region
    from subliminal.video import Video
    from babelfish import Language
    HAVE_SUBLIMINAL = True
except ImportError:
    HAVE_SUBLIMINAL = False


# -----------------------------------------------------------------------------
# Acquisition Commands (from dogpile research)
# -----------------------------------------------------------------------------
acquire_app = typer.Typer(help="Acquire movies from dogpile research")
app.add_typer(acquire_app, name="acquire")

# Radarr configuration
RADARR_URL = os.environ.get("RADARR_URL", "http://localhost:7878")
RADARR_API_KEY = os.environ.get("RADARR_API_KEY", "")


@acquire_app.command("from-dogpile")
def acquire_from_dogpile(
    dogpile_file: Optional[Path] = typer.Option(None, "--file", "-f", help="Dogpile JSON or markdown output file"),
    emotions: Optional[list[str]] = typer.Option(None, "--emotion", "-e", help="Filter to specific emotions"),
    search_only: bool = typer.Option(False, "--search-only", "-s", help="Only search, don't queue downloads"),
    prefer_sdh: bool = typer.Option(True, "--prefer-sdh", help="Prefer releases with SDH subtitles"),
    max_results: int = typer.Option(3, "--max-results", help="Max NZB results per movie"),
):
    """
    Search NZBGeek for movies recommended by dogpile research.
    Prioritizes releases with SDH/CC subtitles for emotion cue extraction.
    """
    _validate_env()

    # Build movie list from EMOTION_MOVIE_MAP or dogpile file
    movies_to_acquire: list[Dict[str, Any]] = []

    if dogpile_file and dogpile_file.exists():
        # Parse dogpile output (simplified - looks for movie titles)
        content = dogpile_file.read_text()
        # Extract movie titles from common patterns
        import re
        # Match patterns like "Movie Title (Year)" or "Movie Title"
        patterns = [
            r'[•\-\*]\s+([A-Z][^•\-\*\n]+?)(?:\s+\([12][0-9]{3}\))?(?:\s*[-–—]|$)',
            r'"([^"]+)"',  # Quoted titles
        ]
        found_titles = set()
        for pattern in patterns:
            matches = re.findall(pattern, content)
            for m in matches:
                title = m.strip()
                if len(title) > 3 and len(title) < 100:
                    found_titles.add(title)

        for title in found_titles:
            movies_to_acquire.append({"title": title, "emotion": "unknown", "actor": "Unknown"})

        console.print(f"[cyan]Found {len(movies_to_acquire)} movie titles in dogpile output[/cyan]")
    else:
        # Use built-in EMOTION_MOVIE_MAP
        emotion_filter = set(e.lower() for e in emotions) if emotions else set(EMOTION_MOVIE_MAP.keys())

        for emotion, movie_list in EMOTION_MOVIE_MAP.items():
            if emotion not in emotion_filter:
                continue
            for movie in movie_list:
                if movie.get("source") in ("youtube", "tv"):
                    continue  # Skip non-movie sources
                movies_to_acquire.append({
                    "title": movie["title"],
                    "emotion": emotion,
                    "actor": movie.get("actor", "Unknown"),
                    "scenes": movie.get("scenes", []),
                })

        console.print(f"[cyan]Searching for {len(movies_to_acquire)} movies from emotion mappings[/cyan]")

    # Check which movies are already in library
    available_movies = set()
    for media_dir in DEFAULT_MEDIA_DIRS:
        media_path = Path(media_dir)
        if media_path.exists():
            for item in media_path.iterdir():
                if item.is_dir():
                    available_movies.add(item.name.lower())

    # Search NZBGeek for missing movies
    results_table = Table(title="Movie Acquisition Search")
    results_table.add_column("Movie", style="green", max_width=30)
    results_table.add_column("Emotion", style="cyan")
    results_table.add_column("Status", style="yellow")
    results_table.add_column("Best Release", style="dim", max_width=40)

    session = get_requests_session()
    acquired_count = 0
    already_have = 0

    for movie in movies_to_acquire:
        title = movie["title"]
        emotion = movie.get("emotion", "unknown")

        # Check if already in library
        title_lower = title.lower()
        in_library = any(title_lower in lib_title for lib_title in available_movies)

        if in_library:
            results_table.add_row(title[:30], emotion, "[green]In Library[/green]", "-")
            already_have += 1
            continue

        if search_only or not NZB_API_KEY:
            # Just search and report
            params = {
                "t": "search",
                "q": title,
                "cat": "2000",  # Movies
                "apikey": NZB_API_KEY or "demo",
                "o": "json",
            }
            url = f"{NZB_BASE_URL.rstrip('/')}/api"

            try:
                resp = session.get(url, params=params, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    items = []
                    if "channel" in data and "item" in data["channel"]:
                        items = data["channel"]["item"]
                        if isinstance(items, dict):
                            items = [items]

                    if items:
                        # Find best release (prefer SDH)
                        best = None
                        for item in items[:max_results]:
                            has_subs = release_has_subtitle_hint(item)
                            if prefer_sdh and has_subs:
                                best = item
                                break
                            if best is None:
                                best = item

                        if best:
                            best_title = best.get("title", "Unknown")[:40]
                            subs_flag = " [SDH]" if release_has_subtitle_hint(best) else ""
                            results_table.add_row(
                                title[:30],
                                emotion,
                                f"[yellow]{len(items)} results[/yellow]",
                                f"{best_title}{subs_flag}",
                            )
                            acquired_count += 1
                        else:
                            results_table.add_row(title[:30], emotion, "[red]No results[/red]", "-")
                    else:
                        results_table.add_row(title[:30], emotion, "[red]No results[/red]", "-")
                else:
                    results_table.add_row(title[:30], emotion, f"[red]HTTP {resp.status_code}[/red]", "-")
            except Exception as e:
                results_table.add_row(title[:30], emotion, f"[red]Error[/red]", str(e)[:30])
        else:
            results_table.add_row(title[:30], emotion, "[dim]Skipped[/dim]", "-")

    console.print(results_table)
    console.print(f"\n[green]Already in library: {already_have}[/green]")
    console.print(f"[yellow]Found on NZBGeek: {acquired_count}[/yellow]")

    if not NZB_API_KEY:
        console.print("[yellow]Note: Set NZB_GEEK_API_KEY to enable full search[/yellow]")


# =============================================================================
# RADARR HORUS PRESET - Exact configuration for TTS voice training
# =============================================================================
# This preset enforces:
#   - 1080p maximum (no 4K) - sufficient quality for voice extraction
#   - 15GB maximum file size - prevents storage bloat
#   - English audio required - for TTS training
#   - SDH/CC subtitles required - for emotion tagging
#
# HOW TO CONFIGURE IN RADARR:
# --------------------------
# 1. Settings > Profiles > Quality Profiles > Add new profile "Horus TTS"
#    - Name: "Horus TTS"
#    - Enable ONLY these qualities (disable all others):
#      * Bluray-1080p (preferred)
#      * WEB 1080p
#      * HDTV-1080p (fallback)
#    - For Bluray-1080p, set:
#      * Min: 0 MB
#      * Max: 15000 MB (15GB limit)
#    - For WEB 1080p:
#      * Min: 0 MB
#      * Max: 12000 MB
#    - Language: English (any)
#
# 2. Settings > Custom Formats > Add "SDH Subtitles"
#    - Conditions: Release Title contains "SDH" OR "CC" OR "Subs"
#    - Score: +100 (prefer releases with subtitles)
#
# 3. Settings > Profiles > Quality Profiles > "Horus TTS"
#    - Custom Format Scores: SDH Subtitles = +100
#    - Minimum Custom Format Score: 0 (allows non-SDH but prefers SDH)
#
# 4. Settings > Profiles > Language Profiles (if v3+)
#    - Create "English Only" profile
#    - Enable only English
# =============================================================================

RADARR_HORUS_PRESET = {
    "name": "horus_tts",
    "description": "1080p Bluray/WEB, max 15GB, English audio, SDH subtitles preferred",
    "quality_profile": {
        "name": "Horus TTS",
        "cutoff": "Bluray-1080p",
        "items": [
            {"quality": "Bluray-1080p", "allowed": True, "min_size_mb": 0, "max_size_mb": 15000},
            {"quality": "WEB 1080p", "allowed": True, "min_size_mb": 0, "max_size_mb": 12000},
            {"quality": "HDTV-1080p", "allowed": True, "min_size_mb": 0, "max_size_mb": 10000},
            # Explicitly disabled - no 4K
            {"quality": "Bluray-2160p", "allowed": False},
            {"quality": "WEB 2160p", "allowed": False},
            {"quality": "Remux-2160p", "allowed": False},
            {"quality": "Remux-1080p", "allowed": False},  # Too large
        ],
    },
    "custom_formats": [
        {
            "name": "SDH Subtitles",
            "conditions": [
                {"type": "release_title", "pattern": r"(SDH|CC|Subs|Subtitles)", "negate": False},
            ],
            "score": 100,  # Prefer releases with subtitles
        },
        {
            "name": "English Audio",
            "conditions": [
                {"type": "language", "value": "English", "negate": False},
            ],
            "score": 50,
        },
    ],
    "constraints": {
        "max_size_gb": 15,
        "language": "English",
        "require_subtitles_in_title": True,  # Prefer releases mentioning subs
    },
}

# Legacy presets for backwards compatibility
RADARR_QUALITY_PRESETS = {
    "horus_standard": {
        "description": "1080p Bluray, max 15GB, English audio + SDH subs (recommended)",
        "profile_id": 1,  # Update to match your Radarr 'Horus TTS' profile ID
        "max_size_gb": 15,
        "preferred_quality": "Bluray-1080p",
        "language": "English",
        "require_subtitles": True,
    },
    "horus_compact": {
        "description": "1080p Web, max 10GB, English + subs",
        "profile_id": 2,
        "max_size_gb": 10,
        "preferred_quality": "WEB 1080p",
        "language": "English",
        "require_subtitles": True,
    },
}

# Default constraints - ENFORCED for all acquisitions
RADARR_MAX_SIZE_GB_DEFAULT = 15.0  # NEVER download movies over 15GB
RADARR_REQUIRED_LANGUAGE = "English"  # English audio required for TTS
RADARR_REQUIRE_SUBTITLES = True  # SDH/CC subtitles required for emotion tagging
RADARR_MAX_QUALITY = "1080p"  # NO 4K - 1080p is sufficient for voice extraction


@acquire_app.command("radarr")
def acquire_radarr(
    emotions: Optional[list[str]] = typer.Option(None, "--emotion", "-e", help="Filter to specific emotions"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be added without adding"),
    quality_profile: int = typer.Option(1, "--quality", "-q", help="Radarr quality profile ID"),
    root_folder: str = typer.Option("/mnt/storage12tb/media/movies", "--root", "-r", help="Root folder for movies"),
    preset: Optional[str] = typer.Option(None, "--preset", "-p", help="Quality preset (horus_standard, horus_compact)"),
    max_size_gb: float = typer.Option(15.0, "--max-size", help="Maximum file size in GB (default: 15GB)"),
):
    """
    Add missing movies from emotion mappings to Radarr for automated download.
    Radarr will handle searching indexers and downloading with preferred quality.

    IMPORTANT: All downloads are 1080p max, 15GB max size by default.
    No 4K downloads - 1080p is optimal for TTS voice extraction.

    Configure your quality profile in Radarr: Settings > Profiles > Quality Profiles
    - Enable only Bluray-1080p and WEB 1080p qualities
    - Set 'Max Size' to 15GB for Bluray-1080p

    Presets (use --preset):
      horus_standard: 1080p Bluray, max 15GB (recommended)
      horus_compact:  1080p Web, max 10GB
    """
    # Apply preset if specified
    if preset:
        if preset not in RADARR_QUALITY_PRESETS:
            console.print(f"[red]Unknown preset '{preset}'. Available: {list(RADARR_QUALITY_PRESETS.keys())}[/red]")
            raise typer.Exit(code=1)
        preset_config = RADARR_QUALITY_PRESETS[preset]
        quality_profile = preset_config["profile_id"]
        max_size_gb = preset_config["max_size_gb"]
        console.print(f"[cyan]Using preset '{preset}': {preset_config['description']}[/cyan]")

    # Enforce 15GB limit by default
    if max_size_gb > RADARR_MAX_SIZE_GB_DEFAULT:
        console.print(f"[yellow]Warning: max_size_gb ({max_size_gb}GB) exceeds recommended 15GB limit[/yellow]")
        console.print("[yellow]Consider using --preset horus_standard for optimal TTS training[/yellow]")

    console.print(f"[dim]Quality profile ID: {quality_profile}, Max size: {max_size_gb}GB[/dim]")

    if not RADARR_API_KEY:
        console.print("[red]RADARR_API_KEY not set. Get it from Radarr > Settings > General[/red]")
        raise typer.Exit(code=1)

    session = get_requests_session()
    headers = {"X-Api-Key": RADARR_API_KEY}

    # Get existing movies in Radarr
    try:
        resp = session.get(f"{RADARR_URL}/api/v3/movie", headers=headers, timeout=10)
        resp.raise_for_status()
        existing_movies = {m.get("title", "").lower() for m in resp.json()}
        console.print(f"[cyan]Radarr has {len(existing_movies)} movies[/cyan]")
    except Exception as e:
        console.print(f"[red]Failed to connect to Radarr: {e}[/red]")
        raise typer.Exit(code=1)

    # Build list of movies to add
    emotion_filter = set(e.lower() for e in emotions) if emotions else set(EMOTION_MOVIE_MAP.keys())
    movies_to_add: list[Dict[str, Any]] = []

    for emotion, movie_list in EMOTION_MOVIE_MAP.items():
        if emotion not in emotion_filter:
            continue
        for movie in movie_list:
            if movie.get("source") in ("youtube", "tv"):
                continue
            title = movie["title"]
            if title.lower() not in existing_movies:
                movies_to_add.append({
                    "title": title,
                    "emotion": emotion,
                    "actor": movie.get("actor", "Unknown"),
                })

    if not movies_to_add:
        console.print("[green]All emotion mapping movies are already in Radarr[/green]")
        return

    console.print(f"[yellow]Adding {len(movies_to_add)} movies to Radarr[/yellow]")

    # Search and add each movie
    added = 0
    for movie in movies_to_add:
        title = movie["title"]

        # Search for movie in TMDb via Radarr
        try:
            search_resp = session.get(
                f"{RADARR_URL}/api/v3/movie/lookup",
                headers=headers,
                params={"term": title},
                timeout=15,
            )
            search_resp.raise_for_status()
            results = search_resp.json()

            if not results:
                console.print(f"[yellow]Not found: {title}[/yellow]")
                continue

            # Take first result
            tmdb_movie = results[0]

            if dry_run:
                console.print(f"[dim]Would add: {tmdb_movie.get('title')} ({tmdb_movie.get('year')})[/dim]")
                added += 1
                continue

            # Add to Radarr
            add_payload = {
                "title": tmdb_movie.get("title"),
                "tmdbId": tmdb_movie.get("tmdbId"),
                "year": tmdb_movie.get("year"),
                "qualityProfileId": quality_profile,
                "rootFolderPath": root_folder,
                "monitored": True,
                "addOptions": {
                    "searchForMovie": True,  # Automatically search for download
                },
            }

            add_resp = session.post(
                f"{RADARR_URL}/api/v3/movie",
                headers=headers,
                json=add_payload,
                timeout=15,
            )

            if add_resp.status_code in (200, 201):
                console.print(f"[green]Added: {title} ({tmdb_movie.get('year')})[/green]")
                added += 1
            elif add_resp.status_code == 400:
                # Already exists
                console.print(f"[dim]Already in Radarr: {title}[/dim]")
            else:
                console.print(f"[red]Failed to add {title}: {add_resp.status_code}[/red]")

        except Exception as e:
            console.print(f"[red]Error adding {title}: {e}[/red]")

    console.print(f"\n[green]Added {added} movies to Radarr[/green]")
    if not dry_run:
        console.print("[cyan]Radarr will automatically search and download these movies[/cyan]")


@acquire_app.command("list")
def acquire_list(
    emotions: Optional[list[str]] = typer.Option(None, "--emotion", "-e", help="Filter to specific emotions"),
    show_scenes: bool = typer.Option(False, "--scenes", "-s", help="Show target scenes"),
):
    """List all movies in the emotion-movie mappings."""
    emotion_filter = set(e.lower() for e in emotions) if emotions else set(EMOTION_MOVIE_MAP.keys())

    table = Table(title="Horus Emotion Movie Mappings")
    table.add_column("Emotion", style="bold cyan")
    table.add_column("Movie", style="green")
    table.add_column("Actor Model", style="yellow")
    if show_scenes:
        table.add_column("Target Scenes", style="dim")

    for emotion in sorted(EMOTION_MOVIE_MAP.keys()):
        if emotion not in emotion_filter:
            continue
        for movie in EMOTION_MOVIE_MAP[emotion]:
            row = [emotion, movie["title"], movie.get("actor", "Unknown")]
            if show_scenes:
                row.append(", ".join(movie.get("scenes", [])[:3]))
            table.add_row(*row)

    console.print(table)


@subs_app.command("download")
def subs_download(
    video_path: Path = typer.Argument(..., exists=True, help="Video file to find subtitles for"),
    language: str = typer.Option("en", "--language", "-l", help="Subtitle language code (e.g., en, es, fr)"),
    hearing_impaired: bool = typer.Option(True, "--hi", help="Prefer hearing impaired (SDH) subtitles"),
    providers: Optional[list[str]] = typer.Option(None, "--provider", "-p", help="Subtitle providers to use"),
):
    """
    Download subtitles for a video file using subliminal.
    Searches OpenSubtitles, Podnapisi, and other providers.
    """
    if not HAVE_SUBLIMINAL:
        console.print("[red]subliminal not installed. Run: uv pip install subliminal[/red]")
        raise typer.Exit(code=1)

    # Configure subliminal cache
    region.configure('dogpile.cache.dbm', arguments={'filename': '/tmp/subliminal_cache.dbm'})

    video_path = video_path.resolve()
    console.print(f"[cyan]Scanning for subtitles: {video_path.name}[/cyan]")

    try:
        video = Video.fromname(str(video_path))
    except Exception as e:
        console.print(f"[red]Failed to parse video: {e}[/red]")
        raise typer.Exit(code=1)

    # Set up providers (opensubtitles requires API key via OPENSUBTITLES_USERNAME/PASSWORD)
    provider_list = providers or ['opensubtitles', 'podnapisi']

    # Download subtitles - convert 2-letter to 3-letter code
    lang_map = {"en": "eng", "es": "spa", "fr": "fra", "de": "deu", "it": "ita", "pt": "por"}
    lang_code = lang_map.get(language, language)
    lang = Language(lang_code)
    subtitles = download_best_subtitles(
        {video},
        {lang},
        providers=provider_list,
        hearing_impaired=hearing_impaired,
    )

    if not subtitles.get(video):
        console.print(f"[yellow]No subtitles found for {video_path.name}[/yellow]")
        console.print("[dim]Try: --hi=false or different providers[/dim]")
        raise typer.Exit(code=1)

    # Save subtitles
    saved = save_subtitles(video, subtitles[video])
    for sub in saved:
        srt_path = video_path.with_suffix(f'.{language}.srt')
        console.print(f"[green]Downloaded: {srt_path.name}[/green]")
        console.print(f"  Provider: {sub.provider_name}")
        console.print(f"  Hearing Impaired: {sub.hearing_impaired}")


@subs_app.command("batch")
def subs_batch(
    media_dir: Path = typer.Argument(..., exists=True, help="Media directory to scan"),
    language: str = typer.Option("en", "--language", "-l", help="Subtitle language code"),
    skip_existing: bool = typer.Option(True, "--skip-existing", help="Skip videos that already have .srt files"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be downloaded"),
):
    """
    Batch download subtitles for all videos in a directory.
    """
    if not HAVE_SUBLIMINAL:
        console.print("[red]subliminal not installed. Run: uv pip install subliminal[/red]")
        raise typer.Exit(code=1)

    region.configure('dogpile.cache.dbm', arguments={'filename': '/tmp/subliminal_cache.dbm'})

    media_dir = media_dir.resolve()
    console.print(f"[cyan]Scanning {media_dir} for videos without subtitles...[/cyan]")

    videos_to_process: list[Path] = []

    for item in media_dir.iterdir():
        if not item.is_dir():
            continue

        video = find_media_file(item)
        if not video:
            continue

        # Check for existing subtitles
        existing_srt = find_subtitle_file(item, prefer_sdh=False)
        if skip_existing and existing_srt:
            console.print(f"[dim]Skip: {item.name} (has subtitles)[/dim]")
            continue

        videos_to_process.append(video)

    console.print(f"\n[green]Found {len(videos_to_process)} videos needing subtitles[/green]")

    if dry_run:
        for v in videos_to_process[:20]:
            console.print(f"  Would download: {v.parent.name}")
        if len(videos_to_process) > 20:
            console.print(f"  ... and {len(videos_to_process) - 20} more")
        return

    # Process videos
    from subliminal import scan_videos

    videos = scan_videos([str(v.parent) for v in videos_to_process])
    lang = Language(language)

    console.print(f"\n[cyan]Downloading subtitles...[/cyan]")
    subtitles = download_best_subtitles(
        videos,
        {lang},
        providers=['opensubtitles', 'podnapisi'],
        hearing_impaired=True,
    )

    success = 0
    for video, subs in subtitles.items():
        if subs:
            save_subtitles(video, subs)
            success += 1
            console.print(f"[green]✓ {Path(video.name).stem}[/green]")
        else:
            console.print(f"[yellow]✗ {Path(video.name).stem}[/yellow]")

    console.print(f"\n[green]Downloaded {success}/{len(videos_to_process)} subtitles[/green]")


# =============================================================================
# AGENT-FRIENDLY COMMANDS
# =============================================================================
# These commands are designed for easy use by project agents like Horus.
# They integrate with dogpile, agent-inbox, and provide single-step workflows.
# =============================================================================

# Typer sub-app for agent commands
agent_app = typer.Typer(help="Agent-friendly movie research and extraction")
app.add_typer(agent_app, name="agent")

# Inventory file for tracking processed clips
INVENTORY_FILE = Path(os.environ.get("MOVIE_INGEST_INVENTORY", Path.home() / ".movie-ingest-inventory.json"))
INVENTORY_LOCK_FILE = INVENTORY_FILE.with_suffix(".lock")


def _load_inventory() -> Dict[str, Any]:
    """Load the clip inventory registry with file locking."""
    import fcntl

    if not INVENTORY_FILE.exists():
        return {"clips": [], "movies_processed": [], "last_updated": None}

    try:
        # Use shared lock for reading
        with open(INVENTORY_LOCK_FILE, 'a+') as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)
            try:
                content = INVENTORY_FILE.read_text()
                if not content.strip():
                    console.print("[yellow]Warning: Inventory file is empty, starting fresh[/yellow]")
                    return {"clips": [], "movies_processed": [], "last_updated": None}
                return json.loads(content)
            except json.JSONDecodeError as e:
                console.print(f"[red]Error: Inventory file corrupted: {e}[/red]")
                # Create backup of corrupted file
                backup = INVENTORY_FILE.with_suffix(".corrupted.json")
                shutil.copy(INVENTORY_FILE, backup)
                console.print(f"[yellow]Backup saved to {backup}[/yellow]")
                return {"clips": [], "movies_processed": [], "last_updated": None}
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        console.print(f"[red]Error loading inventory: {e}[/red]")
        return {"clips": [], "movies_processed": [], "last_updated": None}


def _save_inventory(inventory: Dict[str, Any]) -> bool:
    """Save the clip inventory registry with atomic write and file locking."""
    import fcntl
    import tempfile

    inventory["last_updated"] = datetime.now(timezone.utc).isoformat()

    try:
        # Ensure parent directory exists
        INVENTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Use exclusive lock for writing
        with open(INVENTORY_LOCK_FILE, 'a+') as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                # Write to temp file first (atomic write pattern)
                fd, tmp_path = tempfile.mkstemp(
                    dir=INVENTORY_FILE.parent,
                    prefix=".inventory_",
                    suffix=".tmp"
                )
                try:
                    with os.fdopen(fd, 'w') as tmp_file:
                        json.dump(inventory, tmp_file, indent=2)
                    # Atomic rename
                    os.replace(tmp_path, INVENTORY_FILE)
                    return True
                except Exception:
                    # Clean up temp file on failure
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    raise
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        console.print(f"[red]Error saving inventory: {e}[/red]")
        return False


def _run_dogpile(query: str, preset: str = "movie_scenes", timeout_sec: int = 300) -> Dict[str, Any]:
    """Run dogpile search and return results.

    Args:
        query: Search query string
        preset: Dogpile preset to use (default: movie_scenes)
        timeout_sec: Timeout in seconds (default: 300)

    Returns:
        Dict with either results or error information
    """
    skills_dir = Path(__file__).resolve().parents[1]
    dogpile_script = skills_dir / "dogpile" / "dogpile.py"

    if not dogpile_script.exists():
        return {"error": f"Dogpile not found at {dogpile_script}", "status": "not_found"}

    cmd = [
        sys.executable, str(dogpile_script),
        "search", query,
        "--preset", preset,
        "--json"
    ]

    proc = None
    try:
        # Use Popen for better process control
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(skills_dir / "dogpile")
        )

        try:
            stdout, stderr = proc.communicate(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            # CRITICAL: Kill the process on timeout to prevent zombies
            proc.kill()
            proc.wait(timeout=5)  # Wait for process to actually die
            return {
                "error": f"Dogpile search timed out after {timeout_sec}s",
                "status": "timeout",
                "query": query
            }

        if proc.returncode == 0:
            # Try to parse JSON from output
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                # Return raw output if not valid JSON
                return {"raw_output": stdout, "status": "success", "query": query}
        else:
            return {
                "error": stderr or "Unknown error",
                "status": "failed",
                "returncode": proc.returncode,
                "query": query
            }
    except FileNotFoundError:
        return {"error": f"Python interpreter not found: {sys.executable}", "status": "exception"}
    except Exception as e:
        # Clean up process if still running
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        return {"error": str(e), "status": "exception", "query": query}


def _send_to_inbox(
    to_project: str,
    message: str,
    message_type: str = "request",
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """Send a message via agent-inbox."""
    skills_dir = Path(__file__).resolve().parents[1]
    inbox_script = skills_dir / "agent-inbox" / "inbox.py"

    if not inbox_script.exists():
        console.print(f"[yellow]Agent inbox not found at {inbox_script}[/yellow]")
        return False

    # Prepare message with metadata
    full_message = message
    if metadata:
        full_message = f"{message}\n\n---\nMetadata: {json.dumps(metadata)}"

    cmd = [
        sys.executable, str(inbox_script),
        "send",
        "--to", to_project,
        "--type", message_type,
        full_message
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception as e:
        console.print(f"[red]Failed to send to inbox: {e}[/red]")
        return False


@agent_app.command("recommend")
def recommend_movies(
    emotion: str = typer.Argument(..., help="Target emotion (rage, anger, sorrow, regret, camaraderie, command)"),
    actor_model: Optional[str] = typer.Option(None, "--actor", "-a", help="Actor model (DDL, Pacino, Crowe, Carlin, Bardem, Butler)"),
    library_path: Optional[Path] = typer.Option(None, "--library", "-l", help="Local media library to cross-reference"),
    exclude_movies: Optional[str] = typer.Option(None, "--exclude", "-x", help="Comma-separated movies to exclude"),
    output_json: Optional[Path] = typer.Option(None, "--output", "-o", help="Save recommendations to JSON"),
    max_results: int = typer.Option(5, "--max", "-m", help="Maximum movie recommendations"),
):
    """
    Research movies with emotional scenes for TTS training.

    Returns abstracts, balanced reviews, and scene recommendations for Horus evaluation.
    Uses dogpile with the movie_scenes preset for comprehensive research.

    Example:
        python movie_ingest.py agent recommend rage --actor DDL --library /mnt/storage12tb/media/movies
    """
    emotion = emotion.lower()
    if emotion not in VALID_EMOTIONS:
        raise typer.BadParameter(f"Unknown emotion '{emotion}'. Allowed: {sorted(VALID_EMOTIONS)}")

    # Get archetype info for this emotion
    archetype = HORUS_ARCHETYPE_MAP.get(emotion, {})
    default_actor = archetype.get("actor_model", "Unknown")
    voice_tone = archetype.get("voice_tone", "neutral")

    # Build search query
    actor_hint = actor_model or default_actor.split("(")[0].strip()
    exclusions = [m.strip() for m in (exclude_movies or "").split(",") if m.strip()]

    query_parts = [
        f"war movies {emotion} scenes",
        f"{actor_hint} intensity performance",
        voice_tone.replace("_", " "),
        "dramatic monologue dialogue"
    ]
    query = " ".join(query_parts)

    console.print(f"[cyan]Researching movies for emotion: {emotion}[/cyan]")
    console.print(f"[dim]Actor model: {default_actor}[/dim]")
    console.print(f"[dim]Voice tone: {voice_tone}[/dim]")
    console.print(f"[dim]Query: {query}[/dim]\n")

    # Run dogpile search
    console.print("[cyan]Running dogpile search (movie_scenes preset)...[/cyan]")
    dogpile_results = _run_dogpile(query, preset="movie_scenes")

    if "error" in dogpile_results:
        console.print(f"[yellow]Dogpile warning: {dogpile_results.get('error')}[/yellow]")

    # Check local library for available movies
    local_movies: Dict[str, Path] = {}
    if library_path and library_path.exists():
        console.print(f"[cyan]Scanning local library: {library_path}[/cyan]")
        for item in library_path.iterdir():
            if item.is_dir():
                video = find_media_file(item)
                if video:
                    # Extract movie name from directory
                    movie_name = item.name
                    # Remove year pattern like "(2004)" for matching
                    clean_name = re.sub(r'\s*\(\d{4}\)\s*$', '', movie_name)
                    local_movies[clean_name.lower()] = item

    # Build recommendations structure
    recommendations = {
        "query": query,
        "emotion_target": emotion,
        "actor_model": default_actor,
        "voice_tone": voice_tone,
        "archetype": archetype.get("primary_archetype", "unknown"),
        "bdi_patterns": {
            "belief": archetype.get("belief_pattern", ""),
            "desire": archetype.get("desire_pattern", ""),
            "intention": archetype.get("intention_pattern", ""),
        },
        "dogpile_results": dogpile_results,
        "local_library_count": len(local_movies),
        "exclusions": exclusions,
        "candidates": [],
        "instructions_for_horus": f"""
## Movie Selection for {emotion.upper()} Emotion

Review the candidates below. For each movie, consider:
1. Does the actor's performance match the {voice_tone.replace('_', ' ')} tone needed?
2. Are there specific scenes with the right emotional intensity?
3. Is SDH subtitle availability confirmed?
4. Is the movie available locally or via streaming?

After reviewing, respond with your selections in this format:
```
APPROVED: Movie Title (Year) - Scene: "description" @ timestamp
QUEUE: Movie Title (Year) - for {emotion} later
SKIP: Movie Title (Year) - reason
```

Then I'll extract the clips using:
  python movie_ingest.py agent quick --movie "path" --emotion {emotion} --scene "description" --timestamp "HH:MM:SS-HH:MM:SS"
""",
    }

    # Display for Horus to review
    console.print("\n" + "=" * 70)
    console.print(f"[bold green]MOVIE RECOMMENDATIONS FOR {emotion.upper()}[/bold green]")
    console.print("=" * 70)

    console.print(f"\n[bold]Target Profile:[/bold]")
    console.print(f"  Actor Model: {default_actor}")
    console.print(f"  Voice Tone: {voice_tone}")
    console.print(f"  Archetype: {archetype.get('primary_archetype', 'unknown')}")

    console.print(f"\n[bold]BDI Patterns to Match:[/bold]")
    console.print(f"  Belief: {archetype.get('belief_pattern', 'N/A')}")
    console.print(f"  Desire: {archetype.get('desire_pattern', 'N/A')}")
    console.print(f"  Intention: {archetype.get('intention_pattern', 'N/A')}")

    if local_movies:
        console.print(f"\n[bold]Local Library ({len(local_movies)} movies available):[/bold]")
        for name, path in sorted(local_movies.items())[:10]:
            console.print(f"  ✓ {path.name}")
        if len(local_movies) > 10:
            console.print(f"  ... and {len(local_movies) - 10} more")

    console.print(f"\n[bold]Research Results:[/bold]")
    if "raw_output" in dogpile_results:
        console.print(dogpile_results["raw_output"][:2000])
    else:
        console.print(json.dumps(dogpile_results, indent=2)[:2000])

    console.print("\n" + "-" * 70)
    console.print(recommendations["instructions_for_horus"])

    # Save to JSON if requested
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w") as f:
            json.dump(recommendations, f, indent=2, default=str)
        console.print(f"\n[green]Recommendations saved to {output_json}[/green]")

    return recommendations


@agent_app.command("quick")
def quick_extract(
    movie: Path = typer.Option(..., "--movie", "-m", exists=True, help="Path to movie file or directory"),
    emotion: str = typer.Option(..., "--emotion", "-e", help="Target emotion"),
    scene: str = typer.Option(..., "--scene", "-s", help="Scene description"),
    timestamp: str = typer.Option(..., "--timestamp", "-t", help="Timestamp range (HH:MM:SS-HH:MM:SS or SS-SS)"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory for persona JSON"),
    characters: Optional[str] = typer.Option(None, "--characters", "-c", help="Comma-separated character names"),
    clip_id: Optional[str] = typer.Option(None, "--id", help="Custom clip ID (default: auto-generated)"),
    notify_project: Optional[str] = typer.Option(None, "--notify", help="Send completion to agent-inbox project"),
):
    """
    Single-step clip extraction: download subs → extract clip → create persona JSON.

    Consolidates the 6-step manual workflow into one command.

    Example:
        python movie_ingest.py agent quick \\
            --movie "/mnt/storage12tb/media/movies/Troy (2004)" \\
            --emotion rage \\
            --scene "Achilles beach landing" \\
            --timestamp "01:15:30-01:17:00" \\
            --output /home/graham/workspace/experiments/memory/persona/data/exemplars/rage/
    """
    emotion = emotion.lower()
    if emotion not in VALID_EMOTIONS:
        raise typer.BadParameter(f"Unknown emotion '{emotion}'. Allowed: {sorted(VALID_EMOTIONS)}")

    # Parse timestamp
    timestamp_pattern = r'^(\d{1,2}:?\d{2}:?\d{2})-(\d{1,2}:?\d{2}:?\d{2})$'
    match = re.match(timestamp_pattern, timestamp.replace(" ", ""))
    if not match:
        # Try simple seconds format
        sec_pattern = r'^(\d+)-(\d+)$'
        sec_match = re.match(sec_pattern, timestamp.replace(" ", ""))
        if sec_match:
            start_sec = int(sec_match.group(1))
            end_sec = int(sec_match.group(2))
        else:
            raise typer.BadParameter(f"Invalid timestamp format: {timestamp}. Use HH:MM:SS-HH:MM:SS or SS-SS")
    else:
        start_str, end_str = match.groups()
        start_sec = _parse_timestamp_to_seconds(start_str)
        end_sec = _parse_timestamp_to_seconds(end_str)

    if end_sec <= start_sec:
        raise typer.BadParameter("End timestamp must be after start timestamp")

    # Resolve movie path
    if movie.is_dir():
        video_file = find_media_file(movie)
        if not video_file:
            raise typer.BadParameter(f"No video file found in {movie}")
        movie_dir = movie
    else:
        video_file = movie
        movie_dir = movie.parent

    movie_title = movie_dir.name
    console.print(f"[cyan]Quick extraction: {movie_title}[/cyan]")
    console.print(f"[dim]Emotion: {emotion} | Scene: {scene}[/dim]")
    console.print(f"[dim]Timestamp: {_format_timestamp(start_sec)} - {_format_timestamp(end_sec)}[/dim]")

    # Step 1: Ensure subtitles exist
    console.print("\n[bold]Step 1/4:[/bold] Checking subtitles...")
    subtitle_file = find_subtitle_file(movie_dir, prefer_sdh=True)

    if not subtitle_file:
        console.print("[yellow]No subtitles found. Downloading...[/yellow]")
        # Try to download subtitles using subliminal
        try:
            from subliminal import download_best_subtitles, save_subtitles, scan_videos
            from subliminal.cache import region
            from babelfish import Language

            region.configure('dogpile.cache.dbm', arguments={'filename': '/tmp/subliminal_cache.dbm'})
            videos = scan_videos([str(movie_dir)])
            if videos:
                subs = download_best_subtitles(
                    videos,
                    {Language('eng')},
                    providers=['opensubtitles', 'podnapisi'],
                    hearing_impaired=True,
                )
                for video, sub_list in subs.items():
                    if sub_list:
                        save_subtitles(video, sub_list)
                        console.print(f"[green]✓ Downloaded subtitles[/green]")
        except ImportError:
            console.print("[red]subliminal not available. Please provide subtitles manually.[/red]")
            raise typer.Exit(1)

        # Re-check for subtitles
        subtitle_file = find_subtitle_file(movie_dir, prefer_sdh=True)
        if not subtitle_file:
            console.print("[red]Failed to obtain subtitles. Cannot proceed.[/red]")
            raise typer.Exit(1)

    console.print(f"[green]✓ Using subtitles: {subtitle_file.name}[/green]")

    # Step 2: Create clip directory and extract video segment
    console.print("\n[bold]Step 2/4:[/bold] Extracting video clip...")

    clip_name = clip_id or f"clip_{emotion}_{int(start_sec)}"
    emotion_clips_dir = movie_dir / f"{emotion}_clips"
    emotion_clips_dir.mkdir(exist_ok=True)

    clip_video = emotion_clips_dir / f"{clip_name}.mkv"
    clip_srt = emotion_clips_dir / f"{clip_name}.srt"
    audio_wav = emotion_clips_dir / f"{clip_name}.wav"

    # Track created files for cleanup on failure
    created_files: list[Path] = []

    def _cleanup_on_failure():
        """Clean up partial files on extraction failure."""
        for f in created_files:
            if f.exists():
                try:
                    f.unlink()
                    console.print(f"[dim]Cleaned up: {f.name}[/dim]")
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not clean up {f.name}: {e}[/yellow]")
        # Remove empty clip directory
        if emotion_clips_dir.exists() and not any(emotion_clips_dir.iterdir()):
            try:
                emotion_clips_dir.rmdir()
            except Exception:
                pass

    try:
        # Extract video segment
        ffmpeg_cmd = [
            get_ffmpeg_bin(), "-y",
            "-ss", _format_timestamp(start_sec),
            "-to", _format_timestamp(end_sec),
            "-i", str(video_file),
            "-c", "copy",
            str(clip_video)
        ]
        run_subprocess(ffmpeg_cmd, timeout_sec=120)
        created_files.append(clip_video)
        console.print(f"[green]✓ Extracted clip: {clip_video.name}[/green]")

        # Step 3: Extract subtitle window
        console.print("\n[bold]Step 3/4:[/bold] Extracting subtitle window...")
        has_subtitles = _extract_srt_window(subtitle_file, start_sec, end_sec, clip_srt)
        created_files.append(clip_srt)

        if not has_subtitles:
            console.print("[yellow]Warning: No subtitles in time window. Proceeding without emotion cues.[/yellow]")

        # Step 4: Run transcription to create persona JSON
        console.print("\n[bold]Step 4/4:[/bold] Creating persona JSON...")

        persona_dir = emotion_clips_dir / "persona"
        persona_dir.mkdir(exist_ok=True)

        # Call the existing transcribe function
        transcribe_video(
            input_file=clip_video,
            output_dir=persona_dir,
            model="medium",
            emotion=emotion,
            movie_title=movie_title,
            scene=scene,
            characters=characters,
            source_id=clip_name,
            subtitle_file=clip_srt if has_subtitles else None,
        )

        # Clean up intermediate audio file if it exists
        audio_file = persona_dir / f"{clip_name}.wav"
        if audio_file.exists():
            audio_file.unlink()

    except Exception as e:
        console.print(f"\n[red]Extraction failed: {e}[/red]")
        console.print("[yellow]Cleaning up partial files...[/yellow]")
        _cleanup_on_failure()
        raise typer.Exit(code=1)

    # Find the generated persona JSON
    persona_json = persona_dir / f"{clip_name}_persona.json"
    if not persona_json.exists():
        console.print(f"[red]Error: Persona JSON not created at {persona_json}[/red]")
        _cleanup_on_failure()
        raise typer.Exit(code=1)

    # Copy to output directory if specified
    final_output = persona_json
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        final_output = output_dir / persona_json.name
        shutil.copy(persona_json, final_output)
        console.print(f"[green]✓ Copied to: {final_output}[/green]")

    # Update inventory
    inventory = _load_inventory()
    inventory["clips"].append({
        "clip_id": clip_name,
        "movie": movie_title,
        "emotion": emotion,
        "scene": scene,
        "timestamp": f"{_format_timestamp(start_sec)}-{_format_timestamp(end_sec)}",
        "persona_json": str(final_output),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    if movie_title not in inventory["movies_processed"]:
        inventory["movies_processed"].append(movie_title)

    if not _save_inventory(inventory):
        console.print("[yellow]Warning: Failed to update inventory, but clip was extracted successfully[/yellow]")

    # Notify via agent-inbox if requested
    if notify_project:
        _send_to_inbox(
            to_project=notify_project,
            message=f"Clip extraction complete: {clip_name}",
            message_type="completion",
            metadata={
                "clip_id": clip_name,
                "movie": movie_title,
                "emotion": emotion,
                "scene": scene,
                "persona_json": str(final_output),
            }
        )
        console.print(f"[green]✓ Notified project: {notify_project}[/green]")

    console.print(f"\n[bold green]✓ Quick extraction complete![/bold green]")
    console.print(f"Persona JSON: {final_output}")

    return {"status": "success", "persona_json": str(final_output), "clip_id": clip_name}


def _parse_timestamp_to_seconds(ts: str) -> float:
    """Parse HH:MM:SS or MM:SS or SS to seconds."""
    parts = ts.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    else:
        return float(parts[0])


def _format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def _extract_srt_window(srt_path: Path, start_sec: float, end_sec: float, output_path: Path) -> bool:
    """Extract a window of subtitles with adjusted timestamps.

    Args:
        srt_path: Path to source SRT file
        start_sec: Start time in seconds
        end_sec: End time in seconds
        output_path: Path for output SRT file

    Returns:
        True if subtitles were extracted, False if no subtitles in window

    Raises:
        ValueError: If SRT file cannot be parsed or timestamps are invalid
    """
    from datetime import timedelta

    if start_sec >= end_sec:
        raise ValueError(f"Invalid timestamp range: start ({start_sec}) >= end ({end_sec})")

    # Try multiple encodings for robustness
    content = None
    encodings_to_try = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']

    for encoding in encodings_to_try:
        try:
            with open(srt_path, 'r', encoding=encoding) as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            continue

    if content is None:
        raise ValueError(f"Could not decode SRT file with any supported encoding: {srt_path}")

    # Normalize line endings (handle Windows CRLF)
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    # Parse SRT entries with more flexible regex
    # Allow for minor format variations (extra whitespace, etc.)
    pattern = r'(\d+)\s*\n\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})\s*\n(.*?)(?=\n\n|\n\d+\s*\n|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)

    if not matches:
        console.print(f"[yellow]Warning: No valid SRT entries found in {srt_path.name}[/yellow]")
        console.print("[dim]The SRT file may be malformed or use an unsupported format[/dim]")
        raise ValueError(f"No valid SRT entries found in {srt_path}")

    def parse_srt_time(t: str) -> timedelta:
        """Parse SRT timestamp, handling both comma and period separators."""
        try:
            # Normalize separator
            t = t.replace('.', ',')
            h, m, rest = t.split(":")
            s, ms = rest.split(",")
            return timedelta(hours=int(h), minutes=int(m), seconds=int(s), milliseconds=int(ms))
        except (ValueError, IndexError) as e:
            raise ValueError(f"Malformed SRT timestamp: '{t}'") from e

    def format_srt_time(td: timedelta) -> str:
        """Format timedelta as SRT timestamp."""
        total_ms = int(td.total_seconds() * 1000)
        hours, remainder = divmod(total_ms, 3600000)
        minutes, remainder = divmod(remainder, 60000)
        seconds, milliseconds = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    start_td = timedelta(seconds=start_sec)
    end_td = timedelta(seconds=end_sec)

    output_blocks = []
    idx = 1
    parse_errors = 0

    for num, start, end, text in matches:
        try:
            s = parse_srt_time(start)
            e = parse_srt_time(end)
        except ValueError as e:
            parse_errors += 1
            console.print(f"[dim]Skipping malformed entry {num}: {e}[/dim]")
            continue

        # Check if this subtitle OVERLAPS with our window (not just contained)
        # This catches subtitles that start before window but end inside,
        # or start inside but end after window
        if e > start_td and s < end_td:
            # Adjust timestamps relative to clip start
            new_s = max(timedelta(0), s - start_td)
            new_e = min(end_td - start_td, e - start_td)
            output_blocks.append(f"{idx}\n{format_srt_time(new_s)} --> {format_srt_time(new_e)}\n{text.strip()}\n")
            idx += 1

    if parse_errors > 0:
        console.print(f"[yellow]Warning: {parse_errors} SRT entries had parsing errors[/yellow]")

    if not output_blocks:
        console.print(f"[yellow]Warning: No subtitles found in time window {start_sec:.1f}s - {end_sec:.1f}s[/yellow]")
        console.print(f"[dim]Total entries in SRT: {len(matches)}, parse errors: {parse_errors}[/dim]")
        # Write empty file but return False to indicate no content
        output_path.write_text("")
        return False

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(output_blocks))

    console.print(f"[green]Extracted {len(output_blocks)} subtitle entries[/green]")
    return True


@agent_app.command("discover")
def discover_scenes(
    library_path: Path = typer.Argument(..., exists=True, help="Media library directory to scan"),
    emotion: Optional[str] = typer.Option(None, "--emotion", "-e", help="Filter by emotion"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Text search in subtitles"),
    actor_model: Optional[str] = typer.Option(None, "--actor", "-a", help="Actor model keywords to match"),
    output_json: Optional[Path] = typer.Option(None, "--output", "-o", help="Save results to JSON"),
    max_per_movie: int = typer.Option(5, "--max", "-m", help="Max scenes per movie"),
):
    """
    Discover emotion-matching scenes in local media library by scanning subtitles.

    Searches SRT files for keywords associated with each emotion and actor model.

    Example:
        python movie_ingest.py agent discover /mnt/storage12tb/media/movies --emotion rage
    """
    if emotion:
        emotion = emotion.lower()
        if emotion not in VALID_EMOTIONS:
            raise typer.BadParameter(f"Unknown emotion '{emotion}'. Allowed: {sorted(VALID_EMOTIONS)}")

    # Build keyword sets for each emotion
    emotion_keywords = {
        "rage": ["rage", "fury", "betray", "traitor", "destroy", "kill", "blood", "vengeance", "damn"],
        "anger": ["angry", "hate", "cold", "quiet", "fool", "mistake", "pay", "consequence"],
        "sorrow": ["mourn", "grief", "loss", "death", "gone", "remember", "honor", "fallen", "farewell"],
        "regret": ["mistake", "wrong", "should have", "could have", "fool", "error", "wish", "if only"],
        "camaraderie": ["brother", "together", "fight", "stand", "loyal", "friend", "comrade", "side"],
        "command": ["follow", "lead", "order", "fight", "glory", "victory", "charge", "men", "soldiers"],
    }

    # Get keywords for the target emotion or use query
    if emotion:
        keywords = emotion_keywords.get(emotion, [])
        if query:
            keywords.append(query.lower())
    elif query:
        keywords = [query.lower()]
    else:
        raise typer.BadParameter("Must specify --emotion or --query")

    console.print(f"[cyan]Scanning library: {library_path}[/cyan]")
    console.print(f"[dim]Keywords: {', '.join(keywords)}[/dim]\n")

    results = []
    movies_scanned = 0

    for movie_dir in library_path.iterdir():
        if not movie_dir.is_dir():
            continue

        # Find subtitle file
        srt_file = find_subtitle_file(movie_dir, prefer_sdh=True)
        if not srt_file:
            continue

        movies_scanned += 1
        movie_name = movie_dir.name

        try:
            with open(srt_file, 'r', encoding='utf-8-sig', errors='ignore') as f:
                content = f.read()
        except Exception:
            continue

        # Parse SRT and find matching entries
        pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\Z)'
        matches = re.findall(pattern, content, re.DOTALL)

        movie_matches = []
        for num, start, end, text in matches:
            text_lower = text.lower()
            matched_keywords = [kw for kw in keywords if kw in text_lower]

            if matched_keywords:
                movie_matches.append({
                    "timestamp": start.split(",")[0],
                    "text": text.strip()[:200],
                    "keywords_matched": matched_keywords,
                })

        if movie_matches:
            # Sort by number of keyword matches
            movie_matches.sort(key=lambda x: len(x["keywords_matched"]), reverse=True)

            results.append({
                "movie": movie_name,
                "subtitle_file": str(srt_file),
                "video_file": str(find_media_file(movie_dir) or ""),
                "matches": movie_matches[:max_per_movie],
                "total_matches": len(movie_matches),
            })

            console.print(f"[green]✓ {movie_name}[/green]: {len(movie_matches)} scenes found")
            for m in movie_matches[:3]:
                console.print(f"  [{m['timestamp']}] {m['text'][:60]}...")

    console.print(f"\n[bold]Scanned {movies_scanned} movies, found scenes in {len(results)}[/bold]")

    # Build output structure
    discovery_results = {
        "emotion": emotion,
        "query": query,
        "keywords": keywords,
        "movies_scanned": movies_scanned,
        "movies_with_matches": len(results),
        "results": results,
        "instructions_for_horus": f"""
## Scene Discovery Results

Found {sum(r['total_matches'] for r in results)} potential {emotion or 'matching'} scenes across {len(results)} movies.

To extract a scene, use:
```
python movie_ingest.py agent quick \\
    --movie "MOVIE_PATH" \\
    --emotion {emotion or 'EMOTION'} \\
    --scene "DESCRIPTION" \\
    --timestamp "START-END"
```

Review the matches above and select scenes that best match the target emotional profile.
""",
    }

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w") as f:
            json.dump(discovery_results, f, indent=2)
        console.print(f"\n[green]Results saved to {output_json}[/green]")

    return discovery_results


@agent_app.command("inventory")
def show_inventory(
    emotion: Optional[str] = typer.Option(None, "--emotion", "-e", help="Filter by emotion"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Show inventory of processed clips.

    Tracks all clips extracted across sessions for progress monitoring.
    """
    inventory = _load_inventory()

    clips = inventory.get("clips", [])
    if emotion:
        clips = [c for c in clips if c.get("emotion") == emotion.lower()]

    if output_json:
        print(json.dumps({"clips": clips, "total": len(clips)}, indent=2))
        return

    # Count by emotion
    emotion_counts = {}
    for clip in inventory.get("clips", []):
        e = clip.get("emotion", "unknown")
        emotion_counts[e] = emotion_counts.get(e, 0) + 1

    console.print("[bold]Clip Inventory[/bold]")
    console.print(f"Total clips: {len(inventory.get('clips', []))}")
    console.print(f"Movies processed: {len(inventory.get('movies_processed', []))}")
    console.print(f"Last updated: {inventory.get('last_updated', 'Never')}\n")

    console.print("[bold]Clips by Emotion:[/bold]")
    for e in VALID_EMOTIONS:
        count = emotion_counts.get(e, 0)
        status = "✓" if count >= 5 else "○"
        console.print(f"  {status} {e}: {count}")

    if clips:
        console.print(f"\n[bold]Recent Clips{' (' + emotion + ')' if emotion else ''}:[/bold]")
        for clip in clips[-10:]:
            console.print(f"  [{clip.get('emotion', '?')}] {clip.get('movie', 'Unknown')} - {clip.get('scene', '')[:40]}")


@agent_app.command("request")
def request_extraction(
    to_project: str = typer.Option("movie-ingest", "--to", help="Target project for request"),
    emotion: str = typer.Option(..., "--emotion", "-e", help="Target emotion"),
    description: str = typer.Option(..., "--desc", "-d", help="What kind of scenes are needed"),
    count: int = typer.Option(5, "--count", "-n", help="Number of clips needed"),
):
    """
    Send a clip extraction request to another project via agent-inbox.

    Used by Horus to request specific emotional clips from movie-ingest.

    Example:
        python movie_ingest.py agent request --to movie-ingest --emotion rage --desc "Betrayal fury scenes" --count 5
    """
    emotion = emotion.lower()
    if emotion not in VALID_EMOTIONS:
        raise typer.BadParameter(f"Unknown emotion '{emotion}'. Allowed: {sorted(VALID_EMOTIONS)}")

    archetype = HORUS_ARCHETYPE_MAP.get(emotion, {})

    request_data = {
        "type": "clip_request",
        "emotion": emotion,
        "description": description,
        "count_needed": count,
        "archetype": archetype.get("primary_archetype"),
        "actor_model": archetype.get("actor_model"),
        "voice_tone": archetype.get("voice_tone"),
        "bdi_patterns": {
            "belief": archetype.get("belief_pattern"),
            "desire": archetype.get("desire_pattern"),
            "intention": archetype.get("intention_pattern"),
        },
    }

    message = f"""Clip Extraction Request

Emotion: {emotion}
Description: {description}
Count needed: {count}

Actor Model: {archetype.get('actor_model', 'Unknown')}
Voice Tone: {archetype.get('voice_tone', 'Unknown')}

Please use `python movie_ingest.py agent recommend {emotion}` to find suitable movies,
then `python movie_ingest.py agent quick` to extract clips."""

    success = _send_to_inbox(
        to_project=to_project,
        message=message,
        message_type="request",
        metadata=request_data,
    )

    if success:
        console.print(f"[green]✓ Request sent to {to_project}[/green]")
    else:
        console.print(f"[red]✗ Failed to send request[/red]")


if __name__ == "__main__":
    app()
