#!/usr/bin/env node
// JSON-first report checker for lazy-report-shame-shame-shame.
// Decision inputs:
//   1. a trailing fenced ```json block containing {"schema":"pi.agent_status.v1",...}
//   2. LRSSS_MUTATING_TURN / LRSSS_FORCE_STATUS env flags (set from tool events)
// The JSON block is validated by the pydantic model in
// skills/shame/scripts/agent_status_schema.py (catalog-checked triage codes,
// state legality). The prose Status Report must visibly project the final JSON.

import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const CHECKER_VERSION = '2026-09-01.status-report-json.v3';
const TRUTHY_FLAG_VALUES = new Set(['1', 'true', 'yes']);
const flagEnabled = (value) => TRUTHY_FLAG_VALUES.has(String(value || '').trim().toLowerCase());
const MUTATING_TURN = flagEnabled(process.env.LRSSS_MUTATING_TURN);
const FORCE_STATUS = flagEnabled(process.env.LRSSS_FORCE_STATUS);
const STRICT_STATUS = flagEnabled(process.env.LRSSS_STRICT_STATUS);

const VALIDATOR = process.env.LRSSS_VALIDATOR || join(
  homedir(),
  'workspace/experiments/agent-skills/skills/shame/scripts/agent_status_schema.py',
);
// Pinned interpreter: eval runners execute under uv venvs without pydantic,
// and a bare `python3` there crashes the validator with ImportError.
const PYTHON = existsSync('/usr/bin/python3') ? '/usr/bin/python3' : 'python3';

const text = await new Promise((resolve) => {
  let data = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => { data += chunk; });
  process.stdin.on('end', () => resolve(data));
});

const BANNED_SECTION_PHRASE = 'what remains';
const BANNED_UNRESOLVED_STOP_PHRASES = [
  'remaining work',
  'remaining fixes',
  'still remains',
  'left to do',
];
const HTML_ENTITIES = new Map([
  ['nbsp', ' '],
  ['#32', ' '],
  ['#x20', ' '],
  ['amp', '&'],
  ['lt', '<'],
  ['gt', '>'],
  ['nobreak', '\u2060'],
]);

function stripHtmlComments(line, active = false) {
  let rest = String(line || '');
  let output = '';
  let inComment = active;
  while (rest) {
    if (inComment) {
      const end = rest.indexOf('-->');
      if (end === -1) return { text: output, active: true };
      rest = rest.slice(end + 3);
      inComment = false;
      continue;
    }
    const start = rest.indexOf('<!--');
    if (start === -1) {
      output += rest;
      return { text: output, active: false };
    }
    output += rest.slice(0, start);
    rest = rest.slice(start + 4);
    inComment = true;
  }
  return { text: output, active: inComment };
}

const BIDI_CONTROL_RE = /[\u061c\u200e-\u200f\u202a-\u202e\u2066-\u2069]/i;
const NON_ASCII_RE = /[^\x00-\x7f]/;

function stripDefaultIgnorables(input) {
  return String(input || '').replaceAll(/[\p{Cf}\p{Default_Ignorable_Code_Point}]/gu, '');
}

function hasBidiControls(input) {
  return BIDI_CONTROL_RE.test(decodeBasicHtmlEntities(input));
}

function hasNonAsciiAfterEntityDecode(input) {
  return NON_ASCII_RE.test(decodeBasicHtmlEntities(input));
}

function hasRawHtmlTag(input) {
  return /<[a-z!/][^>]*>/i.test(decodeBasicHtmlEntities(input));
}

function hasMarkdownLinkOrImage(input) {
  return /!?\[[^\]]*\]\(/.test(String(input || ''));
}

function collectJsonStrings(value, out = []) {
  if (typeof value === 'string') out.push(value);
  else if (Array.isArray(value)) value.forEach((item) => collectJsonStrings(item, out));
  else if (value && typeof value === 'object') Object.values(value).forEach((item) => collectJsonStrings(item, out));
  return out;
}

