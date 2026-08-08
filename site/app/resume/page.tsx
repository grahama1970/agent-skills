import type { Metadata, Viewport } from 'next';
import { SiteNav } from '@/components/site-nav';
import resume from '@/resume.json';

/**
 * /resume — the formal, skimmable resume.
 *
 * Deliberately the calmest page on the site: no constellation, no motion, no
 * hero. A recruiter skimming for twenty seconds should meet a document, not an
 * exhibit. Every word comes from RESUME.md via scripts/gen_resume.py; nothing
 * is authored here. The PDF and Markdown exports are one click away because
 * the page is what you link, the file is what you attach.
 */

const title = 'Résumé — Graham Anderson';
const description =
  'Principal AI Engineer, ML Engineer, and AI Architect. Agentic AI, LLM/RAG, knowledge graphs, defense and aerospace. Download as PDF or Markdown.';

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: '/resume' },
  openGraph: {
    title,
    description,
    url: 'https://grahama.co/resume',
    siteName: 'grahama.co',
    type: 'profile',
    images: [{ url: '/og.png', width: 1200, height: 630, alt: 'grahama.co — Graham Anderson résumé' }],
  },
  twitter: { card: 'summary_large_image', title, description, images: ['/og.png'] },
};

// Matches --ink, so mobile browser chrome continues the page rather than
// bracketing it with a colour the design system does not contain.
export const viewport: Viewport = { themeColor: '#0c0908' };

type Token = { t: string; v: string; href?: string };
type Block =
  | { kind: 'p'; inline: Token[] }
  | { kind: 'ul'; items: Token[][] }
  | { kind: 'role'; title: Token[]; period: string; blocks: Block[] };

function Inline({ tokens }: { tokens: Token[] }) {
  return (
    <>
      {tokens.map((tok, i) => {
        if (tok.t === 'link') {
          const external = /^https?:\/\//.test(tok.href ?? '');
          return (
            <a
              key={i}
              href={tok.href}
              data-qid={`resume:link:${i}`}
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

function Blocks({ blocks }: { blocks: Block[] }) {
  return (
    <>
      {blocks.map((b, i) => {
        if (b.kind === 'p') return <p key={i}><Inline tokens={b.inline} /></p>;
        if (b.kind === 'ul')
          return (
            <ul key={i}>
              {b.items.map((item, j) => (
                <li key={j}><Inline tokens={item} /></li>
              ))}
            </ul>
          );
        return (
          <article key={i} className="cv-role">
            <h3><Inline tokens={b.title} /></h3>
            {b.period ? <p className="cv-period machine">{b.period}</p> : null}
            <Blocks blocks={b.blocks} />
          </article>
        );
      })}
    </>
  );
}

export default function ResumePage() {
  const doc = resume as unknown as {
    name: string;
    contact: Token[];
    lede: string;
    intro: Block[];
    sections: { title: string; blocks: Block[] }[];
    downloads: { pdf: string; markdown: string };
    sourceCommit: string;
    asOf: string;
    jsonLd: unknown;
  };

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
          <p className="cv-contact"><Inline tokens={doc.contact} /></p>
          {doc.lede ? <p className="cv-lede">{doc.lede}</p> : null}
        </header>

        {/* Sticky so the download stays one click away through a long scroll.
            Both are real file links, not window.print(): the PDF served here
            is the typeset, ATS-checked artifact, and a browser print-to-PDF
            would substitute a different file per visitor. */}
        <div className="cv-actions">
          <a
            className="cv-btn cv-btn-primary"
            href={doc.downloads.pdf}
            download
            data-qid="resume:link:pdf"
            data-qs-action="RESUME_DOWNLOAD_PDF"
            title="Download the résumé as a PDF"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" x2="12" y1="15" y2="3" />
            </svg>
            <span>Download PDF</span>
          </a>
          <a
            className="cv-btn"
            href={doc.downloads.markdown}
            download
            data-qid="resume:link:markdown"
            data-qs-action="RESUME_DOWNLOAD_MARKDOWN"
            title="Download the résumé as Markdown"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
              <path d="M14 2v4a2 2 0 0 0 2 2h4" />
              <path d="M10 9H8" />
              <path d="M16 13H8" />
              <path d="M16 17H8" />
            </svg>
            <span>Markdown</span>
          </a>
        </div>


        {doc.intro.length ? <section className="cv-intro"><Blocks blocks={doc.intro} /></section> : null}

        {doc.sections.map((s) => (
          <section key={s.title} className="cv-section">
            <h2>{s.title}</h2>
            <Blocks blocks={s.blocks} />
          </section>
        ))}

        {/* The build stamp is a receipt for the page, not part of the resume,
            so the print stylesheet drops it. */}
        <footer className="cv-foot">
          <p className="machine">
            Generated from{' '}
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
            at{' '}
            <a
              href={`https://github.com/grahama1970/agent-skills/commit/${doc.sourceCommit}`}
              target="_blank"
              rel="noopener noreferrer"
              data-qid="resume:link:commit"
              data-qs-action="RESUME_OPEN_COMMIT"
              title={`Open commit ${doc.sourceCommit} on GitHub`}
            >
              {doc.sourceCommit}
            </a>{' '}
            · <time dateTime={doc.asOf}>{doc.asOf}</time>
          </p>
        </footer>
      </main>
    </>
  );
}
