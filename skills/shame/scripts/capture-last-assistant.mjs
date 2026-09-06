#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';

const DEFAULT_OUT = process.env.LAZY_REPORT_SHAME_TRAINING_JSONL || '/mnt/storage12tb/skills/shame/training/classifier-feedback.jsonl';
const CONFIGURED_MEMORY_URL = process.env.MEMORY_SERVICE_URL || process.env.MEMORY_API_URL || '';
const DEFAULT_MEMORY_URL = CONFIGURED_MEMORY_URL.startsWith('unix://') ? 'http://127.0.0.1:8601' : (CONFIGURED_MEMORY_URL || 'http://127.0.0.1:8601');
const DEFAULT_MEMORY_COLLECTION = process.env.SHAME_MEMORY_COLLECTION || 'shame_training_examples';
const VERDICTS = new Set(['allow', 'reject', 'warn', 'needs_review']);
const LEGACY_LABEL_TO_RECORD = {
  false_positive: { verdict: 'allow', reasons: ['false_positive'] },
  false_negative: { verdict: 'reject', reasons: ['false_negative'] },
  good_status_report: { verdict: 'allow', reasons: ['good_status_report'] },
  commit_laundering: { verdict: 'reject', reasons: ['commit_laundering'] },
  jargon_no_status: { verdict: 'reject', reasons: ['jargon_no_status'] },
  needs_review: { verdict: 'needs_review', reasons: [] },
  reject: { verdict: 'reject', reasons: [] },
  allow: { verdict: 'allow', reasons: [] },
  warn: { verdict: 'warn', reasons: [] },
};

function usage(exitCode = 0) {
  console.log(`Usage:
  capture-last-assistant.mjs [--session FILE] [--entry-id ID] [--response-sha256 HASH]
                             [--verdict VERDICT] [--reason REASON ...] [--note TEXT] [--out FILE]
  capture-last-assistant.mjs --text TEXT [--verdict VERDICT] [--reason REASON ...]
  capture-last-assistant.mjs [--session FILE] --label LEGACY_LABEL [--note TEXT] [--out FILE]

Defaults:
  --session $PI_SESSION_FILE
  --verdict needs_review
  --out ${DEFAULT_OUT}
  --memory-url ${DEFAULT_MEMORY_URL}
  --memory-collection ${DEFAULT_MEMORY_COLLECTION}

Verdicts: allow, reject, warn, needs_review`);
  process.exit(exitCode);
}

function parseArgs(argv) {
  const opts = {
    session: process.env.PI_SESSION_FILE || '',
    entryId: '',
    responseSha256: '',
    text: '',
    verdict: 'needs_review',
    reasons: [],
    note: '',
    out: DEFAULT_OUT,
    memory: true,
    memoryUrl: DEFAULT_MEMORY_URL,
    memoryCollection: DEFAULT_MEMORY_COLLECTION,
    source: 'shame-skill-cli',
    synthetic: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') usage(0);
    if (arg === '--session') opts.session = argv[++i] || '';
    else if (arg === '--entry-id') opts.entryId = argv[++i] || '';
    else if (arg === '--response-sha256') opts.responseSha256 = argv[++i] || '';
    else if (arg === '--verdict') opts.verdict = (argv[++i] || '').toLowerCase().replaceAll('-', '_');
    else if (arg === '--reason') opts.reasons.push((argv[++i] || '').toLowerCase().replaceAll('-', '_'));
    else if (arg === '--note') opts.note = argv[++i] || '';
    else if (arg === '--out') opts.out = argv[++i] || '';
    else if (arg === '--text') opts.text = argv[++i] || '';
    else if (arg === '--memory') opts.memory = true;
    else if (arg === '--no-memory') opts.memory = false;
    else if (arg === '--memory-url') opts.memoryUrl = argv[++i] || '';
    else if (arg === '--memory-collection') opts.memoryCollection = argv[++i] || '';
    else if (arg === '--search-collection') opts.searchCollection = argv[++i] || '';
    else if (arg === '--source') opts.source = argv[++i] || opts.source;
    else if (arg === '--synthetic') opts.synthetic = true;
    else if (arg === '--label') {
      const label = (argv[++i] || '').toLowerCase().replaceAll('-', '_');
      if (!(label in LEGACY_LABEL_TO_RECORD)) throw new Error(`invalid --label ${label}; use --verdict plus --reason`);
      opts.verdict = LEGACY_LABEL_TO_RECORD[label].verdict;
      opts.reasons.push(...LEGACY_LABEL_TO_RECORD[label].reasons);
    } else throw new Error(`unknown argument: ${arg}`);
  }
  if (!opts.text && !opts.session) throw new Error('missing --text, or missing --session and PI_SESSION_FILE is not set');
  if (!VERDICTS.has(opts.verdict)) throw new Error(`invalid --verdict ${opts.verdict}; expected one of: ${[...VERDICTS].join(', ')}`);
  if (!opts.out) throw new Error('missing --out');
  if (opts.memory && !opts.memoryCollection) throw new Error('missing --memory-collection');
  if (opts.memory && !opts.memoryUrl) throw new Error('missing --memory-url');
  if (opts.synthetic && !opts.reasons.includes('synthetic_fixture')) opts.reasons.push('synthetic_fixture');
  opts.reasons = [...new Set(opts.reasons)].filter(Boolean);
  opts.memoryUrl = opts.memoryUrl.replace(/\/+$/, '').trim();
  opts.memoryCollection = opts.memoryCollection.trim();
  opts.source = opts.source.trim() || 'shame-skill-cli';
  opts.text = opts.text.trim();
  opts.note = opts.note.trim();
  opts.session = opts.session.trim();
  opts.responseSha256 = opts.responseSha256.trim();
  opts.entryId = opts.entryId.trim();
  opts.out = opts.out.trim();
  opts.verdict = opts.verdict.trim();
  if (opts.memoryCollection.startsWith('_')) throw new Error('memory collection must not be a system collection');
  if (!/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(opts.memoryCollection)) throw new Error(`unsafe memory collection name: ${opts.memoryCollection}`);
  return opts;
}

