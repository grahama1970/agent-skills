'use client';

import { useEffect, useState } from 'react';

const LINKS = [
  { id: 'ledger', label: 'Inventory' },
  { id: 'work', label: 'Work' },
  { id: 'dream', label: 'Dream' },
  { id: 'receipts', label: 'Receipts' },
  { id: 'about', label: 'About' },
];

export function SiteNav() {
  const [active, setActive] = useState('');

  useEffect(() => {
    const spy = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(entry.target.id);
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
          grahama<span>.co</span>
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
