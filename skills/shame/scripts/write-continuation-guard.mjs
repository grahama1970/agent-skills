#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';

const args = process.argv.slice(2);
function take(name, fallback = '') {
  const index = args.indexOf(name);
  if (index < 0) return fallback;
  return args[index + 1] || fallback;
}
function has(name) { return args.includes(name); }

const repo = take('--repo') || take('-R');
const issue = take('--issue');
const target = take('--target');
const nextCommand = take('--next-command', 'Continue the ticketed goal until this issue is closed or explicitly blocked.');
const out = take('--out', process.env.LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE || '/mnt/storage12tb/skills/shame/continuation-guard/current.json');

if (!repo || !issue || !target) {
  console.error('usage: write-continuation-guard.mjs --repo owner/repo --issue N --target PATH [--next-command CMD] [--out PATH]');
  process.exit(2);
}

const gh = spawnSync('gh', ['issue', 'view', issue, '--repo', repo, '--json', 'number,state,labels,url,title'], {
  encoding: 'utf8',
  timeout: 30_000,
});
if (gh.status !== 0) {
  console.error(gh.stderr || gh.stdout || 'gh issue view failed');
  process.exit(1);
}
let issueData;
try {
  issueData = JSON.parse(gh.stdout || '{}');
} catch (error) {
  console.error(`gh issue view returned non-JSON: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
}
const labels = Array.isArray(issueData.labels) ? issueData.labels.map((label) => String(label?.name || label)).filter(Boolean) : [];
const closed = String(issueData.state || '').toUpperCase() === 'CLOSED';
const doc = {
  schema: 'lazy_report_shame.continuation_guard.v1',
  generated_by: 'skills/shame/scripts/write-continuation-guard.mjs',
  generated_at: new Date().toISOString(),
  active: !closed,
  target,
  tickets: [{
    ref: `${repo}#${issueData.number || issue}`,
    url: issueData.url || `https://github.com/${repo}/issues/${issue}`,
    state: issueData.state || 'UNKNOWN',
    labels,
    title: issueData.title || '',
    next_command: nextCommand,
  }],
  gates: [],
  obvious_next_steps: closed ? [] : [nextCommand],
};
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify(doc, null, 2) + '\n', 'utf8');
if (has('--json')) {
  console.log(JSON.stringify({ ok: true, out, active: doc.active, ticket: doc.tickets[0], target }, null, 2));
} else {
  console.log(out);
}
