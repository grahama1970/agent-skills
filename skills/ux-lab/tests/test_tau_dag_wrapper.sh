#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$(dirname "$SCRIPT_DIR")/run.sh"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/ux-lab-tau-wrapper-test.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT

PASS=0
FAIL=0

pass() {
    echo "PASS: $1"
    PASS=$((PASS + 1))
}

fail() {
    echo "FAIL: $1" >&2
    FAIL=$((FAIL + 1))
}

make_fake_tau() {
    local path="$1"
    cat >"$path" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
    dag-view-capabilities)
        printf '%s\n' "${FAKE_TAU_CAPABILITIES:-{\"schema\":\"tau.dag_viewer_capabilities.v1\",\"read_only\":true}}"
        ;;
    dag-view)
        shift
        printf '%s\n' "$@" >"${FAKE_TAU_ARGS_LOG:?}"
        exit "${FAKE_TAU_VIEW_EXIT:-0}"
        ;;
    *)
        exit 97
        ;;
esac
SH
    chmod +x "$path"
}

fake_tau="$TMP_ROOT/tau"
args_log="$TMP_ROOT/args.log"
make_fake_tau "$fake_tau"

if TAU_BIN="$fake_tau" FAKE_TAU_ARGS_LOG="$args_log" \
    "$RUNNER" tau-dag-view --run-dir "/tmp/run with spaces" --host 127.0.0.1 --port 0; then
    expected=$'--run-dir\n/tmp/run with spaces\n--host\n127.0.0.1\n--port\n0'
    if [[ "$(cat "$args_log")" == "$expected" ]]; then
        pass "TAU_BIN override delegates exact arguments"
    else
        fail "TAU_BIN override changed delegated arguments"
    fi
else
    fail "compatible Tau capability receipt did not delegate"
fi

path_dir="$TMP_ROOT/path-bin"
mkdir -p "$path_dir"
cp "$fake_tau" "$path_dir/tau"
if PATH="$path_dir:$PATH" FAKE_TAU_ARGS_LOG="$args_log" \
    "$RUNNER" tau-dag-view --run-dir /tmp/path-discovery; then
    pass "Tau is discovered from PATH"
else
    fail "Tau PATH discovery failed"
fi

set +e
TAU_BIN="$TMP_ROOT/missing-tau" "$RUNNER" tau-dag-view --run-dir /tmp/run \
    >"$TMP_ROOT/missing.out" 2>"$TMP_ROOT/missing.err"
status=$?
set -e
if [[ "$status" -eq 2 ]] && grep -q "Tau is required" "$TMP_ROOT/missing.err"; then
    pass "missing Tau blocks"
else
    fail "missing Tau did not block with exit 2"
fi

set +e
TAU_BIN="$fake_tau" FAKE_TAU_ARGS_LOG="$args_log" \
    FAKE_TAU_CAPABILITIES='{"schema":"tau.other.v1","read_only":true}' \
    "$RUNNER" tau-dag-view --run-dir /tmp/run >/dev/null 2>"$TMP_ROOT/schema.err"
status=$?
set -e
if [[ "$status" -eq 2 ]] && grep -q "capabilities are incompatible" "$TMP_ROOT/schema.err"; then
    pass "wrong capability schema blocks"
else
    fail "wrong capability schema was accepted"
fi

set +e
TAU_BIN="$fake_tau" FAKE_TAU_ARGS_LOG="$args_log" \
    FAKE_TAU_CAPABILITIES='{"schema":"tau.dag_viewer_capabilities.v1","read_only":false}' \
    "$RUNNER" tau-dag-view --run-dir /tmp/run >/dev/null 2>"$TMP_ROOT/read-only.err"
status=$?
set -e
if [[ "$status" -eq 2 ]] && grep -q "capabilities are incompatible" "$TMP_ROOT/read-only.err"; then
    pass "read_only=false blocks"
else
    fail "read_only=false was accepted"
fi

set +e
TAU_BIN="$fake_tau" FAKE_TAU_ARGS_LOG="$args_log" FAKE_TAU_VIEW_EXIT=37 \
    "$RUNNER" tau-dag-view --run-dir /tmp/run >/dev/null 2>&1
status=$?
set -e
if [[ "$status" -eq 37 ]]; then
    pass "Tau dag-view exit code is preserved"
else
    fail "Tau dag-view exit code was not preserved"
fi

wrapper_body="$(sed -n '/^tau_dag_view()/,/^case /p' "$RUNNER")"
if [[ -n "$wrapper_body" ]] && \
    ! grep -Eqi 'sqlite|react|pi-mono|dag_runtime|runtime_event|source-dag\.json' <<<"$wrapper_body"; then
    pass "wrapper contains no copied viewer implementation"
else
    fail "wrapper contains a forbidden viewer implementation reference"
fi

if [[ "$(wc -l <"$RUNNER")" -le 100 ]]; then
    pass "UX Lab runner remains a thin launcher"
else
    fail "UX Lab runner exceeds the thin-launcher size bound"
fi

echo "Results: ${PASS} passed, ${FAIL} failed"
[[ "$FAIL" -eq 0 ]]
