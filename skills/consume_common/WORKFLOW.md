# Book-Before-Movie Workflow

This document describes the recommended workflow for consuming books before their movie adaptations to maximize contextual learning for Horus persona training.

## Why Read Books First?

Reading source material before watching adaptations provides:

1. **Textual Grounding** - Understanding character motivations, internal monologue, and world-building details that don't transfer to visual media
2. **Character Understanding** - Deeper comprehension of character psychology for persona coherence
3. **Comparative Analysis** - Ability to note what was changed, condensed, or emphasized in adaptation
4. **Richer Emotional Context** - Literary descriptions of emotions complement visual/audio exemplars
5. **Voice Training** - Audiobook narration provides prosody and delivery patterns for TTS

## Pipeline Overview

```
┌──────────┐     ┌─────────────┐     ┌──────────────────┐     ┌──────────────┐     ┌─────────────────┐
│ /dogpile │ --> │ ingest-book │ --> │ ingest-audiobook │ --> │ consume-book │ --> │  ingest-movie   │
│ Research │     │  (Readarr)  │     │    (Audible)     │     │  (Read/Note) │     │ (Emotion clips) │
└──────────┘     └─────────────┘     └──────────────────┘     └──────────────┘     └─────────────────┘
     │                 │                      │                      │                      │
     v                 v                      v                      v                      v
  Reviews          Acquire             Download audio          Study text            Extract scenes
  Summaries        eBooks              Transcribe              Take notes            Transcribe audio
  Comparisons      via NZB             Voice training          Track progress        Create personas
```

## Step-by-Step Workflow

### Phase 0: Research (dogpile)

Before acquiring content, use `/dogpile` to research books, movies, and reviews:

```bash
cd .pi/skills/dogpile

# Research books with strong emotional themes
./run.sh search "war novels betrayal loyalty themes" --preset book_reviews

# Find book-to-movie adaptations with emotional depth
./run.sh search "Dune adaptation comparison book vs movie" --preset general

# Research actor performances for emotion modeling
./run.sh search "Daniel Day-Lewis intense performances rage" --preset movie_scenes

# Get balanced reviews (positive and negative) for context
./run.sh search "There Will Be Blood critical analysis" --sources letterboxd,rottentomatoes
```

**Dogpile provides:**
- Book summaries and critical reception
- Movie reviews with scene-specific commentary
- Comparisons between adaptations and source material
- Actor performance analysis for emotion modeling
- Community discussions about thematic elements

### Phase 1: Book Acquisition (ingest-book)

```bash
cd .pi/skills/ingest-book

# 1. Search for the book
./run.sh search "Dune Frank Herbert"

# 2. Check NZB availability if Readarr metadata fails
./run.sh nzb-search "Dune Frank Herbert epub"

# 3. Add book to Readarr (auto-monitors for download)
./run.sh add "Dune"

# 4. Wait for download to complete (check Readarr UI or queue)
```

### Phase 1b: Audiobook Acquisition (ingest-audiobook)

For voice training and prosody analysis, acquire audiobook versions:

```bash
cd .pi/skills/ingest-audiobook

# List available Warhammer 40k audiobooks (for Horus voice model)
./run.sh list-warhammer

# Download Warhammer audiobooks from Audible
./run.sh download-warhammer

# Or download all audiobooks
./run.sh download-all

# Process a specific audiobook (decrypt + transcribe)
./run.sh ingest "Horus_Rising.aax"

# Process all audiobooks in inbox
./run.sh ingest-all
```

**Audiobook ingestion provides:**
- Decrypted M4B audio files for voice training
- Whisper transcriptions synced with audio
- Professional narrator prosody patterns
- Character voice variations within single works

**Voice Training Use Cases:**
1. **Narrator Prosody** - Extract pacing, emphasis, emotional delivery
2. **Character Voices** - Identify and extract specific character dialogue
3. **Emotional Range** - Map audio segments to textual emotion annotations
4. **TTS Training Data** - Paired audio-text for fine-tuning

### Phase 2: Book Consumption (consume-book)

```bash
cd .pi/skills/consume-book

# 1. Sync downloaded books to consumption registry
./run.sh sync --books-dir ~/workspace/experiments/Readarr/books

# 2. List available books
./run.sh list

# 3. Search for key passages (e.g., characters relevant to movie scenes)
./run.sh search "Paul Atreides fear" --book <book_id>

# 4. Take notes at significant positions
./run.sh note --book <book_id> --char-position 45000 \
  --note "Paul's internal conflict about prescience and destiny"

# 5. Track reading progress
./run.sh bookmark --book <book_id> --char-position 125000

# 6. Resume later
./run.sh resume --book <book_id>
```

