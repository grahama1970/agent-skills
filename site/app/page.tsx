import artifacts from '@/artifacts.json';
import { KeyboardNav } from '@/components/keyboard-nav';
import { SiteNav } from '@/components/site-nav';
import { SkillMosaic } from '@/components/skill-mosaic';
import content from '@/content.json';
import inventory from '@/inventory.json';

const REPO = 'https://github.com/grahama1970/agent-skills';

/** Per-card collage placement + tint from the winning comp. */
const CARD_META: Record<string, { cls: string; tint: string; img?: string }> = {
  tau: { cls: 'c1', tint: 'rgba(209,112,60,.55)' },
  battle: { cls: 'c2', tint: 'rgba(178,74,58,.5)' },
  surf: { cls: 'c3', tint: 'rgba(147,162,137,.45)' },
  'persona-dream': { cls: 'c4', tint: 'rgba(226,172,98,.5)' },
  extractor: { cls: 'c5', tint: 'rgba(196,142,86,.45)' },
  dogpile: { cls: 'c6', tint: 'rgba(160,120,150,.4)' },
  watch: { cls: 'c7', tint: 'rgba(209,112,60,.42)' },
  scillm: { cls: 'c8', tint: 'rgba(147,162,137,.42)' },
  debugger: { cls: 'c9', tint: 'rgba(196,142,86,.42)' },
  'sparta-explorer': { cls: 'c10', tint: 'rgba(120,140,170,.38)', img: 'sparta-montage' },
};

const DREAM_PHASES = [
  { f: 'phase01-idea-memory-residue', n: '01', c: 'idea · memory residue', t: 'rgba(209,112,60,.5)' },
  { f: 'phase02-story', n: '02', c: 'story', t: 'rgba(196,142,86,.45)' },
  { f: 'phase03-crew', n: '03', c: 'crew', t: 'rgba(147,162,137,.42)' },
  { f: 'phase04-contact-sheets', n: '04', c: 'contact sheets', t: 'rgba(226,172,98,.42)' },
  { f: 'phase05-voices', n: '05', c: 'voices', t: 'rgba(178,74,58,.42)' },
  { f: 'phase06-script', n: '06', c: 'script', t: 'rgba(160,120,150,.4)' },
  { f: 'phase07-storyboard', n: '07', c: 'storyboard', t: 'rgba(196,142,86,.42)' },
  { f: 'phase08-media-lock', n: '08', c: 'media lock', t: 'rgba(147,162,137,.4)' },
  { f: 'phase09-video-provider-current', n: '09', c: 'video provider', t: 'rgba(209,112,60,.4)' },
];

const TRACK = [
  { t: 'Composer', d: 'Commercial work for Adidas, Pepsi, X-Games.' },
  { t: 'Executive producer, Sony', d: 'God of War: Ascension campaign — Webby-recognized, 80-person productions.' },
  { t: 'DARPA ARCOS', d: 'Principal data scientist and technical lead, alongside Honeywell, Lockheed Martin, MIT, GE, SRI.' },
  { t: 'AFRL “Hacker” challenge coin', d: 'Recognition out of that work.' },
  { t: 'Lean 4 formal methods', d: 'Proof discipline carried into agent design.' },
  { t: 'This practice', d: 'Agent systems that produce their own evidence — shipped as working code, in public.' },
];

const skillFlags = new Map(
  (inventory.skills as { n: string; s: boolean }[]).map((s) => [s.n, s.s]),
);

