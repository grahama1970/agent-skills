#!/usr/bin/env bash
# Live probes for the agentic evals. These exist as a script rather than inline
# eval commands because the checks need real quoting: escaping shell inside JSON
# inside `bash -c` silently mangled two cases and reported the CODE as broken
# when the code was correct.
unset VIRTUAL_ENV
set -uo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SKILL_DIR"

case "${1:-}" in
  crontab-untouched-by-dry-run)
    before="$(crontab -l 2>/dev/null | md5sum)"
    ./run.sh install-cron >/dev/null 2>&1
    ./run.sh activate     >/dev/null 2>&1
    after="$(crontab -l 2>/dev/null | md5sum)"
    if [ "$before" = "$after" ]; then
      echo "dry runs left the crontab byte-identical"
    else
      echo "FAIL: a dry run mutated the crontab"; exit 1
    fi
    ;;
  activate-single-document)
    ./run.sh activate 2>/dev/null | python3 -c '
import json, sys
text = sys.stdin.read()
json.loads(text)                      # raises if more than one document
assert text.strip().startswith("{"), "output does not start with the receipt"
print("activate emits one parseable document")
'
    ;;
  *)
    echo "unknown probe: ${1:-}" >&2; exit 2 ;;
esac
