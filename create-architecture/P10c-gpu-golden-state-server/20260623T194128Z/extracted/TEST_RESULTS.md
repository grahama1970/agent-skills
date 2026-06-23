# Test Results

Executed in the packaging sandbox:

```text
python -m py_compile skills/personaplex/scripts/personaplex_gpu_inference_probe.py
exit code: 0
```

```text
pytest -q skills/personaplex/tests/test_p10c_gpu_golden_state_server_probe.py
exit code: 0
3 passed
```

Live GPU proof is intentionally not claimed by this zip. On the target PersonaPlex workstation, run:

```bash
bash skills/personaplex/sanity_p10c_gpu_golden_state_server.sh
```

A real proof requires the receipt to show `real_gpu_personaplex=true`, `valid_cuda_device=true`, and `valid_generated_output=true`.
