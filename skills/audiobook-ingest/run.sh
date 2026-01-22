#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Directories
INBOX="${HOME}/clawd/library/inbox"
LIBRARY="${HOME}/clawd/library/books"

# Ensure directories exist
mkdir -p "$INBOX" "$LIBRARY"

# Helper function to show usage
show_usage() {
    cat <<'EOF'
Usage: run.sh <command> [args]

Commands:
  list-warhammer        List all Warhammer 40k books in your library
  download-warhammer    Download all Warhammer 40k books
  download-all          Download all books from Audible library
  ingest <filename>     Process a single file from inbox (CPU, slow)
  ingest-all            Process all audio files in inbox (CPU, slow)
  ingest-gpu <filename> Process a single file with GPU (fast, requires setup)
  ingest-all-gpu        Process all files with GPU (fast, requires setup)
  decrypt-all           Decrypt all AAX files in parallel (fast, CPU)
  transcribe-all        Transcribe all decrypted M4B files (GPU, basic)
  transcribe            Transcribe with rich progress display (recommended)
  status                Show transcription progress (--json for agents)
  monitor               Live TUI dashboard (like nvtop)
  watchdog              Auto-restart on hangs (10min timeout)
  pipeline              Full parallel pipeline: decrypt-all + transcribe
  help                  Show this help message

GPU Setup (one-time):
  ./setup-gpu.sh        Set up faster-whisper GPU environment

Examples:
  ./run.sh list-warhammer
  ./run.sh download-warhammer
  ./run.sh download-all
  ./run.sh ingest "book.mp3"
  ./run.sh ingest-all
  ./run.sh ingest-gpu "book.aax"         # GPU-accelerated (much faster!)
  ./run.sh ingest-all-gpu                 # GPU-accelerated batch
EOF
}

# Command: list-warhammer
cmd_list_warhammer() {
    local library_export="${HOME}/audible-library.json"

    echo "==> Exporting library..."
    uvx --from audible-cli audible library export --output "$library_export"

    echo ""
    echo "=== Your Warhammer 40k Collection ==="
    grep -iE "Warhammer|Horus|Gaunt|40,000|Eisenhorn|Ravenor|Siege of Terra" "$library_export" | \
        awk -F'\t' '{printf "%-15s %s\n", $1, $2}' | \
        nl
}

# Command: download-warhammer
cmd_download_warhammer() {
    local library_export="${HOME}/audible-library.json"

    echo "==> Exporting library to find Warhammer books..."
    uvx --from audible-cli audible library export --output "$library_export"

    # Get all Warhammer book ASINs
    local asins=$(grep -iE "Warhammer|Horus|Gaunt|40,000|Eisenhorn|Ravenor|Siege of Terra" "$library_export" | \
        awk -F'\t' '{print $1}')

    local count=$(echo "$asins" | wc -l)
    echo "==> Found $count Warhammer 40k books"
    echo ""

    local downloaded=0
    local failed=0

    # Download each book by ASIN
    for asin in $asins; do
        local title=$(grep "^$asin" "$library_export" | awk -F'\t' '{print $2}')
        echo "==> [$((downloaded + failed + 1))/$count] Downloading: $title (ASIN: $asin)"

        if uvx --from audible-cli audible download --asin "$asin" --aax --output-dir "$INBOX" --no-confirm; then
            ((downloaded++))
        else
            echo "Warning: Failed to download $title" >&2
            ((failed++))
        fi
        echo ""
    done

    echo "==> Download complete: $downloaded succeeded, $failed failed"

    if [[ $failed -gt 0 ]]; then
        return 1
    fi
}

# Command: download-all
cmd_download_all() {
    echo "==> Downloading all books from Audible library..."
    uvx --from audible-cli audible download --all --aax --output-dir "$INBOX" --no-confirm
}

