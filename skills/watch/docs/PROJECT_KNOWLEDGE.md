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
- **Persistence contract:** Qdrant/Jina multimodal embeddings store vectors for representative frames, crops, transcript chunks, and audio/text evidence. Arango/memory stores metadata, source pointers, graph edges, and case/overlay records.
- **Case trigger:** create `watch_evidence_cases` only when a claim needs durable anchoring, such as visual-track/SRT/Whisper/domain conflicts, telemetry-vs-visual mismatches, operator isolate actions, or unresolved identity evidence.
- **Chat UX:** the `$memory` pipeline belongs in Watch Agent dynamic thinking/status, not in the Library ingest panel. Expected stages are `/intent`, `extract entities`, `/recall`, `create evidence case` when needed, and `/answer | /clarify | /deflect`.
- **Current contract artifacts:** `docs/architecture/watch_realtime_character_tracking_contract.md` records the candidate architecture; `docs/architecture/watch_realtime_tracking_execution_plan.md` records the execution sequence from domain seed to live tracker proof to memory/Qdrant recall; `docs/architecture/watch_track_observations.schema.json` and `docs/architecture/watch_track_observation.bad_santa_marcus.sample.json` define the first bounded track-observation canary. `docs/architecture/watch_realtime_character_tracking_inspection.md` remains `REVISE` until memory upsert/recall proof and a live playback tracker log exist.
- **Dry-run memory plan:** `docs/architecture/watch_realtime_tracking_memory_upsert_manifest.bad_santa_marcus.json` is the first accepted dry-run manifest for the Bad Santa Marcus canary. It prepares one movie-domain entity, one bounded track observation, one evidence case, three graph edges, Qdrant pointer metadata, rollback keys, and recall-proof queries without executing memory or vector writes.
- **Tracker event fixture:** `docs/architecture/watch_tracker_event_log.bad_santa_marcus.fixture.jsonl` is the first accepted deterministic live-event fixture. It contains three provisional `watch.live_track_update.v1` events for `track_07` over 02:48-03:12 and feeds the dry-run manifest without claiming live YOLO/ByteTrack runtime proof.
- **Dry-run upsert payloads:** `scripts/build_realtime_tracking_upsert_payloads.py` reads the accepted manifest plus tracker JSONL fixture and emits concrete `/upsert` request bodies under `docs/architecture/generated/bad_santa_marcus_0248_upsert_payloads/` without posting. This proves payload shape only; live memory writes and recall remain gated.
- **Frame-backed event harness:** `scripts/build_realtime_tracking_event_log.py` reads the accepted manifest frame and emits schema-valid `watch.live_track_update.v1` JSONL under `docs/architecture/generated/bad_santa_marcus_0248_tracker_events/`. It is deterministic harness output, not YOLO/ByteTrack or identity proof.
- **UI overlay payload adapter:** `scripts/build_tracking_overlay_payload.py` converts validated `watch.live_track_update.v1` JSONL into a browser/modal overlay payload under `docs/architecture/generated/bad_santa_marcus_0248_overlay_payload/`. `docs/architecture/watch_ui_overlay_payload.schema.json` and `scripts/validate_watch_overlay_payload.py` enforce the geometry/proof-scope contract. This proves event-derived geometry plumbing only; it does not prove live ML, identity, memory writes, Qdrant writes, or recall.
- **Local UI consumption inspection:** `docs/architecture/watch_ui_overlay_payload_consumption.inspection.md` records a local UX Lab proof that the Watch modal can render one event-derived overlay for the 02:48 Marcus dry-run payload and fail closed for a non-matching clip. This is still dry-run geometry plumbing, not live tracking or identity proof. The local app file was not committed from that inspection because the `pi-mono` Watch component already had broad unrelated dirty edits.
- **YOLO/ByteTrack adapter:** `scripts/track_yolo_bytetrack.py` maps Ultralytics `model.track(..., tracker="bytetrack.yaml", stream=True)` output into the same `watch.live_track_update.v1` JSONL contract. The Watch canary defaults to `--sample-fps 5`, computes a source-frame stride, and passes it to Ultralytics `vid_stride` so live checks have a bounded cadence before memory summarization. `ultralytics`, OpenCV, and ByteTrack's `lap` dependency are provided through the `tracking` extra in `pyproject.toml`. Local inspection now proves a bounded live YOLO/ByteTrack run emitted 80 schema-valid provisional events for the Bad Santa Marcus clip; it still does not prove character identity, UI real-time overlay updates, memory/Qdrant writes, or `/memory recall`.
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

Configured with OpenSubtitles credentials and Radarr integration. Working API key: `63251eb7ee21880126c0a70dacf96548`. Config at `/path/to/bazarr/config/config/config.yaml`.

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
