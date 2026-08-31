#!/usr/bin/env node
// JSON-first report checker for lazy-report-shame-shame-shame.
// NO prose classification. NO regex over assistant text. Decision inputs:
//   1. a trailing fenced ```json block containing {"schema":"pi.agent_status.v1",...}
//   2. LRSSS_MUTATING_TURN / LRSSS_FORCE_STATUS env flags (set from tool events)
// The JSON block is validated by the pydantic model in
// skills/shame/scripts/agent_status_schema.py (catalog-checked triage codes,
// state legality). Ambiguous blocker labels are a validation failure there.

import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const CHECKER_VERSION = '2026-09-01.status-report-json.v2';
const TRUTHY_FLAG_VALUES = new Set(['1', 'true', 'yes']);
const flagEnabled = (value) => TRUTHY_FLAG_VALUES.has(String(value || '').trim().toLowerCase());
const MUTATING_TURN = flagEnabled(process.env.LRSSS_MUTATING_TURN);
const FORCE_STATUS = flagEnabled(process.env.LRSSS_FORCE_STATUS);
const STRICT_STATUS = flagEnabled(process.env.LRSSS_STRICT_STATUS);

const VALIDATOR = join(
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
const ZERO_WIDTH_CHARS = new Set(['\u200b', '\u200c', '\u200d', '\ufeff']);
function normalizePolicyText(input) {
  return String(input || '')
    .normalize('NFKC')
    .split('')
    .filter((char) => !ZERO_WIDTH_CHARS.has(char))
    .join('')
    .replaceAll(/\s+/g, ' ')
    .toLowerCase();
}

function mentionsBannedWhatRemains(input) {
  return normalizePolicyText(input).includes(BANNED_SECTION_PHRASE);
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
  return normalizePolicyText(line).includes('status report');
}

function extractStatusReportSection(input, extracted) {
  if (!extracted) return { failure: 'missing_status_report_section' };
  const beforeJson = input.slice(0, extracted.start);
  const lines = beforeJson.split('\n');
  let inFence = false;
  let headingIndex = -1;
  let badHeadingFailure = null;
  for (let i = 0; i < lines.length; i += 1) {
    const trimmed = String(lines[i] || '').replaceAll('\r', '').trim();
    if (trimmed.startsWith('```')) {
      inFence = !inFence;
      continue;
    }
    if (trimmed === 'Status Report' && !inFence) {
      headingIndex = i;
      continue;
    }
    if (statusReportHeadingSignal(trimmed)) {
      if (inFence || trimmed.startsWith('>') || trimmed.startsWith('<!--')) {
        badHeadingFailure ||= 'status_report_not_owned';
      } else {
        badHeadingFailure ||= 'status_report_heading_not_exact';
      }
    }
  }
  if (headingIndex === -1) {
    return { failure: badHeadingFailure || 'missing_status_report_section' };
  }
  const body = lines.slice(headingIndex + 1).join('\n').trim();
  return { body, headingIndex };
}

function statusReportFailures(input, extracted, status) {
  if (input.slice(extracted.end).trim()) return ['trailing_content_after_status_json'];
  const section = extractStatusReportSection(input, extracted);
  if (section.failure) return [section.failure];
  const failures = [];
  const bodyLines = section.body.split('\n').map((line) => line.trim());
  const hasLine = (value) => bodyLines.includes(value) || bodyLines.includes(`- ${value}`);
  if (!hasLine(`Goal: ${status.goal}`)) {
    failures.push('status_report_goal_mismatch');
  }
  if (!hasLine(`State: ${status.state}`)) {
    failures.push('status_report_state_mismatch');
  }
  return failures;
}

// Extract the LAST fenced json block whose parsed object declares the schema.
// This is structural extraction (fence markers + JSON.parse), not prose classification.
function extractStatusJson(input) {
  const fences = [];
  let idx = 0;
  while (true) {
    const start = input.indexOf('```json', idx);
    if (start === -1) break;
    const bodyStart = input.indexOf('\n', start);
    if (bodyStart === -1) break;
    const end = input.indexOf('```', bodyStart);
    if (end === -1) break;
    fences.push({ body: input.slice(bodyStart + 1, end), start, end: end + 3 });
    idx = end + 3;
  }
  for (let i = fences.length - 1; i >= 0; i -= 1) {
    try {
      const parsed = JSON.parse(fences[i].body);
      if (parsed && parsed.schema === 'pi.agent_status.v1') return fences[i];
    } catch { /* not JSON; skip */ }
  }
  // Also accept a bare trailing JSON object (no fence).
  const braceStart = input.lastIndexOf('{"schema":"pi.agent_status.v1"');
  if (braceStart !== -1) {
    const candidate = input.slice(braceStart);
    try {
      JSON.parse(candidate);
      return { body: candidate, start: braceStart, end: input.length };
    } catch { /* fallthrough */ }
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
  process.exit(decision === 'reject' ? 1 : 0);
}

const extractedStatus = extractStatusJson(text);
const statusJson = extractedStatus?.body || null;
const statusState = statusStateFromJson(statusJson);
if (mentionsBannedWhatRemains(text) && statusState !== 'needs_human') {
  emit('reject', ['banned_what_remains_without_needs_human'], {
    state: statusState,
    correction: 'Do not use a "What remains" section unless pi.agent_status.v1 state is needs_human. Use continuing.not_done[].next_command for executable next work.',
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
try:
    json.loads(sys.stdin.read(), object_pairs_hook=hook)
except Exception:
    pass
print(json.dumps(seen_duplicates))
`], {
  input: statusJson,
  encoding: 'utf8',
  timeout: 15000,
});
try {
  const duplicates = JSON.parse(String(duplicateCheck.stdout || '[]'));
  if (Array.isArray(duplicates) && duplicates.length) {
    emit('reject', ['duplicate_agent_status_key'], { duplicates });
  }
} catch { /* duplicate detector failure falls through to validator */ }

const run = spawnSync(PYTHON, [VALIDATOR, 'validate', '-'], {
  input: statusJson,
  encoding: 'utf8',
  timeout: 15000,
});

if (run.error || run.status === 2) {
  emit('error', ['validator_invocation_failed'], { stderr: String(run.stderr || run.error || '').slice(0, 500) });
}

let verdict = null;
try { verdict = JSON.parse(String(run.stdout || '').trim().split('\n').pop()); } catch { verdict = null; }

// A crash (no parseable verdict) is a checker error, never a rejection of the
// agent's answer. Only a parsed {"valid": false} rejects.
if (!verdict || typeof verdict.valid !== 'boolean') {
  emit('error', ['validator_crashed'], {
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
        'Add a prose section named Status Report before the JSON, with Goal '
        + 'and State lines copied from pi.agent_status.v1.'
      ),
    },
    reportFailures,
  );
}

emit('pass', ['valid_agent_status_json', 'valid_status_report_section'], {
  state: verdict.state,
  status: parsedStatus,
});

