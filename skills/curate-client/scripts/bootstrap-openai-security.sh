#!/usr/bin/env bash
set -euo pipefail

AGENT_SKILLS_ROOT="${AGENT_SKILLS_ROOT:-$HOME/workspace/experiments/agent-skills}"
KB_ROOT="${KB_ROOT:-$HOME/workspace/experiments/openai-security-kb}"
FETCH_ROOT="${FETCH_ROOT:-$HOME/workspace/experiments/openai-security-fetch}"
STAGED_ROOT="${STAGED_ROOT:-$HOME/workspace/experiments/openai-security-staged}"
CURATE_ROOT="$AGENT_SKILLS_ROOT/skills/curate-client"
SOURCE_ROOT="$CURATE_ROOT/sources"
CONFIG="$CURATE_ROOT/configs/openai-security.yaml"
FETCHER="$AGENT_SKILLS_ROOT/skills/fetcher/run.sh"
STAGER="$CURATE_ROOT/scripts/stage-openai-security.py"
CONTROL_ROOT="$KB_ROOT/.source-control"
REPORT_ROOT="$KB_ROOT/.reports"

for required in \
  "$FETCHER" \
  "$STAGER" \
  "$CONFIG" \
  "$SOURCE_ROOT/openai-security-primary.txt" \
  "$SOURCE_ROOT/openai-security-secondary.txt" \
  "$SOURCE_ROOT/openai-security-p0-required.txt"; do
  test -e "$required" || { echo >&2 "missing required path: $required"; exit 2; }
done

mkdir -p "$FETCH_ROOT" "$STAGED_ROOT" "$KB_ROOT/knowledge" "$CONTROL_ROOT" "$REPORT_ROOT"

for lane in primary secondary; do
  "$FETCHER" get-manifest \
    "$SOURCE_ROOT/openai-security-${lane}.txt" \
    --out "$FETCH_ROOT/$lane" \
    --emit download,text,md,fit_md
done

python3 "$STAGER" \
  --lane primary="$FETCH_ROOT/primary/consumer_summary.json" \
  --lane secondary="$FETCH_ROOT/secondary/consumer_summary.json" \
  --staged-root "$STAGED_ROOT" \
  --manifest-out "$KB_ROOT/source-manifest.json" \
  --receipt-out "$REPORT_ROOT/staging-receipt.json" \
  --required-url-file "$SOURCE_ROOT/openai-security-p0-required.txt" \
  --expected-url-file primary="$SOURCE_ROOT/openai-security-primary.txt" \
  --expected-url-file secondary="$SOURCE_ROOT/openai-security-secondary.txt" \
  --scope client:openai-privacy

for name in \
  openai-security-primary.txt \
  openai-security-secondary.txt \
  openai-security-p0-required.txt \
  openai-security-reference.txt \
  openai-security-auth-required.txt \
  openai-security-implementation-inputs.txt; do
  test ! -f "$SOURCE_ROOT/$name" || cp "$SOURCE_ROOT/$name" "$CONTROL_ROOT/"
done

rg -n -i \
  'deprecated|superseded|this content has moved|no longer supported|legacy|retired|known issue|temporary limitation' \
  "$STAGED_ROOT" \
  | tee "$REPORT_ROOT/deprecation-and-conflict-scan.txt" || true

cat >&2 <<NEXT
Retrieval and source-bound staging completed.

REQUIRED REVIEW GATE:
  1. Review every $FETCH_ROOT/*/consumer_summary.json.
  2. Review $REPORT_ROOT/staging-receipt.json.
  3. Review $REPORT_ROOT/deprecation-and-conflict-scan.txt.
  4. Resolve every warning that could affect an interview claim.

After approval, promote through curate-client and Graph Memory:
  cd $CURATE_ROOT
  rm -rf "$KB_ROOT/knowledge/curated"
  ./run.sh plan   --config configs/openai-security.yaml
  ./run.sh chunks --config configs/openai-security.yaml
  ./run.sh ingest --config configs/openai-security.yaml
  ./run.sh verify --config configs/openai-security.yaml

No database mutation was performed by this bootstrap.
NEXT
