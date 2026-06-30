---
name: personaplex
description: >
  Generate, validate, and publish PersonaPlex voice prompts and bidirectional
  conversation test artifacts from persona reference audio. Use when converting
  Orpheus-TTS persona artifacts for Horus, Embry, or another persona into
  PersonaPlex-native .pt voice prompt files and live conversation review output.
triggers:
  - generate personaplex voice
  - create personaplex pt files
  - convert orpheus voice to personaplex
  - publish personaplex prompt
  - test personaplex conversation
  - personaplex from orpheus
provides:
  - personaplex-voice-prompt-generation
  - personaplex-config-publish
  - orpheus-to-personaplex-bridge
  - personaplex-bidirectional-conversation-proof
  - personaplex-readiness-report
composes:
  - orpheus-tts-voice-trainer
  - create-persona
  - voice-segment-selector
  - tts-voice
  - memory
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - audio
  - tts
  - conversation
  - validation
runtime_self_improvement: basic
---

# personaplex

`personaplex` is the bridge from trained persona voice artifacts to NVIDIA
PersonaPlex live conversation artifacts.

It accepts Orpheus-TTS reference audio packs, creates PersonaPlex-native voice
prompt `.pt` files, runs bidirectional offline conversation checks, and writes
receipts that make the current state inspectable.

## Boundary

- `orpheus-tts-voice-trainer` owns Orpheus training, emotion tags, reference WAV
  generation, and Orpheus inference receipts.
- `personaplex` owns PersonaPlex prompt-cache generation, PersonaPlex config,
  bidirectional conversation smoke output, and review HTML.
- `create-persona` owns persona memory, BDI, and mannerism/profile data.

Do not treat generic Resemblyzer/ECAPA speaker embeddings as PersonaPlex voice
prompts. PersonaPlex `.pt` files must be native Moshi/PersonaPlex prompt-cache
files containing:

```python
{"embeddings": ..., "cache": ...}
```

## Required Input: Orpheus Reference Pack

The upstream Orpheus trainer should provide a JSON file like:

```json
{
  "schema": "orpheus.personaplex_reference_pack.v1",
  "persona": "horus",
  "source": "orpheus-tts-voice-trainer",
  "orpheus_checkpoint": "/mnt/storage12tb/skills/voice-segment-selector/checkpoints/...",
  "references": [
    {
      "register": "neutral",
      "wav": "/mnt/storage12tb/skills/orpheus-tts-voice-trainer/outputs/horus/personaplex/horus_neutral.wav",
      "text_prompt": "You are Horus Lupercal in a calm, direct conversational register."
    }
  ]
}
```

Reference WAVs must be clean, single-speaker, and conversational. Emotion-tag
training clips are not ideal voice prompts unless they are deliberately selected
as a register reference.

Reference pack values are intentionally strict:

- `persona` and `references[].register` must be lowercase slugs, not paths.
- registers must be unique.
- unknown JSON fields are rejected.

## Commands

```bash
skills/personaplex/run.sh pack-from-receipt \
  --receipt /mnt/storage12tb/skills/voice-segment-selector/checkpoints/horus_orpheus_lora_v2_identity_plus_emotions/inference_receipt.json \
  --out /mnt/storage12tb/skills/personaplex/outputs/reference-packs/horus.json \
  --register neutral
```

Creates a reference pack from a single Orpheus PASS inference receipt. It maps
container-style `/checkpoints/...` receipt paths to the local checkpoint root,
hashes the receipt and WAV, validates the WAV, and writes a pack that
`validate-pack` and `verify-e2e` can consume.

By default, the source receipt must contain `verified: true`. For a technical
smoke reference that must not be treated as publication-ready, add:

```bash
--allow-unverified-smoke
```

That writes `verified: false` and `review_status: "unverified_smoke"` into the
pack. Such references require `--allow-provisional-reference` in `from-orpheus`
or `verify-e2e`, and the resulting receipt remains non-published.

```bash
skills/personaplex/run.sh validate-pack \
  --reference-pack /path/to/personaplex-reference-pack.json
```

Validates that the pack schema exists, every WAV path exists, and no output is
claimed.

```bash
skills/personaplex/run.sh from-orpheus \
  --reference-pack /path/to/personaplex-reference-pack.json \
  --personaplex-root ${HOME}/workspace/experiments/personaplex \
  --personaplex-python ${HOME}/workspace/experiments/personaplex/.venv/bin/python \
  --human-input-wav ${HOME}/workspace/experiments/personaplex/assets/test/input_assistant.wav \
  --max-human-input-seconds 2.0 \
  --out-dir /mnt/storage12tb/skills/personaplex/outputs/horus
```

For each reference WAV, this runs the real PersonaPlex offline path in two
separate subprocess phases:

1. build from the reference WAV with `--save-voice-embeddings`, producing a
   native PersonaPlex `.pt` cache;
2. replay from the generated `.pt` in a fresh process.

PASS requires the replay phase. A build run that only proves the source WAV can
run is not enough.

`--personaplex-python` or a PersonaPlex checkout venv is required. The command
does not silently fall back to the skill interpreter because PersonaPlex caches
are runtime/model-specific.

