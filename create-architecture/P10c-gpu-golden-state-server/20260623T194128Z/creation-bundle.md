# Fix: Run golden_state_server under PersonaPlex venv for GPU proof

## Problem

GPU probe tries binary WebSocket against Docker container (no generated tokens
returned — container expects streaming audio, not one-shot requests).

The golden_state_server at personaplex_golden_state_server.py already knows how
to run PersonaPlex LMGen.step() with GPU. It uses os.execv to switch to the
PersonaPlex venv which has torch 2.4.1+cu121 with CUDA on RTX A5000.

## Fix

Update personaplex_gpu_inference_probe.py to:
1. Run golden_state_server as subprocess under PersonaPlex venv
   (/home/graham/workspace/experiments/personaplex/.venv/bin/python)
2. Pass --probe-lmgen-step --json flags to get a bounded LMGen.step() result
3. Record real_gpu_personaplex=true when the subprocess returns valid output
4. Fall back to real_gpu_personaplex=false when the server/cuda is unavailable

Zip: personaplex-p10c-gpu-golden-state-server-solution.zip
