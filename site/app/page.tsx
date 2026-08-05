import { CopyEmail } from '@/components/copy-email';
import { ReceiptsSection } from '@/components/receipts-section';
import { SiteNav } from '@/components/site-nav';
import { SkillMosaic } from '@/components/skill-mosaic';
import { TelemetryBar } from '@/components/telemetry-bar';
import { WorkGrid } from '@/components/work-grid';
import inventory from '@/inventory.json';

const REPO = 'https://github.com/grahama1970/agent-skills';

const DREAM_PHASES = [
  { f: 'phase01-idea-memory-residue', c: '01 · Memory residue becomes an idea' },
  { f: 'phase02-story', c: '02 · The story takes shape' },
  { f: 'phase03-crew', c: '03 · A crew is cast' },
  { f: 'phase04-contact-sheets', c: '04 · Contact sheets are reviewed' },
  { f: 'phase05-voices', c: '05 · Voices are trained' },
  { f: 'phase06-script', c: '06 · The script locks' },
  { f: 'phase07-storyboard', c: '07 · Storyboard panels pass review' },
  { f: 'phase08-media-lock', c: '08 · Media locks with receipts' },
  { f: 'phase09-video-provider-current', c: '09 · Providers are scored and chosen' },
  { f: 'dream-panel', c: 'A frame from the finished dream — rendered June 2026' },
];

