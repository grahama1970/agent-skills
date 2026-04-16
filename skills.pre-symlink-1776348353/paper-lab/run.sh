#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "paper-lab: Self-improving documentation convergence loop"
echo ""
echo "Status: SPECIFICATION ONLY — implementation pending"
echo "See: $SCRIPT_DIR/SKILL.md for full design"
echo ""
echo "Planned commands:"
echo "  tune <document>       Run convergence loop on a document"
echo "  status <document>     Show quality trajectory"
echo "  compare <v1> <v2>     Compare two document versions"
echo "  diagnose <document>   Identify specific weaknesses"
echo ""
echo "Dependencies: review-paper, create-paper, memory, scillm"
exit 1
