#!/bin/bash
# ops-recruiter LIVE e2e = actually PRODUCE John's reply and prove it is claim-safe.
# Runs the real capability, not the wiring: build packet -> $ask webgpt draft ->
# $ask webkimi humanize -> claim-bind gate on the PRODUCED draft.
# live_e2e: real browser transport. If a provider is down it prints BLOCKED_EXTERNAL
# (honest: capability not proven this run) rather than faking a pass.
set -u
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$SKILL_DIR/../.." && pwd)"
ASK="$REPO/skills/ask/run.sh"
work=$(mktemp -d)
art="$SKILL_DIR/artifacts"; mkdir -p "$art"
trap 'rm -rf "$work"' EXIT
THREAD="john-davis-teksystems-amex"

printf 'Hi Graham, I am John, a Technical Recruiter with TEKsystems. Your experience building AI applications and agent-based systems caught my attention. Senior AI Engineer with American Express: production AI, agentic workflows from scratch, partnering with business stakeholders. Open to connecting?\n' > "$work/msg.md"
printf 'Senior AI Engineer, American Express (via TEKsystems): production AI, agentic workflows from scratch, stakeholder partnering, LLMs/agent systems.\n' > "$work/role.md"
cp "$REPO/RESUME.md" "$work/resume.md"

# 1) store inbound + build packet (deterministic, owned)
cat > "$work/in.json" <<JSON
{"source":"linkedin","thread_id":"$THREAD","message_id":"001","direction":"inbound","recruiter":"John Davis","company":"American Express (via TEKsystems)","role":"Senior AI Engineer","body":"John (TEKsystems) about Amex Senior AI Engineer","received_at":"2026-09-11T00:00:00Z","tags":["recruiter:John Davis","thread:$THREAD","source:linkedin"]}
JSON
"$SKILL_DIR/run.sh" store --message "$work/in.json" >/dev/null 2>&1 || { echo "BLOCKED_EXTERNAL: memory store unavailable"; exit 0; }
"$SKILL_DIR/run.sh" build --recruiter-message "$work/msg.md" --role "$work/role.md" --resume "$work/resume.md" \
  --recruiter "John Davis" --thread-id "$THREAD" --out "$work/o" >/dev/null 2>&1 || { echo "E2E FAIL: build failed"; exit 1; }
packet="$work/o/context-packet.md"
python3 "$REPO/skills/ask/scripts/browser_prompt_preflight.py" --prompt "draft" "$packet" >/dev/null 2>&1 || { echo "E2E FAIL: packet not browser-submittable"; exit 1; }

# 2) LIVE webgpt draft
bash "$ASK" webgpt --browser-tab-lifecycle fresh-keep --run-output-root "$work/wg" \
  --attach-file "$packet" "Draft a warm, collaborative reply to recruiter John about the Amex Senior AI Engineer role. Use ONLY facts in the attached ledger; never invent employers, metrics, dates, or clearances. LinkedIn length. Output only the reply." >/dev/null 2>&1 || true
wg=$(find "$work/wg" -path '*handler-webgpt/response.md' 2>/dev/null | head -1)
[ -s "$wg" ] || { echo "BLOCKED_EXTERNAL: webgpt produced no draft (provider/browser down)"; exit 0; }

# 3) LIVE webkimi humanize
bash "$ASK" webkimi --browser-tab-lifecycle fresh-keep --run-output-root "$work/wk" \
  --attach-file "$wg" "Humanize this recruiter reply for warm, collaborative, non-templated prose. Add no new factual claim. Output only the final reply." >/dev/null 2>&1 || true
wk=$(find "$work/wk" -path '*handler-webkimi/response.md' 2>/dev/null | head -1)
[ -s "$wk" ] || { echo "BLOCKED_EXTERNAL: webkimi produced no draft (provider/browser down)"; exit 0; }

# 4) claim-bind gate on the PRODUCED draft (fail-closed capability proof)
gate_pass=false
if "$SKILL_DIR/run.sh" gate --draft "$wk" --claims "$work/resume.md" >/dev/null 2>&1; then gate_pass=true; fi
draft_sha=$(sha256sum "$wk" | cut -d' ' -f1)
cp "$wk" "$art/john-reply.md"
cat > "$art/e2e-live-result.json" <<JSON
{"webgpt_produced":true,"webkimi_produced":true,"gate_pass":$gate_pass,"draft_sha256":"$draft_sha","thread_id":"$THREAD"}
JSON
$gate_pass || { echo "E2E FAIL: produced draft failed the claim-bind gate"; exit 1; }
echo "E2E PASS: produced John reply via webgpt->webkimi and gate PASSED (claim-safe)"
