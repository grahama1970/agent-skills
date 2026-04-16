#!/bin/bash
set -e

# Sanity Script: High-Fidelity End-to-End Dream Workflow
# 1. Memory Seed: Manually learn a thematic idea
# 2. Ingest: Process a real movie clip (ingest-movie)
# 3. Consume: Add notes/context (consume-movie)
# 4. Learn: Analyze cinematographic techniques (learn-movie)
# 5. Dream: Generate 30s Movie (create-movie) seeded from the above

echo "🎬 Starting High-Fidelity End-to-End Sanity Check..."

# Check Keys
if [ -z "$GEMINI_API_KEY" ]; then
    echo "❌ Missing API Keys: GEMINI_API_KEY required."
    exit 1
fi

SKILLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INGEST_DIR="$SKILLS_DIR/ingest-movie"
CONSUME_DIR="$SKILLS_DIR/consume-movie"
LEARN_DIR="$SKILLS_DIR/learn-movie"
CREATE_DIR="$SKILLS_DIR/create-movie"
MEMORY_DIR="$SKILLS_DIR/memory"

REAL_MOVIE="/mnt/storage12tb/media/movies/There Will Be Blood (2007)/There.Will.Be.Blood.2007.PROPER.1080p.BluRay.x264-ELBOWDOWN.mkv"
REAL_SRT="/mnt/storage12tb/media/movies/There Will Be Blood (2007)/There.Will.Be.Blood.2007.SDH.eng.srt"
TEMP_DIR="/tmp/high_fidelity_sanity_$(date +%s)"
PROJECT_NAME="high_fidelity_dream"
OUTPUT_FILE="$TEMP_DIR/high_fidelity_result.mp4"

mkdir -p "$TEMP_DIR"

# ==============================================================================
# Step 1: Memory Seed
# ==============================================================================
echo -e "\n🧠 [Step 1] Seeding Memory with Dream Idea..."
cd "$MEMORY_DIR"
./run.sh learn \
    --problem "Horus is dreaming of a futuristic city where data flows like neon rivers" \
    --solution "Use blue and cyan color palettes with high-contrast lighting to evoke a cyberpunk neon dream." \
    --tag dream_seed --tag cyberpunk --tag neon

# ==============================================================================
# Step 2: Ingest Real Movie
# ==============================================================================
echo -e "\n📥 [Step 2] Ingesting Real Movie Clip..."
cd "$INGEST_DIR"

# Using agent quick to process the clip (Milkshake scene approx 02:28:09)
# Note: ingest-movie will look for subtitles in the movie directory
./run.sh agent quick \
    --movie "$REAL_MOVIE" \
    --emotion rage \
    --scene "The Milkshake Scene" \
    --timestamp "02:28:09-02:28:39" \
    --output "$TEMP_DIR/ingest_output"

# Locate the extracted clip in the movie directory's rage_clips folder
REAL_MOVIE_DIR=$(dirname "$REAL_MOVIE")
INGESTED_CLIP=$(find "$REAL_MOVIE_DIR/rage_clips" -maxdepth 1 \( -name "*.mp4" -o -name "*.mkv" \) | head -n 1)

if [ -f "$INGESTED_CLIP" ]; then
    echo "   ✓ Ingested clip found: $INGESTED_CLIP"
else
    echo "   ❌ Ingestion failed to produce clip in $REAL_MOVIE_DIR/rage_clips"
    exit 1
fi

# ==============================================================================
# Step 3: Consume & Note
# ==============================================================================
echo -e "\n🍿 [Step 3] Consuming & Taking Notes..."
cd "$CONSUME_DIR"
# Sync from ingest-movie to populate the registry, pointing to our temp output
./run.sh sync --ingest "$TEMP_DIR/ingest_output"
./run.sh note --movie "There Will Be Blood (2007)" --timestamp 2.5 --note "Note: The lighting here is exceptionally moody, perfect for the neon dream."

# ==============================================================================
# Step 4: Learn from Ingested Clip
# ==============================================================================
echo -e "\n🎨 [Step 4] Learning Cinematographic Techniques..."
cd "$LEARN_DIR"
./run.sh analyze "$INGESTED_CLIP" --director "Veo High Fidelity" --limit 1

# ==============================================================================
# Step 5: Create 30s Dream Movie
# ==============================================================================
echo -e "\n😴 [Step 5] Orchestrating 30s Dream Render..."
cd "$CREATE_DIR"

# Clean up project dir
rm -rf "$TEMP_DIR/$PROJECT_NAME"

# We target 24-30s (approx 3-4 shots of 8s each)
uv run orchestrator.py create \
    --dream \
    --render-veo \
    --output "$OUTPUT_FILE" \
    --work-dir "$TEMP_DIR/$PROJECT_NAME" \
    --duration 30 \
    --skip-research \
    --skip-hardware-check

if [ $? -eq 0 ]; then
    echo "   ✓ High-fidelity dream creation complete."
    if [ -f "$OUTPUT_FILE" ]; then
         echo "   ✓ Output verified: $OUTPUT_FILE"
    fi
else
    echo "   ❌ High-fidelity creation failed."
    exit 1
fi

echo -e "\n✅ High-Fidelity Sanity Check PASSED!"
echo "Artifacts located in: $TEMP_DIR"
