# Watch Skill: Project Knowledge

## Architecture

- **CLI:** Typer via `run.sh`/`scripts/cli.py`; `scripts/watch.py` is importable pipeline logic
- **Two memory layers:**
  - `watch_content` — per-scene rows with timecode, SRT text, Whisper text, visual descriptions, divergence category, persona tag
  - `persona_memory` — "Embry watched Movie Title" record with `persona_id`, `answer_text`, `retrieval_text`, `watch_history` tag
- **Whisper:** Dedicated Docker container `hwdsl2/whisper-server:cuda` on port 9000 (GPU-accelerated). Falls back to local faster-whisper on CPU only when Docker is unreachable.

## Real-Time Entity Tracking Direction

- **Strategic purpose:** Watch is the test bed for managing many evidence streams in an area of operations. Movies are the controlled canary; the destination includes drone, telemetry, industrial, web, RTSP, and other streamed evidence sources.
- **Core boundary:** live ML tracking is streamed to the player/table, while `$memory` stores bounded segment observations, domain entities, graph edges, Qdrant pointers, overlays, and evidence cases. Do not write every frame to memory.
- **Initial ML stack:** use Ultralytics YOLO for person/object detection, ByteTrack or DeepSORT for stable track IDs, OpenCV for media I/O/sampling/overlay, and optional face/person re-identification embeddings for character candidates.
- **Domain hydration:** use `$brave-search` to seed movie-domain actor/character priors such as `Tony Cox -> Marcus` and `Billy Bob Thornton -> Willie`. Brave/domain memory can corroborate public cast facts, but cannot override extracted frame/clip/transcript evidence.
- **Default reference policy by stream type:** cinema/movie ingest should automatically run cast/domain/reference-source hydration before extraction/tracking so the tracker has a reference pool available. Drone, RTSP, YouTube, and ITAR/industrial streams may receive their reference package from a mission manifest, asset registry, operator annotations, or channel metadata; only fall back to web/domain search when the source package is missing.
- **Persistence contract:** Qdrant/Jina multimodal embeddings store vectors for representative frames, crops, transcript chunks, and audio/text evidence. Arango/memory stores metadata, source pointers, graph edges, and case/overlay records.
- **Case trigger:** create `watch_evidence_cases` only when a claim needs durable anchoring, such as visual-track/SRT/Whisper/domain conflicts, telemetry-vs-visual mismatches, operator isolate actions, or unresolved identity evidence.
- **Chat UX:** the `$memory` pipeline belongs in Watch Agent dynamic thinking/status, not in the Library ingest panel. Expected stages are `/intent`, `extract entities`, `/recall`, `create evidence case` when needed, and `/answer | /clarify | /deflect`.
- **Current contract artifacts:** `docs/architecture/watch_realtime_character_tracking_contract.md` records the candidate architecture; `docs/architecture/watch_realtime_tracking_execution_plan.md` records the execution sequence from domain seed to live tracker proof to memory/Qdrant recall; `docs/architecture/watch_track_observations.schema.json` and `docs/architecture/watch_track_observation.bad_santa_marcus.sample.json` define the first bounded track-observation canary. `docs/architecture/watch_realtime_character_tracking_inspection.md` remains `REVISE` until memory upsert/recall proof and a live playback tracker log exist.
- **Dry-run memory plan:** `docs/architecture/watch_realtime_tracking_memory_upsert_manifest.bad_santa_marcus.json` is the first accepted dry-run manifest for the Bad Santa Marcus canary. It prepares one movie-domain entity, one bounded track observation, one evidence case, three graph edges, Qdrant pointer metadata, rollback keys, and recall-proof queries without executing memory or vector writes.
- **Tracker event fixture:** `docs/architecture/watch_tracker_event_log.bad_santa_marcus.fixture.jsonl` is the first accepted deterministic live-event fixture. It contains three provisional `watch.live_track_update.v1` events for `track_07` over 02:48-03:12 and feeds the dry-run manifest without claiming live YOLO/ByteTrack runtime proof.
- **Text/scene corroboration gate:** `docs/architecture/generated/bad_santa_marcus_0248_text_scene_corroboration_receipt_plan/watch_text_scene_corroboration_receipt_plan.bad_santa_marcus.json` records the current row-text gap for the Marcus canary: `0/4` materialized text channels and status `BLOCKED_PENDING_ROW_TEXT_MATERIALIZATION`. A case claim or Brave/movie-domain prior cannot promote identity without materialized scene/SRT/Whisper/VLM text plus `$memory recall` over `items`.
- **Row text materialization gate:** `docs/architecture/generated/bad_santa_marcus_0248_row_text_materialization_receipt_plan/watch_row_text_materialization_receipt_plan.bad_santa_marcus.json` records the exact source-read contract for the Marcus row. It currently has 3 planned reads (`visual_description` serving scene marker/VLM and `whisper_text`) and 1 blocked channel (`srt_text` has no source ref). It proves source refs are named, not that the row text has been read, hashed, span-extracted, recalled, or used to support identity.
- **Dry-run upsert payloads:** `scripts/build_realtime_tracking_upsert_payloads.py` reads the accepted manifest plus tracker JSONL fixture and emits concrete `/upsert` request bodies under `docs/architecture/generated/bad_santa_marcus_0248_upsert_payloads/` without posting. This proves payload shape only; live memory writes and recall remain gated.
- **Frame-backed event harness:** `scripts/build_realtime_tracking_event_log.py` reads the accepted manifest frame and emits schema-valid `watch.live_track_update.v1` JSONL under `docs/architecture/generated/bad_santa_marcus_0248_tracker_events/`. It is deterministic harness output, not YOLO/ByteTrack or identity proof.
- **UI overlay payload adapter:** `scripts/build_tracking_overlay_payload.py` converts validated `watch.live_track_update.v1` JSONL into a browser/modal overlay payload under `docs/architecture/generated/bad_santa_marcus_0248_overlay_payload/`. `docs/architecture/watch_ui_overlay_payload.schema.json` and `scripts/validate_watch_overlay_payload.py` enforce the geometry/proof-scope contract. This proves event-derived geometry plumbing only; it does not prove live ML, identity, memory writes, Qdrant writes, or recall.
- **Local UI consumption inspection:** `docs/architecture/watch_ui_overlay_payload_consumption.inspection.md` records a local UX Lab proof that the Watch modal can render one event-derived overlay for the 02:48 Marcus dry-run payload and fail closed for a non-matching clip. This is still dry-run geometry plumbing, not live tracking or identity proof. The local app file was not committed from that inspection because the `pi-mono` Watch component already had broad unrelated dirty edits.
- **YOLO/ByteTrack adapter:** `scripts/track_yolo_bytetrack.py` maps Ultralytics `model.track(..., tracker="bytetrack.yaml", stream=True)` output into the same `watch.live_track_update.v1` JSONL contract. The Watch canary defaults to `--sample-fps 5`, computes a source-frame stride, and passes it to Ultralytics `vid_stride` so live checks have a bounded cadence before memory summarization. `ultralytics`, OpenCV, and ByteTrack's `lap` dependency are provided through the `tracking` extra in `pyproject.toml`. Local inspection now proves a bounded live YOLO/ByteTrack run emitted 80 schema-valid provisional events for the Bad Santa Marcus clip; it still does not prove character identity, UI real-time overlay updates, memory/Qdrant writes, or `/memory recall`.
- **Live YOLO overlay payload:** `docs/architecture/generated/bad_santa_marcus_0248_yolo_overlay_payload/` converts the 80 live YOLO/ByteTrack events into 10 schema-valid browser overlay records. This proves live event geometry can feed the overlay contract without hard-coded boxes. It also exposes the current identity gap: all tracks carry the same provisional `Marcus` domain candidate, so UI labels must remain provisional until re-identification, frame evidence, transcript evidence, or human review supports a specific character.
- **Track crop and identity gate:** `scripts/extract_tracking_crops.py` extracts 10 representative PNG crops from the live-YOLO-derived overlay boxes for `segment_0007`. `scripts/verify_tracking_identity.py` consumes the overlay payload plus crop manifest and reports 0 supported identities / 10 inconclusive identities. The crops prove image availability only; they do not identify Marcus, Willie, or any other character until per-track re-ID, crop embeddings, transcript/frame binding, or human approval is added.
- **Identity reference manifest:** `scripts/build_identity_reference_manifest.py` links extracted track crops to public reference-source candidates without approving identity. The current Bad Santa canary records 3 Brave Search queries / 15 raw results, and the Marcus manifest links 2 query groups / 10 candidate URLs to 10 review crops. Approved reference images, Qdrant/Jina embeddings, memory writes, and `/memory recall` are still not proven.
- **Reference embedding receipt plan:** `scripts/build_watch_reference_embedding_receipt_plan.py` converts the Marcus identity-reference manifest into explicit positive/negative reference-image slots and planned `watch_reference_image_embeddings` Qdrant points. The canary has 1 entity, 6 planned reference slots, 0 approved references, and remains `PLANNED_NOT_WRITTEN`; it proves receipt shape only, not image download, approval, embedding, Qdrant writes, crop/reference similarity, recall, or real-time UI tracking.
- **Crop/reference similarity receipt plan:** `scripts/build_watch_crop_reference_similarity_receipt_plan.py` pairs 10 tracker crops with 3 positive and 3 negative planned reference slots for Marcus, yielding 60 planned comparison receipts. It is still `PLANNED_NOT_RUN` and proves only the comparison receipt shape; no similarity scores, text/scene corroboration, memory recall, supported identity, or real-time annotation tracking are proven.
- **Brave Search seed artifact:** `docs/architecture/generated/bad_santa_domain_seed/brave_bad_santa_cast_search.json` is a raw bounded Brave Search result set for the Bad Santa cast canary. `docs/architecture/generated/bad_santa_domain_seed/inspection.md` accepts it only as domain prior evidence, never as proof that a character appears in a Watch segment.

