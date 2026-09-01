#!/usr/bin/env node
import { readFileSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

const checker = process.argv[2] || 'extensions/pi/lazy-report-shame-shame-shame/status-json-check.mjs';
const source = readFileSync(checker, 'utf8');

const banned = [
  'status_report_',
  'statusReportFailures',
  'Status Report',
  'BANNED_',
  'matchedBanned',
  'normalizePolicyText',
  'visibleOwnedLines',
  'hasMarkdown',
  'hasRawHtml',
  'non_ascii_status',
  'bidi_control',
  'raw_html_in_status',
  'markdown_link_in_status',
  'what_remains',
  'new RegExp',
  '.match(',
  '.search(',
  '.split(/',
  '.replace(/',
];
const hits = banned.filter((needle) => source.includes(needle));
if (hits.length) {
  console.error(JSON.stringify({ ok: false, checker, reason: 'status_guard_contains_regex_or_prose_policy', hits }, null, 2));
  process.exit(1);
}

function run(input) {
  const r = spawnSync('node', [checker], {
    input,
    encoding: 'utf8',
    env: { ...process.env, LRSSS_FORCE_STATUS: '1', LRSSS_MUTATING_TURN: '1' },
    timeout: 20000,
  });
  let parsed = null;
  try { parsed = JSON.parse(String(r.stdout || '').trim()); } catch {}
  return { status: r.status, parsed, stdout: r.stdout, stderr: r.stderr };
}

writeFileSync('/tmp/data-first-proof.json', 'check-status-guard-data-first.mjs PASS\n');
const valid = JSON.stringify({
  schema: 'pi.agent_status.v1',
  goal: 'data first guard',
  state: 'done',
  changed: ['typed JSON controls status'],
  verified: [{ command: 'check-status-guard-data-first.mjs', result: 'PASS' }],
  proof: ['/tmp/data-first-proof.json'],
});
const invalid = JSON.stringify({
  schema: 'pi.agent_status.v1',
  goal: 'data first guard',
  state: 'done',
  changed: ['prose cannot rescue missing proof'],
  verified: [{ command: 'fake', result: 'PASS' }],
  proof: [],
});

const badProseValidJson = run(`Status Report\n- Goal: wrong\n- State: failed\n- What remains: everything\n<script>hidden</script>\n\n\`\`\`json\n${valid}\n\`\`\``);
if (badProseValidJson.status !== 0 || badProseValidJson.parsed?.decision !== 'pass') {
  console.error(JSON.stringify({ ok: false, reason: 'valid_json_was_not_authoritative', actual: badProseValidJson }, null, 2));
  process.exit(1);
}

const goodProseInvalidJson = run(`Status Report\n- Goal: data first guard\n- State: done\n- Changed: typed JSON controls status\n- Verified: check-status-guard-data-first.mjs -> PASS\n- Proof: /tmp/data-first-proof.json\n\n\`\`\`json\n${invalid}\n\`\`\``);
if (goodProseInvalidJson.status === 0 || goodProseInvalidJson.parsed?.decision !== 'reject' || !goodProseInvalidJson.parsed?.reason_codes?.includes('invalid_agent_status_json')) {
  console.error(JSON.stringify({ ok: false, reason: 'prose_rescued_invalid_json', actual: goodProseInvalidJson }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true, checker, decision: 'data_first_status_guard_verified' }));
