import inventory from '@/inventory.json';

const GH = 'https://github.com/grahama1970/agent-skills/blob/main/skills';

/**
 * The ledger mosaic from the winning comp — but every cell is a REAL skill
 * from inventory.json (the comp scattered fake gaps with a PRNG; here the
 * outlined cells are the actual contracts without sanity checks, in
 * alphabetical order, each linking to its SKILL.md).
 */
export function SkillMosaic() {
  const skills = inventory.skills as { n: string; c: string; s: boolean }[];
  const checked = skills.filter((s) => s.s).length;
  return (
    <div className="ledger-mosaic">
      <div
        className="mosaic"
        role="list"
        aria-label={`Mosaic of ${skills.length} skill contracts; ${checked} filled cells carry sanity checks and ${skills.length - checked} outlined cells are contract-only`}
      >
        {skills.map((s, i) => (
          <a
            key={s.n}
            role="listitem"
            href={`${GH}/${s.n}/SKILL.md`}
            data-qid={`ledger:cell:${s.n}`}
            data-qs-action="LEDGER_OPEN_SKILL"
            title={`${s.n} · ${s.c}${s.s ? ' · sanity-checked' : ' · contract only'}`}
            className={`cell${s.s ? '' : ' out'}`}
            style={{ ['--i' as string]: i }}
          >
            <span className="sr-only">{s.n}</span>
          </a>
        ))}
      </div>
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
