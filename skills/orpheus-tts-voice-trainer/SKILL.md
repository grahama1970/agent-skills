---
name: orpheus-tts-voice-trainer
description: >
  Persona-level Orpheus TTS voice training orchestrator. Use when the human asks
  to train or improve an Orpheus persona voice, collect Orpheus-native emotion
  tags, generate ElevenLabs voice_id-backed nonverbal examples, fill missing
  laugh/chuckle/sigh/cough/sniffle/groan/yawn/gasp tags, review synthetic or
  movie-curated voice clips, or finish train/inference/publish for Embry,
  Horus Lupercal, or another persona. Delegates clip review/export/training to
  voice-segment-selector and voice identity/bakeoff guidance to hum.
triggers:
  - orpheus tts voice trainer
  - /orpheus-tts-voice-trainer
  - train orpheus persona voice
  - collect orpheus emotion tags
  - generate elevenlabs orpheus emotion tags
  - fill missing orpheus tags
  - horus lupercal orpheus emotion tags
  - embry orpheus emotion tags
provides:
  - orpheus-persona-training-plan
  - orpheus-emotion-tag-gap-fill
  - elevenlabs-voice-tts-candidate-plan
  - voice-segment-selector-handoff
  - unsloth-studio-training-handoff
composes:
  - voice-segment-selector
  - hum
  - watch
  - ingest-movie
  - get-subtitles
  - brave-search
  - ops-huggingface
  - tts-voice
  - unsloth-studio
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-subagent
taxonomy:
  - audio
  - orchestration
  - tts
  - validation
disciplines:
  - ml-training
  - voice-audio
---

# orpheus-tts-voice-trainer

Use this skill as the **front door** for persona Orpheus voice training when the
job is bigger than selecting clips: source discovery, missing emotion tags,
ElevenLabs `voice_id` selection, synthetic gap-fill, human review, Orpheus
dataset export, fine-tune, inference proof, and publish.

Do not reimplement audio selection, review UI, export, or training. Delegate
those to `voice-segment-selector` and `tts-voice`.

## Required Outcome

A run is not useful until it can answer these questions with paths:

- Which persona is being trained?
- Which Orpheus-native tags are required and how many reviewed examples exist?
- Which examples are movie-curated, ElevenLabs generic SFX, or ElevenLabs
  `voice_id`-backed TTS audio tags?
- Which tags are still missing or under target?
- Which `voice-segment-selector` job contains the reviewed candidates?
- Which train, inference, and publish receipts prove the Orpheus model state?

Native Orpheus tags are exactly:

```text
<laugh> <chuckle> <sigh> <cough> <sniffle> <groan> <yawn> <gasp>
```

Never train custom tags such as `<angry>`, `<sarcastic>`, or `<giggle>`.
Map `giggle` requests to `<chuckle>` or `<laugh>` with the original cue kept in
metadata.

## Workflow

1. **Define persona and target inventory**
   - Persona: `embry`, `horus`, or explicit speaker id.
   - Pilot count: default 20 reviewed examples per tag to prove generation,
     review, export, and inference end to end.
   - Training count: default 100 reviewed examples per tag unless the human
     gives another number. Treat 20-50 reviewed examples/tag as a smoke/minimum
     range, not training-ready coverage.
   - Output job: use `/mnt/storage12tb/skills/voice-segment-selector/jobs/<persona>-orpheus-emotion-tags`.

2. **Prefer authentic sources first**
   - Use `watch`, `get-subtitles`, `brave-search`, `ingest-movie`, and local
     media to find movie/audiobook/dialogue examples.
   - If a tag does not appear in subtitles/transcripts/audio evidence, report it
     as missing instead of inventing movie evidence.

3. **Choose or bake off ElevenLabs voice identity**
   - Use `$hum` guidance for voice search and voice bakeoff.
   - Record `voice_id`, voice name, search query, persona fit notes, and rejected
     alternatives.
   - Do not use celebrity names in generation prompts.
   - Search the ElevenLabs Voice Library through the API; do not rely on a
     manually remembered voice name.

4. **Generate synthetic gap-fill only for missing/under-target tags**
   - Use `voice-segment-selector generate-orpheus-sfx`.
   - No prompt may be sent to ElevenLabs until `agents/prompt-reviewer` has
     reviewed the generated prompt bundle and written a PASS receipt. This is a
     hard gate, not advisory. If the receipt is absent, stale, or not PASS,
     stop with `BLOCKED: prompt_review_required`.
   - For persona-matched nonverbals, use Eleven v3 TTS audio tags:

