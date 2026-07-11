# Persona Dream ComfyUI Lane

This lane exists so an agent can use ComfyUI as a reproducible API service
rather than as a human-only canvas.

## Purpose

ComfyUI provides value to `persona-dream` when it can run saved workflow graphs
for:

- character and pose sheets for Embry, Horus, or scene extras;
- Z-Image Turbo keyframes and perspective variants;
- Wan 2.2 image-to-video clips when local models are mounted;
- visual workflow inspection by a human after the agent has submitted jobs.

The project agent should submit workflow JSON through the API and store both
the UI workflow JSON and API prompt JSON as receipts. `$surf` is only for
opening the browser UI later to inspect or screenshot the graph; it is not the
primary execution mechanism.

## Expected Readiness

Start the service:

```bash
docker compose -f skills/persona-dream/comfyui/docker-compose.yml up -d --build
```

Then prove readiness:

```bash
curl -fsS http://127.0.0.1:8188/system_stats
curl -fsS http://127.0.0.1:8188/object_info
./skills/persona-dream/run.sh backend-readiness \
  --output-dir /mnt/storage12tb/skills/persona-dream/outputs/horus-embry-tea-void-sparta-r1
```

The readiness receipt must move `comfyui_service` from `not_running` to
`available` before any ComfyUI generation step is accepted.

## Required Model Mount

The compose file mounts:

```text
/mnt/storage12tb/comfyui/models -> /opt/comfyui/models
```

That path must contain the actual Z-Image Turbo and Wan 2.2 model files in the
subdirectories ComfyUI expects. Placeholder files such as `put_checkpoints_here`
do not count as readiness evidence.

## Agent Artifact Contract

For each ComfyUI generation attempt, write:

```text
comfyui_workflow_<stage>_<shot>.json
comfyui_api_prompt_<stage>_<shot>.json
comfyui_receipt_<stage>_<shot>.json
generated image/video output path
sha256 hash of each output
```

Do not advance to I2V or FFmpeg assembly unless the receipt proves the expected
output file exists and passes the continuity checks in `character_scene_bible.json`.
