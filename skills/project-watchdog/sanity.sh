#!/usr/bin/env bash
# Behavioural acceptance gates for project-watchdog.
#
# These run the real CLI against an isolated state root and a recording `gh`
# shim. Nothing here touches the operator's real receipts, real crontab, or real
# GitHub. Every gate asserts observable behaviour, not just a zero exit code.
#
# Gates:
#   1  CLI surface is reachable and exposes all four commands
#   2  status emits a schema-valid payload with the expected keys
#   3  POSITIVE control: dry-run tick on an active project scans and reports
#   4  SAFETY boundary: a dry-run tick performs zero GitHub mutations
#   5  NEGATIVE control: paused global state refuses to scan at all
#   6  NEGATIVE control: unknown project id fails closed with exit 2
#   7  ARTIFACT policy: uneventful ticks leave no receipt directory behind
#   8  ARTIFACT schema: eventful receipts persist with the declared schema
#   9  REGRESSION guard: no unexpanded shell variables in Python path literals
#  10  Unit tests pass
#  11  IDLE ESCALATION: prolonged silence stops reporting as healthy
#  12  TICKET ROUTE: ordinary /ticket-filed issues reach the router
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
unset VIRTUAL_ENV
UV_BIN="${UV_BIN:-${HOME}/.local/bin/uv}"
[[ -x "$UV_BIN" ]] || UV_BIN="uv"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

export PROJECT_WATCHDOG_STATE_ROOT="$WORK/state"
mkdir -p "$PROJECT_WATCHDOG_STATE_ROOT"

PASS=0
FAIL=0

ok()   { printf '  PASS  %s\n' "$1"; PASS=$((PASS + 1)); }
bad()  { printf '  FAIL  %s\n' "$1"; FAIL=$((FAIL + 1)); }
gate() { printf '\n[%s] %s\n' "$1" "$2"; }

watchdog() { "$UV_BIN" run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/project_watchdog.py" "$@"; }

# --- recording gh shim: logs every call, refuses to mutate ------------------- #
SHIM_DIR="$WORK/bin"
GH_LOG="$WORK/gh-calls.log"
mkdir -p "$SHIM_DIR"
: > "$GH_LOG"
cat > "$SHIM_DIR/gh" <<SHIM
#!/usr/bin/env bash
echo "\$*" >> "$GH_LOG"
case "\${2:-}" in
  comment|edit|close) echo "FORBIDDEN MUTATION: gh \$*" >&2; exit 91 ;;
esac
if [[ "\${1:-}" == "issue" && "\${2:-}" == "list" ]]; then echo '[]'; exit 0; fi
if [[ "\${1:-}" == "crontab" ]]; then exit 0; fi
echo '[]'
SHIM
chmod +x "$SHIM_DIR/gh"
export PATH="$SHIM_DIR:$PATH"

# --- isolated registry copy so gates never edit the real state -------------- #
REAL_STATE="$SCRIPT_DIR/registry/state.json"
STATE_BACKUP="$WORK/state.json.orig"
cp "$REAL_STATE" "$STATE_BACKUP"
restore_state() { cp "$STATE_BACKUP" "$REAL_STATE"; }
trap 'restore_state; rm -rf "$WORK"' EXIT

export SANITY_SKILL_DIR="$SCRIPT_DIR"
export SANITY_STAMP="$(date -u +%H%M%S)"

echo "project-watchdog sanity — state root: $PROJECT_WATCHDOG_STATE_ROOT"

# --------------------------------------------------------------------------- #
gate 1 "CLI surface"
HELP="$(watchdog --help 2>&1)"
for cmd in tick install-cron set-state status; do
  if grep -q -- "$cmd" <<<"$HELP"; then ok "command exposed: $cmd"; else bad "command missing: $cmd"; fi
done

# --------------------------------------------------------------------------- #
gate 2 "status payload schema"
STATUS="$(watchdog status 2>/dev/null)"
if jq -e '.schema == "agent_skills.project_watchdog.status.v1"' <<<"$STATUS" >/dev/null 2>&1; then
  ok "status declares its schema"
else
  bad "status schema missing or wrong"