## Subtitle Sourcing

**Correctness hierarchy:**

1. **Embedded text subs (subrip/ASS/SSA)** — extracted directly from the MKV via `extract_subtitles()` — guaranteed timing match with the exact encode
2. **Embedded PGS (BluRay image subs)** — OCR is too slow (~50h per movie) → Whisper-only, no SRT
3. **Third-party SRT downloads (OpenSubtitles/Bazarr)** — unreliable timing, different cuts, NOT used

The pipeline auto-extracts subtitles from the MKV when no `--subtitle` flag is given:

```
if not sub_path and video has embedded subrip stream:
    extract_subtitles(video)
    use extracted SRT
elif not sub_path:
    Whisper-only, no SRT divergence
```

## SRT vs Whisper: Complementary, Not Competing

| Layer | Source | Contains |
|-------|--------|----------|
| **SRT** | Official script | Dialogue + `(SIGHS)`, `Willie:`, `(EXPLOSIONS)` |
| **Whisper** | Raw audio transcription | Verbatim speech, ad-libs, background chatter |

They describe different things by nature. Divergence only flags semantically meaningful gaps:

| Flag | Condition | Example |
|------|-----------|---------|
| `hidden_dialogue` | Whisper caught speech SRT omitted | SRT: `(PEOPLE CHATTERING)` → Whisper: "I've got my eyes on you" |
| `sanitized` | SRT cleaned profanity | SRT: `Oh, my.` → Whisper: `Oh my fucking god.` |
| `acoustic_context` | SRT has audio cue, Whisper no speech | SRT: `(EXPLOSIONS)` → Whisper: empty |

