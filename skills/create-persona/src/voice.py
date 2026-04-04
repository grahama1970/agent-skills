#!/usr/bin/env python3
"""
Voice/TTS integration for create-persona.

Enables training Qwen3-TTS voice models from YouTube audio of personas.
Integrates with:
- ingest-youtube: Download audio from YouTube videos
- tts-train: Build datasets and train Qwen3-TTS models

Workflow:
1. Collect YouTube URLs from /ask learn or manual input
2. Download audio using ingest-youtube/downloader
3. Build TTS dataset (transcripts + audio segments)
4. Train Qwen3-TTS model
5. Store model path in persona
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger as log

# Paths
SKILLS_DIR = Path(__file__).parent.parent.parent
TTS_TRAIN_DIR = SKILLS_DIR / "tts-train"
INGEST_YOUTUBE_DIR = SKILLS_DIR / "ingest-youtube"
_EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))
VOICE_DATASETS_DIR = _EMBRY_STORAGE / "media" / "personas" / "voice-datasets"
VOICE_MODELS_DIR = _EMBRY_STORAGE / "media" / "personas" / "voice-models"

# Fallback paths for smaller systems
if not VOICE_DATASETS_DIR.parent.exists():
    VOICE_DATASETS_DIR = Path.home() / "datasets" / "persona-voices"
    VOICE_MODELS_DIR = Path.home() / "models" / "persona-voices"


@dataclass
class VoiceTrainingConfig:
    """Configuration for voice training."""
    persona_name: str
    slug: str  # Filesystem-safe name
    youtube_urls: list[str] = field(default_factory=list)
    min_audio_minutes: int = 15  # Minimum audio for training
    max_audio_minutes: int = 60  # Maximum audio to collect
    epochs: int = 5
    batch_size: int = 8
    learning_rate: float = 1e-4
    model_size: str = "0.6B"  # "0.6B" or "1.7B"
    use_lora: bool = True
    dataset_dir: Optional[Path] = None
    output_dir: Optional[Path] = None

    def __post_init__(self):
        if not self.dataset_dir:
            self.dataset_dir = VOICE_DATASETS_DIR / self.slug
        if not self.output_dir:
            self.output_dir = VOICE_MODELS_DIR / self.slug


@dataclass
class VoiceTrainingStatus:
    """Status of a voice training job."""
    persona_name: str
    status: str  # "pending", "collecting", "training", "ready", "failed"
    progress_pct: float = 0.0
    audio_collected_minutes: float = 0.0
    current_epoch: int = 0
    total_epochs: int = 0
    model_path: str = ""
    error_message: str = ""
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _run_skill(name: str, args: list[str], timeout: int = 300, cwd: Optional[Path] = None) -> dict:
    """Run a skill via its run.sh and capture output."""
    script = SKILLS_DIR / name / "run.sh"
    if not script.exists():
        script = SKILLS_DIR.parent / ".agent" / "skills" / name / "run.sh"

    if not script.exists():
        log.warning("Skill '%s' not found", name)
        return {"returncode": -1, "stdout": "", "stderr": f"Skill {name} not found"}

    env = os.environ.copy()
    # Unset VIRTUAL_ENV to prevent uv/venv conflicts in child processes
    env.pop("VIRTUAL_ENV", None)

    try:
        result = subprocess.run(
            [str(script)] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd or script.parent),
            env=env,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -2, "stdout": "", "stderr": f"Timeout after {timeout}s"}
    except Exception as e:
        return {"returncode": -3, "stdout": "", "stderr": str(e)}


def _slugify(name: str) -> str:
    """Convert persona name to filesystem-safe slug."""
    return name.lower().replace(" ", "-").replace("'", "").replace(".", "")


def collect_audio(
    config: VoiceTrainingConfig,
    progress_callback: Optional[callable] = None,
) -> tuple[list[Path], list[str]]:
    """Download audio from YouTube URLs.

    Args:
        config: Training configuration with URLs
        progress_callback: Optional callback(pct, message)

    Returns:
        Tuple of (audio_files, errors)
    """
    audio_files = []
    errors = []

    config.dataset_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = config.dataset_dir / "audio_raw"
    audio_dir.mkdir(exist_ok=True)

    total_urls = len(config.youtube_urls)
    for i, url in enumerate(config.youtube_urls):
        if progress_callback:
            progress_callback((i / total_urls) * 50, f"Downloading {i+1}/{total_urls}")

        # Extract video ID from URL
        video_id = None
        if "v=" in url:
            video_id = url.split("v=")[1].split("&")[0]
        elif "youtu.be/" in url:
            video_id = url.split("youtu.be/")[1].split("?")[0]

        if not video_id:
            errors.append(f"Could not extract video ID from: {url}")
            continue

        # Check if already downloaded
        existing = list(audio_dir.glob(f"{video_id}.*"))
        if existing:
            audio_files.extend(existing)
            log.info("Audio already exists: %s", existing[0])
            continue

        # Download using ingest-youtube's downloader
        try:
            # Import the downloader directly
            sys.path.insert(0, str(INGEST_YOUTUBE_DIR))
            from youtube_transcripts.downloader import download_audio

            audio_path, error = download_audio(video_id, audio_dir)
            if audio_path:
                audio_files.append(audio_path)
                log.info("Downloaded audio: %s", audio_path)
            else:
                errors.append(f"{video_id}: {error}")
                log.warning("Failed to download %s: %s", video_id, error)

        except ImportError as e:
            errors.append(f"Import error: {e}")
            log.error("Could not import downloader: %s", e)
        finally:
            if str(INGEST_YOUTUBE_DIR) in sys.path:
                sys.path.remove(str(INGEST_YOUTUBE_DIR))

    return audio_files, errors


def build_tts_dataset(
    config: VoiceTrainingConfig,
    audio_files: list[Path],
    progress_callback: Optional[callable] = None,
) -> tuple[Optional[Path], list[str]]:
    """Build a TTS dataset from audio files.

    Uses tts-train's ingest workflow to:
    1. Transcribe audio with WhisperX
    2. Segment into training clips
    3. Create Qwen3-TTS manifest

    Args:
        config: Training configuration
        audio_files: List of audio file paths
        progress_callback: Optional callback(pct, message)

    Returns:
        Tuple of (manifest_path, errors)
    """
    errors = []

    if not audio_files:
        return None, ["No audio files to process"]

    manifest_dir = config.dataset_dir
    manifest_dir.mkdir(parents=True, exist_ok=True)

    # Use tts-train prep command (handles VAD, ASR, tokenization)
    audio_dir = config.dataset_dir / "audio_raw"
    manifest_dir = config.dataset_dir

    if progress_callback:
        progress_callback(50, "Building TTS dataset (transcribe + tokenize)...")

    # Call tts-train prep
    # Note: This runs docker for WhisperX and then local python for Qwen3 tokenization
    result = _run_skill("tts-train", [
        "prep",
        "--audio-dir", str(audio_dir),
        "--out-dir", str(manifest_dir),
        "--transcribe", # Required for raw audio
        "--min-sec", "2.0",
        "--max-sec", "12.0",
        "--base-model", "Qwen/Qwen3-TTS-Tokenizer-12Hz", # Default tokenizer
    ], timeout=7200) # 2 hour timeout for processing

    if result["returncode"] != 0:
        errors.append(f"Prep failed: {result['stderr'][-500:]}")
        log.error("Prep failed: %s", result["stderr"])
        return None, errors

    # Check for manifest
    manifest_path = manifest_dir / "manifest.jsonl"
    if not manifest_path.exists():
        return None, errors + ["No manifest generated from prep"]
    
    if manifest_path.stat().st_size == 0:
        return None, errors + ["Manifest is empty (transcription failed or no valid segments)"]
    
    return manifest_path, errors


def extract_voice_taxonomy(
    config: VoiceTrainingConfig,
    manifest_path: Path,
) -> tuple[dict, list[str]]:
    """Extract Federated Taxonomy alignment from voice transcripts.
    
    Aligns the voice model with Bridge Attributes (Precision, Resilience, etc.)
    based on the content of the training data.
    """
    errors = []
    tags = {}
    
    if not manifest_path.exists():
        return {}, ["Manifest not found for taxonomy extraction"]

    # Sample transcripts (first 50 lines to avoid token limits)
    text_sample = []
    try:
        with open(manifest_path) as f:
            for i, line in enumerate(f):
                if i > 50: break
                if line.strip():
                    item = json.loads(line)
                    if "text" in item:
                        text_sample.append(item["text"])
    except Exception as e:
        return {}, [f"Failed to read manifest for taxonomy: {e}"]

    if not text_sample:
        return {}, ["No text found in manifest"]

    full_text = " ".join(text_sample)
    
    # Run taxonomy extraction
    # We use the 'behavioral' collection as it maps well to voice/personality
    result = _run_skill("taxonomy", [
        "extract",
        "--text", full_text[:4000],  # Limit length for CLI
        "--collection", "behavioral",
        "--bridges-only"
    ], timeout=120)

    if result["returncode"] != 0:
        errors.append(f"Taxonomy extraction failed: {result['stderr'][:100]}")
    else:
        try:
            # Parse output which should be JSON
            # The tool output might have some logs before JSON, so we look for first {
            import re
            json_match = re.search(r'\{.*\}', result["stdout"], re.DOTALL)
            if json_match:
                extracted = json.loads(json_match.group(0))
                tags = extracted
                log.info("Extracted taxonomy for %s: %s", config.persona_name, tags.get("bridge_tags", []))
            else:
                errors.append("Could not parse taxonomy JSON output")
        except json.JSONDecodeError as e:
            errors.append(f"Failed to parse taxonomy output: {e}")

    return tags, errors


def train_voice_model(
    config: VoiceTrainingConfig,
    manifest_path: Path,
    progress_callback: Optional[callable] = None,
) -> tuple[Optional[Path], list[str]]:
    """Train a Qwen3-TTS voice model.

    Args:
        config: Training configuration
        manifest_path: Path to training manifest
        progress_callback: Optional callback(pct, message)

    Returns:
        Tuple of (model_path, errors)
    """
    errors = []

    config.output_dir.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(90, f"Training {config.model_size} model")

    # Build training command
    base_model = f"Qwen/Qwen3-TTS-12Hz-{config.model_size}-Base"
    args = [
        "train-qwen3",
        "--base-model", base_model,
        "--data-manifest", str(manifest_path),
        "--out-dir", str(config.output_dir),
        "--epochs", str(config.epochs),
        "--batch-size", str(config.batch_size),
        "--lr", str(config.learning_rate),
    ]

    if config.use_lora:
        args.extend(["--use-lora", "--lora-r", "16", "--lora-alpha", "32"])

    if config.model_size == "1.7B":
        args.extend([
            "--use-8bit-adam",
            "--gradient-checkpointing",
            "--gradient-accumulation-steps", "8",
        ])

    # Run training (long timeout for multi-epoch training)
    result = _run_skill("tts-train", args, timeout=7200)  # 2 hours

    if result["returncode"] != 0:
        errors.append(f"Training failed: {result['stderr'][:200]}")
        return None, errors

    # Find the best checkpoint
    checkpoints = list(config.output_dir.glob("checkpoint-epoch-*"))
    if not checkpoints:
        errors.append("No checkpoints found after training")
        return None, errors

    # Return the last checkpoint
    best_checkpoint = sorted(checkpoints)[-1]
    log.info("Training complete: %s", best_checkpoint)

    if progress_callback:
        progress_callback(100, "Training complete")

    return best_checkpoint, errors


def synthesize_speech(
    model_path: Path,
    text: str,
    output_path: Path,
    speaker: Optional[str] = None,
) -> tuple[bool, str]:
    """Generate speech using a trained model.

    Args:
        model_path: Path to trained Qwen3-TTS model
        text: Text to synthesize
        output_path: Output WAV file path
        speaker: Optional speaker name (defaults to model name)

    Returns:
        Tuple of (success, error_message)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = _run_skill("tts-train", [
        "synthesize",
        "--text", text,
        "--output", str(output_path),
        "--model", str(model_path),
    ], timeout=60)

    if result["returncode"] != 0:
        return False, result["stderr"][:200]

    if not output_path.exists():
        return False, "Output file not created"

    return True, ""


