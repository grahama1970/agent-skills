# ingest-yt-history Implementation Tasks

## Goal

**Let Horus persona easily find music based on human's listening history.**

Location: `/home/graham/workspace/experiments/memory/persona` needs to query music preferences.

## Context

Ingest YouTube/YouTube Music history from Google Takeout, build music index, integrate with `/memory` so Horus can:

1. Find music matching moods (melancholic, epic, atmospheric)
2. Reference human's taste in conversations
3. Inform creative work (stories, movies) with appropriate music

**Discovery services** (Last.fm, ListenBrainz, etc.) will be added to `/dogpile music` separately.

## Horus Music Taxonomy (HMT) Integration

Music MUST use the Federated Taxonomy for `/memory` integration:

| Tier | Type | Music Examples |
|------|------|----------------|
| **Tier 0** | Bridge Attributes | Precision, Resilience, Fragility, Corruption, Loyalty, Stealth |
| **Tier 1** | Tactical Tags | Score, Recall, Amplify, Contrast, Immerse, Signal, Invoke, Endure |
| **Tier 3** | Collection Tags | Function (Battle, Mourning), Domain (Doom_Metal, Dark_Folk), Thematic (Melancholic, Epic) |

**Bridge → Lore Connections:**
- `Precision` → Iron Warriors, Perturabo (polyrhythmic, technical music)
- `Resilience` → Imperial Fists, Dorn (crescendo, triumphant, enduring)
- `Fragility` → Webway, Magnus's Folly (delicate, breaking, acoustic)
- `Corruption` → Warp, Chaos, Davin (distorted, industrial, harsh)
- `Loyalty` → Oaths of Moment, Loken (ceremonial, choral, sacred)
- `Stealth` → Alpha Legion, Alpharius (ambient, drone, minimalist)

**Mathematical Features (non-human analysis):**
- Spectral: centroid, bandwidth, rolloff, flatness, contrast
- Temporal: tempo_bpm, tempo_variance, onset_density, beat_strength
- Psychoacoustic: roughness, dissonance, sharpness, dynamic_range
- Entropy: spectral_entropy, temporal_entropy, harmonic_complexity

HMT verifier: `/home/graham/workspace/experiments/memory/persona/bridge/horus_music_taxonomy.py`

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method | Sanity Script | Status |
|---------|------------|---------------|--------|
| Takeout JSON format | N/A | `sanity/takeout_format.py` | [x] PASS |
| google-api-python-client | `youtube.videos().list()` | `sanity/youtube_api.py` | [x] PASS |
| horus_music_taxonomy | `HorusMusicTaxonomyVerifier` | `sanity/hmt_verifier.py` | [x] PASS |
| requests | `requests.get()` | N/A (well-known) | N/A |
| rich | `Console(), Progress()` | N/A (well-known) | N/A |

> Need to create sanity script for HMT verifier before orchestration.

## Questions/Blockers

- [x] Which discovery services? → Last.fm, ListenBrainz, MusicBrainz, Bandcamp (moved to /dogpile music)
- [x] Memory integration format? → JSONL with category "music-preferences"
- [x] Horus persona aesthetic? → Epic/orchestral/metal (Warhammer 40K)
- [x] ~~YOUTUBE_API_KEY suspended~~ → New key created and verified ✅
- [x] ~~Takeout export~~ → Downloaded: 10,000 entries (44% YouTube Music)

> ✅ All blockers resolved. Ready for orchestration.

## Takeout Analysis (Human's Profile)

| Metric | Value |
|--------|-------|
| Total entries | 10,000 |
| YouTube Music | 4,366 (44%) |
| YouTube | 5,634 (56%) |

**Music taste (Horus-aligned):**
- Chelsea Wolfe (dark folk/doom)
- Daughter (melancholic indie)
- Spiritbox (progressive metal)

**Warhammer 40K lore channels:**
- Luetin09, In Deep Geek, Stories by Imperium

**Tech/AI:**
- Discover AI, AICodeKing, Sabine Hossenfelder

## Tasks

- [x] **Task 1**: Takeout JSON Parser
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Sanity**: `sanity/takeout_format.py` - verify Takeout JSON structure
  - **Definition of Done**:
    - Test: `tests/test_ingest.py::test_parse_takeout_json`
    - Assertion: Parses sample Takeout JSON, outputs valid JSONL with video_id, title, ts, url

- [x] **Task 2**: YouTube vs YouTube Music Detection
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Sanity**: N/A (uses regex, string matching - standard)
  - **Definition of Done**:
    - Test: `tests/test_ingest.py::test_detect_music_service`
    - Assertion: Correctly identifies music.youtube.com URLs, VEVO channels, " - Topic" channels

- [x] **Task 3**: YouTube API Enrichment
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Sanity**: `sanity/youtube_api.py` - verify API key and quota
  - **Definition of Done**:
    - Test: `tests/test_ingest.py::test_enrich_with_youtube_api`
    - Assertion: Adds duration_seconds, category, tags to entries (requires YOUTUBE_API_KEY)

- [x] **Task 4**: Find-Music Command (Horus Primary Interface)
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1, Task 2
  - **Sanity**: N/A (uses Counter, datetime - standard)
  - **Definition of Done**:
    - Test: `tests/test_ingest.py::test_find_music_command`
    - Assertion: `./run.sh find-music --mood melancholic` returns Chelsea Wolfe, Daughter

