#!/usr/bin/env node
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const root = new URL('../src', import.meta.url).pathname;
const files = [];
function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path);
    else if (path.endsWith('.tsx')) files.push(path);
  }
}
walk(root);

const all = files.map((file) => [file, readFileSync(file, 'utf8')]);
const failures = [];

for (const [file, source] of all) {
  const rel = file.replace(`${root}/`, 'src/');
  if (source.split('\n').length > 400) failures.push(`${rel}: TSX file exceeds 400 lines`);
}

const joined = all.map(([, source]) => source).join('\n');
const required = [
  'data-qid="watchdog:refresh"',
  'data-qs-action="WATCHDOG_REFRESH_SNAPSHOT"',
  'data-qid="watchdog:filters"',
  'data-qs-action="WATCHDOG_SET_FILTER"',
  'data-qid="watchdog:detail"',
  'data-qs-action="WATCHDOG_OPEN_ROW"',
  'data-qid="watchdog:cards"',
  'data-qs-action="WATCHDOG_OPEN_CARD"',
  'title="Reload the latest project-watchdog UI snapshot JSON"',
];
for (const needle of required) {
  if (!joined.includes(needle)) failures.push(`missing required UI contract literal: ${needle}`);
}
if (!joined.includes('useRegisterAction({ qid:')) {
  failures.push('missing useRegisterAction registration');
}
if (!joined.includes('lg:hidden') || !joined.includes('hidden overflow-hidden') || !joined.includes('sticky top-0')) {
  failures.push('responsive/sticky table-card classes are missing');
}
if (!joined.includes('Tau React Flow viewer') || !joined.includes('Receipt chain')) {
  failures.push('Tau DAG / receipt-chain language is missing');
}

if (failures.length) {
  console.error(JSON.stringify({ ok: false, failures }, null, 2));
  process.exit(1);
}
console.log(JSON.stringify({ ok: true, files: files.length, checks: required.length + 4 }, null, 2));
