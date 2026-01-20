#!/bin/bash
# Sanity check for pdf-screenshot skill
# Generates a dummy PDF and screenshots it.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_RUN="$SCRIPT_DIR/run.sh"
TEMP_PDF="/tmp/sanity_test.pdf"
TEMP_OUT="/tmp/sanity_test.png"

# 1. Generate Dummy PDF (3 Pages)
cat <<EOF > "$SCRIPT_DIR/gen_pdf.py"
import fitz
doc = fitz.open()

# Page 0
p0 = doc.new_page()
p0.insert_text((100, 100), "Page 0 - Base", fontsize=20)

# Page 1
p1 = doc.new_page()
p1.insert_text((100, 100), "Page 1 - Highlight Me", fontsize=20)

# Page 2
p2 = doc.new_page()
p2.insert_text((100, 100), "Page 2 - Batch Test", fontsize=20)

doc.save("$TEMP_PDF")
EOF

echo "Generating test PDF..."
if command -v uv &>/dev/null; then
    uv run --quiet --project "$SCRIPT_DIR" "$SCRIPT_DIR/gen_pdf.py"
else
    python3 "$SCRIPT_DIR/gen_pdf.py"
fi
rm "$SCRIPT_DIR/gen_pdf.py"

if [[ ! -f "$TEMP_PDF" ]]; then
    echo "Failed to generate test PDF."
    exit 1
fi

# Test 1: Single Page with Highlight (Page 1)
echo "Test 1: Highlight Page 1..."
"$SKILL_RUN" "$TEMP_PDF" --page 1 --highlight "50,50,300,300" --out "$TEMP_OUT"
if [[ ! -f "$TEMP_OUT" ]]; then
    echo "FAILURE: Highlight test failed."
    exit 1
fi
echo "SUCCESS: Highlight test passed."

# Test 2: Batch Pages (0, 2)
echo "Test 2: Batch Pages (0, 2)..."
OUT_DIR="/tmp/pdf-screenshot-test"
rm -rf "$OUT_DIR"
"$SKILL_RUN" "$TEMP_PDF" --pages "0,2" --out "$OUT_DIR/"

if [[ -f "$OUT_DIR/sanity_test_page0.png" && -f "$OUT_DIR/sanity_test_page2.png" ]]; then
    echo "SUCCESS: Batch test passed."
else
    echo "FAILURE: Batch test failed. Files not found in $OUT_DIR"
    ls -l "$OUT_DIR"
    exit 1
fi

echo "All sanity checks passed!"
exit 0