### Phase 3: Movie Emotion Extraction (ingest-movie)

```bash
cd .pi/skills/ingest-movie

# 1. Get recommendations for emotion-rich movies related to the book
./run.sh agent recommend camaraderie --actor "Timothée Chalamet" \
  --library /mnt/storage12tb/media/movies

# 2. Search for the movie in NZBGeek
./run.sh search "Dune 2021"

# 3. Extract emotion scenes from subtitles
./run.sh scenes extract \
  --subtitle "/path/to/Dune.2021.en.srt" \
  --tag camaraderie \
  --video "/path/to/Dune.2021.mkv" \
  --clip-dir ./clips/dune_camaraderie

# 4. Quick single-scene extraction (if you know the timestamp)
./run.sh agent quick \
  --movie "/path/to/Dune (2021)" \
  --emotion camaraderie \
  --scene "Atreides family departure from Caladan" \
  --timestamp "00:15:30-00:18:00"
```

## Cross-Reference Pattern

When taking notes during reading, consider what will be useful for emotion extraction:

| Book Note Category | Movie Extraction Use |
|--------------------|---------------------|
| Character relationships | Tag scenes with character pairs |
| Emotional peaks (fear, rage) | Search subtitles for matching cues |
| Key dialogue | Verify adaptation fidelity |
| Internal monologue | Compare to visual/audio expression |
| Setting descriptions | Establish scene context |

### Example: Dune Workflow

```bash
# PHASE 1: Read the book
cd .pi/skills/consume-book
./run.sh sync --books-dir ~/library/books
./run.sh search "Gom Jabbar" --book dune-id

# Take notes on Paul's fear during the test
./run.sh note --book dune-id --char-position 12500 \
  --note "Paul masters fear through Bene Gesserit training. Key line: 'Fear is the mind-killer.' This is internal resolve, not external rage."

# PHASE 2: Extract movie scene
cd .pi/skills/ingest-movie
./run.sh scenes find --subtitle ./Dune.2021.en.srt --query "fear is the mind"

# Extract the Gom Jabbar scene
./run.sh agent quick \
  --movie "/media/movies/Dune (2021)" \
  --emotion resolve \
  --scene "Gom Jabbar test - fear mastery" \
  --timestamp "00:22:00-00:25:30"
```

## Emotion Mapping: Book to Movie

| Book Emotion | ingest-movie Tag | Actor Model |
|--------------|------------------|-------------|
| Rage/Fury | `rage` | Daniel Day-Lewis |
| Contempt/Disdain | `anger` | Al Pacino |
| Grief/Loss | `sorrow` | Russell Crowe |
| Guilt/Shame | `regret` | George Carlin |
| Brotherhood/Loyalty | `camaraderie` | Javier Bardem |

## Integration with Memory

Both consume-book and ingest-movie integrate with the memory skill:

```bash
# Book notes are automatically stored
./run.sh note --book X --char-position Y --note "insight"
# -> Calls: memory learn --problem "Consumed book: Title" --solution "insight"

# Movie transcriptions create persona entries
./run.sh transcribe clip.mkv --emotion rage --scene "confrontation"
# -> Creates persona JSON for knowledge graph import
```

## Batch Processing

For systematic persona training across multiple book-movie pairs:

```bash
# 1. Create a batch manifest of book-movie pairs
cat > training_pairs.json << 'EOF'
[
  {"book": "Dune", "movie": "Dune (2021)", "emotions": ["camaraderie", "fear"]},
  {"book": "The Godfather", "movie": "The Godfather (1972)", "emotions": ["anger", "regret"]},
  {"book": "Blood Meridian", "movie": null, "emotions": ["rage"]}
]
EOF

# 2. Process each pair
for pair in $(jq -c '.[]' training_pairs.json); do
  book=$(echo $pair | jq -r '.book')
  movie=$(echo $pair | jq -r '.movie')

  # Consume book first
  cd .pi/skills/consume-book
  ./run.sh search "$book" --json > /tmp/book_notes.json

  # Then extract movie scenes (if movie exists)
  if [ "$movie" != "null" ]; then
    cd .pi/skills/ingest-movie
    ./run.sh batch plan --emotion $(echo $pair | jq -r '.emotions | join(",")')
    ./run.sh batch run --manifest batch_manifest.json
  fi
done
```