function decodeBasicHtmlEntities(input) {
  return String(input || '')
    .replaceAll(/<!--[\s\S]*?-->/g, '')
    .replaceAll(/&([a-zA-Z]+|#[0-9]+|#x[0-9a-fA-F]+);/g, (match, key) => {
      const normalized = key.toLowerCase();
      if (HTML_ENTITIES.has(normalized)) return HTML_ENTITIES.get(normalized);
      if (normalized.startsWith('#x')) {
        const code = Number.parseInt(normalized.slice(2), 16);
        return Number.isFinite(code) ? String.fromCodePoint(code) : match;
      }
      if (normalized.startsWith('#')) {
        const code = Number.parseInt(normalized.slice(1), 10);
        return Number.isFinite(code) ? String.fromCodePoint(code) : match;
      }
      return match;
    });
}

function normalizePolicyText(input) {
  return stripDefaultIgnorables(decodeBasicHtmlEntities(input).normalize('NFKC'))
    .replaceAll(/[\\`*_~\[\](){}<>|:;.,!?#+=-]/g, ' ')
    .replaceAll(/\s+/g, ' ')
    .toLowerCase();
}

function parseStatus(raw) {
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function statusStateFromJson(raw) {
  const parsed = parseStatus(raw);
  return typeof parsed?.state === 'string' ? parsed.state : null;
}

function statusReportHeadingSignal(line) {
  return normalizePolicyText(line) === 'status report';
}

function fenceMarker(trimmed) {
  const match = String(trimmed || '').match(/^(`{3,}|~{3,})/);
  if (!match) return null;
  return { char: match[1][0], len: match[1].length };
}

