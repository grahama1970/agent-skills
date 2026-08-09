'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import inventory from '@/inventory.json';

const GH = 'https://github.com/grahama1970/agent-skills/blob/main/skills';

interface SkillCell {
  n: string;
  c: string;
  s: boolean;
}

/**
 * The ledger: every cell a real skill from inventory.json, linking to its
 * SKILL.md. Category chips + text filter (press "/" anywhere to focus),
 * and a Matrix / Categorized density toggle. Filtering dims non-matches —
 * the transition is the query result.
 */
export function SkillMosaic() {
  const [query, setQuery] = useState('');
  const [cat, setCat] = useState('all');
  const [view, setView] = useState<'categorized' | 'matrix'>('categorized');
  // Phones get a search-first labeled list (filtering shortens it, rows are
  // tappable and labeled) instead of the 338 tiny unlabeled cells, which need
  // a hover tooltip touch can't give. Desktop keeps the matrix. Defaults to
  // false so SSR and first client render agree, then flips on mount if mobile.
  const [isMobile, setIsMobile] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 640px)');
    const update = () => setIsMobile(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);

  const skills = inventory.skills as SkillCell[];
  const checked = skills.filter((s) => s.s).length;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement as HTMLElement | null;
      const editing =
        !!el &&
        (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) ||
          el.isContentEditable);
      if (e.key === '/' && !editing) {
        e.preventDefault();
        inputRef.current?.scrollIntoView({ block: 'center' });
        inputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const groups = useMemo(() => {
    const by = new Map<string, SkillCell[]>();
    for (const s of skills) {
      const list = by.get(s.c) ?? [];
      list.push(s);
      by.set(s.c, list);
    }
    return [...by.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [skills]);

  const q = query.trim().toLowerCase();
  const matches = (s: SkillCell) =>
    (cat === 'all' || s.c === cat) &&
    (!q || s.n.includes(q) || s.c.includes(q));
  const shown = skills.filter(matches).length;

  const COLS = 26;
  const maxRank = COLS - 1 + Math.ceil(skills.length / COLS) - 1;
  const renderCell = (s: SkillCell, i: number) => {
    const rank = (i % COLS) + Math.floor(i / COLS);
    const t = Math.pow(rank / maxRank, 0.8); // decaying stagger: tail converges
    return (
    <a
      key={s.n}
      role="listitem"
      href={`${GH}/${s.n}/SKILL.md`}
      data-qid={`ledger:cell:${s.n}`}
      data-qs-action="LEDGER_OPEN_SKILL"
      title={`${s.n} · ${s.c}${s.s ? ' · sanity-checked' : ' · contract only'}`}
      className={`cell${s.s ? '' : ' out'}`}
      style={{
        ['--i' as string]: i,
        ['--t' as string]: t.toFixed(4),
        ...(matches(s) ? {} : { opacity: 0.12 }),
      }}
    >
      <span className="sr-only">{s.n}</span>
    </a>
    );
  };

  let gi = 0;
  return (
    <div className="ledger-mosaic">
      <div className="ledger-tools">
        <label>
          filter
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            data-qid="ledger:input:filter"
            data-qs-action="LEDGER_FILTER"
            title="Filter skills by name or category (press / to focus)"
            placeholder="press / to search"
          />
        </label>
        <span aria-live="polite">
          {shown}/{skills.length} shown
        </span>
        <button
          type="button"
          data-qid="ledger:action:view"
          data-qs-action="LEDGER_TOGGLE_VIEW"
          title="Toggle between categorized and flat matrix view"
          onClick={() =>
            setView(view === 'categorized' ? 'matrix' : 'categorized')
          }
          className="ledger-view"
        >
          [{view === 'categorized' ? 'categorized' : 'matrix'}]
        </button>
      </div>
      <div className="ledger-chips" role="group" aria-label="Category filters">
        <button
          type="button"
          data-qid="ledger:chip:all"
          data-qs-action="LEDGER_FILTER_CATEGORY"
          title="Show all categories"
          onClick={() => setCat('all')}
          className={`ledger-chip${cat === 'all' ? ' is-on' : ''}`}
        >
          all · {skills.length}
        </button>
        {groups.map(([c, list]) => (
          <button
            key={c}
            type="button"
            data-qid={`ledger:chip:${c}`}
            data-qs-action="LEDGER_FILTER_CATEGORY"
            title={`Filter to ${c}`}
            onClick={() => setCat(cat === c ? 'all' : c)}
            className={`ledger-chip${cat === c ? ' is-on' : ''}`}
          >
            {c} · {list.length}
          </button>
        ))}
      </div>
      {isMobile ? (
        <ul
          className="ledger-list"
          aria-label={`${shown} of ${skills.length} skill contracts`}
        >
          {skills.filter(matches).map((s) => (
            <li key={s.n}>
              <a
                href={`${GH}/${s.n}/SKILL.md`}
                data-qid={`ledger:row:${s.n}`}
                data-qs-action="LEDGER_OPEN_SKILL"
                title={`Open ${s.n} SKILL.md — ${s.c}${s.s ? ', sanity-checked' : ', contract only'}`}
              >
                <span className={`lr-dot${s.s ? '' : ' out'}`} aria-hidden="true" />
                <span className="lr-name">{s.n}</span>
                <span className="lr-cat">{s.c}</span>
                <span className="sr-only">
                  {s.s ? 'sanity-checked' : 'contract only'}
                </span>
              </a>
            </li>
          ))}
        </ul>
      ) : view === 'categorized' ? (
        groups.map(([c, list]) => (
          <div className="ledger-group" key={c}>
            <span className="ledger-cat">
              {c} · {list.length}
            </span>
            <div
              className="mosaic"
              role="list"
              aria-label={`${c}: ${list.length} skill contracts`}
            >
              {list.map((s) => renderCell(s, gi++))}
            </div>
          </div>
        ))
      ) : (
        <div
          className="mosaic"
          role="list"
          aria-label={`All ${skills.length} skill contracts`}
          style={{ marginTop: '1rem' }}
        >
          {skills.map((s, i) => renderCell(s, i))}
        </div>
      )}
      <div className="legend">
        <span>
          <i className="swatch" /> <b>{checked}</b> sanity-checked
        </span>
        <span>
          <i className="swatch out" /> <b>{skills.length - checked}</b>{' '}
          contract-only
        </span>
        <span>
          <b>{skills.length}</b> total · <b>{inventory.stats.agents}</b> bounded
          agents
        </span>
      </div>
    </div>
  );
}
