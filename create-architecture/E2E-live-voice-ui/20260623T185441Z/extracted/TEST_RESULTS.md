# TEST_RESULTS

Executed in the solution build directory.

## Unit tests

Command:

```bash
cd /mnt/data/personaplex_e2e_solution
PYTHONPATH="$PWD/skills/personaplex/scripts:${PYTHONPATH:-}" python3 -m unittest discover -s skills/personaplex/tests -v
```

Result:

```text
Ran 15 tests in 1.563s

OK
```

Exit code: `0`.

## Syntax check

Command:

```bash
cd /mnt/data/personaplex_e2e_solution
PYTHONPATH="$PWD/skills/personaplex/scripts:${PYTHONPATH:-}" \
  python3 -m py_compile \
    skills/personaplex/scripts/personaplex_e2e_live_voice_session.py \
    skills/personaplex/scripts/personaplex_e2e_ui_render.py
```

Result: no output.

Exit code: `0`.

## Deterministic fallback sanity

Command:

```bash
cd /mnt/data/personaplex_e2e_solution
./skills/personaplex/sanity_e2e_live_voice_fallback.sh
```

Relevant result:

```text
fallback receipt is honest: all_real_true=false
Fallback receipt: /tmp/personaplex-e2e-live-voice-ui-fallback/e2e-live-voice-receipt.json
Fallback UI: /tmp/personaplex-e2e-live-voice-ui-fallback/personaplex-e2e-live-voice-ui.html
```

Exit code: `0`.

## Live service proof

Not executed in this build environment because it requires the target workstation services and credentials:

- `DEEPGRAM_API_KEY`
- memory daemon at `http://127.0.0.1:8601`
- PersonaPlex GPU proof path through `personaplex_golden_state_server.py`
- PersonaPlex checkout audio at `assets/test/input_assistant.wav`

The live proof command is documented in `ARCHITECTURE.md` and enforced by `--require-real`, which exits `2` unless every final `real_*` flag is true.
