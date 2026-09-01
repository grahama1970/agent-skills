#!/usr/bin/env bash
set -euo pipefail

AGENT_SKILLS_ROOT="${AGENT_SKILLS_ROOT:-$HOME/workspace/experiments/agent-skills}"
KB_ROOT="${KB_ROOT:-$HOME/workspace/experiments/openai-security-kb}"
OPENAI_SPEC_REPO="${OPENAI_SPEC_REPO:-$HOME/workspace/experiments/openai-openapi}"
CURATE_ROOT="$AGENT_SKILLS_ROOT/skills/curate-client"
SOURCE_ROOT="$CURATE_ROOT/sources"
CONFIG="$CURATE_ROOT/configs/openai-security.yaml"
FETCHER="$AGENT_SKILLS_ROOT/skills/fetcher/run.sh"

for required in "$FETCHER" "$CONFIG" \
  "$SOURCE_ROOT/openai-security-primary.txt" \
  "$SOURCE_ROOT/openai-security-secondary.txt"; do
  test -e "$required" || { echo >&2 "missing required path: $required"; exit 2; }
done

mkdir -p \
  "$KB_ROOT/fetch" \
  "$KB_ROOT/knowledge/sources" \
  "$KB_ROOT/source-control" \
  "$KB_ROOT/reports"

# Pin the official OpenAI OpenAPI repository. Its real specification satisfies
# curate-client's current OpenAPI/Terraform source gate.
if test -d "$OPENAI_SPEC_REPO/.git"; then
  git -C "$OPENAI_SPEC_REPO" fetch --depth 1 origin main
  git -C "$OPENAI_SPEC_REPO" checkout --detach origin/main
else
  git clone --depth 1 --branch main \
    https://github.com/openai/openai-openapi.git "$OPENAI_SPEC_REPO"
fi

git -C "$OPENAI_SPEC_REPO" rev-parse HEAD \
  | tee "$KB_ROOT/source-control/openai-openapi.commit"
test -s "$OPENAI_SPEC_REPO/openapi.yaml"

export FETCHER_EMIT_MARKDOWN=1
export FETCHER_EMIT_FIT_MARKDOWN=1
export FETCHER_HTTP_CACHE_DISABLE=1

for lane in primary secondary; do
  manifest="$SOURCE_ROOT/openai-security-${lane}.txt"
  out="$KB_ROOT/fetch/$lane"

  "$FETCHER" get-manifest "$manifest" --out "$out"

  src="$out/fit_markdown"
  test -d "$src" || src="$out/markdown"
  test -d "$src" || {
    echo >&2 "fetcher emitted no Markdown directory for lane=$lane"
    exit 1
  }

  mkdir -p "$KB_ROOT/knowledge/sources/$lane"
  rsync -a --delete "$src/" "$KB_ROOT/knowledge/sources/$lane/"
done

cp "$SOURCE_ROOT/openai-security-primary.txt" "$KB_ROOT/source-control/"
cp "$SOURCE_ROOT/openai-security-secondary.txt" "$KB_ROOT/source-control/"
cp "$SOURCE_ROOT/openai-security-reference.txt" "$KB_ROOT/source-control/"
cp "$SOURCE_ROOT/openai-security-auth-required.txt" "$KB_ROOT/source-control/"

# graph-memory-operator's workspace-ingest contract requires a hygiene review
# for deprecated, contradictory, moved, or limited guidance before reliance.
rg -n -i \
  'deprecated|superseded|this content has moved|no longer supported|legacy|retired|known issue|temporary limitation' \
  "$KB_ROOT/knowledge" \
  | tee "$KB_ROOT/reports/deprecation-and-conflict-scan.txt" || true

cat >&2 <<NEXT
Retrieval and staging completed.

REQUIRED HUMAN GATE:
  Review $KB_ROOT/reports/deprecation-and-conflict-scan.txt
  Review every fetcher consumer_summary.json and non-empty junk_results.jsonl.
  Do not ingest until every missing P0 source has an explicit disposition.

Then run:
  cd $CURATE_ROOT
  ./run.sh plan   --config configs/openai-security.yaml
  ./run.sh chunks --config configs/openai-security.yaml
  ./run.sh ingest --config configs/openai-security.yaml
  ./run.sh verify --config configs/openai-security.yaml

The script intentionally does not perform database mutation automatically.
NEXT