function applyFenceTransition(activeFence, trimmed) {
  const marker = fenceMarker(trimmed);
  if (!marker) return { activeFence, fenceLine: false };
  if (!activeFence) return { activeFence: marker, fenceLine: true };
  const close = String(trimmed || '').match(/^(`{3,}|~{3,})[ \t]*$/);
  if (close && close[1][0] === activeFence.char && close[1].length >= activeFence.len) {
    return { activeFence: null, fenceLine: true };
  }
  return { activeFence, fenceLine: true };
}

const NON_OWNED_HTML_CONTAINERS = new Set(['pre', 'textarea', 'template', 'script', 'style', 'details', 'dialog', 'bdo']);

function applyHiddenHtmlTransition(hiddenTags, trimmed) {
  const tags = [...hiddenTags];
  const line = String(trimmed || '');
  const opens = line.matchAll(/<([a-z][a-z0-9:-]*)\b[^>]*>/gi);
  for (const tag of opens) {
    const name = tag[1].toLowerCase();
    const raw = tag[0];
    if (raw.endsWith('/>')) continue;
    if (
      NON_OWNED_HTML_CONTAINERS.has(name)
      || /\shidden\b/i.test(raw)
      || /aria-hidden\s*=\s*["']?true/i.test(raw)
      || /\sdir\s*=\s*["']?(rtl|ltr)/i.test(raw)
      || /direction\s*:\s*(rtl|ltr)/i.test(raw)
      || /unicode-bidi\s*:/i.test(raw)
      || /display\s*:\s*none/i.test(raw)
    ) {
      tags.push(name);
    }
  }
  for (let i = tags.length - 1; i >= 0; i -= 1) {
    if (new RegExp(`</${tags[i]}[^>]*>`, 'i').test(line)) tags.splice(i, 1);
  }
  return tags;
}

function isOwnedHeading(trimmed) {
  const plain = trimmed === 'Status Report';
  const atx = /^(#{1,6}) Status Report\s*#*$/.test(trimmed);
  return plain || atx;
}

function visibleOwnedLines(rawLines) {
  const visible = [];
  let activeFence = null;
  let hiddenTags = [];
  let htmlCommentActive = false;
  for (const rawLine of rawLines) {
    const originalLine = String(rawLine || '').replaceAll('\r', '');
    const strippedComment = stripHtmlComments(originalLine, htmlCommentActive);
    htmlCommentActive = strippedComment.active;
    const line = strippedComment.text;
    const trimmed = line.trim();
    const fenceTransition = applyFenceTransition(activeFence, trimmed);
    if (fenceTransition.fenceLine) {
      activeFence = fenceTransition.activeFence;
      continue;
    }
    const wasHidden = hiddenTags.length > 0;
    hiddenTags = applyHiddenHtmlTransition(hiddenTags, trimmed);
    const commentStripped = trimmed;
    const indentedCode = /^ {4,}\S/.test(line) || /^\t\S/.test(line);
    const blockquote = trimmed.startsWith('>');
    const htmlLine = commentStripped.includes('<') && commentStripped.includes('>');
    const referenceDefinition = /^\[[^\]]+\]:/.test(commentStripped);
    if (activeFence || wasHidden || hiddenTags.length > 0 || indentedCode || blockquote || htmlLine || referenceDefinition || !commentStripped) continue;
    visible.push(commentStripped);
  }
  return visible;
}

function extractStatusReportSection(input, extracted) {
  if (!extracted) return { failure: 'missing_status_report_section' };
  const beforeJson = input.slice(0, extracted.start);
  const lines = beforeJson.split('\n');
  let activeFence = null;
  let hiddenTags = [];
  let htmlCommentActive = false;
  let headingIndex = -1;
  let badHeadingFailure = null;
  for (let i = 0; i < lines.length; i += 1) {
    const originalLine = String(lines[i] || '').replaceAll('\r', '');
    const strippedComment = stripHtmlComments(originalLine, htmlCommentActive);
    htmlCommentActive = strippedComment.active;
    const line = strippedComment.text;
    const trimmed = line.trim();
    const fenceTransition = applyFenceTransition(activeFence, trimmed);
    if (fenceTransition.fenceLine) {
      activeFence = fenceTransition.activeFence;
      continue;
    }
    const wasHidden = hiddenTags.length > 0;
    hiddenTags = applyHiddenHtmlTransition(hiddenTags, trimmed);
    const notOwned = Boolean(activeFence)
      || wasHidden
      || hiddenTags.length > 0
      || trimmed.startsWith('>')
      || /^ {4,}\S/.test(line)
      || /^\t\S/.test(line)
      || htmlCommentActive
      || (trimmed.includes('<') && trimmed.includes('>'))
      || /^\[[^\]]+\]:/.test(trimmed);
    if (isOwnedHeading(trimmed) && !notOwned) {
      headingIndex = i;
      continue;
    }
    if (statusReportHeadingSignal(trimmed)) {
      if (notOwned) {
        badHeadingFailure ||= 'status_report_not_owned';
      } else {
        badHeadingFailure ||= 'status_report_heading_not_exact';
      }
    }
  }
  if (headingIndex === -1) {
    return { failure: badHeadingFailure || 'missing_status_report_section' };
  }
  let bodyEnd = lines.length;
  for (let i = headingIndex + 1; i < lines.length; i += 1) {
    const trimmed = String(lines[i] || '').replaceAll('\r', '').trim();
    if (/^#{1,6} /.test(trimmed) && !isOwnedHeading(trimmed)) {
      bodyEnd = i;
      break;
    }
  }
  const bodyLines = lines.slice(headingIndex + 1, bodyEnd);
  return { body: bodyLines.join('\n').trim(), visibleLines: visibleOwnedLines(bodyLines), headingIndex };
}

function labelValues(visibleLines, label) {
  const prefix = `${label}:`;
  const bulletPrefix = `- ${prefix}`;
  return visibleLines.flatMap((line) => {
    if (line.startsWith(bulletPrefix)) return [line.slice(bulletPrefix.length).trim()];
    if (line.startsWith(prefix)) return [line.slice(prefix.length).trim()];
    return [];
  });
}

function requireExactLabeledValues(failures, actual, expected, code) {
  const actualValues = actual.map((value) => stripDefaultIgnorables(decodeBasicHtmlEntities(value).normalize('NFKC')).trim());
  const expectedValues = expected.map((value) => stripDefaultIgnorables(decodeBasicHtmlEntities(value).normalize('NFKC')).trim()).filter(Boolean);
  if (actualValues.length !== expectedValues.length) {
    failures.push(code);
    return;
  }
  for (const value of expectedValues) {
    if (!actualValues.includes(value)) failures.push(code);
  }
}

function statusReportFailures(input, extracted, status) {
  if (input.slice(extracted.end).trim()) return ['trailing_content_after_status_json'];
  const section = extractStatusReportSection(input, extracted);
  if (section.failure) return [section.failure];
  const failures = [];
  const visibleLines = section.visibleLines;
  const goals = labelValues(visibleLines, 'Goal');
  if (goals.length !== 1 || goals[0] !== status.goal) {
    failures.push('status_report_goal_mismatch');
  }
  const states = labelValues(visibleLines, 'State');
  if (states.length !== 1 || states[0] !== status.state) {
    failures.push('status_report_state_mismatch');
  }
  const changedLines = labelValues(visibleLines, 'Changed');
  requireExactLabeledValues(failures, changedLines, status.changed || [], 'status_report_changed_mismatch');
  const verifiedLines = labelValues(visibleLines, 'Verified');
  requireExactLabeledValues(
    failures,
    verifiedLines,
    (status.verified || []).map((item) => `${item.command} -> ${item.result}`),
    'status_report_verified_mismatch',
  );
  const proofLines = labelValues(visibleLines, 'Proof');
  requireExactLabeledValues(failures, proofLines, status.proof || [], 'status_report_proof_mismatch');
  const notDoneLines = labelValues(visibleLines, 'Not done');
  requireExactLabeledValues(
    failures,
    notDoneLines,
    (status.not_done || []).map((item) => `${item.item} -> ${item.next_command}`),
    'status_report_not_done_mismatch',
  );
  if (status.failure?.triage) {
    const failureLines = labelValues(visibleLines, 'Failure');
    requireExactLabeledValues(
      failures,
      failureLines,
      [`${status.failure.triage.code} -> ${status.failure.triage.cause} -> ${status.failure.triage.next_command}`],
      'status_report_failure_mismatch',
    );
  }
  if (status.needs_human) {
    const needsHumanLines = labelValues(visibleLines, 'Needs Human');
    requireExactLabeledValues(
      failures,
      needsHumanLines,
      [`${status.needs_human.action} because ${status.needs_human.reason}`],
      'status_report_needs_human_mismatch',
    );
  }
  const payloadLabels = {
    needs_brave_search: 'needs_brave_search',
    needs_agent: 'needs_agent',
    needs_webgpt: 'needs_webgpt',
    needs_roundtable: 'needs_roundtable',
    needs_competition: 'needs_competition',
  };
  for (const [field, label] of Object.entries(payloadLabels)) {
    const payload = status[field];
    if (!payload) continue;
    const values = labelValues(visibleLines, label);
    requireExactLabeledValues(failures, values, Object.values(payload).flat(), `status_report_${field}_mismatch`);
  }
  return Array.from(new Set(failures));
}

function matchedBannedUnresolvedStopPhraseInVisibleReport(input, extracted) {
  const scanText = extracted ? input.slice(0, extracted.start) : input;
  const normalized = normalizePolicyText(visibleOwnedLines(scanText.split('\n')).join('\n'));
  if (normalized.includes(BANNED_SECTION_PHRASE)) return BANNED_SECTION_PHRASE;
  return BANNED_UNRESOLVED_STOP_PHRASES.find((phrase) => normalized.includes(phrase)) || null;
}

function extractStatusJson(input) {
  const fences = [];
  const lines = String(input || '').split(/(?<=\n)/);
  let offset = 0;
  let activeJson = null;
  let activeOuterFence = null;
  let hiddenTags = [];
  let htmlCommentActive = false;
  for (const line of lines) {
    const lineStart = offset;
    const lineEnd = offset + line.length;
    const originalWithoutNewline = line.replace(/\r?\n$/, '');
    const strippedComment = stripHtmlComments(originalWithoutNewline, htmlCommentActive);
    htmlCommentActive = strippedComment.active;
    const withoutNewline = strippedComment.text;
    const trimmed = withoutNewline.trim();
    if (activeJson) {
      const close = withoutNewline.match(/^ {0,3}(`{3,}|~{3,})[ \t]*$/);
      if (close && close[1][0] === activeJson.char && close[1].length >= activeJson.len) {
        fences.push({ body: input.slice(activeJson.bodyStart, lineStart), start: activeJson.start, end: lineEnd });
        activeJson = null;
      }
      offset = lineEnd;
      continue;
    }
    if (activeOuterFence) {
      const outerTransition = applyFenceTransition(activeOuterFence, trimmed);
      activeOuterFence = outerTransition.activeFence;
      offset = lineEnd;
      continue;
    }
    const wasHidden = hiddenTags.length > 0;
    hiddenTags = applyHiddenHtmlTransition(hiddenTags, trimmed);
    if (htmlCommentActive || wasHidden || hiddenTags.length > 0 || (trimmed.includes('<') && trimmed.includes('>'))) {
      offset = lineEnd;
      continue;
    }
    const open = withoutNewline.match(/^ {0,3}(`{3,}|~{3,})([^`~]*)$/);
    if (open) {
      const info = open[2].trim().toLowerCase();
      if (info === 'json') {
        activeJson = { char: open[1][0], len: open[1].length, start: lineStart, bodyStart: lineEnd };
      } else {
        activeOuterFence = { char: open[1][0], len: open[1].length };
      }
    }
    offset = lineEnd;
  }
  for (let i = fences.length - 1; i >= 0; i -= 1) {
    try {
      const parsed = JSON.parse(fences[i].body);
      if (parsed && parsed.schema === 'pi.agent_status.v1') return fences[i];
    } catch { /* not JSON; skip */ }
  }
  return null;
}

