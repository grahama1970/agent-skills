# Audiobook Ingest Skill - Horus Lupercal Voice & Personality

Complete pipeline for building a Horus Lupercal AI character with voice cloning and personality modeling from Warhammer 40k audiobooks.

## Current Status

### ✅ Completed

1. **Downloaded 18 Warhammer 40k Audiobooks** (~11GB)
   - Horus Heresy series
   - Gaunt's Ghosts series
   - All in AAX format (Audible's encrypted format)

2. **AAX Decryption Pipeline**
   - Automatic activation bytes retrieval
   - FFmpeg-based decryption to M4B
   - Fully automated in scripts

3. **GPU-Accelerated Transcription**
   - faster-whisper with CUDA support
   - RTX A5000 (24GB VRAM)
   - ~10-15x faster than CPU
   - Setup: `./setup-gpu.sh` (one-time)

4. **Character Extraction Tools**
   - `horus-extraction/extract_dialogue.py` - Extract Horus dialogue
   - `horus-extraction/warhammer_lexicon.py` - 40k pronunciation dictionary

### ⏳ In Progress

- GPU transcription test running (verifying pipeline works)
- Estimated: 2-4 hours for all 18 books on GPU

## Quick Start

### 1. Download Books

```bash
# Login to Audible (one-time)
uvx --from audible-cli audible quickstart

# Download all Warhammer 40k books
./run.sh download-warhammer
```

### 2. Transcribe Books

**GPU-accelerated (recommended):**
```bash
# One-time setup
./setup-gpu.sh

# Process all books
./run.sh ingest-all-gpu
```

**CPU (slower fallback):**
```bash
./run.sh ingest-all
```

### 3. Extract Horus Character Data

```bash
cd horus-extraction
python3 extract_dialogue.py
```

Output:
- `output/horus_dialogue.jsonl` - Direct quotes from Horus
- `output/horus_thoughts.jsonl` - Internal monologue
- `output/horus_descriptions.jsonl` - Narrator descriptions
- `output/horus_all_text.txt` - Human-readable combined output

## Pipeline Architecture

```
Phase 1: Data Collection (Current)
├─ Download audiobooks (audible-cli)
├─ Decrypt AAX → M4B (ffmpeg)
└─ Transcribe audio → text (faster-whisper GPU)

Phase 2: Character Extraction (Next)
├─ Extract Horus dialogue from transcripts
├─ Speaker diarization (identify Horus vs narrator vs others)
├─ Align dialogue to audio timestamps
└─ Build reference datasets

Phase 3A: Personality Model
├─ Collect Horus dialogue + descriptions
├─ Fine-tune LLM (Llama/Mistral)
└─ Test personality responses

Phase 3B: Voice Clone
├─ Extract clean Horus audio segments
├─ Select 10-30 best reference clips
├─ Train XTTS-v2 voice model
└─ Generate speech from personality output

Phase 4: Integration
└─ LLM generates Horus dialogue → XTTS-v2 speaks it
```

## File Structure

```
~/clawd/library/
├── inbox/                          # Downloaded AAX files
└── books/                          # Processed books
    └── <BookTitle>/
        ├── audio.m4b              # Decrypted audio
        └── text.md                # Whisper transcript

skills/audiobook-ingest/
├── run.sh                         # Main script
├── setup-gpu.sh                   # GPU environment setup
├── .venv/                         # Python environment (faster-whisper)
└── horus-extraction/
    ├── extract_dialogue.py        # Character dialogue extraction
    ├── warhammer_lexicon.py       # 40k pronunciation dictionary
    └── output/                    # Extracted character data
        ├── horus_dialogue.jsonl
        ├── horus_thoughts.jsonl
        ├── horus_descriptions.jsonl
        └── horus_all_text.txt
```

## Commands Reference

### Download
- `./run.sh list-warhammer` - List Warhammer books in library
- `./run.sh download-warhammer` - Download Warhammer books only
- `./run.sh download-all` - Download entire Audible library

### Transcribe
- `./run.sh ingest <file>` - Transcribe one file (CPU)
- `./run.sh ingest-all` - Transcribe all files (CPU)
- `./run.sh ingest-gpu <file>` - Transcribe one file (GPU, fast)
- `./run.sh ingest-all-gpu` - Transcribe all files (GPU, fast)

### Extract Character Data
- `cd horus-extraction && python3 extract_dialogue.py`

## Performance Metrics

**Transcription Speed (12-hour audiobook):**
- CPU (openai-whisper): 30-60 minutes
- GPU (faster-whisper on RTX A5000): 5-10 minutes
- Speedup: ~10-15x

**Full Collection (18 books, ~126 hours total):**
- CPU: 9-18 hours
- GPU: 1.5-3 hours

## Next Steps: Voice Cloning

After transcription completes, follow `scratch.md` recommendations:

1. **Speaker Diarization**
   ```bash
   pip install pyannote.audio
   # Identify which segments are Horus speaking
   ```

2. **Extract Audio Clips**
   - Use transcript timestamps
   - Extract clean 10-30 second Horus clips
   - Store in `horus_audio_refs/`

3. **Voice Clone with XTTS-v2**
   ```python
   from TTS.api import TTS

   tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
   tts.tts_to_file(
       text="I was there the day Horus slew the Emperor.",
       speaker_wav=["horus_audio_refs/*.wav"],
       language="en",
       file_path="horus_output.wav"
   )
   ```

4. **Apply 40k Lexicon**
   ```python
   from horus_extraction.warhammer_lexicon import apply_lexicon

   text = apply_lexicon("The Warmaster Horus Lupercal stood on Isstvan III.")
   # Ensures proper pronunciation of 40k terms
   ```

## Legal Notice

This project is for **personal learning and educational use only**. The audiobooks are copyrighted by Games Workshop and Black Library. Voice cloning uses professional voice actor performances. Do not distribute or commercialize.

## Troubleshooting

**GPU not detected:**
```bash
nvidia-smi  # Verify GPU is available
./setup-gpu.sh  # Reinstall faster-whisper
```

**Transcript file missing:**
- Check `~/clawd/library/books/<Title>/text.md`
- Re-run with verbose: Remove `--verbose False` flag

**AAX decryption fails:**
```bash
# Re-authenticate with Audible
uvx --from audible-cli audible quickstart
```

## References

- [faster-whisper GitHub](https://github.com/SYSTRAN/faster-whisper)
- [Coqui TTS (XTTS-v2)](https://docs.coqui.ai/en/latest/models/xtts.html)
- [Voice Cloning Guide](./scratch.md)
- [Warhammer 40k Lexicon](./horus-extraction/warhammer_lexicon.py)
