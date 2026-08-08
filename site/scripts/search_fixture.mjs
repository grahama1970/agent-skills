#!/usr/bin/env node
// Capability-search acceptance fixture (#1292, webgpt review item 6).
// Exercises the SHIPPED ranking core (lib/search-core.mjs) over the real
// catalog and measures the review's acceptance gates. Exit non-zero on any
// gate failure so CI/local runs fail closed instead of asserting quality.
//
//   node scripts/search_fixture.mjs
//
// Gates:
//   G1  exact project/skill names rank #1 ......... require 100%
//   G2  acceptable result in top 3 (all queries) .. require >= 90%
//   G3  exact & alias hits never marked fuzzed ..... require 100%
//   G4  nonsense queries -> honest no-match ........ require 100%

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import MiniSearch from 'minisearch';
import { makeIndex, runSearch } from '../lib/search-core.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const catalog = JSON.parse(readFileSync(resolve(here, '../catalog.json'), 'utf8'));
const index = makeIndex(MiniSearch, catalog.documents);

// kind: 'name'  -> query is an exact name; must rank #1 and never be fuzzed
//       'alias' -> alias/problem phrase; acceptable id must be top-3, not fuzzed
//       'typo'  -> misspelling; acceptable id must be top-3 (fuzzy allowed)
//       'none'  -> nonsense; must return zero hits (honest no-confident-match)
// `want` is the acceptable doc name, or an array of acceptable names (any one
// in the top-3 satisfies the query). For kind 'name' the FIRST acceptable name
// must rank #1. Matched case-insensitively against hit.name.
const FIX = [
  // --- exact names (projects) ---
  // "tau" is a real *skill*; the *project* is "t'au". Both are correct answers.
  ['tau', 'name', 'tau'],
  ["t'au", 'name', "t'au"],
  ['battle', 'name', 'battle'],
  ['surf', 'name', 'surf'],
  ['persona-dream', 'name', 'persona-dream'],
  ['extractor', 'name', 'extractor'],
  ['dogpile', 'name', 'dogpile'],
  ['watch', 'name', 'watch'],
  ['scillm', 'name', 'scillm'],
  ['debugger', 'name', 'debugger'],
  // --- exact names (skills) ---
  ['ask', 'name', 'ask'],
  ['arxiv', 'name', 'arxiv'],
  ['align', 'name', 'align'],
  ['anvil', 'name', 'anvil'],
  ['argue', 'name', 'argue'],
  ['assess', 'name', 'assess'],
  ['analytics', 'name', 'analytics'],
  ['brave-search', 'name', 'brave-search'],
  ['browser-oracle', 'name', 'browser-oracle'],
  ['checkpoint', 'name', 'checkpoint'],
  ['classifier-lab', 'name', 'classifier-lab'],
  ['bootcamp', 'name', 'bootcamp'],
  ['benchmark-models', 'name', 'benchmark-models'],
  ['agent-inbox', 'name', 'agent-inbox'],
  ['agent-status', 'name', 'agent-status'],
  ['agentic-evals', 'name', 'agentic-evals'],
  ['agents-registry', 'name', 'agents-registry'],
  ['animation-vocabulary', 'name', 'animation-vocabulary'],
  ['apple-design', 'name', 'apple-design'],
  ['assistant', 'name', 'assistant'],
  ['batch-quality', 'name', 'batch-quality'],
  ['batch-report', 'name', 'batch-report'],
  ['ccopy', 'name', 'ccopy'],
  ['chutes-call', 'name', 'chutes-call'],
  ['best-practices-python', 'name', 'best-practices-python'],
  ['best-practices-react', 'name', 'best-practices-react'],
  ['best-practices-rust', 'name', 'best-practices-rust'],
  ['best-practices-d3', 'name', 'best-practices-d3'],
  ['best-practices-roundtable', 'name', 'best-practices-roundtable'],
  ['best-practices-security', 'name', 'best-practices-security'],
  ['best-practices-arangodb', 'name', 'best-practices-arangodb'],
  ['best-practices-tau-dag', 'name', 'best-practices-tau-dag'],
  ['best-practices-competition', 'name', 'best-practices-competition'],
  ['analyze-elf', 'name', 'analyze-elf'],
  ['assistant-lab', 'name', 'assistant-lab'],
  // --- alias / problem phrases (must reach the right project, not fuzzed) ---
  ['red team', 'alias', 'battle'],
  ['adversarial', 'alias', 'battle'],
  ['exploit', 'alias', 'battle'],
  ['security testing', 'alias', 'battle'],
  ['agent harness', 'alias', "t'au"],
  ['agent orchestration', 'alias', "t'au"],
  ['browser agents', 'alias', "t'au"],
  ['document extraction', 'alias', ['extractor', 'pdf-lab']],
  ['pdf', 'alias', ['extractor', 'pdf-lab', 'create-annotated-pdf', 'debug-pdf']],
  ['ocr', 'alias', 'extractor'],
  ['compliance', 'alias', ['Compliance, security & governance', 'sparta explorer']],
  ['governance', 'alias', ['Compliance, security & governance', 'sparta explorer']],
  ['audit', 'alias', ['sparta explorer', 'Compliance, security & governance']],
  ['persona', 'alias', 'persona-dream'],
  ['voice', 'alias', ['persona-dream', 'voice-lab', 'learn-voice', 'train-voice']],
  ['rag memory', 'alias', 'persona-dream'],
  // --- typos (fuzzy recovery allowed) ---
  ['debuger', 'typo', 'debugger'],
  ['extracter', 'typo', 'extractor'],
  ['persona dreem', 'typo', 'persona-dream'],
  ['complience', 'typo', ['Compliance, security & governance', 'sparta explorer']],
  ['adversarail', 'typo', 'battle'],
  ['brave serch', 'typo', 'brave-search'],
  ['browserr-oracle', 'typo', 'browser-oracle'],
  ['analyics', 'typo', 'analytics'],
  ['classifier lab', 'typo', 'classifier-lab'],
  ['benchmark modles', 'typo', 'benchmark-models'],
  // --- nonsense (must be honest no-confident-match) ---
  ['zzzxqqwv', 'none', null],
  ['qwertyuiop', 'none', null],
  ['xkcd9999zz', 'none', null],
  ['asdfghjklzxcv', 'none', null],
  ['blorptquux', 'none', null],
];

