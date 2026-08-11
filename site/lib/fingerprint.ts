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

const ARCHIVED_FINGERPRINTS: FingerprintRecord[] = [
  {
    schema: 'grahama.public_fingerprint.v1',
    canary: 'GRAHAMA_PUBLIC_FINGERPRINT_REVIEW_V1',
    sourceCommit: '3e02ea1840ea482f45b9297d2be929af6f7dd62e',
    sourceCommitShort: '3e02ea1840ea',
    candidateFingerprint: 'ead6aa31d8b92d4308182b30065c7fddb33379c2a6d7106496bf619a564538cc',
    generatedAt: '2026-08-11T18:06:17Z',
    manifestSourceCommit: 'c6ef540f47',
    manifestSha256: null,
    importantHashes: {},
    reviewUnits: REVIEW_UNITS,
  },
  {
    schema: 'grahama.public_fingerprint.v1',
    canary: 'GRAHAMA_PUBLIC_FINGERPRINT_REVIEW_V1',
    sourceCommit: '12826f5defe0cf81e91310242ee0e7efc29f7076',
    sourceCommitShort: '12826f5defe',
    candidateFingerprint: '5e9c2de825cae0d46659b77f584e7e5194d80fa0815311f69af837f377ce5d00',
    generatedAt: '2026-08-11T17:59:33Z',
    manifestSourceCommit: '12826f5defe0cf81e91310242ee0e7efc29f7076',
    manifestSha256: null,
    importantHashes: {},
    reviewUnits: REVIEW_UNITS,
  },
  {
    schema: 'grahama.public_fingerprint.v1',
    canary: 'GRAHAMA_PUBLIC_FINGERPRINT_REVIEW_V1',
    sourceCommit: 'bc27beac7d5dda504beef9d07dce448f91796956',
    sourceCommitShort: 'bc27beac7d5d',
    candidateFingerprint: '09e861bf69d2cfc7faaf2b220c342a7a2e92f9eb8e6b8e7d9c3981c86d16ce31',
    generatedAt: '2026-08-11T17:37:19Z',
    manifestSourceCommit: 'bc27beac7d5dda504beef9d07dce448f91796956',
    manifestSha256: null,
    importantHashes: {},
    reviewUnits: REVIEW_UNITS,
  },
  {
    schema: 'grahama.public_fingerprint.v1',
    canary: 'GRAHAMA_PUBLIC_FINGERPRINT_REVIEW_V1',
    sourceCommit: '7ba43e387d734b2a4f007e580bd18dd7d7b3c705',
    sourceCommitShort: '7ba43e387d73',
    candidateFingerprint: 'd7c890171e51e4803d618df23aa7ffb63657466a710cf7834ea027823dff8aee',
    generatedAt: '2026-08-11T17:29:48Z',
    manifestSourceCommit: '7ba43e387d734b2a4f007e580bd18dd7d7b3c705',
    manifestSha256: null,
    importantHashes: {},
    reviewUnits: REVIEW_UNITS,
  },
  {
    schema: 'grahama.public_fingerprint.v1',
    canary: 'GRAHAMA_PUBLIC_FINGERPRINT_REVIEW_V1',
    sourceCommit: '4d6e08ef83261b30afe8eb0c97d589a0d48450f5',
    sourceCommitShort: '4d6e08ef8326',
    candidateFingerprint: '9f605939891fd19e40e2a2d6e36ef0cbacf1ef1b6ec507236f78219d88c43298',
    generatedAt: '2026-08-11T17:18:20Z',
    manifestSourceCommit: '4d6e08ef83261b30afe8eb0c97d589a0d48450f5',
    manifestSha256: null,
    importantHashes: {},
    reviewUnits: REVIEW_UNITS,
  },
];

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
  return getFingerprintRecords().flatMap((record) => [
    record.candidateFingerprint,
    record.candidateFingerprint.slice(0, 16),
    record.sourceCommit,
    record.sourceCommitShort,
  ]);
}

export function getFingerprintRecords() {
  const records = [getFingerprintRecord(), ...ARCHIVED_FINGERPRINTS];
  const seen = new Set<string>();
  return records.filter((record) => {
    const key = `${record.sourceCommit}:${record.candidateFingerprint}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function getFingerprintRecordForId(requestedId?: string) {
  if (!requestedId) return getFingerprintRecord();
  return (
    getFingerprintRecords().find((record) =>
      [
        record.candidateFingerprint,
        record.candidateFingerprint.slice(0, 16),
        record.sourceCommit,
        record.sourceCommitShort,
      ].includes(requestedId),
    ) ?? getFingerprintRecord()
  );
}
