#!/usr/bin/env node
const CHECKER_VERSION = '2026-08-30.tau-triage-memory-research-ask-gates.v6';

const payload = JSON.parse(await new Promise((resolve) => {
  let data = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => { data += chunk; });
  process.stdin.on('end', () => resolve(data || '{}'));
}));

const userText = String(payload.user_text || '');
const assistantText = String(payload.assistant_text || '');
const observations = Array.isArray(payload.observations) ? payload.observations : [];
const enabled = payload.enabled !== false;

function strip(input) {
  return String(input || '')
    .replace(/```[\s\S]*?```/g, '\n[FENCED_BLOCK]\n')
    .split(/\n/)
    .filter((line) => !/^\s*>/.test(line))
    .join('\n');
}
function matchesAny(text, patterns) { return patterns.some((pattern) => pattern.test(text)); }

const user = strip(userText);
const assistant = strip(assistantText);
const combined = `${user}\n${assistant}`;
const guardControlPattern = /^\s*(?:🦥|🔁)?\s*(?:PI_GUARD_STATUS|RESEARCH_ROUTING_GATE_RETRY|CONTINUE_OBVIOUS_NEXT_STEP|CONTINUING_OBVIOUS_NEXT_STEP|UNLAZY_FORCED_RETRY|REJECTED_BY_SLOTH_COURT|REJECTED_BY_RESEARCH_ROUTING_GATE)\b/i;
const guardGeneratedAssistant = guardControlPattern.test(assistant);

const controlCommand = /^\s*\/(?:reload|model|help|clear|compact|tree|session|settings|login|logout|quit|exit|shame)\b/i.test(user)
  || /^\s*\$shame\b/i.test(user)
  || guardControlPattern.test(user)
  || guardGeneratedAssistant;
