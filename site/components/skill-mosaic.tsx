'use client';

import { useMemo, useState } from 'react';
import inventory from '@/inventory.json';

const GH = 'https://github.com/grahama1970/agent-skills/blob/main/skills';

interface SkillCell {
  n: string;
  c: string;
  s: boolean;
}

/**
 * The ledger, grouped by the taxonomy already in the data, with a filter.
 * Every cell is a REAL skill from inventory.json — outlined cells are the
 * actual contracts without sanity checks — and each links to its SKILL.md.
 * Filtering dims non-matches; the transition is the query result.
 */
export function SkillMosaic() {
  const [query, setQuery] = useState('');
  const skills = inventory.skills as SkillCell[];
  const checked = skills.filter((s) => s.s).length;

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
  const matches = (s: SkillCell) => !q || s.n.includes(q) || s.c.includes(q);
  const shown = q ? skills.filter(matches).length : skills.length;
  let globalIndex = 0;

  return (
    <div className="ledger-mosaic">
      <div className="ledger-tools">
        <label>
          filter
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            data-qid="ledger:input:filter"
            data-qs-action="LEDGER_FILTER"
            title="Filter skills by name or category"
            placeholder="e.g. monitor, tau, extract"
          />
        </label>
        <span aria-live="polite">
          {shown}/{skills.length} shown
        </span>
      </div>
      {groups.map(([cat, list]) => (
        <div className="ledger-group" key={cat}>
          <span className="ledger-cat">
            {cat} · {list.length}
          </span>
          <div
            className="mosaic"
            role="list"
            aria-label={`${cat}: ${list.length} skill contracts`}
          >
            {list.map((s) => {
              const i = globalIndex++;
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
                    ...(matches(s) ? {} : { opacity: 0.12 }),
                  }}
                >
                  <span className="sr-only">{s.n}</span>
                </a>
              );
            })}
          </div>
        </div>
      ))}
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
