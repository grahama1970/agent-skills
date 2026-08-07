'use client';

import { useMemo, useRef, useState } from 'react';
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
function buildIndex() {
  const ms = new MiniSearch<Doc>({
    fields: ['name', 'aliases', 'area', 'disciplines', 'question', 'summary', 'category'],
    storeFields: ['type', 'name', 'slug', 'area', 'href', 'question', 'summary', 'visibility', 'evidenceAccess'],
    searchOptions: {
      boost: { name: 4, aliases: 3, area: 2 },
      prefix: true,
      fuzzy: (term) => (term.length > 4 ? 0.2 : false),
      combineWith: 'AND',
    },
    extractField: (doc, field) => {
      const v = (doc as unknown as Record<string, unknown>)[field];
      return Array.isArray(v) ? v.join(' ') : ((v as string) ?? '');
    },
  });
  ms.addAll(DOCS);
  return ms;
}

const EXAMPLES = [
  'voice agent that remembers',
  'red team',
  'compliance evidence',
  'which browser tab acted',
  'RAG extraction',
  'video generation',
];

/**
 * Capability search: a client types a problem, gets ranked real work back.
 * Retrieval only selects/ranks — every href and label comes from the
 * generated catalog (public/visibility-safe), never invented.
 */
export function CapabilitySearch() {
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const index = useMemo(buildIndex, []);

  const q = query.trim();
  const results = q
    ? index.search(q).slice(0, 8).map((r) => r as unknown as Doc & { score: number })
    : [];

  return (
    <div className="capsearch" aria-label="Search the practice by problem">
      <label className="capsearch-label" htmlFor="capsearch-input">
        Find work by problem
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
        placeholder="e.g. a voice agent that remembers previous conversations"
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
          {results.length === 0 && (
            <li className="capsearch-empty">
              No match — try a capability, a problem, or a project name.
            </li>
          )}
          {results.map((r) => (
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
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
