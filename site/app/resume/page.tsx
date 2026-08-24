import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';
import { CalendlyPopupLink } from '@/components/calendly-scheduler';
import { CopyEmailButton } from '@/components/copy-email-button';
import { SiteNav } from '@/components/site-nav';
import calendly from '@/calendly.json';
import resume from '@/resume.json';

/**
 * /resume — the formal, skimmable resume.
 *
 * Deliberately the calmest page on the site: no constellation, no motion, no
 * hero. A recruiter skimming for twenty seconds should meet a document, not an
 * exhibit. Resume body copy comes from RESUME.md via scripts/gen_resume.py; the
 * download, scheduling, and employer-facts affordances are authored here. The
 * PDF, DOCX, and Markdown exports are one click away because the page is what
 * you link, the file is what you attach.
 */

const title = 'Résumé — Graham Anderson';
const description =
  'Principal AI Engineer specializing in LLM certification, graph-memory RAG systems, and ITAR/EAR-compliant defense R&D. U.S. Citizen.';

export const metadata: Metadata = {
  title: 'Graham Anderson | Principal AI Engineer & AI Architect',
  description,
  alternates: { canonical: '/resume' },
  openGraph: {
    title: 'Graham Anderson | Principal AI Engineer & AI Architect',
    description,
    url: 'https://grahama.co/resume',
    siteName: 'Graham Anderson - Portfolio & Resume',
    type: 'profile',
    firstName: 'Graham',
    lastName: 'Anderson',
    images: [{ url: '/og.png', width: 1200, height: 630, alt: 'Graham Anderson - Principal AI Engineer Resume Summary' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Graham Anderson | Principal AI Engineer & AI Architect',
    description,
    images: [{ url: '/og.png', alt: 'Graham Anderson - Principal AI Engineer Resume Summary' }],
  },
};

// Matches --ink, so mobile browser chrome continues the page rather than
// bracketing it with a colour the design system does not contain.
export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: dark)', color: '#0a0a0a' },
    { media: '(prefers-color-scheme: light)', color: '#ffffff' },
  ],
};

type Token = { t: string; v: string; href?: string };
type Block =
  | { kind: 'p'; inline: Token[] }
  | { kind: 'ul'; items: Token[][] }
  | { kind: 'role'; title: Token[]; period: string; blocks: Block[] };
type ResumeSection = { title: string; blocks: Block[] };

const TECH_TERMS = [
  'MITRE ATT&CK',
  'Knowledge Graphs',
  'GraphRAG',
  'ArangoDB',
  'Software Assurance',
  'NIST 800-53',
  'Lean 4',
  'D3FEND',
  'SPARTA',
  'Rust',
  'LLM',
  'RAG',
  'NIST',
  'CWE',
];

const ROLE_TECH_STACKS = [
  {
    match: 'Founder & Principal AI Engineer / Architect',
    skills: ['Rust', 'Python', 'ArangoDB', 'Lean 4', 'React/D3', 'NIST 800-53', 'ITAR'],
  },
  {
    match: 'Lead Research Scientist, Agentic Formal Methods',
    skills: ['Formal Methods', 'Lean 4', 'LLM', 'Aerospace Assurance', 'ITAR'],
  },
  {
    match: 'Principal Data Scientist & ACERT Technical Lead',
    skills: ['Knowledge Graphs', 'ArangoDB', 'LLM Certification', 'Software Assurance'],
  },
  {
    match: 'Data Scientist | grahamaco',
    skills: ['Python', 'Data Science', 'Production ML', 'Knowledge Graphs'],
  },
  {
    match: 'Earlier: Interactive Executive Producer & Composer',
    skills: ['Interactive Production', 'Campaigns', 'Large Teams', 'Audio'],
  },
];