fi
for key in state project_count project_ids receipt_root uv_bin lock_held; do
  if jq -e "has(\"$key\")" <<<"$STATUS" >/dev/null 2>&1; then ok "status.$key present"; else bad "status.$key missing"; fi
done
if jq -e '.uv_bin | test("^\\$") | not' <<<"$STATUS" >/dev/null 2>&1; then
  ok "status.uv_bin is a resolved path, not a shell literal"
else
  bad "status.uv_bin looks unexpanded"
fi

# --------------------------------------------------------------------------- #
gate 3 "POSITIVE control — dry-run tick on an active project"
watchdog set-state global active --reason "sanity positive control" >/dev/null 2>&1
watchdog set-state project active --project tau --reason "sanity positive control" >/dev/null 2>&1
TICK="$(watchdog tick --project tau 2>/dev/null)"
if jq -e '.schema == "agent_skills.project_watchdog.tick_receipt.v1"' <<<"$TICK" >/dev/null 2>&1; then
  ok "tick receipt declares its schema"
else
  bad "tick receipt schema missing"
fi
if jq -e '.apply == false' <<<"$TICK" >/dev/null 2>&1; then
  ok "dry-run tick records apply=false"
else
  bad "dry-run tick did not record apply=false"
fi
if jq -e '.status | IN("NOOP","COMPLETED","NEEDS_ATTENTION","BLOCKED")' <<<"$TICK" >/dev/null 2>&1; then
  ok "tick status is a declared value: $(jq -r .status <<<"$TICK")"
else
  bad "tick status is not a declared value"
fi
if grep -q 'issue list' "$GH_LOG"; then
  ok "tick actually scanned GitHub (gh issue list observed)"
else
  bad "tick never called gh issue list — scan did not happen"
fi

# --------------------------------------------------------------------------- #
gate 4 "SAFETY boundary — dry run must not mutate GitHub"
if grep -Eq 'issue (comment|edit|close)' "$GH_LOG"; then
  bad "dry-run tick attempted a GitHub mutation"
  grep -E 'issue (comment|edit|close)' "$GH_LOG" | sed 's/^/        /'
else
  ok "zero comment/edit/close calls during dry run"
fi
if grep -q 'FORBIDDEN' <<<"$TICK"; then bad "shim reported a forbidden mutation"; else ok "shim recorded no forbidden mutation"; fi

# --------------------------------------------------------------------------- #
gate 5 "NEGATIVE control — paused global state refuses to scan"
: > "$GH_LOG"
watchdog set-state global paused --reason "sanity negative control" >/dev/null 2>&1
PAUSED="$(watchdog tick --project tau 2>/dev/null)"
if jq -e '.status == "SKIPPED" and .stop_reason == "global_state_paused"' <<<"$PAUSED" >/dev/null 2>&1; then
  ok "paused state yields SKIPPED/global_state_paused"
else
  bad "paused state did not fail closed: $(jq -rc '{status,stop_reason}' <<<"$PAUSED" 2>/dev/null)"
fi
if [[ -s "$GH_LOG" ]] && grep -q 'issue list' "$GH_LOG"; then
  bad "paused watchdog still scanned GitHub"
else
  ok "paused watchdog performed no GitHub scan"
fi
watchdog set-state global active --reason "sanity restore" >/dev/null 2>&1

# --------------------------------------------------------------------------- #
gate 6 "NEGATIVE control — unknown project id fails closed"
UNKNOWN="$(watchdog tick --project not-a-real-project 2>/dev/null)"
UNKNOWN_RC=$?
if [[ "$UNKNOWN_RC" -eq 2 ]]; then ok "unknown project exits 2"; else bad "unknown project exited $UNKNOWN_RC, expected 2"; fi
if jq -e '.status == "BLOCKED"' <<<"$UNKNOWN" >/dev/null 2>&1; then
  ok "unknown project yields BLOCKED"
else
  bad "unknown project did not yield BLOCKED"
fi
if jq -e '.errors[0] | test("Registered ids")' <<<"$UNKNOWN" >/dev/null 2>&1; then
  ok "error message lists the registered project ids"
else
  bad "error message does not teach the caller which ids exist"
