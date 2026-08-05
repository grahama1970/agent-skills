import { SiteNav } from '@/components/site-nav';
import { SkillMosaic } from '@/components/skill-mosaic';
import content from '@/content.json';
import inventory from '@/inventory.json';

const REPO = 'https://github.com/grahama1970/agent-skills';

export default function Home() {
  const { stats, commit, as_of } = inventory;
  return (
    <>
      <SiteNav />
      <main id="top" className="mx-auto max-w-[1080px] px-6">
        <section className="grid gap-10 border-b border-line py-16 md:grid-cols-[3fr_2fr] md:py-20">
          <div>
            <h1 className="mb-6 text-balance font-display text-5xl leading-[1.08] md:text-6xl">
              I build agent systems that can prove what they did.
            </h1>
            <p className="mb-4 max-w-[58ch] text-[18px]">
              A one-person practice with an unusual résumé: commercial composer
              for Adidas and Pepsi, Webby-recognized producer for Sony, DARPA
              technical lead alongside Lockheed Martin and MIT. High-end
              creative and hard technical work — delivered by the same person,
              shipped as working code, in public. Available for engagements and
              full-time roles.
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
              <span className="mx-3 text-line">·</span>
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
          <div className="machine self-end border-l-2 border-line pl-5 text-mute">
            <div className="mb-1 text-ink">repo inventory — generated, not typed</div>
            <div>{stats.skills} skill contracts (SKILL.md)</div>
            <div>{stats.sanity} with sanity checks</div>
            <div>{stats.agents} bounded agent definitions</div>
            <div className="mt-2">
              source{' '}
              <a
                href={`${REPO}/commit/${commit}`}
                data-qid="hero:link:commit"
                data-qs-action="HERO_OPEN_COMMIT"
                title={`Open commit ${commit} on GitHub`}
                className="text-accent no-underline hover:underline"
              >
                {commit}
              </a>{' '}
              · {as_of} · {inventory.generator}
            </div>
          </div>
        </section>

        <section className="border-b border-line py-10">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            {content.projects.map((p) => (
              <a
                key={p.slug}
                href={`#${p.slug}`}
                data-qid={`sheet:thumb:${p.slug}`}
                data-qs-action="SHEET_GOTO_PROJECT"
                title={`Jump to ${p.name}`}
                className="block"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/projects/${p.slug}.webp`}
                  alt={`${p.name} project card`}
                  loading="lazy"
                  className="aspect-[16/10] w-full rounded-sm border border-line object-cover"
                />
              </a>
            ))}
          </div>
        </section>

        <section id="work" className="scroll-mt-6 border-b border-line py-16">
          <h2 className="mb-2 font-display text-3xl">The work</h2>
          <p className="mb-10 max-w-[60ch] text-mute">
            Ten running systems, each an open research question with code
            behind it. Every entry links to its source.
          </p>
          <ol className="flex flex-col gap-14">
            {content.projects.map((p, i) => (
              <li
                key={p.slug}
                id={p.slug}
                className={`grid scroll-mt-6 items-start gap-6 md:grid-cols-[2fr_3fr] ${
                  i % 2 ? 'md:[&>a]:order-2' : ''
                }`}
              >
                <a
                  href={p.href}
                  data-qid={`work:image:${p.slug}`}
                  data-qs-action="WORK_OPEN_PROJECT"
                  title={`Open ${p.name} on GitHub`}
                  className="block"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={`/projects/${p.slug}.webp`}
                    alt={`${p.name} project card`}
                    loading="lazy"
                    className="w-full rounded-sm border border-line"
                  />
                </a>
                <div>
                  <div className="machine mb-1 text-mute">
                    {String(i + 1).padStart(2, '0')}
                  </div>
                  <h3 className="mb-2 font-display text-2xl">{p.name}</h3>
                  <p className="mb-2 font-display text-[19px] italic text-mute">
                    {p.question}
                  </p>
                  <p className="mb-3 max-w-[52ch] text-[16px]">{p.blurb}</p>
                  <p className="machine">
                    <a
                      href={p.href}
                      data-qid={`work:link:${p.slug}`}
                      data-qs-action="WORK_OPEN_README"
                      title={`Open the ${p.name} README on GitHub`}
                      className="text-accent no-underline hover:underline"
                    >
                      README ↗
                    </a>
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section id="index" className="scroll-mt-6 border-b border-line py-16">
          <h2 className="mb-2 font-display text-3xl">
            Every skill, including the gaps
          </h2>
          <p className="mb-8 max-w-[60ch] text-mute">
            One cell per SKILL.md contract in the public repo, generated from
            commit <span className="machine">{commit}</span>. Filled cells have
            a sanity check; outlined cells don&apos;t yet. Showing the holes is
            the point — no claim ships without a receipt, including this one.
          </p>
          <SkillMosaic />
        </section>

        <section id="about" className="scroll-mt-6 border-b border-line py-16">
          <h2 className="mb-3 font-display text-3xl">An unusual path, on purpose</h2>
          <div className="max-w-[62ch]">
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
            </p>
            <p className="machine text-mute">
              DARPA ARCOS · AFRL &quot;Hacker&quot; challenge coin · Lean 4
              formal methods · 15+ years hand-coding · ITAR-experienced ·{' '}
              <a
                href="https://github.com/grahama1970/agent-skills/blob/main/RESUME.md"
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

        <section id="contact" className="scroll-mt-6 py-16">
          <h2 className="mb-3 font-display text-3xl">
            Bring me the project you shelved
          </h2>
          <p className="mb-6 max-w-[58ch]">
            If your team wants an agentic system it can&apos;t staff — or has a
            prototype that never survived contact with production — that&apos;s
            the work I take. The repo above is the working evidence behind the{' '}
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
          <a
            href="mailto:graham@grahama.co"
            data-qid="contact:action:email"
            data-qs-action="CONTACT_EMAIL"
            title="Email graham@grahama.co"
            className="inline-block rounded-sm bg-ink px-6 py-3 text-[15px] text-paper no-underline hover:bg-accent"
          >
            Email graham@grahama.co
          </a>
        </section>
      </main>
    </>
  );
}