const PUBLIC_WORK_META: Record<string, { title?: string; href?: string; facts: string; tags: string[] }> = {
  'agent-skills': {
    facts: '340+ skills · 90+ worker roles · ~85% sanity gates',
    tags: ['Python', 'Skills', 'Receipts'],
  },
  tau: {
    facts: 'Receipt-gated DAG harness',
    tags: ['Agents', 'Typed DAGs', 'Checks'],
  },
  pdf_oxide: {
    facts: '430 commits · ~137K lines added',
    tags: ['Rust', 'PDF', 'NIST'],
  },
  scillm: {
    href: 'https://github.com/grahama1970/agent-skills/tree/main/skills/scillm',
    facts: 'LLM gateway and routing skill',
    tags: ['LLMOps', 'Streaming', 'Fallbacks'],
  },
  'grahama.co': {
    facts: 'Static export · generated counts · d3-force graph',
    tags: ['Next.js', 'D3', 'Evidence'],
  },
  'extractor, anvil, fetcher, chatterbox voice-agent fork': {
    title: 'supporting cast',
    href: 'https://github.com/grahama1970/agent-skills/tree/main/skills',
    facts: 'Public skill contracts inside agent-skills',
    tags: ['Extraction', 'Tools', 'Voice'],
  },
};

function DownloadIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" x2="12" y1="15" y2="3" />
    </svg>
  );
}

function DocIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
      <path d="M14 2v6h6" />
      <path d="M8 13h8" />
      <path d="M8 17h5" />
    </svg>
  );
}

function MarkdownIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
      <path d="M14 2v4a2 2 0 0 0 2 2h4" />
      <path d="M10 9H8" />
      <path d="M16 13H8" />
      <path d="M16 17H8" />
    </svg>
  );
}

function CalendarIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M8 2v4" />
      <path d="M16 2v4" />
      <rect width="18" height="18" x="3" y="4" rx="2" />
      <path d="M3 10h18" />
    </svg>
  );
}

function TechPill({ children }: { children: ReactNode }) {
  return <span className="cv-tech-pill">{children}</span>;
}

function tokenText(tokens: Token[]) {
  return tokens.map((token) => token.v).join('');
}

function roleTechStack(title: Token[]) {
  const text = tokenText(title);
  return ROLE_TECH_STACKS.find((stack) => text.includes(stack.match))?.skills ?? [];
}

function publicWorkTitle(tokens: Token[]) {
  const firstLink = tokens.find((token) => token.t === 'link');
  if (firstLink) return firstLink.v;
  const text = tokenText(tokens);
  return text.split(' — ', 1)[0].trim();
}

function publicWorkDescription(tokens: Token[]) {
  const text = tokenText(tokens);
  const cut = text.indexOf(' — ');
  return cut >= 0 ? text.slice(cut + 3).trim() : text;
}

function RoleTechBadges({ skills }: { skills: string[] }) {
  if (!skills.length) return null;
  return (
    <div className="cv-role-tech" aria-label="Role technology stack">
      {skills.map((skill) => (
        <TechPill key={skill}>{skill}</TechPill>
      ))}
    </div>
  );
}

