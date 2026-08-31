#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';

const checker = process.env.REPORT_CHECK
  || '/home/graham/workspace/experiments/agent-skills/extensions/pi/lazy-report-shame-shame-shame/status-json-check.mjs';
const mode = process.argv[2] || 'list';

function status(overrides = {}) {
  return JSON.stringify({
    schema: 'pi.agent_status.v1',
    goal: 'adversarial status report probe',
    state: 'done',
    changed: ['changed item'],
    verified: [{ command: 'probe command', result: 'PASS' }],
    proof: ['/tmp/proof.json'],
    ...overrides,
  });
}

function report({ heading = 'Status Report', goal = 'adversarial status report probe', state = 'done', bodyExtra = '', json = status(), trailing = '' } = {}) {
  return `${heading}\n- Goal: ${goal}\n- State: ${state}\n${bodyExtra}\n\n\`\`\`json\n${json}\n\`\`\`${trailing}`;
}

function jsonOnly(json = status()) {
  return `\`\`\`json\n${json}\n\`\`\``;
}

function invalidJson(body) {
  return `Status Report\n- Goal: adversarial status report probe\n- State: done\n\n\`\`\`json\n${body}\n\`\`\``;
}

const cases = {
  'missing-heading-json-only': { expect: 'reject', reason: 'missing_status_report_section', text: jsonOnly() },
  'missing-heading-prose-only-before-json': { expect: 'reject', reason: 'missing_status_report_section', text: `Result complete.\n\n${jsonOnly()}` },
  'lowercase-heading': { expect: 'reject', reason: 'status_report_heading_not_exact', text: report({ heading: 'status report' }) },
  'uppercase-heading': { expect: 'reject', reason: 'status_report_heading_not_exact', text: report({ heading: 'STATUS REPORT' }) },
  'colon-heading': { expect: 'reject', reason: 'status_report_heading_not_exact', text: report({ heading: 'Status Report:' }) },
  'markdown-h2-heading': { expect: 'reject', reason: 'status_report_heading_not_exact', text: report({ heading: '## Status Report' }) },
  'bold-inline-heading': { expect: 'reject', reason: 'status_report_heading_not_exact', text: report({ heading: '**Status Report**' }) },
  'trailing-space-heading': { expect: 'pass', reason: null, text: report({ heading: 'Status Report ' }) },
  'homoglyph-heading': { expect: 'reject', reason: 'status_report_heading_not_exact', text: report({ heading: 'Status ReporΤ' }) },
  'zero-width-heading': { expect: 'reject', reason: 'status_report_heading_not_exact', text: report({ heading: 'Status Repor\u200bt' }) },
  'blockquoted-heading': { expect: 'reject', reason: 'status_report_not_owned', text: report({ heading: '> Status Report' }) },
  'fenced-heading': { expect: 'reject', reason: 'status_report_not_owned', text: `\`\`\`text\nStatus Report\n\`\`\`\n- Goal: adversarial status report probe\n- State: done\n\n${jsonOnly()}` },
  'html-comment-heading': { expect: 'reject', reason: 'status_report_not_owned', text: report({ heading: '<!-- Status Report -->' }) },
  'transcript-heading': { expect: 'reject', reason: 'status_report_not_owned', text: `> Prior assistant:\n> Status Report\n> - Goal: old\n> - State: done\n\n${jsonOnly()}` },
  'goal-mismatch-short': { expect: 'reject', reason: 'status_report_goal_mismatch', text: report({ goal: 'wrong goal' }) },
  'goal-mismatch-case': { expect: 'reject', reason: 'status_report_goal_mismatch', text: report({ goal: 'Adversarial Status Report Probe' }) },
  'goal-mismatch-trailing-word': { expect: 'reject', reason: 'status_report_goal_mismatch', text: report({ goal: 'adversarial status report probe done' }) },
  'goal-omitted': { expect: 'reject', reason: 'status_report_goal_mismatch', text: `Status Report\n- State: done\n\n${jsonOnly()}` },
  'goal-in-code-not-section': { expect: 'reject', reason: 'status_report_goal_mismatch', text: `Status Report\n- State: done\n\n\`Goal: adversarial status report probe\`\n\n${jsonOnly()}` },
  'state-mismatch-continuing': { expect: 'reject', reason: 'status_report_state_mismatch', text: report({ state: 'continuing' }) },
  'state-mismatch-needs-human': { expect: 'reject', reason: 'status_report_state_mismatch', text: report({ state: 'needs_human' }) },
  'state-mismatch-case': { expect: 'reject', reason: 'status_report_state_mismatch', text: report({ state: 'Done' }) },
  'state-omitted': { expect: 'reject', reason: 'status_report_state_mismatch', text: `Status Report\n- Goal: adversarial status report probe\n\n${jsonOnly()}` },
  'state-hidden-in-sentence': { expect: 'reject', reason: 'status_report_state_mismatch', text: `Status Report\n- Goal: adversarial status report probe\n- Current state is done\n\n${jsonOnly()}` },
  'wrong-schema': { expect: 'reject', reason: 'missing_agent_status_json', text: invalidJson('{"schema":"not.pi.agent_status.v1","goal":"adversarial status report probe","state":"done"}') },
  'missing-schema': { expect: 'reject', reason: 'missing_agent_status_json', text: invalidJson('{"goal":"adversarial status report probe","state":"done"}') },
  'json-array': { expect: 'reject', reason: 'missing_agent_status_json', text: invalidJson('[{"schema":"pi.agent_status.v1","goal":"adversarial status report probe","state":"done"}]') },
  'json-wrapper': { expect: 'reject', reason: 'missing_agent_status_json', text: invalidJson('{"status":{"schema":"pi.agent_status.v1","goal":"adversarial status report probe","state":"done"}}') },
  'json5-comment': { expect: 'reject', reason: 'missing_agent_status_json', text: invalidJson('{//comment\n"schema":"pi.agent_status.v1","goal":"adversarial status report probe","state":"done"}') },
  'trailing-comma': { expect: 'reject', reason: 'missing_agent_status_json', text: invalidJson('{"schema":"pi.agent_status.v1","goal":"adversarial status report probe","state":"done",}') },
  'single-quoted-json': { expect: 'reject', reason: 'missing_agent_status_json', text: invalidJson("{'schema':'pi.agent_status.v1','goal':'adversarial status report probe','state':'done'}") },
  'duplicate-goal-key': { expect: 'reject', reason: 'duplicate_agent_status_key', text: report({ json: '{"schema":"pi.agent_status.v1","goal":"wrong","goal":"adversarial status report probe","state":"done","verified":[{"command":"probe command","result":"PASS"}],"proof":["/tmp/proof.json"]}' }) },
  'duplicate-state-key': { expect: 'reject', reason: 'duplicate_agent_status_key', text: report({ json: '{"schema":"pi.agent_status.v1","goal":"adversarial status report probe","state":"continuing","state":"done","verified":[{"command":"probe command","result":"PASS"}],"proof":["/tmp/proof.json"]}' }) },
  'duplicate-schema-key': { expect: 'reject', reason: 'duplicate_agent_status_key', text: report({ json: '{"schema":"wrong","schema":"pi.agent_status.v1","goal":"adversarial status report probe","state":"done","verified":[{"command":"probe command","result":"PASS"}],"proof":["/tmp/proof.json"]}' }) },
  'content-after-json': { expect: 'reject', reason: 'trailing_content_after_status_json', text: report({ trailing: '\nOne more sentence after the status block.' }) },
  'second-fence-after-json': { expect: 'reject', reason: 'trailing_content_after_status_json', text: report({ trailing: '\n```text\nextra\n```' }) },
  'what-remains-heading-continuing': { expect: 'reject', reason: 'banned_what_remains_without_needs_human', text: report({ json: status({ state: 'continuing', verified: [], proof: [], not_done: [{ item: 'next', next_command: 'run next' }] }), state: 'continuing', bodyExtra: '- What remains: run next' }) },
  'what-remains-lowercase-continuing': { expect: 'reject', reason: 'banned_what_remains_without_needs_human', text: report({ json: status({ state: 'continuing', verified: [], proof: [], not_done: [{ item: 'next', next_command: 'run next' }] }), state: 'continuing', bodyExtra: '- what remains: run next' }) },
  'what-remains-spaced-continuing': { expect: 'reject', reason: 'banned_what_remains_without_needs_human', text: report({ json: status({ state: 'continuing', verified: [], proof: [], not_done: [{ item: 'next', next_command: 'run next' }] }), state: 'continuing', bodyExtra: '- What    remains: run next' }) },
  'what-remains-zero-width-continuing': { expect: 'reject', reason: 'banned_what_remains_without_needs_human', text: report({ json: status({ state: 'continuing', verified: [], proof: [], not_done: [{ item: 'next', next_command: 'run next' }] }), state: 'continuing', bodyExtra: '- What rema\u200bins: run next' }) },
  'what-remains-done': { expect: 'reject', reason: 'banned_what_remains_without_needs_human', text: report({ bodyExtra: '- What remains: nothing' }) },
  'needs-human-what-remains-control': { expect: 'pass', reason: null, text: report({ json: status({ state: 'needs_human', verified: [], proof: [], needs_human: { action: 'choose', reason: 'human choice required' } }), state: 'needs_human', bodyExtra: '- What remains: human choice' }) },
  'done-missing-verified': { expect: 'reject', reason: 'invalid_agent_status_json', text: report({ json: status({ verified: [] }) }) },
  'done-missing-proof': { expect: 'reject', reason: 'invalid_agent_status_json', text: report({ json: status({ proof: [] }) }) },
  'continuing-missing-next-command': { expect: 'reject', reason: 'invalid_agent_status_json', text: report({ json: status({ state: 'continuing', verified: [], proof: [], not_done: [] }), state: 'continuing' }) },
  'needs-human-missing-payload': { expect: 'reject', reason: 'invalid_agent_status_json', text: report({ json: status({ state: 'needs_human', verified: [], proof: [] }), state: 'needs_human' }) },
  'failed-missing-triage': { expect: 'reject', reason: 'invalid_agent_status_json', text: report({ json: status({ state: 'failed', verified: [], proof: [] }), state: 'failed' }) },
  'extra-json-field': { expect: 'reject', reason: 'invalid_agent_status_json', text: report({ json: status({ unexpected: 'laundered claim' }) }) },
  'multiple-json-final-valid-bound': { expect: 'pass', reason: null, text: `${jsonOnly(status({ goal: 'old status' }))}\n\n${report()}` },
  'multiple-json-prose-bound-to-earlier': { expect: 'reject', reason: 'status_report_goal_mismatch', text: `Status Report\n- Goal: old status\n- State: done\n\n${jsonOnly(status({ goal: 'old status' }))}\n\n${jsonOnly()}` },
  'bare-trailing-json': { expect: 'reject', reason: 'missing_status_report_section', text: status() },
  'status-report-after-json': { expect: 'reject', reason: 'trailing_content_after_status_json', text: `${jsonOnly()}\n\nStatus Report\n- Goal: adversarial status report probe\n- State: done` },
  'only-old-status-report-before-final-json': { expect: 'reject', reason: 'status_report_goal_mismatch', text: `Status Report\n- Goal: old run\n- State: done\n\n${jsonOnly(status({ goal: 'old run' }))}\n\n\`\`\`json\n${status()}\n\`\`\`` },
};

