# Task List: Embry Humming Pipeline

**Created**: 2026-02-11
**Goal**: Enable Embry to hum songs she "likes" in her own voice while working, starting with Hawaiian War Chant by the Lennon Sisters

## Context

Embry needs to hum actual melodies (not just backchannel "mmm" sounds) while
running UX scenarios. The pipeline: download a song from YouTube → separate
vocals via Demucs → convert vocals to Embry's voice via RVC → cache the
result → play through AudioMixer during idle, ducking to 0% when conversation
starts.

PersonaPlex (Moshi) handles short backchannel sounds natively. Actual melodies
require pre-processed external audio mixed at the output level.

**First test track**: Hawaiian War Chant by the Lennon Sisters (nonsense
Hawaiian syllables — fits Embry's Linguistics degree persona).

## Crucial Dependencies (Sanity Scripts)

| Library/Tool | API/Method | Sanity Script | Status |
|-------------|------------|---------------|--------|
| yt-dlp | `yt-dlp --extract-audio` | `sanity/yt_dlp.sh` | [ ] PENDING |
| demucs | `demucs.separate.main()` | `sanity/demucs.sh` | [ ] PENDING |
| RVC inference | `create-music rvc-infer` | `sanity/rvc_infer.sh` | [ ] PENDING |
| espeak-ng | `espeak-ng --stdout` | `sanity/espeak.sh` | [x] PASS |
| PipeWire | `pw-play` | `sanity/pipewire.sh` | [x] PASS |

## Questions/Blockers

None — all requirements clear.

- Hawaiian War Chant video URL confirmed: https://youtu.be/Dordpe3KX_I
- Embry voice samples exist (43 WAV, ~153MB at /mnt/storage12tb/media/personas/embry/tts_output/)
- 46 RVC models already trained (pipeline proven)
- AudioMixer ducking already implemented in converse skill
- consume-music registry has 2,844 tracks (HMT taxonomy pipeline proven)

## Tasks

### P0: Sanity & Setup (Sequential)

- [ ] **Task 1**: Create and verify sanity scripts for all dependencies
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - Details: Create sanity scripts that verify yt-dlp can download audio,
    Demucs can separate stems, and RVC inference works. Each must exit 0.
  - Scripts to create:
    - `sanity/yt_dlp.sh` — download 10s of a test video
    - `sanity/demucs.sh` — separate a short WAV into stems
    - `sanity/rvc_infer.sh` — run inference with any existing model
  - **Definition of Done**:
    - Test: All three sanity scripts exit 0
    - Assertion: `./sanity/yt_dlp.sh && ./sanity/demucs.sh && ./sanity/rvc_infer.sh` returns 0

- [ ] **Task 2**: Train Embry RVC voice model
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 1 (sanity/rvc_infer.sh must pass)
  - Details: Train an RVC v2 model on Embry's 43 existing voice samples at
    `/mnt/storage12tb/media/personas/embry/tts_output/`. Use learn-artist
    skill with `--source-dir` flag. Target: 200 epochs, batch size 4.
  - Skill: `/home/graham/workspace/experiments/pi-mono/.pi/skills/learn-artist`
  - Command: `./run.sh train "embry" --source-dir /mnt/storage12tb/media/personas/embry/tts_output --category voice --epochs 200`
  - **Definition of Done**:
    - Test: `ls /mnt/storage12tb/media/music/rvc-models/voice/embry/embry-infer.pth`
    - Assertion: File exists and is >10MB

### P1: Ingest + Stem (Parallel after P0)

- [ ] **Task 3**: Download Hawaiian War Chant audio from YouTube
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - Details: Use yt-dlp to download audio from https://youtu.be/Dordpe3KX_I.
    Save as WAV at a known path for stemming.
  - Skill: `/home/graham/workspace/experiments/pi-mono/.pi/skills/ingest-youtube`
  - **Definition of Done**:
    - Test: Downloaded WAV exists and is >1MB
    - Assertion: `file <output>.wav` shows "WAVE audio"

- [ ] **Task 4**: Add Hawaiian War Chant to consume-music registry
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 3
  - Details: Register the track in consume-music with HMT taxonomy metadata:
    bridge_attributes=["Loyalty", "Resilience"], mood=["playful", "curious"],
    persona_connection="Linguistics degree, Hawaiian cultural ties"
  - Skill: `/home/graham/workspace/experiments/pi-mono/.pi/skills/consume-music`
  - **Definition of Done**:
    - Test: `./run.sh search "Hawaiian War Chant"` returns the track
    - Assertion: Track found in registry with bridge attributes

### P2: Stem Separation (After P1)

- [ ] **Task 5**: Separate vocals from Hawaiian War Chant
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 3 (downloaded audio must exist)
  - Details: Run Demucs htdemucs_6s to separate vocals from the full mix.
    Store vocal stem for RVC conversion.
  - Skill: `/home/graham/workspace/experiments/pi-mono/.pi/skills/create-stems`
  - Command: `./run.sh separate --mix <downloaded.wav> --out /tmp/stems/hawaiian-war-chant --instrument vocals`
  - **Definition of Done**:
    - Test: Vocal stem WAV exists at output path
    - Assertion: `file /tmp/stems/hawaiian-war-chant/htdemucs_6s/*/vocals.wav` shows "WAVE audio"

### P3: Voice Conversion (After P2 + Embry model)

- [ ] **Task 6**: Convert Lennon Sisters vocals to Embry's voice via RVC
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 2 (Embry RVC model), Task 5 (vocal stem)
  - Details: Run RVC inference with Embry's model to convert the Lennon Sisters
    vocal performance into Embry's voice timbre. Output to hum-cache.
  - Skill: `/home/graham/workspace/experiments/pi-mono/.pi/skills/create-music`
  - Command: `./run.sh rvc-infer --input <vocals.wav> --model embry --output /mnt/storage12tb/media/personas/embry/hum-cache/hawaiian_war_chant.wav`
  - **Definition of Done**:
    - Test: Converted WAV exists and is playable
    - Assertion: `pw-play /mnt/storage12tb/media/personas/embry/hum-cache/hawaiian_war_chant.wav` plays audio through Jabra

### P4: Integration (After P3)

- [ ] **Task 7**: Create hum-cache manifest with taxonomy metadata
  - Agent: general-purpose
  - Parallel: 4
  - Dependencies: Task 6
  - Details: Create manifest.json in hum-cache directory indexing the converted
    audio with Federated Taxonomy bridge attributes, mood tags, and persona
    connection metadata. Format matches what converse/idler.py MusicSelector
    expects.
  - **Definition of Done**:
    - Test: `python3 -c "import json; m=json.load(open('/mnt/storage12tb/media/personas/embry/hum-cache/manifest.json')); assert len(m['tracks']) > 0"`
    - Assertion: Manifest loads and contains at least 1 track with bridge_attributes

- [ ] **Task 8**: Wire hum-cache playback into converse idler
  - Agent: general-purpose
  - Parallel: 4
  - Dependencies: Task 7
  - Details: Update idler.py MusicSelector to check hum-cache first (Embry-voiced
    audio preferred over raw music). When hum_tune behavior triggers, load from
    cache, play through mixer "humming" channel. Verify ducking works: humming
    stops when Embry speaks.
  - File: `/home/graham/workspace/experiments/pi-mono/.pi/skills/converse/idler.py`
  - **Definition of Done**:
    - Test: `python3 -c "from idler import Idler; i = Idler(); import asyncio; asyncio.run(i.test_hum('playful'))"`
    - Assertion: Audio plays from hum-cache, not silence

### P5: End-to-End Test (After P4)

- [ ] **Task 9**: Run full integration test — Embry hums while working
  - Agent: general-purpose
  - Parallel: 5
  - Dependencies: Task 8
  - Details: Run the converse orchestrator with a scenario attached. Verify
    that Embry: (a) narrates scenario steps via espeak, (b) hums Hawaiian War
    Chant during idle periods between steps, (c) humming ducks to 0% when she
    speaks, (d) humming resumes during next idle period.
  - Command: `python3 test_solo_work_talk.py --audio-only` (extended to include humming)
  - **Definition of Done**:
    - Test: Run test_solo_work_talk.py with humming enabled
    - Assertion: Session transcript shows both "idle_behavior: hum_tune" entries AND "role: persona" speech entries, confirming both layers work

## Completion Criteria

- [ ] All sanity scripts pass
- [ ] Embry RVC model trained and verified
- [ ] Hawaiian War Chant converted to Embry's voice
- [ ] Hum-cache manifest created with taxonomy
- [ ] Idler plays from hum-cache with correct ducking
- [ ] All tasks marked [x]
- [ ] All Definition of Done tests pass

## Dependency Graph

```
Task 1 (sanity) ──┬──▶ Task 2 (train Embry RVC) ──────────┐
                   │                                         │
                   ├──▶ Task 3 (download) ──▶ Task 5 (stem) │
                   │         │                    │          │
                   │         ▼                    │          │
                   └──▶ Task 4 (registry)         ▼          ▼
                                            Task 6 (RVC convert)
                                                  │
                                                  ▼
                                            Task 7 (manifest)
                                                  │
                                                  ▼
                                            Task 8 (wire idler)
                                                  │
                                                  ▼
                                            Task 9 (e2e test)
```

## Notes

- Task 2 (RVC training) is the longest task (~2 hours on GPU). All other tasks
  are <5 minutes each.
- Tasks 3-4 can run in parallel with Task 2 since they don't need the Embry model.
- The Kamakawiwoole guard in idler.py must remain active — Hawaiian War Chant
  is safe (playful, not sentimental) but the guard protects against grief triggers.
- Future: generalize this pipeline into a `./run.sh add-hum <youtube-url>` command.
