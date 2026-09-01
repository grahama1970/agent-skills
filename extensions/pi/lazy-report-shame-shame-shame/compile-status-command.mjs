#!/usr/bin/env node
// Compile a validated pi.agent_status.v1 object into the exact runnable
// command for its state. Pure data -> command mapping; zero interpretation,
// zero regex. Input: status JSON on stdin. Output: {command|null, reason}.
//
// Ladder + floors mirror $ask contracts:
//   needs_brave_search -> skills/brave-search/run.sh web (rung 0)
//   needs_agent        -> $ask tau-dag single-call, cross-family (rung 1)
//   needs_webgpt       -> $ask tau-dag --handler webgpt (rung 2; schema
//                         already required typed parent_refs)
//   needs_roundtable   -> $ask tau-dag --dag-template roundtable (>=3 seats)
//   needs_competition  -> $ask compete (>=2 candidates)
//   continuing         -> first not_done[].next_command verbatim
//   done|needs_human|failed -> no command (terminal or human-owned)

const REPO = '/home/graham/workspace/experiments/agent-skills';
const q = (s) => `'${String(s).replace(/'/g, `'\\''`)}'`;

const raw = await new Promise((resolve) => {
  let data = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (c) => { data += c; });
  process.stdin.on('end', () => resolve(data));
});

let status;
try { status = JSON.parse(raw); } catch {
  console.log(JSON.stringify({ command: null, reason: 'unparseable_status_json' }));
  process.exit(1);
}
if (status.schema !== 'pi.agent_status.v1') {
  console.log(JSON.stringify({ command: null, reason: 'wrong_schema' }));
  process.exit(1);
}

function tauSingle(question, handler) {
  return `cd ${REPO} && skills/ask/run.sh tau-dag ${q(question)} --repo local/agent-skills --target status-escalation --immutable-goal ${q('Return one likely cause, one next command, or NEEDS_ATTENTION.')} --handler ${q(handler)} --execute --json`;
}

function compile(s) {
  switch (s.state) {
    case 'continuing': {
      const next = (s.not_done || []).map((i) => i && i.next_command).find((c) => c && String(c).trim());
      return next ? { command: String(next), reason: 'continuing_next_command' } : { command: null, reason: 'continuing_without_next_command' };
    }
    case 'needs_brave_search': {
      const query = s.needs_brave_search.queries[0];
      return { command: `cd ${REPO} && skills/brave-search/run.sh web ${q(query)} --count 5`, reason: 'escalation_rung_0' };
    }
    case 'needs_agent':
      return { command: tauSingle(s.needs_agent.question, s.needs_agent.handler), reason: 'escalation_rung_1_cross_family' };
    case 'needs_webgpt': {
      const refs = (s.needs_webgpt.parent_refs || [])
        .map((r) => `${r.receipt_id} (${r.expected_schema} from ${r.expected_producer})`)
        .join(', ');
      return { command: tauSingle(`${s.needs_webgpt.question}\n\nPrior typed parent refs: ${refs}`, 'webgpt'), reason: 'escalation_rung_2_webgpt' };
    }
    case 'needs_roundtable': {
      const p = s.needs_roundtable;
      const handlers = p.handlers.map((h) => `--handler ${q(h)}`).join(' ');
      return { command: `cd ${REPO} && skills/ask/run.sh tau-dag ${q(p.question)} --repo local/agent-skills --target status-roundtable --immutable-goal ${q(p.immutable_goal)} --dag-template roundtable ${handlers} --topology concurrent --execute --json`, reason: 'milestone_roundtable' };
    }
    case 'needs_competition': {
      const p = s.needs_competition;
      const handlers = p.handlers.map((h) => `--handler ${q(h)}`).join(' ');
      const criteria = p.criteria.map((c) => `--criterion ${q(c)}`).join(' ');
      return { command: `cd ${REPO} && skills/ask/run.sh compete ${q(p.task)} --repo local/agent-skills --target status-competition --immutable-goal ${q(p.immutable_goal)} ${handlers} ${criteria} --execute --json`, reason: 'competition' };
    }
    case 'done':
    case 'needs_human':
    case 'failed':
      return { command: null, reason: `terminal_or_human_state_${s.state}` };
    default:
      return { command: null, reason: 'unknown_state' };
  }
}

console.log(JSON.stringify(compile(status), null, 2));
