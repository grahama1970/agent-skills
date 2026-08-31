#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createJiti } from 'jiti';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const checker = join(root, 'research-gate-check.mjs');
const mode = process.argv[2] || 'all';

function runChecker(payload) {
  const r = spawnSync('node', [checker], { input: JSON.stringify(payload), encoding: 'utf8', timeout: 5000 });
  const parsed = JSON.parse(r.stdout || '{}');
  return { status: r.status, parsed };
}

function memoryObs() {
  return [
    { phase: 'call', kind: 'memory', toolName: 'bash', command: 'skills/memory/run.sh recall --q x --brief' },
    { phase: 'result', kind: 'memory', toolName: 'bash', command: 'skills/memory/run.sh recall --q x --brief', ok: true },
  ];
}

function requireCond(cond, message, details) {
  if (!cond) {
    console.error(JSON.stringify({ ok: false, message, details }, null, 2));
    process.exit(1);
  }
}

async function loadExtension() {
  const jiti = createJiti(import.meta.url, { interopDefault: true });
  const mod = jiti(join(root, 'index.ts'));
  const handlers = {};
  let retryMessages = 0;
  const sentMessages = [];
  const pi = {
    on(name, fn) { (handlers[name] ||= []).push(fn); },
    registerCommand() {},
    sendUserMessage(message, options) { retryMessages += 1; sentMessages.push({ message: String(message || ''), options }); },
  };
  (mod.default || mod)(pi);
  return { handlers, getRetryMessages: () => retryMessages, getSentMessages: () => sentMessages };
}

async function probeExtensionHook() {
  const { handlers, getRetryMessages } = await loadExtension();
  await handlers.input[0]({ text: 'Choose between two competing implementations', source: 'interactive' });
  await handlers.tool_call[0]({ toolName: 'bash', toolCallId: 'm1', input: { command: 'skills/memory/run.sh recall --q x --brief' } });
  await handlers.tool_result[0]({ toolName: 'bash', toolCallId: 'm1', input: { command: 'skills/memory/run.sh recall --q x --brief' }, isError: false });
  const result = await handlers.message_end[0]({ message: { role: 'assistant', content: [{ type: 'text', text: 'Pick option A.' }] } });
  const text = result?.message?.content?.[0]?.text || '';
  requireCond(text.includes('PI_GUARD_STATUS'), 'extension hook did not return the plain guard status notice', { text });
  requireCond(text.includes('missing_ask_compete_gate'), 'extension hook did not report missing compete gate', { text });
  requireCond(!text.includes('Gate JSON') && !text.includes('REJECTED_BY_RESEARCH_ROUTING_GATE'), 'extension hook leaked raw guard rejection JSON', { text });
  requireCond(getRetryMessages() === 1, 'extension hook did not issue exactly one retry prompt', { retryMessages: getRetryMessages() });
  console.log(JSON.stringify({ ok: true, mode: 'extension_hook_compete_rejection', retryMessages: getRetryMessages(), reason: 'missing_ask_compete_gate', visible: 'plain_status' }));
}

