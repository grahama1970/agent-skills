#!/usr/bin/env node
// Data-first report checker for lazy-report-shame-shame-shame.
// The only report contract is the final pi.agent_status.v1 JSON object.
// Pydantic owns state/proof legality; this file only extracts, duplicate-checks,
// invokes validation, and returns the validated object for the extension renderer.

import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const CHECKER_VERSION = '2026-09-07.status-json-typed-context.v12';
const TRUTHY_FLAG_VALUES = new Set(['1', 'true', 'yes']);
const FALSY_FLAG_VALUES = new Set(['0', 'false', 'no']);
const flagEnabled = (value) => TRUTHY_FLAG_VALUES.has(String(value || '').trim().toLowerCase());
const flagValue = (value) => {
  const normalized = String(value ?? '').trim().toLowerCase();
  if (!normalized) return null;
  if (TRUTHY_FLAG_VALUES.has(normalized)) return true;
  if (FALSY_FLAG_VALUES.has(normalized)) return false;
  return null;
};
const MUTATING_TURN = flagEnabled(process.env.LRSSS_MUTATING_TURN);
const FORCE_STATUS = flagEnabled(process.env.LRSSS_FORCE_STATUS);
const STRICT_STATUS = flagEnabled(process.env.LRSSS_STRICT_STATUS);
const FORMAT_ONLY_RETRY = flagEnabled(process.env.LRSSS_FORMAT_ONLY_RETRY);

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

function findJsonFences(input) {
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
        const body = input.slice(active.bodyStart, start);
        let parsed = null;
        try { parsed = JSON.parse(body); } catch { parsed = null; }
        fences.push({ body, start: active.start, end, parsed });
        active = null;
      }
      offset = end;
      continue;
    }
    const open = fenceOpen(line);
    if (open) active = { marker: open.marker, start, bodyStart: end };
    offset = end;
  }
  return fences;
}

function findStatusJson(input) {
  const fences = findJsonFences(input);
  for (let i = fences.length - 1; i >= 0; i -= 1) {
    if (fences[i].parsed && fences[i].parsed.schema === 'pi.agent_status.v1') return fences[i];
  }
  return null;
}

const typedContextFailures = [];

function parseJsonEnv(name) {
  const raw = String(process.env[name] || '').trim();
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed;
    typedContextFailures.push({ name, type: 'typed_context_not_object' });
    return null;
  } catch {
    typedContextFailures.push({ name, type: 'typed_context_json_invalid' });
    return null;
  }
}

const typedContextSources = [
  parseJsonEnv('LRSSS_TYPED_TURN_CONTEXT'),
  parseJsonEnv('LRSSS_TURN_CONTEXT'),
  parseJsonEnv('LRSSS_STATUS_CONTEXT'),
  parseJsonEnv('LRSSS_TASK_CONTEXT'),
].filter(Boolean);

function valueAtPath(source, path) {
  let value = source;
  for (const key of path) {
    if (!value || typeof value !== 'object' || !(key in value)) return undefined;
    value = value[key];
  }
  return value;
}

function firstTypedValue(paths, envNames = []) {
  for (const source of typedContextSources) {
    for (const path of paths) {
      const value = valueAtPath(source, path);
      if (value !== undefined && value !== null && String(value).trim() !== '') return value;
    }
  }
  for (const name of envNames) {
    const value = process.env[name];
    if (value !== undefined && value !== null && String(value).trim() !== '') return value;
  }
  return null;
}

function contextFlag(paths, envNames = [], options = {}) {
  const value = firstTypedValue(paths, envNames);
  if (typeof value === 'boolean') return value;
  if (value && typeof value === 'object') {
    for (const key of ['active', 'enabled', 'required', 'present']) {
      if (key in value) {
        const nested = typeof value[key] === 'boolean' ? value[key] : flagValue(value[key]);
        if (nested !== null) return nested;
      }
    }
    return true;
  }
  const flag = flagValue(value);
  if (flag !== null) return flag;
  return options.nonBooleanStringTruthy && String(value || '').trim() ? true : null;
}

function contextText(paths, envNames = []) {
  const value = firstTypedValue(paths, envNames);
  if (value && typeof value === 'object') {
    for (const key of ['immutable_goal_state', 'immutableGoalState', 'global_goal_state', 'globalGoalState', 'goal_state', 'goalState', 'outcome', 'state', 'disposition', 'status', 'result', 'completion_state', 'completionState', 'goal_completion', 'goalCompletion', 'mode', 'value']) {
      if (value[key] !== undefined && value[key] !== null && String(value[key]).trim() !== '') {
        return String(value[key]).trim();
      }
    }
    return '';
  }
  return String(value || '').trim();
}

function normalizedToken(value) {
  return String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
}

