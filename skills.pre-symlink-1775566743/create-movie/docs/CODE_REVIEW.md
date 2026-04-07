Create-Movie Deep Review (2026-02-17)

Summary
The workflow is feature-rich, but several placeholders and hardcoded paths create silent-failure risks and portability issues. The highest risk is audio tooling that reports success without producing audio. Medium risks include brittle paths and large modules that are difficult to safely modify without regression tests.

High
1. `.pi/skills/create-movie/create_movie/phases/build_tools.py` and `.pi/skills/create-movie/**/tools/audio_processor.py`: Audio processing is a no-op stub that exits successfully. This can silently ship videos missing audio while the pipeline reports success. Suggested fix: implement a minimal FFmpeg-based mixer or make the stub exit non-zero with an explicit error and mark the tool as unimplemented in the manifest. Minimal tests: add a unit test that `build_tools_for_script` generates an audio processor that fails loudly until implemented, and an integration test that an audio-required script surfaces a clear error instead of silently continuing.

Suggested diff (fail-fast stub):
```diff
--- a/.pi/skills/create-movie/test_e2e_together/tools/audio_processor.py
+++ b/.pi/skills/create-movie/test_e2e_together/tools/audio_processor.py
@@
-print("Tool audio_processor not yet implemented")
+raise SystemExit("audio_processor not implemented; provide a real mixer or disable audio")
```

Medium
1. `.pi/skills/create-movie/nightly_dream.sh`, `.pi/skills/create-movie/RESEARCH_SYNTHESIS.md`, `.pi/skills/create-movie/0N_TASKS_VIDEO_API.md`: Hardcoded absolute paths to `${MEMORY_PROJECT_PATH}` and `${MEMORY_PROJECT_PATH}/persona` break portability and can write to a non-existent location. Suggested fix: require `MEMORY_PROJECT_PATH` and validate it exists; document the env var in the docs. Minimal tests: a shell test that exits non-zero when `MEMORY_PROJECT_PATH` is unset or invalid; a test that uses a temp directory and confirms output paths are derived from the env var.

Suggested diff (env validation):
```diff
--- a/.pi/skills/create-movie/nightly_dream.sh
+++ b/.pi/skills/create-movie/nightly_dream.sh
@@
-PERSONA_DIR="${MEMORY_PROJECT_PATH:-/path/to/memory}/persona"
+if [[ -z "${MEMORY_PROJECT_PATH:-}" || ! -d "${MEMORY_PROJECT_PATH}" ]]; then
+  echo "[nightly-dream] MEMORY_PROJECT_PATH must point to the memory repo" >&2
+  exit 1
+fi
+PERSONA_DIR="${MEMORY_PROJECT_PATH}/persona"
```

2. `.pi/skills/create-movie/core/renderer.py`: `NullRenderer.render_shot` returns `success=True` with `output_path=None`. In `orchestrator.py`, renderer success is used to continue; a `none` renderer can make later phases appear successful without output. Suggested fix: return `success=False` or create a placeholder file when running in dry-run mode, and ensure downstream checks for `output_path`. Minimal tests: `tests/test_renderer.py` verifying `get_renderer("none")` yields a renderer that either writes a placeholder file or signals failure, and `assemble_movie` handles the dry-run case deterministically.

3. `.pi/skills/create-movie/create_movie/phases/dream_mode.py` and `.pi/skills/create-movie/persona_integration_monolith.py`: Both exceed 800 lines, increasing regression risk. Suggested fix: split into focused modules (prompting, rendering, persistence, memory adapters) and move shared helpers into `create_movie/utils.py`. Minimal tests: add unit tests for each extracted module and a high-level dream-mode integration test that uses a small fixture script and validates expected files are created.

Low
1. `.pi/skills/create-movie/persona_integration_monolith.py`: Broad `except Exception: pass` blocks swallow errors (e.g., TTS failures, JSON decode errors), which hides misconfigurations. Suggested fix: log warnings with context and, where safe, return sentinel values. Minimal tests: a unit test that invalid JSON logs a warning and returns an empty list rather than silently passing.

2. `.pi/skills/create-movie/0N_TASKS_VIDEO_API.md` and `.pi/skills/create-movie/0N_IMPROVEMENTS.md`: Multiple placeholders and a code block with `pass` represent aspirational work but are not tracked. Suggested fix: convert to issues or move to a single tracking section with owners and dates. Minimal tests: none (doc-only), but keep a lint rule that forbids unresolved placeholders in non-task docs if desired.