function emit(decision, reasonCodes, extra = {}, footerFailures = []) {
  const result = {
    schema: 'lazy_report_shame.report_check.v2',
    checker_version: CHECKER_VERSION,
    decision,
    reason_codes: reasonCodes,
    features: {
      force_status: FORCE_STATUS,
      mutating_turn: MUTATING_TURN,
      strict_status: STRICT_STATUS,
      ...extra,
    },
    footer_failures: footerFailures,
  };
  console.log(JSON.stringify(result, null, 2));
  process.exit(decision === 'pass' ? 0 : 1);
}

const extractedStatus = extractStatusJson(text);
const statusJson = extractedStatus?.body || null;
const statusState = statusStateFromJson(statusJson);
const bannedUnresolvedStopPhrase = matchedBannedUnresolvedStopPhraseInVisibleReport(text, extractedStatus);
if (bannedUnresolvedStopPhrase && statusState !== 'needs_human') {
  const reason = bannedUnresolvedStopPhrase === BANNED_SECTION_PHRASE
    ? 'banned_what_remains_without_needs_human'
    : 'banned_unresolved_stop_without_needs_human';
  emit('reject', [reason], {
    state: statusState,
    phrase: bannedUnresolvedStopPhrase,
    correction: 'Do not use unresolved-work stop sections unless pi.agent_status.v1 state is needs_human. Use continuing.not_done[].next_command for executable next work.',
  });
}