No generic similarity ratio. No `unknown_diff` or `minor_diff` noise. Memory `answer` field stores both:
```
SRT: Start talking. I'm not sure if we're on the air.
Whisper: Start talking, I am not sure if we are on the air.
```

## Scene Detection

Two-pass approach (no `-frames:v` limit that caused partial coverage):

1. ffmpeg `select='gt(scene,0.3)'` detects all scene changes across the entire video
2. Results subsampled evenly to `--max-frames` if more than budget

Covers the full movie. Frame budget defaults to 150 (capped at 500).

## Whisper Docker

```bash
docker run --name whisper --restart=always --gpus=all \
  -v whisper-data:/var/lib/whisper \
  -p 9000:9000 \
  -e WHISPER_MODEL=base \
  -e WHISPER_DEVICE=cuda \
  -d hwdsl2/whisper-server:cuda
```

OpenAI-compatible API at `POST /v1/audio/transcriptions`. API key auto-generated on first start:
```bash
docker exec whisper whisper_manage --showkey
```

The pipeline reads `WHISPER_API_KEY` and `WHISPER_API_URL` from environment.

## Bazarr

Configured with OpenSubtitles credentials and Radarr integration via runtime secrets. Use `BAZARR_API_KEY` or the local Bazarr secret store; do not commit plaintext keys. The config path is environment-specific and must not contain committed credentials.

