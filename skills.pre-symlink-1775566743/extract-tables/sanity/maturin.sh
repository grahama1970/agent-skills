#!/bin/bash
set -e
cd ~/.claude/skills/extract-tables/src/rust
maturin develop --release 2>&1
python3 -c "import extract_tables_rs; print('PASS: maturin build + import works')"
