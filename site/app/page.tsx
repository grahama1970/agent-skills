import artifacts from '@/artifacts.json';
import lineage from '@/generated/battle-lineage.json';
import { HeroLineage, type HeroLineageData } from '@/components/hero-lineage';
import { HeroProofBridge } from '@/components/hero-proof-bridge';
import { ReceiptTicket } from '@/components/receipt-ticket';
import { DreamStepper } from '@/components/dream-stepper';
import { KeyboardNav } from '@/components/keyboard-nav';
import { SiteNav } from '@/components/site-nav';
import { UnusualPath } from '@/components/unusual-path';
import { SkillMosaic } from '@/components/skill-mosaic';
import content from '@/content.json';
import inventory from '@/inventory.json';

const REPO = 'https://github.com/grahama1970/agent-skills';

/** Per-card collage placement + tint from the winning comp. */
const CARD_META: Record<string, { cls: string; tint: string; img?: string; decode?: string }> = {
  tau: { cls: 'c1', tint: 'rgba(209,112,60,.55)', decode: 'zero-trust agent harness' },
  battle: { cls: 'c2', tint: 'rgba(178,74,58,.5)', decode: 'exploit-evolution arena' },
  surf: { cls: 'c3', tint: 'rgba(147,162,137,.45)', decode: 'authenticated browser control' },
  'persona-dream': { cls: 'c4', tint: 'rgba(226,172,98,.5)', decode: 'dream-affect voice study' },
  extractor: { cls: 'c5', tint: 'rgba(196,142,86,.45)' },
  dogpile: { cls: 'c6', tint: 'rgba(160,120,150,.4)' },
  watch: { cls: 'c7', tint: 'rgba(209,112,60,.42)' },
  scillm: { cls: 'c8', tint: 'rgba(147,162,137,.42)' },
  debugger: { cls: 'c9', tint: 'rgba(196,142,86,.42)' },
  'sparta-explorer': { cls: 'c10', tint: 'rgba(120,140,170,.38)', img: 'sparta-montage', decode: 'space-cyber evidence workbench' },
};

