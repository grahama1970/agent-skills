// Roundtable: identical packet to every seat, concurrent, join synthesis with attributed dissent.
// Follows best-practices-roundtable. Seats MUST have explicit models: {key, agent, model, task}.
// Usage: subagent({workflowScriptPath: '<this file>', async: true}) after editing SEATS.
const PACKET = 'EDIT_ME: one identical question/brief for every seat';
const SEATS = [
  { key: 'seat-a', agent: 'general-purpose', model: 'openai-codex/gpt-5.5:high' },
  { key: 'seat-b', agent: 'reviewer', model: 'anthropic/claude-opus-4-8:high' },
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

for (const s of SEATS) if (!s.model) throw new Error('roundtable fail-closed: seat ' + s.key + ' has no explicit model');
const webRuns = WEB_BACKENDS.map(b => ({ key: b, agent: "general-purpose", task: webSeatTask(b, PACKET) }));
const results = await runs.all(SEATS.map(s => ({ key: s.key, agent: s.agent, model: s.model, task: PACKET + '\n\nYou are seat ' + s.key + ' in a concurrent roundtable. Answer independently; other seats cannot see you.' })));
const join = await runs.run({ key: 'join', agent: 'reviewer', model: 'anthropic/claude-opus-4-8:high',
  task: 'Synthesize these roundtable responses into one answer with attributed agreements, disagreements, and dissent. Preserve minority positions by seat key.\n\n' + JSON.stringify(results) });
return { seats: results, synthesis: join };
