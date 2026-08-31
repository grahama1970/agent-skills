#!/usr/bin/env bash
set -euo pipefail

command="${1:-verify}"
case "$command" in
  verify|sanity)
    python3 - <<'PY'
from pathlib import Path
import yaml

text = Path('SKILL.md').read_text()
meta = yaml.safe_load(text.split('---', 2)[1])
required = {
    'triggers': 'tighten code',
    'provides': 'verbosity-review',
    'composes': 'agentic-evals',
    'complies': 'best-practices-skills',
}
for field, value in required.items():
    assert value in meta.get(field, []), f'{field} missing {value}'
for phrase in (
    'If write access is ambiguous, default to review-only.',
    'preserves behavior, error signals, cleanup semantics',
    'Keep one test per distinct behavior or risk',
    'Fixed [N] issue(s). Ready for another review.',
    'No issues found.',
):
    assert phrase in text, phrase
print('VERBOSITY_CLEANER_VERIFY_OK')
PY
    ;;
  *)
    echo "Usage: $0 [verify|sanity]" >&2
    exit 2
    ;;
esac
