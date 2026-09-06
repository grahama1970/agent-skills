// Operator-armed task policy. Approved commands are trusted capabilities, not
// an OS sandbox. No prose classification and no model-controlled budget resets.
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, statSync, writeFileSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { recordFailure } from './failure-history.mjs';

type Check = { id: string; argv: string[]; inputs: string[]; definition_files?: string[]; timeout_ms: number; kind?: 'check' | 'review' | 'delivery' };
type Contract = { schema: 'pi.task_budget.v1'; mode: 'task' | 'question'; deliverable: string; allowed_paths: string[]; elapsed_ms: number; checks: Check[] };
type Run = { command: string; argv: string[]; result: string; stdout: string; stderr: string; exit_code: number; input_hash: string; passed: boolean; attempts: number; failures: number };
const hash = (s: string | Buffer) => createHash('sha256').update(s).digest('hex');
const readers = new Set(['read', 'grep', 'find', 'ls', 'shame_failures']);
const baseTool = (s: string) => String(s).split('.').at(-1)?.split('/').at(-1) || '';

function canonical(path: string): string {
  const full = resolve(path);
  let parent = full;
  while (!existsSync(parent)) parent = dirname(parent);
  return resolve(realpathSync(parent), relative(parent, full));
}
function below(root: string, path: string): boolean {
  const rel = relative(root, path);
  return rel === '' || (!rel.startsWith('..' + '/') && rel !== '..' && !isAbsolute(rel));
}
function parse(raw: string): Contract {
  if (raw.length > 65536) throw new Error('task_contract_too_large');
  const c = JSON.parse(raw);
  const fields = ['schema', 'mode', 'deliverable', 'allowed_paths', 'elapsed_ms', 'checks'];
  if (process.platform === 'win32') throw new Error('task_budget_requires_posix_process_groups');
  if (!c || Object.keys(c).some(k => !fields.includes(k)) || c.schema !== 'pi.task_budget.v1'
      || !['task', 'question'].includes(c.mode) || typeof c.deliverable !== 'string' || !c.deliverable.trim()
      || !Number.isInteger(c.elapsed_ms) || c.elapsed_ms < 1 || c.elapsed_ms > 86400000
      || !Array.isArray(c.allowed_paths) || c.allowed_paths.length > 256 || !c.allowed_paths.every((p: unknown) => typeof p === 'string' && p.length > 0)
      || !Array.isArray(c.checks) || c.checks.length > 32 || (c.mode === 'task' && !c.checks.length)
      || (c.mode === 'question' && (c.checks.length || c.allowed_paths.length))) throw new Error('invalid_task_contract');
  const ids = new Set();
  for (const x of c.checks) {
    if (!x || Object.keys(x).some(k => !['id', 'argv', 'inputs', 'definition_files', 'timeout_ms', 'kind'].includes(k))
        || typeof x.id !== 'string' || !x.id.trim() || ids.has(x.id)
        || !Array.isArray(x.argv) || !x.argv.length || !x.argv.every((a: unknown) => typeof a === 'string') || !x.argv[0]
        || !Array.isArray(x.inputs) || x.inputs.length > 256 || !x.inputs.every((p: unknown) => typeof p === 'string' && p.length > 0)
        || (x.definition_files !== undefined && (!Array.isArray(x.definition_files) || !x.definition_files.every((p: unknown) => typeof p === 'string' && p.length > 0)))
        || !Number.isInteger(x.timeout_ms) || x.timeout_ms < 1 || x.timeout_ms > c.elapsed_ms
        || (x.kind !== undefined && !['check', 'review', 'delivery'].includes(x.kind))) throw new Error('invalid_task_check');
    ids.add(x.id);
  }
  return c;
}

