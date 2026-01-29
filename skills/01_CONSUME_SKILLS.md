# Consume Skills Implementation

**Created**: 2026-01-29
**Goal**: Implement consume-movie, consume-book, consume-youtube skills for content consumption after ingestion
**Priority**: High (blocks Horus content consumption workflow)

## Context

Existing ingest skills (`ingest-movie`, `ingest-audiobook`, `ingest-book`, `ingest-youtube`) store content in various formats. We need consume skills to:

1. Search and extract content from ingested media
2. Track consumption history (rewatches, re-reads)
3. Enable Horus notes at timestamps/character positions
4. Integrate with /memory for knowledge storage

## Data Storage

- **Code**: `.pi/skills/consume-{movie,book,youtube}/` (synced via skills-broadcast)
- **Global Data**: `~/.pi/consume-{movie,book,youtube}/` (local, never synced)

## Crucial Dependencies (Sanity Scripts)

| Library      | API/Method                                        | Sanity Script                  | Status  |
| ------------ | ------------------------------------------------- | ------------------------------ | ------- |
| srt          | `srt.parse()`                                     | `sanity/test_srt_parse.py`     | ⬜ TODO |
| whoosh       | `whoosh.index`, `whoosh.qparser`                  | `sanity/test_whoosh_index.py`  | ⬜ TODO |
| ebooklib     | `ebooklib.epub.read_epub()`                       | `sanity/test_ebooklib.py`      | ⬜ TODO |
| scikit-learn | `sklearn.feature_extraction.text.TfidfVectorizer` | `sanity/test_sklearn_tfidf.py` | ⬜ TODO |

## Questions/Blockers

None - all requirements clarified:

1. ✅ Global data storage in `~/.pi/consume-*/`
2. ✅ /memory integration for all consumption + watching habits
3. ✅ Movie: SRT search, clip extraction, sync verification
4. ✅ Book: Markdown + EPUB support
5. ✅ YouTube: transcript search, video analysis
6. ✅ Horus notes with timestamp/character position tracking

---

## Tasks

### Phase 1: Core Infrastructure

- [ ] **Task 1.1**: Create base ContentRegistry class
  - Agent: code
  - Dependencies: none
  - **Files**: `.pi/skills/consume-common/registry.py`, `.pi/skills/consume-common/__init__.py`
  - **Definition of Done**:
    - Test: `python -m pytest sanity/test_registry.py -v`
    - Assertion: Registry can CRUD content entries, persist to JSON
    - Test creates registry, adds movie entry, saves, loads, verifies data integrity

- [ ] **Task 1.2**: Create HorusNotesManager
  - Agent: code
  - Dependencies: Task 1.1
  - **Files**: `.pi/skills/consume-common/notes.py`
  - **Definition of Done**:
    - Test: `python -m pytest sanity/test_notes_manager.py -v`
    - Assertion: Can add note at timestamp, retrieve by content_id, list all notes for agent
    - Note schema validated (note_id, content_type, content_id, agent_id, timestamp, position, note, tags)

- [ ] **Task 1.3**: Create memory bridge utilities
  - Agent: code
  - Dependencies: Task 1.1, Task 1.2
  - **Files**: `.pi/skills/consume-common/memory_bridge.py`
  - **Definition of Done**:
    - Test: `python -m pytest sanity/test_memory_bridge.py -v`
    - Assertion: Functions exist to call `./memory/run.sh learn` and `./memory/run.sh recall`
    - Mock tests verify correct command construction

- [ ] **Task 1.4**: Create sanity scripts for dependencies
  - Agent: code
  - Dependencies: none
  - **Files**: `.pi/skills/consume-common/sanity/test_srt_parse.py`, `test_whoosh_index.py`, `test_ebooklib.py`, `test_sklearn_tfidf.py`
  - **Definition of Done**:
    - Test: `cd .pi/skills/consume-common && python sanity/test_srt_parse.py`
    - Assertion: Each script runs without error, tests core API functionality
    - srt: parses sample SRT file, returns subtitle entries
    - whoosh: creates index, adds document, searches successfully
    - ebooklib: reads sample EPUB, extracts text
    - sklearn: vectorizes text, computes TF-IDF