function contentToText(content) {
  if (typeof content === 'string') return content;
  if (!Array.isArray(content)) return '';
  return content.map((part) => {
    if (!part) return '';
    if (part.type === 'text' && typeof part.text === 'string') return part.text;
    if (typeof part.content === 'string') return part.content;
    return '';
  }).join('\n');
}

function sha256(value) {
  return 'sha256:' + createHash('sha256').update(value).digest('hex');
}

function sessionEntries(sessionFile) {
  const lines = readFileSync(sessionFile, 'utf8').split(/\n/).filter(Boolean);
  const entries = [];
  for (const line of lines) {
    let entry;
    try { entry = JSON.parse(line); } catch { continue; }
    const message = entry?.message;
    const role = message?.role;
    if ((role === 'assistant' || role === 'user') && entry?.type === 'message') {
      const text = contentToText(message.content);
      if (text.trim()) entries.push({ id: String(entry.id || 'unknown'), role, text });
    }
  }
  return entries;
}

function selectAssistant(sessionFile, opts) {
  if (opts.text) return { id: 'explicit-text', role: 'assistant', text: opts.text, userText: '' };
  const allEntries = sessionEntries(sessionFile);
  const entries = allEntries.filter((entry) => entry.role === 'assistant');
  if (!entries.length) throw new Error(`no assistant message found in ${sessionFile}`);
  let selected;
  let selectedIndex = -1;
  if (opts.entryId) {
    selectedIndex = allEntries.findIndex((entry) => entry.role === 'assistant' && entry.id === opts.entryId);
    selected = allEntries[selectedIndex];
  } else if (opts.responseSha256) {
    selectedIndex = allEntries.findIndex((entry) => entry.role === 'assistant' && sha256(entry.text) === opts.responseSha256);
    selected = allEntries[selectedIndex];
  } else {
    for (let i = allEntries.length - 1; i >= 0; i -= 1) {
      if (allEntries[i].role === 'assistant') {
        selectedIndex = i;
        selected = allEntries[i];
        break;
      }
    }
  }
  if (!selected) {
    const selector = opts.entryId ? `entry id ${opts.entryId}` : `response hash ${opts.responseSha256}`;
    throw new Error(`no assistant ${selector} found in ${sessionFile}`);
  }
  const previousUser = allEntries.slice(0, selectedIndex).reverse().find((entry) => entry.role === 'user');
  return { ...selected, userText: previousUser?.text || '' };
}

