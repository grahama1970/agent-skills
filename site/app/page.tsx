import { CommandPalette } from '@/components/command-palette';
import { ContactCta } from '@/components/contact-cta';
import { Kinetic } from '@/components/kinetic';
import { ProjectCard, type Project } from '@/components/project-card';
import { SiteNav } from '@/components/site-nav';
import { StatCounter } from '@/components/stat-counter';
import { Trace } from '@/components/trace';
import content from '@/content.json';

const PROJECTS: Project[] = content.projects;
const STATS = content.stats;

const PILLARS = [
  {
    name: 'multi-agent orchestration',
    body: 'Creator–reviewer–judge loops compiled as verifiable DAGs. Roundtables of frontier models that deliberate, dissent, and converge — with every round’s evidence shared equally and every verdict attributable.',
  },
  {
    name: 'self-improving skill ecosystems',
    body: 'Hundreds of composable agent skills under continuous evaluation: adversarial test harnesses, drift monitors, and CI that grades the agents — not just the code.',
  },
  {
    name: 'persistent agent memory',
    body: 'Graph-backed memory that survives the session: BM25 + semantic + multi-hop recall over everything the agents have learned, so week two starts smarter than week one.',
  },
  {
    name: 'autonomy that runs unattended',
    body: 'Overnight goals with fail-closed stop conditions, watchdogs, bounded retries, and receipts for every action — agents you can leave alone because they can prove themselves.',
  },
];

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-4 font-mono text-xs uppercase tracking-[0.18em] text-accent">
      {children}
    </p>
  );
}

export default function Home() {
  return (
    <>
      <SiteNav />
      <main id="top" className="px-6 md:ml-[200px] md:px-12">
        <section className="mx-auto max-w-[70ch] border-b border-line py-20">
          <Eyebrow>Applied research engineering · agentic systems</Eyebrow>
          <h1 className="mb-6 text-balance font-display text-4xl leading-[1.14] tracking-tight md:text-5xl">
            <Kinetic text="We run the agent experiments most teams" />
            <Kinetic text="can't afford to attempt." startDelay={0.45} dim />
          </h1>
          <p className="text-[19px]">
            Multi-agent orchestration, self-improving skill ecosystems, and
            verified autonomy — taken from paper to production discipline:
            systems that run overnight, unattended, and prove what they did.
          </p>
          <CommandPalette />
          <Trace />
        </section>

        <section id="build" className="reveal ruled mx-auto max-w-[70ch] scroll-mt-8 border-b border-line py-20">
          <Eyebrow>What we build</Eyebrow>
          <h2 className="mb-4 text-balance font-display text-2xl">
            Research that stays running
          </h2>
          <p className="mb-6 text-mute">
            Most labs can pose these questions; most product teams can ship
            software. The rare thing is both: exploratory systems held to
            operations discipline — watchdogs, bounded retries, fail-closed
            stops, receipts.
          </p>
          <div className="flex flex-col gap-3.5">
            {PILLARS.map((p) => (
              <div key={p.name} className="rounded-md border border-line bg-panel px-6 py-5">
                <h3 className="mb-2 font-mono text-[15px] font-semibold tracking-wide text-accent">
                  {p.name}
                </h3>
                <p className="text-[15.5px] text-mute">{p.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section id="receipts" className="reveal ruled mx-auto max-w-[70ch] scroll-mt-8 border-b border-line py-20">
          <Eyebrow>Why trust it</Eyebrow>
          <h2 className="mb-5 text-balance font-display text-2xl">
            Verified, or it didn&apos;t happen
          </h2>
          <p className="mb-4">
            The failure mode of agentic AI isn&apos;t capability — it&apos;s
            unverifiable claims. Our discipline is simple and total: every agent
            action produces an artifact, every artifact is read back
            independently, and every claim is labeled <em>verified</em> or{' '}
            <em>inference</em>. Success responses are not proof. Green
            self-written tests are not proof. A receipt is proof.
          </p>
          <p className="text-mute">
            That discipline is why our systems can gate pull requests, run
            compliance evidence pipelines, and operate overnight without a human
            quality gate.
          </p>
          <div className="mt-7 grid grid-cols-2 gap-3.5 md:grid-cols-3">
            <StatCounter value={STATS.skills} label="skills with operating contracts (SKILL.md)" />
            <StatCounter value={STATS.sanity} label="ship a sanity.sh — cheap local proof" />
            <StatCounter value={STATS.agents} label="bounded agents with receipts & stop conditions" />
          </div>
          <p className="mt-5 text-sm text-mute">
            All of it public:{' '}
            <a
              href="https://github.com/grahama1970/agent-skills"
              data-qid="receipts:link:repo"
              data-qs-action="RECEIPTS_OPEN_REPO"
              title="Open the agent-skills repository on GitHub"
              className="text-accent underline underline-offset-2"
            >
              github.com/grahama1970/agent-skills
            </a>{' '}
            — the code and contracts are open; the private runtime (memory
            services, browser bindings, model gateways) stays private. A
            blueprint you can read, not a demo you have to believe.
          </p>
        </section>

        <section id="projects" className="reveal ruled mx-auto max-w-[70ch] scroll-mt-8 border-b border-line py-20">
          <Eyebrow>Live experiments</Eyebrow>
          <h2 className="mb-5 text-balance font-display text-2xl">
            Ten running systems, not ten slide decks
          </h2>
          <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2">
            {PROJECTS.map((p) => (
              <ProjectCard key={p.slug} project={p} />
            ))}
          </div>
        </section>

        <section id="contact" className="reveal ruled mx-auto max-w-[70ch] scroll-mt-8 py-20">
          <Eyebrow>Contact</Eyebrow>
          <h2 className="mb-5 text-balance font-display text-2xl">
            Bring us the project you shelved
          </h2>
          <p className="mb-5">
            If your team has an agentic system it wants but can&apos;t staff —
            or a prototype that never survived contact with production —
            that&apos;s the work I take. Available for engagements and full-time
            roles; the repo above is the working evidence behind the{' '}
            <a
              href="https://github.com/grahama1970/agent-skills/blob/main/RESUME.md"
              data-qid="contact:link:resume"
              data-qs-action="CONTACT_OPEN_RESUME"
              title="Open RESUME.md on GitHub"
              className="text-accent underline underline-offset-2"
            >
              resume
            </a>
            .
          </p>
          <ContactCta />
        </section>
      </main>
    </>
  );
}
