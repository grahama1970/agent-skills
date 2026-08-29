#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
SESSION="$TMP_DIR/session.jsonl"
LOCAL_OUT="$TMP_DIR/local-training.jsonl"
LIVE_OUT="$TMP_DIR/live-training.jsonl"

cat > "$SESSION" <<'JSONL'
{"type":"message","id":"u1","message":{"role":"user","content":[{"type":"text","text":"what is your actual status"}]}}
{"type":"message","id":"a1","message":{"role":"assistant","content":[{"type":"text","text":"Committed and pushed. Done."}]}}
{"type":"message","id":"u2","message":{"role":"user","content":[{"type":"text","text":"explain git branches"}]}}
{"type":"message","id":"a2","message":{"role":"assistant","content":[{"type":"text","text":"A branch is a movable pointer to a commit."}]}}
JSONL

chmod +x "$SKILL_DIR/run.sh" "$SKILL_DIR/scripts/capture-last-assistant.mjs"

local_result="$($SKILL_DIR/run.sh capture --session "$SESSION" --entry-id a1 --out "$LOCAL_OUT" --verdict reject --reason commit_laundering --note "missing actual status" --no-memory)"
printf '%s\n' "$local_result"

node - "$LOCAL_OUT" <<'JS'
const fs = require('fs');
const out = process.argv[2];
const lines = fs.readFileSync(out, 'utf8').trim().split(/\n/);
if (lines.length !== 1) throw new Error(`expected 1 JSONL row, got ${lines.length}`);
const row = JSON.parse(lines[0]);
if (row.schema !== 'lazy_report_shame.training_example.v2') throw new Error('bad schema');
if (row.human_verdict !== 'reject') throw new Error('bad verdict');
if (!row.human_reasons.includes('commit_laundering')) throw new Error('bad reason');
if (row.classifier_label !== 'bullshit_update') throw new Error('bad classifier label');
if (row.assistant_entry_id !== 'a1') throw new Error('wrong assistant entry');
if (!row.user_text.includes('actual status')) throw new Error('missing prior user text');
if (!row.assistant_text.includes('Committed and pushed. Done.')) throw new Error('missing response text');
if (!row.response_sha256.startsWith('sha256:')) throw new Error('missing response hash');
console.log('PASS local shame capture');
JS

live_result="$($SKILL_DIR/run.sh capture --text "Committed and pushed. Done." --out "$LIVE_OUT" --verdict reject --reason vague_git_update --note "synthetic live memory write sanity" --synthetic --memory-collection shame_training_examples)"
printf '%s\n' "$live_result"

node - "$live_result" <<'JS'
const payload = JSON.parse(process.argv[2]);
if (!payload.ok) throw new Error('capture did not report ok');
if (payload.memory?.collection !== 'shame_training_examples') throw new Error('wrong memory collection');
if (payload.memory?.read_back_count !== 1) throw new Error('missing memory read-back');
if (!payload.response_sha256?.startsWith('sha256:')) throw new Error('missing response hash');
console.log('PASS live memory capture readback');
JS

echo 'SHAME_SANITY_OK'
