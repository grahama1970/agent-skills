#!/bin/bash
# project-taxonomy entrypoint: check | apply | sync | list <discipline>
unset VIRTUAL_ENV
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=(uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/apply_disciplines.py")

case "${1:-check}" in
    check)  exec "${PY[@]}" ;;
    apply)  exec "${PY[@]}" --write ;;
    sync)   exec "${PY[@]}" --write --memory-sync ;;
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
    *) echo "usage: run.sh check|apply|sync|list <discipline>" >&2; exit 2 ;;
esac
