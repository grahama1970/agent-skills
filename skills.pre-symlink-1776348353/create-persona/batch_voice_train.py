#!/usr/bin/env python3
"""
Batch voice training for all personas.

For each persona:
1. Use create-persona/src/voice.py::discover_voice_sources() to find YouTube URLs
2. Download actual audio via train_persona_voice() (calls /ingest-youtube)
3. Train PersonaPlex + Qwen3-TTS models
4. Update /memory with voice_status
"""

import sys
from pathlib import Path
import time
from datetime import datetime

from loguru import logger as log

# Run from create-persona directory, imports work via src module
sys.path.insert(0, str(Path(__file__).parent))

from src.voice import train_persona_voice, discover_voice_sources, get_voice_status
from src.persona import recall_from_memory

def main():
    personas_file = Path(__file__).parent / "persona_names.txt"
    
    if not personas_file.exists():
        log.error(f"Personas file not found: {personas_file}")
        sys.exit(1)
    
    with open(personas_file) as f:
        personas = [line.strip() for line in f if line.strip()]
    
    log.info(f"Starting batch voice training for {len(personas)} personas")
    
    results = []
    for idx, persona_name in enumerate(personas, 1):
        log.info(f"\n{'='*60}")
        log.info(f"[{idx}/{len(personas)}] Processing: {persona_name}")
        log.info(f"{'='*60}")
        
        try:
            # Check if voice already trained
            status = get_voice_status(persona_name)
            if status.status == "ready":
                log.info(f"  ✓ Voice already trained for {persona_name}, skipping")
                results.append({"persona": persona_name, "status": "already_trained", "skipped": True})
                continue
            
            # Discover YouTube sources
            log.info(f"  Discovering YouTube sources for {persona_name}...")
            youtube_urls = discover_voice_sources(persona_name)
            
            if not youtube_urls:
                log.warning(f"  ✗ No YouTube sources found for {persona_name}")
                results.append({"persona": persona_name, "status": "no_sources", "error": "No YouTube URLs found"})
                continue
            
            log.info(f"  Found {len(youtube_urls)} YouTube sources")
            for i, url in enumerate(youtube_urls[:3], 1):
                log.info(f"    {i}. {url}")
            
            # Train voice model (downloads audio + trains)
            log.info(f"  Starting voice training...")
            training_status = train_persona_voice(
                persona_name=persona_name,
                youtube_urls=youtube_urls[:5],  # Use top 5 sources
                model_size="1.7B",  # Full quality model as requested
                epochs=5,  # Standard training epochs
            )
            
            if training_status.status == "ready":
                log.info(f"  ✓ Voice training complete for {persona_name}")
                log.info(f"    Model: {training_status.model_path}")
                log.info(f"    Audio: {training_status.audio_collected_minutes:.1f} minutes")
                results.append({
                    "persona": persona_name,
                    "status": "success",
                    "model_path": training_status.model_path,
                    "audio_minutes": training_status.audio_collected_minutes
                })
            else:
                log.error(f"  ✗ Voice training failed for {persona_name}: {training_status.error_message}")
                results.append({
                    "persona": persona_name,
                    "status": "failed",
                    "error": training_status.error_message
                })
        
        except Exception as e:
            log.error(f"  ✗ Exception processing {persona_name}: {e}", exc_info=True)
            results.append({"persona": persona_name, "status": "exception", "error": str(e)})
        
        # Rate limit protection
        time.sleep(5)
        
        # Checkpoint every 10 personas
        if idx % 10 == 0:
            log.info(f"\n{'='*60}")
            log.info(f"CHECKPOINT: Processed {idx}/{len(personas)} personas")
            successful = sum(1 for r in results if r["status"] == "success")
            failed = sum(1 for r in results if r["status"] in ["failed", "exception", "no_sources"])
            skipped = sum(1 for r in results if r.get("skipped", False))
            log.info(f"  Success: {successful}, Failed: {failed}, Skipped: {skipped}")
            log.info(f"{'='*60}\n")
    
    # Final summary
    log.info(f"\n{'='*80}")
    log.info(f"BATCH VOICE TRAINING COMPLETE")
    log.info(f"{'='*80}")
    log.info(f"Total personas: {len(personas)}")
    
    successful = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] in ["failed", "exception"])
    no_sources = sum(1 for r in results if r["status"] == "no_sources")
    skipped = sum(1 for r in results if r.get("skipped", False))
    
    log.info(f"  ✓ Successful: {successful}")
    log.info(f"  ✗ Failed: {failed}")
    log.info(f"  ⚠ No sources: {no_sources}")
    log.info(f"  ⊘ Already trained: {skipped}")
    
    total_audio_minutes = sum(r.get("audio_minutes", 0) for r in results)
    log.info(f"  Total audio collected: {total_audio_minutes:.1f} minutes")
    log.info(f"{'='*80}")

if __name__ == "__main__":
    main()
