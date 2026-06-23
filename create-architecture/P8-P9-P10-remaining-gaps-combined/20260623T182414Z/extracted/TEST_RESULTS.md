# Local Deterministic Validation Results

These are local offline/deterministic validation results generated while building the bundle. They are not live Deepgram, live memory-daemon, or live GPU proof unless the target receipt has the relevant `real_*` flag set to true.

## Unit tests

Command:

```bash
cd /mnt/data/p8p9p10_solution && \
PYTHONPATH="$PWD/skills/personaplex/scripts:${PYTHONPATH:-}" \
python3 -m unittest discover -s skills/personaplex/tests -p 'test_p8_p9_p10_remaining_gaps.py' -v
```

Observed result:

```text
Ran 10 tests in 1.544s
OK
```

Expected exit code: `0`.

## Sanity scripts

Commands run from `/mnt/data/p8p9p10_solution`:

```bash
bash skills/personaplex/sanity_p8_live_deepgram_real_audio.sh
bash skills/personaplex/sanity_p9_conversation_compaction.sh
bash skills/personaplex/sanity_p10_gpu_personaplex_inference.sh
PERSONAPLEX_SKIP_DEEPGRAM=1 PERSONAPLEX_SKIP_GPU=1 bash skills/personaplex/sanity_p8_p9_p10_combined.sh
bash skills/personaplex/sanity_p8_p9_p10_combined.sh
```

Observed result: all exited `0` in non-strict mode. Where live services were unavailable in this sandbox, receipts recorded `real_* = false` with deterministic fallback.