function TextWithTechPills({ text }: { text: string }) {
  const pattern = new RegExp(`(${TECH_TERMS.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'g');
  return (
    <>
      {text.split(pattern).map((part, i) => (
        TECH_TERMS.includes(part) ? <TechPill key={i}>{part}</TechPill> : <span key={i}>{part}</span>
      ))}
    </>
  );
}

function Inline({ tokens, ns = 'link' }: { tokens: Token[]; ns?: string }) {
  return (
    <>
      {tokens.map((tok, i) => {
        if (tok.t === 'link') {
          const external = /^https?:\/\//.test(tok.href ?? '');
          return (
            <a
              key={i}
              href={tok.href}
              // Slug of the label, not the token index: indices restart in every
              // block, which produced five elements all called resume:link:0
              // and broke the one-qid-one-element contract the DOM tests rely on.
              data-qid={`resume:${ns}:${(tok.v || String(i))
                .toLowerCase()
                .replace(/[^a-z0-9]+/g, '-')
                .replace(/^-+|-+$/g, '')
                .slice(0, 40)}`}
              data-qs-action="RESUME_OPEN_LINK"
              title={tok.v}
              {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
            >
              {tok.v}
            </a>
          );
        }
        if (tok.t === 'strong') return <strong key={i}>{tok.v}</strong>;
        if (tok.t === 'code') return <code key={i}>{tok.v}</code>;
        return <span key={i}>{tok.v}</span>;
      })}
    </>
  );
}

function SelectedImpactList({ items }: { items: Token[][] }) {
  return (
    <ul className="cv-impact-list">
      {items.map((item, i) => {
        if (item.length === 1 && item[0]?.t === 'text') {
          const text = item[0].v;
          const cut = text.indexOf(' — ');
          if (cut > 0) {
            return (
              <li key={i}>
                <strong>{text.slice(0, cut)}</strong>
                <span> — </span>
                <TextWithTechPills text={text.slice(cut + 3)} />
              </li>
            );
          }
        }
        return (
          <li key={i}><Inline tokens={item} /></li>
        );
      })}
    </ul>
  );
}

function EmployerQuickFacts() {
  return (
    <section className="cv-facts" aria-labelledby="cv-facts-title">
      <div className="cv-facts-head">
        <h2 id="cv-facts-title">Employer Quick Facts &amp; Eligibility</h2>
        <span className="cv-facts-status">
          <span aria-hidden="true" />
          Available for hire
        </span>
      </div>

      <ul className="cv-facts-chips" aria-label="Eligibility facts">
        <li>U.S. Citizen</li>
        <li>No Visa Sponsorship Required</li>
        <li>ITAR / EAR Compliant</li>
        <li>Clearable</li>
      </ul>

      <div className="cv-facts-context">
        <span>Earlier Commercial Contexts</span>
        <p>Sony · Adidas · X-Games · Disney · Microsoft · Toyota. Recent client and program detail is intentionally limited by export-control boundaries.</p>
      </div>

      <dl className="cv-facts-grid">
        <div>
          <dt>Target Roles</dt>
          <dd>Principal AI Engineer · AI Architect · Staff LLM Platform</dd>
        </div>
        <div>
          <dt>Engagement Preferences</dt>
          <dd>Full-time W-2 or Scoped 1099 R&amp;D Consulting</dd>
        </div>
        <div>
          <dt>Location &amp; Mobility</dt>
          <dd>Buffalo, NY (EST) · Remote / Hybrid · Onsite Briefings</dd>
        </div>
        <div>
          <dt>Start Notice</dt>
          <dd>Immediate to 2 Weeks</dd>
        </div>
      </dl>
    </section>
  );
}

/**
 * A competency line is "Cluster: term, term, term". On paper the labelled
 * bullet parses well for ATS, but on screen a bullet buries the label mid-line.
 * Splitting on the first colon gives a scannable label column without changing
 * the source, so the PDF and the page stay one document.
 */
function ClusterList({ items }: { items: Token[][] }) {
  return (
    <dl className="cv-clusters">
      {items.map((item, i) => {
        const first = item[0]?.v ?? '';
        const cut = first.indexOf(':');
        if (item[0]?.t !== 'text' || cut < 0) {
          return (
            <div key={i} className="cv-cluster">
              <dd><Inline tokens={item} /></dd>
            </div>
          );
        }
        const label = first.slice(0, cut);
        const rest: Token[] = [{ ...item[0], v: first.slice(cut + 1).trim() }, ...item.slice(1)];
        return (
          <div key={i} className="cv-cluster">
            <dt>{label}</dt>
            <dd><Inline tokens={rest} /></dd>
          </div>
        );
      })}
    </dl>
  );
}

function Blocks({
  blocks,
  clusters = false,
  selectedImpact = false,
}: {
  blocks: Block[];
  clusters?: boolean;
  selectedImpact?: boolean;
}) {
  return (
    <>
      {blocks.map((b, i) => {
        if (b.kind === 'p') return <p key={i}><Inline tokens={b.inline} /></p>;
        if (b.kind === 'ul') {
          if (selectedImpact) return <SelectedImpactList key={i} items={b.items} />;
          return clusters ? (
            <ClusterList key={i} items={b.items} />
          ) : (
            <ul key={i}>
              {b.items.map((item, j) => (
                <li key={j}><Inline tokens={item} /></li>
              ))}
            </ul>
          );
        }
        const roleTech = roleTechStack(b.title);
        return (
          <article key={i} className="cv-role">
            {/* The career rail lives on the roles themselves: one node per
                position, threading down the left of the experience list. No
                separate timeline band, so no duplicated dates and no truncated
                titles. */}
            <span className="cv-role-node" aria-hidden="true" />
            <h3><Inline tokens={b.title} /></h3>
            {b.period ? <p className="cv-period machine">{b.period}</p> : null}
            <Blocks blocks={b.blocks} />
            <RoleTechBadges skills={roleTech} />
          </article>
        );
      })}
    </>
  );
}

function PublicWorkSection({ section }: { section: ResumeSection }) {
  const introBlocks = section.blocks.filter((block) => block.kind !== 'ul');
  const items = section.blocks.flatMap((block) => block.kind === 'ul' ? block.items : []);

  return (
    <section className="cv-section cv-public-work">
      <h2>{section.title}</h2>
      <Blocks blocks={introBlocks} />
      <div className="cv-public-grid" aria-label="Public work repositories and project evidence">
        {items.map((item) => {
          const key = publicWorkTitle(item);
          const meta = PUBLIC_WORK_META[key] ?? { facts: 'Public work sample', tags: ['Public'] };
          const link = item.find((token) => token.t === 'link')?.href ?? meta.href;
          const title = meta.title ?? key;

          return (
            <article className="cv-public-card" key={key}>
              <div className="cv-public-card-head">
                <h3>
                  {link ? (
                    <a
                      href={link}
                      target="_blank"
                      rel="noopener noreferrer"
                      data-qid={`resume:public-work:${title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')}`}
                      data-qs-action="RESUME_OPEN_PUBLIC_WORK"
                      title={`Open ${title}`}
                    >
                      {title}
                    </a>
                  ) : title}
                </h3>
                <span className="cv-public-facts">{meta.facts}</span>
              </div>
              <p>{publicWorkDescription(item)}</p>
              <div className="cv-public-tags" aria-label={`${title} tags`}>
                {meta.tags.map((tag) => (
                  <TechPill key={tag}>{tag}</TechPill>
                ))}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export default function ResumePage() {
  const doc = resume as unknown as {
    name: string;
    contact: Token[];
    contactLines: Token[][];
    lede: string;
    intro: Block[];
    sections: ResumeSection[];
    downloads: { pdf: string; docx: string; markdown: string };
    sourceCommit: string;
    asOf: string;
    sourceSha256?: string;
    pdfBytes?: number;
    docxBytes?: number;
    jsonLd: unknown;
    timeline: { start: number; end: string; label: string; org: string }[];
  };
  const calendlyUrl = calendly.primarySchedulingUrl || calendly.user.schedulingUrl;
  const email = doc.contact.find((token) => token.href?.startsWith('mailto:'))?.v;

  return (
    <>
      {/* Every field is derived from RESUME.md by gen_resume.py, so the
          structured data cannot claim a title, location, or profile the
          resume itself does not. */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(doc.jsonLd) }}
      />
      <SiteNav hrefBase="/" />
      <main className="cv" id="top">
        <header className="cv-head">
          <h1>{doc.name}</h1>
          {doc.contactLines.map((line, i) => (
            <p key={i} className={i === 0 ? 'cv-contact cv-contact-where' : 'cv-contact'}>
              <Inline tokens={line} ns="contact" />
            </p>
          ))}
          {email ? (
            <div className="cv-contact-actions">
              <CopyEmailButton email={email} />
            </div>
          ) : null}
          {doc.lede ? <p className="cv-lede">{doc.lede}</p> : null}
        </header>

        {/* Sticky so the downloads stay one click away through a long scroll.
            These are real file links, not window.print(): browser export would
            substitute a different file per visitor. */}
        {/* The page is the full version; the attachable PDF/DOCX exports are
            the two-page cut. Saying so here replaces the PDF-only source line,
            which would be self-referential on the page it points at. */}
        <div className="cv-actions">
          <div className="cv-actions-row">
            <a
              className="cv-btn cv-btn-primary"
              href={doc.downloads.pdf}
              download
              data-qid="resume:link:pdf"
              data-qs-action="RESUME_DOWNLOAD_PDF"
              title="Download the résumé as a PDF"
            >
              <DownloadIcon />
              <span>Download PDF</span>
            </a>
            <a
              className="cv-btn"
              href={doc.downloads.docx}
              download
              data-qid="resume:link:docx"
              data-qs-action="RESUME_DOWNLOAD_DOCX"
              title="Download the résumé as an ATS-oriented DOCX"
            >
              <DocIcon />
              <span>DOCX</span>
            </a>
            <a
              className="cv-btn"
              href="/llms.txt"
              download
              data-qid="resume:link:markdown"
              data-qs-action="RESUME_DOWNLOAD_LLMS_TXT"
              title="Download the agent-readable llms.txt context"
            >
              <MarkdownIcon />
              <span>Markdown</span>
            </a>
            <CalendlyPopupLink
              className="cv-btn cv-btn-calendly"
              url={calendlyUrl}
              qid="resume:link:calendly"
            >
              <CalendarIcon />
              <span>Book time</span>
            </CalendlyPopupLink>
          </div>
          <p className="cv-actions-note">Full version — PDF/DOCX are specialized 2-page cuts</p>
        </div>

        <EmployerQuickFacts />

        {doc.intro.length ? <section className="cv-intro"><Blocks blocks={doc.intro} /></section> : null}

        {doc.sections.map((s) => (
          s.title.startsWith('PUBLIC WORK') ? (
            <PublicWorkSection key={s.title} section={s} />
          ) : (
          <section key={s.title} className="cv-section">
            <h2>{s.title}</h2>
            <Blocks
              blocks={s.blocks}
              clusters={s.title === 'CORE COMPETENCIES'}
              selectedImpact={s.title === 'SELECTED IMPACT'}
            />
            {s.title === 'DEEPER DETAIL' ? (
              <p className="cv-evidence-link">
                The generated discipline census is technical-inspector material, not
                resume reading.{' '}
                <a
                  href="/capabilities"
                  data-qid="resume:link:technical-capability-evidence"
                  data-qs-action="RESUME_OPEN_CAPABILITY_EVIDENCE"
                  title="Inspect generated discipline and capability evidence"
                >
                  Inspect technical capability evidence
                </a>
                .
              </p>
            ) : null}
          </section>
          )
        ))}

        {/* The build stamp is a receipt for the page, not part of the resume,
            so the print stylesheet drops it. */}
        <footer className="cv-foot">
          <p className="machine">
            Build receipt: static export · llms.txt indexed · source{' '}
            {/* Pinned to the commit, not to main, so the link always shows the
                exact source that produced this page rather than whatever the
                resume looks like today. */}
            <a
              href={`https://github.com/grahama1970/agent-skills/blob/${doc.sourceCommit}/RESUME.md`}
              target="_blank"
              rel="noopener noreferrer"
              data-qid="resume:link:source"
              data-qs-action="RESUME_OPEN_SOURCE"
              title="Open the RESUME.md this page was generated from"
            >
              RESUME.md
            </a>{' '}
            at commit{' '}
            <a
              href={`https://github.com/grahama1970/agent-skills/commit/${doc.sourceCommit}`}
              target="_blank"
              rel="noopener noreferrer"
              data-qid="resume:link:commit"
              data-qs-action="RESUME_OPEN_COMMIT"
              title={`Open commit ${doc.sourceCommit} on GitHub`}
            >
              {doc.sourceCommit}
            </a>
            {doc.pdfBytes ? <> · PDF {doc.pdfBytes.toLocaleString()} bytes</> : null}
            {doc.docxBytes ? <> · DOCX {doc.docxBytes.toLocaleString()} bytes</> : null}
            {doc.sourceSha256 ? <> · source SHA-256 {doc.sourceSha256.slice(0, 12)}</> : null}
            {' '}· <a href="/llms.txt" title="LLM-readable site context">LLM context</a>
            {' '}· <time dateTime={doc.asOf}>{doc.asOf}</time>
          </p>
        </footer>
      </main>
    </>
  );
}
