import heroContradiction from '@/hero-contradiction.json';
import { HeroContradictionPlate } from '@/components/hero-contradiction-plate';
import { KeyboardNav } from '@/components/keyboard-nav';
import { SiteNav } from '@/components/site-nav';
import { UnusualPath } from '@/components/unusual-path';
import content from '@/content.json';
import { HomeJsonLd } from '@/components/home-json-ld';
import inventory from '@/inventory.json';

const REPO = 'https://github.com/grahama1970/agent-skills';

const projectBySlug = new Map<string, (typeof content.projects)[number]>();
for (const project of content.projects) {
  projectBySlug.set(project.slug, project);
}
const flagship = projectBySlug.get('tau') ?? content.projects[0];
const supporting = ['sparta-explorer', 'persona-dream', 'battle']
  .map((slug) => projectBySlug.get(slug))
  .filter((project): project is NonNullable<typeof project> => Boolean(project));

const TRACK = [
  { t: 'Composer', d: 'Commercial work for Adidas, Pepsi, X-Games.' },
  { t: 'Executive producer, Sony', d: 'God of War: Ascension campaign — Webby-recognized, 80-person productions.' },
  { t: 'DARPA ARCOS', d: 'Principal data scientist and technical lead, alongside Honeywell, Lockheed Martin, MIT, GE, SRI.' },
  { t: 'AFRL “Hacker” challenge coin', d: 'Recognition out of that work.' },
  { t: 'Lean 4 formal methods', d: 'Proof discipline carried into agent design.' },
];

