"""
ACE-Step Music Score CLI.

Commands:
- up: Start Docker service
- down: Stop Docker service
- generate: Generate scene music with HMT integration
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

from .bridge_prompts import (
    augment_prompt_for_bridges,
    extract_bridges_from_prompt,
    get_bridges_for_episode,
)
from .docker_manager import (
    docker_compose_down,
    ensure_service_running,
    get_service_logs,
    make_default_config,
)
from .http_client import check_health, download_output, poll_job, submit_generate
from .schemas import GenerateRequest, HMTTaxonomy, ScoreResult
from .task_monitor import ScoreMonitor, end_generation, start_generation

app = typer.Typer(
    name="create-score",
    help="Scene music generation via ACE-Step Docker with HMT integration.",
    add_completion=False,
)


def _skill_root() -> Path:
    """Get the skill root directory."""
    return Path(__file__).resolve().parents[1]


def _setup_logging(verbose: bool = False) -> None:
    """Configure loguru logging."""
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, level=level, format="<level>{level: <8}</level> | {message}")


@app.command()
def up(
    build: bool = typer.Option(False, "--build", "-b", help="Force rebuild Docker image"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
) -> None:
    """Start the ACE-Step Docker service (idempotent)."""
    _setup_logging(verbose)
    cfg = make_default_config(_skill_root())

    logger.info("Starting ACE-Step service...")
    try:
        ensure_service_running(cfg, build=build)
        logger.info("Service is running at {}", cfg.base_url)
    except Exception as e:
        logger.error("Failed to start service: {}", e)
        logger.info("Recent logs:\n{}", get_service_logs(cfg))
        raise typer.Exit(1)


@app.command()
def down(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
) -> None:
    """Stop the ACE-Step Docker service."""
    _setup_logging(verbose)
    cfg = make_default_config(_skill_root())

    logger.info("Stopping ACE-Step service...")
    docker_compose_down(cfg)
    logger.info("Service stopped")


@app.command()
def generate(
    prompt: str = typer.Option(..., "--prompt", "-p", help="Text prompt for music generation"),
    out: Path = typer.Option(..., "--out", "-o", help="Output file path"),
    # Generation parameters
    duration_s: float = typer.Option(30.0, "--duration-s", "-d", help="Duration in seconds"),
    steps: int = typer.Option(27, "--steps", help="Inference steps"),
    seed: int = typer.Option(-1, "--seed", "-s", help="Seed (-1 for random)"),
    cfg_scale: float = typer.Option(4.0, "--cfg-scale", help="Guidance scale"),
    format: str = typer.Option("wav", "--format", "-f", help="Output format: wav, mp3, flac"),
    # HMT integration
    bridges: Optional[str] = typer.Option(
        None, "--bridges", help="Comma-separated bridge attributes (e.g., Resilience,Precision)"
    ),
    episode: Optional[str] = typer.Option(None, "--episode", "-e", help="Episode association"),
    store_memory: bool = typer.Option(True, "--store-memory/--no-store-memory", help="Store in /memory"),
    # Conditioning
    reference_audio: Optional[Path] = typer.Option(
        None, "--reference-audio", "-r", exists=True, help="Reference audio for theme continuity"
    ),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated genre/style tags"),
    instrumental: bool = typer.Option(True, "--instrumental/--no-instrumental", help="Instrumental only"),
    # Other
    poll_timeout_s: int = typer.Option(900, "--poll-timeout", help="Max seconds to wait"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON"),
) -> None:
    """
    Generate scene music with HMT taxonomy integration.

    Ensures Docker service is running, generates music, and optionally stores in /memory.
    """
    _setup_logging(verbose)
    cfg = make_default_config(_skill_root())

    # Parse bridges
    bridge_list: list[str] = []
    if bridges:
        bridge_list = [b.strip() for b in bridges.split(",") if b.strip()]

    # If episode provided but no bridges, infer from episode
    if episode and not bridge_list:
        bridge_list = get_bridges_for_episode(episode)
        if bridge_list:
            logger.info("Inferred bridges from episode {}: {}", episode, bridge_list)

    # If still no bridges, try to extract from prompt
    if not bridge_list:
        bridge_list = extract_bridges_from_prompt(prompt)
        if bridge_list:
            logger.info("Extracted bridges from prompt: {}", bridge_list)

    # Augment prompt with bridge keywords
    original_prompt = prompt
    if bridge_list:
        prompt = augment_prompt_for_bridges(prompt, bridge_list)
        logger.info("Augmented prompt: {}", prompt)

    # Ensure service is running
    logger.info("Ensuring ACE-Step service is running...")
    try:
        ensure_service_running(cfg)
    except Exception as e:
        logger.error("Service not available: {}", e)
        raise typer.Exit(1)

    # Build request
    req = GenerateRequest(
        prompt=prompt,
        tags=tags,
        instrumental=instrumental,
        duration_s=duration_s,
        steps=steps,
        seed=seed,
        cfg_scale=cfg_scale,
        format=format,
    )

    # Start task-monitor tracking
    monitor = start_generation(prompt=original_prompt, duration_s=duration_s)

    # Submit generation
    logger.info(
        "Generating: duration={}s, steps={}, seed={}, bridges={}",
        duration_s, steps, seed, bridge_list
    )
    try:
        job_id = submit_generate(cfg.base_url, req, reference_audio)
        monitor.start_job(job_id=job_id, seed=seed)
        monitor.update_progress(state="generating", progress_pct=10)
    except Exception as e:
        logger.error("Failed to submit generation: {}", e)
        monitor.fail_job(error_msg=str(e))
        end_generation(success=False)
        raise typer.Exit(1)

    # Poll for completion
    try:
        monitor.update_progress(state="generating", progress_pct=30)
        status = poll_job(cfg.base_url, job_id, timeout_s=poll_timeout_s)
        monitor.update_progress(state="downloading", progress_pct=80)
    except TimeoutError as e:
        logger.error("Generation timed out: {}", e)
        monitor.fail_job(error_msg=f"Timeout: {e}")
        end_generation(success=False)
        raise typer.Exit(1)

    if status.state == "error":
        logger.error("Generation failed: {}", status.detail)
        monitor.fail_job(error_msg=status.detail or "Unknown error")
        end_generation(success=False)
        raise typer.Exit(1)

    if not status.output_url:
        logger.error("Generation completed but no output URL")
        monitor.fail_job(error_msg="No output URL")
        end_generation(success=False)
        raise typer.Exit(1)

    # Download output
    try:
        download_output(cfg.base_url, status.output_url, out)
        monitor.complete_job(output_path=out)
    except Exception as e:
        logger.error("Failed to download output: {}", e)
        monitor.fail_job(error_msg=f"Download failed: {e}")
        end_generation(success=False)
        raise typer.Exit(1)

    # Extract HMT taxonomy
    hmt = _extract_hmt_taxonomy(prompt, bridge_list, episode)

    # Build result
    result = ScoreResult(
        output_path=out,
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

    # Output result
    if json_output:
        print(json.dumps(result.model_dump(mode="json"), indent=2, default=str))
    else:
        logger.info("Generated: {}", out)
        logger.info("Bridges: {}", hmt.bridge_attributes)
        if episode:
            logger.info("Episode: {}", episode)


def _extract_hmt_taxonomy(
    prompt: str,
    bridges: list[str],
    episode: Optional[str],
) -> HMTTaxonomy:
    """Extract HMT taxonomy using common/taxonomy.py if available."""
    # Try to import common taxonomy
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
        logger.warning("common/taxonomy.py not available, using basic HMT")
        return HMTTaxonomy(
            bridge_attributes=bridges[:3],
            collection_tags={"function": ["Score"], "domain": ["Generated"]},
            tactical_tags=["Score"],
            episodic_associations=[episode] if episode else [],
            confidence=0.5,
        )


def _store_in_memory(result: ScoreResult) -> None:
    """Store generation result in /memory."""
    try:
        # Try to use memory skill
        memory_path = Path(__file__).parent.parent.parent / "memory"
        if not memory_path.exists():
            logger.warning("Memory skill not found at {}", memory_path)
            return

        # Build tags
        tags = ["ace-step", "generated", "music-score"]
        tags.extend(result.hmt.bridge_attributes)
        if result.episode_association:
            tags.append(f"episode:{result.episode_association}")

        # For now, just log what we would store
        # Full integration would call memory's learn function
        logger.info(
            "Would store in memory: scope=horus-filmmaking, bridges={}, tags={}",
            result.hmt.bridge_attributes,
            tags,
        )

        # Future work: Implement actual memory storage via subprocess or import
        # subprocess.run([
        #     str(memory_path / "run.sh"), "learn",
        #     "--scope", "horus-filmmaking",
        #     "--problem", f"Scene score: {result.original_prompt[:100]}",
        #     "--solution", f"Generated {result.output_path}, seed={result.seed}",
        #     "--category", "music_score",
        #     "--tags", ",".join(tags),
        # ], check=False,
        # env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        # )

    except Exception as e:
        logger.warning("Failed to store in memory: {}", e)


@app.command()
def status(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
) -> None:
    """Check service status."""
    _setup_logging(verbose)
    cfg = make_default_config(_skill_root())

    if check_health(cfg.base_url):
        logger.info("Service healthy at {}", cfg.base_url)
    else:
        logger.warning("Service not responding at {}", cfg.base_url)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