if (!statusJson) {
  if (MUTATING_TURN || FORCE_STATUS || STRICT_STATUS) {
    emit('reject', ['missing_agent_status_json'], {
      correction: (
        'End the answer with a Status Report section followed by a fenced '
        + '```json block containing a valid pi.agent_status.v1 object.'
      ),
    });
  }
  emit('pass', ['no_status_required_non_mutating_turn']);
}

const parsedStatusForBidi = parseStatus(statusJson);
const preJsonText = text.slice(0, extractedStatus.start);
const statusStringsForUnicode = collectJsonStrings(parsedStatusForBidi);
if (hasRawHtmlTag(preJsonText)) {
  emit('reject', ['raw_html_in_status_report'], {
    correction: 'Remove raw HTML from the Status Report region; tags, comments, attributes, and CSS can hide or visually reorder the report the human sees.',
  });
}
if (hasMarkdownLinkOrImage(preJsonText)) {
  emit('reject', ['markdown_link_in_status_report'], {
    correction: 'Remove Markdown links/images from the Status Report region; link titles, destinations, image alt text, and generated attributes are not plain owned report prose.',
  });
}
if (
  hasBidiControls(preJsonText)
  || statusStringsForUnicode.some((value) => hasBidiControls(value))
) {
  emit('reject', ['bidi_control_in_status_report'], {
    correction: 'Remove Unicode bidirectional controls from Status Report prose and pi.agent_status.v1 string values; they can render a different visible order than the logical text being checked.',
  });
}
if (
  hasNonAsciiAfterEntityDecode(preJsonText)
  || statusStringsForUnicode.some((value) => hasNonAsciiAfterEntityDecode(value))
) {
  emit('reject', ['non_ascii_status_report_text'], {
    correction: 'Use ASCII-only Status Report prose and pi.agent_status.v1 string values; non-ASCII glyphs can spoof required labels or banned phrases.',
  });
}

