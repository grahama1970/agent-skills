# Prompt Improvements For Future PersonaPlex Creation Bundles

1. Include the current source bodies or a patch base for every file named as “likely in scope.” This avoids accidental replacement of local server behavior when the requested change is an adapter extension.

2. For CAS requirements, specify whether the memory daemon has a read/conditional-write endpoint. If only `POST /upsert` exists, require receipts to distinguish client-side generation checks from server-enforced CAS.

3. For Deepgram validation, state whether the fixture is WAV-container audio or raw PCM. When the WebSocket URL includes `encoding=linear16`, the adapter should strip WAV headers and send PCM frames.

4. For GPU proof, require the golden-state server to expose one stable machine-callable hook, for example:

```python
def probe_lmgen_step(out_dir: str, personaplex_root: str | None = None, timeout: float = 30.0, max_steps: int = 1) -> dict:
    ...
```

The hook should return JSON containing:

```json
{
  "real_gpu_personaplex": true,
  "lmgen_step_called": true,
  "device": "cuda:0",
  "output_token_id": 123,
  "step_output_sha256": "..."
}
```

5. Keep the receipt contract explicit: non-strict sanity may exit 0 with fallback, while strict gates must exit 2 when the relevant `real_*` flag is false.

6. Continue to forbid inline vectors and raw audio bytes in memory payloads. Store vector lifecycle ownership and audio path/hash metadata instead.
