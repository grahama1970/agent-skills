# review-music Implementation Tasks

## Goal

**Analyze audio files to extract musical features and generate HMT taxonomy-mapped reviews for Horus persona.**

Location: `/home/graham/workspace/experiments/pi-mono/.pi/skills/review-music`

## Context

Build a music analysis pipeline that:
1. Extracts audio features using MIR tools (madmom, essentia, librosa)
2. Detects chord progressions and key
3. Transcribes lyrics with Whisper
4. Uses LLM chain-of-thought to generate multi-aspect reviews
5. Maps features to Horus Music Taxonomy (HMT) Bridge Attributes
6. Syncs to `/memory` for persona recall

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method | Sanity Script | Status |
|---------|------------|---------------|--------|
| librosa | `librosa.feature.mfcc()`, `librosa.feature.chroma_stft()`, `librosa.beat.beat_track()` | `sanity/librosa_features.py` | [x] PASS |
| faster-whisper | `WhisperModel().transcribe()` | `sanity/whisper_transcribe.py` | [x] PASS |
| madmom | `BeatTrackingProcessor`, `RNNBeatProcessor` | `sanity/madmom_beats.py` | [ ] OPTIONAL (build issues with Python 3.13) |
| essentia | `KeyExtractor`, `LoudnessEBUR128` | `sanity/essentia_key.py` | [ ] OPTIONAL (build issues with Python 3.13) |
| yt-dlp | `yt_dlp.YoutubeDL().download()` | N/A (well-known, verified in ingest-youtube) | N/A |

> Core dependencies (librosa, faster-whisper) verified. madmom/essentia are optional enhancements.

## Questions/Blockers

None - architecture defined in SKILL.md, HMT taxonomy verified in ingest-yt-history.

## Tasks

- [x] **Task 1**: Create Sanity Scripts for MIR Libraries
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - Notes: Create working examples for librosa, whisper (madmom/essentia optional due to build issues)
  - **Sanity**: N/A (this task creates the sanity scripts)
  - **Definition of Done**:
    - Test: `./sanity/librosa_features.py && ./sanity/whisper_transcribe.py`
    - Assertion: All core scripts exit 0 with valid output ✓

- [x] **Task 2**: Audio Loader Module
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - Notes: Load audio from file or YouTube URL, normalize to consistent format
  - **Sanity**: N/A (uses librosa.load - well-known)
  - **Definition of Done**:
    - Test: `tests/test_audio.py::test_load_audio_file`
    - Assertion: Loads mp3/wav/flac, returns numpy array with sample rate ✓

- [x] **Task 3**: Rhythm Feature Extraction (librosa primary, madmom optional)
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - Notes: Use librosa.beat.beat_track() as primary, madmom as optional enhancement
  - **Sanity**: `sanity/librosa_features.py`
  - **Definition of Done**:
    - Test: `tests/test_features.py::test_extract_rhythm_features`
    - Assertion: Returns bpm (float), beat_positions (list), tempo_variance (float), time_signature (str) ✓

- [x] **Task 4**: Harmony Feature Extraction (librosa primary, essentia optional)
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - Notes: Use librosa.feature.chroma_stft() for key/mode detection, essentia as optional enhancement
  - **Sanity**: `sanity/librosa_features.py`
  - **Definition of Done**:
    - Test: `tests/test_features.py::test_extract_harmony_features`
    - Assertion: Returns key (str), mode (str), scale (str) ✓

- [x] **Task 5**: Timbre Feature Extraction (librosa)
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Sanity**: `sanity/librosa_features.py`
  - **Definition of Done**:
    - Test: `tests/test_features.py::test_extract_timbre_features`
    - Assertion: Returns spectral_centroid, spectral_bandwidth, mfcc_mean, zero_crossing_rate ✓

- [x] **Task 6**: Dynamics Feature Extraction (librosa + scipy)
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - Notes: Use librosa.feature.rms() and scipy for loudness estimation, essentia as optional
  - **Sanity**: `sanity/librosa_features.py`
  - **Definition of Done**:
    - Test: `tests/test_features.py::test_extract_dynamics_features`
    - Assertion: Returns loudness_integrated (LUFS estimate), dynamic_range, loudness_range ✓

- [x] **Task 7**: Lyrics Transcription (Whisper)
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Sanity**: `sanity/whisper_transcribe.py`
  - **Definition of Done**:
    - Test: `tests/test_features.py::test_transcribe_lyrics`
    - Assertion: Returns lyrics text, language, word_timestamps ✓

- [x] **Task 8**: Feature Aggregator
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 3, Task 4, Task 5, Task 6, Task 7
  - Notes: Combine all feature extractors into unified pipeline
  - **Sanity**: N/A (orchestration code)
  - **Definition of Done**:
    - Test: `tests/test_features.py::test_extract_all_features`
    - Assertion: Returns complete feature dict with rhythm, harmony, timbre, dynamics, lyrics sections ✓

