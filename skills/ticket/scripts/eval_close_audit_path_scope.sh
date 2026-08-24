#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")/../../.." rev-parse --show-toplevel)"
base="$(mktemp -d -p /mnt/storage12tb ticket-close-scope.XXXXXX)"
repo="$base/repo"
wt="$base/secondary"
fakebin="$base/bin"
calls="$base/gh.calls"
proof="$base/proof.md"
results="$base/results.json"
artifact="$base/live-artifact.json"
out="$base/close.out"
err="$base/close.err"

git init "$repo" >/dev/null
git -C "$repo" config user.email ticket-eval@example.test
git -C "$repo" config user.name "Ticket Eval"
mkdir -p "$repo/skills/ticket" "$repo/unrelated"
printf 'base\n' > "$repo/skills/ticket/file.txt"
printf 'base\n' > "$repo/unrelated/file.txt"
git -C "$repo" add .
git -C "$repo" commit -m initial >/dev/null
git -C "$repo" worktree add "$wt" HEAD >/dev/null
printf 'dirty but unrelated\n' > "$wt/unrelated/file.txt"

mkdir -p "$fakebin"
cat > "$fakebin/gh" <<'GH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${FAKE_GH_CALLS:?}"
if [[ "${1:-}" == "issue" && "${2:-}" == "view" ]]; then
  if printf '%s\n' "$*" | grep -q -- '--json labels'; then
    printf 'maintainer-active\n'
    exit 0
  fi
  if printf '%s\n' "$*" | grep -q -- '--json body'; then
    cat <<'BODY'
## Type

maintenance

## Target

skills/ticket + scripts/validation

## Target paths

- skills/ticket + scripts/validation

## Ticket type details

- **Scoped files:** skills/ticket/scripts/ticket_cli.py skills/ticket/SKILL.md

## Orientation for a stateless agent

Use `skills/memory/run.sh recall`, `skills/project-state/run.sh --json`,
`skills/dogpile/run.sh`, `skills/brave-search/run.sh`, `skills/test/run.sh`,
and `skills/treesitter/run.sh`.
BODY
    exit 0
  fi
fi
if [[ "${1:-}" == "issue" && ( "${2:-}" == "comment" || "${2:-}" == "edit" || "${2:-}" == "close" ) ]]; then
  exit 0
fi
printf '{}\n'
GH
chmod +x "$fakebin/gh"

printf 'Proof command exited 0 with scoped worktree audit.\n' > "$proof"
printf '{"ok":true}\n' > "$artifact"
cat > "$results" <<JSON
{
  "schema": "agent_skills.ticket_closure_evidence.v1",
  "unit": {
    "command": "uv run --project skills/ticket python -m pytest skills/ticket/tests/test_memory_plan.py",
    "exit_code": 0
  },
  "e2e": {
    "command": "./run.sh sanity-live.sh --allow-live",
    "exit_code": 0,
    "mocked": false,
    "live": true,
    "artifact": "$artifact"
  }
}
JSON

(
  cd "$repo"
  FAKE_GH_CALLS="$calls" PATH="$fakebin:$PATH" \
    "$ROOT/skills/ticket/run.sh" close 1 \
      --proof "$proof" \
      --results "$results" \
      --repo owner/repo \
      >"$out" 2>"$err"
)

grep -q '"dirty_secondary":0' "$err"
grep -q '"dirty_secondary_ignored":1' "$err"
grep -q '"scope_paths":\["skills/ticket/scripts/ticket_cli.py","skills/ticket/SKILL.md"\]' "$err"
grep -q '"action":"close"' "$out"
grep -q 'issue comment 1' "$calls"
grep -q 'issue close 1' "$calls"
echo "CLOSE_AUDIT_PATH_SCOPED_OK"
