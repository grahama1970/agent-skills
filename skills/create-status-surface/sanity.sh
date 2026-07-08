#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${TMPDIR:-/tmp}/create-status-surface-sanity"
rm -rf "$OUT"
mkdir -p "$OUT"

"$SCRIPT_DIR/run.sh" render \
  --input "$SCRIPT_DIR/fixtures/persona_dream_global_progress.v1.json" \
  --output-dir "$OUT" \
  --title "Persona Dream Fixture" \
  --json > "$OUT/render.stdout.json"

"$SCRIPT_DIR/run.sh" validate \
  --surface "$OUT/status_surface.json" \
  --receipt-out "$OUT/status_surface_validation_receipt.json" \
  --json > "$OUT/validate.stdout.json"

"$SCRIPT_DIR/run.sh" tau-dag \
  --surface-receipt "$OUT/status_surface_receipt.json" \
  --output "$OUT/tau_status_surface_dag_contract.v1.json" \
  --json > "$OUT/tau-dag.stdout.json"

"$SCRIPT_DIR/run.sh" tau-check \
  --dag "$OUT/tau_status_surface_dag_contract.v1.json" \
  --receipt-out "$OUT/tau_status_surface_dag_validation_receipt.json" \
  --json > "$OUT/tau-check.stdout.json"

jq -e '
  .status == "PASS_STATUS_SURFACE_RENDER" and
  .actual_provider_call_attempts == 0 and
  .live_tau_dag_execution_started == false
' "$OUT/status_surface_receipt.json" >/dev/null

jq -e '
  .status == "PASS_STATUS_SURFACE_VALIDATION" and
  .provider_ready == false and
  .live_submit_ready == false
' "$OUT/status_surface_validation_receipt.json" >/dev/null

jq -e '
  .schema == "tau.dag_contract.v1" and
  .entry_node == "render-status-surface" and
  (.fail_closed_on | index("provider_ready_claimed")) and
  (.nodes[] | select(.id == "human" and .executor == "human"))
' "$OUT/tau_status_surface_dag_contract.v1.json" >/dev/null

jq -e '
  .status == "PASS_TAU_STATUS_SURFACE_DAG_CONTRACT" and
  .live_tau_dag_execution_started == false and
  .actual_provider_call_attempts == 0
' "$OUT/tau_status_surface_dag_validation_receipt.json" >/dev/null

echo "PASS_CREATE_STATUS_SURFACE_SANITY $OUT"
