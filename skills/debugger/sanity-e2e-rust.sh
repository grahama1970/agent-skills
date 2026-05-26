#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$(mktemp -d /tmp/debugger-rust-e2e.XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT

if ! command -v rust-gdb >/dev/null 2>&1; then
  echo "rust-gdb is required for real Rust debugger E2E proof" >&2
  exit 1
fi

cat > "$WORK_DIR/main.rs" <<'RS'
fn classify(value: i32) -> &'static str {
    let label = if value > 10 { "large" } else { "small" };
    label
}

fn main() {
    let _ = classify(14);
}
RS

binary="$WORK_DIR/sample"
rustc -g -C opt-level=0 -o "$binary" "$WORK_DIR/main.rs"

proof=/tmp/debugger-rust-e2e-proof.txt
rust-gdb -q -batch \
  -ex "break $WORK_DIR/main.rs:3" \
  -ex run \
  -ex 'print value' \
  -ex 'print label' \
  -ex bt \
  --args "$binary" | tee "$proof"

rg 'Breakpoint 1, .*classify \(value=14\)' "$proof" >/dev/null
rg -F '$1 = 14' "$proof" >/dev/null
rg -F '$2 = "large"' "$proof" >/dev/null

echo "debugger Rust E2E sanity passed: $proof"
