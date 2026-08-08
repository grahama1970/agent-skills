#!/bin/bash
# project-taxonomy entrypoint: check | apply | sync | crosswalk [--write] | portfolio | ci | list <discipline>
unset VIRTUAL_ENV
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=(uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/apply_disciplines.py")

case "${1:-check}" in
    check)      exec "${PY[@]}" run ;;
    apply)      exec "${PY[@]}" run --write ;;
    sync)       exec "${PY[@]}" run --write --memory-sync ;;
    crosswalk)  shift; exec "${PY[@]}" crosswalk "$@" ;;
    portfolio)  exec "${PY[@]}" portfolio-check ;;
    ci)
        # Deterministic full gate: discipline mapping + crosswalk drift + portfolio
        # registry validity/freshness/coverage. Used by /monitor-projects nightly.
        "${PY[@]}" run
        "${PY[@]}" crosswalk
        exec "${PY[@]}" portfolio-check
        ;;
    list)
        shift
        exec uv run --project "$SCRIPT_DIR" python -c "
import sys, yaml
from pathlib import Path
cfg = yaml.safe_load((Path('$SCRIPT_DIR') / 'references' / 'disciplines.yml').read_text())
disc = sys.argv[1] if len(sys.argv) > 1 else ''
if disc not in cfg['vocabulary']:
    print('unknown discipline. valid:', ', '.join(sorted(cfg['vocabulary'])))
    raise SystemExit(2)
for name, discs in sorted(cfg['skills'].items()):
    if disc in discs:
        print(name)
" "$@" ;;
    *) echo "usage: run.sh check|apply|sync|crosswalk|portfolio|ci|list <discipline>" >&2; exit 2 ;;
esac
