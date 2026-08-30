#!/usr/bin/env node
// Deterministic checker for final answers that name an obvious unblocked next step.
// Reads assistant text from stdin and emits a machine-readable follow_up/pass decision.

const CHECKER_VERSION = '2026-08-30.obvious-next-step.v4';

const text = await new Promise((resolve) => {
  let data = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => { data += chunk; });
  process.stdin.on('end', () => resolve(data));
});

function stripQuotedAndFenced(input) {
  return input
    .replace(/```[\s\S]*?```/g, '\n[FENCED_BLOCK]\n')
    .split(/\n/)
    .filter((line) => !/^\s*>/.test(line))
    .join('\n');
}

const classifiedText = stripQuotedAndFenced(text);
const hookNotice = /^\s*(?:🦥\s*)?(?:REJECTED_BY_SLOTH_COURT|REJECTED_BY_RESEARCH_ROUTING_GATE|RESEARCH_ROUTING_GATE_RETRY|UNLAZY_FORCED_RETRY|CONTINUE_OBVIOUS_NEXT_STEP)\b/im.test(classifiedText);

const BLOCKER_PATTERNS = [
  /\b(?:blocked|blocker|BLOCKED|NEEDS_ATTENTION|needs attention)\b/i,
  /\b(?:needs?|requires?|waiting for)\s+(?:human|user|operator|your)\s+(?:approval|authorization|confirmation|decision|input|credential|credentials|permission|token|secret|access)\b/i,
  /\b(?:missing|invalid|expired)\s+(?:credential|credentials|token|secret|api key|permission|access)\b/i,
  /\b(?:permission denied|protected branch hook declined|rate limit|quota exhausted|unauthorized|forbidden)\b/i,
  /\b(?:tell me|choose|confirm|approve|authorize|provide)\b.{0,80}\b(?:before|so I can|to continue|next)\b/i,
];

const ADVISORY_PATTERNS = [
  /^\s*(?:you can|you could|you should|consider|optionally|if you want|recommended|recommendation|i recommend)\b/i,
  /\b(?:recommended next steps|suggested next steps|options?)\b/i,
  /\b(?:would be|could be)\s+(?:to\s+)?(?:run|add|create|implement|verify|fix)\b/i,
];

const DONE_PATTERNS = [
  /^\s*(?:none|nothing|n\/a|no further action|no remaining work|nothing remains|done|complete)\b.*$/i,
  /^\s*wait for the queued reload to run\.?\s*$/i,
  /^\s*(?:reload|runtime reload)\s+(?:queued|pending)\.?\s*$/i,
  /^\s*no\s+`?\$?memory`?\s+hardening\s+work\s+remains;?\s+the\s+remaining\s+problem\s+is\s+(?:pi\s+)?(?:hook|harness|reload|runtime)\s+thrash\.?\s*$/i,
];

const ACTION_PATTERNS = [
  /`[^`]*(?:cd|uv|npm|pnpm|python|python3|node|git|gh|make|cargo|pytest|vitest|skills\/|\.\/|\/reload)[^`]*`/i,
  /(?:^|\s)(?:cd|uv|npm|pnpm|python3?|node|git|gh|make|cargo|pytest|vitest)\s+[^\n]+/i,
  /(?:^|\s)(?:\.\/|\/home\/|~\/|skills\/|src\/|tests\/|docs\/|mvp\/|\.pi\/|\.github\/)\S+/i,
  /\b(?:issue|ticket|PR|pull request)\s+#?\d+\b/i,
  /#\d+\b/,
  /\b(?:run|execute|implement|add|write|create|edit|fix|repair|rerun|verify|validate|close|open|file|update|reload|commit|push|attach|inspect|read|diagnose|triage)\b.{0,160}/i,
];

const FAILURE_REPORT_PATTERNS = [
  /\b(?:failed|failure|failing|did not pass|non[- ]zero|exit(?:ed)?\s+(?:code|status)\s+[1-9]\d*)\b/i,
  /\b(?:not acceptance|not accepted|not acceptable|insufficient|invalid|rejected)\b/i,
  /\b\d+\s*\/\s*\d+\b.{0,80}\b(?:failed|fail|passed|pass)\b/i,
  /\b(?:failed|fail)\b.{0,80}\b\d+\s*\/\s*\d+\b/i,
  /\b(?:errors?|failures?|score_errors|verdict_mismatch|schema:)\b/i,
];

