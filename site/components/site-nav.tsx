'use client';

import { useEffect, useState } from 'react';

const LINKS = [
  { id: 'work', label: 'Work' },
  { id: 'dream', label: 'Dream' },
  { id: 'ledger', label: 'Inventory' },
  { id: 'receipts', label: 'Receipts' },
  { id: 'about', label: 'About' },
];

export function SiteNav() {
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
          href="#top"
          data-qid="nav:link:home"
          data-qs-action="NAV_GOTO_TOP"
          title="Back to top"
        >
          <svg className="brandmark" viewBox="0 0 40 40" aria-hidden="true" focusable="false">
            <circle className="brandmark-ring" cx="20" cy="20" r="18" />
            <text className="brandmark-g" x="18.5" y="27" textAnchor="middle">
              G
              <tspan className="brandmark-c" dx="-2" dy="4">
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
              href={`#${l.id}`}
              data-qid={`nav:link:${l.id}`}
              data-qs-action={`NAV_GOTO_${l.id.toUpperCase()}`}
              title={`Go to ${l.label}`}
              aria-current={active === l.id ? 'page' : undefined}
              className={active === l.id ? 'is-active' : undefined}
            >
              {l.label}
            </a>
          ))}
          <a
            className="mailref"
            href="mailto:graham@grahama.co"
            data-qid="nav:link:email"
            data-qs-action="NAV_EMAIL"
            title="Email graham@grahama.co"
          >
            graham@grahama.co
          </a>
        </nav>
      </div>
    </header>
  );
}
