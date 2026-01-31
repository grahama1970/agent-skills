# discover-music Implementation Tasks

## Goal

**Discover new music for Horus using external services and HMT bridge matching.**

## Context

Uses Last.fm, ListenBrainz, MusicBrainz, and Bandcamp to find new music based on Horus's taste profile from `/consume-music`. Filters and ranks results using HMT bridge attributes.

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method | Sanity Script | Status |
|---------|------------|---------------|--------|
| pylast | `lastfm.get_similar()` | `sanity/lastfm.py` | [ ] PENDING |
| musicbrainzngs | `search_artists()` | `sanity/musicbrainz.py` | [ ] PENDING |
| requests | Bandcamp scraping | N/A (well-known) | N/A |
| consume-music | `profile.json` | `sanity/profile.py` | [ ] PENDING |

## Questions/Blockers

- [ ] Last.fm API key required - do we have one?
- [ ] ListenBrainz token - optional but recommended
- [x] Bandcamp approach? → Scraping (no official API)
- [x] Integration with /dogpile? → Can be invoked via `/dogpile music`

> Blocked: Need Last.fm API key before implementation.

## Tasks

- [ ] **Task 1**: Last.fm Integration
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Sanity**: `sanity/lastfm.py` - verify API key works
  - **Definition of Done**:
    - Test: `tests/test_discover.py::test_lastfm_similar`
    - Assertion: `get_similar("Chelsea Wolfe")` returns artist list

- [ ] **Task 2**: MusicBrainz Integration
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Sanity**: `sanity/musicbrainz.py` - verify API works
  - **Definition of Done**:
    - Test: `tests/test_discover.py::test_musicbrainz_search`
    - Assertion: `search_artists("doom metal")` returns results with genres

- [ ] **Task 3**: Bandcamp Search
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Sanity**: N/A (scraping, test with requests)
  - **Definition of Done**:
    - Test: `tests/test_discover.py::test_bandcamp_search`
    - Assertion: `search_bandcamp("dark folk")` returns artist/album list

- [ ] **Task 4**: Recommend Command
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1, Task 2
  - **Definition of Done**:
    - Test: `tests/test_discover.py::test_recommend`
    - Assertion: `./run.sh recommend` returns recommendations based on profile

- [ ] **Task 5**: Similar Artist Command
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Definition of Done**:
    - Test: `tests/test_discover.py::test_similar`
    - Assertion: `./run.sh similar "Chelsea Wolfe"` returns similar artists

- [ ] **Task 6**: Search by Bridge Command
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1, Task 2
  - **Definition of Done**:
    - Test: `tests/test_discover.py::test_search_bridge`
    - Assertion: `./run.sh search --bridge Fragility` returns acoustic/folk artists

- [ ] **Task 7**: Scene Command
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 6
  - **Definition of Done**:
    - Test: `tests/test_discover.py::test_scene`
    - Assertion: `./run.sh scene "Siege of Terra"` returns epic/triumphant music

- [ ] **Task 8**: Memory Sync
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 4
  - **Definition of Done**:
    - Test: `tests/test_discover.py::test_memory_sync`
    - Assertion: Discoveries stored in /memory with category `music_discovery`

- [ ] **Task 9**: dogpile Integration
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 4, Task 5, Task 6
  - **Definition of Done**:
    - Test: Manual test via `/dogpile music "dark folk"`
    - Assertion: Returns combined results from all services

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
| 0 | Task 1, 2, 3 | API integrations (can run in parallel) |
| 1 | Task 4, 5, 6 | Core commands |
| 2 | Task 7, 8 | Advanced features |
| 3 | Task 9, 10 | Integration |

## Completion Criteria

1. `./run.sh recommend` returns recommendations based on profile
2. `./run.sh similar "Artist"` finds similar artists
3. `./run.sh search --bridge X` finds music by HMT bridge
4. `./run.sh bandcamp "query"` searches Bandcamp
5. `./run.sh scene "..."` finds music for scene
6. `/dogpile music "query"` invokes discover-music
7. `./sanity.sh` exits 0

## API Keys Required

```bash
# Add to .env
LASTFM_API_KEY=xxx          # Required - https://www.last.fm/api/account/create
LISTENBRAINZ_TOKEN=xxx      # Optional - https://listenbrainz.org/profile/
```