function questionModeRequiresAnswer(mode) {
  const normalized = normalizedToken(mode);
  return new Set(['answer_required', 'requires_answer', 'question', 'question_answer', 'qa', 'answer']).has(normalized)
    || flagValue(mode) === true;
}

const questionMode = contextText(
  [
    ['question_mode'],
    ['questionMode'],
    ['typed_turn_context', 'question_mode'],
    ['typedTurnContext', 'questionMode'],
    ['turn', 'question_mode'],
    ['turn', 'questionMode'],
    ['turn', 'mode'],
  ],
  ['LRSSS_QUESTION_MODE', 'LRSSS_TURN_QUESTION_MODE', 'LRSSS_TYPED_QUESTION_MODE'],
);
const explicitAnswerRequired = contextFlag(
  [
    ['answer_required'],
    ['answerRequired'],
    ['typed_turn_context', 'answer_required'],
    ['typedTurnContext', 'answerRequired'],
    ['turn', 'answer_required'],
    ['turn', 'answerRequired'],
    ['question', 'answer_required'],
    ['question', 'answerRequired'],
  ],
  ['LRSSS_ANSWER_REQUIRED', 'LRSSS_TURN_ANSWER_REQUIRED', 'LRSSS_TYPED_ANSWER_REQUIRED'],
);
const answerRequired = explicitAnswerRequired === true || (explicitAnswerRequired === null && questionModeRequiresAnswer(questionMode));
const immutableGoalContext = contextFlag(
  [
    ['immutable_goal_context'],
    ['immutableGoalContext'],
    ['immutable_goal'],
    ['immutableGoal'],
    ['typed_turn_context', 'immutable_goal_context'],
    ['typedTurnContext', 'immutableGoalContext'],
    ['typed_turn_context', 'immutable_goal'],
    ['typedTurnContext', 'immutableGoal'],
    ['turn', 'immutable_goal_context'],
    ['turn', 'immutableGoalContext'],
    ['turn', 'immutable_goal'],
    ['turn', 'immutableGoal'],
  ],
  ['LRSSS_IMMUTABLE_GOAL_CONTEXT', 'LRSSS_IMMUTABLE_GOAL_TURN', 'LRSSS_IMMUTABLE_GOAL', 'LRSSS_TYPED_IMMUTABLE_GOAL_CONTEXT'],
  { nonBooleanStringTruthy: true },
);
const authoritativeTaskOutcome = contextText(
  [
    ['authoritative_task_outcome'],
    ['authoritativeTaskOutcome'],
    ['task_outcome'],
    ['taskOutcome'],
    ['runner_outcome'],
    ['runnerOutcome'],
    ['outcome'],
    ['status'],
    ['result'],
    ['completion_state'],
    ['completionState'],
    ['goal_completion'],
    ['goalCompletion'],
    ['task', 'outcome'],
    ['task', 'status'],
    ['task', 'result'],
    ['task', 'immutable_goal_state'],
    ['task', 'immutableGoalState'],
    ['task', 'global_goal_state'],
    ['task', 'globalGoalState'],
    ['task', 'goal_state'],
    ['task', 'goalState'],
    ['task', 'completion_state'],
    ['task', 'completionState'],
    ['runner', 'outcome'],
    ['runner', 'status'],
    ['runner', 'result'],
    ['runner', 'immutable_goal_state'],
    ['runner', 'immutableGoalState'],
    ['runner', 'global_goal_state'],
    ['runner', 'globalGoalState'],
    ['runner', 'goal_state'],
    ['runner', 'goalState'],
    ['runner', 'completion_state'],
    ['runner', 'completionState'],
    ['typed_turn_context', 'authoritative_task_outcome'],
    ['typedTurnContext', 'authoritativeTaskOutcome'],
    ['typed_turn_context', 'task_outcome'],
    ['typedTurnContext', 'taskOutcome'],
    ['typed_turn_context', 'runner_outcome'],
    ['typedTurnContext', 'runnerOutcome'],
    ['typed_turn_context', 'outcome'],
    ['typedTurnContext', 'outcome'],
    ['typed_turn_context', 'immutable_goal_state'],
    ['typedTurnContext', 'immutableGoalState'],
    ['typed_turn_context', 'global_goal_state'],
    ['typedTurnContext', 'globalGoalState'],
    ['typed_turn_context', 'goal_state'],
    ['typedTurnContext', 'goalState'],
    ['immutable_goal', 'outcome'],
    ['immutableGoal', 'outcome'],
    ['immutable_goal', 'immutable_goal_state'],
    ['immutableGoal', 'immutableGoalState'],
    ['immutable_goal', 'global_goal_state'],
    ['immutableGoal', 'globalGoalState'],
    ['immutable_goal', 'goal_state'],
    ['immutableGoal', 'goalState'],
    ['immutable_goal', 'status'],
    ['immutableGoal', 'status'],
    ['immutable_goal', 'result'],
    ['immutableGoal', 'result'],
    ['immutable_goal', 'completion_state'],
    ['immutableGoal', 'completionState'],
    ['immutable_goal', 'authoritative_task_outcome'],
    ['immutableGoal', 'authoritativeTaskOutcome'],
    ['immutable_goal_context', 'outcome'],
    ['immutableGoalContext', 'outcome'],
    ['immutable_goal_context', 'immutable_goal_state'],
    ['immutableGoalContext', 'immutableGoalState'],
    ['immutable_goal_context', 'global_goal_state'],
    ['immutableGoalContext', 'globalGoalState'],
    ['immutable_goal_context', 'goal_state'],
    ['immutableGoalContext', 'goalState'],
    ['immutable_goal_context', 'status'],
    ['immutableGoalContext', 'status'],
    ['immutable_goal_context', 'result'],
    ['immutableGoalContext', 'result'],
    ['immutable_goal_context', 'completion_state'],
    ['immutableGoalContext', 'completionState'],
    ['immutable_goal_context', 'authoritative_task_outcome'],
    ['immutableGoalContext', 'authoritativeTaskOutcome'],
    ['turn', 'authoritative_task_outcome'],
    ['turn', 'authoritativeTaskOutcome'],
    ['turn', 'task_outcome'],
    ['turn', 'taskOutcome'],
    ['turn', 'outcome'],
    ['turn', 'status'],
    ['turn', 'result'],
    ['turn', 'immutable_goal_state'],
    ['turn', 'immutableGoalState'],
    ['turn', 'global_goal_state'],
    ['turn', 'globalGoalState'],
    ['turn', 'goal_state'],
    ['turn', 'goalState'],
  ],
  ['LRSSS_AUTHORITATIVE_TASK_OUTCOME', 'LRSSS_TASK_OUTCOME', 'LRSSS_RUNNER_OUTCOME', 'LRSSS_IMMUTABLE_GOAL_STATE', 'LRSSS_GLOBAL_GOAL_STATE', 'LRSSS_GOAL_STATE', 'LRSSS_GOAL_COMPLETION', 'LRSSS_TASK_STATUS', 'LRSSS_RUNNER_STATUS'],
);