Bazarr is NOT used as a subtitle source for watch — only for Orpheus TTS dataset curation. Third-party SRTs have unreliable timing vs specific encodes.

## Divergence Intelligence UI

Located at `localhost:3002/#watch` (ux-lab). Features:

- **Divergence Chips** — `[!] SANITIZED` (amber), `[+] HIDDEN` (purple), `[?] OCCLUDED` (teal), `[~] MINOR DIFF` (gray)
- **Cyber-Glass styling** — backdrop-filter blur, box-shadow glow, hover transitions
- **Show Divergences Only toggle** — filters to rows with diffs
- **Forensic Summary sidebar** — category counts, clickable chips, takeaways
- **Character Truth** — extracted from SRT `Name:` colon prefixes, enriched with actor names via Wikipedia API
- **Diff-Hover tooltip** — detailed explanation on chip hover
- **Watch Agent tab** — chat interface backed by `/recall` on `watch_content`
- **Annotation tab** — Orpheus clip candidate, emotion tags, export workflow

## Character Intelligence

Characters extracted from SRT `Name: dialogue` patterns (zero hardcoded logic). Actor names looked up via Wikipedia API:

```
Wikipedia parse API → <li>Actor</a> as Character</li> → match via prefix + alias map
```

Aliases: `grandma`→`Granny`, `kid`→`Thurman Merman`, `santa`→`Willie T. Soke`

## Cast Lookup

`_fetch_cast_map(title)` queries Wikipedia's `action=parse` API for the Cast section, extracts `Actor as Character` pairs, and injects actor names into `diff_intelligence.character_intel[]`.

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| `question`/`reasoning`/`answer` not `problem`/`solution` | QRA format enables structured recall alongside SPARTA QRA |
| `include_edges=False` | `lesson_edges` doesn't exist — AQL crashes |
| Watch-owned upsert | Watch upserts only its own `watch_content` records; memory promotion is out of scope |
| `answer` field stores both SRT + Whisper | So `/recall` returns both, agent decides which to trust |
| No `-frames:v` limit in scene detection | Without limit, ffmpeg detects all scene changes across full duration; subsampled afterward |
| Three divergence types only | SRT and Whisper naturally describe different things — only flag when one captures something the other structurally cannot |
| PGS OCR not attempted | ffmpeg overlay + tesseract is too slow (~2s per subtitle event × 3000 = ~100min) |
| SRT extracted from MKV, not downloaded | Third-party SRTs have unreliable timing vs specific encodes |
| `--persona` flag tags records | Enables persona-specific recall filtering |

## E2E Sanity

`sanity.sh` section 14 verifies persona watch records are recallable from `persona_memory`. Standalone `e2e_sanity.py` runs the full pipeline on Bad Santa clip + YouTube, verifying memory writes.

## Embry-Ingested Movies

| Movie | Scenes | Divergence | Notable |
|-------|--------|------------|---------|
| Bad Santa (2003) | 30 | 67% (no Whisper) | 5 sanitized, 2 characters |
| Sicario (2015) | 20 | 75% | 4 hidden dialogue, 1 sanitized |
| Edge of Tomorrow (2014) | 400 | 26% | 97 hidden dialogue, 3 sanitized |
| Gore. - Lead Me To the Slaughter (YouTube) | 10 | — | Music video |

## Current Understanding