def get_voice_status(persona_name: str, scope: str = "personas") -> VoiceTrainingStatus:
    """Get the voice training status for a persona.

    Args:
        persona_name: Name of the persona
        scope: Memory scope

    Returns:
        VoiceTrainingStatus object
    """
    slug = _slugify(persona_name)
    status = VoiceTrainingStatus(persona_name=persona_name, status="unknown")

    dataset_dir = VOICE_DATASETS_DIR / slug
    model_dir = VOICE_MODELS_DIR / slug

    # Check for state file
    state_file = dataset_dir / "training_state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            status.status = state.get("status", "unknown")
            status.progress_pct = state.get("progress_pct", 0)
            status.audio_collected_minutes = state.get("audio_minutes", 0)
            status.current_epoch = state.get("current_epoch", 0)
            status.total_epochs = state.get("total_epochs", 0)
            status.error_message = state.get("error", "")
            status.started_at = state.get("started_at", "")
            status.completed_at = state.get("completed_at", "")
        except (json.JSONDecodeError, OSError):
            pass

    # Check for trained model
    if model_dir.exists():
        checkpoints = list(model_dir.glob("checkpoint-epoch-*"))
        if checkpoints:
            status.model_path = str(sorted(checkpoints)[-1])
            if status.status != "failed":
                status.status = "ready"

    # Check for pending/in-progress
    if not dataset_dir.exists():
        status.status = "pending"
    elif not (dataset_dir / "audio_raw").exists():
        status.status = "pending"
    elif status.status == "unknown":
        # Has dataset but no model
        status.status = "ready_to_train"

    return status


