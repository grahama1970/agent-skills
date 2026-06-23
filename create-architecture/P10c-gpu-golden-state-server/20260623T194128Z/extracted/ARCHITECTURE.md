# PersonaPlex P10c GPU Golden-State Server Fix

This overlay replaces the invalid Docker REST/WebSocket proof path in `skills/personaplex/scripts/personaplex_gpu_inference_probe.py`.

The PersonaPlex container on `127.0.0.1:8998` is a Moshi/Opus binary streaming-audio WebSocket service. It is not a one-shot generated-token proof surface. The correct GPU proof path is the checked-out golden-state server probe:

```bash
/home/graham/workspace/experiments/personaplex/.venv/bin/python \
  /home/graham/workspace/experiments/personaplex/personaplex_golden_state_server.py \
  --probe-lmgen-step --json
```

The probe writes `real_gpu_personaplex=true` only when all of these hold:

1. the subprocess exits with code 0,
2. stdout contains parseable JSON,
3. JSON contains positive CUDA/GPU evidence, and
4. JSON contains actual generated LMGen.step output such as generated text, token ids, step output, or response content.

Hash-only fields such as `step_output_sha256` do not count as generated output. Fallback receipts remain deterministic and explicitly set `real_gpu_personaplex=false`.

## Commands

```bash
python -m py_compile skills/personaplex/scripts/personaplex_gpu_inference_probe.py
# expected exit code: 0

pytest -q skills/personaplex/tests/test_p10c_gpu_golden_state_server_probe.py
# expected exit code: 0

bash skills/personaplex/sanity_p10c_gpu_golden_state_server.sh
# expected exit code: 0 only on the target machine when CUDA and LMGen.step return generated output
```
