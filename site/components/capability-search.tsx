'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import MiniSearch from 'minisearch';
import catalog from '@/catalog.json';

interface Doc {
  id: string;
  type: 'area' | 'project' | 'skill';
  name: string;
  slug?: string;
  area?: string;
  lens?: string;
  aliases?: string[];
  disciplines?: string[];
  question?: string;
  summary?: string;
  href?: string;
  visibility?: string;
  evidenceAccess?: string;
  category?: string;
}

const DOCS = catalog.documents as Doc[];

// Field-weighted BM25 (#1292): names and aliases dominate, prose supports.
const BOOST = { name: 4, aliases: 3, area: 2, question: 1.5, summary: 1.2, body: 0.6 };

function buildIndex() {
  const ms = new MiniSearch<Doc>({
    fields: ['name', 'aliases', 'area', 'disciplines', 'question', 'summary', 'body', 'category'],
    storeFields: ['type', 'name', 'slug', 'area', 'href', 'question', 'summary', 'visibility', 'evidenceAccess'],
    extractField: (doc, field) => {
      const v = (doc as unknown as Record<string, unknown>)[field];
      return Array.isArray(v) ? v.join(' ') : ((v as string) ?? '');
    },
  });
  ms.addAll(DOCS);
  return ms;
}

// Which field a hit matched, ranked, so we can tell the visitor *why* it matched.
const FIELD_RANK = ['name', 'aliases', 'area', 'question', 'disciplines', 'summary', 'body', 'category'];
const FIELD_LABEL: Record<string, string> = {
  name: 'the name',
  aliases: 'an alias',
  area: 'the area',
  question: 'the research question',
  disciplines: 'a discipline',
  summary: 'the description',
  body: 'the write-up',
  category: 'the category',
};

type Hit = Doc & { score: number; reason?: { terms: string; where: string } | null };

function reasonFor(r: { match?: Record<string, string[]>; terms?: string[] }) {
  const fields = new Set<string>();
  Object.values(r.match ?? {}).forEach((fs) => fs.forEach((f) => fields.add(f)));
  const top = FIELD_RANK.find((f) => fields.has(f));
  if (!top) return null;
  const terms = (r.terms ?? []).slice(0, 3).join(' ');
  return { terms, where: FIELD_LABEL[top] ?? top };
}

/**
 * Two-pass retrieval (#1292): precise first — exact/alias/prefix, no fuzz —
 * and only fall back to controlled fuzzy when the precise pass is thin. Short
 * codenames (tau, surf, kai) never fuzz. Exact/prefix hits always rank above
 * fuzzy ones, and every hit carries why it matched.
 */
function runSearch(index: MiniSearch<Doc>, q: string): { hits: Hit[]; fuzzed: boolean } {
  const precise = index.search(q, {
    boost: BOOST, prefix: true, fuzzy: false, combineWith: 'AND',
  });
  let raw = precise;
  let fuzzed = false;
  if (precise.length < 3) {
    // low confidence -> add a controlled fuzzy pass; never fuzz short tokens
    const loose = index.search(q, {
      boost: BOOST, prefix: true,
      fuzzy: (term) => (term.length > 4 ? 0.2 : false),
      combineWith: 'OR',
    });
    const seen = new Set(precise.map((r) => r.id));
    raw = [...precise, ...loose.filter((r) => !seen.has(r.id))]; // precise stays on top
    fuzzed = precise.length === 0;
  }
  const hits = raw.slice(0, 8).map((r) => ({
    ...(r as unknown as Doc),
    score: r.score,
    reason: reasonFor(r as { match?: Record<string, string[]>; terms?: string[] }),
  }));
  return { hits, fuzzed };
}

const EXAMPLES = [
  'voice agent that remembers',
  'red team',
  'compliance evidence',
  'which browser tab acted',
  'RAG extraction',
  'video generation',
];