async function probeConciseRetryReceipt() {
  const { handlers, getRetryMessages, getSentMessages } = await loadExtension();
  await handlers.input[0]({ text: 'Choose between two competing implementations', source: 'interactive' });
  await handlers.tool_call[0]({ toolName: 'bash', toolCallId: 'm1', input: { command: 'skills/memory/run.sh recall --q x --brief' } });
  await handlers.tool_result[0]({ toolName: 'bash', toolCallId: 'm1', input: { command: 'skills/memory/run.sh recall --q x --brief' }, isError: false });
  const result = await handlers.message_end[0]({ message: { role: 'assistant', id: 'concise-retry-message', content: [{ type: 'text', text: 'Pick option A.' }] } });
  const visible = result?.message?.content?.[0]?.text || '';
  const sent = getSentMessages()[0]?.message || '';
  const receiptMatch = sent.match(/^Receipt:\s*(.*)$/m);
  const receiptPath = receiptMatch?.[1] || '';
  requireCond(visible.includes('PI_GUARD_STATUS'), 'extension hook did not return the plain guard status notice', { visible });
  requireCond(getRetryMessages() === 1, 'extension hook did not issue exactly one retry prompt', { retryMessages: getRetryMessages() });
  requireCond(sent.startsWith('RESEARCH_ROUTING_GATE_RETRY'), 'retry prompt missing marker', { sent });
  requireCond(sent.includes('Missing gates: missing_ask_compete_gate'), 'retry prompt did not name missing gate compactly', { sent });
  requireCond(sent.includes('Next command:'), 'retry prompt did not include one next command', { sent });
  requireCond(sent.includes('Full gate JSON is in the receipt, not in chat.'), 'retry prompt did not state JSON was moved to receipt', { sent });
  requireCond(!sent.includes('Gate JSON') && !sent.includes('"route"') && !sent.includes('"evidence"'), 'retry prompt leaked raw gate JSON', { sent });
  requireCond(receiptPath.startsWith('/tmp/pi-research-routing/') && receiptPath.endsWith('.json'), 'retry receipt path was not under /tmp/pi-research-routing', { receiptPath, sent });
  const receipt = JSON.parse(await import('node:fs').then((fs) => fs.readFileSync(receiptPath, 'utf8')));
  requireCond(receipt.schema === 'pi_research_gate.retry_receipt.v1', 'retry receipt schema mismatch', { receipt });
  requireCond(Array.isArray(receipt.next_commands) && receipt.next_commands.some((entry) => entry.reason === 'missing_ask_compete_gate'), 'retry receipt missing next command details', { receipt });
  console.log(JSON.stringify({ ok: true, mode: 'extension_hook_concise_retry_receipt', retryMessages: getRetryMessages(), receiptPath, visible: 'plain_status' }));
}

async function probeCombinedBashEvidence() {
  const { handlers, getRetryMessages } = await loadExtension();
  const command = [
    'skills/memory/run.sh recall --q x --brief',
    'skills/brave-search/run.sh web "latest evidence" --count 5',
    'skills/triage-error/run.sh classify --text "gate failed"',
  ].join('\n');
  await handlers.input[0]({ text: 'Look up the latest gate behavior and summarize the failure.', source: 'interactive' });
  await handlers.tool_call[0]({ toolName: 'bash', toolCallId: 'multi1', input: { command } });
  await handlers.tool_result[0]({ toolName: 'bash', toolCallId: 'multi1', input: { command }, isError: false });
  const result = await handlers.message_end[0]({ message: { role: 'assistant', content: [{ type: 'text', text: 'The gate failed, and the combined Memory, Brave, and triage command captured the needed receipts.' }] } });
  requireCond(result === undefined, 'extension hook rejected combined bash evidence instead of recognizing each command', { result, retryMessages: getRetryMessages() });
  requireCond(getRetryMessages() === 0, 'extension hook queued a retry despite combined bash evidence satisfying gates', { retryMessages: getRetryMessages() });
  console.log(JSON.stringify({ ok: true, mode: 'extension_hook_combined_bash_evidence', retryMessages: getRetryMessages(), evidence: ['memory', 'brave', 'triage_error'] }));
}