```bash
skills/voice-segment-selector/run.sh generate-orpheus-sfx \
  --job-dir "$JOB" \
  --speaker "$SPEAKER" \
  --tags laugh,chuckle,sigh,cough,sniffle,groan,yawn,gasp \
  --samples-per-tag 20 \
  --generation-mode voice-tts \
  --voice-id "$ELEVENLABS_VOICE_ID" \
  --voice-name "$ELEVENLABS_VOICE_NAME"
```

   - Use `--dry-run` first to create `prompt-review/prompt_review_bundle.json`
     without spending API credits.
   - Send that bundle to `agents/prompt-reviewer` and require a receipt at:
     `prompt-review/prompt-reviewer-receipt.json`.
   - The receipt must include `verdict: "PASS"`, the reviewed bundle path, and
     the prompt-reviewer artifact path before any non-dry-run generation.
   - Generic `sound-generation` is allowed only for non-persona guide sounds or
     fallback texture. Persona training candidates should use `voice-tts`.

5. **Review candidates before training**
   - After non-dry-run synthetic generation, run the classifier gate before
     promotion or export:

```bash
skills/voice-segment-selector/run.sh classify-orpheus-sfx \
  --job-dir "$JOB"
```

   - The classifier receipt is `$JOB/classifier-result.json`. It combines
     `MIT/ast-finetuned-audioset-16-16-0.442` AudioSet labels with waveform
     features. If the Hugging Face model is unavailable, `--no-ast` may be used
     only as a local waveform prefilter, not as final training proof.
   - The waveform gate encodes the human-labeled sonic distinction:
     `<laugh>` must be sustained and multi-pulse; `<chuckle>` is short and
     restrained; `<sigh>` is exhale-forward; `<gasp>` is short inhale-forward;
     `<yawn>` requires a longer open-mouth inhale/exhale shape.
   - Use `voice-segment-selector review`.
   - Reject clips with words, music, ambience, crowd noise, wrong persona feel,
     wrong tag, or unclear nonverbal event.
   - Reject or regenerate classifier failures before human review unless the
     human explicitly overrides a specific clip id.
   - Accepted candidates must preserve provenance:
     `movie_curated`, `elevenlabs_sfx`, or `elevenlabs_voice_sfx`.

6. **Export and finish**
   - Run `export-orpheus`.
   - If downstream training is requested, write an explicit
     `unsloth-handoff-dag.yaml` that references the `export-orpheus` dataset
     receipt. Do not hand off prose-only instructions.
   - Ask `agents/unsloth-studio` to run the training/evaluation DAG only after
     the exported dataset receipt exists.
   - Run `finish-orpheus` through `voice-segment-selector`/`tts-voice` only
     when that is the configured local training path. Otherwise, consume the
     `unsloth-studio` training/evaluation/export receipts.
   - Report train, inference, and publish receipts. Do not claim voice readiness
     without an inference receipt with `"status": "PASS"`.

## Unsloth Studio Training Handoff

`orpheus-tts-voice-trainer` owns candidate acquisition and dataset readiness.
`unsloth-studio` owns model training infrastructure after an exported Orpheus
dataset exists. The handoff between them is a DAG artifact, not a prose request.

Minimum handoff artifact:

```yaml
schema: subagent_dag.v1
handoff: orpheus_to_unsloth_training.v1
producer: agents/orpheus-tts-trainer
consumer: agents/unsloth-studio
mode: bounded_dag
inputs_required:
  - exported_dataset_receipt.json
  - hf_dataset_path
  - persona_id
  - base_or_identity_checkpoint
  - inference_probe_prompts
nodes:
  - id: verify_dataset_receipt
    kind: receipt_validation
    receipts: [dataset-receipt-validation.json]
    stop_conditions: [dataset_receipt_valid, dataset_receipt_missing_or_invalid]
  - id: start_training
    kind: unsloth_training_job
    needs: [verify_dataset_receipt]
    receipts: [training-start.json]
    stop_conditions: [training_started, training_start_failed]
  - id: monitor_training
    kind: training_metrics_monitor
    needs: [start_training]
    receipts: [training-metrics.json, training-status.json]
    stop_conditions: [training_completed, training_failed, training_stopped]
  - id: evaluate_inference
    kind: inference_probe_eval
    needs: [monitor_training]
    receipts: [inference-probes.json]
    stop_conditions: [inference_passed, inference_failed]
  - id: export_checkpoint
    kind: checkpoint_export
    needs: [evaluate_inference]
    receipts: [checkpoint-export.json]
    stop_conditions: [checkpoint_exported, export_failed]
receipt_policy:
  per_node_receipt_required: true
  final_receipt_required: true
start_gate:
  require_dag_spec_before_work: true
  reject_prose_only_work_orders: true
```