function immutableGoalDisposition(validatedState, taskOutcome) {
  const state = normalizedToken(validatedState);
  const outcome = normalizedToken(taskOutcome);
  const completeOutcomes = new Set(['complete', 'completed', 'done', 'pass', 'passed', 'success', 'succeeded', 'accepted', 'ready', 'achieved', 'achieved_with_receipt', 'done_with_receipt', 'completed_with_receipt', 'complete_with_receipt']);
  const notCompleteOutcomes = new Set(['not_complete', 'incomplete', 'fail', 'failed', 'failure', 'not_ready', 'blocked', 'rejected', 'error']);
  const needsHumanOutcomes = new Set(['needs_human', 'human', 'human_required', 'needs_attention', 'needs_review']);

  if (state === 'needs_human' || needsHumanOutcomes.has(outcome)) return 'NEEDS_HUMAN';
  if (state === 'failed' || notCompleteOutcomes.has(outcome)) return 'NOT_COMPLETE';
  if (completeOutcomes.has(outcome)) return state === 'done' ? 'COMPLETE' : 'NOT_COMPLETE';
  return 'NOT_COMPLETE';
}

function stripImmutableGoalHeadline(answer) {
  return String(answer || '')
    .replace(/^(?:IMMUTABLE_GOAL:\s*)?(?:COMPLETE|NOT_COMPLETE|NEEDS_HUMAN)\b(?:\s*(?:[-:;,.\u2013\u2014])\s*|\s+|$)/i, '')
    .trim();
}

function applyImmutableGoalHeadline(status, validatedState, taskOutcome) {
  const disposition = immutableGoalDisposition(validatedState, taskOutcome);
  const headline = `IMMUTABLE_GOAL: ${disposition}`;
  const body = stripImmutableGoalHeadline(status.answer);
  status.answer = body ? `${headline} - ${body}` : headline;
  return { disposition, headline };
}

const jsonFences = findJsonFences(text);
const extractedStatus = findStatusJson(text);
const statusJson = extractedStatus?.body || null;