async function probeMultiToolEvidence() {
  const { handlers, getRetryMessages } = await loadExtension();
  const input = {
    tool_uses: [
      { recipient_name: 'functions.bash', parameters: { command: 'skills/memory/run.sh recall --q "why thrashing" --brief' } },
      { recipient_name: 'functions.bash', parameters: { command: 'skills/brave-search/run.sh web "why thrashing" --count 5' } },
      { recipient_name: 'functions.bash', parameters: { command: 'skills/ask/run.sh tau-dag "shared context" --dag-template roundtable --handler webgpt --handler claude-fable-high --topology concurrent --execute --json' } },
    ],
  };
  await handlers.input[0]({ text: 'after days of spiraling/thrashing why is the agent not collaborating?', source: 'interactive' });
  await handlers.tool_call[0]({ toolName: 'multi_tool_use.parallel', toolCallId: 'mt1', input });
  await handlers.tool_result[0]({ toolName: 'multi_tool_use.parallel', toolCallId: 'mt1', input, isError: false });
  const result = await handlers.message_end[0]({ message: { role: 'assistant', content: [{ type: 'text', text: 'The receipts show this is a control-loop failure, not malice.' }] } });
  requireCond(result === undefined, 'extension hook rejected multi_tool_use evidence instead of recognizing nested commands', { result, retryMessages: getRetryMessages() });
  requireCond(getRetryMessages() === 0, 'extension hook queued a retry despite multi_tool_use evidence satisfying gates', { retryMessages: getRetryMessages() });
  console.log(JSON.stringify({ ok: true, mode: 'extension_hook_multi_tool_evidence', retryMessages: getRetryMessages(), evidence: ['memory', 'brave', 'ask_roundtable'] }));
}

async function probeGuardNoticeExempt() {
  const { handlers, getRetryMessages } = await loadExtension();
  await handlers.input[0]({ text: 'can you fix $shame and its pi extension as it appears to be in a feedback loop', source: 'interactive' });
  const result = await handlers.message_end[0]({ message: { role: 'assistant', content: [{ type: 'text', text: '🦥 REJECTED_BY_SLOTH_COURT\n\nThe assistant reported delivery/status in report-like prose without a clear final title.\nReason codes: delivery_report_missing_titled_bullet_summary' }] } });
  requireCond(result === undefined, 'research gate rewrote a shame guard notice', { result, retryMessages: getRetryMessages() });
  requireCond(getRetryMessages() === 0, 'research gate queued a retry for a shame guard notice', { retryMessages: getRetryMessages() });
  console.log(JSON.stringify({ ok: true, mode: 'extension_hook_guard_notice_exempt', retryMessages: getRetryMessages() }));
}

async function probeEmptyAssistantExempt() {
  const { handlers, getRetryMessages } = await loadExtension();
  await handlers.input[0]({ text: 'Look up the latest gate behavior and summarize the failure.', source: 'interactive' });
  const result = await handlers.message_end[0]({ message: { role: 'assistant', content: [] } });
  requireCond(result === undefined, 'research gate rewrote a tool-call-only empty assistant message', { result, retryMessages: getRetryMessages() });
  requireCond(getRetryMessages() === 0, 'research gate queued a retry for a tool-call-only empty assistant message', { retryMessages: getRetryMessages() });
  console.log(JSON.stringify({ ok: true, mode: 'extension_hook_empty_assistant_exempt', retryMessages: getRetryMessages() }));
}

function failBeforeFixRawGuardJsonLeak() {
  const oldVisibleText = `REJECTED_BY_RESEARCH_ROUTING_GATE

Gate JSON:
{"decision":"reject","reason_codes":["missing_memory_recall_gate"]}`;
  requireCond(!oldVisibleText.includes('REJECTED_BY_RESEARCH_ROUTING_GATE') && !oldVisibleText.includes('Gate JSON'), 'old raw guard JSON leak would be visible to the user', { oldVisibleText });
  console.log(JSON.stringify({ ok: true, mode: 'fail_before_fix_raw_guard_json_leak' }));
}