The Orpheus trainer must not ask Unsloth to generate, relabel, or review
ElevenLabs candidates. If the dataset receipt is missing, stale, or points to
unreviewed candidates, the correct outcome is `BLOCKED: dataset_receipt_missing`
or `BLOCKED: dataset_not_reviewed`, not an Unsloth training run.

## Persona Recipes

### Embry Lawson

Voice search intent:

```text
young adult female, husky, light rasp, mid-low/alto, grounded, intimate,
dry humor, understated, not bubbly, not anime, not seductive, not narrator-heavy
```

Useful ElevenLabs library searches:

```text
husky female
young adult female husky
raspy female alto
dry humor female voice
grounded intimate female voice
```

Current ElevenLabs persona voice registry:

```json
{
  "persona": "embry",
  "selected_voice_id": "xYa75LlayhWHCRl1yJSH",
  "selected_voice_name": "Melissa - Intimate, Calming, Light Rasp",
  "source_skill": "hum",
  "evidence": [
    "skills/hum/jobs/joan_jett_crimson_and_clover/run_20260620T164053Z/sts/sts_bakeoff_manifest.json",
    "skills/hum/jobs/joan_jett_crimson_and_clover/run_20260620T164053Z/voices/shared_voices_shortlist.json"
  ],
  "notes": "Human confirmed this as Melissa: intimate, calming, slightly husky/light rasp; quiet confidence, warm, airy, grounded, a bit vulnerable, not polished. Used by hum as the light_rasp required baseline in STS bakeoff variants. Anesha / rujGCruvEqncqHTi6l0q was a shared-voice comparison, not the baseline."
}
```

### Horus Lupercal

Voice search intent:

```text
middle-aged British male narrator, authoritative, gravelly, warm, rich,
commanding, dramatic, gothic science fiction, calm threat, war-worn gravitas
```

Prefer British narrator/professional voices over `military` search terms. Good
candidate searches:

```text
British gravelly narrator
British authoritative male
deep British storytelling
gothic sci fi narrator
warm rich British male
```

Candidate voice names to try first when available in the current ElevenLabs
library:

- `Marcus` — first-pass Horus candidate for Warhammer/Gothic gravitas.
- `George` — warmer, textured fallback.
- `James` — polished professional narrator fallback.

Initial Eleven v3 settings for Horus voice-tag generation:

```json
{
  "stability": 0.35,
  "similarity_boost": 0.8,
  "style": 0.25,
  "use_speaker_boost": true
}
```

Review Horus tags especially hard for theatrical overacting. The desired result
is controlled authority, not cartoon villain delivery.

Current ElevenLabs persona voice registry:

```json
{
  "persona": "horus",
  "selected_voice_id": "jtE6dbPUTt2kchN89Uej",
  "selected_voice_name": "James - Deep, Raspy and Grim",
  "source": "ElevenLabs Voice Library",
  "evidence": [
    "https://elevenlabs.io/app/voice-library?voiceId=jtE6dbPUTt2kchN89Uej",
    "/mnt/storage12tb/skills/voice-segment-selector/jobs/horus-lupercal-orpheus-elevenlabs-voice-tts-smoke-v2/elevenlabs_orpheus_sfx_manifest.json"
  ],
  "notes": "Human selected and added this voice as close to Horus Lupercal's intended voice. Use for Horus voice-tts Orpheus emotion-tag generation unless superseded by a later human-approved bakeoff."
}
```

## ElevenLabs Voice Library API

Use the helper script instead of hand-writing curl repeatedly. It wraps:

- `GET /v1/shared-voices` for Voice Library search.
- `POST /v1/voices/add/{public_owner_id}/{voice_id}` to add a selected shared
  voice to the account before using it with TTS.

Run with `uv` so the script gets `typer` and `httpx` without adding a local
venv:

```bash
uv run --with typer --with httpx --with python-dotenv \
  python skills/orpheus-tts-voice-trainer/scripts/elevenlabs_voice_library.py search \
  --query "gritty dramatic" \
  --gender male \
  --accent british \
  --age middle_aged \
  --page-size 20 \
  --out /mnt/storage12tb/skills/voice-segment-selector/jobs/horus-lupercal-orpheus-emotion-tags/voice-search/gritty-dramatic-british.json
```

For Horus, run at least these searches and compare returned `voice_id`,
`public_owner_id`, labels, descriptions, and previews:

```bash
QUERY="British gravelly narrator"
QUERY="British authoritative male"
QUERY="deep British storytelling"
QUERY="gothic sci fi narrator"
QUERY="warm rich British male"
QUERY="gritty dramatic"
```

Once a candidate is selected, add it to the account:

```bash
uv run --with typer --with httpx --with python-dotenv \
  python skills/orpheus-tts-voice-trainer/scripts/elevenlabs_voice_library.py add \
  --public-owner-id "$PUBLIC_OWNER_ID" \
  --voice-id "$VOICE_ID" \
  --new-name "Horus Orpheus Candidate - Marcus"
```

Then pass the resulting usable `voice_id` to `voice-segment-selector`:

```bash
skills/voice-segment-selector/run.sh generate-orpheus-sfx \
  --job-dir "$JOB" \
  --speaker horus \
  --samples-per-tag 20 \
  --generation-mode voice-tts \
  --voice-id "$VOICE_ID" \
  --voice-name "$VOICE_NAME" \
  --dry-run
```

The dry run must produce `prompt-review/prompt_review_bundle.json` and
`elevenlabs_orpheus_sfx_manifest.json` before any paid generation. The next
step is always prompt review:

```bash
# Request prompt review before spending ElevenLabs credits.
# The prompt-reviewer subagent may write review artifacts only; generation stays blocked
# until prompt-review/prompt-reviewer-receipt.json exists with verdict PASS.
cat > "$JOB/prompt-review/prompt-reviewer-request.json" <<JSON
{
  "schema": "prompt_reviewer_request.v1",
  "target_subagent": "agents/prompt-reviewer",
  "prompt_bundle": "$JOB/prompt-review/prompt_review_bundle.json",
  "required_receipt": "$JOB/prompt-review/prompt-reviewer-receipt.json",
  "policy": {
    "no_elevenlabs_generation_before_pass": true,
    "reviewer_verdict_required": "PASS"
  }
}
JSON
```

## Report Format

Use this shape for status and handoff:

```json
{
  "persona": "horus",
  "pilot_target_per_tag": 20,
  "training_target_per_tag": 100,
  "voice_bakeoff": {
    "selected_voice_id": "string",
    "selected_voice_name": "Marcus",
    "search_query": "British gravelly narrator",
    "rejected": []
  },
  "coverage": {
    "<laugh>": {"accepted": 0, "pending": 0, "missing": true},
    "<chuckle>": {"accepted": 0, "pending": 0, "missing": true},
    "<sigh>": {"accepted": 0, "pending": 0, "missing": true},
    "<cough>": {"accepted": 0, "pending": 0, "missing": true},
    "<sniffle>": {"accepted": 0, "pending": 0, "missing": true},
    "<groan>": {"accepted": 0, "pending": 0, "missing": true},
    "<yawn>": {"accepted": 0, "pending": 0, "missing": true},
    "<gasp>": {"accepted": 0, "pending": 0, "missing": true}
  },
  "job_dir": "/mnt/storage12tb/skills/voice-segment-selector/jobs/...",
  "manifest": ".../elevenlabs_orpheus_sfx_manifest.json",
  "candidates": ".../voice_segment_selector_candidates.jsonl",
  "unsloth_handoff_dag": ".../unsloth-handoff-dag.yaml",
  "next_command": "skills/voice-segment-selector/run.sh review --job-dir ..."
}
```

## Boundaries

- This skill orchestrates; it does not own clip extraction or training code.
- `voice-segment-selector` owns candidates, review state, `tts_text`,
  `export-orpheus`, `finish-orpheus`, and receipts.
- `watch` owns movie scene evidence.
- `hum` owns voice identity/bakeoff heuristics.
- `unsloth-studio` owns downstream training/evaluation/export infrastructure
  only after an `export-orpheus` dataset receipt exists.
- `agents/orpheus-tts-trainer` hands off a bounded DAG to
  `agents/unsloth-studio`; it must not send prose-only training requests.
- Candidate review and Orpheus tag provenance stay in `voice-segment-selector`.
