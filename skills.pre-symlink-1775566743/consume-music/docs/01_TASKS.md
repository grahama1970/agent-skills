# consume-music Implementation Tasks

## Goal

**Process ingested music for Horus persona using HMT taxonomy and /memory integration.**

## Context

Works with content from `/ingest-yt-history`. Extracts HMT taxonomy tags, enables episodic associations with lore events, syncs to `/memory` for Horus recall.

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method | Sanity Script | Status |
|---------|------------|---------------|--------|
| horus_music_taxonomy | `HorusMusicTaxonomyVerifier` | `sanity/hmt.py` | [ ] PENDING |
| memory skill | `run.sh learn` | N/A (verified elsewhere) | N/A |
| ingest-yt-history | `history.jsonl` | `sanity/ingest_data.py` | [ ] PENDING |

## Questions/Blockers

- [x] Which taxonomy model? → HMT (Horus Music Taxonomy) with Federated Taxonomy bridges
- [x] Memory category? → `music` collection with bridge_attributes
- [x] Episodic associations? → EPISODIC_ASSOCIATIONS dict in horus_music_taxonomy.py

> Ready for orchestration after sanity scripts pass.

## Tasks

- [ ] **Task 1**: Sync from Ingest
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Sanity**: `sanity/ingest_data.py` - verify ingest output exists
  - **Definition of Done**:
    - Test: `tests/test_consume.py::test_sync_from_ingest`
    - Assertion: Imports music entries from `~/.pi/ingest-yt-history/history.jsonl`

- [ ] **Task 2**: HMT Taxonomy Extraction
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Sanity**: `sanity/hmt.py` - verify HMT verifier works
  - **Definition of Done**:
    - Test: `tests/test_consume.py::test_hmt_extraction`
    - Assertion: Extracts bridge_attributes, collection_tags for each entry

- [ ] **Task 3**: Search Command
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Definition of Done**:
    - Test: `tests/test_consume.py::test_search_command`
    - Assertion: `./run.sh search "Chelsea"` returns matching tracks

- [ ] **Task 4**: Find by Bridge Command
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - **Definition of Done**:
    - Test: `tests/test_consume.py::test_find_bridge`
    - Assertion: `./run.sh find --bridge Fragility` returns Chelsea Wolfe, Daughter

- [ ] **Task 5**: Find for Episode Command
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - **Definition of Done**:
    - Test: `tests/test_consume.py::test_find_episode`
    - Assertion: `./run.sh episode "Siege_of_Terra"` returns Sabaton, Two Steps From Hell

- [ ] **Task 6**: Find for Scene Command
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - **Definition of Done**:
    - Test: `tests/test_consume.py::test_find_scene`
    - Assertion: `./run.sh scene "Imperial Fists defend"` returns Resilience-bridged tracks

- [ ] **Task 7**: Note Command
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 3
  - **Definition of Done**:
    - Test: `tests/test_consume.py::test_note_command`
    - Assertion: Notes stored in `~/.pi/consume-music/notes/`

- [ ] **Task 8**: Memory Sync Command
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 2
  - **Definition of Done**:
    - Test: `tests/test_consume.py::test_memory_sync`
    - Assertion: `/memory recall --bridge Fragility --collection music` returns results

- [ ] **Task 9**: Profile Builder
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 2
  - **Definition of Done**:
    - Test: `tests/test_consume.py::test_profile_builder`
    - Assertion: Creates profile.json with top_bridge_attributes, top_domains, top_artists

- [ ] **Task 10**: run.sh Wrapper
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: All tasks
  - **Definition of Done**:
    - Test: `./sanity.sh`
    - Assertion: Exits 0, all commands functional

## Parallel Execution Groups

| Group | Tasks | Description |
|-------|-------|-------------|
| 0 | Task 1 | Foundation - sync from ingest |
| 1 | Task 2, 3, 4, 5, 6 | Core features (taxonomy + search) |
| 2 | Task 7, 8, 9 | Notes, memory, profile |
| 3 | Task 10 | Final integration |

## Completion Criteria

1. `./run.sh sync` imports from ingest-yt-history
2. `./run.sh search` finds tracks by title/artist
3. `./run.sh find --bridge X` finds tracks by HMT bridge
4. `./run.sh episode X` finds tracks for lore episode
5. `./run.sh scene "..."` finds tracks for scene description
6. `./run.sh memory-sync` stores entries in /memory with taxonomy
7. `/memory recall --bridge X --collection music` works
8. `./sanity.sh` exits 0
