#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

"$SCRIPT_DIR/run.sh" list --json | grep -q '"immutable-goal-mvp-loop"'
"$SCRIPT_DIR/run.sh" find "anti thrash immutable goal mvp" --json | grep -q '"immutable-goal-mvp-loop"'
"$SCRIPT_DIR/run.sh" materialize immutable-goal-mvp-loop \
  --set dag_id=sanity-loop \
  --set goal_id=sanity-goal \
  --set goal_hash=sha256:1111111111111111111111111111111111111111111111111111111111111111 \
  --set immutable_goal="Ship a bounded sanity MVP with proof" \
  --set target_repo=local/agent-skills \
  --set target=dag-templates-sanity \
  --output "$TMP" >/dev/null
"$SCRIPT_DIR/run.sh" chart "$TMP" | grep -q 'schema=tau.dag_contract.v1 -> ask.dag.v1'
"$SCRIPT_DIR/run.sh" chart "$TMP" | grep -q 'brave-search'

echo "dag-templates sanity PASS"