if (!existsSync(VALIDATOR)) {
  emit('error', ['validator_script_missing'], { validator: VALIDATOR });
}

const duplicateCheck = spawnSync(PYTHON, ['-c', `
import json, sys
seen_duplicates = []
def hook(pairs):
    seen = set()
    for key, _value in pairs:
        if key in seen:
            seen_duplicates.append(key)
        seen.add(key)
    return dict(pairs)
json.loads(sys.stdin.read(), object_pairs_hook=hook)
print(json.dumps(seen_duplicates))
`], {
  input: statusJson,
  encoding: 'utf8',
  timeout: 15000,
});
if (duplicateCheck.error || duplicateCheck.status !== 0) {
  emit('reject', ['duplicate_detector_failed'], { stderr: String(duplicateCheck.stderr || duplicateCheck.error || '').slice(0, 500) });
}
let duplicates = null;
try {
  duplicates = JSON.parse(String(duplicateCheck.stdout || '[]'));
} catch {
  emit('reject', ['duplicate_detector_failed'], { stdout: String(duplicateCheck.stdout || '').slice(0, 500) });
}
if (Array.isArray(duplicates) && duplicates.length) {
  emit('reject', ['duplicate_agent_status_key'], { duplicates });
}

const run = spawnSync(PYTHON, [VALIDATOR, 'validate', '-'], {
  input: statusJson,
  encoding: 'utf8',
  timeout: 15000,
});

if (run.error || (run.status !== 0 && run.status !== 1)) {
  emit('error', ['validator_invocation_failed'], { stderr: String(run.stderr || run.error || '').slice(0, 500) });
}

let verdict = null;
try { verdict = JSON.parse(String(run.stdout || '').trim().split('\n').pop()); } catch { verdict = null; }

if (!verdict || typeof verdict.valid !== 'boolean') {
  emit('error', ['validator_crashed'], {
    exit_status: run.status,
    stderr: String(run.stderr || '').slice(0, 500),
  });
}

if (verdict.valid === true && run.status !== 0) {
  emit('reject', ['validator_nonzero_with_valid_true'], {
    exit_status: run.status,
    stderr: String(run.stderr || '').slice(0, 500),
  });
}

if (verdict.valid !== true) {
  emit('reject', ['invalid_agent_status_json'], {
    pydantic_error: String(verdict.error || '').slice(0, 800),
  });
}

const parsedStatus = parseStatus(statusJson);
const reportFailures = statusReportFailures(text, extractedStatus, parsedStatus);
if (reportFailures.length) {
  emit(
    'reject',
    reportFailures,
    {
      correction: (
        'Add an assistant-owned Status Report section before the final JSON. '
        + 'Every reportable value in pi.agent_status.v1 must appear under its matching Status Report label.'
      ),
    },
    reportFailures,
  );
}

emit('pass', ['valid_agent_status_json', 'valid_status_report_section'], {
  state: verdict.state,
  status: parsedStatus,
});
