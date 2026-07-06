# Async Voice Coordinator

Use this reference when implementing or reviewing Chatterbox voice-agent code.

## Architecture

```text
turn manager
  -> skill orchestrator
      -> asyncio task batch
      -> result queue
  -> voice coordinator
      -> speech queue
      -> Chatterbox worker
      -> playback
```

The orchestrator runs work. The coordinator decides what is worth saying. The
TTS queue renders exact text. These responsibilities must stay separate.

## JSON Event Stream

Every turn should emit newline-delimited JSON or SSE-compatible events:

```json
{"type":"turn.started","turn_id":"turn-42","conversation_id":"embry-live"}
{"type":"skill.started","turn_id":"turn-42","skill":"memory.intent"}
{"type":"skill.result","turn_id":"turn-42","skill":"memory.recall","ok":true}
{"type":"speech.queued","turn_id":"turn-42","chunk_id":"hold-1","text_sha256":"..."}
{"type":"tts.submitted","turn_id":"turn-42","chunk_id":"hold-1","audio_path":"..."}
{"type":"interruption.requested","old_turn_id":"turn-42","new_turn_id":"turn-43"}
{"type":"speech.stale_skipped","turn_id":"turn-42","chunk_id":"answer-2"}
{"type":"turn.final","turn_id":"turn-43","ok":true}
```

Required fields for operational events:

```text
type
turn_id
conversation_id
sequence
phase
status
timestamp
artifact_path or null
text_sha256 or null
```

## Skill Batch Pattern

Use `asyncio.as_completed()` for backend results, not direct speech.

```python
async def run_skill_batch(turn_id, skills, result_queue, cancel_event, max_concurrency=4):
    sem = asyncio.Semaphore(max_concurrency)

    async def wrapped(name, factory):
        async with sem:
            if cancel_event.is_set():
                raise asyncio.CancelledError()
            result = await run_skill(name, factory)
            return name, result

    tasks = [
        asyncio.create_task(wrapped(name, factory), name=f"{turn_id}:{name}")
        for name, factory in skills.items()
    ]

    try:
        for completed in asyncio.as_completed(tasks):
            if cancel_event.is_set():
                break
            name, result = await completed
            await result_queue.put({
                "type": "skill.result",
                "turn_id": turn_id,
                "skill": name,
                "result": result,
            })
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await result_queue.put({"type": "batch.done", "turn_id": turn_id})
```

For Python 3.11/3.12 compatibility, wrap tasks so they return `(name, result)`.
Python 3.13+ can also use `as_completed()` as an async iterator that preserves
correlation with original tasks.

## Voice Coordinator Rules

The coordinator consumes result events and decides when to speak:

```text
as_completed result
  -> normalize
  -> update state
  -> score importance
  -> debounce
  -> speak short progress or wait
```

Speak when:

- silence would feel broken;
- pending work would otherwise create 3 seconds of perceived dead air;
- a critical result is found;
- a slow step needs a holding update;
- a fallback path starts;
- a useful partial answer exists;
- the final answer is ready.

Do not speak when:

- low-value internal tasks finish;
- several events arrive rapidly;
- the user is talking;
- the update would not change the user's understanding.

The coordinator should maintain a `last_audible_at` or equivalent playback
marker. Backend events are not audible proof. If the audio queue is empty or
about to become empty while tasks are still pending, queue a short low-buffer
filler before the user hears three seconds of silence.

## TTS Queue

All speech goes through a cancellable queue:

```python
async def tts_worker(speech_queue, current_turn):
    while True:
        item = await speech_queue.get()

        if item["type"] == "cancel":
            await stop_audio_now()
            await clear_audio_buffer()
            continue

        if item["turn_id"] != current_turn.id:
            emit({"type": "speech.stale_skipped", "chunk_id": item["chunk_id"]})
            continue

        if item["type"] == "speak":
            await synthesize_and_play_exact_text(item)
```

Record `text_sha256` before submitting to TTS and verify the submitted text hash
matches the approved chunk text hash.

## Python Requirements

Follow `best-practices-python`:

- Use `httpx.AsyncClient` for provider calls.
- Use Loguru for logs.
- Use Typer for CLIs.
- Keep business logic in functions, not `__init__.py`.
- Do not call `subprocess.run()` in async code.
- Do not swallow `asyncio.CancelledError`.
- Include non-mocked sanity tests for live/local worker paths.
