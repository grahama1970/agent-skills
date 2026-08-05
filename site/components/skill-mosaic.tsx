'use client';

import { useMemo, useState } from 'react';
import inventory from '@/inventory.json';

interface SkillCell {
  n: string;
  c: string;
  s: boolean;
}

const GH = 'https://github.com/grahama1970/agent-skills/blob/main/skills';

/**
 * One cell per real SKILL.md, generated at commit time by
 * site/scripts/gen_inventory.py, grouped by the taxonomy that is already in
 * the data. Filled = has a sanity check; outlined = doesn't yet. The gaps
 * are shown deliberately. Filtering dims non-matches — the transition is
 * the query result, not decoration.
 */
export function SkillMosaic() {
  const [query, setQuery] = useState('');
  const skills = inventory.skills as SkillCell[];

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
  const shown = skills.filter(matches).length;

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <label className="flex items-baseline gap-2 text-[15px] text-mute">
          Filter
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            data-qid="index:input:filter"
            data-qs-action="INDEX_FILTER"
            title="Filter skills by name or category"
            placeholder="e.g. monitor, extract, tau"
            className="machine border-b border-line bg-transparent px-1 py-0.5 text-ink outline-none placeholder:text-mute"
          />
        </label>
        <span aria-live="polite" className="machine text-mute">
          {shown}/{skills.length} · filled = sanity-checked · outlined =
          contract only
        </span>
      </div>
      <div className="flex flex-col gap-5">
        {groups.map(([cat, list]) => (
          <div key={cat}>
            <div className="machine mb-1.5 text-mute">
              {cat} · {list.length}
            </div>
            <div className="flex flex-wrap gap-[3px]" role="list">
              {list.map((s) => (
                <a
                  key={s.n}
                  role="listitem"
                  href={`${GH}/${s.n}/SKILL.md`}
                  data-qid={`index:cell:${s.n}`}
                  data-qs-action="INDEX_OPEN_SKILL"
                  title={`${s.n}${s.s ? ' · sanity-checked' : ' · contract only'}`}
                  className={`mosaic-cell block h-4 w-4 rounded-[2px] border ${
                    s.s ? 'border-accent bg-fill' : 'border-mute bg-transparent'
                  } hover:border-ink`}
                  style={matches(s) ? undefined : { opacity: 0.15 }}
                >
                  <span className="sr-only">{s.n}</span>
                </a>
              ))}
            </div>
          </div>
        ))}
      </div>
      <details className="mt-6">
        <summary className="cursor-pointer text-[15px] text-mute">
          Plain list of all {skills.length} skills
        </summary>
        <ul className="machine mt-3 columns-2 gap-8 text-mute md:columns-3">
          {skills.map((s) => (
            <li key={s.n}>
              <a
                href={`${GH}/${s.n}/SKILL.md`}
                data-qid={`index:item:${s.n}`}
                data-qs-action="INDEX_OPEN_SKILL"
                title={`Open ${s.n} SKILL.md`}
                className="text-mute no-underline hover:text-ink"
              >
                {s.n}
                {s.s ? '' : ' *'}
              </a>
            </li>
          ))}
        </ul>
        <p className="machine mt-2 text-mute">* contract without a sanity check</p>
      </details>
    </div>
  );
}