- 2026-07-01: Watch row 5 character annotation workflow now treats human keyframes as durable identity seeds. Visible keyframes are stored in memory collection watch_keyframe_annotations with movie_metadata, actor_metadata, interpolation metadata, scene_context_refs, training_role, detector links when available, and qdrant_refs pointing to watch_track_crop_embeddings_jina_v5_1024; raw vectors stay in Qdrant, not Arango. Runtime interpolation/hold is computed in the Watch UI and offscreen stop markers end a character scan without deleting earlier keyframes. Delete/Backspace on a held/interpolated visible box should insert an offscreen stop at the playhead; exact keyframe deletion marks that keyframe deleted. Evidence from row 5 Bad Santa check: memory HTTP /list returned 8 active row 5 Willie docs, 6 visible keyframes, 2 offscreen stop markers, and 6 visible keyframes with Qdrant crop pointers; live Watch UI rehydrated 8 saved boxes from memory.
- 2026-07-07: Watch world-model architecture: YOLOAnalytics supplies detector boxes/tracks only; Watch owns temporal identity sequences, unassign/stop control points, interpolation between explicit labels, Qdrant/Memory crop recall, readiness counters, and escalation to Tau for deeper sequence analysis. Qdrant/Memory suggestions are tentative evidence, not accepted truth, until a human or accepted policy confirms them. For high-risk streaming domains, Watch should write durable evidence records and confidence-scored recommendations for human review, not targeting or autonomous engagement decisions.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-07-07 | Watch owns second-stage identity/world-model state over YOLOAnalytics detections | YOLOAnalytics does not know domain identity; Watch must persist keyframe/stop sequences, use Memory/Qdrant for recall, and invoke Tau only when sequence-level reasoning is needed. |
| 2026-07-18 | The 02:48 Marcus canary chain was executed live end-to-end and the claim was REFUTED | Row text materialized 4/4 channels with zero Marcus mentions; live crop/reference similarity (10 crops x 10 approved external references) scored every track higher against Willie; true-window frame extraction shows Willie bar + alley title walk. Evidence case `WEC-BADSANTAMARCUS0248` filed live with `ARTIFACT_WINDOW_MISALIGNMENT`. A refuted canary is the intended fail-closed outcome, not a failure of the gate design. |
| 2026-07-18 | Persisted clip/audio artifacts must be window-validated, not index-trusted | `storage.generate_playable_segments` reused stale clips by index across runs with different sampling (root cause of the misalignment). It now writes `segments_manifest.json` and force-regenerates on window mismatch. Pre-fix rows are suspect until re-run. |
| 2026-07-18 | Reference images live in the reference lane with visual review receipts | 6 Marcus + 4 Willie external references approved (2 rejected: wrong character / mixed-entity image); the earlier circular canary manifest that approved Watch's own tracker crops as Marcus references is superseded. Reference artifacts stored under `generated/watch_reference_image_receipts/<run>/` rot if the run dir is deleted — the 2026-06-29 Willie artifacts were lost this way and were re-downloaded. |

## Live Canary Receipts (2026-07-18)

- Row text materialization + corroboration: `generated/bad_santa_marcus_0248_row_text_receipts/`
- Approved reference manifest (Marcus+Willie, supersedes circular canary): `generated/bad_santa_marcus_0248_approved_reference_manifest_live/`
- Live identity loop (crop embeddings, similarity, memory upserts, recall): `generated/watch_realtime_identity_memory_loop_live_20260718/`
- Evidence case filing + true-window frame check: `generated/bad_santa_marcus_0248_evidence_case_live/`
- Recall canary (natural question, alias, case lookup): `generated/bad_santa_marcus_recall_canary_20260718/`

Known hygiene debt: `watch_track_crop_embeddings_jina_v5_1024` contains smoke-test
debris points with `codex-live-*` character labels written by UI test runs against
the live Qdrant collection; tests should target an isolated collection, and the
debris should be purged before similarity stats are computed over the collection.

## Streaming Gate (WebGPT 3-round assessment, 2026-07-18)

Bundles/responses: `.codex/webgpt-watch-streaming-assess/round{1,2,3}-bundle*`
(tab 837359319, all routing proofs clean). Final ruling: PASS on the
consolidated state; streaming lane stays BLOCKED until P0A lands.

- **Current gate: `SOURCE_SESSION_JOURNAL_PREFLIGHT_P0A`** (recorded-file
  canary, no live source): shared immutable journal module — tracker adapter
  (`track_yolo_bytetrack.py`) is the only append writer, persistence loop
  (`run_realtime_identity_memory_loop.py`) is a read-only consumer. Session
  header binds source hash, model/tracker config, confidence/imgsz, sampling
  stride, crop manifest; committed record framing + checksums + finalized
  marker; truncated final record fails closed. Explicit `clock_mode`
  (authoritative decoded PTS or declared frame-offset clock — never mixed;
  today's `media_time_seconds` is synthesized index*stride/fps and must not be
  called PTS). Deterministic `event_id` =
  uuid5(schema|session|sequence); `observation_id` =
  uuid5(schema|session|track|first_seq|last_seq|window PTS); mutable evidence
  (bbox, crop bytes, labels, scores) lives in a separate canonical digest so
  divergent evidence collides on the same ID instead of forking records. One
  injected same-position PTS/window/content mismatch must be rejected before
  probe_services/embedding/Qdrant/Memory.
