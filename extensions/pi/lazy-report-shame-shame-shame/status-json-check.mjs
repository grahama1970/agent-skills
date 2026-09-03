#!/usr/bin/env node
// Data-first report checker for lazy-report-shame-shame-shame.
// The only report contract is the final pi.agent_status.v1 JSON object.
// Pydantic owns state/proof legality; this file only extracts, duplicate-checks,
// invokes validation, and returns the validated object for the extension renderer.

import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const CHECKER_VERSION = '2026-09-03.status-json-data-first.v9';
const TRUTHY_FLAG_VALUES = new Set(['1', 'true', 'yes']);
const flagEnabled = (value) => TRUTHY_FLAG_VALUES.has(String(value || '').trim().toLowerCase());
const MUTATING_TURN = flagEnabled(process.env.LRSSS_MUTATING_TURN);
const FORCE_STATUS = flagEnabled(process.env.LRSSS_FORCE_STATUS);
const STRICT_STATUS = flagEnabled(process.env.LRSSS_STRICT_STATUS);

const VALIDATOR = process.env.LRSSS_VALIDATOR || join(
  homedir(),
  'workspace/experiments/agent-skills/skills/shame/scripts/agent_status_schema.py',
);
const PYTHON = existsSync('/usr/bin/python3') ? '/usr/bin/python3' : 'python3';

const text = await new Promise((resolve) => {
  let data = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => { data += chunk; });
  process.stdin.on('end', () => resolve(data));
});

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

function lineBody(line) {
  return String(line || '').replace('\r', '').replace('\n', '');
}

function fenceOpen(line) {
  const s = lineBody(line).trim();
  if (s === '```json') return { marker: '```' };
  if (s === '~~~json') return { marker: '~~~' };
  return null;
}

function fenceClose(line, marker) {
  return lineBody(line).trim() === marker;
}

function findStatusJson(input) {
  const lines = String(input || '').split('\n');
  const fences = [];
  let offset = 0;
  let active = null;
  for (const rawLine of lines) {
    const line = `${rawLine}\n`;
    const start = offset;
    const end = offset + line.length;
    if (active) {
      if (fenceClose(line, active.marker)) {
        fences.push({ body: input.slice(active.bodyStart, start), start: active.start, end });
        active = null;
      }
      offset = end;
      continue;
    }
    const open = fenceOpen(line);
    if (open) active = { marker: open.marker, start, bodyStart: end };
    offset = end;
  }
  for (let i = fences.length - 1; i >= 0; i -= 1) {
    try {
      const parsed = JSON.parse(fences[i].body);
      if (parsed && parsed.schema === 'pi.agent_status.v1') return fences[i];
    } catch { /* invalid JSON is handled as missing final status */ }
  }
  return null;
}

const extractedStatus = findStatusJson(text);
const statusJson = extractedStatus?.body || null;

if (!statusJson) {
  if (MUTATING_TURN || FORCE_STATUS || STRICT_STATUS) {
    emit('reject', ['missing_agent_status_json'], {
      correction: 'End the answer with a final fenced ```json block containing one valid pi.agent_status.v1 object.',
    });
  }
  emit('pass', ['no_status_required_non_mutating_turn']);
}

const trailingContent = text.slice(extractedStatus.end).trim();

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
  const pydanticError = String(verdict.error || '');
  const reason = pydanticError.includes('proof path does not exist')
    ? 'proof_path_missing'
    : pydanticError.includes('verified item is not backed by proof text')
      ? 'verified_not_backed_by_proof'
      : 'invalid_agent_status_json';
  emit('reject', [reason], {
    pydantic_error: pydanticError.slice(0, 800),
  });
}

const parsedStatus = JSON.parse(statusJson);
emit('pass', ['valid_agent_status_json'], {
  state: verdict.state,
  status: parsedStatus,
  ignored_trailing_content_chars: trailingContent.length,
});