### Phase 2: consume-movie

- [ ] **Task 2.1**: Create consume-movie directory structure
  - Agent: code
  - Dependencies: Task 1.1, Task 1.2, Task 1.3, Task 1.4
  - **Files**: `.pi/skills/consume-movie/SKILL.md`, `run.sh`, `pyproject.toml`
  - **Definition of Done**:
    - Test: `./run.sh info` runs without error
    - Assertion: Directory follows skill conventions, SKILL.md has proper frontmatter

- [ ] **Task 2.2**: Implement SRT search module
  - Agent: code
  - Dependencies: Task 2.1
  - **Files**: `.pi/skills/consume-movie/consume_movie/search.py`
  - **Definition of Done**:
    - Test: `python -m pytest consume_movie/test_search.py -v`
    - Assertion: `search_subtitles(query, movie_id)` returns list of matches with (start, end, text, context)
    - Search handles case-insensitive matching, returns 5s context window

- [ ] **Task 2.3**: Implement clip extraction
  - Agent: code
  - Dependencies: Task 2.2
  - **Files**: `.pi/skills/consume-movie/consume_movie/clips.py`
  - **Definition of Done**:
    - Test: `python -m pytest consume_movie/test_clips.py -v`
    - Assertion: `extract_clip(movie_id, start, end, output_path)` calls ffmpeg correctly
    - Mock test verifies ffmpeg command: `ffmpeg -ss <start> -to <end> -i <video> -c copy <output>`

- [ ] **Task 2.4**: Implement sync verification
  - Agent: code
  - Dependencies: Task 2.2
  - **Files**: `.pi/skills/consume-movie/consume_movie/sync.py`
  - **Definition of Done**:
    - Test: `python -m pytest consume_movie/test_sync.py -v`
    - Assertion: `verify_sync(movie_id, sample_points=5)` extracts audio samples, compares transcript to SRT
    - Returns sync confidence score (0.0-1.0)

- [ ] **Task 2.5**: Implement CLI commands
  - Agent: code
  - Dependencies: Task 2.2, Task 2.3, Task 2.4
  - **Files**: `.pi/skills/consume-movie/run.sh` (update)
  - **Definition of Done**:
    - Test: `./run.sh search "rage" --movie "test_movie_id"` returns results
    - Test: `./run.sh clip --query "test" --output /tmp/test.mkv` creates clip
    - Test: `./run.sh note --movie "test_id" --timestamp 125.5 --note "test note"` adds note
    - Test: `./run.sh list` shows available movies

- [ ] **Task 2.6**: Integrate with ingest-movie registry
  - Agent: code
  - Dependencies: Task 2.1
  - **Files**: `.pi/skills/consume-movie/consume_movie/ingest_bridge.py`
  - **Definition of Done**:
    - Test: `python -m pytest consume_movie/test_ingest_bridge.py -v`
    - Assertion: Scans `../ingest-movie/transcripts/` directory, imports movie entries to consume-movie registry
    - Imports metadata (title, emotion tags, duration) from existing transcript JSON

### Phase 3: consume-book

- [ ] **Task 3.1**: Create consume-book directory structure
  - Agent: code
  - Dependencies: Task 1.1, Task 1.2, Task 1.3
  - **Files**: `.pi/skills/consume-book/SKILL.md`, `run.sh`, `pyproject.toml`
  - **Definition of Done**:
    - Test: `./run.sh info` runs without error
    - Assertion: Directory follows skill conventions

