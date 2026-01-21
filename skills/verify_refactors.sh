#!/bin/bash
set -e
echo "Verifying path refactors..."

# 1. Extractor
EXT_RUN=".pi/skills/extractor/run.sh"
echo "Check extractor run.sh..."
if grep -q "DEFAULT_ROOT" "$EXT_RUN"; then
    echo "✅ extractor/run.sh uses detection"
else
    echo "❌ extractor/run.sh failed check"
    exit 1
fi

# 2. Arxiv
ARXIV_PY=".pi/skills/arxiv/arxiv_learn.py"
echo "Check arxiv_learn.py..."
if grep -q "SKILLS_DIR).parent.parent.parent" "$ARXIV_PY"; then
    echo "✅ arxiv_learn.py uses relative path logic"
else
    echo "❌ arxiv_learn.py failed check"
    exit 1
fi

# 3. Surf
SURF_RUN=".pi/skills/surf/run.sh"
echo "Check surf/run.sh..."
if grep -q "DEFAULT_SURF_CLI" "$SURF_RUN"; then
    echo "✅ surf/run.sh uses detection"
else
    echo "❌ surf/run.sh failed check"
    exit 1
fi

echo "All checks passed!"
