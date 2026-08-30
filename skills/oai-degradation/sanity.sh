#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$ROOT/run.sh" check-skill
cat > /tmp/oai-degradation-good-answer.md <<'EOF'
| Field | Entry |
|---|---|
| Goal | VERIFIED: recover the task. |
| Blocked | none verified |
| Failing | VERIFIED: prior answer missed the named URL. |
| Confused | INFERENCE: context is degraded. |
| Human needed | none verified |
| Next command | read the named artifact |
| Switch trigger | Use Kimi or DeepSeek if this check misses again. |
EOF
"$ROOT/run.sh" check-answer /tmp/oai-degradation-good-answer.md
cat > /tmp/oai-degradation-bad-answer.md <<'EOF'
I cannot verify quantization, but I will try harder. Everything is fine.
EOF
if "$ROOT/run.sh" check-answer /tmp/oai-degradation-bad-answer.md >/tmp/oai-degradation-bad.out 2>&1; then
  echo "bad answer unexpectedly passed" >&2
  exit 1
fi
grep -q 'OAI_DEGRADATION_ANSWER_CONTRACT_FAIL' /tmp/oai-degradation-bad.out
printf 'OAI_DEGRADATION_SANITY_OK\n'