## Research-Driven Content Discovery

Use `/dogpile` to discover and prioritize content before acquisition:

### Finding Emotion-Rich Content

```bash
cd .pi/skills/dogpile

# Research rage/intensity performances
./run.sh search "movies with explosive confrontation scenes DDL intensity" \
  --sources imdb,letterboxd,reddit

# Find books with strong internal monologue (for persona grounding)
./run.sh search "novels unreliable narrator psychological depth" \
  --sources goodreads,reddit

# Research audiobook narrator quality
./run.sh search "best Warhammer 40k audiobook narrators Jonathan Keeble" \
  --sources audible,reddit
```

### Comparing Adaptations

```bash
# Get balanced reviews on adaptation fidelity
./run.sh search "Dune 2021 vs book differences what was cut" \
  --sources reddit,letterboxd

# Research specific scene adaptations
./run.sh search "Godfather baptism scene book vs movie Coppola" \
  --sources filmanalysis,reddit
```

### Building Training Queues

```bash
# Research movies by emotion for batch processing
./run.sh search "movies about brotherhood and loyalty war films" \
  --output camaraderie_candidates.md

# Then feed to ingest-movie
cd .pi/skills/ingest-movie
./run.sh batch plan --emotion camaraderie
```

## Curated Book-Movie Pairs for Persona Training

| Emotion | Book | Movie | Notes |
|---------|------|-------|-------|
| **Rage** | Blood Meridian | N/A (no adaptation) | Book-only for extreme violence |
| **Rage** | There Will Be Blood | There Will Be Blood (2007) | Loosely adapted from "Oil!" |
| **Camaraderie** | Dune | Dune (2021), Dune Part Two (2024) | House Atreides loyalty |
| **Sorrow** | Gladiator (novelization) | Gladiator (2000) | Loss and vengeance |
| **Regret** | The Godfather | The Godfather (1972) | Michael's transformation |
| **Anger** | Apocalypse Now (Heart of Darkness) | Apocalypse Now (1979) | Kurtz's descent |

## Troubleshooting

### Readarr metadata search returns 503
The external metadata providers (GoodReads, OpenLibrary) may rate-limit requests. Use NZB search as a fallback:
```bash
./run.sh nzb-search "Book Title author:Author Name"
```

### Book not syncing to consume-book
Verify the book file exists and has a supported extension:
```bash
ls ~/workspace/experiments/Readarr/books/**/*.{epub,pdf,mobi}
./run.sh sync --books-dir ~/workspace/experiments/Readarr/books
```

### Movie subtitles missing emotion cues
Some subtitle files lack stage directions. Look for SDH (Subtitles for Deaf/Hard of Hearing) versions which include [LAUGHS], [SHOUTS], etc.

### Audiobook decryption fails
Ensure you have Audible activation bytes configured:
```bash
# Re-run quickstart to refresh credentials
uvx --from audible-cli audible quickstart
```

### Whisper transcription is slow
Use the `turbo` model for faster processing with good accuracy:
```bash
./run.sh ingest "book.m4b"  # Uses turbo by default
```

## Complete Example: Horus Heresy Pipeline

A full example for building the Horus Lupercal voice model:

```bash
# 1. Research the series
cd .pi/skills/dogpile
./run.sh search "Horus Heresy audiobook narrators best performances" --sources reddit,audible

# 2. Download Warhammer audiobooks
cd .pi/skills/ingest-audiobook
./run.sh list-warhammer
./run.sh download-warhammer

# 3. Transcribe audiobooks
./run.sh ingest-all

# 4. Sync transcriptions to consume-book
cd .pi/skills/consume-book
./run.sh sync --books-dir ~/clawd/library/books

# 5. Study and annotate
./run.sh search "Horus Lupercal" --book horus-rising-id
./run.sh note --book horus-rising-id --char-position 50000 \
  --note "Horus's charisma and command presence. Voice should convey authority with warmth."

# 6. Extract movie scenes with similar emotional register
cd .pi/skills/ingest-movie
./run.sh agent recommend camaraderie --actor "Gerard Butler"
./run.sh agent quick --movie "300" --emotion camaraderie --scene "This is Sparta speech"
```
