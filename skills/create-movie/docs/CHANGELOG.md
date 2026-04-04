# Changelog

All notable changes to the create-movie skill will be documented in this file.

## [Unreleased]

### Breaking Changes
- KSML format is now deprecated in favor of HorusShotSpec YAML
- `--veo` flag now uses HorusShotSpec YAML instead of KSML
- `--renderer` now accepts `together:seedance-lite`, `fal:kling`, `veo`, `none` (replaces bare `veo`/`stills`)

### Added
- **Multi-renderer architecture**: pluggable video backends via `get_renderer(spec)` factory
  - `together:seedance-lite` — Together AI Seedance-lite (~$0.35/10s clip, default for dreams)
  - `fal:kling` / `fal:hailuo` — FAL.ai gateway to Kling 1.6 and MiniMax Hailuo
  - `veo` — Google Veo (original renderer)
  - `none` — skip video generation entirely
- HorusShotSpec v0.1 schema for shot-level video specification
- `core/shot_compiler.py` - Validates and compiles YAML to Veo API JSON
- `veo_adapter.py` - Exports create-movie output to HorusShotSpec YAML
- Validation layer enforcing Veo API constraints:
  - Duration must be 4, 8, or 16 seconds
  - Aspect ratio must be 16:9, 9:16, or 1:1
  - Max 6 reference images with weights 0.0-1.0
  - Prompt max length 4000 characters
- `tests/test_shot_compiler.py` - Schema validation and compilation tests
- `tests/test_orchestrator.py` - Integration tests for YAML shot generation
- `docs/KSML_TO_YAML_MIGRATION.md` - Migration guide from KSML to HorusShotSpec
- Skill registry entries for `tts-train`, `create-sound-design`, `create-storyboard`
- Per-skill `timeout_seconds` in `SkillInfo` dataclass (create-story: 900s, create-score: 1200s)

### Fixed
- **create-image**: `run.sh` now uses `uv run --script` for PEP 723 inline metadata resolution
- **create-image**: Caller passes positional prompt argument (was incorrectly using `--prompt` flag)
- **create-cast**: `script_analyzer.py` normalizes list-typed `action` fields to string before regex
- **create-cast**: Added missing `partial_results` field to `CastingResult` dataclass
- **create-movie orchestrator**: Safe access to `casting_result.partial_results` (guards against None)
- **create-sound-design**: Scene durations loaded from script JSON instead of hardcoded 30s
- **tts-train**: Model path uses `HORUS_TTS_CHECKPOINT` / `MEMORY_PROJECT_PATH` env vars with fallback chain
- **persona_integration.py**: tts-horus command changed from `"synthesize"` to `"say"` (correct subcommand)

### Changed
- Orchestrator now uses HorusShotSpec YAML for Veo rendering instead of KSML
- Added deprecation warnings when using KSML/Kling path
- AGENTS.md updated for multi-renderer reality (contracts, env vars, degradation matrix)

### Deprecated
- KSML format - use HorusShotSpec YAML instead
- `export_to_kling()` - use `export_to_veo()` instead
- KSML-based Veo rendering path

## [0.1.0] - 2026-01-15

### Added
- Initial release of create-movie skill
- Orchestrated workflow: Research → Script → Build Tools → Generate → Assemble → Learn
- Docker-isolated code execution
- Integration with LTX-2, WAN 2.2, Mochi video models
- Memory integration for storing filmmaking techniques
- RunPod integration for cloud GPU usage
- Equipment presets for camera/film simulation
- KSML export for Kling video API