export default function Home() {
  const { stats, commit, as_of } = inventory;
  return (
    <>
      <SiteNav />
      <main id="top" className="mx-auto max-w-[1440px] px-6 md:px-10">
        <section className="grid gap-10 border-b border-line py-16 md:grid-cols-[3fr_2fr] md:py-24">
          <div>
            <h1 className="mb-8 max-w-[14ch] text-balance font-display text-[clamp(3.2rem,6.8vw,7.5rem)] leading-[0.95]">
              <span className="hero-line">
                <span style={{ ['--d' as string]: '0ms' }}>I build agent</span>
              </span>
              <span className="hero-line">
                <span style={{ ['--d' as string]: '90ms' }}>systems that can</span>
              </span>
              <span className="hero-line">
                <span style={{ ['--d' as string]: '180ms' }}>prove what they did.</span>
              </span>
            </h1>
            <p className="hero-sub mb-4 max-w-[62ch] text-[18px]">
              A one-person practice with an unusual résumé: commercial composer
              for Adidas and Pepsi, Webby-recognized producer for Sony, DARPA
              technical lead alongside Lockheed Martin and MIT. High-end
              creative and hard technical work — delivered by the same person,
              shipped as working code, in public.
            </p>
            <p className="text-[16px]">
              <a
                href="mailto:graham@grahama.co"
                data-qid="hero:link:email"
                data-qs-action="HERO_EMAIL"
                title="Email graham@grahama.co"
                className="text-accent underline underline-offset-4"
              >
                graham@grahama.co
              </a>
              <span className="mx-3 text-mute">·</span>
              <a
                href={REPO}
                data-qid="hero:link:repo"
                data-qs-action="HERO_OPEN_REPO"
                title="Open the agent-skills repository on GitHub"
                className="text-accent underline underline-offset-4"
              >
                github.com/grahama1970/agent-skills
              </a>
            </p>
          </div>
        </section>

        <div className="border-b border-line py-5">
          <TelemetryBar />
        </div>

        <section id="work" className="surface scroll-mt-14 border-b border-line py-16 md:py-20">
          <h2 className="mb-2 font-display text-[clamp(2rem,3.6vw,3.4rem)]">The work</h2>
          <p className="mb-3 max-w-[64ch] text-mute">
            Ten running systems, each an open research question with code
            behind it. Every entry links to its source.
          </p>
          <p className="machine mb-10 text-mute">
            status badges computed from the repo inventory @ {commit} — not
            asserted
          </p>
          <WorkGrid />
        </section>

        <section id="dream" className="surface scroll-mt-14 border-b border-line py-16 md:py-20">
          <h2 className="mb-2 font-display text-[clamp(2rem,3.6vw,3.4rem)]">
            A dream, assembled
          </h2>
          <p className="mb-3 max-w-[64ch] text-mute">
            persona-dream turns an agent&apos;s accumulated memory into a
            reviewed, receipt-gated film. These are real frames from the
            pipeline — nine phases of actual product UI, then a frame from a
            finished dream. Scroll through the run.
          </p>
          <p className="machine mb-8 text-mute">
            captured from the live run of 2026-06-29 · every PASS chip is a
            real review verdict
          </p>
          <div className="dream-scroller">
            <div className="dream-frames">
              {DREAM_PHASES.map((d, i) => (
                <figure
                  key={d.f}
                  className="dream-frame"
                  style={{
                    animationRange: `contain ${i * 9.5}% contain ${i * 9.5 + 12}%`,
                  }}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={`/dream/${d.f}.webp`} alt={d.c} loading="lazy" />
                  <figcaption className="machine">{d.c}</figcaption>
                </figure>
              ))}
            </div>
          </div>
        </section>

        <section id="index" className="surface scroll-mt-14 border-b border-line py-16 md:py-20">
          <h2 className="mb-2 font-display text-[clamp(2rem,3.6vw,3.4rem)]">
            Every skill, including the gaps
          </h2>
          <p className="mb-8 max-w-[64ch] text-mute">
            One cell per SKILL.md contract in the public repo, generated from
            commit <span className="machine">{commit}</span>, grouped by the
            taxonomy in the data. Filled cells have a sanity check; outlined
            cells don&apos;t yet. Showing the holes is the point — no claim
            ships without a receipt, including this one.
          </p>
          <SkillMosaic />
        </section>

        <ReceiptsSection />

        <section id="about" className="surface scroll-mt-14 border-b border-line py-16 md:py-20">
          <h2 className="mb-3 font-display text-[clamp(2rem,3.6vw,3.4rem)]">
            An unusual path, on purpose
          </h2>
          <div className="max-w-[64ch]">
            <p className="mb-4">
              I scored commercials for Adidas, Pepsi, and the X-Games. I ran
              80-person interactive productions as Executive Producer on
              Sony&apos;s <em>God of War: Ascension</em> campaign
              (Webby-recognized). Then I spent four years as Principal Data
              Scientist and technical lead on DARPA ARCOS, building the
              knowledge-graph and LLM reasoning system for automated
              certification of mission-critical software — alongside Honeywell,
              Lockheed Martin, MIT, GE Research, and SRI.
            </p>
            <p className="mb-4">
              That path is the point. Traditional teams hand hard problems to
              specialists who have seen them before. The problems I take are
              the ones nobody has seen before — where the playbook doesn&apos;t
              exist yet. Composition, production, and certification taught the
              same discipline from different directions: hold a large system in
              your head, make its structure explicit, and prove that it works.
              It&apos;s why my systems are architected, not stapled together.
              Available for engagements and full-time roles.
            </p>
            <p className="machine text-mute">
              DARPA ARCOS · AFRL &quot;Hacker&quot; challenge coin · Lean 4
              formal methods · 15+ years hand-coding · ITAR-experienced ·{' '}
              <a
                href={`${REPO}/blob/main/RESUME.md`}
                data-qid="about:link:resume"
                data-qs-action="ABOUT_OPEN_RESUME"
                title="Open RESUME.md on GitHub"
                className="text-accent no-underline hover:underline"
              >
                full résumé ↗
              </a>
            </p>
          </div>
        </section>

        <section id="contact" className="surface scroll-mt-14 py-16 md:py-20">
          <h2 className="mb-3 font-display text-[clamp(2rem,3.6vw,3.4rem)]">
            Bring me the project you shelved
          </h2>
          <p className="mb-4 max-w-[62ch]">
            If your team wants an agentic system it can&apos;t staff — or has a
            prototype that never survived contact with production — that&apos;s
            the work I take.
          </p>
          <p className="mb-6 max-w-[62ch]">
            One person also means a different deal than a consulting firm: the
            person you talk to is the person who architects, builds, and
            answers for the result — no account layer, no handoffs, no diffused
            accountability. One senior rate instead of an army&apos;s overhead.
            The repo above is the working evidence behind the{' '}
            <a
              href={`${REPO}/blob/main/RESUME.md`}
              data-qid="contact:link:resume"
              data-qs-action="CONTACT_OPEN_RESUME"
              title="Open RESUME.md on GitHub"
              className="text-accent underline underline-offset-4"
            >
              résumé
            </a>
            .
          </p>
          <CopyEmail className="inline-block bg-ink px-6 py-3 text-[15px] text-paper no-underline hover:bg-accent" />
        </section>
      </main>
    </>
  );
}
