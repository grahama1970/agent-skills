import content from '@/content.json';
import inventory from '@/inventory.json';

/** Real per-project metadata: category accent + honest tag pills. */
const META: Record<string, { cat: string; tags: string[] }> = {
  tau: { cat: 'core', tags: ['DAG contracts', 'receipts', 'zero-trust'] },
  battle: { cat: 'monitor', tags: ['red/blue', 'genetic fuzzing', 'arena'] },
  surf: { cat: 'ops', tags: ['authenticated Chrome', 'tab-scoped', 'proof receipts'] },
  'persona-dream': { cat: 'create', tags: ['memory → film', 'review-gated', 'voice'] },
  extractor: { cat: 'extract', tags: ['evidence trees', 'PDF', 'hierarchy'] },
  dogpile: { cat: 'discover', tags: ['arXiv', 'GitHub', 'multi-source'] },
  watch: { cat: 'learn', tags: ['video', 'frame-level', 'agents'] },
  scillm: { cat: 'core', tags: ['orchestration', 'DAG', 'model gateway'] },
  debugger: { cat: 'review', tags: ['breakpoints', 'live state', 'observe first'] },
  'sparta-explorer': { cat: 'review', tags: ['space-cyber', 'evidence', 'human review'] },
};

const skillSet = new Map(
  (inventory.skills as { n: string; s: boolean }[]).map((s) => [s.n, s.s]),
);

function status(slug: string): { label: string; ok: boolean } {
  if (!skillSet.has(slug)) return { label: 'external repo', ok: true };
  return skillSet.get(slug)
    ? { label: 'sanity-checked', ok: true }
    : { label: 'contract only', ok: false };
}

export function WorkGrid() {
  return (
    <div className="work-grid">
      {content.projects.map((p, i) => {
        const meta = META[p.slug] ?? { cat: 'core', tags: [] };
        const st = status(p.slug);
        return (
          <a
            key={p.slug}
            id={p.slug}
            href={p.href}
            data-qid={`work:card:${p.slug}`}
            data-qs-action="WORK_OPEN_PROJECT"
            title={`Open ${p.name} on GitHub — ${st.label}`}
            className="project-card scroll-mt-14"
            style={{ ['--card-accent' as string]: `var(--cat-${meta.cat}, var(--cat-default))` }}
          >
            <div className="mb-3 mt-1 flex items-start justify-between gap-3">
              <h3 className="font-display text-[1.25rem] leading-tight">
                <span className="machine mr-2 text-mute">
                  {String(i + 1).padStart(2, '0')}
                </span>
                {p.name}
              </h3>
              <span
                className={`machine mt-1 whitespace-nowrap uppercase ${
                  st.ok ? 'text-accent' : 'text-mute'
                }`}
              >
                {st.ok ? '✓' : '○'} {st.label}
              </span>
            </div>
            <p className="mb-2 font-display text-[15.5px] italic text-mute">
              {p.question}
            </p>
            <p className="mb-4 grow text-[14px] text-mute">{p.blurb}</p>
            <div className="mb-4 flex flex-wrap gap-1.5">
              {meta.tags.map((t) => (
                <span key={t} className="tag-pill">
                  {t}
                </span>
              ))}
            </div>
            <span className="card-action">View README</span>
          </a>
        );
      })}
    </div>
  );
}