async function runRetryResetScenario(source) {
  const { handlers, getRetryMessages } = await loadExtension();
  await handlers.input[0]({ text: 'Do a comprehensive multi-source audit UI comparison for full-page inspect route versus modal.', source: 'interactive' });
  await handlers.tool_call[0]({ toolName: 'bash', toolCallId: 'scan1', input: { command: 'rg -n inspect src' } });
  await handlers.tool_result[0]({ toolName: 'bash', toolCallId: 'scan1', input: { command: 'rg -n inspect src' }, isError: false });
  const rejected = await handlers.message_end[0]({ message: { role: 'assistant', content: [{ type: 'text', text: 'Use the full page.' }] } });
  const rejectedText = rejected?.message?.content?.[0]?.text || '';
  requireCond(rejectedText.includes('memory_recall_not_first_gate'), 'first attempt should reject because scan preceded memory', { rejectedText });
  requireCond(getRetryMessages() === 1, 'first rejection should queue one retry prompt', { retryMessages: getRetryMessages() });

  await handlers.input[0]({ text: 'RESEARCH_ROUTING_GATE_RETRY\nRun Memory then Dogpile.', source });
  await handlers.tool_call[0]({ toolName: 'bash', toolCallId: 'mem1', input: { command: 'skills/memory/run.sh recall --q x --brief' } });
  await handlers.tool_result[0]({ toolName: 'bash', toolCallId: 'mem1', input: { command: 'skills/memory/run.sh recall --q x --brief' }, isError: false });
  await handlers.tool_call[0]({ toolName: 'bash', toolCallId: 'dog1', input: { command: 'skills/dogpile/run.sh search x --output-dir /tmp/pi-research-gate-dogpile' } });
  await handlers.tool_result[0]({ toolName: 'bash', toolCallId: 'dog1', input: { command: 'skills/dogpile/run.sh search x --output-dir /tmp/pi-research-gate-dogpile' }, isError: false });
  const result = await handlers.message_end[0]({ message: { role: 'assistant', content: [{ type: 'text', text: 'Completion Report\n- Changed: full-page inspect route.\n\nStatus Report\n- Changed: full-page inspect route.\n- Verified: Memory and Dogpile ran after retry.\n- Proof: retry evidence window.\n- Not done: none.' }] } });
  requireCond(result === undefined, 'retry evidence window still included stale pre-retry scan', { source, result, retryMessages: getRetryMessages() });
  requireCond(getRetryMessages() === 1, 'retry pass should not queue another retry prompt', { source, retryMessages: getRetryMessages() });
  return getRetryMessages();
}

async function probeRetryResetsStaleObservations() {
  const retryMessages = await runRetryResetScenario('extension');
  console.log(JSON.stringify({ ok: true, mode: 'extension_hook_retry_resets_stale_observations', retryMessages }));
}

async function probeGuardMarkerResetsStaleObservations() {
  const retryMessages = await runRetryResetScenario('interactive');
  console.log(JSON.stringify({ ok: true, mode: 'extension_hook_guard_marker_resets_stale_observations', retryMessages }));
}

