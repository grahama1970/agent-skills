// One local observational journal; not a classifier, gate, or training dataset.
import { appendFileSync, closeSync, existsSync, fstatSync, mkdirSync, openSync, readSync } from 'node:fs';
import { createHash, randomUUID } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const failureLogPath = () => process.env.LAZY_REPORT_SHAME_FAILURE_LOG || '/mnt/storage12tb/skills/shame/failures/events.jsonl';
const digest = value => 'sha256:' + createHash('sha256').update(JSON.stringify(value)).digest('hex');

export function recordFailure(ctx, details) {
  const event = {
    ...details,
    schema: 'lazy_report_shame.failure_event.v1', event_id: randomUUID(), at: new Date().toISOString(),
    session_id: ctx?.sessionManager?.getSessionId?.() || process.env.PI_SESSION_ID || null,
    session_file: ctx?.sessionManager?.getSessionFile?.() || process.env.PI_SESSION_FILE || null,
  };
  event.fingerprint = digest([event.kind, event.goal, event.reason_codes, event.tool_name, event.check_id]);
  const path = failureLogPath();
  try {
    mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
    appendFileSync(path, JSON.stringify(event) + '\n', { encoding: 'utf8', mode: 0o600 });
    return event;
  } catch (error) {
    // Observability failure must be visible, without starting another agent loop.
    const warning = `failure_history_write_failed: ${path}: ${String(error)}`;
    if (ctx?.ui?.notify) ctx.ui.notify(warning, 'warning');
    else console.error(warning);
    return null;
  }
}

export function readFailureHistory({ sessionId = process.env.PI_SESSION_ID || null, all = false, limit = 20 } = {}) {
  if (!Number.isInteger(limit) || limit < 1 || limit > 200) throw new Error('failure_history_limit_must_be_1_to_200');
  const path = failureLogPath();
  const result = { schema: 'lazy_report_shame.failure_history.v1', path, session_id: all ? null : sessionId, scope: all || !sessionId ? 'all' : 'session', events: [], tail_limited: false, output_limited: false, malformed_lines: 0 };
  if (!existsSync(path)) return result;
  const fd = openSync(path, 'r');
  try {
    const size = fstatSync(fd).size;
    const length = Math.min(size, 4 * 1024 * 1024), start = size - length;
    const buffer = Buffer.alloc(length);
    const count = readSync(fd, buffer, 0, length, start);
    let text = buffer.subarray(0, count).toString('utf8');
    result.tail_limited = start > 0;
    if (start > 0) text = text.slice(text.indexOf('\n') + 1);
    for (const line of text.split('\n')) {
      if (!line.trim()) continue;
      let event;
      try { event = JSON.parse(line); } catch { result.malformed_lines++; continue; }
      if (event?.schema !== 'lazy_report_shame.failure_event.v1' || typeof event.kind !== 'string' || typeof event.event_id !== 'string') { result.malformed_lines++; continue; }
      if (result.scope === 'all' || event.session_id === sessionId) result.events.push(event);
    }
    result.events = result.events.slice(-limit);
    while (result.events.length && Buffer.byteLength(JSON.stringify(result)) > 32768) {
      result.events.shift(); result.output_limited = true;
    }
    return result;
  } finally { closeSync(fd); }
}

export function historyOptions(args) {
  const options = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--all') options.all = true;
    else if (args[i] === '--limit' && args[i + 1]) options.limit = Number(args[++i]);
    else if (args[i] === '--session-id' && args[i + 1]) options.sessionId = args[++i];
    else if (args[i] !== '--json') throw new Error('usage: failures [--all | --session-id ID] [--limit 1..200] [--json]');
  }
  if (options.all && options.sessionId) throw new Error('--all and --session-id are mutually exclusive');
  return options;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { console.log(JSON.stringify(readFailureHistory(historyOptions(process.argv.slice(2))), null, 2)); }
  catch (error) { console.error(String(error)); process.exitCode = 2; }
}