fi
if grep -q 'not-a-real-project' <<<"$UNKNOWN"; then ok "error echoes the offending id"; else bad "error omits the offending id"; fi

# --------------------------------------------------------------------------- #
gate 7 "ARTIFACT policy — uneventful ticks leave no receipt directory"
# Against the real fleet "uneventful" is not deterministic: a tick has three
# lanes now (repair, closure audit, completion attestation) and any of them
# becoming eventful is legitimate. Pin a paused fixture project so the tick has
# provably nothing to do and this gate tests retention, not the fleet's mood.
cat > "$WORK/idle-projects.json" <<'JSON'
{"schema": "agent_skills.project_watchdog.registry.v1",
 "projects": [{"project_id": "tau", "repo": "grahama1970/tau", "worktree": "/nonexistent"}]}
JSON
# Pause GLOBALLY, not per project. A fleet where every project is paused is
# correctly NEEDS_ATTENTION -- it never clears without a human -- and that is
# eventful, so it persists. The uneventful case is the kill switch being off.
cat > "$PROJECT_WATCHDOG_STATE_ROOT/state.json" <<'JSON'
{"schema": "agent_skills.project_watchdog.state.v1",
 "global": {"state": "paused"},
 "projects": {"tau": {"state": "active"}}}
JSON
PROJECT_WATCHDOG_PROJECTS_PATH="$WORK/idle-projects.json"
export PROJECT_WATCHDOG_PROJECTS_PATH
BEFORE="$(find "$PROJECT_WATCHDOG_STATE_ROOT/receipts" -maxdepth 1 -type d -name 'project-watchdog-2*' 2>/dev/null | wc -l)"
watchdog tick --project tau >/dev/null 2>&1
watchdog tick --project tau >/dev/null 2>&1
watchdog tick --project tau >/dev/null 2>&1
AFTER="$(find "$PROJECT_WATCHDOG_STATE_ROOT/receipts" -maxdepth 1 -type d -name 'project-watchdog-2*' 2>/dev/null | wc -l)"
unset PROJECT_WATCHDOG_PROJECTS_PATH
if [[ "$AFTER" -eq "$BEFORE" ]]; then
  ok "three uneventful ticks added zero receipt dirs (was $BEFORE, now $AFTER)"
else
  bad "uneventful ticks leaked receipt dirs (was $BEFORE, now $AFTER)"
fi

# --------------------------------------------------------------------------- #
gate 8 "ARTIFACT schema — eventful receipts persist"
STATE_RECEIPT="$(watchdog set-state project paused --project tau --reason "sanity artifact gate" 2>/dev/null)"
RECEIPT_PATH="$(jq -r '.receipt_path // empty' <<<"$STATE_RECEIPT")"
if [[ -n "$RECEIPT_PATH" && -f "$RECEIPT_PATH" ]]; then
  ok "eventful receipt persisted at $(basename "$(dirname "$RECEIPT_PATH")")/receipt.json"
else
  bad "eventful receipt was not persisted"
fi
if [[ -f "$RECEIPT_PATH" ]] && jq -e '.schema == "agent_skills.project_watchdog.state_change_receipt.v1"' "$RECEIPT_PATH" >/dev/null 2>&1; then
  ok "persisted receipt carries the declared schema"
else
  bad "persisted receipt schema missing or wrong"
fi
if [[ -f "$RECEIPT_PATH" ]] && jq -e '.mocked == false and .live == true' "$RECEIPT_PATH" >/dev/null 2>&1; then
  ok "persisted receipt declares its evidence class"
else
  bad "persisted receipt omits mocked/live"
fi
watchdog set-state project active --project tau --reason "sanity restore" >/dev/null 2>&1

# --------------------------------------------------------------------------- #
gate 9 "REGRESSION guard — no unexpanded shell variables in path literals"
if "$UV_BIN" run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/check_path_literals.py" \
     "$SCRIPT_DIR/scripts" >"$WORK/pathcheck.log" 2>&1; then
  ok "AST scan: no path literal contains a shell variable"
else
  bad "AST scan found shell variables inside path literals"
  sed 's/^/        /' "$WORK/pathcheck.log"