export default function Home() {
  const { stats, commit, as_of } = inventory;

  return (
    <>
      <HomeJsonLd />
      <div className="glow" aria-hidden="true" />
      <div className="grain" aria-hidden="true" />
      <div className="page">
        <SiteNav />
        <KeyboardNav />

        <section className="hero ruledbg" id="top" data-home-beat="proposition">
          <div className="wrap">
            <div className="hero-grid">
              <div className="hero-main">
                <h1 className="rise" style={{ ['--d' as string]: '.12s' }}>
                  I build agent systems that can <span className="it">prove</span> what they did.
                </h1>
                <div className="hero-actions rise" style={{ ['--d' as string]: '.4s' }}>
                  <a
                    className="btn"
                    href={heroContradiction.primary_action.href}
                    data-qid="hero:action:artifact"
                    data-qs-action="HERO_OPEN_CONTRADICTION_ARTIFACT"
                    title="Open the contradiction source receipt"
                  >
                    {heroContradiction.primary_action.label} <span className="arrow">→</span>
                  </a>
                  <a
                    className="btn ghost"
                    href={heroContradiction.secondary_action.href}
                    data-qid="hero:action:repo"
                    data-qs-action="HERO_OPEN_REPO"
                    title="Open the agent-skills repository on GitHub"
                  >
                    Read the code
                  </a>
                </div>
              </div>
              <HeroContradictionPlate />
            </div>
          </div>
        </section>

        <section id="flagship" className="home-beat flagship-beat" data-home-beat="flagship">
          <div className="wrap flagship-grid">
            <div className="beat-copy">
              <p className="kicker">
                <b>01</b> Dominant investigation
              </p>
              <h2 className="h2">{flagship.question}</h2>
              <p className="lede">{flagship.why}</p>
              <dl className="case-boundary">
                <div>
                  <dt>Source</dt>
                  <dd>
                    <a
                      href={flagship.href}
                      data-qid={`flagship:source:${flagship.slug}`}
                      data-qs-action="FLAGSHIP_OPEN_SOURCE"
                      title={`Open ${flagship.name} source`}
                    >
                      {flagship.href.replace('https://github.com/', 'github.com/')}
                    </a>
                  </dd>
                </div>
                <div>
                  <dt>Boundary</dt>
                  <dd>One flagship example; not a claim that every skill has equal proof depth.</dd>
                </div>
              </dl>
            </div>
            <a
              className="flagship-artifact"
              href={flagship.href}
              data-qid={`flagship:artifact:${flagship.slug}`}
              data-qs-action="FLAGSHIP_OPEN_ARTIFACT"
              title={`Open ${flagship.name} artifact source`}
              style={{ ['--img' as string]: `url('/projects/${flagship.slug}.webp')` }}
            >
              <span>{flagship.name}</span>
              <b>{flagship.blurb}</b>
            </a>
          </div>
        </section>

        <section id="supporting" className="home-beat supporting-beat" data-home-beat="supporting">
          <div className="wrap">
            <div className="supporting-head">
              <p className="kicker">
                <b>02</b> Supporting investigations
              </p>
              <a
                href="/explore.html"
                data-qid="supporting:link:explore"
                data-qs-action="SUPPORTING_OPEN_EXPLORE"
                title="Open the full project explorer"
              >
                Full explorer
              </a>
            </div>
            <ol className="support-index">
              {supporting.map((project, index) => (
                <li key={project.slug}>
                  <a
                    href={project.href}
                    data-qid={`supporting:source:${project.slug}`}
                    data-qs-action="SUPPORTING_OPEN_SOURCE"
                    title={`Open ${project.name} source`}
                  >
                    <span>{String(index + 1).padStart(2, '0')}</span>
                    <b>{project.name}</b>
                    <em>{project.question}</em>
                  </a>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="proof-method" className="home-beat proof-preview" data-home-beat="proof-method">
          <div className="wrap proof-preview-grid">
            <div>
              <p className="kicker">
                <b>03</b> Proof method
              </p>
              <h2 className="h2">The method is claim, artifact, rule, boundary.</h2>
            </div>
            <ol className="method-steps">
              <li>
                <span>Claim</span>
                <b>State what the system says happened.</b>
              </li>
              <li>
                <span>Artifact</span>
                <b>Attach the immutable locator and digest.</b>
              </li>
              <li>
                <span>Boundary</span>
                <b>Name what the evidence does not prove.</b>
              </li>
            </ol>
            <a
              className="text-link"
              href="/how-proof-works.html"
              data-qid="proof-preview:link:how-proof-works"
              data-qs-action="PROOF_PREVIEW_OPEN_DEPTH"
              title="Open the proof-method route"
            >
              See the complete proof walkthrough →
            </a>
          </div>
        </section>

        <section id="about" className="home-beat about-beat" data-home-beat="person">
          <div className="wrap about-grid">
            <div className="about-copy">
              <p className="kicker">
                <b>04</b> Person and accountability
              </p>
              <h2 className="h2">
                An unusual path, on purpose.
                <UnusualPath />
              </h2>
              <div className="thesis">
                <p>An unconventional path is an advantage on problems with no playbook.</p>
              </div>
              <p className="lede" style={{ marginTop: '1.6rem' }}>
                One person also means direct accountability: the person you meet
                is the person who investigates, architects, builds, and answers
                for the result.
              </p>
              <p className="accountability">Bring me the project you shelved.</p>
              <p className="person-actions">
                <a
                  className="btn"
                  href="mailto:graham@grahama.co"
                  data-qid="person:action:email"
                  data-qs-action="PERSON_EMAIL"
                  title="Email graham@grahama.co"
                >
                  graham@grahama.co <span className="arrow">→</span>
                </a>
                <a
                  className="btn ghost"
                  href="/resume"
                  data-qid="person:action:resume"
                  data-qs-action="PERSON_OPEN_RESUME"
                  title="Open résumé"
                >
                  Résumé
                </a>
              </p>
            </div>
            <div className="track">
              {TRACK.map((stop) => (
                <div className="stop" key={stop.t}>
                  <p className="st">{stop.t}</p>
                  <p className="sd">{stop.d}</p>
                </div>
              ))}
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
              </div>
              <div className="foot-b">
                <p className="lab">Inventory</p>
                <p className="prov" style={{ marginTop: 0 }}>
                  {stats.skills} skill contracts
                  <br />
                  {stats.sanity} with sanity checks
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