- [ ] **Task 3.2**: Implement book registry import
  - Agent: code
  - Dependencies: Task 3.1
  - **Files**: `.pi/skills/consume-book/consume_book/ingest_bridge.py`
  - **Definition of Done**:
    - Test: `python -m pytest consume_book/test_ingest_bridge.py -v`
    - Assertion: Scans `~/clawd/library/books/` for markdown files, imports to registry
    - Extracts book title from directory name, parses chapter markers if available

- [ ] **Task 3.3**: Implement full-text search
  - Agent: code
  - Dependencies: Task 3.2
  - **Files**: `.pi/skills/consume-book/consume_book/search.py`
  - **Definition of Done**:
    - Test: `python -m pytest consume_book/test_search.py -v`
    - Assertion: `search_books(query)` searches across all books, returns matches with (book_id, char_position, context)
    - Context includes 200 chars before/after match

- [ ] **Task 3.4**: Implement bookmark/position tracking
  - Agent: code
  - Dependencies: Task 3.1
  - **Files**: `.pi/skills/consume-book/consume_book/position.py`
  - **Definition of Done**:
    - Test: `python -m pytest consume_book/test_position.py -v`
    - Assertion: `save_position(book_id, char_position)` persists to `~/.pi/consume-book/bookmarks.json`
    - `get_position(book_id)` returns last saved position
    - `get_reading_stats(book_id)` returns total chars read, time spent

- [ ] **Task 3.5**: Implement EPUB support
  - Agent: code
  - Dependencies: Task 3.3
  - **Files**: `.pi/skills/consume-book/consume_book/epub.py`
  - **Definition of Done**:
    - Test: `python -m pytest consume_book/test_epub.py -v`
    - Assertion: `extract_text(epub_path)` returns plain text with chapter markers
    - Character positions map correctly between EPUB and extracted text

- [ ] **Task 3.6**: Implement CLI commands
  - Agent: code
  - Dependencies: Task 3.3, Task 3.4, Task 3.5
  - **Files**: `.pi/skills/consume-book/run.sh` (update)
  - **Definition of Done**:
    - Test: `./run.sh search "Emperor" --book "Horus_Rising"` returns results
    - Test: `./run.sh bookmark --book "test_id" --char-position 125000` saves position
    - Test: `./run.sh resume --book "test_id"` returns saved position
    - Test: `./run.sh note --book "test_id" --char-position 125000 --note "test"` adds note

### Phase 4: consume-youtube

- [ ] **Task 4.1**: Create consume-youtube directory structure
  - Agent: code
  - Dependencies: Task 1.1, Task 1.2, Task 1.3
  - **Files**: `.pi/skills/consume-youtube/SKILL.md`, `run.sh`, `pyproject.toml`
  - **Definition of Done**:
    - Test: `./run.sh info` runs without error
    - Assertion: Directory follows skill conventions

- [ ] **Task 4.2**: Implement transcript indexing
  - Agent: code
  - Dependencies: Task 4.1
  - **Files**: `.pi/skills/consume-youtube/consume_youtube/indexer.py`
  - **Definition of Done**:
    - Test: `python -m pytest consume_youtube/test_indexer.py -v`
    - Assertion: Scans `../../../run/youtube-transcripts/` directory, builds inverted index per channel
    - Index stored in `~/.pi/consume-youtube/indices/<channel>.json`

- [ ] **Task 4.3**: Implement transcript search
  - Agent: code
  - Dependencies: Task 4.2
  - **Files**: `.pi/skills/consume-youtube/consume_youtube/search.py`
  - **Definition of Done**:
    - Test: `python -m pytest consume_youtube/test_search.py -v`
    - Assertion: `search_transcripts(query, channel=None)` returns matches with (video_id, start, text, context)
    - Supports filtering by channel, time range

