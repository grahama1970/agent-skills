'use client';

import { useEffect, useState } from 'react';

const LINKS = [
  { id: 'flagship', label: 'Work' },
  { id: 'supporting', label: 'Cases' },
  { id: 'proof-method', label: 'Proof' },
  { id: 'about', label: 'About' },
];

/**
 * `hrefBase` lets a subpage (e.g. /resume) reuse this nav: the section links
 * are homepage anchors, so from anywhere but `/` they must resolve to `/#id`
 * instead of a dead in-page fragment.
 */
export function SiteNav({ hrefBase = '' }: { hrefBase?: string }) {
  const [active, setActive] = useState('');

  useEffect(() => {
    const spy = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          // Only ids that have nav links may set the highlight — the hero
          // ('top') and closer must not wipe a J/K jump's active state.
          if (
            entry.isIntersecting &&
            LINKS.some((l) => l.id === entry.target.id)
          )
            setActive(entry.target.id);
        }
      },
      { rootMargin: '-20% 0px -70% 0px', threshold: 0 },
    );
    document.querySelectorAll('section[id]').forEach((s) => spy.observe(s));
    return () => spy.disconnect();
  }, []);

  return (
    <header className="topbar">
      <div className="wrap">
        <a
          className="wordmark"
          href={`${hrefBase}#top`}
          data-qid="nav:link:home"
          data-qs-action="NAV_GOTO_TOP"
          title="Back to top"
        >
          <svg className="brandmark" viewBox="0 0 40 40" aria-hidden="true" focusable="false">
            <circle className="brandmark-ring" cx="20" cy="20" r="18" />
            <text className="brandmark-g" x="18.5" y="27" textAnchor="middle">
              G
              <tspan className="brandmark-c" dx="-0.5" dy="4">
                c
              </tspan>
            </text>
          </svg>
          <span className="wordmark-text">
            grahama<span>.co</span>
          </span>
        </a>
        <nav className="nav" aria-label="Primary">
          {LINKS.map((l) => (
            <a
              key={l.id}
              href={`${hrefBase}#${l.id}`}
              data-qid={`nav:link:${l.id}`}
              data-qs-action={`NAV_GOTO_${l.id.toUpperCase()}`}
              title={`Go to ${l.label}`}
              aria-current={active === l.id ? 'page' : undefined}
              className={active === l.id ? 'is-active' : undefined}
            >
              {l.label}
            </a>
          ))}
          <span className="nav-icons">
            <a
              className="nav-icon"
              href="mailto:graham@grahama.co"
              data-qid="nav:link:email"
              data-qs-action="NAV_EMAIL"
              title="Email graham@grahama.co"
              aria-label="Email graham@grahama.co"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect width="20" height="16" x="2" y="4" rx="2" />
                <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
              </svg>
            </a>
            <a
              className="nav-icon"
              href="https://github.com/grahama1970/agent-skills"
              target="_blank"
              rel="noopener noreferrer"
              data-qid="nav:link:github"
              data-qs-action="NAV_GITHUB"
              title="Open the agent-skills repository"
              aria-label="Open the agent-skills repository"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.4 5.4 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
                <path d="M9 18c-4.51 2-5-2-7-2" />
              </svg>
            </a>
            <a
              className="nav-icon"
              href="https://www.linkedin.com/in/grahamanderson/"
              target="_blank"
              rel="noopener noreferrer"
              data-qid="nav:link:linkedin"
              data-qs-action="NAV_LINKEDIN"
              title="LinkedIn — Graham Anderson"
              aria-label="LinkedIn"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z" />
                <rect width="4" height="12" x="2" y="9" />
                <circle cx="4" cy="4" r="2" />
              </svg>
            </a>
            <a
              className="nav-icon"
              href="/resume"
              data-qid="nav:link:resume"
              data-qs-action="NAV_RESUME"
              title="Résumé"
              aria-label="Résumé"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
                <path d="M14 2v4a2 2 0 0 0 2 2h4" />
                <path d="M16 13H8" />
                <path d="M16 17H8" />
                <path d="M10 9H8" />
              </svg>
            </a>
          </span>
        </nav>
      </div>
    </header>
  );
}