// Scout-conversion fixture (webgpt review, Criterion 4): a visitor describes a
// PROBLEM in natural language and must land on the right PROJECT — the actual
// conversion promise, not exact-name retrieval. `want` = acceptable project
// name(s); the expected project must appear in the top-3 PROJECT-type results.
const SCOUT = [
  ['my agent forgets previous decisions', ['persona-dream']],
  ['prove which browser tab an agent acted in', ['surf']],
  ['adversarially test an agent', ['battle']],
  ['red team an ai system', ['battle']],
  ['extract evidence from messy pdfs', ['extractor']],
  ['trace compliance claims back to evidence', ['sparta explorer']],
  ['orchestrate several agent workers safely', ["t'au"]],
  ['understand what was on screen at an exact moment', ['watch']],
  ['use multiple model providers consistently', ['scillm']],
  ['inspect runtime truth before patching a bug', ['debugger']],
  ['research across github arxiv and the web', ['dogpile']],
  ['a workflow reports success without evidence', ["t'au", 'surf']],
];

const norm = (s) => (s ?? '').toLowerCase();
let g1n = 0, g1d = 0;   // exact name #1
let g2n = 0, g2d = 0;   // acceptable in top-3 (all non-'none')
let g3n = 0, g3d = 0;   // exact/alias not fuzzed
let g4n = 0, g4d = 0;   // nonsense -> empty
const failures = [];

for (const [q, kind, want] of FIX) {
  const { hits, fuzzed } = runSearch(index, q);
  const names = hits.map((h) => norm(h.name));
  const top1 = names[0];
  const accept = (Array.isArray(want) ? want : [want]).map(norm);
  const inTop3 = want != null && names.slice(0, 3).some((n) => accept.includes(n));

  if (kind === 'none') {
    g4d++;
    if (hits.length === 0) g4n++;
    else failures.push(`G4 "${q}": expected no-match, got ${hits.length} (top ${top1})`);
    continue;
  }

  // G2 applies to every query that names an acceptable result.
  g2d++;
  if (inTop3) g2n++;
  else failures.push(`G2 "${q}" (${kind}): none of [${accept.join(', ')}] in top-3 [${names.slice(0, 3).join(', ')}]`);

  if (kind === 'name') {
    g1d++;
    // For an exact-name query the first acceptable name must rank #1.
    if (top1 === accept[0]) g1n++;
    else failures.push(`G1 "${q}": expected #1 "${accept[0]}", got "${top1}"`);
  }

  if (kind === 'name' || kind === 'alias') {
    g3d++;
    if (!fuzzed) g3n++;
    else failures.push(`G3 "${q}" (${kind}): matched but flagged fuzzed`);
  }
}

const pct = (n, d) => (d ? ((100 * n) / d).toFixed(1) : '—');
const line = (label, n, d, need, ok) =>
  `${ok ? 'PASS' : 'FAIL'}  ${label}: ${n}/${d} (${pct(n, d)}%)  need ${need}`;

// G5 — scout conversion: a natural-language problem lands on the right PROJECT
// in the top-3 project-type results.
let g5n = 0, g5d = 0;
for (const [q, want] of SCOUT) {
  g5d++;
  const { hits } = runSearch(index, q);
  const projects = hits.filter((h) => h.type === 'project').map((h) => norm(h.name));
  const accept = want.map(norm);
  if (projects.slice(0, 3).some((n) => accept.includes(n))) g5n++;
  else failures.push(`G5 "${q}": none of [${accept.join(', ')}] in top-3 projects [${projects.slice(0, 3).join(', ') || 'none'}]`);
}

const G1 = g1n === g1d;
const G2 = g2d > 0 && g2n / g2d >= 0.9;
const G3 = g3n === g3d;
const G4 = g4n === g4d;
const G5 = g5d > 0 && g5n / g5d >= 0.9;

console.log(`capability-search fixture — ${FIX.length + SCOUT.length} queries over ${catalog.documents.length} docs\n`);
console.log(line('G1 exact names rank #1 ', g1n, g1d, '100%', G1));
console.log(line('G2 acceptable in top-3 ', g2n, g2d, '>=90%', G2));
console.log(line('G3 exact/alias not fuzzed', g3n, g3d, '100%', G3));
console.log(line('G4 nonsense -> no-match', g4n, g4d, '100%', G4));
console.log(line('G5 scout problem->project', g5n, g5d, '>=90%', G5));

if (failures.length) {
  console.log(`\n${failures.length} failing case(s):`);
  for (const f of failures) console.log('  - ' + f);
}

const ok = G1 && G2 && G3 && G4 && G5;
console.log(`\n${ok ? 'OK: all gates pass' : 'FAIL: search does not meet the acceptance bar'}`);
process.exit(ok ? 0 : 1);
