#!/usr/bin/env node
// Deterministic report integrity checker for lazy-report-shame-shame-shame.
// Reads a candidate assistant answer from stdin. It is intentionally narrow:
// reject only report-like delivery/status answers that lack a final titled,
// plain-English bullet summary with an honest evidence boundary.

const CHECKER_VERSION = '2026-08-31.needs-human-footer-v10';
const FORCE_STATUS = /^(1|true|yes)$/i.test(process.env.LRSSS_FORCE_STATUS || '');
const STRICT_STATUS = /^(1|true|yes)$/i.test(process.env.LRSSS_STRICT_STATUS || '');
const MUTATING_TURN = /^(1|true|yes)$/i.test(process.env.LRSSS_MUTATING_TURN || '');
const USER_TEXT = String(process.env.LRSSS_USER_TEXT || '');

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

const STATUS_SPEECH_PATTERNS = [
  /\b(?:I|we)\s+(?:have\s+|just\s+)?(?:changed|fixed|implemented|completed|deployed|merged|shipped|published|pushed|committed|closed|resolved|landed|updated)\b/i,
  /\b(?:I|we)\s+(?:am|are|'m|'re)\s+(?:done|finished|complete)\b/i,
  /\b(?:the|this)\s+(?:bug|issue|ticket|feature|change|work|fix|patch|update)\s+(?:is|was|has been)\s+(?:fixed|completed|deployed|merged|shipped|published|closed|resolved|landed|implemented|updated)\b/i,
  /^(?:status|completed|delivered|changed|verified|remaining|done|fixed|resolved|closed|implemented)\s*:/im,
  /^\s*(?:done|complete|completed|fixed|resolved|landed|implemented|closed|shipped|published)\.?\s*$/im,
  /^\s*(?:committed|pushed|merged|deployed)\b.{0,200}$/im,
  /\b(?:committed|pushed)\b[\s\S]{0,240}\b(?:done|complete|completed|fixed|resolved|landed|closed|published)\b/i,
];

