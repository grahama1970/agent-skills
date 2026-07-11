# Persona-Dream Bakeoff Integration Notes

## Assessment

This directory contains the imported `persona_dream_full_bakeoff_agent_bundle`
as an experimental research lane for `persona-dream`.

The bundle fits the skill as a bounded bakeoff harness, not as the primary
runtime. It adds:

- story asset generation from a locked dream packet
- scene/script JSON and YAML exports
- contact-sheet prompt rendering with a dry-run path
- a hosted ElevenLabs plus Kling LipSync baseline
- a WavTTS plus Kling LipSync lane requiring consented voice references
- optional NAVA joint audio-video prompt generation and local run helpers
- machine receipts plus mandatory manual review gates

Important constraints from the bundle:

- no memory, ArangoDB, or Qdrant writes
- no uncited lore invention beyond `source_grounded_residue_ids`
- no unconsented voice cloning
- ElevenLabs and WavTTS lanes must use one shared base video
- NAVA is a separate joint audio-video comparator, not a TTS lane
- machine checks do not prove visual quality or persona fit

## Local Import Decisions

- Imported under `skills/persona-dream/research/bakeoff/`.
- Excluded generated Python bytecode and `__pycache__` directories.
- Trimmed generated sample outputs into small deterministic fixtures under
  `fixtures/story_assets_minimal/`.
- Ignored generated runs, rendered contact sheets, media, and audio/video
  artifacts.
- Promoted the bundle to `./run.sh research-bakeoff` mode, separate from
  `run.sh generate`.
- Kept the production skill as the owner of dream packets and video plans; this
  lane is opt-in research only.
- Added `config/research_bakeoff.json` to document backend and voice-lane enums.

## Clarifying Questions

1. Production promotion is still blocked on a reviewed receipt bundle from at
   least one real hosted A/V run plus manual visual inspection.
2. GPT image and `$scillm` image backends are declared but not wired; wire them
   only with caller attribution and image receipts.
3. Kokoro/KokoClone remains a future local low-cost lane and is not implemented
   in this research bundle.
