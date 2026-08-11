import artifacts from '@/artifacts.json';
import lineage from '@/generated/battle-lineage.json';
import { HeroLineage, type HeroLineageData } from '@/components/hero-lineage';
import { HeroProofBridge } from '@/components/hero-proof-bridge';
import { ResearchMap } from '@/components/research-map';
import { ProofLegend } from '@/components/proof-legend';
import {
  DeferredCapabilitySearch,
  DeferredKeyboardNav,
  DeferredReceiptTicket,
} from '@/components/home-deferred-surfaces';
import { SiteNav } from '@/components/site-nav';
import { StripVideo } from '@/components/strip-video';
import { UnusualPath } from '@/components/unusual-path';
import { TauCase } from '@/components/cases/tau-case';
import content from '@/content.json';
import { HomeJsonLd } from '@/components/home-json-ld';
import inventory from '@/inventory.json';
import visibility from '@/project-visibility.json';

const REPO = 'https://github.com/grahama1970/agent-skills';

/** Per-card collage placement + tint from the winning comp. */
const SUPPORTING_SLUGS = ['sparta-explorer', 'persona-dream', 'battle'] as const;

const PROJECT_VISUALS: Record<string, { cls: string; tint: string; img?: string; decode?: string }> = {
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

const TRACK = [
  { t: 'Composer', d: 'Commercial work for Adidas, Pepsi, X-Games.' },
  { t: 'Executive producer, Sony', d: 'God of War: Ascension campaign — Webby-recognized, 80-person productions.' },
  { t: 'DARPA ARCOS', d: 'Principal data scientist and technical lead, alongside Honeywell, Lockheed Martin, MIT, GE, SRI.' },
  { t: 'AFRL “Hacker” challenge coin', d: 'Recognition out of that work.' },
  { t: 'Lean 4 formal methods', d: 'Proof discipline carried into agent design.' },
  { t: 'This practice', d: 'Agent systems that produce their own evidence — shipped as working code, in public.' },
];

type ReceiptArtifact = {
  id: 'roundtable-receipt' | 'live-audit' | 'inventory-provenance';
  title: string;
  capture_status: 'captured' | 'unavailable';
  judgment: string;
  proves: string;
  does_not_prove: string;
  body: string;
  caption: string;
  unavailable_reason?: string;
};

const RECEIPT_IDS: ReceiptArtifact['id'][] = [
  'roundtable-receipt',
  'live-audit',
  'inventory-provenance',
];

const skillFlags = new Map(
  (inventory.skills as { n: string; s: boolean }[]).map((s) => [s.n, s.s]),
);

type ContentProject = (typeof content.projects)[number];
type VisibilityProject = {
  slug: string;
  visibility: string;
  href: string | null;
  evidence_access?: string;
};

export default function Home() {
  const { stats, commit, as_of } = inventory;
  const receiptArtifacts = Object.fromEntries(
    (artifacts.artifacts as ReceiptArtifact[]).map((a) => [a.id, a]),
  ) as Record<ReceiptArtifact['id'], ReceiptArtifact>;
  const capturedReceiptCount = (artifacts.artifacts as ReceiptArtifact[]).filter(
    (a) => a.capture_status === 'captured',
  ).length;
  const projectBySlug = new Map(content.projects.map((p) => [p.slug, p]));
  const visibilityBySlug = new Map(
    (visibility.projects as VisibilityProject[]).map((v) => [v.slug, v]),
  );
  const tauProject = projectBySlug.get('tau');
  const supportingProjects = SUPPORTING_SLUGS
    .map((slug) => projectBySlug.get(slug))
    .filter((p): p is ContentProject => Boolean(p));
  return (
    <>
      <HomeJsonLd />
      <main className="page">
        <SiteNav />
        <DeferredKeyboardNav />

        {/* ===================== HERO ===================== */}
        <section className="hero" id="top">
          <div className="wrap">
            <div className="hero-grid">
              <div className="hero-main">
                <p className="eyebrow">
                  <span className="dot" /> One-person applied R&amp;D practice{' '}
                  <span aria-hidden="true">/</span> agent systems, formal
                  methods, evidence
                </p>
                <h1>
                  I build agent systems that can{' '}
                  <span className="it proof-origin" data-proof-origin>
                    prove
                  </span>{' '}
                  what they did.
                </h1>
                <p className="hero-repo-model">
                  This site explains the work. The public{' '}
                  <a
                    href={REPO}
                    data-qid="hero:link:repo-inline"
                    data-qs-action="HERO_OPEN_REPO_INLINE"
                    title="Open the public agent-skills repository on GitHub"
                  >
                    <code>agent-skills</code>
                  </a>{' '}
                  repository holds the source.
                </p>
                <p className="hero-outcomes">
                  I take on hard-to-staff agent, compliance, and multimodal R&amp;D
                  and deliver working source, deterministic checks, runbooks,
                  receipts, and explicit limits your team can inspect and own.
                </p>
                <p className="hero-repo-model hero-repo-model--follow">
                  Browse here first, then inspect the source when you want the
                  contracts, code, checks, receipts, and visible gaps.
                </p>
                <p className="hero-bio">
                  An unusual{' '}
                  <a
                    href="/resume"
                    data-qid="hero:link:resume-receipt"
                    data-qs-action="HERO_OPEN_RESUME_RECEIPT"
                    title="The résumé — the receipt for these credentials"
                    style={{ color: 'var(--brass)', textDecoration: 'underline', textUnderlineOffset: '2px' }}
                  >
                    résumé
                  </a>
                  : commercial composer for{' '}
                  <em style={{ ['--i' as string]: 1 }}>Adidas</em>{' '}
                  and <em style={{ ['--i' as string]: 2 }}>Pepsi</em>,
                  Webby-recognized producer for{' '}
                  <em style={{ ['--i' as string]: 3 }}>Sony</em>,{' '}
                  <em style={{ ['--i' as string]: 4 }}>DARPA</em> technical
                  lead alongside{' '}
                  <em style={{ ['--i' as string]: 5 }}>Lockheed Martin</em> and{' '}
                  <em style={{ ['--i' as string]: 6 }}>MIT</em>.
                  High-end creative and hard technical work, delivered by the
                  same person, shipped as working code, in public.
                </p>
                <div className="hero-actions">
                  <a
                    className="btn"
                    href="#contact"
                    data-qid="hero:action:describe-problem"
                    data-qs-action="HERO_DESCRIBE_PROBLEM"
                    title="Jump to the contact section"
                  >
                    Describe the problem <span className="arrow">→</span>
                  </a>
                  <a
                    className="btn ghost"
                    href="/how-proof-works"
                    data-qid="hero:action:proof-route"
                    data-qs-action="HERO_OPEN_PROOF_ROUTE"
                    title="Read how claims connect to source, checks, receipts, and gaps"
                  >
                    See how proof works →
                  </a>
                  <a
                    className="btn ghost"
                    href={REPO}
                    data-qid="hero:action:repo"
                    data-qs-action="HERO_OPEN_REPO"
                    title="Open the public agent-skills repository on GitHub"
                  >
                    Open the repository <span className="arrow">↗</span>
                  </a>
                </div>
              </div>
              <aside
                className="hero-side"
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
                      href="/ledger"
                      data-qid="rail:link:sanity"
                      data-qs-action="RAIL_GOTO_LEDGER"
                      title="Inspect the full coverage ledger, gaps included"
                    >
                      <span className="n">
                        {stats.sanity}
                        <small>
                          ({Math.round((stats.sanity / stats.skills) * 100)}%)
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
            aria-label="Horus Lupercal and Embry taking tea on a void-world terrace — a rendered persona-dream"
          >
            {/* Atmospheric dream band: poster by default; the clip loads + plays
                only on motion-allowed, non-save-data devices. */}
            <StripVideo />
            <figcaption>
              <b>Horus Lupercal &amp; Embry, taking tea in a dream</b>
            </figcaption>
          </figure>
          <p className="strip-note">
            Not a keyframe: a <em>rendered persona-dream</em>. Embry dreams a
            quiet argument with Horus about building SPARTA Explorer as a{' '}
            <em>campaign of proof</em>: no unsupported claim past the perimeter,
            no receipt pretending to be a verdict. The pipeline dreams it from her
            own memory residue, checks it&apos;s still her, and writes it back to
            memory —{' '}
            <a
              href="/explore"
              data-qid="strip:link:dream-study"
              data-qs-action="STRIP_OPEN_DREAM_STUDY"
              title="Open the Explore route for the persona-dream source and evidence state"
            >
              the source and evidence state are in Explore
            </a>
            .
          </p>
        </section>

        <hr className="rule" />

        {/* ===================== SEARCH ===================== */}
        <section id="search" className="search-band">
          <div className="wrap">
            <DeferredCapabilitySearch />
            <p className="depth-preview-link">
              Public repo map, project fit, and evidence access continue on{' '}
              <a
                href="/explore"
                data-qid="search:link:explore-depth"
                data-qs-action="SEARCH_OPEN_EXPLORE"
                title="Open the Explore route for the full repo map and evidence access"
              >
                the Explore route
              </a>
              .
            </p>
          </div>
        </section>

        {/* ===================== WORK ===================== */}
        <section id="work">
          <div className="wrap">
            <div className="work-head">
              <div>
                <p className="kicker">
                  <b>Tau</b> Selected investigations
                </p>
                <h2 className="h2">One dominant proof, three supporting systems.</h2>
              </div>
              <p className="count">preview here → full index one step deeper</p>
            </div>
            <ResearchMap />
            <ProofLegend />
            <div className="private-boundary" aria-label="Public and private work boundary">
              <p className="private-boundary__lead">
                Most current work is export-controlled or sensitive. The public
                pattern here is deliberately narrower: problem class, public
                artifact, what it proves, and what it does not prove. Private
                systems stay private.
              </p>
              <dl className="private-boundary__grid">
                <div>
                  <dt>Public</dt>
                  <dd>Owned/open skills, receipts, proof dossiers, and synthetic or product-owned visuals.</dd>
                </div>
                <div>
                  <dt>Private</dt>
                  <dd>Client names, program details, data, screenshots, private repos, and evidence counts.</dd>
                </div>
                <div>
                  <dt>Handoff</dt>
                  <dd>Source, checks, runbooks, and boundary notes delivered inside the client stack where practical.</dd>
                </div>
              </dl>
            </div>
            <div className="flagship-cases" aria-label="Flagship proof compositions">
              {tauProject && <TauCase project={tauProject} />}
            </div>
            <div className="cards selected-cards" aria-label="Three supporting investigations">
              {supportingProjects.map((p, i) => {
                const meta = PROJECT_VISUALS[p.slug];
                const external = !skillFlags.has(p.slug);
                // Automatic public/private: a private project links to its
                // curated public overview (never the private repo) and is
                // marked evidence-private. Generated by gen_visibility.py.
                const vis = visibilityBySlug.get(p.slug);
                const linkHref = vis?.href ?? p.href;
                const evidencePrivate = !!vis && vis.visibility !== 'public';
                const ghShort = linkHref
                  .replace('https://github.com/', 'github.com/')
                  .replace('/blob/main/skills/', '/…/')
                  .replace('/README.md', '');
                return (
                  <article
                    key={p.slug}
                    className={`card ${meta.cls} secondary`}
                    id={`project-${p.slug}`}
                  >
                    <a
                      href={linkHref}
                      data-qid={`work:card:${p.slug}`}
                      data-qs-action="WORK_OPEN_PROJECT"
                      title={`Open ${p.name} on GitHub`}
                      className="shot-link"
                    >
                      <div
                        className="shot"
                        style={{
                          ['--tint' as string]: meta.tint,
                        }}
                        role="img"
                        aria-label={p.slug === 'sparta-explorer' ? 'Sparta Explorer — governed evidence thread from program manager and engineer through policy gate to pilot, Embry OS' : `${p.name} — concept art`}
                      >
                        <img
                          className="shot-img"
                          src={`/projects/${meta.img ?? p.slug}.webp`}
                          alt=""
                          loading="lazy"
                          decoding="async"
                          aria-hidden="true"
                        />
                      </div>
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
                          data-qid={`work:repo:${p.slug}`}
                          data-qs-action="WORK_OPEN_REPO"
                          title={`Open ${p.name} repository on github.com`}
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
            <div className="work-depth-actions" aria-label="Full work depth">
              <a
                className="btn ghost"
                href="/explore"
                data-qid="work:action:open-explore"
                data-qs-action="WORK_OPEN_EXPLORE"
                title="Open the full project explorer"
              >
                Open the full explorer <span className="arrow">→</span>
              </a>
              <a
                className="btn ghost"
                href="/capabilities"
                data-qid="work:action:open-capabilities"
                data-qs-action="WORK_OPEN_CAPABILITIES"
                title="Inspect the generated discipline and capability evidence"
              >
                Inspect technical capability evidence <span className="arrow">→</span>
              </a>
            </div>
          </div>
        </section>

        {/* ===================== LEDGER ===================== */}
        <section id="ledger">
          <div className="wrap">
            <div className="ledger-preview">
              <div>
                <p className="kicker">
                  <b>Ledger</b> agent-skills source map
                </p>
                <h2 className="h2">
                  {stats.skills} public contracts; {stats.sanity} with sanity checks.
                </h2>
                <p className="lede" style={{ marginTop: '1.1rem' }}>
                  The full inventory is still public, including contract-only
                  entries and visible gaps. It now lives where a technical
                  inspector expects it: on a direct, reloadable route.
                </p>
              </div>
              <a
                className="btn"
                href="/ledger"
                data-qid="ledger:action:inspect-all"
                data-qs-action="LEDGER_OPEN_DEPTH"
                title="Inspect every public skill contract and gap"
              >
                Inspect all contracts <span className="arrow">→</span>
              </a>
            </div>
          </div>
        </section>

        <hr className="rule" />

        {/* ===================== HOW PROOF WORKS ===================== */}
        <section id="proof">
          <div className="wrap">
            <div className="proofx-head proofx-head--preview">
              <div>
                <p className="kicker">
                  <b>Tau</b> How proof works
                </p>
                <h2 className="h2">
                  One real run, from goal to receipt.
                </h2>
              </div>
              <p className="proofx-intro">
                Not a diagram of an idealised pipeline: the actual{' '}
                <span className="machine">tau</span> roundtable that designed
                this page, walked stage by stage. Each step resolves to a real
                immutable artifact you can hash-check, and each one says plainly
                what it does <em>not</em> prove.
              </p>
            </div>
            <a
              className="btn"
              href="/how-proof-works"
              data-qid="proof:action:open-depth"
              data-qs-action="PROOF_OPEN_DEPTH"
              title="Open the full proof route"
            >
              Open the proof route <span className="arrow">→</span>
            </a>
          </div>
        </section>

        <hr className="rule" />

        {/* ===================== RECEIPTS ===================== */}
        <section id="receipts">
          <div className="wrap">
            <div className="receipts-grid">
              <div className="receipts-copy">
                <p className="kicker">
                  <b>Receipts</b> Bounded evidence
                </p>
                <h2 className="h2">No claim ships without one.</h2>
                <p className="lede" style={{ marginTop: '1.1rem' }}>
                  {capturedReceiptCount === 3 ? 'Three excerpts' : `${capturedReceiptCount} captured excerpts`},
                  printed as they came out of
                  <span className="machine"> gen_artifacts.py</span>: a node
                  receipt from the roundtable run that designed this page, a
                  captured audit, and the provenance of the numbers above.
                  Missing sources stay visible as boundaries, not status widgets.
                </p>
              </div>
              <div className="tickets">
                {RECEIPT_IDS.map((id) => {
                  const receipt = receiptArtifacts[id];
                  return receipt.capture_status === 'captured' ? (
                      <DeferredReceiptTicket
                        key={id}
                        id={id}
                        title={receipt.title}
                        callout={receipt.judgment}
                        proves={receipt.proves}
                        doesNotProve={receipt.does_not_prove}
                        body={receipt.body}
                        caption={receipt.caption}
                      />
                    ) : (
                      <article className="receipt-boundary" key={id}>
                        <h3>{receipt.title}</h3>
                        <p className="callout">{receipt.judgment}</p>
                        <p>{receipt.unavailable_reason ?? receipt.caption}</p>
                        <p className="does-not-prove">{receipt.does_not_prove}</p>
                      </article>
                    );
                })}
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
                  <b>Person</b> Accountability
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
                  meet is the person who investigates, architects, builds, and
                  answers for the result. Available for
                  engagements and full-time roles —{' '}
                  <a
                    href="/resume"
                    data-qid="about:link:resume"
                    data-qs-action="ABOUT_OPEN_RESUME"
                    title="Open RESUME.md on GitHub"
                    style={{ color: 'var(--brass)', textDecoration: 'underline', textUnderlineOffset: '2px' }}
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
        <section className="closer" id="contact">
          <div className="wrap">
            <div className="closer-inner">
              <div className="a">
                <p className="kicker">
                  <b>Next</b> Evidence-first work
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
                    demo well but fail silently or drift in production.
                  </li>
                  <li>
                    <b>Zero-trust &amp; compliance blockers</b> — work that
                    can&apos;t ship without audit trails, receipts, and evidence.
                  </li>
                  <li>
                    <b>Platform-independent R&amp;D</b> — you need the work done
                    inside your stack, delivered as open code you own, with no
                    agency overhead and no vendor platform to adopt.
                  </li>
                  <li>
                    <b>Bespoke multimodal &amp; generative workflows</b> — where
                    the work demands technical rigor and aesthetic polish at
                    once.
                  </li>
                </ul>
                <p className="continuity-note">
                  Principal-led, not principal-dependent: the deliverable is
                  source your team owns, deterministic checks, runbooks, and
                  plain boundary notes so another engineer can continue the work.
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
                  href="/resume"
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
            <div className="foot-boundary">
              <p className="lab">Public scope &amp; data boundaries</p>
              <p className="boundary">
                This site and its open repositories contain reusable agent
                patterns, contracts, prompts, hooks, and evaluation workflows.
                They are intentionally decoupled from controlled, proprietary,
                ITAR-restricted, or sensitive operational data. Private runtime
                contexts, credentials, regulated artifacts, and deployment
                details remain strictly out-of-band.
              </p>
            </div>
          </div>
        </footer>
      </main>
    </>
  );
}
