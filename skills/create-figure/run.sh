#!/usr/bin/env bash
# Run fixture-graph skill with uvx for self-contained execution
# No virtual environment needed - uvx handles all dependencies
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Core dependencies for fixture-graph
# uvx creates an isolated environment with these packages
exec uvx --with typer \
         --with numpy \
         --with matplotlib \
         --with networkx \
         --with pandas \
         --with scipy \
         --with seaborn \
         python fixture_graph.py "$@"