- [x] **Task 9**: LLM Music Theory Analyzer
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 8
  - Notes: Use chain-of-thought prompting to analyze features and generate music theory insights
  - **Sanity**: N/A (uses scillm - already verified)
  - **Definition of Done**:
    - Test: `tests/test_analysis.py::test_llm_music_analysis`
    - Assertion: Returns structured review with summary, music_theory, production, emotional_arc

- [x] **Task 10**: HMT Bridge Attribute Mapper
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 8
  - Notes: Map audio features to Bridge Attributes using rules from ingest-yt-history taxonomy
  - **Sanity**: `../ingest-yt-history/sanity/hmt_verifier.py` (reuse existing)
  - **Definition of Done**:
    - Test: `tests/test_taxonomy.py::test_map_to_bridges`
    - Assertion: Returns bridge_attributes list, collection_tags dict, tactical_tags list, confidence float

- [x] **Task 11**: Review Generator
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 9, Task 10
  - Notes: Combine LLM analysis with HMT mapping into final review JSON
  - **Sanity**: N/A (orchestration code)
  - **Definition of Done**:
    - Test: `tests/test_review.py::test_generate_review`
    - Assertion: Returns complete review JSON matching SKILL.md output format

- [x] **Task 12**: Memory Sync Integration
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 11
  - Notes: Sync reviews to /memory with proper taxonomy tags
  - **Sanity**: N/A (uses existing memory skill)
  - **Definition of Done**:
    - Test: `tests/test_review.py::test_sync_to_memory`
    - Assertion: Creates memory entry with category="music", bridge_attributes, collection_tags

- [x] **Task 13**: CLI Commands (run.sh)
  - Agent: general-purpose
  - Parallel: 4
  - Dependencies: Task 11, Task 12
  - Notes: Create analyze, features, review, batch commands
  - **Sanity**: N/A (integration)
  - **Definition of Done**:
    - Test: `./sanity.sh`
    - Assertion: All commands exit 0, help text works

## Parallel Execution Groups

| Group | Tasks | Description |
|-------|-------|-------------|
| 0 | Task 1 | Foundation - Sanity scripts |
| 1 | Task 2, 3, 4, 5, 6, 7 | Feature extractors (independent) |
| 2 | Task 8, 9, 10 | Aggregation and analysis |
| 3 | Task 11, 12 | Review generation and memory sync |
| 4 | Task 13 | CLI integration |

## Completion Criteria

1. `./run.sh analyze song.mp3` extracts all features and generates review
2. `./run.sh features song.mp3 --bpm --key` extracts specific features
3. `./run.sh review song.mp3 --sync-memory` generates full HMT-mapped review
4. `/memory recall --bridge Fragility --collection music` returns reviewed tracks
5. `./sanity.sh` exits 0

## Bridge Attribute → Audio Feature Mapping

| Bridge | Audio Indicators |
|--------|------------------|
| **Precision** | High tempo variance, polyrhythmic patterns, odd time signatures, technical passages |
| **Resilience** | Building dynamics, triumphant key progressions, crescendos, major keys |
| **Fragility** | Sparse instrumentation, minor keys, soft dynamics, acoustic timbre |
| **Corruption** | Distorted timbre, dissonance, harsh frequencies, industrial textures |
| **Loyalty** | Ceremonial rhythm, drone elements, choral textures, modal harmony |
| **Stealth** | Ambient textures, minimal beats, low spectral centroid, drone |

## Test Fixtures

Create sample audio files for testing:
- `fixtures/test_audio.wav` - Short (10s) audio clip with clear beat
- `fixtures/test_spoken.wav` - Short clip with speech for Whisper testing

## Research Notes

### Industry Leaders (2025-2026)
- **Suno** - Market leader in text-to-music, generates full songs (instrumentals, vocals, lyrics)
- **Udio** - High audio fidelity, strong handling of complex song structures

### Academic Papers
- **Music Flamingo** - Multi-aspect music captioning using MIR tools + LLM
- **MERT** - Acoustic music understanding embeddings (foundation model)
- **CLAP** - Audio-text joint embeddings for semantic search

### MIR Tool Stack
- **madmom** - Beat/tempo/downbeat detection (neural network based)
- **essentia** - Key/mode/loudness extraction (comprehensive audio analysis)
- **librosa** - MFCC/spectral features (Python standard for audio)
- **music21** - Symbolic music theory analysis (for MIDI/notation)
- **Chordino/autochord** - Chord progression detection

### Music Generation Models (Reference)
- **Meta Audiocraft/MusicGen** - github.com/facebookresearch/audiocraft (17k+ stars)
  - Text-to-music, melody-conditioned generation
  - Has Encodec for audio encoding/decoding (useful for embeddings)
- **ACE-Step** - github.com/ace-step/ACE-Step
  - State-of-the-art foundation model for full songs
  - Lyric-to-song with structure understanding
