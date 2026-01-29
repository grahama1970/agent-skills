#!/usr/bin/env bash
#
# doc2qra Skill Runner
# Converts documents (PDF, URL, text) into QRA pairs with summaries
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "${SCRIPT_DIR}")"

# Use uv run to execute in the project environment defined by pyproject.toml
# This ensures rich, tqdm, dotenv, etc. are available.
# Pass parent dir as cwd so 'doc2qra' package is importable
exec uv run --project "${SCRIPT_DIR}" python -c "
import sys
sys.path.insert(0, '${PARENT_DIR}')
from doc2qra.cli import main
sys.exit(main())
" "$@"
