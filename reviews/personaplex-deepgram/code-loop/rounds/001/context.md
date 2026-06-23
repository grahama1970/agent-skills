# PersonaPlex Deepgram Live ASR/VAD Code Review Context

## Objective

Review the direct-async Deepgram integration for the PersonaPlex golden-state
wrapper. The implementation should support a production-style "Talker-Reasoner"
flow: browser Opus audio is decoded once, PCM is fed to both PersonaPlex/Moshi
and Deepgram, Deepgram `speech_final` turn events trigger grounding, and output
speech is masked until required facts arrive.

## Decision Requested

Is this approach safe enough to continue building on, or are there blocking code
or architecture problems in the current implementation that should be fixed
before adding microphone/browser UI tests?

## Review Scope

- `skills/personaplex/scripts/personaplex_golden_state_server.py`
- `skills/personaplex/scripts/personaplex_deepgram_live.py`
- `skills/personaplex/scripts/personaplex_deepgram_live_probe.py`
- `skills/personaplex/scripts/personaplex_memory_flow.py`
- `skills/personaplex/PROJECT_KNOWLEDGE.md`

## Expected Contracts

1. Deepgram turn triggering must be based on `speech_final=true`, not partial
   `is_final=true`, to avoid premature memory/Brave calls.
2. Live audio must continue driving PersonaPlex at the 12.5 Hz cadence while
   Deepgram and grounding run asynchronously.
3. Output gating must mask generated speech/text while required grounding is in
   flight and open only after required stages finish or error handling releases
   the gate.
4. Memory and Brave stages must remain evidence-bearing and source-packeted; no
   facts should be spoken before the grounding stages are complete.
5. GPU/model work must run under `torch.no_grad()` in the live loop and not leak
   gradients or CUDA memory.
6. The proof harness must be clearly marked as synthesized speech, not
   microphone capture.
7. The stock container/runtime must be restored after live wrapper testing.

## Local Evidence Already Run

Compile:

```text
/home/graham/workspace/experiments/personaplex/.venv/bin/python -m py_compile \
  skills/personaplex/scripts/personaplex_golden_state_server.py \
  skills/personaplex/scripts/personaplex_deepgram_live.py \
  skills/personaplex/scripts/personaplex_deepgram_live_probe.py \
  skills/personaplex/scripts/personaplex_memory_flow.py
```

Compile exit code was 0.

Wrapper health:

```json
{
  "schema": "personaplex.golden_state_server.health.v1",
  "ok": true,
  "device": "cuda",
  "cuda_device": "NVIDIA RTX A5000",
  "timings": {
    "load_ms": 6805.2,
    "warmup_ms": 5983.97,
    "golden_pre_roll_ms": 9072.53,
    "golden_clone_ms": 1.15,
    "boot_total_ms": 21862.94
  }
}
```

Deepgram live proof receipt:

```text
/mnt/storage12tb/skills/personaplex/outputs/deepgram-live-probe/embry/20260622T203618Z/personaplex-deepgram-live-probe-receipt.json
```

Receipt summary:

```json
{
  "status": "PASS",
  "speech_final": true,
  "transcript": "Embry, what is the weather like in Hawaii today, and how would that make you feel about surfing with Kai?",
  "stages": ["intent", "memory", "brave", "route"],
  "gate_complete_active": false,
  "queue_depth": 268
}
```

Stock container restored:

```text
personaplex-personaplex-1 Up ... 0.0.0.0:8998->8998/tcp
```

## Known Risks To Re-check

- `deepgram_loop` may hang waiting on `turn_queue.get()` if shutdown ordering is
  wrong.
- The output gate currently masks audio with silence but still allows early
  generated text before the first grounding trigger; decide whether that is
  acceptable or should be state-gated earlier.
- Grounding stage order can vary because memory and Brave may race; review
  whether required facts are truly complete before route/answer tokens are
  injected.
- Deepgram buffering joins final segments with spaces; review whether duplicate
  segment text can occur with Deepgram result semantics.
- The live probe uses synthesized speech and trailing silence; it is not a
  browser microphone proof.

## Non-goals

- Do not review unrelated `skills/personaplex` files outside the listed scope.
- Do not treat WebGPT review as deterministic closure proof.
- Do not require a separate Deepgram microservice unless the direct-async design
  creates a concrete correctness or reliability problem.

## Required Reviewer Output

Return:

```json
{
  "verdict": "satisfied | needs_changes | blocked | insufficient_evidence",
  "blocking_findings": [],
  "non_blocking_findings": [],
  "patch_suggestions": [],
  "tests_to_run": [],
  "do_not_do": [],
  "aggregation_ready": false,
  "missing_evidence": []
}
```
