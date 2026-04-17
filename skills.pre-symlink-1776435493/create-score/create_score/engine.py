"""Business logic for create-score: scene music generation via ACE-Step Docker."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from loguru import logger

from .bridge_prompts import (
    augment_prompt_for_bridges,
    extract_bridges_from_prompt,
    get_all_bridges,
    get_bridges_for_episode,
)
from .docker_manager import (
    docker_compose_down,
    ensure_service_running,
    is_service_running,
    make_default_config,
)
from .http_client import check_health, download_output, poll_job, submit_generate
from .schemas import GenerateRequest, HMTTaxonomy, ScoreResult
from .task_monitor import ScoreMonitor, end_generation, start_generation


def _skill_root() -> Path:
    """Get the skill root directory."""
    return Path(__file__).resolve().parents[1]


def _extract_hmt_taxonomy(
    prompt: str,
    bridges: list[str],
    episode: Optional[str],
) -> HMTTaxonomy:
    """Extract HMT taxonomy using common/taxonomy.py if available."""
    try:
        common_path = Path(__file__).parent.parent.parent / "common"
        if str(common_path) not in sys.path:
            sys.path.insert(0, str(common_path))

        from taxonomy import ContentType, extract_taxonomy_features

        features = extract_taxonomy_features(
            content_type=ContentType.MUSIC,
            title=f"Score: {prompt[:50]}",
            description=prompt,
            tags=["generated", "ace-step", "scene-score"],
        )

        # Merge with explicit bridges
        all_bridges = list(set(bridges + features.get("bridge_attributes", [])))

        return HMTTaxonomy(
            bridge_attributes=all_bridges[:3],
            collection_tags=features.get("collection_tags", {}),
            tactical_tags=features.get("tactical_tags", ["Score"]),
            episodic_associations=features.get("episodic_associations", []),
            confidence=features.get("confidence", 0.5),
        )

    except ImportError:
        logger.debug("common/taxonomy.py not available, using basic HMT")
        return HMTTaxonomy(
            bridge_attributes=bridges[:3],
            collection_tags={"function": ["Score"], "domain": ["Generated"]},
            tactical_tags=["Score"],
            episodic_associations=[episode] if episode else [],
            confidence=0.5,
        )


def _store_in_memory(result: ScoreResult) -> None:
    """Store generation result in /memory (placeholder)."""
    try:
        tags = ["ace-step", "generated", "music-score"]
        tags.extend(result.hmt.bridge_attributes)
        if result.episode_association:
            tags.append(f"episode:{result.episode_association}")

        logger.debug(
            "Memory storage: scope=horus-filmmaking, bridges={}, tags={}",
            result.hmt.bridge_attributes,
            tags,
        )
        # TODO: Implement actual memory storage — currently a no-op
        raise NotImplementedError("Memory storage for score results not yet implemented")
    except Exception as e:
        logger.warning("Failed to store in memory: {}", e)


def generate_scene_score(
    prompt: str,
    duration_s: float,
    output_path: Path,
    bridges: Optional[List[str]] = None,
    episode: Optional[str] = None,
    reference_audio: Optional[Path] = None,
    seed: int = -1,
    steps: int = 27,
    cfg_scale: float = 4.0,
    format: str = "wav",
    store_memory: bool = True,
    poll_timeout_s: int = 900,
) -> ScoreResult:
    """
    Generate music for a scene with HMT taxonomy.

    This is the primary API for integration with /create-movie.

    Args:
        prompt: Text prompt describing desired music
        duration_s: Duration in seconds (1-300)
        output_path: Path to save generated audio
        bridges: Explicit bridge attributes (e.g., ["Resilience", "Precision"])
        episode: Episode association for memory storage (e.g., "Siege_of_Terra")
        reference_audio: Reference audio for style/theme continuity
        seed: Seed for reproducibility (-1 = random)
        steps: Inference steps (higher = better quality, slower)
        cfg_scale: Guidance scale (higher = more prompt adherence)
        format: Output format: wav, mp3, flac
        store_memory: Whether to store in /memory
        poll_timeout_s: Max seconds to wait for generation

    Returns:
        ScoreResult with output_path, prompt, seed, duration_s, hmt taxonomy, etc.

    Raises:
        RuntimeError: If service is unavailable or generation fails
        TimeoutError: If generation times out

    Example:
        >>> from create_score import generate_scene_score
        >>> result = generate_scene_score(
        ...     prompt="battle preparation, epic strings",
        ...     duration_s=30,
        ...     output_path=Path("battle.wav"),
        ...     bridges=["Resilience"],
        ...     episode="Siege_of_Terra",
        ... )
        >>> print(result.hmt.bridge_attributes)
        ['Resilience']
    """
    cfg = make_default_config(_skill_root())

    # Resolve bridges
    bridge_list = list(bridges) if bridges else []

    # If episode provided but no bridges, infer from episode
    if episode and not bridge_list:
        bridge_list = get_bridges_for_episode(episode)
        if bridge_list:
            logger.debug("Inferred bridges from episode {}: {}", episode, bridge_list)

    # If still no bridges, try to extract from prompt
    if not bridge_list:
        bridge_list = extract_bridges_from_prompt(prompt)
        if bridge_list:
            logger.debug("Extracted bridges from prompt: {}", bridge_list)

    # Augment prompt with bridge keywords
    original_prompt = prompt
    if bridge_list:
        prompt = augment_prompt_for_bridges(prompt, bridge_list)
        logger.debug("Augmented prompt: {}", prompt)

    # Ensure service is running
    ensure_service_running(cfg)

    # Start task-monitor tracking
    monitor = start_generation(prompt=original_prompt, duration_s=duration_s)

    # Build request
    req = GenerateRequest(
        prompt=prompt,
        instrumental=True,
        duration_s=duration_s,
        steps=steps,
        seed=seed,
        cfg_scale=cfg_scale,
        format=format,
    )

    # Submit generation
    logger.info(
        "Generating scene score: duration={}s, bridges={}",
        duration_s, bridge_list
    )
    try:
        job_id = submit_generate(cfg.base_url, req, reference_audio)
        monitor.start_job(job_id=job_id, seed=seed)
        monitor.update_progress(state="generating", progress_pct=10)
    except Exception as e:
        monitor.fail_job(error_msg=str(e))
        end_generation(success=False)
        raise

    # Poll for completion
    try:
        monitor.update_progress(state="generating", progress_pct=30)
        status = poll_job(cfg.base_url, job_id, timeout_s=poll_timeout_s)
        monitor.update_progress(state="downloading", progress_pct=80)
    except TimeoutError as e:
        monitor.fail_job(error_msg=f"Timeout: {e}")
        end_generation(success=False)
        raise

    if status.state == "error":
        monitor.fail_job(error_msg=status.detail or "Unknown error")
        end_generation(success=False)
        raise RuntimeError(f"Generation failed: {status.detail}")

    if not status.output_url:
        monitor.fail_job(error_msg="No output URL")
        end_generation(success=False)
        raise RuntimeError("Generation completed but no output URL")

    # Download output
    try:
        download_output(cfg.base_url, status.output_url, output_path)
        monitor.complete_job(output_path=output_path)
    except Exception as e:
        monitor.fail_job(error_msg=f"Download failed: {e}")
        end_generation(success=False)
        raise

    # Extract HMT taxonomy
    hmt = _extract_hmt_taxonomy(prompt, bridge_list, episode)

    # Build result
    result = ScoreResult(
        output_path=output_path,
        prompt=prompt,
        original_prompt=original_prompt,
        seed=seed,
        duration_s=duration_s,
        format=format,
        hmt=hmt,
        episode_association=episode,
        reference_audio=reference_audio,
    )

    # Store in memory if requested
    if store_memory:
        _store_in_memory(result)

    # Finish task-monitor tracking
    end_generation(success=True)

    return result


def start_service(build: bool = False) -> None:
    """Start the ACE-Step Docker service."""
    cfg = make_default_config(_skill_root())
    ensure_service_running(cfg, build=build)


def stop_service() -> None:
    """Stop the ACE-Step Docker service."""
    cfg = make_default_config(_skill_root())
    docker_compose_down(cfg)


def is_service_available() -> bool:
    """Check if the ACE-Step service is running and healthy."""
    cfg = make_default_config(_skill_root())
    return check_health(cfg.base_url)
