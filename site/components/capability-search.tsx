'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { buildIndex, runSearch, type Hit } from '@/lib/search';
import inventory from '@/inventory.json';

const BUILD_COMMIT = (inventory as { commit: string }).commit;

// Honest scout-readiness labels (webgpt Criterion 4): whether the public code
// runs on a fresh clone or needs setup. No project claims "run now" without a
// passing quickstart receipt, so a visitor knows what to expect before leaving.
const SCOUT_LABEL: Record<string, string> = {
  'run-now': 'runs on a fresh clone',
  'setup-required': 'public code · setup required',
  'public-blueprint': 'public blueprint',
  'abstract-only': 'private · overview only',
};

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
      <p className="capsearch-nodemo">
        No &ldquo;book a demo.&rdquo; Describe the problem — I&rsquo;ll point you
        to the closest public project, tell you what runs now and what needs
        setup, and leave the gaps visible. Start there; <em>then</em> let&rsquo;s
        talk.
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
          {(() => {
            // Scout Card: the top PROJECT result becomes a complete, actionable
            // card — why it matched, honest readiness, what it gives you, what
            // you need before starting, its boundary, and the actions to begin.
            const scout = hits.find((h) => h.type === 'project');
            if (!scout) return null;
            const isPrivate = scout.visibility && scout.visibility !== 'public';
            return (
              <li className="scout-card" key={`scout-${scout.id}`}>
                <div className="scout-head">
                  <span className="scout-kicker">best match · project</span>
                  <h3 className="scout-name">{scout.name}</h3>
                  {scout.area && <span className="scout-area">{scout.area}</span>}
                </div>
                <p className="scout-badges">
                  <span className={`capsearch-scout capsearch-scout--${scout.scoutState}`}>
                    {SCOUT_LABEL[scout.scoutState ?? ''] ?? scout.scoutState}
                  </span>
                  <span className="scout-verified">last verified {BUILD_COMMIT}</span>
                </p>
                {scout.reason?.terms && (
                  <p className="scout-why">
                    matched <b>{scout.reason.terms}</b> in {scout.reason.where}
                  </p>
                )}
                {(scout.summary || scout.question) && (
                  <p className="scout-give">
                    <span className="scout-lab">What it gives you</span>
                    {scout.summary || scout.question}
                  </p>
                )}
                {scout.requirements && (
                  <p className="scout-req">
                    <span className="scout-lab">Before you start</span>
                    {scout.requirements}
                  </p>
                )}
                {scout.boundary && (
                  <p className="scout-bound">
                    <span className="scout-lab">Known boundary</span>
                    {scout.boundary}
                  </p>
                )}
                <p className="scout-actions">
                  {!isPrivate && scout.href && (
                    <a
                      href={scout.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="scout-act scout-act--primary"
                      data-qid={`scout:readme:${scout.slug}`}
                      data-qs-action="SCOUT_OPEN_README"
                      title={`Open ${scout.name} on GitHub`}
                    >
                      Start with the README ↗
                    </a>
                  )}
                  <a
                    href={scout.slug ? `#project-${scout.slug}` : '#work'}
                    className="scout-act"
                    data-qid={`scout:evidence:${scout.slug}`}
                    data-qs-action="SCOUT_INSPECT_EVIDENCE"
                    title={`Inspect ${scout.name} evidence on this page`}
                  >
                    Inspect evidence
                  </a>
                  <a
                    href="#search"
                    className="scout-act"
                    data-qid={`scout:connections:${scout.slug}`}
                    data-qs-action="SCOUT_SHOW_CONNECTIONS"
                    title="See how this connects in the constellation"
                  >
                    Show connections
                  </a>
                </p>
              </li>
            );
          })()}
          {hits.filter((h) => h.type !== 'project' || h.id !== hits.find((x) => x.type === 'project')?.id).map((r) => (
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
                {r.type === 'project' && r.scoutState && (
                  <span className={`capsearch-scout capsearch-scout--${r.scoutState}`}>
                    {SCOUT_LABEL[r.scoutState] ?? r.scoutState}
                  </span>
                )}
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
