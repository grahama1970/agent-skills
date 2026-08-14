#!/usr/bin/env bash
# Non-mocked sanity: drives the real CLI against the real provider files.
# Proves idempotency, single-block invariance, non-destructive check mode,
# provider-content preservation, and template selection.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="$SCRIPT_DIR/run.sh"
STYLE="$SCRIPT_DIR/../../output-styles/clear-technical.md"
BEGIN="BEGIN agent-skills:output-contract"
TARGETS=("$HOME/.claude/CLAUDE.md" "$HOME/.codex/AGENTS.md" "$HOME/.gemini/GEMINI.md"
         "$HOME/.cursor/rules/output-contract.mdc" "$STYLE")
fail=0

check() { if [[ "$2" == "$3" ]]; then echo "PASS  $1"; else echo "FAIL  $1 (want '$3', got '$2')"; fail=1; fi; }

restore_active="$("$RUN" list | sed -n 's/^\* //p')"
cleanup() { "$RUN" use "$restore_active" >/dev/null 2>&1 || true; "$RUN" apply >/dev/null 2>&1 || true; }
trap cleanup EXIT

"$RUN" apply >/dev/null

# 1. converged state is clean and exits 0
check "check exits 0 when converged" "$("$RUN" check >/dev/null 2>&1 && echo 0 || echo 1)" "0"

# 2. check mode never mutates
before="$(md5sum < "$HOME/.claude/CLAUDE.md")"
"$RUN" check >/dev/null 2>&1 || true
check "check mode mutates nothing" "$(md5sum < "$HOME/.claude/CLAUDE.md")" "$before"

# 3. repeated applies leave exactly one block
"$RUN" apply >/dev/null; "$RUN" apply >/dev/null
for t in "${TARGETS[@]}"; do
  check "one block in $(basename "$t")" "$(grep -c "$BEGIN" "$t")" "1"
done

# 4. an edit to the active template reaches every target, then reverts
active="$("$RUN" list | sed -n 's/^\* //p')"
tpl="$SCRIPT_DIR/templates/${active}.md"
probe="SANITY_PROBE_$$"
cp "$tpl" "$tpl.sanitybak"
printf '\n%s\n' "$probe" >> "$tpl"
"$RUN" apply >/dev/null
hits=0; for t in "${TARGETS[@]}"; do grep -q "$probe" "$t" && hits=$((hits+1)); done
mv "$tpl.sanitybak" "$tpl"
"$RUN" apply >/dev/null
residual=0; for t in "${TARGETS[@]}"; do grep -q "$probe" "$t" && residual=$((residual+1)); done
check "one edit reaches every target" "$hits" "${#TARGETS[@]}"
check "revert removes it everywhere" "$residual" "0"

# 5. template selection swaps the installed contract everywhere
tmp_name="sanity-tmp-$$"
printf '# Output Contract (%s)\n\nProbe template.\n' "$tmp_name" > "$SCRIPT_DIR/templates/$tmp_name.md"
"$RUN" use "$tmp_name" >/dev/null
"$RUN" apply >/dev/null
swapped=0; for t in "${TARGETS[@]}"; do grep -q "Output Contract ($tmp_name)" "$t" && swapped=$((swapped+1)); done
check "use+apply swaps every target" "$swapped" "${#TARGETS[@]}"
"$RUN" use "$active" >/dev/null
"$RUN" apply >/dev/null
mv "$SCRIPT_DIR/templates/$tmp_name.md" /tmp/"$tmp_name.md" 2>/dev/null || true
check "active template restored" "$("$RUN" list | sed -n 's/^\* //p')" "$active"

# 6. unknown template is refused without writing
check "unknown template refused" "$("$RUN" use no-such-template >/dev/null 2>&1 && echo 0 || echo 2)" "2"

# 7. structural invariants that a broken write would violate
check "style frontmatter intact" "$(head -1 "$STYLE")" "---"
check "codex content preserved" "$(head -1 "$HOME/.codex/AGENTS.md")" "# Global Codex Agent Instructions"
check "no venv inside skill dir" "$([[ -e "$SCRIPT_DIR/.venv" ]] && echo present || echo absent)" "absent"

exit $fail