# Command: ingest <filename>
cmd_ingest() {
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
    local activation_bytes=""

    if [[ "$extension" == "aax" ]] || [[ "$extension" == "aaxc" ]]; then
        echo "==> Decrypting AAX file..."
        activation_bytes=$(uvx --from audible-cli audible activation-bytes 2>&1 | tail -1)

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

    # Transcribe audio to text (suppress progress bars)
    echo "==> Transcribing audio with Whisper turbo model..."
    echo "    This may take a while depending on audio length..."
    uvx --from openai-whisper whisper "$transcribe_file" \
        --model turbo \
        --output_format txt \
        --output_dir "$book_dir" \
        --verbose False 2>&1 | grep -E "(Detecting|Done)" || true

    # Move source audio if not already moved
    if [[ "$transcribe_file" == "$filepath" ]]; then
        echo "==> Moving audio file..."
        mv "$filepath" "${book_dir}/audio.${extension}"
    else
        # Remove original AAX, keep decrypted version
        rm "$filepath"
    fi

    # Rename transcript to text.md (handle both original and decrypted filenames)
    if [[ -f "${book_dir}/${transcribe_basename}.txt" ]]; then
        mv "${book_dir}/${transcribe_basename}.txt" "${book_dir}/text.md"
        echo "==> Transcript saved to: ${book_dir}/text.md"
    else
        echo "Warning: Transcript file not found at ${book_dir}/${transcribe_basename}.txt" >&2
    fi

    echo "==> Done! Output: $book_dir"
}

