#!/usr/bin/env bash
# Sanity check for /project-knowledge skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== project-knowledge sanity check ==="

# 1. Check SKILL.md frontmatter
echo -n "SKILL.md frontmatter... "
if head -1 SKILL.md | grep -q "^---$"; then
    echo "OK"
else
    echo "FAIL: Missing frontmatter opening ---"
    exit 1
fi

# 2. Check required frontmatter fields
echo -n "Required frontmatter fields... "
for field in name description triggers provides composes; do
    if ! grep -q "^${field}:" SKILL.md; then
        echo "FAIL: Missing $field in frontmatter"
        exit 1
    fi
done
echo "OK"

# 3. Check pyproject.toml exists
echo -n "pyproject.toml... "
if [[ -f pyproject.toml ]]; then
    echo "OK"
else
    echo "FAIL: Missing pyproject.toml"
    exit 1
fi

# 4. Check run.sh is executable
echo -n "run.sh executable... "
if [[ -x run.sh ]]; then
    echo "OK"
else
    echo "FAIL: run.sh not executable"
    exit 1
fi

# 5. Check Python package exists
echo -n "Python package... "
if [[ -d project_knowledge && -f project_knowledge/__init__.py ]]; then
    echo "OK"
else
    echo "FAIL: Missing project_knowledge package"
    exit 1
fi

# 6. Check CLI uses typer (not argparse or click)
echo -n "CLI uses typer... "
if grep -q "import typer" project_knowledge/__main__.py; then
    echo "OK"
else
    echo "FAIL: CLI must use typer"
    exit 1
fi

# 7. Check no direct ArangoDB access
echo -n "No direct ArangoDB access... "
if grep -rq "from arango import\|ArangoClient" project_knowledge/; then
    echo "FAIL: Direct ArangoDB access detected - use /memory"
    exit 1
fi
echo "OK"

# 8. Verify venv can be created and package installed
echo -n "Package installable... "
if [[ ! -d .venv ]]; then
    uv venv .venv >/dev/null 2>&1
fi
if uv pip install -e . >/dev/null 2>&1; then
    echo "OK"
else
    echo "FAIL: Package not installable"
    exit 1
fi

# 9. Test CLI help
echo -n "CLI help works... "
if uv run python -m project_knowledge --help >/dev/null 2>&1; then
    echo "OK"
else
    echo "FAIL: CLI --help failed"
    exit 1
fi

echo ""
echo "=== All sanity checks passed ==="
