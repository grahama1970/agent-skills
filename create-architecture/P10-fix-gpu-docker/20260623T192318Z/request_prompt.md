# Fix: P10 GPU Probe — Use Docker Container

PersonaPlex runs in Docker on this machine: `personaplex-personaplex-1` serving
HTTPS on `https://127.0.0.1:8998` with PersonaPlex 7B v1 on RTX A5000.

The GPU probe tries local LMGen but should hit the running container instead.

**Required:** One updated `personaplex_gpu_inference_probe.py` that probes the
Docker container API and records `real_gpu_personaplex=true` on success.

Zip: `personaplex-p10-gpu-docker-fix-solution.zip`