function appendDedup(example, outPath) {
  mkdirSync(dirname(outPath), { recursive: true });
  const existing = existsSync(outPath) ? readFileSync(outPath, 'utf8').split(/\n/).filter(Boolean) : [];
  const kept = existing.filter((line) => {
    try { return JSON.parse(line).example_id !== example.example_id; } catch { return true; }
  });
  kept.push(JSON.stringify(example));
  writeFileSync(outPath, kept.join('\n') + '\n', 'utf8');
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-caller-skill': 'shame' },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
  if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}: ${text.slice(0, 500)}`);
  return data;
}

async function storeMemory(example, opts) {
  const stored = await postJson(`${opts.memoryUrl}/store`, {
    collection: opts.memoryCollection,
    document: example,
  });
  const readBack = await postJson(`${opts.memoryUrl}/recall/by-keys`, {
    collection: opts.memoryCollection,
    keys: [example._key],
    key_field: '_key',
    return_fields: ['_key', 'schema', 'human_verdict', 'human_reasons', 'response_sha256'],
  });
  if (!Array.isArray(readBack.documents) || readBack.documents.length !== 1) {
    throw new Error(`memory read-back failed for ${opts.memoryCollection}/${example._key}`);
  }
  const result = { collection: opts.memoryCollection, key: example._key, stored_key: stored?._key || stored?.document?._key || example._key, read_back_count: readBack.documents.length };
  if (opts.searchCollection) {
    const shadowKey = `${example._key}_search`.slice(0, 254);
    const shadow = {
      _key: shadowKey,
      schema: 'lazy_report_shame.training_example_search.v1',
      kind: 'agent_status_shame_training_search_doc',
      problem: `Human-labeled agent status example: ${example.human_verdict} ${example.human_reasons.join(', ')}`,
      solution: example.retrieval_text,
      project: 'agent-skills',
      scope: 'agent-skills',
      example_ref: `${opts.memoryCollection}/${example._key}`,
      created_at: example.created_at,
      tags: example.tags,
      retrieval_text: example.retrieval_text,
    };
    await postJson(`${opts.memoryUrl}/store`, { collection: opts.searchCollection, document: shadow });
    const shadowBack = await postJson(`${opts.memoryUrl}/recall/by-keys`, {
      collection: opts.searchCollection,
      keys: [shadowKey],
      key_field: '_key',
      return_fields: ['_key', 'schema', 'example_ref'],
    });
    if (!Array.isArray(shadowBack.documents) || shadowBack.documents.length !== 1) {
      throw new Error(`search shadow read-back failed for ${opts.searchCollection}/${shadowKey}`);
    }
    result.search = { collection: opts.searchCollection, key: shadowKey, read_back_count: shadowBack.documents.length };
    const recallBody = {
      q: example.retrieval_text.slice(0, 200),
      scope: 'agent-skills',
      collections: [opts.searchCollection],
      tags: ['shame'],
      k: 10,
      threshold: 0.0,
    };
    // Same bounded index-visibility readback as the Pi extension; never repeat the write.
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const recall = await postJson(`${opts.memoryUrl}/recall`, recallBody);
      const items = Array.isArray(recall.items) ? recall.items : Array.isArray(recall.documents) ? recall.documents : [];
      result.recall_found = items.some((item) => item?._key === shadowKey);
      if (result.recall_found) break;
      if (attempt < 4) await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    if (!result.recall_found) throw new Error(`search recall did not return ${opts.searchCollection}/${shadowKey}`);
  }
  return result;
}

try {
  const opts = parseArgs(process.argv.slice(2));
  const assistant = selectAssistant(opts.session, opts);
  const responseHash = sha256(assistant.text);
  const exampleId = sha256(`${responseHash}\n${opts.verdict}\n${opts.reasons.join(',')}\n${opts.note}`);
  const exampleKey = exampleId.replace('sha256:', 'shame_').slice(0, 254);
  const example = {
    _key: exampleKey,
    schema: 'lazy_report_shame.training_example.v2',
    kind: 'agent_status_shame_training_example',
    example_id: exampleId,
    created_at: new Date().toISOString(),
    source: opts.source,
    source_skill: 'shame',
    human_verdict: opts.verdict,
    human_reasons: opts.reasons,
    classifier_label: opts.verdict === 'allow' ? 'acceptable_update' : 'bullshit_update',
    note: opts.note,
    synthetic: opts.synthetic,
    machine_decision: 'unknown',
    machine_reason_codes: [],
    checker_version: 'unknown',
    force_status: false,
    user_text: assistant.userText || '',
    assistant_text: assistant.text,
    assistant_entry_id: assistant.id,
    session_file: opts.session,
    turn_id: sha256(`${assistant.userText || ''}\n---\n${assistant.text}`),
    response_sha256: responseHash,
    tags: ['shame', 'classifier-training', `verdict:${opts.verdict}`, ...opts.reasons.map((reason) => `reason:${reason}`)],
    retrieval_text: [
      `verdict: ${opts.verdict}`,
      `reasons: ${opts.reasons.join(', ') || 'none'}`,
      opts.note ? `note: ${opts.note}` : '',
      assistant.userText ? `user: ${assistant.userText}` : '',
      `assistant: ${assistant.text}`,
    ].filter(Boolean).join('\n'),
  };
  appendDedup(example, opts.out);
  const memory = opts.memory ? await storeMemory(example, opts) : { skipped: true };
  console.log(JSON.stringify({ ok: true, out: opts.out, memory, human_verdict: opts.verdict, human_reasons: opts.reasons, assistant_entry_id: assistant.id, response_sha256: responseHash, example_id: exampleId }, null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