export default function Home() {
  const { stats, commit, as_of } = inventory;
  const receiptArtifacts = Object.fromEntries(
    artifacts.artifacts.map((a) => [a.id, a]),
  );
  return (
    <>
      <div className="glow" aria-hidden="true" />
      <div className="grain" aria-hidden="true" />
      <div className="page">
        <SiteNav />
        <KeyboardNav />

        {/* ===================== HERO ===================== */}
        <section className="hero ruledbg" id="top">
          <div className="wrap">
            <div className="hero-grid">
              <div className="hero-main">
                <p className="eyebrow rise" style={{ ['--d' as string]: '.05s' }}>
                  <span className="dot" /> One-person practice{' '}
                  <span aria-hidden="true">/</span> agent systems, formal
                  methods, evidence
                </p>
                <h1 className="rise" style={{ ['--d' as string]: '.12s' }}>
                  I build agent systems that can <span className="it">prove</span>{' '}
                  what they did.
                </h1>
                <p className="hero-bio rise" style={{ ['--d' as string]: '.28s' }}>
                  A one-person practice with an unusual résumé: commercial
                  composer for <em>Adidas</em> and <em>Pepsi</em>,
                  Webby-recognized producer for <em>Sony</em>, DARPA technical
                  lead alongside <em>Lockheed Martin</em> and <em>MIT</em>.
                  High-end creative and hard technical work — delivered by the
                  same person, shipped as working code, in public.
                </p>
                <div className="hero-actions rise" style={{ ['--d' as string]: '.4s' }}>
                  <a
                    className="btn"
                    href="mailto:graham@grahama.co"
                    data-qid="hero:action:email"
                    data-qs-action="HERO_EMAIL"
                    title="Email graham@grahama.co"
                  >
                    Bring me the project you shelved <span className="arrow">→</span>
                  </a>
                  <a
                    className="btn ghost"
                    href={REPO}
                    data-qid="hero:action:repo"
                    data-qs-action="HERO_OPEN_REPO"
                    title="Open the agent-skills repository on GitHub"
                  >
                    Read the code
                  </a>
                </div>
              </div>
              <aside
                className="hero-side rise"
                style={{ ['--d' as string]: '.5s' }}
                aria-label="Skill inventory"
              >
                <div className="rail">
                  <p className="rail-title">Inventory</p>
                  <div className="figs">
                    <div className="fig">
                      <span className="n">{stats.skills}</span>
                      <span className="l">skill contracts</span>
                    </div>
                    <div className="fig">
                      <span className="n">
                        {stats.sanity}
                        <small>
                          {Math.round((stats.sanity / stats.skills) * 100)}%
                        </small>
                      </span>
                      <span className="l">with sanity checks</span>
                    </div>
                    <div className="fig">
                      <span className="n">{stats.agents}</span>
                      <span className="l">bounded agents</span>
                    </div>
                  </div>
                  <p className="prov">
                    generated
                    <br />
                    <b>{inventory.generator}</b>
                    <br />@{' '}
                    <a
                      href={`${REPO}/commit/${commit}`}
                      data-qid="hero:link:commit"
                      data-qs-action="HERO_OPEN_COMMIT"
                      title={`Open commit ${commit} on GitHub`}
                    >
                      {commit}
                    </a>{' '}
                    · {as_of}
                  </p>
                </div>
              </aside>
            </div>
          </div>
          <figure
            className="strip wipe"
            role="img"
            aria-label="Horus Lupercal and Embry taking tea on a terrace — persona-dream storyboard panel"
          >
            <figcaption>
              <b>Horus Lupercal &amp; Embry, taking tea in a dream</b> — re-rendered at 2172px from storyboard run 20260612, via WebGPT
            </figcaption>
          </figure>
        </section>

        <hr className="rule" />

        {/* ===================== LEDGER ===================== */}
        <section id="ledger">
          <div className="wrap">
            <div className="ledger-grid">
              <div className="ledger-copy">
                <p className="kicker">
                  <b>01</b> The ledger
                </p>
                <h2 className="h2">
                  Every contract, including the ones without checks.
                </h2>
                <p className="lede" style={{ marginTop: '1.1rem' }}>
                  One cell per skill contract — each links to its SKILL.md.
                  Filled cells carry a sanity check; outlined cells are
                  contract-only. The gaps stay visible on purpose — a practice
                  built on receipts doesn&apos;t get to hide its holes.
                </p>
              </div>
              <SkillMosaic />
            </div>
          </div>
        </section>

        <hr className="rule" />

        {/* ===================== WORK ===================== */}
        <section id="work">
          <div className="wrap">
            <div className="work-head">
              <div>
                <p className="kicker">
                  <b>02</b> Work
                </p>
                <h2 className="h2">Ten questions, answered in running code.</h2>
              </div>
              <p className="count">01 — 10 · each one a research question</p>
            </div>
            <div className="cards">
              {content.projects.map((p, i) => {
                const meta = CARD_META[p.slug];
                const external = !skillFlags.has(p.slug);
                return (
                  <a
                    key={p.slug}
                    className={`card ${meta.cls}`}
                    href={p.href}
                    data-qid={`work:card:${p.slug}`}
                    data-qs-action="WORK_OPEN_PROJECT"
                    title={`Open ${p.name} on GitHub`}
                  >
                    <div
                      className="shot"
                      style={{
                        ['--img' as string]: `url('/projects/${meta.img ?? p.slug}.webp')`,
                        ['--tint' as string]: meta.tint,
                      }}
                      role="img"
                      aria-label={p.slug === 'sparta-explorer' ? 'Sparta Explorer montage — F-36 spaceplane in the factory, live threat-matrix triage interface, governed evidence thread' : `${p.name} — concept art`}
                    />
                    <div className="card-body">
                      <span className="idx">{String(i + 1).padStart(2, '0')}</span>
                      <h3 className="cname">{p.name}</h3>
                      <p className="q">{p.question}</p>
                      <p className="d">{p.blurb}</p>
                      <span className={`chip${external ? ' ext' : ''}`}>
                        {external
                          ? 'external repo'
                          : skillFlags.get(p.slug)
                            ? 'sanity-checked'
                            : 'contract only'}
                      </span>
                    </div>
                  </a>
                );
              })}
            </div>
          </div>
        </section>

        {/* ===================== DREAM ===================== */}
        <section className="dream" id="dream">
          <div className="wrap">
            <div className="dream-head">
              <div className="a">
                <p className="kicker">
                  <b>03</b> persona-dream
                </p>
                <h2 className="h2">Agent memories, rendered into film.</h2>
              </div>
              <p className="b">
                Nine phases from idea to media lock, each a real frame out of
                the pipeline — receipt-backed dream packets rather than a mood
                board. Captured from the live run of 2026-06-29.
              </p>
            </div>
            <figure
              className="panel"
              role="img"
              aria-label="Embry at a desk reviewing contact sheets of her own memories — persona-dream rendered frame"
            >
              <span className="tag">Embry, reviewing her memories · dream-run · panel 01</span>
            </figure>
            <div className="film" aria-label="persona-dream pipeline phases">
              {DREAM_PHASES.map((d) => (
                <figure className="frame" key={d.f}>
                  <div
                    className="im"
                    style={{
                      ['--img' as string]: `url('/dream/${d.f}.webp')`,
                      ['--tint' as string]: d.t,
                    }}
                    role="img"
                    aria-label={`Phase ${d.n} — ${d.c}`}
                  />
                  <figcaption className="cap">
                    <b>phase {d.n}</b>
                    {d.c}
                  </figcaption>
                </figure>
              ))}
            </div>
          </div>
        </section>

        <hr className="rule" />

        {/* ===================== RECEIPTS ===================== */}
        <section id="receipts">
          <div className="wrap">
            <div className="receipts-grid">
              <div className="receipts-copy">
                <p className="kicker">
                  <b>04</b> Receipts
                </p>
                <h2 className="h2">No claim ships without one.</h2>
                <p className="lede" style={{ marginTop: '1.1rem' }}>
                  Three excerpts, printed as they came out of
                  <span className="machine"> gen_artifacts.py</span>: a node
                  receipt from the roundtable run that designed this page, a
                  captured audit, and the provenance of the numbers above.
                  Captured output, not status widgets.
                </p>
              </div>
              <div className="tickets">
                {(['roundtable-receipt', 'live-audit', 'inventory-provenance'] as const).map(
                  (id) =>
                    receiptArtifacts[id] && (
                      <article className="ticket" key={id}>
                        <h3>{receiptArtifacts[id].title}</h3>
                        <pre className="json">{receiptArtifacts[id].body}</pre>
                        <p className="foot">{receiptArtifacts[id].caption}</p>
                      </article>
                    ),
                )}
              </div>
            </div>
          </div>
        </section>

        <hr className="rule" />

        {/* ===================== ABOUT ===================== */}
        <section id="about">
          <div className="wrap">
            <div className="about-grid">
              <div className="about-copy">
                <p className="kicker">
                  <b>05</b> About
                </p>
                <h2 className="h2">An unusual path, on purpose.</h2>
                <div className="thesis">
                  <p>
                    An unconventional path is an advantage on problems with no
                    playbook.
                  </p>
                </div>
                <p className="lede" style={{ marginTop: '1.6rem' }}>
                  One person also means direct accountability — the person you
                  talk to architects, builds, and answers for the result. One
                  senior rate instead of an army&apos;s overhead. Available for
                  engagements and full-time roles —{' '}
                  <a
                    href={`${REPO}/blob/main/RESUME.md`}
                    data-qid="about:link:resume"
                    data-qs-action="ABOUT_OPEN_RESUME"
                    title="Open RESUME.md on GitHub"
                    style={{ color: 'var(--brass)' }}
                  >
                    full résumé
                  </a>
                  .
                </p>
              </div>
              <div className="track">
                {TRACK.map((s) => (
                  <div className="stop" key={s.t}>
                    <p className="st">{s.t}</p>
                    <p className="sd">{s.d}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ===================== CLOSER ===================== */}
        <section className="closer ruledbg" id="contact">
          <div className="wrap">
            <div className="closer-inner">
              <div className="a">
                <p className="kicker">
                  <b>06</b> Next
                </p>
                <p className="shelved">
                  Bring me the project you <em>shelved</em>.
                </p>
              </div>
              <div className="b">
                <p className="accountability">
                  The one with no playbook — the one that stalled because it
                  needed both halves of the job.
                </p>
                <a
                  className="btn"
                  href="mailto:graham@grahama.co"
                  data-qid="contact:action:email"
                  data-qs-action="CONTACT_EMAIL"
                  title="Email graham@grahama.co"
                >
                  graham@grahama.co <span className="arrow">→</span>
                </a>
              </div>
            </div>
          </div>
        </section>

        <footer>
          <div className="wrap">
            <div className="foot-grid">
              <div className="foot-a">
                <p className="lab">Contact</p>
                <a
                  href="mailto:graham@grahama.co"
                  data-qid="footer:link:email"
                  data-qs-action="FOOTER_EMAIL"
                  title="Email graham@grahama.co"
                >
                  graham@grahama.co
                </a>
                <a
                  href={REPO}
                  data-qid="footer:link:repo"
                  data-qs-action="FOOTER_OPEN_REPO"
                  title="Open the agent-skills repository"
                >
                  github.com/grahama1970/agent-skills
                </a>
                <a
                  href={`${REPO}/blob/main/RESUME.md`}
                  data-qid="footer:link:resume"
                  data-qs-action="FOOTER_OPEN_RESUME"
                  title="Open RESUME.md"
                >
                  github.com/grahama1970/agent-skills/blob/main/RESUME.md
                </a>
              </div>
              <div className="foot-b">
                <p className="lab">Inventory</p>
                <p className="prov" style={{ marginTop: 0 }}>
                  {stats.skills} skill contracts
                  <br />
                  {stats.sanity} with sanity checks (
                  {Math.round((stats.sanity / stats.skills) * 100)}%)
                  <br />
                  {stats.agents} bounded agents
                  <br />
                  <b>{inventory.generator}</b> @ {commit}
                  <br />
                  {as_of}
                </p>
              </div>
              <div className="foot-c">
                <p className="lab">Ethos</p>
                <p className="ethos">No claim ships without a receipt.</p>
              </div>
            </div>
          </div>
        </footer>
      </div>
    </>
  );
}