# Command: ingest-all
cmd_ingest_all() {
    echo "==> Processing all audio files in inbox..."

    local count=0
    local failed=0

    # Find all audio files
    while IFS= read -r -d '' file; do
        filename=$(basename "$file")
        echo ""
        echo "==> [$((count + 1))] Processing: $filename"

        if cmd_ingest "$filename"; then
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

# Command: ingest-gpu <filename> (GPU-accelerated with faster-whisper)
cmd_ingest_gpu() {
    local filename="$1"
    local filepath="${INBOX}/${filename}"

    if [[ ! -f "$filepath" ]]; then
        echo "Error: File not found: $filepath" >&2
        return 1
    fi

    # Check for GPU setup
    if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
        echo "Error: GPU environment not set up. Run ./setup-gpu.sh first" >&2
        return 1
    fi

    # Extract filename without extension
    local basename="${filename%.*}"
    local extension="${filename##*.}"
    local book_dir="${LIBRARY}/${basename}"

    echo "==> Processing: $filename (GPU-accelerated)"
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

    # Transcribe with faster-whisper (GPU)
    echo "==> Transcribing with faster-whisper (GPU: RTX A5000)..."
    echo "    Model: turbo, Compute: float16, VAD: enabled"

    "$SCRIPT_DIR/.venv/bin/python3" << PYTHON
from faster_whisper import WhisperModel
from pathlib import Path
import sys

try:
    model = WhisperModel("turbo", device="cuda", compute_type="float16")

    print("    Transcribing audio...", file=sys.stderr)
    segments, info = model.transcribe(
        "${transcribe_file}",
        language="en",
        beam_size=5,
        vad_filter=True,
    )

    print(f"    Language: {info.language} ({info.language_probability:.1%})", file=sys.stderr)
    print(f"    Duration: {info.duration:.1f}s", file=sys.stderr)

    output_file = Path("${book_dir}/${transcribe_basename}.txt")
    with open(output_file, "w", encoding="utf-8") as f:
        for segment in segments:
            f.write(f"{segment.text}\n")

    print("    ✓ Transcription complete", file=sys.stderr)
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
PYTHON

    if [[ $? -ne 0 ]]; then
        echo "Error: Transcription failed" >&2
        return 1
    fi

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
        return 1
    fi

    echo "==> Done! Output: $book_dir"
}

# Command: ingest-all-gpu (GPU-accelerated batch)
cmd_ingest_all_gpu() {
    echo "==> Processing all audio files with GPU acceleration..."

    local count=0
    local failed=0

    # Find all audio files
    while IFS= read -r -d '' file; do
        filename=$(basename "$file")
        echo ""
        echo "==> [$((count + failed + 1))] Processing: $filename"

        if cmd_ingest_gpu "$filename"; then
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

# Helper: decrypt a single AAX file
decrypt_aax() {
    local filepath="$1"
    local filename=$(basename "$filepath")
    local basename="${filename%.*}"
    local book_dir="${LIBRARY}/${basename}"

    # Skip if already decrypted
    if [[ -f "${book_dir}/audio.m4b" ]]; then
        echo "[SKIP] Already decrypted: $basename"
        return 0
    fi

    echo "[DECRYPT] Starting: $basename"
    mkdir -p "$book_dir"

    local activation_bytes=$(uvx --from audible-cli audible activation-bytes 2>&1 | tail -1)

    if ffmpeg -activation_bytes "$activation_bytes" -i "$filepath" -c copy "${book_dir}/audio.m4b" -y >/dev/null 2>&1; then
        echo "[DECRYPT] Done: $basename"
        rm "$filepath"  # Remove original AAX after successful decrypt
        return 0
    else
        echo "[DECRYPT] FAILED: $basename" >&2
        return 1
    fi
}
export -f decrypt_aax
export LIBRARY

# Command: decrypt-all (parallel AAX decryption)
cmd_decrypt_all() {
    local jobs="${1:-4}"
    echo "==> Decrypting all AAX files with $jobs parallel jobs..."

    local aax_files=$(find "$INBOX" -name "*.aax" -o -name "*.aaxc" 2>/dev/null | wc -l)
    echo "==> Found $aax_files AAX files to decrypt"

    if [[ $aax_files -eq 0 ]]; then
        echo "==> No AAX files to decrypt"
        return 0
    fi

    # Use xargs for parallel execution (portable)
    find "$INBOX" \( -name "*.aax" -o -name "*.aaxc" \) -print0 2>/dev/null | \
        xargs -0 -P "$jobs" -I{} bash -c 'decrypt_aax "$@"' _ {}

    echo ""
    echo "==> Decryption complete!"
    echo "==> Decrypted M4B files:"
    find "$LIBRARY" -name "audio.m4b" -print | wc -l
}

# Command: transcribe-all (GPU transcription of M4B files)
cmd_transcribe_all() {
    echo "==> Transcribing all decrypted M4B files (GPU)..."

    # Check for GPU setup
    if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
        echo "Error: GPU environment not set up. Run ./setup-gpu.sh first" >&2
        return 1
    fi

    local count=0
    local failed=0
    local skipped=0

    # Collect all M4B files into array first (avoids heredoc stdin conflict)
    local -a m4b_files=()
    while IFS= read -r -d '' f; do
        m4b_files+=("$f")
    done < <(find "$LIBRARY" -name "audio.m4b" -print0)

    local total=${#m4b_files[@]}
    echo "==> Found $total M4B files"

    # Process each file
    for m4b_file in "${m4b_files[@]}"; do
        local book_dir=$(dirname "$m4b_file")
        local book_name=$(basename "$book_dir")

        # Skip if transcript already exists
        if [[ -f "${book_dir}/text.md" ]]; then
            echo "[SKIP] Already transcribed: $book_name"
            ((skipped++)) || true
            continue
        fi

        echo ""
        echo "==> [$((count + failed + 1))/$((total - skipped))] Transcribing: $book_name"

        # Transcribe with faster-whisper (GPU)
        if "$SCRIPT_DIR/.venv/bin/python3" << PYTHON
from faster_whisper import WhisperModel
from pathlib import Path
import sys

try:
    model = WhisperModel("turbo", device="cuda", compute_type="float16")
    segments, info = model.transcribe(
        "${m4b_file}",
        language="en",
        beam_size=5,
        vad_filter=True,
    )
    print(f"    Language: {info.language} ({info.language_probability:.1%})", file=sys.stderr)
    print(f"    Duration: {info.duration:.1f}s ({info.duration/3600:.1f}h)", file=sys.stderr)

    output_file = Path("${book_dir}/text.md")
    with open(output_file, "w", encoding="utf-8") as f:
        for segment in segments:
            f.write(f"{segment.text}\n")
    print("    ✓ Transcription complete", file=sys.stderr)
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
PYTHON
        then
            ((count++)) || true
            echo "==> Saved: ${book_dir}/text.md"
        else
            echo "Warning: Failed to transcribe $book_name" >&2
            ((failed++)) || true
        fi
    done

    echo ""
    echo "==> Summary: Transcribed $count, Skipped $skipped, Failed $failed"
}

# Command: transcribe (rich progress display - recommended)
cmd_transcribe() {
    echo "==> Starting transcription with rich progress display..."

    # Check for GPU setup
    if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
        echo "Error: GPU environment not set up. Run ./setup-gpu.sh first" >&2
        return 1
    fi

    local extra_args=""
    if [[ "${1:-}" == "--continue-on-error" ]]; then
        extra_args="--continue-on-error"
    fi

    "$SCRIPT_DIR/.venv/bin/python3" "$SCRIPT_DIR/transcribe_runner.py" run $extra_args
}

# Command: status (show progress)
cmd_status() {
    local json_flag=""
    local verbose_flag=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --json) json_flag="--json" ;;
            -v|--verbose) verbose_flag="--verbose" ;;
            *) ;;
        esac
        shift
    done

    # Check for GPU setup
    if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
        echo "Error: GPU environment not set up. Run ./setup-gpu.sh first" >&2
        return 1
    fi

    "$SCRIPT_DIR/.venv/bin/python3" "$SCRIPT_DIR/transcribe_runner.py" status $json_flag $verbose_flag
}

