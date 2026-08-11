import { CapabilitySearch } from '@/components/capability-search';
import { CapabilityConstellation } from '@/components/capability-constellation';
import { SiteNav } from '@/components/site-nav';
import content from '@/content.json';
import inventory from '@/inventory.json';
import visibility from '@/project-visibility.json';

const PROJECT_VISUALS: Record<string, { tint: string; img?: string; decode?: string }> = {
  tau: { tint: 'rgba(209,112,60,.55)', decode: 'zero-trust agent harness' },
  battle: { tint: 'rgba(178,74,58,.5)', decode: 'exploit-evolution arena' },
  surf: { tint: 'rgba(147,162,137,.45)', decode: 'authenticated browser control' },
  'persona-dream': { tint: 'rgba(226,172,98,.5)', decode: 'dream-affect voice study' },
  extractor: { tint: 'rgba(196,142,86,.45)' },
  dogpile: { tint: 'rgba(160,120,150,.4)' },
  watch: { tint: 'rgba(209,112,60,.42)' },
  scillm: { tint: 'rgba(147,162,137,.42)' },
  debugger: { tint: 'rgba(196,142,86,.42)' },
  'sparta-explorer': { tint: 'rgba(120,140,170,.38)', img: 'sparta-montage', decode: 'space-cyber evidence workbench' },
};

const skillFlags = new Map(
  (inventory.skills as { n: string; s: boolean }[]).map((s) => [s.n, s.s]),
);

type VisibilityProject = {
  slug: string;
  visibility: string;
  href: string | null;
};

export default function ExplorePage() {
  const visibilityBySlug = new Map(
    (visibility.projects as VisibilityProject[]).map((v) => [v.slug, v]),
  );

  return (
    <main className="depth-page" id="top">
      <SiteNav hrefBase="/" />
      <section className="depth-head">
        <div className="wrap">
          <p className="kicker">
            <b>Explore</b> Project fit
          </p>
          <h1>Search the practice by problem.</h1>
        </div>
      </section>
      <section className="search-band">
        <div className="wrap">
          <CapabilitySearch />
          <CapabilityConstellation />
        </div>
      </section>
      <section id="projects" className="explore-projects">
        <div className="wrap">
          <div className="work-head">
            <div>
              <p className="kicker">
                <b>Explore</b> Public project index
              </p>
              <h2 className="h2">All public systems, source links, and evidence states.</h2>
            </div>
            <p className="count">graph click → target card → source</p>
          </div>
          <div className="cards explore-cards" aria-label="Complete public project index">
            {content.projects.map((p, i) => {
              const meta = PROJECT_VISUALS[p.slug] ?? { tint: 'rgba(226,172,98,.42)' };
              const external = !skillFlags.has(p.slug);
              const vis = visibilityBySlug.get(p.slug);
              const linkHref = vis?.href ?? p.href;
              const evidencePrivate = !!vis && vis.visibility !== 'public';
              const ghShort = linkHref
                .replace('https://github.com/', 'github.com/')
                .replace('/blob/main/skills/', '/…/')
                .replace('/README.md', '');
              return (
                <article key={p.slug} className="card secondary" id={`project-${p.slug}`}>
                  <a
                    href={linkHref}
                    data-qid={`explore:card:${p.slug}`}
                    data-qs-action="EXPLORE_OPEN_PROJECT"
                    title={`Open ${p.name} source`}
                    className="shot-link"
                  >
                    <div
                      className="shot"
                      style={{ ['--tint' as string]: meta.tint }}
                      role="img"
                      aria-label={`${p.name} — public project preview`}
                    >
                      <img
                        className="shot-img"
                        src={`/projects/${meta.img ?? p.slug}.webp`}
                        alt=""
                        loading="eager"
                        decoding="async"
                        aria-hidden="true"
                      />
                    </div>
                  </a>
                  <div className="card-body">
                    <span className="idx">{String(i + 1).padStart(2, '0')}</span>
                    <h3 className="cname">
                      {p.name}
                      {meta.decode && <span className="decode">{meta.decode}</span>}
                    </h3>
                    <p className="q">{p.question}</p>
                    <p className="d">{p.blurb}</p>
                    <span className={`chip${external ? ' ext' : ''}`}>
                      {external
                        ? 'external repo'
                        : skillFlags.get(p.slug)
                          ? 'sanity-checked'
                          : 'contract only'}
                    </span>
                    {evidencePrivate && (
                      <span
                        className="evidence-private"
                        title="Public product overview; the underlying system and its evidence are private."
                      >
                        product overview · evidence private
                      </span>
                    )}
                    <div className="project-actions">
                      <a
                        href={linkHref}
                        target="_blank"
                        rel="noopener noreferrer"
                        data-qid={`explore:repo:${p.slug}`}
                        data-qs-action="EXPLORE_OPEN_REPO"
                        title={`Open ${p.name} source on github.com`}
                        aria-label={`${ghShort} — ${p.name} source on GitHub (opens in a new tab)`}
                        className="github-repo-link"
                      >
                        <svg className="gh-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.28.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>
                        <span className="gh-path">{ghShort}</span>
                        <span className="gh-arrow" aria-hidden="true">↗</span>
                      </a>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      </section>
    </main>
  );
}
