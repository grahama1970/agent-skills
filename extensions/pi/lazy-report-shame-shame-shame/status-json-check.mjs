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

const CHECKER_VERSION = '2026-09-01.status-json-first.v1';
const MUTATING_TURN = /^(1|true|yes)$/i.test(process.env.LRSSS_MUTATING_TURN || '');
const FORCE_STATUS = /^(1|true|yes)$/i.test(process.env.LRSSS_FORCE_STATUS || '');
const STRICT_STATUS = /^(1|true|yes)$/i.test(process.env.LRSSS_STRICT_STATUS || '');

const VALIDATOR = join(
  homedir(),
  'workspace/experiments/agent-skills/skills/shame/scripts/agent_status_schema.py',
);

const text = await new Promise((resolve) => {
  let data = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => { data += chunk; });
  process.stdin.on('end', () => resolve(data));
});

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
    fences.push(input.slice(bodyStart + 1, end));
    idx = end + 3;
  }
  for (let i = fences.length - 1; i >= 0; i -= 1) {
    try {
      const parsed = JSON.parse(fences[i]);
      if (parsed && parsed.schema === 'pi.agent_status.v1') return fences[i];
    } catch { /* not JSON; skip */ }
  }
  // Also accept a bare trailing JSON object (no fence).
  const braceStart = input.lastIndexOf('{"schema":"pi.agent_status.v1"');
  if (braceStart !== -1) {
    const candidate = input.slice(braceStart);
    try {
      JSON.parse(candidate);
      return candidate;
    } catch { /* fallthrough */ }
  }
  return null;
}

function emit(decision, reasonCodes, extra = {}) {
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
    footer_failures: [],
  };
  console.log(JSON.stringify(result, null, 2));
  process.exit(decision === 'reject' ? 1 : 0);
}

const statusJson = extractStatusJson(text);

if (!statusJson) {
  if (MUTATING_TURN || FORCE_STATUS || STRICT_STATUS) {
    emit('reject', ['missing_agent_status_json'], {
      correction: 'End the answer with a fenced ```json block containing a valid pi.agent_status.v1 object.',
    });
  }
  emit('pass', ['no_status_required_non_mutating_turn']);
}

if (!existsSync(VALIDATOR)) {
  emit('error', ['validator_script_missing'], { validator: VALIDATOR });
}

// Pinned interpreter: eval runners execute under uv venvs without pydantic,
// and a bare `python3` there crashes the validator with ImportError.
const PYTHON = existsSync('/usr/bin/python3') ? '/usr/bin/python3' : 'python3';
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
  emit('reject', ['invalid_agent_status_json'], { pydantic_error: String(verdict.error || '').slice(0, 800) });
}

emit('pass', ['valid_agent_status_json'], {
  state: verdict.state,
  status: JSON.parse(statusJson),
});