# Command: pipeline (full parallel pipeline)
cmd_pipeline() {
    local decrypt_jobs="${1:-4}"

    echo "============================================"
    echo "PARALLEL AUDIOBOOK PIPELINE"
    echo "============================================"
    echo ""
    echo "Phase 1: Parallel AAX decryption ($decrypt_jobs jobs)"
    echo "Phase 2: Sequential GPU transcription"
    echo ""

    # Phase 1: Decrypt all AAX files in parallel
    cmd_decrypt_all "$decrypt_jobs"

    echo ""
    echo "============================================"
    echo "Phase 2: GPU Transcription (with progress)"
    echo "============================================"

    # Phase 2: Transcribe all M4B files with rich progress
    cmd_transcribe --continue-on-error

    echo ""
    echo "============================================"
    echo "PIPELINE COMPLETE"
    echo "============================================"
}

# Main command dispatcher
main() {
    if [[ $# -eq 0 ]]; then
        show_usage
        exit 1
    fi

    local command="$1"
    shift

    case "$command" in
        list-warhammer)
            cmd_list_warhammer "$@"
            ;;
        download-warhammer)
            cmd_download_warhammer "$@"
            ;;
        download-all)
            cmd_download_all "$@"
            ;;
        ingest)
            if [[ $# -eq 0 ]]; then
                echo "Error: Missing filename argument" >&2
                echo "Usage: run.sh ingest <filename>" >&2
                exit 1
            fi
            cmd_ingest "$@"
            ;;
        ingest-all)
            cmd_ingest_all "$@"
            ;;
        ingest-gpu)
            if [[ $# -eq 0 ]]; then
                echo "Error: Missing filename argument" >&2
                echo "Usage: run.sh ingest-gpu <filename>" >&2
                exit 1
            fi
            cmd_ingest_gpu "$@"
            ;;
        ingest-all-gpu)
            cmd_ingest_all_gpu "$@"
            ;;
        decrypt-all)
            cmd_decrypt_all "$@"
            ;;
        transcribe-all)
            cmd_transcribe_all "$@"
            ;;
        transcribe)
            cmd_transcribe "$@"
            ;;
        status)
            cmd_status "$@"
            ;;
        monitor)
            "$SCRIPT_DIR/.venv/bin/python3" "$SCRIPT_DIR/monitor_tui.py"
            ;;
        watchdog)
            "$SCRIPT_DIR/.venv/bin/python3" "$SCRIPT_DIR/watchdog.py"
            ;;
        pipeline)
            cmd_pipeline "$@"
            ;;
        help|--help|-h)
            show_usage
            ;;
        *)
            echo "Error: Unknown command: $command" >&2
            echo "" >&2
            show_usage >&2
            exit 1
            ;;
    esac
}

main "$@"