const statusQuestion = /\b(?:what(?:'s| is) your status|what(?:'s| is) you status|status updates?|did you run|have you run|did you fix|have you fixed|is (?:it|the bug|this) fixed|what have you done|are you blocked|are you stuck|what does this mean|are you failure[- ]reporting|are you just failure[- ]reporting|failure[- ]reporting|speak plainly|don't you already have obvious next steps|dont you already have obvious next steps)\b/i.test(user)
  || /\b(?:are you (?:not |noit )?able to give\s+(?:a\s+)?status|can you give\s+(?:a\s+)?status|why can't you give\s+(?:a\s+)?status|why cant you give\s+(?:a\s+)?status)\b/i.test(user)
  || /\b(?:json[- ]first|structured\s+json|typed\s+status\s+object)\b[^\n]{0,160}\b(?:status\s+report|status\s+object|deterministic(?:ally)?\s+check(?:ed|er|ing)?)\b/i.test(user)
  || /\b(?:status\s+report|status\s+object|deterministic(?:ally)?\s+check(?:ed|er|ing)?)\b[^\n]{0,160}\b(?:json[- ]first|structured\s+json|typed\s+status\s+object)\b/i.test(user)
  || /\b(?:rewrite\s+(?:the\s+)?(?:previously\s+)?rejected\s+answer|rewrite\s+(?:this|that)\s+answer|status\s+report\s+footer|exact\s+required\s+status\s+report|obvious-next-step-guard|follow-up budget exhausted|RESEARCH_ROUTING_GATE_RETRY|UNLAZY_FORCED_RETRY|CONTINUE_OBVIOUS_NEXT_STEP|CONTINUING_OBVIOUS_NEXT_STEP|REJECTED_BY_SLOTH_COURT|REJECTED_BY_RESEARCH_ROUTING_GATE)\b/i.test(user);
const metaRoutingQuestion = /\b(?:logic|when|whether|should|decide|determine|router|routing|route)\b[^\n]{0,160}\b(?:brave-search|dogpile|\$ask|ask webgpt|roundtable|compete|agentic-evals|skill)\b/i.test(user)
  || /\b(?:brave-search|dogpile|\$ask|ask webgpt|roundtable|compete|agentic-evals|skill)\b[^\n]{0,160}\b(?:logic|when|whether|should|decide|determine|router|routing|route)\b/i.test(user)
  || /\b(?:research-routing-gates|research routing gates|route gates?|routing gates?)\b[^\n]{0,160}\b(?:wrong\s+name|rename|named|name|json[- ]first|status\s+report|guard\s+design|deterministic(?:ally)?\s+check(?:ed|er|ing)?)\b/i.test(user)
  || /\b(?:wrong\s+name|rename|named|name|json[- ]first|status\s+report|guard\s+design|deterministic(?:ally)?\s+check(?:ed|er|ing)?)\b[^\n]{0,160}\b(?:research-routing-gates|research routing gates|route gates?|routing gates?)\b/i.test(user);
const trivial = user.trim().split(/\s+/).filter(Boolean).length <= 3 && !/[?]/.test(user) && !/\b(?:fix|debug|research|blocked|error|why|how|what|should|can|could|ask|review|decide|choose)\b/i.test(user);
const substantive = enabled && !controlCommand && !statusQuestion && !trivial;

const broadResearchPatterns = [
  /\b(?:comprehensive|deep|from every angle|multi[- ]source|cross[- ]source|literature review|survey|landscape|state of the art|compare sources|corroborat(?:e|ion)|full research)\b/i,
  /\b(?:github\s*\+\s*arxiv|brave\s*\+\s*github|arxiv\s*\+\s*youtube)\b/i,
];
const narrowResearchPatterns = [
  /\b(?:web|search|brave-search|look up|external source|online|documentation|docs|release notes|pricing|news)\b/i,
  /\b(?:current|latest|recent|today|now)\b[^.\n]{0,100}\b(?:documentation|docs|release notes|pricing|news|web|online|external|sources?|research|api|version|model catalog|provider|library)\b/i,
  /\b(?:documentation|docs|release notes|pricing|news|web|online|external|sources?|research|api|version|model catalog|provider|library)\b[^.\n]{0,100}\b(?:current|latest|recent|today|now)\b/i,
  /\b(?:need|needs|needed|requires|required)\s+(?:research|external|web|current\s+(?:documentation|docs|release notes|pricing|news|api|version|model catalog))\b/i,
  /\b(?:I|we)\s+(?:need|should|must)\s+(?:to\s+)?(?:research|search|look up|verify externally)\b/i,
];
const blockedOrErrorPatterns = [
  /\b(?:I(?:'m| am)|we(?:'re| are)|this(?: task)? is|it is|the workflow is|the run is)\s+blocked\b/i,
  /\b(?:NEEDS_ATTENTION|BLOCKED|unclassified failure|generic failure|unknown failure)\b/,
  /\b(?:gate|tool|command|workflow|provider|handler|lane|node|DAG)\b[^.\n]{0,100}\b(?:failed|errored|timed out|timeout|blocked)\b/i,
  /\b(?:failed|errored|timed out|timeout|blocked)\b[^.\n]{0,100}\b(?:gate|tool|command|workflow|provider|handler|lane|node|DAG)\b/i,
];
const broadErrorFastSinglePatterns = [
  /\b(?:broad|generic|ambiguous|unknown|unclassified)\s+(?:error|failure|blocker|exception)\b/i,
  /\b(?:error|failure|blocker|exception)\b[^.\n]{0,100}\b(?:broad|generic|ambiguous|unknown|unclassified)\b/i,
  /\b(?:different\s+provider\s+family|fast(?:er)?\s+(?:provider|model|lane|single[- ]call)|low[- ]reasoning|low reasoning|claude[- ]?fable(?:[- ]?5)?[- ]?low|before\s+(?:asking\s+)?webgpt|webgpt[^.\n]{0,80}\b(?:slow|20\s*m(?:in|inutes)?)\b)\b/i,
];

const askWebgptPatterns = [
  /^\s*(?:\$ask|\/ask)\s+(?:web\s*gpt|chatgpt)\b/i,
  /\b(?:run|use|call|ask)\s+(?:\$ask\s+)?(?:web\s*gpt|chatgpt)\b/i,
  /\b(?:single|one)\s+(?:webgpt|chatgpt)\s+(?:review|opinion|answer|check)\b/i,
];
const roundtablePatterns = [
  /^\s*(?:\$ask|\/ask)\b[^\n]{0,80}\broundtable\b/i,
  /\b(?:run|use|convene|launch)\s+(?:an?\s+)?(?:ask\s+)?(?:roundtable|panel)\b/i,
  /\b(?:need|needs|required|require)\s+(?:an?\s+)?(?:roundtable|panel|deliberation)\b/i,
  /\b(?:architecture|policy|protocol|roadmap|milestone|release gate|phase boundary|go\/no-go)\b[^.\n]{0,140}\b(?:decision|tradeoff|recommendation|next steps|plan)\b/i,
  /\b(?:next steps|what should we do next|where do we go from here)\b[^.\n]{0,160}\b(?:strategic|unclear|tradeoff|milestone|major|many options|multiple paths|high stakes)\b/i,
];
const competePatterns = [
  /^\s*(?:\$ask|\/ask)\b[^\n]{0,80}\b(?:compete|competition|bakeoff)\b/i,
  /\b(?:run|use|launch)\s+(?:an?\s+)?(?:ask\s+)?(?:compete|competition|bakeoff|tournament)\b/i,
  /\b(?:choose|pick|select)\s+(?:the\s+)?(?:best|winner|implementation|approach|candidate)\b/i,
  /\b(?:multiple|several|competing|alternative)\s+(?:implementations|approaches|patches|designs|candidates|solutions)\b/i,
];
const thrashPatterns = [
  /\b(?:thrash(?:ing)?|spiral(?:ing)?|retry loop|keeps failing|same failure|repeated failures?|two focused attempts|third attempt|attempts? exhausted|not making progress)\b/i,
  /\b(?:I|we|agent|workflow|task|run)\s+(?:am|are|is|was|were)?\s*stuck\b/i,
  /\b(?:tried|attempted|retried)\b[^.\n]{0,120}\b(?:again|twice|multiple times|still fails?|same error|no progress)\b/i,
  /\b(?:side quests?|violat(?:e|ed|ing)\s+(?:the\s+)?immutable goal|self[- ]serving\s+(?:unit\s+)?tests?|tests?\s+(?:over|for)\s+(?:my|your|its|our)\s+own\s+code|proof\s+that\s+passes\s+(?:immediately|before\s+the\s+fix)|work(?:ing)?\s+(?:beside|around)\s+(?:the\s+)?blocker)\b/i,
];
const nextStepPatterns = [
  /\b(?:next steps?|what should we do next|where do we go from here|which path|which approach|how should we proceed)\b/i,
];
const milestonePatterns = [
  /\b(?:milestone|phase boundary|release gate|go\/no-go|architecture decision|policy decision|major decision|roadmap)\b/i,
];
const mvpFirstPatterns = [
  /\b(?:mvp[- ]first|mvp\s*\/|mvp directory|isolated\s+(?:mvp|challenge|proof|spike|seam)|prove\s+(?:the\s+)?(?:smallest|hard\s+part|seam)|proof[- ]of[- ]concept|poc)\b/i,
  /\b(?:before|prior to)\s+(?:implementing|implementation|the plan|broad edits?)\b[^.\n]{0,140}\b(?:mvp|isolated|proof|challenge|seam)\b/i,
  /\b(?:mvp|isolated|proof|challenge|seam)\b[^.\n]{0,140}\b(?:before|prior to)\s+(?:implementing|implementation|the plan|broad edits?)\b/i,
];

const explicitCompete = matchesAny(combined, competePatterns);
const explicitRoundtable = matchesAny(combined, roundtablePatterns);
const explicitWebgpt = matchesAny(combined, askWebgptPatterns);
const broadErrorFastSingle = matchesAny(combined, broadErrorFastSinglePatterns);
const earlySuccessfulEvidenceText = observations
  .filter((obs) => obs && obs.phase === 'result' && obs.ok === true)
  .map((obs) => `${obs.kind || ''}\n${obs.toolName || ''}\n${obs.command || obs.input?.command || ''}`)
  .join('\n');
const triageOrTauAlreadySatisfied = /\btriage_error\b|\b(?:skills\/triage-error\/run\.sh|triage-error\/run\.sh|\.\/run\.sh)\s+(?:classify|triage)\b|\btau\.dag_contract\.v1\b|\btau\s+dag-run\b/i.test(earlySuccessfulEvidenceText);
const thrashing = matchesAny(combined, thrashPatterns);
const asksNextSteps = matchesAny(combined, nextStepPatterns);
const milestone = matchesAny(combined, milestonePatterns);
const mvpFirst = matchesAny(combined, mvpFirstPatterns);
const concreteCandidates = /\b(?:candidate|option|approach|implementation|patch|solution)s?\s*(?:A|B|1|2|one|two|:)|\b(?:two|2|three|3|multiple|several|competing|alternative)\s+(?:candidate|option|approach|implementation|patch|solution)s?\b/i.test(combined);

const route = {
  memory_required: substantive,
  brave_required: false,
  dogpile_required: false,
  tau_or_triage_required: false,
  ask_webgpt_required: false,
  ask_fast_single_required: false,
  ask_roundtable_required: false,
  ask_compete_required: false,
  mvp_required: false,
};

route.dogpile_required = substantive && !metaRoutingQuestion && matchesAny(combined, broadResearchPatterns);
route.brave_required = substantive && !metaRoutingQuestion && !route.dogpile_required && matchesAny(combined, narrowResearchPatterns);
route.tau_or_triage_required = substantive && matchesAny(assistant, blockedOrErrorPatterns);
route.mvp_required = substantive && !metaRoutingQuestion && mvpFirst;
route.ask_compete_required = substantive && !metaRoutingQuestion && (explicitCompete || (thrashing && concreteCandidates));
route.ask_fast_single_required = substantive && !metaRoutingQuestion && !route.ask_compete_required && broadErrorFastSingle && !triageOrTauAlreadySatisfied;
route.ask_roundtable_required = substantive && !metaRoutingQuestion && !route.ask_compete_required && (explicitRoundtable || (!route.ask_fast_single_required && ((thrashing && !route.mvp_required) || milestone || (asksNextSteps && /\b(?:strategic|unclear|tradeoff|major|policy|architecture|roadmap|milestone|many options|multiple paths|high stakes)\b/i.test(combined)))));
route.ask_webgpt_required = substantive && !metaRoutingQuestion && !route.ask_compete_required && !route.ask_roundtable_required && !route.ask_fast_single_required && explicitWebgpt;

const successful = observations.filter((obs) => obs && obs.phase === 'result' && obs.ok === true);
const called = observations.filter((obs) => obs && obs.phase === 'call');
const relevantKinds = ['memory', 'brave', 'dogpile', 'tau', 'triage_error', 'ask_webgpt', 'ask_fast_single', 'ask_roundtable', 'ask_compete', 'mvp', 'scan'];
const commandMatchers = [
  { kind: 'memory', pattern: /\b(?:skills\/memory\/run\.sh|\.\/run\.sh)\s+recall\b|\b(memory-agent|graph_memory).*\brecall\b|\bhttpx\b[\s\S]{0,200}\/(?:recall|answer|intent)\b|\b127\.0\.0\.1:8601\/(?:recall|answer|intent)\b|\bPOST\s+\/(?:recall|answer|intent)\b/i },
  { kind: 'mvp', pattern: /\b(?:mvp\/|\/mvp\/)[^\n]*(?:goal\.md|run\.sh|receipt\.json|manifest\.json)|\b(?:mkdir|find|test|ls)\b[^\n]*\bmvp\/|\bmvp\/[^\n]*\b(?:run\.sh|receipt\.json|goal\.md|manifest\.json)\b/i },
  { kind: 'ask_fast_single', pattern: /\b(?:skills\/ask\/run\.sh|ask\/run\.sh|\.\/run\.sh)\s+tau-dag\b[\s\S]{0,800}(?:^|\s)--handler\s+(?:claude-fable-low|gpt-5\.5-low|[^\s]*(?:qwen|kimi|deepseek|glm)[^\s]*-low)\b/im },
  { kind: 'ask_compete', pattern: /\b(?:skills\/ask\/run\.sh|ask\/run\.sh|\.\/run\.sh)\s+compete\b|(?:^|\s)--dag-template\s+compete\b|(?:^|\s)--pattern\s+compete\b/im },
  { kind: 'ask_roundtable', pattern: /\b(?:skills\/ask\/run\.sh|ask\/run\.sh|\.\/run\.sh)\s+tau-dag\b[\s\S]{0,600}(?:^|\s)(?:--dag-template\s+roundtable|--pattern\s+roundtable|--topology\s+concurrent)\b|\b(?:skills\/ask\/run\.sh|ask\/run\.sh|\.\/run\.sh)\s+ask\b[\s\S]{0,300}(?:^|\s)--roundtable\b/im },
  { kind: 'ask_webgpt', pattern: /\b(?:skills\/ask\/run\.sh|ask\/run\.sh|\.\/run\.sh)\s+(?:webgpt|chatgpt)\b|\b(?:skills\/ask\/run\.sh|ask\/run\.sh|\.\/run\.sh)\s+tau-dag\b[\s\S]{0,400}(?:^|\s)--handler\s+webgpt\b|\b(?:skills\/ask\/run\.sh|ask\/run\.sh|\.\/run\.sh)\s+one-shot\b[\s\S]{0,400}(?:^|\s)--handler\s+webgpt\b/im },
  { kind: 'brave', pattern: /\b(?:skills\/brave-search\/run\.sh|brave_search\.py|\.\/run\.sh)\s+(?:web|context|summarize|local)\b/i },
  { kind: 'dogpile', pattern: /\b(?:skills\/dogpile\/run\.sh|dogpile\/run\.sh|\.\/run\.sh)\s+search\b/i },
  { kind: 'triage_error', pattern: /\b(?:skills\/triage-error\/run\.sh|triage-error\/run\.sh|\.\/run\.sh)\s+(?:classify|triage)\b/i },
  { kind: 'tau', pattern: /\b(?:skills\/tau\/run\.sh|tau\/run\.sh|uv\s+run\s+tau)\b|\btau\.dag_contract\.v1\b|\btau\s+dag-run\b/i },
];
function observationCommand(obs) { return String(obs?.command || obs?.input?.command || ''); }
function observationMatches(obs) {
  const kind = String(obs?.kind || 'other');
  const toolName = String(obs?.toolName || '');
  const command = observationCommand(obs);
  const haystack = `${toolName}\n${command}`;
  const matches = [];
  if (/^(read|grep|find|ls)$/i.test(toolName)) matches.push({ kind: 'scan', index: 0, rank: relevantKinds.indexOf('scan') });
  if (/\b(?:rg|grep|find|ls)\b\s+/i.test(command)) matches.push({ kind: 'scan', index: command.search(/\b(?:rg|grep|find|ls)\b\s+/i), rank: relevantKinds.indexOf('scan') });
  commandMatchers.forEach((matcher, rank) => {
    const match = matcher.pattern.exec(haystack);
    if (match) matches.push({ kind: matcher.kind, index: match.index, rank });
  });
  if (relevantKinds.includes(kind) && !matches.some((match) => match.kind === kind)) {
    matches.push({ kind, index: Number.MAX_SAFE_INTEGER, rank: relevantKinds.indexOf(kind) });
  }
  matches.sort((a, b) => a.index - b.index || a.rank - b.rank);
  const seen = new Set();
  return matches.filter((match) => {
    if (seen.has(match.kind)) return false;
    seen.add(match.kind);
    return true;
  });
}
function has(kind) { return successful.some((obs) => observationMatches(obs).some((match) => match.kind === kind)); }
function firstRelevantKind() {
  for (const obs of called) {
    const match = observationMatches(obs).find((entry) => relevantKinds.includes(entry.kind));
    if (match) return match.kind;
  }
  return null;
}

const evidence = {
  memory: has('memory'),
  brave: has('brave'),
  dogpile: has('dogpile'),
  tau: has('tau'),
  triage_error: has('triage_error'),
  ask_webgpt: has('ask_webgpt'),
  ask_fast_single: has('ask_fast_single'),
  ask_roundtable: has('ask_roundtable'),
  ask_compete: has('ask_compete'),
  mvp: has('mvp'),
  first_relevant_kind: firstRelevantKind(),
};

const failures = [];
if (route.memory_required && !evidence.memory) failures.push('missing_memory_recall_gate');
if (route.memory_required && evidence.first_relevant_kind && evidence.first_relevant_kind !== 'memory') failures.push('memory_recall_not_first_gate');
if (route.brave_required && !(evidence.brave || evidence.dogpile)) failures.push('missing_brave_search_gate');
if (route.dogpile_required && !evidence.dogpile) failures.push('missing_dogpile_gate');
if (route.tau_or_triage_required && !(evidence.tau || evidence.triage_error || evidence.ask_roundtable || evidence.ask_compete)) failures.push('missing_tau_or_triage_error_gate');
if (route.ask_webgpt_required && !evidence.ask_webgpt) failures.push('missing_ask_webgpt_gate');
if (route.ask_fast_single_required && !evidence.ask_fast_single) failures.push('missing_ask_fast_single_gate');
if (route.ask_roundtable_required && !evidence.ask_roundtable) failures.push('missing_ask_roundtable_gate');
if (route.ask_compete_required && !evidence.ask_compete) failures.push('missing_ask_compete_gate');
if (route.mvp_required && !evidence.mvp) failures.push('missing_mvp_isolated_challenge_gate');

const decision = failures.length ? 'reject' : 'pass';
const reason_codes = failures.length ? failures : ['research_route_gates_satisfied'];
const result = {
  schema: 'pi_research_gate.check.v1',
  checker_version: CHECKER_VERSION,
  decision,
  reason_codes,
  route,
  evidence,
  signals: { explicit_webgpt: explicitWebgpt, explicit_roundtable: explicitRoundtable, explicit_compete: explicitCompete, broad_error_fast_single: broadErrorFastSingle, thrashing, asks_next_steps: asksNextSteps, milestone, mvp_first: mvpFirst, concrete_candidates: concreteCandidates, status_question: statusQuestion, meta_routing_question: metaRoutingQuestion },
  counts: { observations: observations.length, successful: successful.length },
};
console.log(JSON.stringify(result, null, 2));
if (decision === 'reject') process.exit(1);