const REPOSITORY_EVIDENCE_PATTERNS = [
  /\bcommit(?:ted)?\s+[`']?[0-9a-f]{7,40}[`']?\b/i,
  /\b[0-9a-f]{7,40}\b[^\n]{0,80}\b(?:commit|origin\/[A-Za-z0-9._/-]+|pushed?)\b/i,
  /\bpushed?\s+(?:to\s+)?[`']?origin\/[A-Za-z0-9._/-]+[`']?\b/i,
  /\bpushed?\s+(?:the\s+)?(?:branch|changes|commit)\b/i,
  /\b(?:PR|pull request)\s+#\d+\b/i,
  /\b(?:issue|ticket)\s+#\d+\b/i,
  /\b(?:closed|resolved)\s+(?:issue|ticket|PR|pull request)\s+#?\d+\b/i,
  /\bgh\s+issue\s+(?:close|view|comment)\b/i,
  /\bmerged\s+(?:PR|pull request|branch)\b/i,
  /\bbranch\s+[`']?[A-Za-z0-9._/-]+[`']?\s+(?:was\s+)?(?:merged|pushed|published)\b/i,
];

const STRONG_REPOSITORY_DELIVERY_PATTERNS = [
  /\bcommit(?:ted)?\s+[`']?[0-9a-f]{7,40}[`']?\b/i,
  /\bpushed?\s+(?:to\s+)?[`']?origin\/[A-Za-z0-9._/-]+[`']?\b/i,
  /\bpushed?\s+(?:the\s+)?(?:branch|changes|commit)\b/i,
  /\bmerged\s+(?:PR|pull request|branch)\b/i,
  /\b(?:closed|resolved)\s+(?:issue|ticket|PR|pull request)\s+#?\d+\b/i,
  /\b(?:tests?|suite|pytest|vitest|npm test|uv run)\b.{0,80}\b(?:pass(?:ed)?|green|ok|0 failed)\b/i,
];

const REPORT_TITLE_PATTERNS = [
  /^\s{0,3}#{0,3}\s*(?:\*\*)?(?:status report|delivery summary|final update|completion summary|what changed|result|outcome|summary)(?:\*\*)?\s*:?\s*$/i,
];

function patternCount(patterns, input = classifiedText) {
  return patterns.reduce((n, pattern) => n + (pattern.test(input) ? 1 : 0), 0);
}

function occurrenceCount(patterns, input = classifiedText) {
  let total = 0;
  for (const pattern of patterns) {
    const flags = pattern.flags.includes('g') ? pattern.flags : pattern.flags + 'g';
    const global = new RegExp(pattern.source, flags);
    total += [...input.matchAll(global)].length;
  }
  return total;
}

function hasStatusSpeechAct() {
  return STATUS_SPEECH_PATTERNS.some((pattern) => pattern.test(classifiedText));
}

function hasRepositoryEvidence() {
  return REPOSITORY_EVIDENCE_PATTERNS.some((pattern) => pattern.test(classifiedText));
}

function strongRepositoryDeliveryCount() {
  return occurrenceCount(STRONG_REPOSITORY_DELIVERY_PATTERNS);
}

function hasReportTitleNearEnd() {
  const lines = text.trimEnd().split(/\n/).slice(-10);
  return lines.some((line) => REPORT_TITLE_PATTERNS.some((pattern) => pattern.test(line.trim())));
}

function requiresStatusFooter() {
  if (STRICT_STATUS) return true;
  const statusSpeechAct = hasStatusSpeechAct();
  const repositoryEvidence = hasRepositoryEvidence();
  const strongRepoCount = strongRepositoryDeliveryCount();
  if (statusSpeechAct && repositoryEvidence) return true;
  if (strongRepoCount >= 2 && (/\b(?:done|complete|completed|fixed|resolved|landed|closed|published|pass(?:ed)?|green)\b/i.test(classifiedText))) return true;
  if ((FORCE_STATUS || MUTATING_TURN) && strongRepoCount >= 2) return true;
  if (FORCE_STATUS && statusSpeechAct && hasReportTitleNearEnd()) return true;
  return false;
}

function normalizeTitle(line) {
  return line
    .trim()
    .replace(/^#{1,6}\s*/, '')
    .replace(/^\*\*(.*)\*\*$/, '$1')
    .replace(/:$/, '')
    .trim();
}

function isReportTitle(line) {
  return REPORT_TITLE_PATTERNS.some((pattern) => pattern.test(line.trim()));
}

function bulletBody(line) {
  const match = line.match(/^\s*(?:[-*+]|\d+[.)])\s+(.+)$/);
  return match ? match[1].trim() : null;
}

function trailingReportSection() {
  const lines = text.trimEnd().split(/\n/);
  while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
  if (!lines.length) return null;

  const bullets = [];
  let title = '';
  let sawBullet = false;

  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const raw = lines[i];
    const trimmed = raw.trim();
    if (!trimmed) break;
    const body = bulletBody(raw);
    if (body !== null) {
      bullets.unshift(body);
      sawBullet = true;
      continue;
    }
    if (sawBullet && /^\s{2,}\S/.test(raw) && bullets.length) {
      bullets[0] = `${trimmed} ${bullets[0]}`;
      continue;
    }
    if (sawBullet && isReportTitle(raw)) {
      title = normalizeTitle(raw);
      return { title, bullets };
    }
    break;
  }
  return null;
}

function stripMetadata(value) {
  return value
    .replace(/https?:\/\/\S+/g, ' ')
    .replace(/`[^`]+`/g, ' ')
    .replace(/\b[0-9a-f]{7,40}\b/gi, ' ')
    .replace(/\borigin\/[A-Za-z0-9._/-]+\b/gi, ' ')
    .replace(/\b(?:commit(?:ted)?|pushed?|branch|SHA|GitHub|gh issue|PR|pull request|issue|ticket)\b/gi, ' ')
    .replace(/[#:`'".,;()[\]{}_-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function ordinaryWordCount(value) {
  const stripped = stripMetadata(value);
  const words = stripped.match(/\b[A-Za-z][A-Za-z'-]{2,}\b/g) || [];
  return words.length;
}

function isMetadataOnly(value) {
  return ordinaryWordCount(value) < 4;
}

function isOutcomeBullet(value) {
  const lower = value.toLowerCase();
  const labelHint = /^(?:changed|change|result|outcome|done|fixed|updated|delivered|summary)\s*:/i.test(value);
  const actionHint = /\b(?:now|added|changed|fixed|implemented|updated|removed|keeps|preserves|returns|loads|validates|prevents|reports|surfaces)\b/i.test(value);
  return (labelHint || actionHint || ordinaryWordCount(value) >= 6) && !isMetadataOnly(value);
}

function isEvidenceBoundaryBullet(value) {
  return /\b(?:verified|checked|validated|proof|evidence|receipt|artifact|not verified|missing|not run|did not run|was not run|unverified)\b/i.test(value)
    || /`[^`]+`\s*(?:->|passed|failed|returned|reported)/i.test(value)
    || /https?:\/\/\S+/.test(value)
    || /\b(?:issue|ticket|PR|pull request)\s+#\d+\b/i.test(value)
    || /\bcommit\s+[0-9a-f]{7,40}\b/i.test(value)
    || /\b\d+\/\d+\s+(?:tests?|cases|trials)\s+(?:passed|pass)\b/i.test(value)
    || /\b(?:passed|failed|green|0 failed)\b/i.test(value) && /\b(?:test|pytest|vitest|npm|uv|suite|case|trial)\b/i.test(value)
    || /(?:^|\s)(?:\.?\.?\/|[A-Za-z0-9_.-]+\/|\S+\.(?:json|jsonl|md|txt|log|html|png|svg|wav|zip))\S*/.test(value);
}

function responseSignalsIncomplete() {
  return /\b(?:not done|remaining|remains|blocked|missing|not verified|unverified|not run|did not run|needs|next step|todo|unfinished)\b/i.test(classifiedText);
}

function hasRemainingBoundary(bullets) {
  return bullets.some((bullet) => /\b(?:not done|needs human|human needed|waiting for human|remaining|remains|nothing remains|none|n\/a|blocked|next|todo|unfinished)\b/i.test(bullet));
}

function isNoRemainingWorkBullet(value) {
  return /^\s*(?:not done|remaining|remains|todo|unfinished)\s*:\s*(?:none|nothing|n\/a|no|zero)\b/i.test(value)
    || /^\s*(?:none|nothing remains|no remaining work)\.?\s*$/i.test(value);
}

function isLegitimateBlockerBullet(value) {
  return /\b(?:blocked|needs_attention|need(?:s)? human|waiting for|requires (?:human|operator|user) (?:approval|decision|authorization)|missing credential|external authorization|no safe next action)\b/i.test(value)
    || /\b(?:not available|unavailable)\b.{0,80}\b(?:tool context|api context|current context)\b/i.test(value)
    || /\btarget\s+(?:Pi\s+)?TUI\s+owner\b/i.test(value)
    || /\b(?:human|operator|user|owner)\b.{0,80}\brun\s+`?\/?reload`?\b/i.test(value);
}

function isActiveGoalNextStepBullet(value) {
  return /^\s*(?:not done|remaining|remains|todo|unfinished)\s*:/i.test(value)
    && /\b(?:continue|next|resume|run|rerun|execute|inspect|patch|fix|verify|validate|review)\b/i.test(value)
    && /\b(?:QRA|ledger-auditor|Tau|create-movie|Sparta|Horus|original goal|current goal|immutable goal|requested work|root task)\b/i.test(value)
    && !isLegitimateBlockerBullet(value)
    && !isNoRemainingWorkBullet(value);
}

function hasAgentOwnedObviousAction(value) {
  return /\b(?:not done|remaining|remains|not run|did not run|unfinished|todo)\b/i.test(value)
    && /\b(?:run|rerun|execute|test|verify|validate|agentic-evals|evals?|project-knowledge|brave-search|ask webgpt|webgpt|triage-error|commit|push|read back|inspect|patch|fix)\b/i.test(value)
    && !isActiveGoalNextStepBullet(value)
    && !isLegitimateBlockerBullet(value)
    && !isNoRemainingWorkBullet(value);
}

function missingAgenticEvalForNewFeature(value) {
  return /\b(?:new feature|feature|implemented|added|built|created)\b/i.test(value)
    && /\b(?:agentic-evals?|\$agentic-evals?|evals?)\b/i.test(value)
    && /\b(?:not run|did not run|missing|not added|without|no|unverified)\b/i.test(value)
    && !isLegitimateBlockerBullet(value);
}

function missingCommitOrPushForRelevantWork(value) {
  return /\b(?:not done|remaining|remains|todo|unfinished|missing|not committed|uncommitted|not pushed|unpushed|without commit|without push)\b/i.test(value)
    && /\b(?:commit|committed|push|pushed|origin\/main|relevant files?|skills?|projects?)\b/i.test(value)
    && !isLegitimateBlockerBullet(value)
    && !isNoRemainingWorkBullet(value);
}

function lacksClearNextStep(value) {
  return /\b(?:not done|remaining|remains|unfinished|todo)\b/i.test(value)
    && !isNoRemainingWorkBullet(value)
    && !isLegitimateBlockerBullet(value)
    && !/\b(?:next|run|rerun|execute|ask|decide|approve|provide|fix|patch|verify|validate|inspect|review|file|choose|open|resume)\b/i.test(value);
}

const CONTROL_PLANE_STATUS_TERMS = /\b(?:hook|guard|routing|research[- ]routing|retry|reload|sloth|shame\s+guard|shame\s+checker|lazy-report-shame-shame-shame|obvious-next-step|CONTINUE_OBVIOUS_NEXT_STEP|UNLAZY_FORCED_RETRY|RESEARCH_ROUTING_GATE_RETRY)\b/i;
const GOAL_PROGRESS_TERMS = /\b(?:immutable goal|goal|objective|requested work|actual task|root task|user-visible|project-visible|progress|QRA|ledger-auditor|eval|create-movie|Sparta|Horus)\b/i;

function hasGoalProgressOrNextStep(bullets) {
  return bullets.some((bullet) => GOAL_PROGRESS_TERMS.test(bullet)
    || hasAgentOwnedObviousAction(bullet)
    || (/\b(?:not done|remaining|remains)\b/i.test(bullet) && /\b(?:next step|next|continue|run|rerun|execute|patch|fix|verify|validate|inspect|review)\b/i.test(bullet) && !isNoRemainingWorkBullet(bullet) && !isLegitimateBlockerBullet(bullet)));
}

function currentRequestIsControlPlaneDebug() {
  return /(?:\$shame|\/shame)\b/i.test(USER_TEXT)
    && /\b(?:feedback loop|retry loop|looping|diagnose|debug|fix|repair)\b/i.test(USER_TEXT)
    && /\b(?:pi extension|extension|guard|routing|research-routing|lazy-report-shame-shame-shame|shame)\b/i.test(USER_TEXT);
}

function controlPlaneStatusWithoutGoalProgress(bullets) {
  const joined = bullets.join('\n');
  return STRICT_STATUS
    && !currentRequestIsControlPlaneDebug()
    && (CONTROL_PLANE_STATUS_TERMS.test(classifiedText) || /(?:hook|guard|routing|research-routing|retry|reload|sloth|obvious-next-step)/i.test(joined))
    && !bullets.some(isLegitimateBlockerBullet)
    && !hasGoalProgressOrNextStep(bullets);
}

function parseStatusSection() {
  const section = trailingReportSection();
  if (!section) {
    return { ok: false, failures: ['missing_trailing_report_title'] };
  }
  const failures = [];
  if (section.bullets.length < 2) failures.push('missing_plain_bullet_block');
  if (!section.bullets.some(isOutcomeBullet)) failures.push('missing_plain_outcome_bullet');
  if (!section.bullets.some(isEvidenceBoundaryBullet)) failures.push('missing_evidence_boundary');
  if (section.bullets.length && section.bullets.every(isMetadataOnly)) failures.push('metadata_only_outcome');
  const joinedBullets = section.bullets.join('\n');
  if (responseSignalsIncomplete() && !hasRemainingBoundary(section.bullets)) failures.push('missing_remaining_boundary');
  if (section.bullets.some(missingAgenticEvalForNewFeature) || missingAgenticEvalForNewFeature(joinedBullets)) failures.push('missing_agentic_eval_for_new_feature');
  if (section.bullets.some(missingCommitOrPushForRelevantWork)) failures.push('missing_commit_or_push_for_relevant_work');
  if (section.bullets.some(hasAgentOwnedObviousAction)) failures.push('obvious_next_step_not_enacted');
  if (section.bullets.some(lacksClearNextStep)) failures.push('missing_clear_next_step_for_unfinished_work');
  if (controlPlaneStatusWithoutGoalProgress(section.bullets)) failures.push('non_status_update_no_goal_progress_or_next_step');
  return { ok: failures.length === 0, failures, section };
}

const features = {
  checker_version: CHECKER_VERSION,
  force_status: FORCE_STATUS,
  strict_status: STRICT_STATUS,
  mutating_turn: MUTATING_TURN,
  status_speech_act: hasStatusSpeechAct(),
  repository_evidence: hasRepositoryEvidence(),
  strong_repository_delivery_count: strongRepositoryDeliveryCount(),
  report_title_near_end: hasReportTitleNearEnd(),
  stripped_bytes: classifiedText.length,
};

const reason_codes = [];
let decision = 'pass';
let footer_failures = [];
let parsed_section = null;

if (!requiresStatusFooter()) {
  reason_codes.push('not_delivery_report');
} else {
  const status = parseStatusSection();
  parsed_section = status.section || null;
  if (status.ok) {
    reason_codes.push('titled_plain_bullet_summary_present');
  } else {
    decision = 'reject';
    reason_codes.push('delivery_report_missing_titled_bullet_summary');
    footer_failures = status.failures;
  }
}

const payload = {
  schema: 'lazy_report_shame.report_check.v2',
  checker_version: CHECKER_VERSION,
  decision,
  reason_codes,
  features,
  footer_failures,
  parsed_section,
};

console.log(JSON.stringify(payload, null, 2));
if (decision === 'reject') {
  console.error('REJECTED_BY_REPORT_CHECK');
  for (const code of reason_codes) console.error('- ' + code);
  for (const failure of footer_failures) console.error('- ' + failure);
  process.exit(1);
}