const cases = {
  checker_status_exempt() {
    const out = runChecker({ user_text: 'what is your status. did you run the agentic-evals?', assistant_text: 'No.', observations: [] });
    requireCond(out.status === 0 && out.parsed.decision === 'pass', 'status questions should not require memory/ask gates', out);
    console.log(JSON.stringify({ ok: true, mode, decision: out.parsed.decision, signals: out.parsed.signals }));
  },
  checker_failure_reporting_status_exempt() {
    const out = runChecker({
      user_text: 'I reloaded pi. are you failure reporting. speak plainly',
      assistant_text: 'Yes. I was failure-reporting.\n\nStatus Report\n- Changed: Verified the current Pi configuration lists lazy-report-shame-shame-shame.\n- Verified: pi list matched.\n- Proof: session file.\n- Not done: none.',
      observations: [
        { phase: 'call', kind: 'scan', toolName: 'bash', command: 'pi list | rg -n "lazy-report" && tail -n 120 "$PI_SESSION_FILE" | rg -n "REJECTED_BY_SLOTH_COURT|UNLAZY_FORCED_RETRY|CONTINUE_OBVIOUS_NEXT_STEP"' },
        { phase: 'result', kind: 'scan', toolName: 'bash', command: 'pi list | rg -n "lazy-report" && tail -n 120 "$PI_SESSION_FILE" | rg -n "REJECTED_BY_SLOTH_COURT|UNLAZY_FORCED_RETRY|CONTINUE_OBVIOUS_NEXT_STEP"', ok: true },
        { phase: 'call', kind: 'memory', toolName: 'bash', command: 'skills/memory/run.sh recall --q "I reloaded pi. are you failure reporting. speak plainly" --brief' },
        { phase: 'result', kind: 'memory', toolName: 'bash', command: 'skills/memory/run.sh recall --q "I reloaded pi. are you failure reporting. speak plainly" --brief', ok: true },
        { phase: 'call', kind: 'brave', toolName: 'bash', command: 'skills/brave-search/run.sh web "I reloaded pi. are you failure reporting. speak plainly" --count 5' },
        { phase: 'result', kind: 'brave', toolName: 'bash', command: 'skills/brave-search/run.sh web "I reloaded pi. are you failure reporting. speak plainly" --count 5', ok: true },
        { phase: 'call', kind: 'triage_error', toolName: 'bash', command: 'skills/triage-error/run.sh classify --text "direct loaded-extension registry readback unavailable"' },
        { phase: 'result', kind: 'triage_error', toolName: 'bash', command: 'skills/triage-error/run.sh classify --text "direct loaded-extension registry readback unavailable"', ok: true },
      ],
    });
    requireCond(out.status === 0 && out.parsed.decision === 'pass' && out.parsed.signals.status_question === true, 'failure-reporting status prompts should not require impossible after-the-fact memory-first order', out);
    console.log(JSON.stringify({ ok: true, mode, decision: out.parsed.decision, route: out.parsed.route, signals: out.parsed.signals }));
  },

  checker_typo_status_exempt() {
    const out = runChecker({ user_text: 'what is you status? do you even know? are you noit able to give a status?', assistant_text: 'Status Report\n- Changed: answered status.\n- Verified: Not verified: status only.\n- Proof: Missing: status only.\n- Not done: none.', observations: [] });
    requireCond(out.status === 0 && out.parsed.decision === 'pass' && out.parsed.signals.status_question === true, 'typo status question should not require research gates', out);
    console.log(JSON.stringify({ ok: true, mode, decision: out.parsed.decision, signals: out.parsed.signals, route: out.parsed.route }));
  },
  checker_cross_project_status_updates_exempt() {
    const out = runChecker({ user_text: 'this issue is hobbling status updates across ALL projects', assistant_text: 'Status Report\n- Changed: answered status.\n- Verified: Not verified: status only.\n- Proof: Missing: status only.\n- Not done: none.', observations: [] });
    requireCond(out.status === 0 && out.parsed.decision === 'pass' && out.parsed.signals.status_question === true && out.parsed.route.memory_required === false, 'cross-project status updates should not require research gates', out);
    console.log(JSON.stringify({ ok: true, mode, decision: out.parsed.decision, signals: out.parsed.signals, route: out.parsed.route }));
  },
  checker_meta_routing_exempt() {
    const out = runChecker({ user_text: 'is there logic to determine when an agent should use $brave-search vs $dogpile vs $ask roundtable or $ask compete?', assistant_text: 'Yes.', observations: memoryObs() });
    requireCond(out.status === 0 && out.parsed.decision === 'pass', 'meta routing question should not require dogpile/ask just because names are mentioned', out);
    console.log(JSON.stringify({ ok: true, mode, decision: out.parsed.decision, signals: out.parsed.signals }));
  },
  checker_json_first_status_guard_design_exempt() {
    const out = runChecker({
      user_text: "and isn't this simply a json first of the status report that be deterministically checked first",
      assistant_text: 'Yes. The status object should be JSON-first, then deterministically checked, then rendered. That can mention research-routing-gates and WebGPT as gate names without requesting web research or WebGPT review.',
      observations: memoryObs(),
    });
    requireCond(out.status === 0 && out.parsed.decision === 'pass' && out.parsed.route.brave_required === false && out.parsed.route.ask_webgpt_required === false, 'JSON-first status guard design question should not require Brave or WebGPT gates', out);
    requireCond(out.parsed.signals.status_question === true || out.parsed.signals.meta_routing_question === true, 'JSON-first status guard design should be classified as status/meta routing', out);
    console.log(JSON.stringify({ ok: true, mode, decision: out.parsed.decision, route: out.parsed.route, signals: out.parsed.signals }));
  },
  checker_sidequest_thrashing_requires_roundtable() {
    const out = runChecker({ user_text: 'The agent is violating the immutable goal with side quests and self-serving unit tests.', assistant_text: 'Continue.', observations: memoryObs() });
    requireCond(out.status === 1 && out.parsed.reason_codes.includes('missing_ask_roundtable_gate'), 'side-quest/self-serving-test signal should require roundtable advice when no candidates exist', out);
    console.log(JSON.stringify({ ok: true, mode, decision: out.parsed.decision, reason_codes: out.parsed.reason_codes }));
  },
  checker_mvp_candidates_require_compete() {
    const out = runChecker({ user_text: 'We are stuck with two alternative MVP patch approaches and need to choose the best isolated implementation.', assistant_text: 'Pick A.', observations: memoryObs() });
    requireCond(out.status === 1 && out.parsed.reason_codes.includes('missing_ask_compete_gate'), 'MVP candidate choice should require compete', out);
    console.log(JSON.stringify({ ok: true, mode, decision: out.parsed.decision, reason_codes: out.parsed.reason_codes }));
  },
  checker_brave_vs_dogpile() {
    const narrow = runChecker({ user_text: 'look up the latest release notes for this one library', assistant_text: 'Answer.', observations: memoryObs() });
    const broad = runChecker({ user_text: 'do a comprehensive multi-source landscape survey of this problem', assistant_text: 'Answer.', observations: memoryObs() });
    requireCond(narrow.status === 1 && narrow.parsed.reason_codes.includes('missing_brave_search_gate'), 'narrow external research should require Brave', narrow);
    requireCond(broad.status === 1 && broad.parsed.reason_codes.includes('missing_dogpile_gate'), 'comprehensive research should require Dogpile', broad);
    console.log(JSON.stringify({ ok: true, mode, narrow: narrow.parsed.reason_codes, broad: broad.parsed.reason_codes }));
  },
  checker_local_ops_completion_today_current_does_not_require_brave() {
    const out = runChecker({
      user_text: 'can you check $ops-streamdeck and determine why the calendar day stuck on the 24th is not updating',
      assistant_text: 'VERIFIED: the current local Stream Deck date widget is updating again. The live widget image hash matches a fresh render for today, Mon 31. Validation performed: journalctl --user -u streamdeck-widgets.service --since 06:40:14 | grep -c Failed-to-load-renderer -> 0.',
      observations: [
        ...memoryObs(),
        { phase: 'call', kind: 'other', toolName: 'bash', command: 'skills/ops-streamdeck/run.sh audit-date-widget' },
        { phase: 'result', kind: 'other', toolName: 'bash', command: 'skills/ops-streamdeck/run.sh audit-date-widget', ok: true },
        { phase: 'call', kind: 'other', toolName: 'bash', command: 'skills/agentic-evals/run.sh run fixtures/agentic_eval.json' },
        { phase: 'result', kind: 'other', toolName: 'bash', command: 'skills/agentic-evals/run.sh run fixtures/agentic_eval.json', ok: true },
      ],
    });
    requireCond(out.status === 0 && out.parsed.decision === 'pass' && out.parsed.route.brave_required === false, 'local ops completion with current/today proof words should not require Brave', out);
    console.log(JSON.stringify({ ok: true, mode, decision: out.parsed.decision, route: out.parsed.route, evidence: out.parsed.evidence }));
  },
  checker_broad_error_prefers_fast_single_before_webgpt() {
    const out = runChecker({ user_text: 'We hit a generic broad error and need outside model sanity before WebGPT because WebGPT may take 20 minutes.', assistant_text: 'I will ask WebGPT first.', observations: memoryObs() });
    requireCond(out.status === 1 && out.parsed.reason_codes.includes('missing_ask_fast_single_gate'), 'broad/generic error should require fast non-browser single-call before WebGPT', out);
    requireCond(out.parsed.route.ask_webgpt_required === false && out.parsed.route.ask_roundtable_required === false, 'broad/generic error should not default to WebGPT or roundtable', out);
    console.log(JSON.stringify({ ok: true, mode, decision: out.parsed.decision, reason_codes: out.parsed.reason_codes, route: out.parsed.route }));
  },
  checker_fast_single_satisfies_broad_error_gate() {
    const out = runChecker({ user_text: 'We hit a generic broad error and need outside model sanity before WebGPT because WebGPT may take 20 minutes.', assistant_text: 'Use the fast single-call receipt first.', observations: [...memoryObs(), { phase: 'call', kind: 'ask_fast_single', toolName: 'bash', command: 'skills/ask/run.sh tau-dag "error" --handler claude-fable-low --execute --json' }, { phase: 'result', kind: 'ask_fast_single', toolName: 'bash', command: 'skills/ask/run.sh tau-dag "error" --handler claude-fable-low --execute --json', ok: true }] });
    requireCond(out.status === 0 && out.parsed.decision === 'pass' && out.parsed.evidence.ask_fast_single === true, 'fast Ask/Tau single-call should satisfy broad-error gate', out);
    console.log(JSON.stringify({ ok: true, mode, decision: out.parsed.decision, evidence: out.parsed.evidence }));
  },
  checker_triage_satisfies_broad_error_gate() {
    const out = runChecker({ user_text: 'We hit a generic broad error and need outside model sanity before WebGPT because WebGPT may take 20 minutes.', assistant_text: 'Triage produced ask_unclassified_89ad090d and I am reporting the typed receipt.', observations: [...memoryObs(), { phase: 'call', kind: 'triage_error', toolName: 'bash', command: 'skills/triage-error/run.sh classify --text "generic broad error" --layer ask' }, { phase: 'result', kind: 'triage_error', toolName: 'bash', command: 'skills/triage-error/run.sh classify --text "generic broad error" --layer ask', ok: true }] });
    requireCond(out.status === 0 && out.parsed.decision === 'pass' && out.parsed.evidence.triage_error === true && out.parsed.route.ask_fast_single_required === false, 'triage-error receipt should satisfy broad-error sanity without demanding another fast single call', out);
    console.log(JSON.stringify({ ok: true, mode, decision: out.parsed.decision, route: out.parsed.route, evidence: out.parsed.evidence }));
  },
  checker_mvp_first_requires_mvp_artifact() {
    const out = runChecker({ user_text: 'Use MVP first before implementing this into ops-chatterbox.', assistant_text: 'Proceed with broad implementation.', observations: memoryObs() });
    requireCond(out.status === 1 && out.parsed.reason_codes.includes('missing_mvp_isolated_challenge_gate'), 'MVP-first request should require project mvp/ proof artifacts', out);
    console.log(JSON.stringify({ ok: true, mode, decision: out.parsed.decision, reason_codes: out.parsed.reason_codes, route: out.parsed.route }));
  },
  checker_mvp_artifact_satisfies_gate() {
    const out = runChecker({ user_text: 'Use MVP first before implementing this into ops-chatterbox.', assistant_text: 'Proceed after MVP proof.', observations: [...memoryObs(), { phase: 'call', kind: 'mvp', toolName: 'bash', command: 'test -f mvp/001-listen/goal.md && test -f mvp/001-listen/run.sh && test -f mvp/001-listen/receipt.json' }, { phase: 'result', kind: 'mvp', toolName: 'bash', command: 'test -f mvp/001-listen/goal.md && test -f mvp/001-listen/run.sh && test -f mvp/001-listen/receipt.json', ok: true }] });
    requireCond(out.status === 0 && out.parsed.decision === 'pass' && out.parsed.evidence.mvp === true, 'mvp/ proof artifact evidence should satisfy MVP gate', out);
    console.log(JSON.stringify({ ok: true, mode, decision: out.parsed.decision, evidence: out.parsed.evidence }));
  },
  checker_retry_prompt_does_not_self_loop() {
    const out = runChecker({ user_text: 'RESEARCH_ROUTING_GATE_RETRY\nmissing_ask_roundtable_gate\n- missing_brave_search_gate:\n  skills/brave-search/run.sh web "or an mvp/ directory in the project" --count 5\n- missing_ask_roundtable_gate:\n  skills/ask/run.sh tau-dag "<shared context>" --dag-template roundtable', assistant_text: 'Plain answer after retry.', observations: [] });
    requireCond(out.status === 0 && out.parsed.decision === 'pass' && out.parsed.route.memory_required === false, 'generated retry prompts should not become a new gate target', out);
    console.log(JSON.stringify({ ok: true, mode, decision: out.parsed.decision, route: out.parsed.route, signals: out.parsed.signals }));
  },
  checker_shame_notice_does_not_self_loop() {
    const out = runChecker({ user_text: 'can you fix $shame and its pi extension as it appears to be in a feedback loop', assistant_text: '🦥 REJECTED_BY_SLOTH_COURT\n\nThe assistant reported delivery/status in report-like prose without a clear final title.\nReason codes: delivery_report_missing_titled_bullet_summary', observations: [] });
    requireCond(out.status === 0 && out.parsed.decision === 'pass' && out.parsed.route.memory_required === false, 'shame guard notices should not become research-routing gate targets', out);
    console.log(JSON.stringify({ ok: true, mode, decision: out.parsed.decision, route: out.parsed.route, signals: out.parsed.signals }));
  },
  checker_continue_prompt_does_not_self_loop() {
    const out = runChecker({ user_text: 'CONTINUE_OBVIOUS_NEXT_STEP\n\nYour previous answer named unfinished work. Execute this next action now: the active runtime/guard interaction still needs a fix so $shame and research-routing do not trigger each other.', assistant_text: 'Continuing.', observations: [] });
    requireCond(out.status === 0 && out.parsed.decision === 'pass' && out.parsed.route.memory_required === false, 'obvious-next-step continuation prompts should not become research-routing gate targets', out);
    console.log(JSON.stringify({ ok: true, mode, decision: out.parsed.decision, route: out.parsed.route, signals: out.parsed.signals }));
  },
  extension_hook_compete_rejection: probeExtensionHook,
  extension_hook_concise_retry_receipt: probeConciseRetryReceipt,
  extension_hook_combined_bash_evidence: probeCombinedBashEvidence,
  extension_hook_multi_tool_evidence: probeMultiToolEvidence,
  extension_hook_guard_notice_exempt: probeGuardNoticeExempt,
  extension_hook_empty_assistant_exempt: probeEmptyAssistantExempt,
  extension_hook_retry_resets_stale_observations: probeRetryResetsStaleObservations,
  extension_hook_guard_marker_resets_stale_observations: probeGuardMarkerResetsStaleObservations,
};

if (mode === 'fail_before_fix_raw_guard_json_leak') {
  failBeforeFixRawGuardJsonLeak();
} else if (mode === 'all') {
  for (const key of Object.keys(cases)) await cases[key]();
} else {
  requireCond(cases[mode], `unknown mode ${mode}`, { modes: Object.keys(cases) });
  await cases[mode]();
}