- **P0B `JOURNAL_CONSUMER_REPLAY`**: kill the consumer (not the tracker)
  mid-run, restart against the unchanged journal, require identical canonical
  observation IDs + digests in ISOLATED Qdrant/Memory collections (isolated
  test collections are the one PREREQUISITE). Compare canonical sets, not
  timestamped bytes.
- **Then**: UI live-event consumption gate → tracker process-resume
  continuity → first live source (webcam/RTSP). Outbox/retry hardening is
  parallel to P0A/P0B but prerequisite before the first unbounded live
  source. Row-7 re-anchoring and pre-fix row re-runs are parallel batch
  remediation; ux-lab legacy import removal and live-browser handoff breadth
  stay deferred.

**P0A and P0B LANDED 2026-07-18** (receipts:
`generated/watch_source_session_p0_20260718/`):
`scripts/watch_source_session_journal.py` (immutable journal: header binds
source sha256/model/tracker/conf/imgsz/stride, explicit clock_mode,
per-record checksums + chain hash + finalize marker, fail-closed reader,
deterministic event/observation IDs separate from canonical evidence
digest); `track_yolo_bytetrack.py --journal` (sole append writer, per-event
fsync); `scripts/replay_source_session_journal.py` (read-only consumer,
validates before any client call, refuses production collections, idempotent
by deterministic IDs). Live proof on a fresh 168-192s clip: 80 events,
3 tamper classes rejected pre-write, SIGKILL after 1/2 observations then
restart converged to the identical canonical set in isolated Memory+Qdrant
collections. Hermetic coverage in
`tests/test_watch_source_session_replay.py`. Decoded-PTS mode and producer
process-resume remain later continuity gates.

**UI live-event consumption LANDED 2026-07-18** (receipts:
`generated/watch_ui_live_event_consumption_20260718/`): the clip modal's
"Live track" toggle opens an EventSource to
`/api/projects/watch/tracker-events/stream?mode=live`; the server spawns the
tracker through the skill venv python with incremental stdout JSONL, and the
SSE meta event carries ffprobe source dimensions so overlay geometry is
independent of browser media decode (required for RTSP later). Browser proof:
2 dashed LIVE_PROVISIONAL overlays with track labels + live status badge over
row 7 of the fresh focused report. Caveat: machine-wide Chrome media decode
was broken during the proof (any mp4 spins — likely the outdated NVIDIA
driver), so video pixels render black; re-screenshot overlay-over-video after
a driver update.

**P0C process-resume, P0D outbox, and the FIRST LIVE SOURCE LANDED
2026-07-18** (receipts: `generated/watch_live_source_canary_20260718/`):
- P0C: `run_watch_tracker_supervised.py` chains a NEW source session on
  producer death (`previous_session_id` in the journal header;
  `read_journal_lenient` salvages a crashed journal's valid prefix; track ids
  never carry identity across the chain). Live proof: tracker SIGKILLED
  mid-run on a live stream (122 events salvaged, unfinalized) → chained
  session reconnected and finalized 400 events; zero observation-id overlap
  across sessions; salvaged observations carry
  `FROM_UNFINALIZED_SESSION_JOURNAL` blockers.
- P0D: the replay consumer has a durable per-observation outbox (atomic
  sidecar, retry with backoff, `--drain`). Live proof: dead memory sink
  absorbed 20/20 observations as FAILED_RETRYABLE without crashing; drain
  against the live daemon converged to 20/20 WRITTEN with the plan-matching
  canonical set.
- First live source: ffmpeg `-re` MPEG-TS over HTTP (real-time paced,
  unseekable, relistening) — ultralytics consumes it directly; the same
  supervisor takes any public HLS/RTSP URI. Note: ultralytics rejects
  `udp://` URIs; use http/rtsp/rtmp/tcp.
- Guard added: supervised sessions isolate the tracker `--out-dir` per
  session after a live run clobbered the committed 80-event fixture log
  (restored from git).

**Still gated**: decoded-PTS clock binding, unbounded multi-hour operation,
public-internet endpoint reliability, and any identity promotion on live
tracks (requires the full evidence chain, as ever).