if (FORMAT_ONLY_RETRY) {
  const finalJson = jsonFences.length ? jsonFences[jsonFences.length - 1] : null;
  const finalSchema = finalJson?.parsed?.schema ? String(finalJson.parsed.schema) : null;
  if (finalSchema && finalSchema !== 'pi.agent_status.v1') {
    emit('reject', ['format_retry_wrong_schema'], {
      format_only_retry: true,
      observed_schema: finalSchema,
      validation_result: {
        schema: 'pi.agent_status.validation_result.v1',
        valid: false,
        errors: [{ type: 'format_retry_wrong_schema', loc: ['schema'], msg: 'format-only retry must emit pi.agent_status.v1, not guard-internal schemas', ctx: { observed_schema: finalSchema } }],
        steering: [{ code: 'format_retry_wrong_schema', loc: ['schema'], action: 'emit_only_pi_agent_status_v1', schema: 'pi.agent_status.v1' }],
      },
    });
  }
  if (jsonFences.length !== 1 || !statusJson) {
    emit('reject', ['format_retry_not_single_status_json'], {
      format_only_retry: true,
      json_fence_count: jsonFences.length,
      validation_result: {
        schema: 'pi.agent_status.validation_result.v1',
        valid: false,
        errors: [{ type: 'format_retry_not_single_status_json', loc: [], msg: 'format-only retry must be exactly one fenced pi.agent_status.v1 JSON block', ctx: { json_fence_count: jsonFences.length } }],
        steering: [{ code: 'format_retry_not_single_status_json', loc: [], action: 'emit_only_pi_agent_status_v1', schema: 'pi.agent_status.v1' }],
      },
    });
  }
  const outside = `${text.slice(0, extractedStatus.start)}${text.slice(extractedStatus.end)}`.trim();
  if (outside) {
    emit('reject', ['format_retry_extra_content'], {
      format_only_retry: true,
      validation_result: {
        schema: 'pi.agent_status.validation_result.v1',
        valid: false,
        errors: [{ type: 'format_retry_extra_content', loc: [], msg: 'format-only retry must not include prose outside the status JSON block', ctx: {} }],
        steering: [{ code: 'format_retry_extra_content', loc: [], action: 'remove_prose_emit_only_status_json' }],
      },
    });
  }
}

if (!statusJson) {
  if (MUTATING_TURN || FORCE_STATUS || STRICT_STATUS) {
    emit('reject', ['missing_agent_status_json'], {
      validation_result: {
        schema: 'pi.agent_status.validation_result.v1',
        valid: false,
        errors: [{ type: 'missing_agent_status_json', loc: [], msg: 'missing pi.agent_status.v1 JSON block', ctx: {} }],
        steering: [{ code: 'missing_agent_status_json', loc: [], action: 'emit_final_fenced_json', schema: 'pi.agent_status.v1' }],
      },
    });
  }
  emit('pass', ['no_status_required_non_mutating_turn']);
}

if (typedContextFailures.length) {
  emit('reject', ['invalid_typed_turn_context'], {
    typed_context_failures: typedContextFailures,
    validation_result: {
      schema: 'pi.agent_status.validation_result.v1',
      valid: false,
      errors: typedContextFailures.map((failure) => ({
        type: failure.type,
        loc: [failure.name],
        msg: 'typed turn context must be a JSON object',
        ctx: { env: failure.name },
      })),
      steering: typedContextFailures.map((failure) => ({
        code: failure.type,
        loc: [failure.name],
        action: 'emit_valid_typed_turn_context_json',
      })),
    },
  });
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
  const validationErrors = Array.isArray(verdict.errors) ? verdict.errors : [];
  const reasonCodes = validationErrors.length
    ? [...new Set(validationErrors.map((error) => String(error.type || 'invalid_agent_status_json')))]
    : ['invalid_agent_status_json'];
  emit('reject', reasonCodes, {
    validation_result: verdict,
  });
}

const parsedStatus = JSON.parse(statusJson);
const terminalStates = new Set(['done', 'failed', 'needs_human']);
const originalAnswer = String(parsedStatus.answer || '').trim();
let immutableGoal = null;
if (answerRequired && terminalStates.has(String(verdict.state || '')) && !originalAnswer) {
  emit('reject', ['missing_answer_to_question'], {
    state: verdict.state,
    status: parsedStatus,
    validation_result: {
      schema: 'pi.agent_status.validation_result.v1',
      valid: false,
      errors: [{ type: 'missing_answer_to_question', loc: ['answer'], msg: 'question turns require status.answer', ctx: { field: 'answer' } }],
      steering: [{ code: 'missing_answer_to_question', loc: ['answer'], field: 'answer', action: 'add_required_field' }],
    },
  });
}
if (immutableGoalContext === true && terminalStates.has(String(verdict.state || ''))) {
  immutableGoal = applyImmutableGoalHeadline(parsedStatus, verdict.state, authoritativeTaskOutcome);
}
emit('pass', ['valid_agent_status_json'], {
  state: verdict.state,
  status: parsedStatus,
  typed_turn_context: {
    answer_required: answerRequired,
    question_mode: questionMode || null,
    immutable_goal_context: immutableGoalContext === true,
    authoritative_task_outcome: authoritativeTaskOutcome || null,
    immutable_goal: immutableGoal,
  },
  ignored_trailing_content_chars: trailingContent.length,
});