fi
UNEXPANDED="$(WATCHDOG_SCRIPTS="$SCRIPT_DIR/scripts" "$UV_BIN" run --project "$SCRIPT_DIR" python - <<'PY' 2>/dev/null
import os
import sys

sys.path.insert(0, os.environ["WATCHDOG_SCRIPTS"])
from watchdog import config

bad = [
    name
    for name in ("workspace_root", "agents_root", "state_root", "receipt_root")
    if "$" in str(getattr(config, name)())
]
print(",".join(bad))
PY
)"
if [[ -z "$UNEXPANDED" ]]; then ok "all config paths resolve without shell variables"; else bad "unexpanded config paths: $UNEXPANDED"; fi

# --------------------------------------------------------------------------- #
gate 11 "IDLE ESCALATION — prolonged silence must stop reporting as healthy"
# Real CLI, real ticks, 2s threshold. Not a unit test over our own helpers.
export PROJECT_WATCHDOG_IDLE_ESCALATION_SECONDS=2
export PROJECT_WATCHDOG_IDLE_RENOTIFY_SECONDS=3600
rm -f "$PROJECT_WATCHDOG_STATE_ROOT/streaks.json" "$PROJECT_WATCHDOG_STATE_ROOT/state.json" 2>/dev/null || true
# Point at a fixture registry holding one paused project. Against the real
# registry this gate stopped being about idleness the moment any live project
# gained a routable ticket -- the tick correctly dispatched, and the gate read
# that as a regression.
cat > "$WORK/idle-projects.json" <<'JSON'
{"schema": "agent_skills.project_watchdog.registry.v1",
 "projects": [{"project_id": "tau", "repo": "grahama1970/tau", "worktree": "/nonexistent"}]}
JSON
cat > "$PROJECT_WATCHDOG_STATE_ROOT/state.json" <<'JSON'
{"schema": "agent_skills.project_watchdog.state.v1",
 "global": {"state": "active"},
 "projects": {"tau": {"state": "active"}}}
JSON
export PROJECT_WATCHDOG_PROJECTS_PATH="$WORK/idle-projects.json"
FIRST="$(watchdog tick --project tau 2>/dev/null)"
if jq -e '.status == "NOOP" and .idle_streak.escalated == false' <<<"$FIRST" >/dev/null 2>&1; then
  ok "first idle tick reports NOOP, not escalated"
else
  bad "first idle tick should be an un-escalated NOOP"
fi
sleep 3
ESC_BEFORE="$(find "$PROJECT_WATCHDOG_STATE_ROOT/receipts" -maxdepth 1 -type d -name 'project-watchdog-2*' 2>/dev/null | wc -l)"
ESCALATED="$(watchdog tick --project tau 2>/dev/null)"
if jq -e '.status == "NEEDS_ATTENTION" and .stop_reason == "idle_streak_exceeded"' <<<"$ESCALATED" >/dev/null 2>&1; then
  ok "idle beyond threshold escalates to NEEDS_ATTENTION"
else
  bad "idle beyond threshold did not escalate: $(jq -rc '{status,stop_reason}' <<<"$ESCALATED" 2>/dev/null)"
fi
if jq -e '.idle_streak.diagnosis | length > 0' <<<"$ESCALATED" >/dev/null 2>&1; then
  ok "escalation carries an actionable diagnosis"
else
  bad "escalation carries no diagnosis"
fi
if jq -e '.idle_streak.diagnosis | join(" ") | test("agent-work")' <<<"$ESCALATED" >/dev/null 2>&1; then
  ok "diagnosis names the label-vocabulary check"
else
  bad "diagnosis does not name the label check"
fi
if jq -e '.receipt_path != null' <<<"$ESCALATED" >/dev/null 2>&1; then
  ok "first escalation persists a receipt"
else
  bad "first escalation did not persist a receipt"
fi
watchdog tick --project tau >/dev/null 2>&1
watchdog tick --project tau >/dev/null 2>&1
REPEAT="$(watchdog tick --project tau 2>/dev/null)"
ESC_AFTER="$(find "$PROJECT_WATCHDOG_STATE_ROOT/receipts" -maxdepth 1 -type d -name 'project-watchdog-2*' 2>/dev/null | wc -l)"
if jq -e '.status == "NEEDS_ATTENTION" and .receipt_persisted == false' <<<"$REPEAT" >/dev/null 2>&1; then
  ok "repeat escalations stay NEEDS_ATTENTION without re-persisting"