const BENIGN_FAILURE_CONTEXT_PATTERNS = [
  /\b(?:recorded|captured|stored|saved|filed|added)\b.{0,120}\b(?:rejected|invalid|bad|failure|failed)\b.{0,120}\b(?:training example|shame example|classifier feedback|negative example|test fixture|fixture|eval case)\b/i,
  /\b(?:training example|shame example|classifier feedback|negative example|test fixture|fixture|eval case)\b.{0,120}\b(?:rejected|invalid|bad|failure|failed)\b/i,
  /\breason\s+`?[a-z0-9_.-]+`?\b/i,
  /(?:\bzero\b|`?\b0\b`?)\s+invalid\b.{0,120}\b(?:outputs?|reviewer|violations?)\b/i,
  /\binvalid[-_ ]to[-_ ]reviewer(?:[-_ ]violations)?\s*(?:[:=]|\b)\s*`?0`?\b/i,
  /\bfail(?:ure)?[-_ ]?count\s*(?:[:=]|\b)\s*0\b/i,
  /\b0\s+(?:FAIL|failed|failures?)\b/i,
  /\b(?:30\/30|\d+\/\d+)\b.{0,80}\b(?:pass(?:ed)?|finished|complete|ok=true)\b/i,
  /\b\d+\s*\/\s*\d+\b.{0,80}\b(?:known\s+)?failure\s+famil(?:y|ies)\b.{0,80}\bsealed\b/i,
  /\bzero\s+diagnostic\s+leaks\b/i,
  /\b(?:hook|harness|reload|runtime|status)\b.{0,120}\bthrash(?:ing)?\b.{0,120}\bnot\b.{0,80}\b`?\$?memory`?\b.{0,40}\bwork\b/i,
];

const GENERIC_FAILURE_CONTINUATION = 'Diagnose the failed gate from the latest evidence, patch the cause, and rerun the same verification/eval until it passes or a verified blocker is proven.';

const LABEL_PATTERNS = [
  /^\s*(?:[-*+]\s*)?(?:not done|remaining|remains|what remains|next step|next steps|todo|to do|unfinished|still needed|still needs?|follow-up|follow up)\s*[:—-]\s*(.*)$/i,
  /^\s*(?:#{1,6}\s*)?(?:not done|remaining|remains|what remains|next step|next steps|todo|to do|unfinished|still needed|still needs?|follow-up|follow up)\s*$/i,
];

function hasAny(patterns, input) {
  return patterns.some((pattern) => pattern.test(input));
}

function bulletBody(line) {
  const match = line.match(/^\s*(?:[-*+]|\d+[.)])\s+(.+)$/);
  return match ? match[1].trim() : null;
}

function collectFailureLines(input) {
  return input
    .split(/\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => hasAny(FAILURE_REPORT_PATTERNS, line))
    .filter((line) => !hasAny(BENIGN_FAILURE_CONTEXT_PATTERNS, line));
}

function collectLabeledActions(input) {
  const lines = input.split(/\n/);
  const actions = [];
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const inline = line.match(LABEL_PATTERNS[0]);
    const title = !inline && LABEL_PATTERNS[1].test(line);
    if (!inline && !title) continue;

    const first = (inline?.[1] || '').trim();
    const bodies = [];
    if (first) bodies.push(first);

    for (let j = i + 1; j < Math.min(lines.length, i + 7); j += 1) {
      const next = lines[j];
      if (!next.trim()) break;
      if (/^\s*#{1,6}\s+/.test(next)) break;
      if (LABEL_PATTERNS.some((pattern) => pattern.test(next))) break;
      const bullet = bulletBody(next);
      if (bullet) bodies.push(bullet);
      else if (/^\s{2,}\S/.test(next)) bodies.push(next.trim());
      else if (bodies.length === 0) bodies.push(next.trim());
      else break;
    }

    for (const body of bodies) {
      if (!body || DONE_PATTERNS.some((pattern) => pattern.test(body))) continue;
      actions.push(body);
    }
  }
  return actions;
}

const actions = collectLabeledActions(classifiedText);
const failureLines = collectFailureLines(classifiedText);
const failureReport = failureLines.length > 0;
const actionable = actions.filter((action) => hasAny(ACTION_PATTERNS, action));
if (actionable.length === 0 && failureReport) {
  actions.push(GENERIC_FAILURE_CONTINUATION);
  actionable.push(GENERIC_FAILURE_CONTINUATION);
}
const advisory = actionable.filter((action) => hasAny(ADVISORY_PATTERNS, action));
const blocked = hasAny(BLOCKER_PATTERNS, classifiedText);

let decision = 'pass';
const reason_codes = [];
if (hookNotice) {
  reason_codes.push('hook_control_or_rejection_notice');
} else if (blocked) {
  reason_codes.push('explicit_blocker_or_human_gate');
} else if (actionable.length === 0) {
  reason_codes.push(actions.length ? 'labeled_remainder_not_actionable' : 'no_labeled_unfinished_work');
} else if (advisory.length === actionable.length) {
  reason_codes.push('advisory_next_steps_only');
} else {
  decision = 'follow_up';
  reason_codes.push(failureReport ? 'unblocked_failure_report_requires_repair_loop' : 'obvious_unblocked_next_step');
}

const payload = {
  schema: 'obvious_next_step_guard.check.v1',
  checker_version: CHECKER_VERSION,
  decision,
  reason_codes,
  actions,
  actionable_actions: actionable,
  features: {
    has_blocker: blocked,
    action_count: actions.length,
    actionable_count: actionable.length,
    advisory_count: advisory.length,
    failure_report: failureReport,
    failure_lines: failureLines,
    hook_notice: hookNotice,
    stripped_bytes: classifiedText.length,
  },
};

console.log(JSON.stringify(payload, null, 2));
if (decision === 'follow_up') {
  console.error('FOLLOW_UP_BY_OBVIOUS_NEXT_STEP_GUARD');
  process.exit(2);
}
