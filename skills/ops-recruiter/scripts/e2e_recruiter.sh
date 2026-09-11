#!/bin/bash
# ops-recruiter E2E = the John Davis (TEKsystems / Amex Senior AI Engineer) RESPONSE pipeline
# on his real thread. Proves everything ops-recruiter owns for producing that reply:
#   store his LinkedIn inbound -> Memory recall marks the thread existing ->
#   the response ask-chain (webgpt draft + webkimi humanize) is emitted ->
#   recruiter deep-research is seeded -> claim-bind gate is fail-closed.
# real_world: hits the live Memory daemon; FAILS honestly if Memory is down.
# The webgpt/webkimi prose is composed via $ask (live browser) and is NOT run here;
# this proves the response pipeline is wired and claim-safe, not the prose quality.
set -e
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SKILL_DIR"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# 1) Ingest the real LinkedIn inbound (John Davis / TEKsystems / Amex Senior AI Engineer).
THREAD="john-davis-teksystems-amex"
cat > "$work/msg.json" <<JSON
{"source":"linkedin","thread_id":"$THREAD","message_id":"001","direction":"inbound",
 "recruiter":"John Davis","company":"American Express (via TEKsystems)","role":"Senior AI Engineer",
 "body":"Hi Graham, I'm John, a Technical Recruiter with TEKsystems. Your experience building AI applications and agent-based systems caught my attention. Senior AI Engineer with American Express: production AI, agentic workflows from scratch, stakeholder partnering. Open to connecting?",
 "received_at":"2026-09-11T00:00:00Z","tags":["recruiter:John Davis","thread:$THREAD","source:linkedin"]}
JSON
./run.sh store --message "$work/msg.json" | grep -q '"stored_key"' || { echo "E2E FAIL: store did not report stored_key"; exit 1; }

# 2) Reply context: build must recall the stored thread and mark the relationship existing.
printf 'Are you open to connecting about the Amex Senior AI Engineer role?\n' > "$work/reply.md"
printf 'Senior AI Engineer, American Express: production AI, agentic workflows from scratch.\n' > "$work/role.md"
printf 'ARCOS technical lead. LLM/agent systems. 430 commits on pdf_oxide.\n' > "$work/resume.md"
out=$(./run.sh build --recruiter-message "$work/reply.md" --role "$work/role.md" --resume "$work/resume.md" \
  --recruiter "John Davis" --thread-id "$THREAD" --research --out "$work/o")
echo "$out" | grep -q '"relationship": "existing"' || { echo "E2E FAIL: prior correspondence not recalled (relationship != existing)"; echo "$out"; exit 1; }
grep -q 'Relationship: existing' "$work/o/context-packet.md" || { echo "E2E FAIL: packet missing existing-relationship framing"; exit 1; }
grep -q 'John' "$work/o/context-packet.md" || { echo "E2E FAIL: packet missing prior-thread body"; exit 1; }
# recruiter deep-research (LinkedIn page + history) must be seeded into the ask chain
research_seeded=false
echo "$out" | grep -q 'John Davis recruiter LinkedIn profile background history' && research_seeded=true
$research_seeded || { echo "E2E FAIL: recruiter deep-research brave-search step not emitted"; echo "$out"; exit 1; }
# the RESPONSE-generation chain must be wired: webgpt drafts, webkimi humanizes (composed via \$ask)
response_chain_wired=false
if echo "$out" | grep -q 'webgpt' && echo "$out" | grep -q 'webkimi'; then response_chain_wired=true; fi
$response_chain_wired || { echo "E2E FAIL: response ask-chain (webgpt draft + webkimi humanize) not emitted"; echo "$out"; exit 1; }

# 3) Claim-bind gate rejects a fabricated metric even in an e2e reply.
printf 'I delivered 987 Amex projects.\n' > "$work/bad.md"
gate_rejected=false
if ./run.sh gate --draft "$work/bad.md" --claims "$work/resume.md" >/dev/null 2>&1; then
  echo "E2E FAIL: gate accepted an unbacked metric"; exit 1
else
  gate_rejected=true
fi

# Independent readback oracle: durable result artifact the fixture asserts on.
rel=$(python3 -c "import json,sys;print(json.loads(sys.argv[1])['relationship'])" "$out")
mkdir -p "$SKILL_DIR/artifacts"
cat > "$SKILL_DIR/artifacts/e2e-result.json" <<JSON
{"relationship":"$rel","gate_rejected":$gate_rejected,"research_seeded":$research_seeded,"response_chain_wired":$response_chain_wired,"thread_id":"$THREAD"}
JSON
echo "E2E PASS: John response pipeline — store -> recall(existing) -> response chain wired -> research seeded -> gate(fail-closed)"