else
  bad "repeat escalation re-persisted a receipt"
fi
if [[ "$((ESC_AFTER - ESC_BEFORE))" -le 1 ]]; then
  ok "escalation added at most one receipt dir across four ticks (delta $((ESC_AFTER - ESC_BEFORE)))"
else
  bad "escalation leaked receipt dirs (delta $((ESC_AFTER - ESC_BEFORE)))"
fi
if jq -e '.idle_streak.consecutive_idle_ticks >= 4' <<<"$REPEAT" >/dev/null 2>&1; then
  ok "consecutive idle ticks are counted: $(jq -r .idle_streak.consecutive_idle_ticks <<<"$REPEAT")"
else
  bad "consecutive idle ticks not counted"
fi
unset PROJECT_WATCHDOG_IDLE_ESCALATION_SECONDS PROJECT_WATCHDOG_IDLE_RENOTIFY_SECONDS

# --------------------------------------------------------------------------- #
gate 12 "TICKET ROUTE — ordinary /ticket-filed issues reach the router"
ROUTE_JSON="$("$UV_BIN" run --project "$SCRIPT_DIR" python - <<'PY' 2>/dev/null
import json
import os
import sys

sys.path.insert(0, os.path.join(os.environ["SANITY_SKILL_DIR"], "scripts"))
from watchdog import config, registry


def issue(labels, body=""):
    return {"number": 1, "title": "t", "body": body, "labels": [{"name": n} for n in labels], "url": "u"}


print(json.dumps({
    "ticket": registry.classify_issue(issue(["agent-work", "type:bug", "route:backend_python_or_skill_runtime"])),
    "no_ready_label": registry.classify_issue(issue(["type:bug", "route:backend_python_or_skill_runtime"])),
    "needs_human": registry.classify_issue(issue(["agent-work", "needs-human"])),
    "maintainer_blocked": registry.classify_issue(issue(["agent-work", "maintainer-blocked"])),
    "leased": registry.classify_issue(issue(["agent-work", "agent-active"])),
    "marker_wins": registry.classify_issue(issue(["agent-work", "executor:local"], "project-watchdog-action:tau-handoff-dispatch start=x.json")),
}))
PY
)"
if jq -e '.ticket == "ticket_repair"' <<<"$ROUTE_JSON" >/dev/null 2>&1; then
  ok "a /ticket-filed issue routes to ticket_repair"
else
  bad "a /ticket-filed issue is still unroutable: $(jq -rc . <<<"$ROUTE_JSON" 2>/dev/null)"
fi
if jq -e '.no_ready_label == null' <<<"$ROUTE_JSON" >/dev/null 2>&1; then
  ok "an issue without agent-work is not routable"
else
  bad "issue without agent-work was routed"
fi
for key in needs_human maintainer_blocked leased; do
  if jq -e ".$key == null" <<<"$ROUTE_JSON" >/dev/null 2>&1; then
    ok "hold label honoured: $key"
  else
    bad "hold label ignored: $key"
  fi
done
if jq -e '.marker_wins == "tau_handoff_dispatch"' <<<"$ROUTE_JSON" >/dev/null 2>&1; then
  ok "explicit body markers still take precedence"
else
  bad "body marker route regressed"
fi

# --------------------------------------------------------------------------- #
gate 10 "unit tests"
if "$UV_BIN" run --project "$SCRIPT_DIR" pytest -q "$SCRIPT_DIR/tests" >"$WORK/pytest.log" 2>&1; then
  ok "pytest: $(tail -1 "$WORK/pytest.log")"
else
  bad "pytest failed"
  tail -20 "$WORK/pytest.log" | sed 's/^/        /'
fi

# --------------------------------------------------------------------------- #
printf '\n=====================================\n'
printf 'project-watchdog sanity: %d passed, %d failed\n' "$PASS" "$FAIL"
printf '=====================================\n'
[[ "$FAIL" -eq 0 ]]
