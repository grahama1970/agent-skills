// API client for embry-memory FastAPI at localhost:8601
// Vite proxy: /memory/* → localhost:8601/*
// Fails loudly — no silent fallback to mock data.

const MEMORY_BASE = '/memory';

export class MemoryServiceError extends Error {
  endpoint: string;
  statusCode?: number;

  constructor(endpoint: string, statusCode?: number, cause?: unknown) {
    const msg = statusCode
      ? `Memory service ${endpoint} returned ${statusCode}`
      : `Memory service ${endpoint} unreachable`;
    super(msg, { cause });
    this.name = 'MemoryServiceError';
    this.endpoint = endpoint;
    this.statusCode = statusCode;
  }
}

async function memoryFetch<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${MEMORY_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new MemoryServiceError(path, res.status);
  return res.json();
}

// --- Response types ---

export interface RecallResult {
  results: Array<{
    key: string;
    score: number;
    content: string;
    metadata: Record<string, unknown>;
  }>;
  total: number;
}

export interface LearnResult {
  key: string;
  status: string;
}

export interface ClarifyResult {
  answer: string;
  confidence: number;
  sources: string[];
}

export interface ListResult {
  documents: Array<{
    key: string;
    content: string;
    metadata: Record<string, unknown>;
  }>;
  total: number;
}

export interface AnalyticsResult {
  query: string;
  result: unknown;
  duration_ms: number;
}

export interface TaxonomyQueryResult {
  tags: Array<{
    text: string;
    category: string;
    confidence: number;
  }>;
}

export interface TaxonomyCoverageResult {
  total_documents: number;
  tagged_documents: number;
  coverage_pct: number;
  categories: Record<string, number>;
}

export interface HealthResult {
  status: string;
  ok?: boolean;
  memory_db_connected?: boolean;
  version?: string;
  uptime_seconds?: number;
  collections?: string[];
}

export interface StoreResult {
  key: string;
  status: string;
}

// --- API functions ---

export async function recallDocuments(
  query: string,
  collection?: string,
): Promise<RecallResult> {
  return memoryFetch<RecallResult>('/recall', {
    q: query,
    ...(collection !== undefined ? { collection } : {}),
    top_k: 50,
  });
}

export async function learnDocument(
  content: string,
  metadata: Record<string, unknown>,
): Promise<LearnResult> {
  return memoryFetch<LearnResult>('/learn', { content, ...metadata });
}

export async function clarifyQuestion(
  question: string,
  context: Record<string, unknown>,
): Promise<ClarifyResult> {
  return memoryFetch<ClarifyResult>('/clarify', { question, context });
}

export async function listDocuments(
  collection: string,
  limit?: number,
  offset?: number,
): Promise<ListResult> {
  const body: Record<string, unknown> = { collection, limit: limit ?? 100 };
  if (offset !== undefined && offset > 0) body.offset = offset;
  return memoryFetch<ListResult>('/list', body);
}

export async function runAnalytics(query: string): Promise<AnalyticsResult> {
  return memoryFetch<AnalyticsResult>('/analytics/run', { q: query });
}

export async function queryTaxonomy(
  text: string,
  scope?: string,
): Promise<TaxonomyQueryResult> {
  return memoryFetch<TaxonomyQueryResult>('/taxonomy/query', {
    text,
    ...(scope !== undefined ? { scope } : {}),
  });
}

export async function getTaxonomyCoverage(): Promise<TaxonomyCoverageResult> {
  return memoryFetch<TaxonomyCoverageResult>('/taxonomy/coverage', {});
}

export async function checkHealth(): Promise<HealthResult> {
  const res = await fetch(`${MEMORY_BASE}/health`);
  if (!res.ok) throw new MemoryServiceError('/health', res.status);
  return res.json();
}

export async function storeDocument(
  key: string,
  value: Record<string, unknown>,
): Promise<StoreResult> {
  return memoryFetch<StoreResult>('/store', { key, value });
}
