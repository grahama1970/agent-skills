import heroContradiction from '@/hero-contradiction.json';
import { HeroContradictionPlate } from '@/components/hero-contradiction-plate';
import { PersonaDreamCase } from '@/components/cases/persona-dream-case';
import { SpartaCase } from '@/components/cases/sparta-case';
import { TauCase } from '@/components/cases/tau-case';
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
const sparta = projectBySlug.get('sparta-explorer') ?? content.projects[1];
const personaDream = projectBySlug.get('persona-dream') ?? content.projects[2];
const battle = projectBySlug.get('battle') ?? content.projects[3];
const supporting = ['sparta-explorer', 'persona-dream', 'battle'];

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
          <div className="wrap">
            <TauCase project={flagship} />
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
            <div className="supporting-cases" data-supporting-projects={supporting.join(',')}>
              <SpartaCase project={sparta} />
              <PersonaDreamCase project={personaDream} />
              <article className="support-index support-index--single">
                <a
                  href={battle.href}
                  data-qid={`supporting:source:${battle.slug}`}
                  data-qs-action="SUPPORTING_OPEN_SOURCE"
                  title={`Open ${battle.name} source`}
                >
                  <span>03</span>
                  <b>{battle.name}</b>
                  <em>{battle.question}</em>
                </a>
              </article>
            </div>
            <ol className="support-index support-index--mobile" aria-label="Supporting investigations">
              {[sparta, personaDream, battle].map((project, index) => (
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
