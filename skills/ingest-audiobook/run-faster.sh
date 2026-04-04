#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Directories
INBOX="${HOME}/clawd/library/inbox"
LIBRARY="${HOME}/clawd/library/books"

# Ensure directories exist
mkdir -p "$INBOX" "$LIBRARY"

# Command: ingest <filename> using faster-whisper
cmd_ingest_fast() {
    local filename="$1"
    local filepath="${INBOX}/${filename}"

    if [[ ! -f "$filepath" ]]; then
        echo "Error: File not found: $filepath" >&2
        return 1
    fi

    # Extract filename without extension
    local basename="${filename%.*}"
    local extension="${filename##*.}"
    local book_dir="${LIBRARY}/${basename}"

    echo "==> Processing: $filename"
    mkdir -p "$book_dir"

    # Handle AAX decryption if needed
    local transcribe_file="$filepath"
    local transcribe_basename="$basename"

    if [[ "$extension" == "aax" ]] || [[ "$extension" == "aaxc" ]]; then
        echo "==> Decrypting AAX file..."
        local activation_bytes=$(uvx --from audible-cli audible activation-bytes 2>&1 | tail -1)

        # Convert AAX to M4B using ffmpeg
        local decrypted="${book_dir}/audio.m4b"
        if ! ffmpeg -activation_bytes "$activation_bytes" -i "$filepath" -c copy "$decrypted" -y >/dev/null 2>&1; then
            echo "Error: Failed to decrypt AAX file" >&2
            return 1
        fi

        transcribe_file="$decrypted"
        transcribe_basename="audio"
        extension="m4b"
    fi

    # Transcribe with faster-whisper (GPU accelerated)
    echo "==> Transcribing with faster-whisper (GPU)..."
    echo "    Model: turbo, Device: cuda"
    
    # Use Python script with faster-whisper
    python3 << PYTHON
from faster_whisper import WhisperModel
from pathlib import Path

model = WhisperModel("turbo", device="cuda", compute_type="float16")

print("    Loading audio...")
segments, info = model.transcribe(
    "${transcribe_file}",
    language="en",
    beam_size=5,
    vad_filter=True,  # Voice activity detection to skip silence
)

print(f"    Detected language: {info.language} (probability: {info.language_probability:.2f})")
print(f"    Processing {info.duration:.1f} seconds of audio...")

output_file = Path("${book_dir}/${transcribe_basename}.txt")
with open(output_file, "w", encoding="utf-8") as f:
    for segment in segments:
        f.write(f"{segment.text}\n")
        
print(f"    Transcription complete!")
PYTHON

    # Move source audio if not already moved
    if [[ "$transcribe_file" == "$filepath" ]]; then
        echo "==> Moving audio file..."
        mv "$filepath" "${book_dir}/audio.${extension}"
    else
        # Remove original AAX, keep decrypted version
        rm "$filepath"
    fi

    # Rename transcript to text.md
    if [[ -f "${book_dir}/${transcribe_basename}.txt" ]]; then
        mv "${book_dir}/${transcribe_basename}.txt" "${book_dir}/text.md"
        echo "==> Transcript saved to: ${book_dir}/text.md"
    else
        echo "Warning: Transcript file not found" >&2
    fi

    echo "==> Done! Output: $book_dir"
}

# Command: ingest-all using faster-whisper
cmd_ingest_all_fast() {
    echo "==> Processing all audio files with faster-whisper (GPU)..."

    local count=0
    local failed=0

    # Find all audio files
    while IFS= read -r -d '' file; do
        filename=$(basename "$file")
        echo ""
        echo "==> [$((count + failed + 1))] Processing: $filename"

        if cmd_ingest_fast "$filename"; then
            ((count++))
        else
            echo "Warning: Failed to process $filename" >&2
            ((failed++))
        fi
    done < <(find "$INBOX" -type f \( -name "*.mp3" -o -name "*.m4a" -o -name "*.m4b" -o -name "*.wav" -o -name "*.aax" -o -name "*.aaxc" \) -print0)

    echo ""
    echo "==> Summary: Processed $count files, $failed failed"

    if [[ $failed -gt 0 ]]; then
        return 1
    fi
}

# Main
case "${1:-}" in
    ingest)
        shift
        cmd_ingest_fast "$@"
        ;;
    ingest-all)
        cmd_ingest_all_fast
        ;;
    *)
        echo "Usage: $0 {ingest|ingest-all} [filename]"
        exit 1
        ;;
esac
