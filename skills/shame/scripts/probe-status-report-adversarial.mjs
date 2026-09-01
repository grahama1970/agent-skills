#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { existsSync, writeFileSync } from 'node:fs';

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
  return `${heading}\n- Goal: ${goal}\n- State: ${state}\n- Changed: changed item\n- Verified: probe command -> PASS\n- Proof: /tmp/proof.json\n${bodyExtra}\n\n\`\`\`json\n${json}\n\`\`\`${trailing}`;
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
  'colon-heading': { expect: 'reject', reason: 'missing_status_report_section', text: report({ heading: 'Status Report:' }) },
  'markdown-h2-heading': { expect: 'pass', reason: null, text: report({ heading: '## Status Report' }) },
  'bold-inline-heading': { expect: 'reject', reason: 'missing_status_report_section', text: report({ heading: '**Status Report**' }) },
  'trailing-space-heading': { expect: 'pass', reason: null, text: report({ heading: 'Status Report ' }) },
  'homoglyph-heading': { expect: 'reject', reason: 'non_ascii_status_report_text', text: report({ heading: 'Status ReporΤ' }) },
  'zero-width-heading': { expect: 'reject', reason: 'non_ascii_status_report_text', text: report({ heading: 'Status Repor\u200bt' }) },
  'blockquoted-heading': { expect: 'reject', reason: 'missing_status_report_section', text: report({ heading: '> Status Report' }) },
  'fenced-heading': { expect: 'reject', reason: 'status_report_not_owned', text: `\`\`\`text\nStatus Report\n\`\`\`\n- Goal: adversarial status report probe\n- State: done\n\n${jsonOnly()}` },
  'unequal-length-fenced-heading': { expect: 'reject', reason: 'status_report_not_owned', text: `\`\`\`\`text\nStatus Report\n\`\`\`json\n- Goal: adversarial status report probe\n- State: done\n\`\`\`\`\n\n${jsonOnly()}` },
  'html-comment-heading': { expect: 'reject', reason: 'missing_status_report_section', text: report({ heading: '<!-- Status Report -->' }) },
  'multiline-html-comment-status-report': { expect: 'reject', reason: 'missing_status_report_section', text: `<!--\nStatus Report\n- Goal: adversarial status report probe\n- State: done\n- Changed: changed item\n- Verified: probe command -> PASS\n- Proof: /tmp/proof.json\n-->\n\n${jsonOnly()}` },
  'hidden-div-heading': { expect: 'reject', reason: 'raw_html_in_status_report', text: `<div hidden><span></span>\nStatus Report\n- Goal: adversarial status report probe\n- State: done\n</div>\n\n${jsonOnly()}` },
  'pre-heading': { expect: 'reject', reason: 'raw_html_in_status_report', text: `<pre>\nStatus Report\n- Goal: adversarial status report probe\n- State: done\n- Changed: changed item\n- Verified: probe command -> PASS\n- Proof: /tmp/proof.json\n</pre>\n\n${jsonOnly()}` },
  'pre-json-fence': { expect: 'reject', reason: 'missing_agent_status_json', text: `Status Report\n- Goal: adversarial status report probe\n- State: done\n- Changed: changed item\n- Verified: probe command -> PASS\n- Proof: /tmp/proof.json\n\n<pre>\n\`\`\`json\n${status()}\n\`\`\`\n</pre>` },
  'transcript-heading': { expect: 'reject', reason: 'missing_status_report_section', text: `> Prior assistant:\n> Status Report\n> - Goal: old\n> - State: done\n\n${jsonOnly()}` },
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
  'what-remains-html-comment-inside-word-continuing': { expect: 'reject', reason: 'banned_what_remains_without_needs_human', text: report({ json: status({ state: 'continuing', verified: [], proof: [], not_done: [{ item: 'next', next_command: 'run next' }] }), state: 'continuing', bodyExtra: '- What re<!--x-->mains: run next' }) },
  'what-remains-html-entity-continuing': { expect: 'reject', reason: 'banned_what_remains_without_needs_human', text: report({ json: status({ state: 'continuing', not_done: [{ item: 'What remains: deploy the patch', next_command: 'deploy the patch' }] }), state: 'continuing', bodyExtra: '- Not done: What rem&#97;ins: deploy the patch -> deploy the patch' }) },
  'what-remains-word-joiner-continuing': { expect: 'reject', reason: 'banned_what_remains_without_needs_human', text: report({ json: status({ changed: ['What re\u2060mains'] }), bodyExtra: '- Changed: What re\u2060mains' }) },
  'what-remains-nobreak-entity-continuing': { expect: 'reject', reason: 'banned_what_remains_without_needs_human', text: report({ json: status({ changed: ['What re&NoBreak;mains'] }), bodyExtra: '- Changed: What re&NoBreak;mains' }) },
  'what-remains-tab-entity-continuing': { expect: 'reject', reason: 'unknown_html_entity_in_status_report', text: report({ json: status({ state: 'continuing', not_done: [{ item: 'deploy the patch', next_command: 'deploy the patch' }] }), state: 'continuing', bodyExtra: '- Not done: deploy the patch -> deploy the patch\n## What&Tab;remains\nDeploy the patch.' }) },
  'what-remains-bidi-rlo-entity-continuing': { expect: 'reject', reason: 'bidi_control_in_status_report', text: report({ json: status({ state: 'continuing', not_done: [{ item: 'What \u202esniamer\u202c', next_command: './continue' }] }), state: 'continuing', bodyExtra: '- Not done: What &#x202E;sniamer&#x202C; -> ./continue' }) },
  'what-remains-bidi-rlo-raw-continuing': { expect: 'reject', reason: 'bidi_control_in_status_report', text: report({ json: status({ state: 'continuing', not_done: [{ item: 'What \u202esniamer\u202c', next_command: './continue' }] }), state: 'continuing', bodyExtra: '- Not done: What \u202esniamer\u202c -> ./continue' }) },
  'bidi-heading': { expect: 'reject', reason: 'bidi_control_in_status_report', text: report({ heading: 'Status \u202eReport\u202c' }) },
  'what-remains-done': { expect: 'reject', reason: 'banned_what_remains_without_needs_human', text: report({ bodyExtra: '- What remains: nothing' }) },
  'remaining-fixes-continuing': { expect: 'reject', reason: 'banned_unresolved_stop_without_needs_human', text: report({ json: status({ state: 'continuing', verified: [], proof: [], not_done: [{ item: 'next', next_command: 'run next' }] }), state: 'continuing', bodyExtra: '- Remaining fixes: run next' }) },
  'left-to-do-done': { expect: 'reject', reason: 'banned_unresolved_stop_without_needs_human', text: report({ bodyExtra: '- Left to do: reviewer' }) },
  'needs-human-what-remains-control': { expect: 'pass', reason: null, text: report({ json: status({ state: 'needs_human', needs_human: { action: 'choose', reason: 'human choice required' } }), state: 'needs_human', bodyExtra: '- Needs Human: choose because human choice required\n- What remains: human choice' }) },
  'done-missing-verified': { expect: 'reject', reason: 'invalid_agent_status_json', text: report({ json: status({ verified: [] }) }) },
  'done-missing-proof': { expect: 'reject', reason: 'invalid_agent_status_json', text: report({ json: status({ proof: [] }) }) },
  'continuing-missing-next-command': { expect: 'reject', reason: 'invalid_agent_status_json', text: report({ json: status({ state: 'continuing', verified: [], proof: [], not_done: [] }), state: 'continuing' }) },
  'needs-human-missing-payload': { expect: 'reject', reason: 'invalid_agent_status_json', text: report({ json: status({ state: 'needs_human', verified: [], proof: [] }), state: 'needs_human' }) },
  'failed-missing-triage': { expect: 'reject', reason: 'invalid_agent_status_json', text: report({ json: status({ state: 'failed', verified: [], proof: [] }), state: 'failed' }) },
  'extra-json-field': { expect: 'reject', reason: 'invalid_agent_status_json', text: report({ json: status({ unexpected: 'laundered claim' }) }) },
  'quoted-values-wrong-labels': { expect: 'reject', reason: 'status_report_changed_mismatch', text: `Status Report\n- Goal: adversarial status report probe\n- State: done\n- Note: changed item probe command PASS /tmp/proof.json are just quoted strings\n\n${jsonOnly()}` },
  'hidden-html-attribute-values': { expect: 'reject', reason: 'raw_html_in_status_report', text: `Status Report\n- Goal: adversarial status report probe\n- State: done\n- <span hidden>changed item probe command PASS /tmp/proof.json</span>\n\n${jsonOnly()}` },
  'bdo-reversed-what-remains': { expect: 'reject', reason: 'raw_html_in_status_report', text: `Status Report\n- Goal: adversarial status report probe\n- State: done\n- Changed: changed item\n- Verified: probe command -> PASS\n- Proof: <bdo dir="rtl">sniamer tahW</bdo>\n\n${jsonOnly(status({ proof: ['sniamer tahW'] }))}` },
  'bdo-visible-projection-mismatch': { expect: 'reject', reason: 'raw_html_in_status_report', text: `Status Report\n- Goal: adversarial status report probe\n- State: done\n- Changed: <bdo dir="rtl">deyolped</bdo>\n- Verified: probe command -> PASS\n- Proof: /tmp/proof.json\n\n${jsonOnly(status({ changed: ['deyolped'] }))}` },
  'inline-css-bidi-override': { expect: 'reject', reason: 'raw_html_in_status_report', text: `Status Report\n- Goal: adversarial status report probe\n- State: done\n- Changed: changed item\n- Verified: probe command -> PASS\n- Proof: <span style="direction:rtl;unicode-bidi:bidi-override">sniamer tahW</span>\n\n${jsonOnly(status({ proof: ['sniamer tahW'] }))}` },
  'bdo-ancestor-reversed-what-remains': { expect: 'reject', reason: 'raw_html_in_status_report', text: `Status Report\n- Goal: adversarial status report probe\n- State: done\n- Changed: changed item\n- Verified: probe command -> PASS\n<bdo dir="rtl">\n- Proof: sniamer tahW\n</bdo>\n\n${jsonOnly(status({ proof: ['sniamer tahW'] }))}` },
  'css-bidi-ancestor-reversed-what-remains': { expect: 'reject', reason: 'raw_html_in_status_report', text: `Status Report\n- Goal: adversarial status report probe\n- State: done\n- Changed: changed item\n- Verified: probe command -> PASS\n<div style="direction:rtl;unicode-bidi:bidi-override">\n- Proof: sniamer tahW\n</div>\n\n${jsonOnly(status({ proof: ['sniamer tahW'] }))}` },
  'markdown-reference-values': { expect: 'reject', reason: 'markdown_link_in_status_report', text: `Status Report\n- Goal: adversarial status report probe\n- State: done\n[hidden-proof]: changed item probe command PASS /tmp/proof.json\n\n${jsonOnly()}` },
  'markdown-link-title-hidden-status-report': { expect: 'reject', reason: 'markdown_link_in_status_report', text: `[receipt](https://example.com\n"\nStatus Report\nGoal: adversarial status report probe\nState: done\nChanged: changed item\nVerified: probe command -> PASS\nProof: /tmp/proof.txt\n"\n)\n\n${jsonOnly(status({ proof: ['/tmp/proof.txt'] }))}` },
  'markdown-image-title-hidden-status-report': { expect: 'reject', reason: 'markdown_link_in_status_report', text: `![pixel](https://example.com/pixel.png\n"\nStatus Report\nGoal: adversarial status report probe\nState: done\nChanged: changed item\nVerified: probe command -> PASS\nProof: /tmp/proof.txt\n"\n)\n\n${jsonOnly(status({ proof: ['/tmp/proof.txt'] }))}` },
  'markdown-nested-link-title-hidden-status-report': { expect: 'reject', reason: 'markdown_link_in_status_report', text: `[receipt [nested]](https://example.com\n"\nStatus Report\nGoal: adversarial status report probe\nState: done\nChanged: changed item\nVerified: probe command -> PASS\nProof: /tmp/proof.txt\n"\n)\n\n${jsonOnly(status({ proof: ['/tmp/proof.txt'] }))}` },
  'indented-pseudofenced-json': { expect: 'reject', reason: 'missing_agent_status_json', text: `Status Report\n- Goal: adversarial status report probe\n- State: done\n- Changed: changed item\n- Verified: probe command -> PASS\n- Proof: /tmp/proof.json\n\n    \`\`\`json\n    ${status()}\n    \`\`\`` },
  'midline-pseudofenced-json': { expect: 'reject', reason: 'missing_agent_status_json', text: `Status Report\n- Goal: adversarial status report probe\n- State: done\n- Changed: changed item\n- Verified: probe command -> PASS\n- Proof: /tmp/proof.json\n\nnot a fence \`\`\`json\n${status()}\n\`\`\`` },
  'duplicate-changed-contradiction': { expect: 'reject', reason: 'status_report_changed_mismatch', text: `Status Report\n- Goal: adversarial status report probe\n- State: done\n- Changed: changed item\n- Changed: not changed item\n- Verified: probe command -> PASS\n- Proof: /tmp/proof.json\n\n${jsonOnly()}` },
  'duplicate-array-multiset-laundering': { expect: 'reject', reason: 'status_report_changed_mismatch', text: `Status Report\nGoal: adversarial status report probe\nState: done\nChanged: changed item\nChanged: not changed item\nVerified: probe command -> PASS\nProof: /tmp/proof.json\n\n${jsonOnly(status({ changed: ['changed item', 'changed item'] }))}` },
  'substring-negated-changed': { expect: 'reject', reason: 'status_report_changed_mismatch', text: `Status Report\n- Goal: adversarial status report probe\n- State: done\n- Changed: not changed item\n- Verified: probe command -> PASS\n- Proof: /tmp/proof.json\n\n${jsonOnly()}` },
  'multiple-json-final-valid-bound': { expect: 'pass', reason: null, text: `${jsonOnly(status({ goal: 'old status' }))}\n\n${report()}` },
  'multiple-json-prose-bound-to-earlier': { expect: 'reject', reason: 'status_report_goal_mismatch', text: `Status Report\n- Goal: old status\n- State: done\n\n${jsonOnly(status({ goal: 'old status' }))}\n\n${jsonOnly()}` },
  'bare-trailing-json': { expect: 'reject', reason: 'missing_agent_status_json', text: status() },
  'validator-nonzero-with-valid-true': { expect: 'reject', reason: 'validator_nonzero_with_valid_true', env: { LRSSS_VALIDATOR: `/tmp/lrsss-valid-true-exit-one-${process.pid}.py` }, setup: () => writeFileSync(`/tmp/lrsss-valid-true-exit-one-${process.pid}.py`, '#!/usr/bin/env python3\nprint("{\\"valid\\": true, \\"state\\": \\"done\\"}")\nraise SystemExit(1)\n'), text: report() },
  'trailing-html-comment-after-json': { expect: 'reject', reason: 'trailing_content_after_status_json', text: report({ trailing: '\n<!-- trailing payload -->' }) },
  'trailing-reference-after-json': { expect: 'reject', reason: 'trailing_content_after_status_json', text: report({ trailing: '\n[ref]: hidden trailing payload' }) },
  'trailing-template-after-json': { expect: 'reject', reason: 'trailing_content_after_status_json', text: report({ trailing: '\n<template>hidden trailing payload</template>' }) },
  'status-report-after-json': { expect: 'reject', reason: 'trailing_content_after_status_json', text: `${jsonOnly()}\n\nStatus Report\n- Goal: adversarial status report probe\n- State: done` },
  'only-old-status-report-before-final-json': { expect: 'reject', reason: 'status_report_goal_mismatch', text: `Status Report\n- Goal: old run\n- State: done\n\n${jsonOnly(status({ goal: 'old run' }))}\n\n\`\`\`json\n${status()}\n\`\`\`` },
};

