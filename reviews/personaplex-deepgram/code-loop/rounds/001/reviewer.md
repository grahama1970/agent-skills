{
"verdict": "NEEDS_CHANGES",
"blocking_findings": [
{
"id": "PPX-LIVE-001",
"title": "The output gate opens before grounding tokens are consumed",
"evidence": "In personaplex_golden_state_server.py run_grounding(), every stage is only queued into injection_tokens and OutputGate.open() is then called immediately. opus_loop() consumes at most one queued token per model step. The supplied PASS summary records gate_complete_active=false while queue_depth=268.",
"impact": "At 12.5 model steps per second, 268 pending tokens represent roughly 21 seconds of uninjected context. Once the gate opens, pending internal routing, memory, and search tokens can be emitted as text or speech, and PersonaPlex can respond before the complete grounding packet is in model state. This directly violates the factual-output boundary and the few-second latency goal.",
"required_fix": "Introduce explicit LISTENING, GROUNDING, INJECTING, READY, and ERROR states. Do not open factual output until all required stages succeed and the current turn's injection queue has been consumed and acknowledged. Prefer one compact final grounding or controlled answer packet rather than queueing every intermediate stage. The E2E probe must fail if grounding_complete is emitted with a nonzero queue depth."
},
{
"id": "PPX-LIVE-002",
"title": "PersonaPlex is ungated before the first speech_final event",
"evidence": "OutputGate initializes with active=false. It is not closed until run_grounding() begins after Deepgram emits a turn. Meanwhile opus_loop() freely decodes and sends generated audio and text for incoming user frames.",
"impact": "PersonaPlex can make arbitrary backchannels or substantive claims during user speech and during Deepgram endpointing latency, before memory or Brave retrieval has started. The implementation provides no allowlist restricting this output to non-factual filler.",
"required_fix": "Start each turn in a closed listen-only state. Force assistant text to PAD and assistant audio to silence while listening and awaiting ASR finalization. Permit filler only through an exact, forced, allowlisted phrase, then return to silence until grounding is ready."
},
{
"id": "PPX-LIVE-003",
"title": "Overlapping turns share one boolean gate and one token queue",
"evidence": "deepgram_loop() starts a new run_grounding() task for every speech_final turn without serializing, superseding, or canceling the previous turn. All tasks mutate the same OutputGate and injection_tokens queue. Any completing task calls OutputGate.open().",
"impact": "Grounding packets from different turns can interleave, and the first task to finish can open output while another turn is still retrieving. A barge-in or duplicate final event can therefore expose stale facts or generate an answer for the wrong question.",
"required_fix": "Assign a monotonically increasing turn ID and allow only one authoritative grounding transaction. On a new turn, cancel and await the previous transaction, clear or version its queued tokens, and make gate transitions conditional on the matching turn ID. Add overlapping-turn and barge-in tests."
},
{
"id": "PPX-LIVE-004",
"title": "Grounding failure and evidence-case paths fail open",
"evidence": "timed_post() and brave_search() encode failures as result dictionaries, but run_grounding() does not reject stages whose result.ok is false. It opens the gate after iteration regardless of stage success. Its exception handler also opens the gate. evidence_case_gate_product() returns only a placeholder with ok=false and requires_evidence_case=true, yet the live path eventually opens normal model output without an evidence-case verdict.",
"impact": "Memory, Brave, routing, or compliance-evidence failure can release unconstrained PersonaPlex generation. The agent may hallucinate current facts or compliance conclusions precisely when authoritative evidence is unavailable.",
"required_fix": "Define required stages per intent and validate every required result before release. On failure, discard pending grounding tokens and force a fixed non-factual error or clarification response; do not enable free generation. Keep evidence-case turns gated until a real verdict and source packet exist."
},
{
"id": "PPX-LIVE-005",
"title": "Brave search invocation permits shell command injection",
"evidence": "brave_search() builds a bash -lc command string containing json.dumps(query). The query can originate from the WebSocket brave_query parameter or a memory-produced tool plan. JSON double quoting does not prevent shell expansion of command substitutions such as $() or backticks inside double quotes.",
"impact": "A crafted query can execute arbitrary shell commands with the server process's permissions. Sourcing ~/.zshrc for every request also executes unrelated shell startup code in the request path.",
"required_fix": "Invoke the Brave script directly with create_subprocess_exec(str(BRAVE_RUN), "web", query, "--count", str(count), "--json") and a preconstructed environment. Do not use bash -lc or source interactive shell configuration with request-controlled values. Add a regression test containing shell metacharacters."
},
{
"id": "PPX-LIVE-006",
"title": "ASR and session task shutdown can hang or mutate model state after lock release",
"evidence": "deepgram_loop() creates deepgram.run() as asr_task but never waits on or monitors it, then blocks indefinitely on turn_queue.get(). DeepgramLiveClient.close() can block while putting a sentinel into a full queue. Sender and ASR tasks are canceled without being awaited. The chat handler cancels opus_loop and other pending tasks but does not await their completion before leaving model_lock.",
"impact": "A Deepgram connection failure can leave the session waiting forever. A canceled opus_loop may still be completing synchronous GPU work when model_lock is released, allowing the next session to restore golden state concurrently with stale model operations and corrupt shared streaming state.",
"required_fix": "Use structured concurrency or an asyncio.TaskGroup. Propagate ASR task completion and errors, use a nonblocking shutdown signal, cancel and await every child and retrieval task, and do not release model_lock until the model-owner loop has terminated. Add disconnect, ASR failure, full-queue shutdown, and repeated-session isolation tests."
},
{
"id": "PPX-LIVE-007",
"title": "Deepgram backpressure silently discards user audio",
"evidence": "DeepgramLiveClient.enqueue_pcm() removes the oldest PCM frame whenever its queue is full and records no drop count or turn-invalid state.",
"impact": "PersonaPlex may hear the complete utterance while Deepgram transcribes a truncated one. Grounding can then be performed for a materially different question with no observable failure, undermining the factual authority boundary.",
"required_fix": "Track dropped frames and latency. Apply bounded backpressure or terminate the affected ASR turn as invalid. Never route a transcript to memory or search after audio loss without an explicit fail-closed recovery."
},
{
"id": "PPX-LIVE-008",
"title": "The live proof harness has a false-positive PASS condition",
"evidence": "personaplex_deepgram_live_probe.py defines success only as the presence of asr_turn_final, grounding_started, and grounding_complete events. It does not require successful stages, memory-before-search behavior, zero pending tokens, absence of early text/audio, valid post-grounding speech, decodable non-silent server audio, or absence of chat_loop_error. The supplied PASS summary itself reports queue_depth=268 at gate release.",
"impact": "The probe reports PASS for the exact unsafe state the acceptance contract is intended to reject. Consequently, the supplied E2E evidence cannot support implementation-readiness claims.",
"required_fix": "Make the probe assert the full state timeline: no non-allowlisted output before READY, speech_final is the sole trigger, required stages succeed, conditional Brave behavior is correct, the active turn queue drains to zero before release, no error events occur, and post-release audio/text are valid. Decode and inspect the returned Opus stream."
},
{
"id": "PPX-LIVE-009",
"title": "Brave is run unconditionally and may inject an unrelated default query",
"evidence": "iter_research_stages() always creates both memory and brave tasks after intent. planned_brave_query() falls back to the server's Hawaii-weather query when the intent contains no Brave tool call.",
"impact": "Persona-only or unrelated turns incur external search and may receive irrelevant Hawaii facts. This contradicts the documented contract that Brave runs only for intents requiring current external facts and can contaminate the final response.",
"required_fix": "Derive a required_search flag from the validated intent plan. Skip Brave entirely when current facts are not required. Record dispatch order and required-stage selection in the turn receipt."
},
{
"id": "PPX-LIVE-010",
"title": "The grounded-speech proof endpoint can bypass grounding and write to arbitrary paths",
"evidence": "grounded_speech_endpoint() accepts a caller-supplied script that replaces the research-generated script, accepts an unrestricted output_dir, and still marks the receipt ok from research status plus WAV size.",
"impact": "A caller can produce arbitrary unsupported speech under a grounded-speech receipt and can direct file creation outside the configured artifact root. This breaks the evidence authority boundary and creates a filesystem-write risk if the server is exposed.",
"required_fix": "Remove the script override from the production endpoint or mark it as a separate explicitly ungrounded test route. Resolve outputs beneath a fixed root, reject path escapes, and require authentication and request limits before binding beyond loopback."
}
],
"conditions": [
"The direct asynchronous Deepgram integration is an acceptable architecture; a separate ASR microservice is not required by the supplied evidence.",
"Use a single model-owner loop and explicit per-turn state machine rather than allowing grounding tasks to manipulate a shared boolean gate directly.",
"A turn may release factual speech only after validated source-bearing stages for that exact turn are complete and any context or controlled-answer tokens have been consumed.",
"Browser microphone work should begin only after the synthesized Opus probe detects early-output, failure, overlap, shutdown, and queue-drain regressions.",
"Keep the stock PersonaPlex container restoration check as a mandatory cleanup step, with raw before-and-after process evidence."
],
"notes": [
"The implementation correctly triggers transcript turns only on speech_final rather than partial is_final events.",
"The live GPU encode, LM step, and decode path is enclosed in torch.no_grad(), addressing the previously observed gradient-to-NumPy failure.",
"Incoming Opus is decoded once and the resulting PCM is fanned out to PersonaPlex and Deepgram, which is the right integration boundary.",
"The probe clearly labels its input as synthesized speech rather than microphone capture.",
"The reported fast golden-state restore and successful Deepgram transcription are useful spike evidence, but they do not overcome the gate and verifier defects above.",
"Because the bundle contains definitive static false-green and security defects, NEEDS_CHANGES is appropriate even though several raw runtime artifacts are missing."
],
"missing_evidence": [
"The full personaplex-deepgram-live-probe-receipt.json rather than only its path and summary.",
"The raw deepgram-live-events.jsonl timeline.",
"Wrapper stdout and stderr covering startup, the complete session, task shutdown, and process exit.",
"Raw command transcript and exit code for the live probe.",
"Raw docker or process output proving the stock container was restored.",
"Decoded server audio, its duration and non-silence metrics, and an ASR transcript of any emitted agent speech.",
"An assertion timeline proving no non-allowlisted text or audio was emitted before the gate became safe.",
"Tests for two overlapping speech_final turns, barge-in, grounding failure, evidence-case routing, Deepgram disconnect, queue overflow, client disconnect, repeated sessions, and shell-metacharacter queries.",
"GPU memory measurements across repeated connect, disconnect, and golden-state restore cycles.",
"A browser microphone and real browser Opus capture remains required for the later live-UI gate, but not for resolving the current code blockers."
],
"non_blocking_followups": [
"Reuse a long-lived aiohttp ClientSession for memory calls instead of constructing one for every stage.",
"Add transcript-segment IDs or timing-based deduplication for repeated Deepgram final results.",
"Record Deepgram queue depth, dropped-frame count, websocket reconnect count, and ASR latency as structured metrics.",
"Replace hardcoded repository, Python, model, and storage paths with validated configuration.",
"Add request-size, session-duration, and rate limits before allowing non-loopback binding.",
"Measure model real-time factor while Deepgram, memory, and Brave operate concurrently.",
"Compress grounding to a small evidence packet or externally composed answer so 12.5 Hz token injection does not reintroduce multi-second latency."
],
"prompt_improvement": {
"clarity_issues": [
"The outer required verdict enum is PASS, NEEDS_CHANGES, BLOCKED, or INSUFFICIENT_EVIDENCE, while context.md requests satisfied, needs_changes, blocked, or insufficient_evidence.",
"The requested gate alternates between safe to continue browser testing, merge readiness, production readiness, and deterministic closure; these are different thresholds.",
"Grounding complete is not defined precisely: retrieval completion, route success, tokens queued, tokens consumed, or model-ready state could each be meant.",
"Mask generated speech and text is ambiguous about whether only network output is suppressed or whether ungrounded tokens must also be prevented from entering the LM history.",
"Memory first is ambiguous between calling /intent first, dispatching /recall before Brave, or waiting for recall completion before starting Brave.",
"The bundle references host-local receipts, logs, screenshots, and events but does not include their raw contents in the zip."
],
"missing_evidence_requirements": [
"Require attachment of raw receipt, events JSONL, server logs, command transcript, exit status, and decoded output-audio metrics.",
"Define the exact allowed output before grounding, including the literal filler phrases and whether any model-generated backchannel is permitted.",
"Define required versus optional grounding stages for each intent class and the required failure behavior.",
"Require a turn-state timeline containing turn IDs, gate transitions, queue depth, stage status, and output timestamps.",
"Require repeated-session and overlapping-turn tests because one shared LMGen instance is being restored and mutated."
],
"blocking_threshold_improvements": [
"State that opening output with pending grounding tokens is a blocking false-green.",
"State that any free model output before speech_final and grounding completion is blocking unless it is an exact allowlisted filler.",
"State that stage failure may release only a forced non-factual failure response, never unconstrained model generation.",
"State that shell execution involving user- or model-controlled queries is blocking.",
"State that the probe must fail on nonzero queue depth, early output, failed stages, dropped ASR audio, or leaked tasks.",
"Separate the synthesized-Opus integration gate from the later browser-microphone gate and from production publication."
],
"improved_request": "Review only the supplied Deepgram-to-PersonaPlex synthesized-Opus integration phase. The phase may pass without a browser microphone, but PASS requires attached raw logs and a probe that proves: speech_final is the sole turn trigger; no output other than an exact allowlisted filler occurs before grounding; memory and any intent-required Brave stage succeed; grounding tokens for the active turn are fully consumed before output opens; overlapping turns cannot interleave; ASR loss or failure is fail-closed; all child tasks terminate before model-state reuse; and returned audio/text are valid. Treat command injection, premature gate release, cross-turn contamination, stale tasks, and a verifier that ignores these conditions as blocking NEEDS_CHANGES."
},
"completion_marker": "browser_transport_marker_will_follow"
}
<<<WEBGPT_DONE:20260622T215611Z:055f7915>>>
