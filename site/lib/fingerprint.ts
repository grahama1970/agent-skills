import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { execSync } from 'node:child_process';

const REVIEW_UNITS = [
  {
    id: 'home-default',
    url: '/',
    label: 'Homepage default path',
    question: 'Does the first visit explain the principal R&D practice without forcing repository literacy?',
  },
  {
    id: 'proof-method',
    url: '/how-proof-works',
    label: 'Proof method depth route',
    question: 'Can an inspector reach claim, evidence, boundary, and bounded judgment without hidden context?',
  },
  {
    id: 'explore-map',
    url: '/explore',
    label: 'Public project and skill explorer',
    question: 'Can a technical reviewer find public work, private boundaries, and source links deliberately?',
  },
  {
    id: 'ledger',
    url: '/ledger',
    label: 'Contract ledger',
    question: 'Can a contract inspector reach the full inventory as a depth surface rather than homepage clutter?',
  },
  {
    id: 'resume',
    url: '/resume',
    label: 'Calm resume lane',
    question: 'Can a hiring reviewer evaluate Graham quickly without entering the proof-workshop interface?',
  },
] as const;

type ReviewUnit = (typeof REVIEW_UNITS)[number];

export type FingerprintRecord = {
  schema: 'grahama.public_fingerprint.v1';
  canary: 'GRAHAMA_PUBLIC_FINGERPRINT_REVIEW_V1';
  sourceCommit: string;
  sourceCommitShort: string;
  candidateFingerprint: string;
  generatedAt: string | null;
  manifestSourceCommit: string | null;
  manifestSha256: string | null;
  importantHashes: Record<string, string | null>;
  reviewUnits: readonly ReviewUnit[];
};

function sitePath(...parts: string[]) {
  return path.join(process.cwd(), ...parts);
}

function readText(rel: string) {
  try {
    return fs.readFileSync(sitePath(rel), 'utf8');
  } catch {
    return null;
  }
}

function shaText(text: string | null) {
  if (text === null) return null;
  return crypto.createHash('sha256').update(text).digest('hex');
}

function readJson(rel: string) {
  const text = readText(rel);
  if (!text) return null;
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function gitValue(args: string[]) {
  try {
    return execSync(`git ${args.join(' ')}`, {
      cwd: path.resolve(process.cwd(), '..'),
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    return 'unknown';
  }
}

export function getFingerprintRecord(): FingerprintRecord {
  const sourceCommit = gitValue(['rev-parse', 'HEAD']);
  const sourceCommitShort = gitValue(['rev-parse', '--short=12', 'HEAD']);
  const manifestText = readText('build-manifest.json');
  const manifest = readJson('build-manifest.json');
  const importantHashes = {
    'build-manifest.json': shaText(manifestText),
    'content.json': shaText(readText('content.json')),
    'graph.json': shaText(readText('graph.json')),
    'research-map.json': shaText(readText('research-map.json')),
    'resume.json': shaText(readText('resume.json')),
    'app/page.tsx': shaText(readText('app/page.tsx')),
    'app/resume/page.tsx': shaText(readText('app/resume/page.tsx')),
    'app/how-proof-works/page.tsx': shaText(readText('app/how-proof-works/page.tsx')),
    'app/explore/page.tsx': shaText(readText('app/explore/page.tsx')),
    'app/ledger/page.tsx': shaText(readText('app/ledger/page.tsx')),
  };
  const payload = {
    sourceCommit,
    manifestSourceCommit: (manifest?.source_commit as string | undefined) ?? null,
    importantHashes,
    reviewUnits: REVIEW_UNITS.map(({ id, url }) => ({ id, url })),
  };
  const candidateFingerprint = crypto
    .createHash('sha256')
    .update(JSON.stringify(payload))
    .digest('hex');

  return {
    schema: 'grahama.public_fingerprint.v1',
    canary: 'GRAHAMA_PUBLIC_FINGERPRINT_REVIEW_V1',
    sourceCommit,
    sourceCommitShort,
    candidateFingerprint,
    generatedAt: new Date(0).toISOString(),
    manifestSourceCommit: (manifest?.source_commit as string | undefined) ?? null,
    manifestSha256: importantHashes['build-manifest.json'],
    importantHashes,
    reviewUnits: REVIEW_UNITS,
  };
}

export function getFingerprintIds() {
  const record = getFingerprintRecord();
  return [
    record.candidateFingerprint,
    record.candidateFingerprint.slice(0, 16),
    record.sourceCommit,
    record.sourceCommitShort,
  ];
}