- [x] **Task 5**: task-monitor Integration
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Sanity**: N/A (task-monitor already verified in that skill)
  - **Definition of Done**:
    - Test: `tests/test_ingest.py::test_monitor_integration`
    - Assertion: Writes to `.batch_state.json`, progress visible in task-monitor

- [x] **Task 6**: HMT Taxonomy Extraction
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 3, Task 4
  - **Sanity**: `sanity/hmt_verifier.py` - verify HMT taxonomy verifier works
  - **Definition of Done**:
    - Test: `tests/test_taxonomy.py::test_hmt_extraction`
    - Assertion: Extracts bridge_attributes (Resilience, Fragility, etc.) and collection_tags (domain, thematic_weight) for each music entry

- [x] **Task 7**: Sync-Memory Command (Taxonomy-Based)
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 6
  - **Sanity**: N/A (memory skill already verified)
  - **Definition of Done**:
    - Test: `tests/test_ingest.py::test_sync_memory`
    - Assertion: `./run.sh sync-memory` creates entries in ArangoDB with:
      - category: "music"
      - collection_tags: {domain: "Dark_Folk", thematic_weight: "Melancholic"}
      - bridge_attributes: ["Fragility", "Corruption"]
      - tactical_tags: ["Score", "Recall"]

- [x] **Task 8**: Music Taste Profile Builder (Taxonomy-Aware)
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 6, Task 7
  - **Sanity**: N/A (uses Counter, json - standard)
  - **Definition of Done**:
    - Test: `tests/test_profile.py::test_build_taste_profile`
    - Assertion: Creates JSON with:
      - top_bridge_attributes: ["Fragility", "Corruption", "Resilience"]
      - top_domains: ["Dark_Folk", "Doom_Metal", "Progressive_Metal"]
      - top_thematic_weights: ["Melancholic", "Epic", "Ominous"]
      - listening_patterns: {by_time, by_artist, by_bridge}

- [x] **Task 9**: Horus Lore Connection (Memory Recall)
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 7, Task 8
  - **Sanity**: N/A (uses existing persona/memory integration)
  - **Definition of Done**:
    - Test: `tests/test_profile.py::test_lore_connection`
    - Assertion: `/memory recall --bridge Fragility --collection music` returns Chelsea Wolfe, Daughter
    - Assertion: `/memory recall --scene "Siege of Terra"` returns music with Resilience bridge

- [x] **Task 10**: run.sh Wrapper and Sanity Check
  - Agent: general-purpose
  - Parallel: 4
  - Dependencies: All tasks
  - **Sanity**: N/A (integration test)
  - **Definition of Done**:
    - Test: `./sanity.sh`
    - Assertion: Exits 0, all commands functional

## Parallel Execution Groups

| Group | Tasks | Description |
|-------|-------|-------------|
| 0 | Task 1 | Foundation - Takeout parser |
| 1 | Task 2, 3, 4, 5 | Core features (can run in parallel) |
| 2 | Task 6, 7 | Taxonomy extraction + Memory sync |
| 3 | Task 8, 9 | Profile building + Lore connection |
| 4 | Task 10 | Final integration |

## Completion Criteria

1. `./run.sh parse` works with Takeout JSON
2. `./run.sh stats` shows breakdown by service
3. `./run.sh enrich` adds YouTube API metadata
4. `./run.sh profile` generates taste profile with taxonomy tags
5. `./run.sh export --format memory` creates memory-compatible output with bridge_attributes
6. `/memory recall --bridge Resilience --collection music` returns relevant tracks
7. `/memory recall --episode "Siege of Terra"` returns music for that lore event
8. `./sanity.sh` exits 0

## Episodic Memory Associations

Music is linked to **lore events** (not just moods):

| Episode | Bridge | Example Music |
|---------|--------|---------------|
| Davin_Corruption | Corruption | Chelsea Wolfe, Nine Inch Nails |
| Siege_of_Terra | Resilience | Sabaton, Two Steps From Hell |
| Webway_Collapse | Fragility | Daughter, Phoebe Bridgers |
| Mournival_Oath | Loyalty | Wardruna, Heilung |
| Iron_Cage | Precision | Tool, Meshuggah |
| Sanguinius_Fall | Fragility | Chelsea Wolfe, Billie Marten |

Horus can query: `find_music_for_episode("Siege_of_Terra", candidates)`

## Related Task Files

After this skill is complete, create:
- `~/.claude/skills/dogpile/02_MUSIC_COMMAND_TASKS.md` - Add `/dogpile music` command

## Research Notes (from /dogpile)

### Key Heuristics for Music Detection
1. **URL-based**: `music.youtube.com` URLs are definitive
2. **Channel patterns**:
   - VEVO channels (official music videos)
   - " - Topic" suffix (auto-generated artist channels)
   - "Official Audio" in title
3. **Category**: YouTube category "Music" (categoryId: 10)
4. **Duration**: Music typically 2-7 minutes

### For Horus Persona
- Weight towards epic/orchestral/metal (Warhammer 40K aesthetic)
- Cross-reference with existing persona preferences in memory
- Audiobooks detected: Horus Heresy series in persona directory