// Unlike pi.exec's parent-only SIGTERM, kill the approved command's process
// group at the hard deadline/cancellation. Output is bounded to 64 KiB/stream.
export function runApprovedCommand(command: string, args: string[], options: any): Promise<any> {
  return new Promise(resolveResult => {
    const proc = spawn(command, args, { cwd: options.cwd, detached: true, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '', stderr = '', timedOut = false, aborted = false;
    const kill = () => { if (proc.pid) { try { process.kill(-proc.pid, 'SIGKILL'); } catch (e: any) { if (e.code !== 'ESRCH') stderr += String(e); } } };
    const abort = () => { aborted = true; kill(); };
    const timer = setTimeout(() => { timedOut = true; kill(); }, options.timeout);
    if (options.signal?.aborted) abort();
    else options.signal?.addEventListener('abort', abort, { once: true });
    proc.stdout.on('data', chunk => { stdout = (stdout + chunk.toString()).slice(0, 65536); });
    proc.stderr.on('data', chunk => { stderr = (stderr + chunk.toString()).slice(0, 65536); });
    proc.once('error', error => { stderr += String(error); });
    proc.once('close', code => {
      clearTimeout(timer); options.signal?.removeEventListener('abort', abort); kill();
      resolveResult({ code: code ?? -1, stdout, stderr, killed: timedOut || aborted, timedOut, aborted });
    });
  });
}

export class TaskBudget {
  contract: Contract;
  root: string;
  phase: 'editing' | 'checking' | 'repair' | 'accepted' | 'exhausted' = 'editing';
  deadline: number;
  runs = new Map<string, Run>();
  mutations = new Set<string>();
  running = false;
  formatOnly = false;
  answerOnlyTurn = false;
  formatRepairs = 0;
  receipt: string;
  timer: ReturnType<typeof setTimeout>;
  private allowed: { path: string; tree: boolean }[];
  private definitions: string[];
  private definitionHash: string;
  private ctx: any;

  constructor(raw: string, file: string, root: string, ctx: any) {
    this.ctx = ctx;
    this.contract = parse(raw);
    this.root = canonical(root);
    const paths = [...this.contract.allowed_paths, ...this.contract.checks.flatMap(c => [...c.inputs, ...(c.definition_files || [])])];
    if (paths.some(p => isAbsolute(p) || !below(this.root, canonical(resolve(this.root, p))))) throw new Error('task_path_outside_project');
    this.allowed = this.contract.allowed_paths.map(p => ({ path: canonical(resolve(this.root, p)), tree: p.endsWith('/') }));
    this.definitions = [file, ...this.contract.checks.flatMap(c => c.definition_files || []).map(p => resolve(this.root, p))];
    this.definitionHash = this.fingerprint(this.definitions);
    this.deadline = Date.now() + this.contract.elapsed_ms;
    const base = process.env.SHAME_TASK_RECEIPT_DIR || join(tmpdir(), 'shame-task-budgets');
    mkdirSync(base, { recursive: true });
    const folder = mkdtempSync(join(base, 'task-'));
    this.receipt = join(folder, 'receipt.json');
    this.timer = setTimeout(() => { this.phase = 'exhausted'; this.save('task_elapsed_budget_exhausted'); this.ctx.ui?.notify?.('Task elapsed-time budget exhausted', 'warning'); this.ctx.abort?.(); }, this.contract.elapsed_ms);
    this.timer.unref?.();
    this.save();
  }
  private fingerprint(paths: string[]): string {
    return hash(JSON.stringify(paths.map(p => {
      const path = canonical(resolve(this.root, p));
      if (!existsSync(path)) return [p, 'missing'];
      if (!statSync(path).isFile() || statSync(path).size > 20 * 1024 * 1024) throw new Error('task_input_must_be_bounded_file');
      return [p, hash(readFileSync(path))];
    })));
  }
  private inputs(c: Check) { return this.fingerprint(c.inputs); }
  save(reason?: string) {
    writeFileSync(this.receipt, JSON.stringify({ schema: 'pi.task_budget.receipt.v1', contract_hash: hash(JSON.stringify(this.contract)), deliverable: this.contract.deliverable, phase: this.phase, deadline: this.deadline, reason, checks: Object.fromEntries(this.runs) }, null, 2));
    if (reason) recordFailure(this.ctx, { kind: 'task_budget_event', goal: this.contract.deliverable,
      reason_codes: [reason], phase: this.phase, task_receipt: this.receipt,
      check_attempts: Object.fromEntries([...this.runs].map(([id, run]) => [id, run.attempts])) });
    this.ctx.ui?.setStatus?.('shame-task', `task: ${this.phase}`);
  }
  dispose() { clearTimeout(this.timer); }
  private expire() {
    if (this.phase !== 'accepted' && Date.now() >= this.deadline) { this.phase = 'exhausted'; this.save('task_elapsed_budget_exhausted'); }
  }
  tool(event: any): string | null {
    this.expire();
    const tool = baseTool(event.toolName);
    if (this.answerOnlyTurn) return readers.has(tool) ? null : 'task_question_is_read_only';
    if (this.formatOnly) return 'task_format_repair_is_output_only';
    if (this.phase === 'accepted') return 'task_already_accepted';
    if (this.phase === 'exhausted') return 'task_budget_exhausted';
    if (readers.has(tool)) return null;
    if (this.contract.mode === 'question') return 'task_question_is_read_only';
    if (tool === 'task_check') return null;
    if (!['write', 'edit'].includes(tool)) return 'task_tool_not_approved_use_named_check';
    if (this.running || !['editing', 'repair'].includes(this.phase)) return 'task_edits_require_editing_or_failed_check';
    const input = event.input || {};
    if (typeof input.path !== 'string') return 'task_write_path_missing';
    const path = canonical(resolve(this.root, input.path));
    if (this.definitions.some(p => canonical(p) === path)) return 'task_check_definition_is_frozen';
    if (!this.allowed.some(a => a.tree ? below(a.path, path) : a.path === path)) return 'task_write_path_not_allowed';
    this.mutations.add(String(event.toolCallId || input.path));
    return null;
  }
  toolResult(event: any) {
    this.mutations.delete(String(event.toolCallId || event.input?.path || ''));
  }
  questionAnswered() { this.phase = 'accepted'; this.dispose(); this.save(); }
  requestFormatRepair(): boolean {
    if (this.formatRepairs >= 1) return false;
    this.formatRepairs++;
    this.formatOnly = true;
    return true;
  }
  validReport(state: string) {
    this.formatOnly = false;
    if (this.phase === 'exhausted' && !['failed', 'needs_human'].includes(state)) return 'task_budget_exhausted';
    if (this.contract.mode === 'task' && state === 'done' && this.phase !== 'accepted') return 'task_acceptance_checks_incomplete';
    if (this.phase === 'accepted' && state !== 'done') return 'task_already_accepted';
    return null;
  }
  async run(id: string, exec: (command: string, args: string[], options: any) => Promise<any>, signal?: AbortSignal) {
    this.expire();
    if (this.formatOnly || this.phase === 'accepted' || this.phase === 'exhausted' || this.contract.mode === 'question') throw new Error('task_execution_not_active');
    if (this.running || this.mutations.size) throw new Error('task_wait_for_batched_edits');
    const c = this.contract.checks.find(c => c.id === id);
    if (!c) throw new Error('task_check_not_approved');
    if (this.definitionHash !== this.fingerprint(this.definitions)) throw new Error('task_check_definition_changed_requires_approval');
    const inputHash = this.inputs(c), previous = this.runs.get(id);
    if (previous?.passed && previous.input_hash === inputHash) return { cached: true, ...previous, receipt: this.receipt };
    if (previous && c.kind === 'review') throw new Error('task_review_resubmission_requires_approval');
    if ((previous?.failures || 0) >= 3) { this.phase = 'exhausted'; this.save('task_check_repair_budget_exhausted'); throw new Error('task_check_repair_budget_exhausted'); }
    this.running = true; this.phase = 'checking';
    try {
      const timeout = Math.max(1, Math.min(c.timeout_ms, this.deadline - Date.now()));
      let result;
      try { result = await exec(c.argv[0], c.argv.slice(1), { cwd: this.root, timeout, signal }); }
      catch (error) { result = { code: -1, stdout: '', stderr: String(error), killed: false }; }
      const passed = result.code === 0 && !result.killed && inputHash === this.inputs(c) && this.definitionHash === this.fingerprint(this.definitions) && Date.now() < this.deadline;
      const run: Run = { command: c.argv.join(' '), argv: [...c.argv], result: result.stdout?.trim() || `exit_code=${result.code}`, stdout: result.stdout || '', stderr: result.stderr || '', exit_code: result.code, input_hash: inputHash, passed, attempts: (previous?.attempts || 0) + 1, failures: passed ? 0 : (previous?.failures || 0) + 1 };
      this.runs.set(id, run);
      if (!passed) this.phase = result.aborted || run.failures >= 3 || c.kind === 'review' ? 'exhausted' : 'repair';
      else if (this.contract.checks.every(x => { const r = this.runs.get(x.id); return r?.passed && r.input_hash === this.inputs(x); }) && Date.now() < this.deadline) { this.phase = 'accepted'; this.dispose(); }
      this.expire();
      const reason = this.phase === 'exhausted' && Date.now() >= this.deadline ? 'task_elapsed_budget_exhausted'
        : passed ? undefined : result.aborted ? 'task_cancelled' : result.timedOut ? 'task_check_deadline_exceeded'
        : run.failures >= 3 ? 'task_check_repair_budget_exhausted' : 'task_check_failed';
      this.save(reason);
      return { ...run, reason, phase: this.phase, receipt: this.receipt };
    } finally { this.running = false; }
  }
}

export function installTaskBudget(pi: any) {
  let current: TaskBudget | null = null;
  function start(file: string, ctx: any) {
    const path = canonical(resolve(ctx.cwd, file));
    const next = new TaskBudget(readFileSync(path, 'utf8'), path, ctx.cwd, ctx);
    current?.dispose(); current = next;
  }
  pi.on('session_start', (_e: any, ctx: any) => { if (process.env.SHAME_TASK_BUDGET) start(process.env.SHAME_TASK_BUDGET, ctx); });
  pi.on('session_shutdown', () => { current?.dispose(); current = null; });
  pi.on('input', (e: any) => { if (current && e.source !== 'extension' && ['accepted', 'exhausted'].includes(current.phase)) current.answerOnlyTurn = true; });
  pi.on('before_agent_start', () => current ? { message: {
    customType: 'task-budget', display: false,
    content: JSON.stringify({ contract: current.contract, phase: current.phase, remaining_ms: Math.max(0, current.deadline - Date.now()), receipt: current.receipt, output_only: current.formatOnly, question_only: current.answerOnlyTurn || current.contract.mode === 'question' }),
  } } : undefined);
  pi.on('tool_call', (e: any, ctx: any) => {
    const reason = current?.tool(e);
    if (reason) {
      recordFailure(ctx, { kind: 'task_violation', goal: current?.contract.deliverable, reason_codes: [reason],
        tool_name: e.toolName, tool_call_id: e.toolCallId, phase: current?.phase, task_receipt: current?.receipt });
      return { block: true, terminate: Boolean(current?.formatOnly || current?.phase === 'accepted' || current?.phase === 'exhausted'), reason: JSON.stringify({ schema: 'pi.task_budget.violation.v1', code: reason, phase: current?.phase, receipt: current?.receipt }) };
    }
  });
  pi.on('tool_result', (e: any) => current?.toolResult(e));
  async function command(args: string, ctx: any) {
    if (args.trim().startsWith('start ')) start(args.trim().slice(6).trim(), ctx);
    ctx.ui.notify(current ? JSON.stringify({ phase: current.phase, deliverable: current.contract.deliverable, receipt: current.receipt }) : 'No task budget armed', 'info');
  }
  pi.registerCommand('shame-task', {
    description: 'Compatibility alias for /shame task start <contract.json> or status', handler: command,
  });
  pi.registerTool?.({
    name: 'task_check', label: 'Approved task check', description: 'Run an operator-approved named check. No custom commands or arguments. Returns cached success when declared inputs have not changed.',
    parameters: { type: 'object', properties: { id: { type: 'string' } }, required: ['id'], additionalProperties: false },
    async execute(_id: string, params: { id: string }, signal: AbortSignal) {
      if (!current) throw new Error('No task budget armed');
      const result = await current.run(params.id, runApprovedCommand, signal);
      return { content: [{ type: 'text', text: JSON.stringify(result) }], details: result };
    },
  });
  return { command, get current() { return current; } };
}