`--out-dir` must be absent or empty. Each run uses fixed private staging names
such as `voice-prompt.wav` and refuses preexisting `.pt` files so stale cache
reuse cannot masquerade as a new build.

For provisional smoke references only:

```bash
--allow-provisional-reference
```

Do not use this flag for publication gates.

The command produces:

- PersonaPlex-native `.pt`
- build output WAV/text JSON
- replay output WAV/text JSON
- `personaplex-publish-receipt.json`
- `index.html` review interface

For live smoke/E2E checks, use `--max-human-input-seconds` to crop the real
human-input WAV into the run directory before inference. The receipt records
both the original input WAV and the effective cropped WAV. This keeps the gate
non-mocked while avoiding long opaque runs on 40s+ fixtures.

```bash
skills/personaplex/run.sh verify-e2e \
  --reference-pack /path/to/personaplex-reference-pack.json \
  --personaplex-root ${HOME}/workspace/experiments/personaplex \
  --human-input-wav ${HOME}/workspace/experiments/personaplex/assets/test/input_assistant.wav \
  --max-human-input-seconds 2.0 \
  --out-dir /mnt/storage12tb/skills/personaplex/outputs/horus-e2e
```

`verify-e2e` is the native-cache release-relevant gate. It is non-mocked and
fail-closed: if PersonaPlex cannot run, cannot create a native `.pt`, cannot
safely inspect the `.pt`, or cannot replay the generated `.pt` into valid WAV
and parseable text JSON, the receipt status is `FAIL`.

This is not yet the live full-duplex WebSocket proof. Live bidirectional
readiness additionally requires server/client logs showing handshake, inbound
audio frames, outbound agent audio frames, text frames, and clean shutdown.

## Sanity

Fast structural sanity:

```bash
skills/personaplex/sanity.sh
```

Live E2E sanity:

```bash
ORPHEUS_PERSONAPLEX_REFERENCE_PACK=/path/to/personaplex-reference-pack.json \
PERSONAPLEX_ROOT=${HOME}/workspace/experiments/personaplex \
PERSONAPLEX_HUMAN_INPUT_WAV=${HOME}/workspace/experiments/personaplex/assets/test/input_assistant.wav \
skills/personaplex/sanity-e2e.sh
```

The live E2E sanity intentionally fails when those environment variables or
runtime dependencies are missing. A generated request file is not proof.

## Receipts

The main receipt shape is:

```json
{
  "schema": "personaplex.publish_receipt.v1",
  "status": "CACHE_REPLAY_PASS",
  "publication_status": "NOT_PUBLISHED",
  "human_review_status": "NOT_REVIEWED",
  "persona": "horus",
  "input_reference_pack": "...",
  "runtime_identity": {
    "personaplex_git_head": "...",
    "personaplex_git_status": "...",
    "personaplex_offline_patch_sha256": "...",
    "python_version": "...",
    "pip_freeze": "..."
  },
  "reference_provenance": [],
  "generated_voice_prompts": [
    {
      "register": "neutral",
      "wav": ".../horus_neutral.wav",
      "pt": ".../horus_neutral.pt",
      "pt_schema": {
        "keys": ["cache", "embeddings"],
        "sha256": "...",
        "embeddings": {"shape": [1, 1, 1, 4096]},
        "cache": {"shape": [1, 32, 4096]}
      },
      "build_output_wav": ".../neutral/build-from-wav-output.wav",
      "build_output_text": ".../neutral/build-from-wav-output.json",
      "replay_output_wav": ".../neutral/replay-from-pt-output.wav",
      "replay_output_text": ".../neutral/replay-from-pt-output.json"
    }
  ],
  "review_html": ".../index.html"
}
```

Receipts include SHA-256 hashes and basic audio/text metrics for the input,
build output, and replay output.

`CACHE_REPLAY_PASS` is a technical gate only. Publication requires a later human
listening receipt and a clean approved identity anchor. A technical receipt must
not be described as `PUBLISHED` or live full-duplex ready.

## WebGPT Review Notes

The initial WebGPT review agreed with keeping `personaplex` separate from
`orpheus-tts-voice-trainer`, but identified these non-negotiable gates:

- do not pass a `.pt` unless a fresh process successfully replays that `.pt`;
- do not import PersonaPlex internals through the skill environment when the
  pinned PersonaPlex runtime can be invoked as a subprocess;
- safely inspect `.pt` files and record tensor reports;
- reject path-like persona/register values;
- escape HTML review output;
- do not claim live full-duplex readiness from offline file-to-file inference.

The follow-up WebGPT review also required:

- strict provenance mode for release-relevant E2E;
- no `verified=false` fallback to PASS status;
- private staging and stale-cache rejection;
- explicit pinned PersonaPlex runtime identity in receipts;
- nonempty string token validation for output text JSON;
- atomic final receipt writing after review HTML exists;
- separate technical cache replay, publication, and live full-duplex gates.

## Project Knowledge

Maintain `PROJECT_KNOWLEDGE.md` when architecture, runtime paths, or known
PersonaPlex artifact requirements change.