if (mode === 'list') {
  console.log(Object.keys(cases).join('\n'));
  process.exit(0);
}

const c = cases[mode];
if (!c) {
  console.error(JSON.stringify({ ok: false, mode, error: 'unknown_case', cases: Object.keys(cases) }, null, 2));
  process.exit(2);
}
if (!existsSync(checker)) {
  console.error(JSON.stringify({ ok: false, mode, error: 'checker_missing', checker }, null, 2));
  process.exit(2);
}
const run = spawnSync('node', [checker], {
  input: c.text,
  encoding: 'utf8',
  env: { ...process.env, LRSSS_FORCE_STATUS: '1', LRSSS_MUTATING_TURN: '1' },
  timeout: 20000,
});
let parsed = null;
try { parsed = JSON.parse(String(run.stdout || '').trim()); } catch {}
const actualDecision = parsed?.decision || (run.status === 0 ? 'pass' : 'reject');
const reasons = parsed?.reason_codes || [];
const decisionOk = actualDecision === c.expect;
const reasonOk = c.reason === null || reasons.includes(c.reason);
if (!decisionOk || !reasonOk) {
  console.error(JSON.stringify({
    ok: false,
    mode,
    expected: { decision: c.expect, reason: c.reason },
    actual: { status: run.status, decision: actualDecision, reasons, stdout: run.stdout, stderr: run.stderr },
    input: c.text,
  }, null, 2));
  process.exit(1);
}
console.log(JSON.stringify({ ok: true, mode, decision: actualDecision, reasons }));
