// Compete: N isolated candidates (never see each other) + declared criterion + judge scorecard naming a winner.
// Follows best-practices-competition. Seats MUST have explicit models.
const TASK = 'EDIT_ME: the isolated task every candidate solves';
const CRITERION = 'EDIT_ME: what makes one answer better (e.g. concreteness, verified code ground truth)';
const SEATS = [
  { key: 'gpt', agent: 'general-purpose', model: 'openai-codex/gpt-5.5:high' },
  { key: 'opus', agent: 'reviewer', model: 'anthropic/claude-opus-4-8:high' },
];

// Web-model seats: browser-backed $ask handlers (webgpt/webkimi/webgemini/webgrok/webperplexity),
// transported by $surf + $browser-oracle through a tau-dag single-call. Not Pi model ids.
// Note: webdeepseek does not exist; DeepSeek is the API handler 'chutes deepseek-ai/DeepSeek-V3.2-TEE' (add as an API_SEAT).
const WEB_BACKENDS = []; // e.g. ['webgpt','webkimi'] — must have bound browser-oracle tabs
function webSeatTask(backend, packet) {
  return 'Run exactly this and return the handler response verbatim plus the artifact dir:\n' +
    'cd /home/graham/.pi/agent/skills/ask && ./run.sh ' + backend + ' ' + JSON.stringify(packet) + '\n' +
    'If it fails, return the failure_code and next_command from the receipt, not prose.';
}

for (const s of SEATS) if (!s.model) throw new Error('compete fail-closed: seat ' + s.key + ' has no explicit model');
const webRuns = WEB_BACKENDS.map(b => ({ key: b, agent: "general-purpose", task: webSeatTask(b, TASK) }));
const candidates = await runs.all(SEATS.map(s => ({ key: s.key, agent: s.agent, model: s.model,
  task: 'COMPETITION BRIEF: ' + TASK + '\n\nYou are competing against another model you cannot see. Maximize: ' + CRITERION })));
const verdict = await runs.run({ key: 'judge', agent: 'reviewer', model: 'anthropic/claude-opus-4-8:high',
  task: 'Judge this model competition. Criterion: ' + CRITERION + '. Score each candidate, name exactly one winner, and state what the loser missed. Return a scorecard.\n\n' + JSON.stringify(candidates) });
return { candidates, verdict };
