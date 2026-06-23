# Fix: P10 GPU Probe — Use Docker Container API Instead of Local LMGen

## Problem

The GPU inference probe (`personaplex_gpu_inference_probe.py`) tries to import
`personaplex_golden_state_server.py` locally via `importlib` and call
`LMGen.step(...)`. But PersonaPlex already runs as a Docker container on this
machine:

- **Container:** `personaplex-personaplex-1` (up 23 hours)
- **GPU:** RTX A5000 (24GB) — verified CUDA available
- **Model:** PersonaPlex 7B v1 loaded
- **API:** `https://127.0.0.1:8998` (HTTPS, serves Web UI)

## Required Fix

Update `personaplex_gpu_inference_probe.py` and/or the E2E session probe to:

1. Check if the PersonaPlex Docker container is running (`docker ps`)
2. If yes, hit `POST https://127.0.0.1:8998/api/chat` or the appropriate
   PersonaPlex inference endpoint with a bounded prompt
3. If the container is not running, fall back to `real_gpu_personaplex=false`
4. Record `real_gpu_personaplex=true` only when the container responds with
   generated audio/text tokens

The Docker container serves static content and a WebSocket/Web UI. The exact
API path may need discovery. The probe should try:
- `GET https://127.0.0.1:8998/` (returns HTML — confirmed working)
- WebSocket at `wss://127.0.0.1:8998/api/chat` or similar

## Deliverable

A single updated `personaplex_gpu_inference_probe.py` that proves GPU inference
via the running Docker container, with honest `real_gpu_personaplex=true|false`.

Zip name: `personaplex-p10-gpu-docker-fix-solution.zip`