def train_persona_voice(
    persona_name: str,
    youtube_urls: list[str],
    scope: str = "personas",
    model_size: str = "0.6B",
    epochs: int = 5,
    progress_callback: Optional[callable] = None,
) -> VoiceTrainingStatus:
    """Full pipeline to train a voice model for a persona.

    Args:
        persona_name: Name of the persona
        youtube_urls: YouTube URLs with persona's voice
        scope: Memory scope
        model_size: "0.6B" or "1.7B"
        epochs: Training epochs
        progress_callback: Optional callback(pct, message)

    Returns:
        VoiceTrainingStatus with results
    """
    slug = _slugify(persona_name)
    config = VoiceTrainingConfig(
        persona_name=persona_name,
        slug=slug,
        youtube_urls=youtube_urls,
        model_size=model_size,
        epochs=epochs,
    )

    status = VoiceTrainingStatus(
        persona_name=persona_name,
        status="collecting",
        started_at=datetime.now().isoformat(),
    )

    # Save initial state
    config.dataset_dir.mkdir(parents=True, exist_ok=True)
    state_file = config.dataset_dir / "training_state.json"

    def save_state():
        state_file.write_text(json.dumps(status.to_dict(), indent=2))

    save_state()

    # Step 1: Collect audio
    if progress_callback:
        progress_callback(0, "Collecting audio from YouTube")

    audio_files, errors = collect_audio(config, progress_callback)
    if errors:
        log.warning("Audio collection errors: %s", errors[:3])

    if not audio_files:
        status.status = "failed"
        status.error_message = "No audio files collected: " + "; ".join(errors[:3])
        save_state()
        return status

    # Calculate audio duration
    total_seconds = sum(
        float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(f)],
            capture_output=True, text=True
        ).stdout.strip() or 0)
        for f in audio_files
        if f.exists()
    )
    status.audio_collected_minutes = total_seconds / 60

    # Step 2: Build dataset
    status.status = "building_dataset"
    save_state()

    manifest_path, build_errors = build_tts_dataset(config, audio_files, progress_callback)
    if build_errors:
        log.warning("Dataset build errors: %s", build_errors[:3])

    if not manifest_path:
        status.status = "failed"
        status.error_message = "Dataset build failed: " + "; ".join(build_errors[:3])
        save_state()
        return status

    # Step 2.5: Extract Taxonomy Alignment
    if progress_callback:
        progress_callback(88, "Aligning with Federated Taxonomy")
        
    taxonomy_tags, tax_errors = extract_voice_taxonomy(config, manifest_path)
    if tax_errors:
        log.warning("Taxonomy extraction errors: %s", tax_errors)
    
    # Save taxonomy metadata
    metadata = {
        "persona": persona_name,
        "taxonomy": taxonomy_tags,
        "aligned_at": datetime.now().isoformat()
    }
    config.output_dir.mkdir(parents=True, exist_ok=True)
    (config.output_dir / "voice_metadata.json").write_text(json.dumps(metadata, indent=2))
    log.info("Saved taxonomy metadata for %s", persona_name)

    # Step 3: Train model
    status.status = "training"
    status.total_epochs = epochs
    save_state()

    model_path, train_errors = train_voice_model(config, manifest_path, progress_callback)
    if train_errors:
        log.warning("Training errors: %s", train_errors[:3])

    if not model_path:
        status.status = "failed"
        status.error_message = "Training failed: " + "; ".join(train_errors[:3])
        save_state()
        return status

    # Success!
    status.status = "ready"
    status.model_path = str(model_path)
    status.completed_at = datetime.now().isoformat()
    status.progress_pct = 100
    save_state()

    log.info("Voice training complete for %s: %s", persona_name, model_path)
    return status


def discover_voice_sources(persona_name: str, scope: str = "personas") -> list[str]:
    """Discover YouTube URLs from existing persona learning sources.

    Looks for interview/lecture/speech content that would be good for TTS.

    Args:
        persona_name: Name of the persona
        scope: Memory scope

    Returns:
        List of YouTube URLs suitable for voice training
    """
    from .persona import recall_from_memory

    # Search for YouTube sources in memory
    items = recall_from_memory(
        f"{persona_name} interview OR lecture OR speech OR talk",
        scope,
        k=20,
    )

    urls = []
    for item in items:
        solution = item.get("solution", "")
        # Extract YouTube URLs from the content
        import re
        youtube_pattern = r'https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]+'
        found = re.findall(youtube_pattern, solution)
        urls.extend(found)

    # Deduplicate
    return list(dict.fromkeys(urls))