const DREAM_PHASES = [
  { f: 'research-loop', n: '00', c: 'the research loop — memory, dream, conversation', t: 'rgba(147,162,137,.42)', dims: '1672×941', src: 'persona-dream/assets/readme/research-loop' },
  { f: 'phase01-idea-memory-residue', n: '01', c: 'idea · memory residue', t: 'rgba(209,112,60,.5)', dims: '1600×1891', src: 'persona-dream/assets/readme/phase01' },
  { f: 'phase02-story-content-pane', n: '02', c: 'story', t: 'rgba(196,142,86,.45)', dims: '1270×1480', src: 'persona-dream/assets/readme/phase02-content-pane' },
  { f: 'phase03-crew-content-pane', n: '03', c: 'crew', t: 'rgba(147,162,137,.42)', dims: '1270×1480', src: 'persona-dream/assets/readme/phase03-content-pane' },
  { f: 'phase04-contact-sheets-content-pane', n: '04', c: 'contact sheets', t: 'rgba(226,172,98,.42)', dims: '1280×681', src: 'persona-dream/assets/readme/phase04-content-pane' },
  { f: 'phase05-voices-content-pane', n: '05', c: 'voices', t: 'rgba(178,74,58,.42)', dims: '1280×952', src: 'persona-dream/assets/readme/phase05-content-pane' },
  { f: 'phase06-script-content-pane', n: '06', c: 'script', t: 'rgba(160,120,150,.4)', dims: '1270×1480', src: 'persona-dream/assets/readme/phase06-content-pane' },
  { f: 'phase07-storyboard-content-pane', n: '07', c: 'storyboard', t: 'rgba(196,142,86,.42)', dims: '1270×1480', src: 'persona-dream/assets/readme/phase07-content-pane' },
  { f: 'phase08-media-lock', n: '08', c: 'media lock', t: 'rgba(147,162,137,.4)', dims: '1600×1387', src: 'persona-dream/assets/readme/phase08' },
  { f: 'phase09-video-provider-current', n: '09', c: 'video provider', t: 'rgba(209,112,60,.4)', dims: '1280×997', src: 'persona-dream/assets/readme/phase09' },
  { f: 'dream-panel', n: '10', c: 'a rendered dream — memory review beneath the watching eye', t: 'rgba(209,112,60,.45)', dims: '1536×1024', src: 'persona-dream/provider_media/issue-33-live · 2026-06-29' },
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
                  I build agent systems that can{' '}
                  <span className="it proof-origin" data-proof-origin>
                    prove
                  </span>{' '}
                  what they did.
                </h1>
                <p className="hero-bio rise" style={{ ['--d' as string]: '.28s' }}>
                  A one-person practice with an unusual résumé: commercial
                  composer for <em style={{ ['--i' as string]: 1 }}>Adidas</em>{' '}
                  and <em style={{ ['--i' as string]: 2 }}>Pepsi</em>,
                  Webby-recognized producer for{' '}
                  <em style={{ ['--i' as string]: 3 }}>Sony</em>,{' '}
                  <em style={{ ['--i' as string]: 4 }}>DARPA</em> technical
                  lead alongside{' '}
                  <em style={{ ['--i' as string]: 5 }}>Lockheed Martin</em> and{' '}
                  <em style={{ ['--i' as string]: 6 }}>MIT</em>.
                  High-end creative and hard technical work — delivered by the
                  same person, shipped as working code, in public.
                </p>
                <p className="hero-outcomes rise" style={{ ['--d' as string]: '.34s' }}>
                  In practice: <b>verifiable audit trails</b>,{' '}
                  <b>zero-trust execution</b>, <b>no silent failures</b> — for
                  workflows where &quot;probably fine&quot; isn&apos;t good
                  enough.
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
                <p className="hero-intake rise" style={{ ['--d' as string]: '.46s' }}>
                  Principal R&amp;D capacity for the agent problems a roadmap
                  can&apos;t prioritize — non-deterministic behavior, formal
                  verification, multimodal pipelines.
                </p>
              </div>
              <aside
                className="hero-side rise"
                style={{ ['--d' as string]: '.5s' }}
                aria-label="Skill inventory"
              >
                <div className="rail">
                  <p className="rail-title">Inventory</p>
                  <div className="figs">
                    <a
                      className="fig"
                      href={`${REPO}/tree/main/skills`}
                      data-qid="rail:link:skills"
                      data-qs-action="RAIL_OPEN_SKILLS"
                      title="Browse all skill contracts on GitHub"
                    >
                      <span className="n">{stats.skills}</span>
                      <span className="l">skill contracts</span>
                    </a>
                    <a
                      className="fig"
                      href="#ledger"
                      data-qid="rail:link:sanity"
                      data-qs-action="RAIL_GOTO_LEDGER"
                      title="See the coverage ledger, gaps included"
                    >
                      <span className="n">
                        {stats.sanity}
                        <small>
                          {Math.round((stats.sanity / stats.skills) * 100)}%
                        </small>
                      </span>
                      <span className="l">with sanity checks</span>
                    </a>
                    <a
                      className="fig"
                      href={`${REPO}/tree/main/agents`}
                      data-qid="rail:link:agents"
                      data-qs-action="RAIL_OPEN_AGENTS"
                      title="Browse bounded agent definitions on GitHub"
                    >
                      <span className="n">{stats.agents}</span>
                      <span className="l">bounded agents</span>
                    </a>
                  </div>
                  <p className="prov">
                    generated
                    <br />
                    <a
                      href={`${REPO}/blob/main/site/scripts/gen_inventory.py`}
                      data-qid="rail:link:generator"
                      data-qs-action="RAIL_OPEN_GENERATOR"
                      title="Read the generator script on GitHub"
                      className="gen-link"
                    >
                      {inventory.generator}
                    </a>
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
                  <HeroLineage data={lineage as HeroLineageData} />
                </div>
              </aside>
              <HeroProofBridge />
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

        {/* ===================== WORK ===================== */}
        <section id="work">
          <div className="wrap">
            <div className="work-head">
              <div>
                <p className="kicker">
                  <b>01</b> Work
                </p>
                <h2 className="h2">Ten questions, answered in running code.</h2>
              </div>
              <p className="count">01 — 10 · each one a research question</p>
            </div>
            <div className="cards">
              {content.projects.map((p, i) => {
                const meta = CARD_META[p.slug];
                const external = !skillFlags.has(p.slug);
                const ghShort = p.href
                  .replace('https://github.com/', 'github.com/')
                  .replace('/blob/main/skills/', '/…/')
                  .replace('/README.md', '');
                return (
                  <article key={p.slug} className={`card ${meta.cls}`} id={`project-${p.slug}`}>
                    <a
                      href={p.href}
                      data-qid={`work:card:${p.slug}`}
                      data-qs-action="WORK_OPEN_PROJECT"
                      title={`Open ${p.name} on GitHub`}
                      className="shot-link"
                    >
                      <div
                        className="shot"
                        style={{
                          ['--img' as string]: `url('/projects/${meta.img ?? p.slug}.webp')`,
                          ['--tint' as string]: meta.tint,
                        }}
                        role="img"
                        aria-label={p.slug === 'sparta-explorer' ? 'Sparta Explorer — governed evidence thread from program manager and engineer through policy gate to pilot, Embry OS' : `${p.name} — concept art`}
                      />
                    </a>
                    <div className="card-body">
                      <span className="idx">{String(i + 1).padStart(2, '0')}</span>
                      <h3 className="cname">
                        {p.name}
                        {meta.decode && (
                          <span className="decode">{meta.decode}</span>
                        )}
                      </h3>
                      <p className="q">{p.question}</p>
                      <p className="d">{p.blurb}</p>
                      <p className="why">{p.why}</p>
                      <span className={`chip${external ? ' ext' : ''}`}>
                        {external
                          ? 'external repo'
                          : skillFlags.get(p.slug)
                            ? 'sanity-checked'
                            : 'contract only'}
                      </span>
                      <div className="project-actions">
                        <a
                          href={p.href}
                          target="_blank"
                          rel="noopener noreferrer"
                          data-qid={`work:repo:${p.slug}`}
                          data-qs-action="WORK_OPEN_REPO"
                          title={`Open ${p.name} repository on github.com`}
                          aria-label={`View ${p.name} source code on GitHub (opens in a new tab)`}
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

        <hr className="rule" />

        {/* ===================== DREAM ===================== */}
        <section className="dream" id="dream">
          <div className="wrap">
            <div className="dream-head">
              <div className="a">
                <p className="kicker">
                  <b>02</b> persona-dream
                </p>
                <h2 className="h2">Can a persona dream itself a personality?</h2>
              </div>
              <p className="b">
                Not a movie generator — a preregistered study. The question:
                does letting a persistent voice persona <em>dream</em> about
                its experience actually help, beyond plainly remembering — and
                is it still itself afterwards? The day&apos;s memories yield a
                tension; the tension yields a dream; the dream returns as
                typed, inspectable records — and its certified affect is
                injected into the persona&apos;s live Chatterbox voice —
                emotion tags, conversation tone — identity held stable. Four
                sealed arms
                (flat / memory-only / dream / shuffled-dream) decide whether
                the dream earns its keep. &quot;No&quot; is a real answer.{' '}
                <span className="lore">
                  Embry, Kai, and Horus Lupercal are the resident personas —
                  long-lived agent identities with durable memory and trained
                  voices. Below: nine real pipeline surfaces from the live run
                  of 2026-06-29, then a rendered dream frame.
                </span>
              </p>
            </div>
            <DreamStepper phases={DREAM_PHASES} />
          </div>
        </section>

        {/* ===================== LEDGER ===================== */}
        <section id="ledger">
          <div className="wrap">
            <div className="ledger-grid">
              <div className="ledger-copy">
                <p className="kicker">
                  <b>03</b> The ledger
                </p>
                <h2 className="h2">
                  Every contract, including the ones without checks.
                </h2>
                <p className="ledger-count" aria-hidden="true">
                  {stats.skills}
                </p>
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
                {(
                  [
                    [
                      'roundtable-receipt',
                      'PREFLIGHT: PASS',
                      'Proves the agent that designed this page actually ran in the intended environment — not that a model merely claimed it did.',
                    ],
                    [
                      'live-audit',
                      'DRIFT: 0 · LIVE: 200/200',
                      'Proves the deployed site and the repository haven’t silently diverged.',
                    ],
                    [
                      'inventory-provenance',
                      `BUILD: ${commit}`,
                      'Proves the numbers above came from checked source state, not marketing copy.',
                    ],
                  ] as const
                ).map(
                  ([id, callout, proves]) =>
                    receiptArtifacts[id] && (
                      <ReceiptTicket
                        key={id}
                        id={id}
                        title={receiptArtifacts[id].title}
                        callout={callout}
                        proves={proves}
                        body={receiptArtifacts[id].body}
                        caption={receiptArtifacts[id].caption}
                      />
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
                <h2 className="h2">
                  An unusual path, on purpose.
                  <UnusualPath />
                </h2>
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
                  needed both halves of the job. Good fits:
                </p>
                <ul className="fits">
                  <li>
                    <b>Stalled multi-agent orchestration</b> — pipelines that
                    demo well and drift in production.
                  </li>
                  <li>
                    <b>Zero-trust &amp; compliance blockers</b> — work that
                    can&apos;t ship without audit trails and evidence.
                  </li>
                  <li>
                    <b>Bespoke multimodal &amp; generative workflows</b> — where
                    the work demands technical rigor and aesthetic polish at
                    once.
                  </li>
                </ul>
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
