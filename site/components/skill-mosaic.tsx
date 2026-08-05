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
 * One cell per real SKILL.md in the repo, generated at commit time by
 * site/scripts/gen_inventory.py. Filled = has a sanity check; outlined = a
 * contract without one. The gaps are shown deliberately.
 */
export function SkillMosaic() {
  const [query, setQuery] = useState('');
  const skills = inventory.skills as SkillCell[];

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return new Set(skills.map((s) => s.n));
    return new Set(
      skills.filter((s) => s.n.includes(q) || s.c.includes(q)).map((s) => s.n),
    );
  }, [query, skills]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-baseline gap-x-6 gap-y-2">
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
        <span className="machine text-mute">
          {visible.size}/{skills.length} shown · filled = sanity-checked ·
          outlined = contract only
        </span>
      </div>
      <div className="flex flex-wrap gap-[3px]" role="list">
        {skills.map((s) => (
          <a
            key={s.n}
            role="listitem"
            href={`${GH}/${s.n}/SKILL.md`}
            data-qid={`index:cell:${s.n}`}
            data-qs-action="INDEX_OPEN_SKILL"
            title={`${s.n} — ${s.c}${s.s ? ' · sanity-checked' : ' · contract only'}`}
            className={`block h-[14px] w-[14px] rounded-[2px] border ${
              visible.has(s.n)
                ? s.s
                  ? 'border-accent bg-fill'
                  : 'border-mute bg-transparent'
                : 'border-line bg-transparent opacity-25'
            } hover:border-ink`}
          >
            <span className="sr-only">{s.n}</span>
          </a>
        ))}
      </div>
      <details className="mt-5">
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
