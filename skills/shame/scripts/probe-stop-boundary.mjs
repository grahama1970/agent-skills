#!/usr/bin/env node
// Replays Pi lifecycle events against the real extension and pydantic checker.
// The event driver is synthetic; the separate CLI eval covers a live model run.
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, existsSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const dir = mkdtempSync(join(tmpdir(), 'shame-stop-'));
process.env.LAZY_REPORT_SHAME_AUDIO_ENABLED = '0';
process.env.LAZY_REPORT_SHAME_MEMORY_ENABLED = '0';
process.env.LAZY_REPORT_SHAME_DEFAULT_MODE = 'strict';
process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET = join(dir, 'pending.json');
process.env.LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE = join(dir, 'ledger.json');
const root = '/home/graham/workspace/experiments/agent-skills';
const index = process.env.LAZY_REPORT_SHAME_INDEX || `${root}/extensions/pi/lazy-report-shame-shame-shame/index.ts`;
const handlers = {};
const sent = [];
const ctx = {
  isIdle: () => true,
  hasPendingMessages: () => false,
  ui: { notify() {}, setStatus() {} },
  sessionManager: { getSessionId: () => dir, getSessionFile: () => join(dir, 'session.jsonl') },
};
const pi = {
  on(name, fn) { (handlers[name] ||= []).push(fn); },
  registerCommand() {},
  sendUserMessage(text, options) { sent.push({ text, options }); },
};
(await import(pathToFileURL(index).href)).default(pi);
async function emit(name, event = {}) {
  let result;
  for (const fn of handlers[name] || []) result = await fn(event, ctx);
  return result;
}
function message(text, stopReason = 'stop', extra = []) {
  return { role: 'assistant', stopReason, content: [{ type: 'text', text }, ...extra] };
}
function status(i) {
  return '```json\n' + JSON.stringify({ schema: 'pi.agent_status.v1', goal: 'stop-boundary regression', state: 'continuing', changed: [`step ${i} completed`], not_done: [{ item: `step ${i + 1}`, next_command: `printf step-${i + 1}` }] }) + '\n```';
}
await emit('input', { text: '$shame finish the multi-step job', source: 'interactive' });
await emit('tool_result', { toolName: 'read', input: { path: `${root}/skills/shame/SKILL.md` }, isError: false, content: readFileSync(`${root}/skills/shame/SKILL.md`, 'utf8') });
await emit('tool_call', { toolName: 'write', input: { path: join(dir, 'work.txt') } });
for (let i = 0; i < 8; i++) {
  const m = message(`Working on step ${i}`, 'toolUse', [{ type: 'toolCall', id: `call-${i}`, name: 'read', arguments: { path: `${root}/skills/shame/SKILL.md` } }]);
  assert.equal(await emit('message_end', { message: m }), undefined, 'tool-bearing assistant message must not be rewritten');
}
assert.equal(sent.length, 0, 'working agent consumed report retries');
assert.equal(existsSync(process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET + '.sessions'), false);
for (const stopReason of ['aborted', 'error', 'length']) {
  assert.equal(await emit('message_end', { message: message('Interrupted', stopReason) }), undefined);
  await emit('agent_end');
  assert.equal(sent.length, 0, 'interruption restarted agent');
}
const bad = await emit('message_end', { message: message('') }); // Empty terminal stop still needs a report.
assert.match(JSON.stringify(bad), /missing_agent_status_json/);
assert.equal(sent.length, 0, 'repair dispatched before agent settled');
await emit('agent_end');
assert.equal(sent.length, 1, 'one repair at stop boundary');
await emit('agent_end');
assert.equal(sent.length, 1, 'duplicate settled event queued duplicate repair');
// More than three legitimate continuations must not exhaust formatting retries.
for (let i = 0; i < 6; i++) {
  await emit('input', { text: sent.at(-1).text, source: 'extension' });
  await emit('message_end', { message: message(status(i)) });
  assert.equal(sent.length, i + 1, 'continuation dispatched before settled');
  await emit('agent_end');
  assert.equal(sent.length, i + 2, 'valid continuation exhausted repair budget');
  assert.match(sent.at(-1).text, /CONTINUE_FROM_AGENT_STATUS/);
}
// Cancellation after a terminal candidate must discard its scheduled repair.
await emit('message_end', { message: message('bad final after progress') });
await emit('message_end', { message: message('cancelled', 'aborted') });
await emit('agent_end');
assert.equal(sent.length, 7, 'cancellation must discard pending repair');
const proof = join(dir, 'proof.txt');
writeFileSync(proof, 'stop-boundary probe: six continuations completed');
const done = { schema: 'pi.agent_status.v1', goal: 'stop-boundary regression', state: 'done', changed: ['six steps completed'], verified: [{ command: 'stop-boundary probe', result: 'six continuations completed' }], proof: [proof] };
const accepted = await emit('message_end', { message: message('```json\n' + JSON.stringify(done) + '\n```') });
assert.match(JSON.stringify(accepted), /State: done/);
await emit('agent_end');
assert.equal(sent.length, 7, 'accepted completion restarted work');
// Host-queued work wins; a reporting repair must not race a user's follow-up.
ctx.hasPendingMessages = () => true;
assert.equal(await emit('message_end', { message: message('queued work remains') }), undefined);
await emit('agent_end');
assert.equal(sent.length, 7);
ctx.hasPendingMessages = () => false;
// Even contradictory stop metadata cannot authorize erasing actual tool calls.
assert.equal(await emit('message_end', { message: message('working', 'stop', [{ type: 'toolCall', name: 'read' }]) }), undefined);
const report = { toolMessagesPreserved: 8, intermediateRetries: 0, continuations: 6, cancellationRespected: true, doneAccepted: true };
writeFileSync(join(dir, 'report.json'), JSON.stringify(report, null, 2));
console.log(JSON.stringify({ ...report, report: join(dir, 'report.json') }));
