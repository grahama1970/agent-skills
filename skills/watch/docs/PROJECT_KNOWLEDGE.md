# Watch Skill: Project Knowledge

## Architecture

- **CLI:** Typer via `run.sh`/`scripts/cli.py`; `scripts/watch.py` is importable pipeline logic
- **Two memory layers:**
  - `watch_content` — per-scene rows with timecode, SRT text, Whisper text, visual descriptions, divergence category, persona tag
  - `persona_memory` — "Embry watched Movie Title" record with `persona_id`, `answer_text`, `retrieval_text`, `watch_history` tag
- **Whisper:** Dedicated Docker container `hwdsl2/whisper-server:cuda` on port 9000 (GPU-accelerated). Falls back to local faster-whisper on CPU only when Docker is unreachable.
- **Diarization:** Contract defined for a future pyannote Community-1 audio evidence lane. It must produce anonymous speaker turns and transcript attribution, but it is not implemented in the Watch runtime yet.

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

## Pyannote Diarization Boundary

Status: `CONTRACT_DEFINED_NOT_IMPLEMENTED`.

Watch needs a separate acoustic diarization lane for "who spoke when" because
ordinary SRT/caption files often lack reliable speaker identity and Whisper
segments are timestamped text, not speaker turns. The selected contract is a
future localhost pyannote Community-1 service pinned to pyannote.audio `4.0.7`.

Contract artifacts:

- `docs/architecture/watch_diarization_contract.md`
- `docs/architecture/schemas/watch_diarization.schema.json`
- `docs/architecture/schemas/watch_speaker_attribution.schema.json`
- `scripts/diarization_contract.py`
- `tests/fixtures/diarization/`

The pyannote lane must remain anonymous acoustic evidence:

```text
SPEAKER_00 != Willie
SPEAKER_01 != Marcus
SPEAKER_02 != narrator
```

Any speaker-to-character relation is a candidate requiring separate evidence
and human acceptance through the existing Watch identity ledger. Pyannote must
not alter SRT text, Whisper text, YOLO receipts, accepted labels, or Memory
identity state.

## Scene Detection

Two-pass approach (no `-frames:v` limit that caused partial coverage):

1. ffmpeg `select='gt(scene,0.3)'` detects all scene changes across the entire video
2. Results subsampled evenly to `--max-frames` if more than budget

Covers the full movie. Frame budget defaults to 100. The YOLO materializer has
a separate `--max-events` cap of 500 for tracker events.

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
- 2026-07-20: Immutable YOLO identity goal scope: row 9 is the narrow live Memory/Qdrant canary for tentative Marcus crop suggestion; row 10 accept/stop/reassign/reload is deterministic browser-gated behavior over a proof-only asset to avoid contaminating canonical Bad Santa identity memory. Broad handoff coverage remains pending. RTSP, drone, F36, production identity accuracy, and full streaming runtime are not implemented by this gate. Durable proof manifests live under `skills/watch/proofs/immutable-goal/<git-sha>/manifest.json`.
- 2026-07-23: Pyannote diarization scope: Watch has contract artifacts for a future anonymous speaker topology lane, including failure receipts and source-timeline focused-range rules. This is not runtime support. The next implementation slice should add either the persistent pyannote service or the model-free speaker-attribution algorithm, not both at once.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-07-07 | Watch owns second-stage identity/world-model state over YOLOAnalytics detections | YOLOAnalytics does not know domain identity; Watch must persist keyframe/stop sequences, use Memory/Qdrant for recall, and invoke Tau only when sequence-level reasoning is needed. |
