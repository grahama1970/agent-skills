#!/usr/bin/env node
import { existsSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const mode = process.argv[2] || 'all';
process.env.LAZY_REPORT_SHAME_AUDIO_ENABLED ||= '0';
process.env.LAZY_REPORT_SHAME_MEMORY_ENABLED ||= '0';
process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET ||= `/tmp/shame-probe-${mode}-pending-packet.json`;
process.env.LAZY_REPORT_SHAME_TRAINING_JSONL ||= `/tmp/shame-probe-${mode}-training.jsonl`;
const indexPath = process.env.LAZY_REPORT_SHAME_INDEX || '/home/graham/workspace/experiments/agent-skills/extensions/pi/lazy-report-shame-shame-shame/index.ts';

function assert(condition, message, details = {}) {
  if (!condition) {
    console.error(JSON.stringify({ ok: false, mode, message, details }, null, 2));
    process.exit(1);
  }
}

let extensionImportCounter = 0;

async function loadExtension() {
  const handlers = {};
  const commands = {};
  const sent = [];
  const moduleUrl = pathToFileURL(indexPath);
  moduleUrl.searchParams.set('probe_import', String(extensionImportCounter++));
  const mod = await import(moduleUrl.href);
  const pi = {
    on(name, fn) { (handlers[name] ||= []).push(fn); },
    registerCommand(name, spec) { commands[name] = spec; },
    sendUserMessage(text, options) { sent.push({ text, options }); },
  };
  (mod.default || mod)(pi);
  return { handlers, commands, sent };
}

function ctx(branch = []) {
  const notifications = [];
  return {
    hasUI: false,
    notifications,
    ui: { notify(message, level) { notifications.push({ message: String(message), level: String(level || '') }); } },
    cwd: '/home/graham/workspace/experiments/agent-skills',
    sessionManager: {
      getBranch() { return branch; },
      getSessionFile() { return '/tmp/shame-probe-session.jsonl'; },
      getSessionId() { return 'shame-probe-session'; },
    },
  };
}

async function markShameSkillRead(handlers, c) {
  await handlers.tool_result[0]({
    toolName: 'read',
    input: { path: '/home/graham/workspace/experiments/agent-skills/skills/shame/SKILL.md' },
    isError: false,
    content: readFileSync(
      '/home/graham/workspace/experiments/agent-skills/skills/shame/SKILL.md',
      'utf8',
    ),
  }, c);
}

async function runEmptyToolTurn() {
  const packet = process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET || '/tmp/shame-probe-empty-packet.json';
  if (existsSync(packet)) rmSync(packet);
  const { handlers, sent } = await loadExtension();
  const c = ctx();
  await handlers.input[0]({ text: '$shame check this', source: 'user' });
  const result = await handlers.message_end[0]({ id: 'tool-only', message: { id: 'tool-only', role: 'assistant', content: [] } }, c);
  assert(result === undefined, 'empty assistant/tool-call turn was rewritten', { result });
  assert(sent.length === 0, 'empty assistant/tool-call turn queued retry', { sent });
  assert(!existsSync(packet), 'empty assistant/tool-call turn wrote pending packet', { packet });
  console.log(JSON.stringify({ ok: true, mode: 'empty-tool-turn', emptyAssistantIgnored: true, retryMessages: sent.length, packetExists: existsSync(packet) }));
}

async function runRejectionPendingRetry() {
  const packet = process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET || '/tmp/shame-probe-pending-packet.json';
  if (existsSync(packet)) rmSync(packet);
  const { handlers, sent } = await loadExtension();
  const c = ctx();
  await handlers.input[0]({ text: '$shame fix this bad status', source: 'user' });
  const result = await handlers.message_end[0]({ id: 'assistant-bad', message: { id: 'assistant-bad', role: 'assistant', content: [{ type: 'text', text: 'Committed and pushed. Done.' }] } }, c);
  const notice = result?.message?.content?.map?.((part) => part?.text || '').join('\n') || String(result?.message?.content || '');
  assert(notice.includes('REJECTED_BY_SLOTH_COURT'), 'bad status was not replaced with shame notice', { notice });
  assert(notice.includes('Status Report'), 'replacement notice does not include Status Report footer', { notice });
  assert(notice.includes('/shame review'), 'replacement notice does not mention /shame review', { notice });
  assert(sent.length === 1, 'bad status did not queue exactly one retry', { sentCount: sent.length });
  assert(sent[0].text.includes('UNLAZY_FORCED_RETRY'), 'retry prompt did not contain UNLAZY_FORCED_RETRY', { sent });
  assert(existsSync(packet), 'pending review packet was not written', { packet });
  const saved = JSON.parse(readFileSync(packet, 'utf8'));
  assert(saved.schema === 'lazy_report_shame.review_packet.v1', 'pending packet schema mismatch', saved);
  assert(saved.candidate?.assistant_text === 'Committed and pushed. Done.', 'pending packet did not preserve rejected candidate', saved);
  console.log(JSON.stringify({ ok: true, mode: 'rejection-pending-retry', retryMessages: sent.length, packet, schema: saved.schema, candidateHash: saved.candidate_hash }));
}

async function runShowRecoversPending() {
  const packet = process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET || '/tmp/shame-probe-pending-packet.json';
  process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET = packet;
  if (existsSync(packet)) rmSync(packet);
  await runRejectionPendingRetry();
  const { commands } = await loadExtension();
  const c = ctx();
  await commands.shame.handler('show', c);
  const text = c.notifications.map((n) => n.message).join('\n');
  assert(text.includes('Shame review packet'), '/shame show did not load pending packet', { notifications: c.notifications });
  assert(text.includes('Committed and pushed. Done.'), '/shame show did not expose rejected excerpt', { notifications: c.notifications });
  assert(text.includes('/shame review'), '/shame show did not include review command guidance', { notifications: c.notifications });
  console.log(JSON.stringify({ ok: true, mode: 'show-recovers-pending', notifications: c.notifications.length, packet }));
}

async function runReviewFallback() {
  const packet = process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET || '/tmp/shame-probe-review-packet.json';
  process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET = packet;
  if (existsSync(packet)) rmSync(packet);
  await runRejectionPendingRetry();
  const { commands } = await loadExtension();
  const c = ctx();
  await commands.shame.handler('review', c);
  const text = c.notifications.map((n) => n.message).join('\n');
  assert(text.includes('Interactive /shame review is unavailable here'), '/shame review did not fall back in headless context', { notifications: c.notifications });
  assert(text.includes('/shame reject|allow|warn'), '/shame review fallback omitted direct label command syntax', { notifications: c.notifications });
  console.log(JSON.stringify({ ok: true, mode: 'review-fallback', notifications: c.notifications.length }));
}

async function runContinuationGuardOpenTicket() {
  const guardFile = `/tmp/shame-probe-continuation-${process.pid}.json`;
  const packet = process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET || '/tmp/shame-probe-continuation-packet.json';
  if (existsSync(packet)) rmSync(packet);
  process.env.LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE = guardFile;
  writeFileSync(guardFile, JSON.stringify({
    schema: 'lazy_report_shame.continuation_guard.v1',
    active: true,
    target: 'extensions/pi/continuation-guard',
    tickets: [{ ref: 'grahama1970/agent-skills#1554', state: 'OPEN', labels: ['agent-work', 'type:feature'], next_command: 'Run the continuation guard implementation task.' }],
    gates: [{ id: 'live-replay', status: 'pending', next_command: 'Run live-replay and read back followup_injected=true.' }],
    obvious_next_steps: ['Extend lazy-report-shame-shame-shame instead of stopping.'],
  }), 'utf8');
  const { handlers, sent } = await loadExtension();
  const c = ctx();
  await handlers.input[0]({ text: 'please finish the ticketed goal', source: 'user' });
  // JSON-first: a premature final is a valid done-status JSON claiming completion
  // while the continuation guard state file still has open tickets.
  const doneStatus = JSON.stringify({
    schema: 'pi.agent_status.v1',
    goal: 'continuation guard probe',
    state: 'done',
    verified: [{ command: 'probe', result: 'probe' }],
    proof: ['/tmp/probe'],
  });
  const goodLookingFinal = (
    'The continuation guard is handled.\n\n'
    + 'Status Report\n- Goal: continuation guard probe\n- State: done\n\n'
    + '```json\n' + doneStatus + '\n```'
  );
  const result = await handlers.message_end[0]({ id: 'assistant-premature', message: { id: 'assistant-premature', role: 'assistant', content: [{ type: 'text', text: goodLookingFinal }] } }, c);
  const notice = result?.message?.content?.map?.((part) => part?.text || '').join('\n') || String(result?.message?.content || '');
  assert(notice.includes('continuation_guard_unresolved_work'), 'continuation guard did not reject premature final', { notice });
  assert(notice.includes('open_relevant_agent_work_ticket'), 'continuation guard did not name open ticket failure', { notice });
  assert(sent.length === 1, 'continuation guard did not queue one follow-up', { sentCount: sent.length, sent });
  assert(sent[0].text.includes('Run the continuation guard implementation task'), 'follow-up did not include next ticket action', { sent });
  const saved = JSON.parse(readFileSync(packet, 'utf8'));
  assert(saved.machine?.reason_codes?.includes('continuation_guard_unresolved_work'), 'pending packet omitted continuation reason', saved);
  rmSync(guardFile, { force: true });
  console.log(JSON.stringify({ ok: true, mode: 'continuation-open-ticket', followup_injected: true, ticket_gate: 'blocked_open_agent_work', retryMessages: sent.length }));
}

async function runContinuationGuardClosedTicketAllowsFinal() {
  const guardFile = `/tmp/shame-probe-continuation-closed-${process.pid}.json`;
  process.env.LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE = guardFile;
  writeFileSync(guardFile, JSON.stringify({
    schema: 'lazy_report_shame.continuation_guard.v1',
    active: true,
    target: 'extensions/pi/continuation-guard',
    tickets: [{ ref: 'grahama1970/agent-skills#1554', state: 'CLOSED', labels: ['agent-work', 'type:feature'] }],
    gates: [{ id: 'live-replay', status: 'PASS', proof: '/tmp/proof.json' }],
    obvious_next_steps: [],
  }), 'utf8');
  const { handlers, sent } = await loadExtension();
  const c = ctx();
  await handlers.input[0]({ text: 'report final', source: 'user' });
  const okStatus = JSON.stringify({
    schema: 'pi.agent_status.v1',
    goal: 'continuation guard probe',
    state: 'done',
    verified: [{ command: 'live-replay', result: 'PASS' }],
    proof: ['/tmp/proof.json'],
  });
  const finalText = (
    'Done.\n\n'
    + 'Status Report\n- Goal: continuation guard probe\n- State: done\n\n'
    + '```json\n' + okStatus + '\n```'
  );
  const result = await handlers.message_end[0]({ id: 'assistant-ok', message: { id: 'assistant-ok', role: 'assistant', content: [{ type: 'text', text: finalText }] } }, c);
  assert(result === undefined, 'closed ticket / passed gates should allow final answer', { result });
  assert(sent.length === 0, 'allowed final should not queue follow-up', { sent });
  rmSync(guardFile, { force: true });
  console.log(JSON.stringify({ ok: true, mode: 'continuation-closed-ticket-allows-final', followup_injected: false, ticket_gate: 'closed_or_passed' }));
}

async function runWhatRemainsRejectedWithoutNeedsHuman() {
  const packet = process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET || '/tmp/shame-probe-what-remains-packet.json';
  if (existsSync(packet)) rmSync(packet);
  const { handlers, sent } = await loadExtension();
  const c = ctx();
  await handlers.input[0]({ text: 'report status for this active goal', source: 'user' }, c);
  const continuingStatus = JSON.stringify({
    schema: 'pi.agent_status.v1',
    goal: 'what remains ban probe',
    state: 'continuing',
    not_done: [{ item: 'continue work', next_command: 'run the next deterministic command' }],
  });
  const badText = (
    'Result text.\n\n'
    + 'Status Report\n- Goal: what remains ban probe\n- State: continuing\n\n'
    + 'What remains:\n- keep working\n\n'
    + '```json\n' + continuingStatus + '\n```'
  );
  const result = await handlers.message_end[0]({ id: 'assistant-what-remains', message: { id: 'assistant-what-remains', role: 'assistant', content: [{ type: 'text', text: badText }] } }, c);
  const notice = result?.message?.content?.map?.((part) => part?.text || '').join('\n') || String(result?.message?.content || '');
  assert(notice.includes('banned_what_remains_without_needs_human'), 'What remains was not rejected when state was not needs_human', { notice });
  assert(sent.length === 1, 'What remains rejection did not queue one retry', { sentCount: sent.length, sent });
  assert(existsSync(packet), 'What remains rejection did not write pending packet', { packet });
  const saved = JSON.parse(readFileSync(packet, 'utf8'));
  assert(saved.machine?.reason_codes?.includes('banned_what_remains_without_needs_human'), 'pending packet omitted banned What remains reason', saved);
  console.log(JSON.stringify({ ok: true, mode: 'what-remains-rejected-without-needs-human', retryMessages: sent.length, reason: 'banned_what_remains_without_needs_human' }));
}

async function runWhatRemainsAllowedWithNeedsHuman() {
  const { handlers, sent } = await loadExtension();
  const c = ctx();
  await handlers.input[0]({ text: 'report human-blocked status', source: 'user' }, c);
  const needsHumanStatus = JSON.stringify({
    schema: 'pi.agent_status.v1',
    goal: 'what remains ban probe',
    state: 'needs_human',
    needs_human: {
      action: 'choose the next target',
      reason: 'the next action requires a human decision',
    },
  });
  const okText = (
    'Result text.\n\n'
    + 'Status Report\n- Goal: what remains ban probe\n- State: needs_human\n\n'
    + 'What remains:\n- human decision required\n\n'
    + '```json\n' + needsHumanStatus + '\n```'
  );
  const result = await handlers.message_end[0]({ id: 'assistant-needs-human', message: { id: 'assistant-needs-human', role: 'assistant', content: [{ type: 'text', text: okText }] } }, c);
  assert(result === undefined, 'What remains should be allowed only with state=needs_human', { result });
  assert(sent.length === 0, 'allowed needs_human status should not queue retry', { sent });
  console.log(JSON.stringify({ ok: true, mode: 'what-remains-allowed-with-needs-human', retryMessages: sent.length }));
}

async function runStatusReportRequiredWithJson() {
  const packet = process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET || '/tmp/shame-probe-status-report-required-packet.json';
  if (existsSync(packet)) rmSync(packet);
  const { handlers, sent } = await loadExtension();
  const c = ctx();
  await handlers.input[0]({ text: '$shame report this', source: 'user' }, c);
  await markShameSkillRead(handlers, c);
  const doneStatus = JSON.stringify({
    schema: 'pi.agent_status.v1',
    goal: 'status report required probe',
    state: 'done',
    verified: [{ command: 'probe', result: 'PASS' }],
    proof: ['/tmp/proof.json'],
  });
  const result = await handlers.message_end[0]({ id: 'assistant-json-only', message: { id: 'assistant-json-only', role: 'assistant', content: [{ type: 'text', text: 'Done.\n\n```json\n' + doneStatus + '\n```' }] } }, c);
  const notice = result?.message?.content?.map?.((part) => part?.text || '').join('\n') || String(result?.message?.content || '');
  assert(notice.includes('missing_status_report_section'), 'JSON-only status was not rejected for missing Status Report section', { notice });
  assert(sent.length === 1, 'missing Status Report rejection did not queue one retry', { sentCount: sent.length, sent });
  assert(existsSync(packet), 'missing Status Report rejection did not write pending packet', { packet });
  const saved = JSON.parse(readFileSync(packet, 'utf8'));
  assert(saved.machine?.reason_codes?.includes('missing_status_report_section'), 'pending packet omitted missing Status Report reason', saved);
  console.log(JSON.stringify({ ok: true, mode: 'status-report-required-with-json', retryMessages: sent.length, reason: 'missing_status_report_section' }));
}

async function runStatusReportMismatchRejected() {
  const packet = process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET || '/tmp/shame-probe-status-report-mismatch-packet.json';
  if (existsSync(packet)) rmSync(packet);
  const { handlers, sent } = await loadExtension();
  const c = ctx();
  await handlers.input[0]({ text: '$shame report this', source: 'user' }, c);
  await markShameSkillRead(handlers, c);
  const doneStatus = JSON.stringify({
    schema: 'pi.agent_status.v1',
    goal: 'status report mismatch probe',
    state: 'done',
    verified: [{ command: 'probe', result: 'PASS' }],
    proof: ['/tmp/proof.json'],
  });
  const text = (
    'Status Report\n- Goal: status report mismatch probe\n- State: continuing\n\n'
    + '```json\n' + doneStatus + '\n```'
  );
  const result = await handlers.message_end[0]({ id: 'assistant-mismatch', message: { id: 'assistant-mismatch', role: 'assistant', content: [{ type: 'text', text }] } }, c);
  const notice = result?.message?.content?.map?.((part) => part?.text || '').join('\n') || String(result?.message?.content || '');
  assert(notice.includes('status_report_state_mismatch'), 'mismatched Status Report was not rejected', { notice });
  assert(sent.length === 1, 'mismatched Status Report rejection did not queue one retry', { sentCount: sent.length, sent });
  console.log(JSON.stringify({ ok: true, mode: 'status-report-mismatch-rejected', retryMessages: sent.length, reason: 'status_report_state_mismatch' }));
}

async function runStatusReportMatchesJsonAllowed() {
  const { handlers, sent } = await loadExtension();
  const c = ctx();
  await handlers.input[0]({ text: '$shame report this', source: 'user' }, c);
  await markShameSkillRead(handlers, c);
  const doneStatus = JSON.stringify({
    schema: 'pi.agent_status.v1',
    goal: 'status report derived from json probe',
    state: 'done',
    verified: [{ command: 'probe', result: 'PASS' }],
    proof: ['/tmp/proof.json'],
  });
  const text = (
    'Status Report\n- Goal: status report derived from json probe\n- State: done\n\n'
    + '```json\n' + doneStatus + '\n```'
  );
  const result = await handlers.message_end[0]({ id: 'assistant-status-report-ok', message: { id: 'assistant-status-report-ok', role: 'assistant', content: [{ type: 'text', text }] } }, c);
  assert(result === undefined, 'matching Status Report and JSON should pass', { result });
  assert(sent.length === 0, 'matching Status Report should not queue retry', { sent });
  console.log(JSON.stringify({ ok: true, mode: 'status-report-matches-json-allowed', retryMessages: sent.length }));
}

async function runSkillReadGuardBlocksActionBeforeRead() {
  const { handlers } = await loadExtension();
  const c = ctx();
  await handlers.input[0]({ text: '$shame update the guard', source: 'user' }, c);
  const result = await handlers.tool_call[0]({ toolName: 'bash', input: { command: 'echo should-not-run' } }, c);
  assert(result?.block === true, 'skill-read guard did not block bash before SKILL.md read', { result });
  const reason = JSON.parse(result.reason);
  assert(reason.code === 'skill_contract_unread', 'block reason code mismatch', reason);
  assert(reason.skill === 'shame', 'block skill mismatch', reason);
  assert(reason.next_steps?.[0]?.next_command?.includes('SKILL.md'), 'block reason omitted next read step', reason);
  assert(typeof reason.next_steps?.[0]?.sha256 === 'string' && reason.next_steps[0].sha256.startsWith('sha256:'), 'block reason omitted skill hash', reason);
  console.log(JSON.stringify({ ok: true, mode: 'skill-read-guard-blocks-action-before-read', code: reason.code, skill: reason.skill, hasHash: true }));
}

async function runSkillReadGuardBlocksSlashSkillBeforeRead() {
  const { handlers } = await loadExtension();
  const c = ctx();
  await handlers.input[0]({ text: '/shame update the guard', source: 'user' }, c);
  const result = await handlers.tool_call[0]({ toolName: 'bash', input: { command: 'echo should-not-run' } }, c);
  assert(result?.block === true, 'skill-read guard did not block slash skill before SKILL.md read', { result });
  const reason = JSON.parse(result.reason);
  assert(reason.code === 'skill_contract_unread', 'slash block reason code mismatch', reason);
  assert(reason.skill === 'shame', 'slash block skill mismatch', reason);
  assert(reason.next_steps?.[0]?.sha256?.startsWith('sha256:'), 'slash block omitted skill hash', reason);
  console.log(JSON.stringify({ ok: true, mode: 'skill-read-guard-blocks-slash-skill-before-read', code: reason.code, skill: reason.skill, hasHash: true }));
}

async function runSkillReadGuardAllowsActionAfterFullRead() {
  const { handlers } = await loadExtension();
  const c = ctx();
  await handlers.input[0]({ text: '$shame update the guard', source: 'user' }, c);
  await handlers.tool_result[0]({ toolName: 'read', input: { path: '/home/graham/workspace/experiments/agent-skills/skills/shame/SKILL.md' }, isError: false, content: readFileSync('/home/graham/workspace/experiments/agent-skills/skills/shame/SKILL.md', 'utf8') }, c);
  const result = await handlers.tool_call[0]({ toolName: 'bash', input: { command: 'echo allowed-after-read' } }, c);
  assert(result === undefined, 'skill-read guard blocked after full SKILL.md read', { result });
  console.log(JSON.stringify({ ok: true, mode: 'skill-read-guard-allows-action-after-full-read', allowed: true }));
}

async function runDirectLabelJsonl() {
  const out = process.env.LAZY_REPORT_SHAME_TRAINING_JSONL || '/tmp/shame-probe-training.jsonl';
  const packet = process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET || '/tmp/shame-probe-label-packet.json';
  if (existsSync(out)) rmSync(out);
  if (existsSync(packet)) rmSync(packet);
  const { handlers, commands } = await loadExtension();
  const c = ctx();
  await handlers.input[0]({ text: '$shame capture this', source: 'user' });
  await handlers.message_end[0]({ id: 'assistant-bad', message: { id: 'assistant-bad', role: 'assistant', content: [{ type: 'text', text: 'Committed and pushed. Done.' }] } }, c);
  await commands.shame.handler('reject commit_laundering -- no useful status', c);
  assert(existsSync(out), '/shame direct label did not write JSONL', { out, notifications: c.notifications });
  const rows = readFileSync(out, 'utf8').trim().split(/\n/).filter(Boolean).map((line) => JSON.parse(line));
  assert(rows.length === 1, 'expected one JSONL row', { rows });
  const row = rows[0];
  assert(row.schema === 'lazy_report_shame.training_example.v2', 'wrong training schema', row);
  assert(row.human_verdict === 'reject', 'wrong verdict', row);
  assert(row.human_reasons.includes('commit_laundering'), 'wrong reasons', row);
  assert(row.assistant_text === 'Committed and pushed. Done.', 'did not label raw rejected candidate', row);
  console.log(JSON.stringify({ ok: true, mode: 'direct-label-jsonl', rows: rows.length, example_id: row.example_id }));
}

const modes = {
  'empty-tool-turn': runEmptyToolTurn,
  'rejection-pending-retry': runRejectionPendingRetry,
  'show-recovers-pending': runShowRecoversPending,
  'review-fallback': runReviewFallback,
  'direct-label-jsonl': runDirectLabelJsonl,
  'skill-read-guard-blocks-action-before-read': runSkillReadGuardBlocksActionBeforeRead,
  'skill-read-guard-blocks-slash-skill-before-read': runSkillReadGuardBlocksSlashSkillBeforeRead,
  'skill-read-guard-allows-action-after-full-read': runSkillReadGuardAllowsActionAfterFullRead,
  'continuation-open-ticket': runContinuationGuardOpenTicket,
  'continuation-closed-ticket-allows-final': runContinuationGuardClosedTicketAllowsFinal,
  'what-remains-rejected-without-needs-human': runWhatRemainsRejectedWithoutNeedsHuman,
  'what-remains-allowed-with-needs-human': runWhatRemainsAllowedWithNeedsHuman,
  'status-report-required-with-json': runStatusReportRequiredWithJson,
  'status-report-mismatch-rejected': runStatusReportMismatchRejected,
  'status-report-matches-json-allowed': runStatusReportMatchesJsonAllowed,
};

if (mode === 'all') {
  for (const name of Object.keys(modes)) await modes[name]();
} else {
  assert(modes[mode], `unknown mode ${mode}`, { modes: Object.keys(modes) });
  await modes[mode]();
}