- [ ] **Task 4.4**: Implement topic modeling
  - Agent: code
  - Dependencies: Task 4.3
  - **Files**: `.pi/skills/consume-youtube/consume_youtube/topics.py`
  - **Definition of Done**:
    - Test: `python -m pytest consume_youtube/test_topics.py -v`
    - Assertion: `extract_topics(channel, min_videos=5)` returns list of topics with representative videos
    - Uses TF-IDF + clustering to identify recurring themes

- [ ] **Task 4.5**: Implement related video detection
  - Agent: code
  - Dependencies: Task 4.3
  - **Files**: `.pi/skills/consume-youtube/consume_youtube/related.py`
  - **Definition of Done**:
    - Test: `python -m pytest consume_youtube/test_related.py -v`
    - Assertion: `find_related(video_id, min_overlap=0.3)` returns list of related video IDs
    - Similarity based on shared transcript terms (cosine similarity)

- [ ] **Task 4.6**: Implement CLI commands
  - Agent: code
  - Dependencies: Task 4.3, Task 4.4, Task 4.5
  - **Files**: `.pi/skills/consume-youtube/run.sh` (update)
  - **Definition of Done**:
    - Test: `./run.sh search "siege" --channel "luetin09"` returns results
    - Test: `./run.sh topics --channel "luetin09"` returns topic list
    - Test: `./run.sh related --video "VIDEO_ID"` returns related videos
    - Test: `./run.sh note --video "VIDEO_ID" --timestamp 184.5 --note "test"` adds note

### Phase 5: Integration & Broadcast

- [ ] **Task 5.1**: Create unified documentation
  - Agent: code
  - Dependencies: Task 2.6, Task 3.6, Task 4.6
  - **Files**: `.pi/skills/consume-common/README.md`
  - **Definition of Done**:
    - Assertion: README explains architecture, shared components, skill-specific features
    - Includes examples for all three skills

- [ ] **Task 5.2**: Run all sanity checks
  - Agent: code
  - Dependencies: All previous tasks
  - **Definition of Done**:
    - Test: `cd .pi/skills/consume-common && python -m pytest sanity/ -v`
    - Test: `cd .pi/skills/consume-movie && ./sanity.sh`
    - Test: `cd .pi/skills/consume-book && ./sanity.sh`
    - Test: `cd .pi/skills/consume-youtube && ./sanity.sh`
    - Assertion: All tests pass

- [ ] **Task 5.3**: Broadcast skills to all IDEs
  - Agent: code
  - Dependencies: Task 5.2
  - **Files**: N/A (uses existing skills-broadcast)
  - **Definition of Done**:
    - Test: `./skills-broadcast/push-consume-skills.sh` (or equivalent)
    - Assertion: Skills appear in `.agent/skills/`, `.codex/skills/`, `.kilocode/skills/`

---

## Post-Completion Verification

After all tasks complete, verify:

1. **Horus can consume a movie**:

   ```bash
   cd .pi/skills/consume-movie
   ./run.sh search "rage" --movie "tywin_tyrion"
   ./run.sh clip --query "You are a Lannister" --output ~/clips/test.mkv
   ./run.sh note --movie "tywin_tyrion" --timestamp 125.5 --note "Manipulation pattern observed" --agent horus
   ```

2. **Horus can consume a book**:

   ```bash
   cd .pi/skills/consume-book
   ./run.sh search "Emperor" --book "Horus_Rising"
   ./run.sh bookmark --book "horus_rising" --char-position 125000
   ./run.sh note --book "horus_rising" --char-position 125000 --note "Doubt begins here" --agent horus
   ```

3. **Horus can consume YouTube**:

   ```bash
   cd .pi/skills/consume-youtube
   ./run.sh search "siege mentality" --channel "luetin09"
   ./run.sh note --video "VIDEO_ID" --timestamp 184.5 --note "Parallel to 40k" --agent horus
   ```

4. **Memory integration works**:
   ```bash
   cd .pi/skills/memory
   ./run.sh recall --q "Tywin manipulation pattern"
   # Should return Horus's note
   ```
