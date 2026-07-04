# Embry Response QRA Memory

Use this reference when a Chatterbox Embry agent speaks answers from existing
QRA records.

## Source Of Truth

Keep factual QRA content separate from voice delivery.

```text
sparta_qra / lessons_v2 QRA record
  -> factual question, answer, evidence, tags

persona_response_qra overlay
  -> persona-specific phrasing, emotion, pauses, and latency behavior

persona_pronunciation_lexicon overlay
  -> reusable spoken forms for acronyms, control IDs, names, and local jargon
```

Do not write Embry speech into canonical `sparta_qra` as the first design. A
SPARTA QRA is shared factual/evidence material. Embry speech is presentation
state that can change by conversation context.

## Recommended Collection

Use Memory `/store` or `/upsert` only. Do not write ArangoDB directly. Do not
store embedding vectors in the document; Memory semantic sync owns embeddings.

Recommended collection:

```text
persona_response_qra
```

Recommended companion collection:

```text
persona_pronunciation_lexicon
```

Record shape:

```json
{
  "_key": "persona_response_qra:embry:<qra_key>:<style_hash>",
  "schema": "persona_response_qra.v1",
  "persona_id": "embry",
  "source_qra": {
    "collection": "sparta_qra",
    "key": "conv_stress_...",
    "question_sha256": "...",
    "answer_sha256": "..."
  },
  "question": "What SPARTA controls are designed to detect...",
  "factual_answer": "Regarding SI-16...",
  "spoken_answer": "Regarding SI-16, the relevant control is Service Stop...",
  "delivery": {
    "tone": "calm_precise",
    "emotion": ["focused"],
    "pace": "measured",
    "pause_strategy": "short_answer_no_filler",
    "allowed_fillers": ["Hmm.", "Let me check.", "I have the answer."],
    "chatterbox_tags": [],
    "max_dead_air_ms": 3000
  },
  "routing": {
    "preferred_route": "memory_direct",
    "fallback_route": "fast_style_model",
    "expensive_route": "gpt55_medium"
  },
  "context_policy": {
    "use_when": ["qra_exact_match", "qra_high_confidence"],
    "avoid_when": ["ambiguous_user_question", "multi_qra_synthesis", "stale_or_conflicting_qra"]
  },
  "receipts": {
    "created_from": "receipts/...",
    "last_audio_receipt": "receipts/..."
  },
  "tags": ["persona:embry", "response_qra", "source:sparta_qra", "emotion:focused"],
  "semantic_sync_state": "pending"
}
```

## Dynamic Speech Policy

The voice coordinator can choose speech dynamically from the QRA and current
latency state:

```text
0-700 ms:
  no filler; answer if memory_direct is ready

700 ms-2 s:
  "Hmm." or "Let me check."

2-5 s:
  "I have the answer. I'll keep it tight."

5+ s:
  "Still with you. I'm checking one more thing."
```

For exact QRA matches, prefer:

```text
memory.answer direct
  -> optional deterministic cleanup of QRA prefixes
  -> Chatterbox exact-text speech
```

Use a fast/local style model only when the QRA answer is too written, too long,
or contains source prefixes that need spoken phrasing. Use GPT-5.5 medium only
for ambiguous user questions, conflicting QRA rows, multi-QRA synthesis, or
clarify/deflect decisions.

## Why Not A `sparta_qra.embry_speech` Field First

A field on `sparta_qra` can be useful later for cached production delivery, but
it couples a shared factual artifact to one persona and one delivery state. It
also makes dynamic latency behavior harder because the best spoken text can
change depending on whether Embry is answering immediately, recovering from a
long wait, or redirecting after interruption.

If a field is added later, keep it as cache metadata rather than source truth:

```json
{
  "persona_speech_cache": {
    "embry": {
      "default_spoken_answer_key": "persona_response_qra:embry:...",
      "last_receipt": "receipts/..."
    }
  }
}
```

The overlay record remains the inspectable source for emotion, pauses, and
speech receipts.

## Pronunciation Lexicon

Store reusable pronunciation rules outside canonical QRA records. The QRA keeps
the factual anchor; the lexicon tells Embry how to say it.

Use Memory `/store` or `/upsert` only.

Example record:

```json
{
  "_key": "persona_pronunciation_lexicon:embry:SI-16",
  "schema": "persona_pronunciation_lexicon.v1",
  "persona_id": "embry",
  "anchor": "SI-16",
  "anchor_type": "nist_control",
  "long_form": "Memory Protection",
  "spoken_form": "Memory Protection, the System and Information Integrity sixteen control",
  "spoken_preference": "control_name_then_family",
  "fallback_phonetic": "ess eye sixteen",
  "avoid_spoken_forms": ["S I sixteen"],
  "source": {
    "collection": "sparta_qra",
    "key": null,
    "authority": "memory.intent entity extraction or reviewed SPARTA control metadata"
  },
  "tags": ["persona:embry", "pronunciation", "sparta", "control-family:SI"],
  "semantic_sync_state": "pending"
}
```

Runtime policy:

```text
1. Use `memory.intent` / entity extraction long forms when available.
2. Use `persona_pronunciation_lexicon` for known acronyms and IDs.
3. Prefer human-readable control names in speech.
4. Keep raw IDs in receipt metadata for traceability.
5. Use phonetic spelling only when no long form or control name exists.
```

Receipt JSON should include the exact map used:

```json
{
  "anchor_spoken_map": {
    "SI-16": "Memory Protection, the System and Information Integrity sixteen control"
  },
  "pronunciation_policy_used": {
    "SI-16": "control_name_then_family"
  }
}
```