const dataInvalidModes = new Set([
  'wrong-schema',
  'missing-schema',
  'json-array',
  'json-wrapper',
  'json5-comment',
  'trailing-comma',
  'single-quoted-json',
  'duplicate-goal-key',
  'duplicate-state-key',
  'duplicate-schema-key',
  'content-after-json',
  'second-fence-after-json',
  'unequal-length-fenced-heading',
  'pre-json-fence',
  'midline-pseudofenced-json',
  'done-missing-verified',
  'done-missing-proof',
  'continuing-missing-next-command',
  'needs-human-missing-payload',
  'failed-missing-triage',
  'extra-json-field',
  'bare-trailing-json',
  'validator-nonzero-with-valid-true',
  'trailing-html-comment-after-json',
  'trailing-reference-after-json',
  'trailing-template-after-json',
  'status-report-after-json',
]);

for (const [name, c] of Object.entries(cases)) {
  if (!dataInvalidModes.has(name)) {
    c.expect = 'pass';
    c.reason = null;
  } else if (name === 'pre-json-fence'
      || String(c.reason || '').startsWith('status_report_')
      || String(c.reason || '').startsWith('banned_')
      || String(c.reason || '').includes('html')
      || String(c.reason || '').includes('markdown')
      || String(c.reason || '').includes('bidi')) {
    c.reason = null;
  }
}

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
if (typeof c.setup === 'function') c.setup();
const run = spawnSync('node', [checker], {
  input: c.text,
  encoding: 'utf8',
  env: { ...process.env, ...(c.env || {}), LRSSS_FORCE_STATUS: '1', LRSSS_MUTATING_TURN: '1' },
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