// Client-style questions the placeholder rotates through, so a visitor sees the
// range of "does Graham have experience with X" this search actually answers.
const PROMPTS = [
  'a voice agent that remembers previous conversations',
  'generating compliance evidence from a control catalog',
  'extracting tables and figures from messy PDFs',
  'proving which browser tab an agent acted in',
  'red-teaming an adaptive adversary over many rounds',
  'reference-locked character generation for video',
  'a memory layer over ArangoDB and Qdrant',
];

/**
 * Capability search: a client types a problem, gets ranked real work back.
 * Retrieval only selects/ranks — every href and label comes from the
 * generated catalog (public/visibility-safe), never invented.
 */
export function CapabilitySearch() {
  const [query, setQuery] = useState('');
  const [promptIdx, setPromptIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const index = useMemo(buildIndex, []);

  // Rotate the placeholder question while the box is empty. Honours reduced
  // motion (stays on the first prompt) and pauses once the visitor types.
  useEffect(() => {
    if (query) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const id = window.setInterval(
      () => setPromptIdx((i) => (i + 1) % PROMPTS.length),
      3200,
    );
    return () => window.clearInterval(id);
  }, [query]);

  const q = query.trim();
  const { hits, fuzzed } = q ? runSearch(index, q) : { hits: [] as Hit[], fuzzed: false };

  return (
    <div className="capsearch" aria-label="Search the practice by problem">
      <p className="capsearch-intro">
        I gravitate to the experimental, hard-to-staff work — but this is about
        what <em>you</em> need. Describe a problem or a capability.
      </p>
      <label className="capsearch-label" htmlFor="capsearch-input">
        What interests you?
      </label>
      <input
        id="capsearch-input"
        ref={inputRef}
        className="capsearch-input"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        data-qid="search:input:capability"
        data-qs-action="SEARCH_CAPABILITY"
        title="Type a problem or capability to find matching projects and skills"
        placeholder={`e.g. ${PROMPTS[promptIdx]}`}
        autoComplete="off"
      />
      {!q && (
        <p className="capsearch-examples">
          try:{' '}
          {EXAMPLES.map((ex, i) => (
            <span key={ex}>
              {i > 0 && <span aria-hidden="true"> · </span>}
              <button
                type="button"
                className="capsearch-example"
                data-qid={`search:example:${i}`}
                data-qs-action="SEARCH_EXAMPLE"
                title={`Search for "${ex}"`}
                onClick={() => {
                  setQuery(ex);
                  inputRef.current?.focus();
                }}
              >
                {ex}
              </button>
            </span>
          ))}
        </p>
      )}
      {q && (
        <ul className="capsearch-results" aria-live="polite">
          {hits.length === 0 && (
            <li className="capsearch-empty">
              No confident match for <b>{q}</b> — try a capability, a problem, or a
              project name.
            </li>
          )}
          {hits.length > 0 && fuzzed && (
            <li className="capsearch-note" aria-hidden="true">
              no exact match — showing closest results
            </li>
          )}
          {hits.map((r) => (
            <li key={r.id} className={`capsearch-hit capsearch-hit--${r.type}`}>
              <a
                href={
                  r.type === 'project' && r.slug
                    ? `#project-${r.slug}`
                    : r.href ?? '#work'
                }
                data-qid={`search:hit:${r.id}`}
                data-qs-action="SEARCH_OPEN_HIT"
                title={r.summary || r.name}
              >
                <span className="capsearch-type">{r.type}</span>
                <span className="capsearch-name">{r.name}</span>
                {r.area && <span className="capsearch-area">{r.area}</span>}
                {r.visibility && r.visibility !== 'public' && (
                  <span className="capsearch-evi">evidence private</span>
                )}
              </a>
              {(r.question || r.summary) && (
                <p className="capsearch-sum">{r.question || r.summary}</p>
              )}
              {r.reason && r.reason.terms && (
                <p className="capsearch-why">
                  matched <b>{r.reason.terms}</b> in {r.reason.where}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
