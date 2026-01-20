#!/bin/bash
# Sanity check for pdf-screenshot skill
# Generates a dummy PDF and screenshots it.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_RUN="$SCRIPT_DIR/run.sh"
TEMP_PDF="/tmp/sanity_test.pdf"
TEMP_OUT="/tmp/sanity_test.png"

# 1. Generate Dummy PDF
cat <<EOF > "$SCRIPT_DIR/gen_pdf.py"
import fitz
doc = fitz.open()
page = doc.new_page()
page.insert_text((100, 100), "Sanity Check PDF", fontsize=20)
page.draw_rect(fitz.Rect(50, 50, 200, 200), color=(0, 0, 1))
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

echo "Running pdf-screenshot on Page 0..."
"$SKILL_RUN" "$TEMP_PDF" --page 0 --out "$TEMP_OUT"

if [[ -f "$TEMP_OUT" ]]; then
    echo "SUCCESS: Screenshot created at $TEMP_OUT"
    echo "Size: $(du -h $TEMP_OUT | cut -f1)"
    exit 0
else
    echo "FAILURE: Screenshot not found."
    exit 1
fi
